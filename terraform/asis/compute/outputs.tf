output "alb_arn" {
  description = "Public application load balancer ARN."
  value       = aws_lb.public.arn
}

output "alb_dns_name" {
  description = "Public application load balancer DNS name."
  value       = aws_lb.public.dns_name
}

output "alb_zone_id" {
  description = "Route 53 alias 연결에 사용할 ALB hosted zone ID."
  value       = aws_lb.public.zone_id
}

output "https_listener_arn" {
  description = "TLS 1.2+ HTTPS listener ARN."
  value       = aws_lb_listener.https.arn
}

output "target_group_arns" {
  description = "서비스별 ALB target group ARN."
  value       = { for name, target_group in aws_lb_target_group.service : name => target_group.arn }
}

output "route_path_patterns" {
  description = "HTTPS listener의 서비스별 path pattern."
  value       = { for name, service in local.services : name => service.path_patterns }
}

output "ecs_cluster_arn" {
  description = "ECS Fargate cluster ARN."
  value       = aws_ecs_cluster.main.arn
}

output "ecs_cluster_name" {
  description = "ECS Fargate cluster 이름."
  value       = aws_ecs_cluster.main.name
}

output "task_definition_arns" {
  description = "서비스별 ECS task definition ARN."
  value       = { for name, task in aws_ecs_task_definition.service : name => task.arn }
}

output "ecs_service_names" {
  description = "서비스별 ECS service 이름."
  value       = { for name, service in aws_ecs_service.service : name => service.name }
}

output "ecr_repository_arns" {
  description = "서비스별 ECR repository ARN."
  value       = { for name, repository in aws_ecr_repository.service : name => repository.arn }
}

output "ecr_repository_urls" {
  description = "서비스별 ECR repository URL."
  value       = { for name, repository in aws_ecr_repository.service : name => repository.repository_url }
}
