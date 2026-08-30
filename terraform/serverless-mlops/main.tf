locals {
  enabled = var.deployment_stage != "disabled"
  runtime = var.deployment_stage == "runtime"

  source_prefix = "mlops/sources/"
  result_prefix = "mlops/runs/"

  common_tags = {
    Project    = "jcareer"
    jk_layer   = "asis-serverless-mlops-demo"
    jk_purpose = "synthetic-feature-snapshot-training"
  }
}

resource "aws_ecr_repository" "mlops" {
  count = local.enabled ? 1 : 0

  name                 = "${var.name_prefix}-lambda"
  image_tag_mutability = "IMMUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    precondition {
      condition     = var.activation_acknowledgement == "JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED"
      error_message = "The serverless MLOps root is fail-closed until explicit human acknowledgement."
    }
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "mlops" {
  count = local.enabled ? 1 : 0

  repository = aws_ecr_repository.mlops[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the newest five immutable demo images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_s3_bucket" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket        = var.artifact_bucket_name
  force_destroy = false

  lifecycle {
    precondition {
      condition     = var.artifact_bucket_name != ""
      error_message = "artifact_bucket_name is required for bootstrap and runtime stages."
    }
  }

  tags = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket                  = aws_s3_bucket.artifacts[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.artifacts[0].arn,
        "${aws_s3_bucket.artifacts[0].arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.artifacts]
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  count = local.enabled ? 1 : 0

  bucket = aws_s3_bucket.artifacts[0].id
  rule {
    id     = "expire-synthetic-mlops-material"
    status = "Enabled"

    filter {
      prefix = "mlops/"
    }

    expiration {
      days = var.artifact_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.artifact_retention_days
    }
  }

  depends_on = [aws_s3_bucket_versioning.artifacts]
}

resource "aws_dynamodb_table" "runs" {
  count = local.enabled ? 1 : 0

  name         = "${var.name_prefix}-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "mlops" {
  count = local.enabled ? 1 : 0

  name              = "/aws/lambda/${var.name_prefix}-trainer"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_iam_role" "lambda" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "lambda" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-runtime"
  role = aws_iam_role.lambda[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadFeatureOnlySourcePackages"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.artifacts[0].arn}/${local.source_prefix}*"
      },
      {
        Sid      = "WriteVersionedSyntheticResults"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.artifacts[0].arn}/${local.result_prefix}*"
      },
      {
        Sid      = "WriteRunState"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.runs[0].arn
      },
      {
        Sid      = "WriteBoundedFunctionLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.mlops[0].arn}:*"
      },
    ]
  })
}

resource "aws_lambda_function" "trainer" {
  count = local.runtime ? 1 : 0

  function_name = "${var.name_prefix}-trainer"
  role          = aws_iam_role.lambda[0].arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  timeout       = 300
  memory_size   = var.lambda_memory_mb
  architectures = ["x86_64"]

  reserved_concurrent_executions = 1

  ephemeral_storage {
    size = 1024
  }

  environment {
    variables = {
      ALLOW_SYNTHETIC_MLOPS_RUN     = "JCAREER_SYNTHETIC_SERVERLESS_MLOPS"
      MLOPS_SYNTHETIC_ATTESTATION   = "JCAREER_SYNTHETIC_ONLY"
      MLOPS_SOURCE_MODE             = "feature_snapshot"
      MLOPS_FEATURE_SNAPSHOT_BUCKET = aws_s3_bucket.artifacts[0].bucket
      MLOPS_FEATURE_SNAPSHOT_ROOT   = trimsuffix(local.source_prefix, "/")
      MLOPS_ARTIFACT_BUCKET         = aws_s3_bucket.artifacts[0].bucket
      MLOPS_RUN_TABLE               = aws_dynamodb_table.runs[0].name
      MLOPS_EPOCHS                  = tostring(var.mlops_epochs)
    }
  }

  lifecycle {
    precondition {
      condition = startswith(
        var.lambda_image_uri,
        "${aws_ecr_repository.mlops[0].repository_url}@sha256:"
      ) && can(regex("@sha256:[0-9a-f]{64}$", var.lambda_image_uri))
      error_message = "runtime stage requires a digest-pinned image from the ECR repository managed by this root."
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.mlops,
    aws_iam_role_policy.lambda,
  ]

  tags = local.common_tags
}
