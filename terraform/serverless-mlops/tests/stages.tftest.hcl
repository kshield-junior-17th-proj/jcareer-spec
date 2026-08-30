mock_provider "aws" {
  override_resource {
    target = aws_ecr_repository.mlops
    values = {
      repository_url = "registry.example.invalid/jcareer-asis-mlops-lambda"
    }
  }
}

run "disabled_plans_zero" {
  command = plan

  assert {
    condition = (
      length(aws_ecr_repository.mlops) == 0 &&
      length(aws_ecr_lifecycle_policy.mlops) == 0 &&
      length(aws_s3_bucket.artifacts) == 0 &&
      length(aws_s3_bucket_public_access_block.artifacts) == 0 &&
      length(aws_s3_bucket_policy.artifacts) == 0 &&
      length(aws_s3_bucket_ownership_controls.artifacts) == 0 &&
      length(aws_s3_bucket_server_side_encryption_configuration.artifacts) == 0 &&
      length(aws_s3_bucket_versioning.artifacts) == 0 &&
      length(aws_s3_bucket_lifecycle_configuration.artifacts) == 0 &&
      length(aws_dynamodb_table.runs) == 0 &&
      length(aws_cloudwatch_log_group.mlops) == 0 &&
      length(aws_iam_role.lambda) == 0 &&
      length(aws_iam_role_policy.lambda) == 0 &&
      length(aws_lambda_function.trainer) == 0
    )
    error_message = "disabled must plan exactly zero managed resources"
  }
}

run "bootstrap_plans_thirteen" {
  command = plan

  variables {
    deployment_stage           = "bootstrap"
    activation_acknowledgement = "JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED"
    artifact_bucket_name       = "jcareer-synthetic-mlops-test-000000"
  }

  assert {
    condition = (
      length(aws_ecr_repository.mlops) +
      length(aws_ecr_lifecycle_policy.mlops) +
      length(aws_s3_bucket.artifacts) +
      length(aws_s3_bucket_public_access_block.artifacts) +
      length(aws_s3_bucket_policy.artifacts) +
      length(aws_s3_bucket_ownership_controls.artifacts) +
      length(aws_s3_bucket_server_side_encryption_configuration.artifacts) +
      length(aws_s3_bucket_versioning.artifacts) +
      length(aws_s3_bucket_lifecycle_configuration.artifacts) +
      length(aws_dynamodb_table.runs) +
      length(aws_cloudwatch_log_group.mlops) +
      length(aws_iam_role.lambda) +
      length(aws_iam_role_policy.lambda) == 13 &&
      length(aws_lambda_function.trainer) == 0
    )
    error_message = "bootstrap must plan exactly thirteen managed resources and no Lambda"
  }
}

run "runtime_plans_fourteen" {
  command = plan

  variables {
    deployment_stage           = "runtime"
    activation_acknowledgement = "JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED"
    artifact_bucket_name       = "jcareer-synthetic-mlops-test-000000"
    lambda_image_uri           = "registry.example.invalid/jcareer-asis-mlops-lambda@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }

  assert {
    condition = (
      length(aws_ecr_repository.mlops) +
      length(aws_ecr_lifecycle_policy.mlops) +
      length(aws_s3_bucket.artifacts) +
      length(aws_s3_bucket_public_access_block.artifacts) +
      length(aws_s3_bucket_policy.artifacts) +
      length(aws_s3_bucket_ownership_controls.artifacts) +
      length(aws_s3_bucket_server_side_encryption_configuration.artifacts) +
      length(aws_s3_bucket_versioning.artifacts) +
      length(aws_s3_bucket_lifecycle_configuration.artifacts) +
      length(aws_dynamodb_table.runs) +
      length(aws_cloudwatch_log_group.mlops) +
      length(aws_iam_role.lambda) +
      length(aws_iam_role_policy.lambda) +
      length(aws_lambda_function.trainer) == 14
    )
    error_message = "runtime must plan exactly fourteen managed resources"
  }
}
