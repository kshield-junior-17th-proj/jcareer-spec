output "cloudtrail_id" {
  description = "ID of the management-events-only CloudTrail trail."
  value       = aws_cloudtrail.this.id
}

output "cloudtrail_arn" {
  description = "ARN of the management-events-only CloudTrail trail."
  value       = aws_cloudtrail.this.arn
}

output "cloudwatch_log_group_names" {
  description = "Names of the AS-IS CloudWatch log groups."
  value = {
    access     = aws_cloudwatch_log_group.access.name
    flow       = aws_cloudwatch_log_group.flow.name
    prompt_raw = aws_cloudwatch_log_group.prompt_raw.name
  }
}

output "cloudwatch_log_group_arns" {
  description = "ARNs of the AS-IS CloudWatch log groups."
  value = {
    access     = aws_cloudwatch_log_group.access.arn
    flow       = aws_cloudwatch_log_group.flow.arn
    prompt_raw = aws_cloudwatch_log_group.prompt_raw.arn
  }
}

output "vpc_flow_log_id" {
  description = "ID of the VPC Flow Log."
  value       = aws_flow_log.vpc.id
}

output "guardduty_detector_id" {
  description = "ID of the GuardDuty detector."
  value       = aws_guardduty_detector.this.id
}
