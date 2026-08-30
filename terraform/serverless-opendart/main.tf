locals {
  enabled = var.deployment_stage != "disabled"
  runtime = var.deployment_stage == "runtime"

  common_tags = {
    Project         = "jcareer"
    jk_layer        = "asis-serverless-opendart-demo"
    jk_purpose      = "on-demand-public-company-facts"
    jk_approval_ref = var.approval_ref
  }
}

resource "aws_ecr_repository" "worker" {
  count = local.enabled ? 1 : 0

  name                 = "${var.name_prefix}-worker"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_OPENDART_SERVERLESS_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref))
      )
      error_message = "OpenDART serverless resources require a separate human acknowledgement and approval reference."
    }
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "worker" {
  count = local.enabled ? 1 : 0

  repository = aws_ecr_repository.worker[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the newest five immutable worker images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_sqs_queue" "dead_letter" {
  count = local.enabled ? 1 : 0

  name                        = "${var.name_prefix}-dead-letter.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  sqs_managed_sse_enabled     = true
  message_retention_seconds   = 1209600

  tags = local.common_tags
}

resource "aws_sqs_queue" "refresh" {
  count = local.enabled ? 1 : 0

  name                        = "${var.name_prefix}-refresh.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  sqs_managed_sse_enabled     = true
  message_retention_seconds   = 86400
  visibility_timeout_seconds  = 180
  receive_wait_time_seconds   = 10
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter[0].arn
    maxReceiveCount     = 4
  })

  tags = local.common_tags
}

resource "aws_dynamodb_table" "results" {
  count = local.enabled ? 1 : 0

  name         = "${var.name_prefix}-results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute {
    name = "request_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  count = local.enabled ? 1 : 0

  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_iam_role" "worker" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-worker"
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

resource "aws_iam_role_policy" "worker" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-worker"
  role = aws_iam_role.worker[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid    = "ConsumeOnlyRefreshQueue"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.refresh[0].arn
      },
      {
        Sid      = "WriteCreateOnlyResult"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = aws_dynamodb_table.results[0].arn
      },
      {
        Sid      = "ReadOnlyApprovedApiKeyParameter"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter"]
        Resource = var.opendart_api_key_parameter_arn
      },
      {
        Sid      = "WriteBoundedFunctionLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.worker[0].arn}:*"
      },
      ], var.opendart_api_key_kms_key_arn != "" ? [
      {
        Sid      = "DecryptOnlyApprovedParameterKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.opendart_api_key_kms_key_arn
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com"
          }
          StringLike = {
            "kms:EncryptionContext:PARAMETER_ARN" = var.opendart_api_key_parameter_arn
          }
        }
      }
    ] : [])
  })

  lifecycle {
    precondition {
      condition = (
        !local.enabled ||
        (
          var.opendart_api_key_parameter_name != "" &&
          can(regex("^arn:aws:ssm:ap-northeast-2:[0-9]{12}:parameter/.+", var.opendart_api_key_parameter_arn))
        )
      )
      error_message = "bootstrap/runtime require an existing SecureString parameter name and its exact ap-northeast-2 ARN."
    }
  }
}

resource "aws_lambda_function" "worker" {
  count = local.runtime ? 1 : 0

  function_name = "${var.name_prefix}-worker"
  role          = aws_iam_role.worker[0].arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  timeout       = 30
  memory_size   = 512
  architectures = ["x86_64"]

  reserved_concurrent_executions = 1

  environment {
    variables = {
      OPENDART_API_KEY_PARAMETER_NAME = var.opendart_api_key_parameter_name
      OPENDART_RESULT_TABLE           = aws_dynamodb_table.results[0].name
      OPENDART_RESULT_TTL_SECONDS     = tostring(var.result_ttl_seconds)
    }
  }

  lifecycle {
    precondition {
      condition = (
        startswith(var.lambda_image_uri, "${aws_ecr_repository.worker[0].repository_url}@sha256:") &&
        can(regex("@sha256:[0-9a-f]{64}$", var.lambda_image_uri))
      )
      error_message = "runtime requires a digest-pinned worker image from this root's ECR repository."
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.worker,
    aws_iam_role_policy.worker,
  ]

  tags = local.common_tags
}

resource "aws_lambda_event_source_mapping" "refresh" {
  count = local.runtime ? 1 : 0

  event_source_arn                   = aws_sqs_queue.refresh[0].arn
  function_name                      = aws_lambda_function.worker[0].arn
  batch_size                         = 5
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
  enabled                            = true
}

resource "aws_iam_role_policy" "api" {
  count = local.runtime ? 1 : 0

  name = "${var.name_prefix}-api-dispatch-collect"
  role = var.api_sender_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SendOnlyRefreshRequests"
        Effect   = "Allow"
        Action   = ["sqs:GetQueueUrl", "sqs:SendMessage"]
        Resource = aws_sqs_queue.refresh[0].arn
      },
      {
        Sid      = "CollectAndRemoveBoundResults"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.results[0].arn
      },
    ]
  })

  lifecycle {
    precondition {
      condition     = var.api_sender_role_name != ""
      error_message = "runtime requires the existing API EC2 role name."
    }
  }
}
