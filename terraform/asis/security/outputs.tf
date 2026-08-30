# terraform/asis/security — 출력
#
# 출력은 식별자만 내보낸다. 충족/미충족·잔여위험 같은 판정값은 내보내지 않는다.
# 판정은 사람이 docs/current/CONTROL_ASSESSMENT.yaml 에서 한다 (AGENTS.md §0 · §4).

output "ssm_interface_endpoint_ids" {
  description = "SSM 계열 interface endpoint ID 맵 (ssm · ssmmessages · ec2messages)."
  value       = { for k, v in aws_vpc_endpoint.ssm : k => v.id }
}

output "ssm_interface_endpoint_arns" {
  description = "SSM 계열 interface endpoint ARN 맵."
  value       = { for k, v in aws_vpc_endpoint.ssm : k => v.arn }
}

output "ecs_task_execution_role_arn" {
  description = "ECS 태스크 정의의 execution_role_arn 에 배선한다. compute 모듈이 쓴다."
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_execution_role_name" {
  description = "ECS task execution role 이름."
  value       = aws_iam_role.ecs_task_execution.name
}

output "ecs_task_role_arn" {
  description = "ECS 태스크 정의의 task_role_arn 에 배선한다. compute 모듈이 쓴다."
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_role_name" {
  description = "ECS task role 이름."
  value       = aws_iam_role.ecs_task.name
}

output "vpc_flow_logs_role_arn" {
  description = "aws_flow_log 의 iam_role_arn 에 배선한다. observability 모듈이 쓴다."
  value       = aws_iam_role.vpc_flow_logs.arn
}
