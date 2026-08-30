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
    condition = (
      var.enable_bedrock_live == false ||
      var.bedrock_live_acknowledgement == "JCAREER_SYNTHETIC_BEDROCK_APPROVED"
    )
    error_message = "Bedrock live에는 capability broker 경계를 전제로 한 별도 승인 문구가 필요하다."
  }
}

variable "bedrock_live_acknowledgement" {
  description = "합성 입력만 사용하는 Bedrock capability-broker 경로를 별도로 승인하는 문구."
  type        = string
  default     = "disabled"

  validation {
    condition = contains([
      "disabled",
      "JCAREER_SYNTHETIC_BEDROCK_APPROVED",
    ], var.bedrock_live_acknowledgement)
    error_message = "bedrock_live_acknowledgement는 disabled 또는 지정 승인 문구여야 한다."
  }
}

variable "enable_opendart_live" {
  description = "별도 승인·배포된 OpenDART serverless root를 capability broker로 연결할지 여부."
  type        = bool
  default     = false

  validation {
    condition = (
      var.enable_opendart_live == false ||
      var.opendart_live_acknowledgement == "JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED"
    )
    error_message = "OpenDART live에는 별도 serverless 배포 증적과 승인 문구가 필요하다."
  }
}

variable "opendart_live_acknowledgement" {
  description = "기존 OpenDART runtime-stage 배포를 합성 lab에 연결하는 별도 승인 문구."
  type        = string
  default     = "disabled"

  validation {
    condition = contains([
      "disabled",
      "JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED",
    ], var.opendart_live_acknowledgement)
    error_message = "opendart_live_acknowledgement는 disabled 또는 지정 승인 문구여야 한다."
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

variable "enable_aws_https_preview" {
  description = "CloudFront HTTPS를 통한 단기 합성 프리뷰 활성화 여부. 기본값은 false다."
  type        = bool
  default     = false

  validation {
    condition = (
      var.enable_aws_https_preview == false ||
      (
        var.https_preview_acknowledgement == "JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED" &&
        can(regex("^[0-9a-f]{64}$", var.preview_access_token_sha256))
      )
    )
    error_message = "AWS HTTPS 프리뷰에는 별도 승인문구와 256-bit 임시 토큰이 필요하다."
  }
}

variable "https_preview_acknowledgement" {
  description = "단기 AWS HTTPS 프리뷰를 별도로 승인하는 명시적 문구."
  type        = string
  default     = "disabled"

  validation {
    condition = contains([
      "disabled",
      "JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED",
    ], var.https_preview_acknowledgement)
    error_message = "https_preview_acknowledgement는 disabled 또는 승인 문구만 허용한다."
  }
}

variable "preview_access_token_sha256" {
  description = "단기 토큰의 SHA-256 digest. 원문 토큰은 Terraform에 전달하지 않는다."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition = (
      var.preview_access_token_sha256 == "" ||
      can(regex("^[0-9a-f]{64}$", var.preview_access_token_sha256))
    )
    error_message = "preview_access_token_sha256은 비어 있거나 64자리 소문자 16진수여야 한다."
  }
}
