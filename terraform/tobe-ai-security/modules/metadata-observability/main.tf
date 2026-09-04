locals {
  publisher_channels = {
    "llm-gateway" = {
      log_group_suffix = "llm-gateway-metadata"
      s3_prefix        = "records/llm-gateway"
      dynamodb_prefix  = "llm-gateway#"
    }
    "capability-broker" = {
      log_group_suffix = "capability-broker-metadata"
      s3_prefix        = "records/capability-broker"
      dynamodb_prefix  = "capability-broker#"
    }
  }

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

  account_id = try(data.aws_caller_identity.current[0].account_id, join("", ["000000", "000000"]))
  partition  = try(data.aws_partition.current[0].partition, "aws")
  trail_name = "${var.name_prefix}-metadata-audit"
  trail_arn  = "arn:${local.partition}:cloudtrail:${var.aws_region}:${local.account_id}:trail/${local.trail_name}"

  required_tags = {
    jk_layer    = "tobe"
    control_id  = "T.2.1,T.2.2,T.2.3,T.7.1,T.7.2,T.8.1,T.8.2"
    gap_id      = "NF-02,NF-04,NF-06"
    evidence_id = "EXPECTED-METADATA-EVIDENCE"
    status      = "PROPOSED_CONTROL_NOT_VERIFIED"
  }

  tags = merge(var.additional_tags, local.required_tags, {
    approval_ref        = var.approval_ref
    component           = "metadata-observability"
    data_classification = "metadata-only"
  })
}

data "aws_caller_identity" "current" {
  count = var.enable ? 1 : 0
}

data "aws_partition" "current" {
  count = var.enable ? 1 : 0
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

    precondition {
      condition = (
        toset(keys(var.publisher_roles)) == toset(keys(local.publisher_channels)) &&
        length(toset(values(var.publisher_roles))) == 2
      )
      error_message = "Exactly two distinct mapped roles are required: llm-gateway and capability-broker."
    }
  }
}

resource "aws_kms_key" "evidence" {
  count = var.enable ? 1 : 0

  description             = "PROPOSED / NOT DEPLOYED key for de-identified metadata evidence."
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DelegateAdministrationToAccount"
        Effect = "Allow"
        Principal = {
          AWS = "arn:${local.partition}:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsForApprovedGroups"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:/${var.name_prefix}/*"
          }
        }
      },
      {
        Sid    = "AllowCloudTrailEncryption"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action = [
          # Required when CloudTrail writes to an SSE-KMS bucket with S3 Bucket Keys.
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:SourceArn"                            = local.trail_arn
            "kms:EncryptionContext:aws:cloudtrail:arn" = local.trail_arn
          }
        }
      },
    ]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-metadata-evidence"
  })

  # Object-Locked evidence, audit objects, logs, and the DynamoDB index all
  # depend on this key. Retirement requires a dedicated, evidence-backed
  # migration and must never be coupled to a component-disable change.
  lifecycle {
    prevent_destroy = true
  }

  depends_on = [terraform_data.activation_gate]
}

resource "aws_kms_alias" "evidence" {
  count = var.enable ? 1 : 0

  name          = "alias/${var.name_prefix}-metadata-evidence"
  target_key_id = aws_kms_key.evidence[0].key_id
}

resource "aws_cloudwatch_log_group" "metadata" {
  for_each = var.enable ? local.publisher_channels : {}

  name              = "/${var.name_prefix}/${each.value.log_group_suffix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.evidence[0].arn

  tags = merge(local.tags, {
    Name         = "${var.name_prefix}-${each.value.log_group_suffix}"
    content_rule = "NO_RAW_PROMPT_OR_RESPONSE"
  })

  depends_on = [
    aws_kms_key.evidence,
    terraform_data.activation_gate,
  ]
}

resource "aws_cloudwatch_log_group" "cloudtrail" {
  count = var.enable ? 1 : 0

  name              = "/${var.name_prefix}/cloudtrail-metadata-audit"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.evidence[0].arn

  tags = merge(local.tags, {
    Name         = "${var.name_prefix}-cloudtrail-metadata-audit"
    content_rule = "CONTROL_PLANE_AND_SELECTED_DATA_EVENTS"
  })

  depends_on = [aws_kms_key.evidence]
}

resource "aws_iam_role" "cloudtrail_to_logs" {
  count = var.enable ? 1 : 0

  name = "${var.name_prefix}-cloudtrail-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "CloudTrailAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "cloudtrail.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceArn" = local.trail_arn
        }
      }
    }]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-cloudtrail-logs"
  })
}

resource "aws_iam_role_policy" "cloudtrail_to_logs" {
  count = var.enable ? 1 : 0

  name = "${var.name_prefix}-cloudtrail-logs"
  role = aws_iam_role.cloudtrail_to_logs[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "WriteOnlyApprovedCloudTrailLogGroup"
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"
    }]
  })
}

resource "aws_cloudwatch_log_metric_filter" "guardrail_block" {
  count = var.enable ? 1 : 0

  name           = "${var.name_prefix}-guardrail-block"
  pattern        = "{ $.guardrail_action = \"BLOCKED\" }"
  log_group_name = aws_cloudwatch_log_group.metadata["llm-gateway"].name

  metric_transformation {
    name          = "GuardrailBlocked"
    namespace     = "JCareer/AI/Security"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "guardrail_block" {
  count = var.enable ? 1 : 0

  alarm_name          = "${var.name_prefix}-guardrail-block"
  alarm_description   = "PROPOSED alarm for repeated Bedrock guardrail blocks; response owner and routing remain approval gates."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = var.guardrail_block_alarm_threshold
  metric_name         = "GuardrailBlocked"
  namespace           = "JCareer/AI/Security"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-guardrail-block"
  })
}

resource "aws_s3_bucket" "evidence" {
  count = var.enable ? 1 : 0

  bucket_prefix       = "${var.name_prefix}-evidence-"
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

# CloudTrail uses a separate bucket because its service delivery does not set
# the metadata-only object tag required by the application evidence bucket.
resource "aws_s3_bucket" "audit" {
  count = var.enable ? 1 : 0

  bucket_prefix = "${var.name_prefix}-audit-"
  force_destroy = false

  tags = merge(local.tags, {
    Name                = "${var.name_prefix}-cloudtrail-audit"
    data_classification = "security-audit-metadata"
  })
}

resource "aws_s3_bucket_ownership_controls" "audit" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.audit[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  count = var.enable ? 1 : 0

  bucket                  = aws_s3_bucket.audit[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "audit" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.audit[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.audit[0].id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.evidence[0].arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.audit[0].id

  rule {
    id     = "bounded-cloudtrail-retention"
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

  depends_on = [aws_s3_bucket_versioning.audit]
}

resource "aws_s3_bucket_policy" "audit" {
  count = var.enable ? 1 : 0

  bucket = aws_s3_bucket.audit[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.audit[0].arn
        Condition = {
          StringEquals = {
            "aws:SourceArn" = local.trail_arn
          }
        }
      },
      {
        Sid    = "CloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.audit[0].arn}/cloudtrail/AWSLogs/${local.account_id}/*"
        Condition = {
          StringEquals = {
            "aws:SourceArn" = local.trail_arn
            "s3:x-amz-acl"  = "bucket-owner-full-control"
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.audit[0].arn,
          "${aws_s3_bucket.audit[0].arn}/*",
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.audit,
    aws_s3_bucket_server_side_encryption_configuration.audit,
  ]
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

resource "aws_iam_policy" "metadata_publisher" {
  for_each = var.enable ? local.publisher_channels : {}

  name        = "${var.name_prefix}-${each.key}-metadata-publisher"
  description = "PROPOSED ${each.key}-only publication of allowlisted metadata to its log, object prefix, and index partition."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "WriteOwnMetadataLog"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.metadata[each.key].arn}:*"
      },
      {
        Sid      = "WriteOwnTaggedEncryptedEvidenceObjects"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.evidence[0].arn}/${each.value.s3_prefix}/*"
        Condition = {
          StringEquals = {
            "s3:RequestObjectTag/jk-data-class"              = "metadata-only"
            "s3:x-amz-server-side-encryption"                = "aws:kms"
            "s3:x-amz-server-side-encryption-aws-kms-key-id" = aws_kms_key.evidence[0].arn
          }
        }
      },
      {
        Sid      = "WriteOwnEvidenceIndexPartition"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.evidence_index[0].arn
        Condition = {
          "ForAllValues:StringLike" = {
            "dynamodb:LeadingKeys" = ["${each.value.dynamodb_prefix}*"]
          }
        }
      },
      {
        Sid      = "UseEvidenceKeyViaApprovedServices"
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.evidence[0].arn
        Condition = {
          StringEquals = {
            "kms:ViaService" = [
              "dynamodb.${var.aws_region}.amazonaws.com",
              "s3.${var.aws_region}.amazonaws.com",
            ]
          }
        }
      },
    ]
  })

  tags = merge(local.tags, {
    Name = "${var.name_prefix}-${each.key}-metadata-publisher"
  })
}

resource "aws_iam_role_policy_attachment" "metadata_publisher" {
  for_each = var.enable ? local.publisher_channels : {}

  policy_arn = aws_iam_policy.metadata_publisher[each.key].arn
  role       = var.publisher_roles[each.key]
}

resource "aws_cloudtrail" "metadata_audit" {
  count = var.enable ? 1 : 0

  name                          = local.trail_name
  s3_bucket_name                = aws_s3_bucket.audit[0].id
  s3_key_prefix                 = "cloudtrail"
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  enable_logging                = true
  kms_key_id                    = aws_kms_key.evidence[0].arn
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail[0].arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_to_logs[0].arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["${aws_s3_bucket.evidence[0].arn}/"]
    }

    data_resource {
      type   = "AWS::DynamoDB::Table"
      values = [aws_dynamodb_table.evidence_index[0].arn]
    }
  }

  tags = merge(local.tags, {
    Name = local.trail_name
  })

  depends_on = [
    aws_iam_role_policy.cloudtrail_to_logs,
    aws_s3_bucket_policy.audit,
  ]
}
