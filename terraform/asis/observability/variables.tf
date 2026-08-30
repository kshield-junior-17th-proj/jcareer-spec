variable "region" {
  description = "AWS region represented by this AS-IS module."
  type        = string
  default     = "ap-northeast-2"
}

variable "name_prefix" {
  description = "Prefix used for observability resource names."
  type        = string
  default     = "jcareer-asis"
}

variable "cloudtrail_s3_bucket_id" {
  description = "ID (bucket name) of the externally managed S3 bucket used by CloudTrail."
  type        = string
}

variable "flow_log_iam_role_arn" {
  description = "ARN of the externally managed IAM role that lets VPC Flow Logs publish to CloudWatch Logs."
  type        = string
}

variable "vpc_id" {
  description = "ID of the externally managed VPC for which flow logs are recorded."
  type        = string
}

variable "tags" {
  description = "Additional tags. Required AS-IS evidence tags take precedence."
  type        = map(string)
  default     = {}
}
