variable "region" {
  description = "J-Career AS-IS 서비스 리전."
  type        = string
  default     = "ap-northeast-2"
}

variable "edge_region" {
  description = "CloudFront용 WAFv2와 ACM이 요구하는 제어 리전."
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "data source 대신 사용하는 계정 식별자. 공개 기본값은 마스킹하며 mock plan에서만 형식값으로 바꾼다."
  type        = string
  default     = "redacted"
}

variable "name_prefix" {
  description = "AS-IS 재현 리소스 이름 접두사."
  type        = string
  default     = "jcareer-asis"
}

variable "domain_name" {
  description = "실제 DNS에 위임되지 않는 RFC 2606 합성 도메인."
  type        = string
  default     = "jcareer.example"
}

variable "service_hostname" {
  description = "서비스 호스트명. 빈 문자열이면 합성 도메인의 apex를 사용한다."
  type        = string
  default     = ""
}

variable "alb_certificate_arn" {
  description = "mock plan용 서울 리전 ACM ARN. 공개 기본값은 마스킹하며 apply에 사용할 수 없다."
  type        = string
  default     = "redacted"
}

variable "llm_api_key" {
  description = "AS-IS 환경변수 주입을 재현하는 합성값. 실제 비밀정보가 아니다."
  type        = string
  default     = "mock-llm-api-key"
  sensitive   = true
}

variable "db_master_password" {
  description = "Secrets Manager 미사용 AS-IS를 재현하는 합성 DB 비밀번호."
  type        = string
  default     = "mock-db-password-not-a-secret"
  sensitive   = true
}

variable "common_tags" {
  description = "모든 모듈에 전달하는 비판정 공통 태그."
  type        = map(string)
  default = {
    Project = "jcareer"
    Phase   = "asis-model"
  }
}
