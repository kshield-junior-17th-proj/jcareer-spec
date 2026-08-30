output "vpc_id" {
  description = "ID of the AS-IS service VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the AS-IS service VPC."
  value       = aws_vpc.this.cidr_block
}

output "internet_gateway_id" {
  description = "ID of the VPC internet gateway."
  value       = aws_internet_gateway.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs ordered as 2a and 2c."
  value       = [for key in local.az_keys : aws_subnet.public[key].id]
}

output "app_subnet_ids" {
  description = "Private application subnet IDs ordered as 2a and 2c."
  value       = [for key in local.az_keys : aws_subnet.app[key].id]
}

output "data_subnet_ids" {
  description = "Private data subnet IDs ordered as 2a and 2c."
  value       = [for key in local.az_keys : aws_subnet.data[key].id]
}

output "public_subnet_ids_by_az" {
  description = "Public subnet IDs keyed by the 2a and 2c suffixes."
  value       = { for key, subnet in aws_subnet.public : key => subnet.id }
}

output "app_subnet_ids_by_az" {
  description = "Private application subnet IDs keyed by the 2a and 2c suffixes."
  value       = { for key, subnet in aws_subnet.app : key => subnet.id }
}

output "data_subnet_ids_by_az" {
  description = "Private data subnet IDs keyed by the 2a and 2c suffixes."
  value       = { for key, subnet in aws_subnet.data : key => subnet.id }
}

output "nat_gateway_ids_by_az" {
  description = "NAT gateway IDs keyed by the 2a and 2c suffixes."
  value       = { for key, gateway in aws_nat_gateway.this : key => gateway.id }
}

output "nat_eip_public_ips_by_az" {
  description = "NAT gateway EIP addresses keyed by the 2a and 2c suffixes."
  value       = { for key, address in aws_eip.nat : key => address.public_ip }
}

output "route_table_ids" {
  description = "Public, application, and data route table IDs."
  value = {
    public = aws_route_table.public.id
    app    = { for key, table in aws_route_table.app : key => table.id }
    data   = { for key, table in aws_route_table.data : key => table.id }
  }
}

output "security_group_ids" {
  description = "Security group IDs for resources owned by other AS-IS modules."
  value = {
    alb      = aws_security_group.alb.id
    ecs      = aws_security_group.ecs.id
    rds      = aws_security_group.rds.id
    cache    = aws_security_group.cache.id
    endpoint = aws_security_group.endpoint.id
  }
}

output "alb_security_group_id" {
  description = "Security group ID for the application load balancer."
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID shared by the four ECS task types."
  value       = aws_security_group.ecs.id
}

output "rds_security_group_id" {
  description = "Security group ID for PostgreSQL resources."
  value       = aws_security_group.rds.id
}

output "cache_security_group_id" {
  description = "Security group ID for ElastiCache resources."
  value       = aws_security_group.cache.id
}

output "endpoint_security_group_id" {
  description = "Security group ID for interface VPC endpoints."
  value       = aws_security_group.endpoint.id
}
