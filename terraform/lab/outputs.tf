output "runtime_instance_id" {
  description = "SSM provisioning target."
  value       = aws_instance.runtime.id
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
  description = "EC2가 OS shutdown으로 자동 중지되는 기동 후 시간."
  value       = var.auto_stop_minutes
}

output "destroy_command" {
  description = "이 lab만 제거하는 명령. 자동 실행되지 않는다."
  value       = "terraform -chdir=terraform/lab destroy"
}
