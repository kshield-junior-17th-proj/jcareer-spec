output "runtime_instance_id" {
  description = "SSM provisioning target."
  value       = aws_instance.runtime.id
}

output "runtime_role_name" {
  description = "Non-secret IAM role-name handoff for the separately reviewed OpenDART serverless root."
  value       = aws_iam_role.runtime.name
}

output "operator_tunnel" {
  description = "공개 ingress 없이 SSM port forwarding으로 접속하기 위한 비밀정보 없는 파라미터."
  value = {
    target_instance_id = aws_instance.runtime.id
    remote_port        = 3000
    local_port         = 3000
    local_url          = "http://127.0.0.1:3000/jobs"
  }
}

output "auto_stop_minutes" {
  description = "요청된 구성 입력값. 기존 인스턴스의 user_data 변경은 무시되므로 실제 타이머 관찰값이 아니다."
  value       = var.auto_stop_minutes
}

output "aws_https_preview_url" {
  description = "토큰을 포함하지 않는 단기 합성 AWS HTTPS 프리뷰 URL. 비활성화 시 null."
  value = var.enable_aws_https_preview ? (
    "https://${aws_cloudfront_distribution.preview[0].domain_name}/jobs"
  ) : null
}

output "destroy_command" {
  description = "Guarded plan-only cleanup command. A non-empty state prints three review digests; an empty state prints only the provider-account digest. Add -Apply only after human review."
  value       = "powershell -NoProfile -File terraform/lab/provisioning/destroy-lab.ps1 -DestroyAcknowledgement JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED"
}
