output "architecture_summary" {
  description = "사람 검토용 AS-IS 계층별 좌표. 판정값은 포함하지 않는다."
  value = {
    vpc_id                 = module.network.vpc_id
    public_subnet_ids      = module.network.public_subnet_ids
    application_subnet_ids = module.network.app_subnet_ids
    data_subnet_ids        = module.network.data_subnet_ids
    nat_gateway_ids        = module.network.nat_gateway_ids_by_az
    alb_dns_name           = module.compute.alb_dns_name
    ecs_cluster_name       = module.compute.ecs_cluster_name
    rds_primary            = module.data.db_primary_identifier
    rds_replica            = module.data.db_replica_identifier
    cache_id               = module.data.cache_replication_group_id
    cloudfront_domain_name = module.edge.cloudfront_domain_name
    web_acl_arn            = module.edge.web_acl_arn
    guardduty_detector_id  = module.observability.guardduty_detector_id
  }
}

output "apply_policy" {
  description = "이 계층의 실행 정책. Terraform 출력은 apply 권한을 부여하지 않는다."
  value       = "FORBIDDEN — mock plan only"
}
