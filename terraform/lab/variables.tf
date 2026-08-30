variable "name_prefix" {
  description = "격리된 J-Career 합성 런타임 lab 리소스 접두사."
  type        = string
  default     = "jcareer-runtime-lab"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,32}$", var.name_prefix))
    error_message = "name_prefix는 3~32자의 소문자 영숫자와 하이픈만 허용한다."
  }
}

variable "activation_acknowledgement" {
  description = "명시적으로 승인된 단기 합성 lab 계획에서만 사용하는 활성화 문구."
  type        = string
  default     = "disabled"

  validation {
    condition = contains([
      "disabled",
      "JCAREER_SYNTHETIC_LAB_APPROVED",
    ], var.activation_acknowledgement)
    error_message = "activation_acknowledgement는 disabled 또는 승인 문구만 허용한다."
  }
}

variable "enable_bedrock_live" {
  description = "lab instance role에 Bedrock 호출 권한을 추가할지 여부. 기본값은 false다."
  type        = bool
  default     = false

  validation {
    condition     = var.enable_bedrock_live == false
    error_message = "컨테이너 전용 AWS 자격증명 경계가 승인·구현되기 전에는 Bedrock live를 계획할 수 없다."
  }
}

variable "instance_type" {
  description = "lab 비용 가드가 허용한 EC2 타입."
  type        = string
  default     = "t3.small"

  validation {
    condition     = var.instance_type == "t3.small"
    error_message = "6개 컨테이너 lab은 t3.small만 허용한다. 더 작은 타입의 실행 가능성은 실측되지 않았다."
  }
}

variable "root_volume_gib" {
  description = "컨테이너 이미지와 합성 데이터용 gp3 루트 볼륨 크기."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 30
    error_message = "root_volume_gib는 20~30GiB여야 한다."
  }
}

variable "auto_stop_minutes" {
  description = "기동 후 OS shutdown으로 EC2를 자동 중지할 시간."
  type        = number
  default     = 240

  validation {
    condition     = var.auto_stop_minutes >= 60 && var.auto_stop_minutes <= 480
    error_message = "auto_stop_minutes는 60~480분이어야 한다."
  }
}

variable "budget_limit_usd" {
  description = "계정 비용을 관찰하기 위한 월간 비용 예산. 알림 이메일은 생성하지 않는다."
  type        = number
  default     = 20

  validation {
    condition     = var.budget_limit_usd >= 5 && var.budget_limit_usd <= 100
    error_message = "budget_limit_usd는 5~100 USD 범위여야 한다."
  }
}

variable "bedrock_model_id" {
  description = "합성 설명 생성에 사용할 Bedrock inference profile ID."
  type        = string
  default     = "apac.amazon.nova-lite-v1:0"

  validation {
    condition     = var.bedrock_model_id == "apac.amazon.nova-lite-v1:0"
    error_message = "현재 lab은 검토한 APAC Nova Lite profile만 허용한다."
  }
}
