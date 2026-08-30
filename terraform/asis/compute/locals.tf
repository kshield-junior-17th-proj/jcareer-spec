locals {
  # 공개 기본값은 마스킹하고, standalone mock plan에 필요한 형식값만 메모리에서 조립한다.
  mock_account_id = var.account_id == "redacted" ? join("", ["0000", "0000", "0000"]) : var.account_id
  mock_certificate_id = join("-", [
    "00000000",
    "0000",
    "0000",
    "0000",
    join("", ["0000", "0000", "0000"]),
  ])
  effective_certificate_arn         = var.certificate_arn == "redacted" ? "arn:aws:acm:${var.region}:${local.mock_account_id}:certificate/${local.mock_certificate_id}" : var.certificate_arn
  effective_task_execution_role_arn = var.task_execution_role_arn == "redacted" ? "arn:aws:iam::${local.mock_account_id}:role/${var.name_prefix}-ecs-task-execution" : var.task_execution_role_arn
  effective_task_role_arns = {
    for service_name, arn in var.task_role_arns :
    service_name => arn == "redacted" ? "arn:aws:iam::${local.mock_account_id}:role/${var.name_prefix}-${service_name}-task" : arn
  }

  services = {
    web = {
      port              = 3000
      cpu               = 256
      memory            = 512
      health_check_path = "/"
      path_patterns     = ["/*"]
      priority          = 400
    }
    api = {
      port              = 8000
      cpu               = 256
      memory            = 512
      health_check_path = "/health"
      path_patterns     = ["/api", "/api/*"]
      priority          = 100
    }
    agent = {
      port              = 8100
      cpu               = 256
      memory            = 512
      health_check_path = "/health"
      path_patterns     = ["/agent", "/agent/*"]
      priority          = 200
    }
    llm-gateway = {
      port              = 8200
      cpu               = 256
      memory            = 512
      health_check_path = "/health"
      path_patterns     = ["/llm", "/llm/*"]
      priority          = 300
    }
  }

  ecr_repository_names = {
    for service_name, _ in local.services :
    service_name => "${var.name_prefix}/${service_name}"
  }

  default_container_images = {
    for service_name, repository_name in local.ecr_repository_names :
    service_name => "${local.mock_account_id}.dkr.ecr.${var.region}.amazonaws.com/${repository_name}:asis"
  }

  container_images = merge(local.default_container_images, var.container_images)

  required_tags = {
    jk_layer  = "asis-model"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
    jk_apply  = "forbidden"
  }

  common_tags = merge(var.tags, local.required_tags)
}
