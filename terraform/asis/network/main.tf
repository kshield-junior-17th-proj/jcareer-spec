locals {
  az_keys = ["2a", "2c"]

  network_by_az = {
    for index, key in local.az_keys : key => {
      availability_zone = var.az_names[index]
      public_cidr       = var.public_subnet_cidrs[index]
      app_cidr          = var.app_subnet_cidrs[index]
      data_cidr         = var.data_subnet_cidrs[index]
    }
  }

  common_tags = merge(var.additional_tags, {
    jk_layer  = "asis-model"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
    jk_apply  = "forbidden"
  })
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

resource "aws_subnet" "public" {
  for_each = local.network_by_az

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.availability_zone
  cidr_block              = each.value.public_cidr
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-public-${each.key}"
    Tier = "public"
  })
}

resource "aws_subnet" "app" {
  for_each = local.network_by_az

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.availability_zone
  cidr_block              = each.value.app_cidr
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-app-${each.key}"
    Tier = "application"
  })
}

resource "aws_subnet" "data" {
  for_each = local.network_by_az

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.availability_zone
  cidr_block              = each.value.data_cidr
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-data-${each.key}"
    Tier = "data"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-igw"
  })
}

resource "aws_eip" "nat" {
  for_each = local.network_by_az

  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-nat-eip-${each.key}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  for_each = local.network_by_az

  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-nat-${each.key}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-public-rt"
    Tier = "public"
  })
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = local.network_by_az

  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "app" {
  for_each = local.network_by_az

  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-app-${each.key}-rt"
    Tier = "application"
  })
}

resource "aws_route" "app_default" {
  for_each = local.network_by_az

  route_table_id         = aws_route_table.app[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[each.key].id
}

resource "aws_route_table_association" "app" {
  for_each = local.network_by_az

  subnet_id      = aws_subnet.app[each.key].id
  route_table_id = aws_route_table.app[each.key].id
}

resource "aws_route_table" "data" {
  for_each = local.network_by_az

  vpc_id = aws_vpc.this.id

  # Data subnets intentionally have only the VPC-local route. The approved
  # service topology places the sole external LLM path in the app tier.
  # 근거: context/raw/D02-진단대상-아키텍처-정의.md#3.1
  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-data-${each.key}-rt"
    Tier = "data"
  })
}

resource "aws_route_table_association" "data" {
  for_each = local.network_by_az

  subnet_id      = aws_subnet.data[each.key].id
  route_table_id = aws_route_table.data[each.key].id
}
