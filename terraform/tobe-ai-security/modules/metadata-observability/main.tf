locals {
  log_groups = toset([
    "llm-gateway-metadata",
    "capability-broker-metadata",
  ])

  permitted_metadata_fields = [
    "correlation_id",
    "event_type",
    "guardrail_action",
    "latency_ms",
    "model_id_digest",
    "policy_version",
    "request_bytes",
    "response_bytes",
    "result_status",
    "schema_version",
    "tenant_ref_digest",
    "timestamp",
  ]

  required_tags = {
    jk_layer    = "tobe"
    control_id  = "T.2.1,T.2.2,T.2.3,T.7.1,T.7.2,T.8.1,T.8.2"
    gap_id      = "NF-02,NF-04,NF-06"
    evidence_id = "EXPECTED-METADATA-EVIDENCE"
    status      = "PROPOSED_NOT_DEPLOYED"
  }

  tags = merge(var.additional_tags, local.required_tags, {
    approval_ref       = var.approval_ref
    component          = "metadata-observability"
    data_classification = "metadata-only"
  })
}

resource "terraform_data" "activation_gate" {
  count = var.enable ? 1 : 0

  lifecycle {
    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_TOBE_AI_SECURITY_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
      )
      error_message = "The metadata/evidence module requires explicit human approval before activation."
    }

    precondition {
      condition     = var.evidence_expiration_days > var.evidence_lock_days
      error_message = "Evidence expiration must be later than the Object Lock retention period."
    }
  }
}

resource "aws_kms_key" "evidence" {
  count = var.enable ? 1 : 0

  description             = "PROPOSED / NOT DEPLOYED key for de-identified metadata evidence."
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-metadata-evidence"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_kms_alias" "evidence" {
  count = var.enable ? 1 : 0

  name          = "alias/${var.name_prefix}-metadata-evidence"
  target_key_id = aws_kms_key.evidence[0].key_id
}

resource "aws_cloudwatch_log_group" "metadata" {
  for_each = var.enable ? local.log_groups : toset([])

  name              = "/${var.name_prefix}/${each.value}"
  retention_in_days = var.log_retention_days

  tags = merge(local.tags, {
    Name        = "${var.name_prefix}-${each.value}"
    content_rule = "NO_RAW_PROMPT_OR_RESPONSE"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_s3_bucket" "evidence" {
  count = var.enable ? 1 : 0

  bucket_prefix       = "${var.name_prefix}-metadata-evidence-"
  force_destroy       = false
  object_lock_enabled = true

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-metadata-evidence"
  })

  depends_on = [terraform_data.activation_gate]
}

resource "aws_s3_bucket_ownership_controls" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  count = var.enable ? 1 : 0

  bucket                  = aws_s3_bucket.evidence[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.evidence[0].arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id

  rule {
    default_retention {
      days = var.evidence_lock_days
      mode = "COMPLIANCE"
    }
  }

  depends_on = [aws_s3_bucket_versioning.evidence]
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id

  rule {
    id     = "bounded-metadata-evidence-retention"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    expiration {
      days = var.evidence_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.evidence_expiration_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.evidence]
}

resource "aws_s3_bucket_policy" "evidence" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.evidence[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.evidence[0].arn,
          "${aws_s3_bucket.evidence[0].arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "DenyMissingKmsEncryption"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.evidence[0].arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      },
      {
        Sid       = "DenyWrongKmsKey"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.evidence[0].arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption-aws-kms-key-id" = aws_kms_key.evidence[0].arn
          }
        }
      },
      {
        Sid       = "DenyMissingMetadataOnlyAssertion"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.evidence[0].arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:RequestObjectTag/jk-data-class" = "metadata-only"
          }
        }
      },
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.evidence,
    aws_s3_bucket_server_side_encryption_configuration.evidence,
  ]
}

resource "aws_dynamodb_table" "evidence_index" {
  count = var.enable ? 1 : 0

  name                        = "${var.name_prefix}-evidence-index"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "evidence_id"
  range_key                   = "recorded_at"
  deletion_protection_enabled = true
  stream_enabled              = true
  stream_view_type            = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "evidence_id"
    type = "S"
  }

  attribute {
    name = "recorded_at"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.evidence[0].arn
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-evidence-index"
  })

  depends_on = [terraform_data.activation_gate]
}
