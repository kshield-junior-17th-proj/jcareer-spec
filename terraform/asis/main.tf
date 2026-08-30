locals {
  cloudtrail_name = "${var.name_prefix}-management"

  # 공개 소스에는 12자리 계정 식별자를 남기지 않는다. 아래 값은 mock plan의
  # 형식 검사만 통과시키기 위한 조립값이며 AWS API나 apply에는 쓰지 않는다.
  mock_account_id = var.account_id == "redacted" ? join("", ["0000", "0000", "0000"]) : var.account_id
  mock_certificate_id = join("-", [
    "00000000",
    "0000",
    "0000",
    "0000",
    join("", ["0000", "0000", "0000"]),
  ])
  mock_alb_certificate_arn = var.alb_certificate_arn == "redacted" ? "arn:aws:acm:${var.region}:${local.mock_account_id}:certificate/${local.mock_certificate_id}" : var.alb_certificate_arn

  required_tags = merge(var.common_tags, {
    jk_layer = "asis-model"
    jk_apply = "forbidden"
  })
}

module "network" {
  source = "./network"

  region          = var.region
  name_prefix     = var.name_prefix
  additional_tags = local.required_tags
}

module "data" {
  source = "./data"

  region                   = var.region
  account_id               = local.mock_account_id
  name_prefix              = var.name_prefix
  common_tags              = local.required_tags
  data_subnet_ids          = module.network.data_subnet_ids
  db_security_group_ids    = [module.network.rds_security_group_id]
  cache_security_group_ids = [module.network.cache_security_group_id]
  db_master_password       = var.db_master_password
  cloudtrail_name          = local.cloudtrail_name
  cloudtrail_source_account_ids = [
    local.mock_account_id,
  ]
}

module "security" {
  source = "./security"

  region                          = var.region
  name_prefix                     = var.name_prefix
  vpc_id                          = module.network.vpc_id
  app_subnet_ids                  = module.network.app_subnet_ids
  vpc_endpoint_security_group_ids = [module.network.endpoint_security_group_id]
  resume_bucket_name              = module.data.resume_bucket_id
  common_tags                     = local.required_tags
}

module "observability" {
  source = "./observability"

  depends_on = [module.data]

  region                  = var.region
  name_prefix             = var.name_prefix
  cloudtrail_s3_bucket_id = module.data.cloudtrail_bucket_id
  flow_log_iam_role_arn   = module.security.vpc_flow_logs_role_arn
  vpc_id                  = module.network.vpc_id
  tags                    = local.required_tags
}

module "compute" {
  source = "./compute"

  depends_on = [module.data]

  region                     = var.region
  account_id                 = local.mock_account_id
  name_prefix                = var.name_prefix
  vpc_id                     = module.network.vpc_id
  public_subnet_ids          = module.network.public_subnet_ids
  application_subnet_ids     = module.network.app_subnet_ids
  alb_security_group_ids     = [module.network.alb_security_group_id]
  service_security_group_ids = [module.network.ecs_security_group_id]
  certificate_arn            = local.mock_alb_certificate_arn
  task_execution_role_arn    = module.security.ecs_task_execution_role_arn
  task_role_arns = {
    web         = module.security.ecs_task_role_arn
    api         = module.security.ecs_task_role_arn
    agent       = module.security.ecs_task_role_arn
    llm-gateway = module.security.ecs_task_role_arn
  }
  cloudwatch_log_group_names = {
    web         = module.observability.cloudwatch_log_group_names.access
    api         = module.observability.cloudwatch_log_group_names.access
    agent       = module.observability.cloudwatch_log_group_names.access
    llm-gateway = module.observability.cloudwatch_log_group_names.prompt_raw
  }
  llm_api_key            = var.llm_api_key
  alb_access_logs_bucket = module.data.alb_logs_bucket_id
  alb_access_logs_prefix = module.data.alb_logs_prefix
  tags                   = local.required_tags
}

module "edge" {
  source = "./edge"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  domain_name            = var.domain_name
  service_hostname       = var.service_hostname
  alb_origin_domain_name = module.compute.alb_dns_name
  common_tags            = local.required_tags
}
