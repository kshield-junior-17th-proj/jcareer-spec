variable "region" {
  description = "AWS 리전. AS-IS 서비스망은 ap-northeast-2를 사용한다."
  type        = string
  default     = "ap-northeast-2"
  nullable    = false
}

variable "account_id" {
  description = "이미지 URI를 구성할 계정 식별자. 공개 기본값은 마스킹하며 실제 계정을 조회하지 않는다."
  type        = string
  default     = "redacted"
  nullable    = false

  validation {
    condition     = var.account_id == "redacted" || can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id는 redacted 또는 12자리 숫자여야 한다."
  }
}

variable "name_prefix" {
  description = "ALB, ECS, ECR 리소스 이름 접두사."
  type        = string
  default     = "jcareer-asis"
  nullable    = false

  validation {
    condition = (
      length(var.name_prefix) <= 18 &&
      can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.name_prefix))
    )
    error_message = "name_prefix는 18자 이하의 소문자 영숫자와 하이픈으로 구성하고 영숫자로 시작·종료해야 한다."
  }
}

variable "vpc_id" {
  description = "네 개 target group을 배치할 VPC ID."
  type        = string
  default     = "vpc-00000000000000000"
  nullable    = false

  validation {
    condition     = can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "vpc_id는 vpc-로 시작하는 AWS VPC ID 형식이어야 한다."
  }
}

variable "public_subnet_ids" {
  description = "ALB를 배치할 2a·2c public subnet ID 두 개."
  type        = list(string)
  default = [
    "subnet-00000000000000001",
    "subnet-00000000000000002",
  ]
  nullable = false

  validation {
    condition = (
      length(var.public_subnet_ids) == 2 &&
      length(distinct(var.public_subnet_ids)) == 2 &&
      alltrue([for id in var.public_subnet_ids : can(regex("^subnet-[0-9a-f]+$", id))])
    )
    error_message = "public_subnet_ids에는 서로 다른 public subnet ID 두 개를 지정해야 한다."
  }
}

variable "application_subnet_ids" {
  description = "ECS Fargate task를 배치할 2a·2c private application subnet ID 두 개."
  type        = list(string)
  default = [
    "subnet-00000000000000011",
    "subnet-00000000000000012",
  ]
  nullable = false

  validation {
    condition = (
      length(var.application_subnet_ids) == 2 &&
      length(distinct(var.application_subnet_ids)) == 2 &&
      alltrue([for id in var.application_subnet_ids : can(regex("^subnet-[0-9a-f]+$", id))])
    )
    error_message = "application_subnet_ids에는 서로 다른 private application subnet ID 두 개를 지정해야 한다."
  }
}

variable "alb_security_group_ids" {
  description = "Public ALB에 연결할 security group ID 목록."
  type        = list(string)
  default     = ["sg-00000000000000001"]
  nullable    = false

  validation {
    condition = (
      length(var.alb_security_group_ids) > 0 &&
      alltrue([for id in var.alb_security_group_ids : can(regex("^sg-[0-9a-f]+$", id))])
    )
    error_message = "alb_security_group_ids에는 하나 이상의 AWS security group ID를 지정해야 한다."
  }
}

variable "service_security_group_ids" {
  description = "네 ECS service의 awsvpc ENI에 연결할 security group ID 목록."
  type        = list(string)
  default     = ["sg-00000000000000002"]
  nullable    = false

  validation {
    condition = (
      length(var.service_security_group_ids) > 0 &&
      alltrue([for id in var.service_security_group_ids : can(regex("^sg-[0-9a-f]+$", id))])
    )
    error_message = "service_security_group_ids에는 하나 이상의 AWS security group ID를 지정해야 한다."
  }
}

variable "certificate_arn" {
  description = "ALB HTTPS listener에 연결할 ACM 인증서 ARN."
  type        = string
  default     = "redacted"
  nullable    = false

  validation {
    condition     = var.certificate_arn == "redacted" || can(regex("^arn:aws:acm:[a-z0-9-]+:[0-9]{12}:certificate/[0-9a-f-]+$", var.certificate_arn))
    error_message = "certificate_arn은 redacted 또는 ACM 인증서 ARN 형식이어야 한다."
  }
}

variable "alb_access_logs_bucket" {
  description = "data 모듈이 만드는 90일 보존 ALB 액세스 로그 버킷 이름."
  type        = string
  default     = "jcareer-asis-alb-logs-redacted"
  nullable    = false
}

variable "alb_access_logs_prefix" {
  description = "ALB 액세스 로그 버킷 정책·수명주기와 맞추는 S3 키 접두사."
  type        = string
  default     = "alb"
  nullable    = false
}

variable "task_execution_role_arn" {
  description = "ECS task execution IAM role ARN. IAM 리소스는 이 모듈에서 만들지 않는다."
  type        = string
  default     = "redacted"
  nullable    = false

  validation {
    condition     = var.task_execution_role_arn == "redacted" || can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.task_execution_role_arn))
    error_message = "task_execution_role_arn은 redacted 또는 IAM role ARN 형식이어야 한다."
  }
}

variable "task_role_arns" {
  description = "web, api, agent, llm-gateway task가 사용할 기존 IAM role ARN."
  type        = map(string)
  default = {
    web         = "redacted"
    api         = "redacted"
    agent       = "redacted"
    llm-gateway = "redacted"
  }
  nullable = false

  validation {
    condition = (
      length(var.task_role_arns) == 4 &&
      alltrue([
        for service_name in ["web", "api", "agent", "llm-gateway"] :
        contains(keys(var.task_role_arns), service_name)
      ]) &&
      alltrue([
        for arn in values(var.task_role_arns) :
        arn == "redacted" || can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", arn))
      ])
    )
    error_message = "task_role_arns에는 네 서비스의 IAM role ARN을 정확히 지정해야 한다."
  }
}

variable "container_images" {
  description = "서비스별 전체 container image URI override. 생략하면 account_id·region·ECR 이름으로 AS-IS 태그 URI를 구성한다."
  type        = map(string)
  default     = {}
  nullable    = false

  validation {
    condition = (
      alltrue([
        for service_name in keys(var.container_images) :
        contains(["web", "api", "agent", "llm-gateway"], service_name)
      ]) &&
      alltrue([for image in values(var.container_images) : length(trimspace(image)) > 0])
    )
    error_message = "container_images에는 네 서비스 이름 중 필요한 키와 비어 있지 않은 image URI만 지정해야 한다."
  }
}

variable "cloudwatch_log_group_names" {
  description = "observability 모듈에서 제공할 기존 CloudWatch Logs group 이름."
  type        = map(string)
  default = {
    web         = "/jcareer/asis/web"
    api         = "/jcareer/asis/api"
    agent       = "/jcareer/asis/agent"
    llm-gateway = "/jcareer/asis/llm-gateway"
  }
  nullable = false

  validation {
    condition = (
      length(var.cloudwatch_log_group_names) == 4 &&
      alltrue([
        for service_name in ["web", "api", "agent", "llm-gateway"] :
        contains(keys(var.cloudwatch_log_group_names), service_name)
      ])
    )
    error_message = "cloudwatch_log_group_names에는 네 서비스의 log group 이름을 정확히 지정해야 한다."
  }
}

variable "llm_api_key" {
  description = "AS-IS llm-gateway 환경변수 주입을 재현하는 합성 API 키. 실제 키를 저장하지 않는다."
  type        = string
  default     = "mock-llm-api-key"
  sensitive   = true
  nullable    = false
}

variable "service_max_capacity" {
  description = "각 ECS service Application Auto Scaling target의 최대 task 수. 최소값은 AS-IS 사양대로 2로 고정한다."
  type        = number
  default     = 4
  nullable    = false

  validation {
    condition     = var.service_max_capacity >= 2 && floor(var.service_max_capacity) == var.service_max_capacity
    error_message = "service_max_capacity는 2 이상의 정수여야 한다."
  }
}

variable "tags" {
  description = "추가 태그. jk_layer, jk_source, jk_apply는 모듈이 AS-IS 고정값으로 덮어쓴다."
  type        = map(string)
  default     = {}
  nullable    = false
}
