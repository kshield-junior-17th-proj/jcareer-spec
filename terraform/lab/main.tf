locals {
  common_tags = {
    Project    = "jcareer"
    jk_layer   = "lab"
    jk_purpose = "synthetic-runtime-validation"
  }

  cloudfront_caching_disabled_policy_id    = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  cloudfront_all_viewer_except_host_policy = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  cloudfront_security_headers_policy_id    = "67f7725c-6f97-4210-82d7-5512b31e9d03"
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_vpc" "lab" {
  cidr_block           = "10.91.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-vpc" })

  lifecycle {
    precondition {
      condition     = var.activation_acknowledgement == "JCAREER_SYNTHETIC_LAB_APPROVED"
      error_message = "lab은 기본 차단 상태다. 사람 승인 후 activation_acknowledgement를 명시해야 한다."
    }
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.91.0.0/26"
  availability_zone       = "ap-northeast-2a"
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-public" })
}

resource "aws_subnet" "private_preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.91.0.64/26"
  availability_zone       = "ap-northeast-2a"
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-private-preview" })
}

resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lab.id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-public" })
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.lab.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "preview_nat" {
  count = var.enable_aws_https_preview ? 1 : 0

  domain = "vpc"

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-preview-nat" })

  depends_on = [aws_internet_gateway.lab]
}

resource "aws_nat_gateway" "preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  allocation_id = aws_eip.preview_nat[0].id
  subnet_id     = aws_subnet.public.id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-preview-nat" })
}

resource "aws_route_table" "private_preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  vpc_id = aws_vpc.lab.id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-private-preview" })
}

resource "aws_route" "private_preview_internet" {
  count = var.enable_aws_https_preview ? 1 : 0

  route_table_id         = aws_route_table.private_preview[0].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.preview[0].id
}

resource "aws_route_table_association" "private_preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  subnet_id      = aws_subnet.private_preview[0].id
  route_table_id = aws_route_table.private_preview[0].id
}

resource "aws_security_group" "runtime" {
  name        = "${var.name_prefix}-runtime"
  description = "J-Career synthetic lab; no inbound rules, operator access through SSM tunnel"
  vpc_id      = aws_vpc.lab.id

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-runtime" })
}

resource "aws_vpc_security_group_egress_rule" "internet" {
  security_group_id = aws_security_group.runtime.id
  description       = "Package, container image, SSM and Bedrock egress"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-egress" })
}

data "aws_security_group" "cloudfront_vpc_origin_service" {
  count = var.enable_aws_https_preview ? 1 : 0

  vpc_id = aws_vpc.lab.id

  filter {
    name   = "group-name"
    values = ["CloudFront-VPCOrigins-Service-SG"]
  }

  depends_on = [aws_cloudfront_vpc_origin.preview]
}

resource "aws_vpc_security_group_ingress_rule" "cloudfront_preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  security_group_id = aws_security_group.runtime.id
  description       = "This VPC origin service SG to synthetic web entrypoint only"
  referenced_security_group_id = (
    data.aws_security_group.cloudfront_vpc_origin_service[0].id
  )
  from_port   = 3000
  to_port     = 3000
  ip_protocol = "tcp"

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-cloudfront-ingress" })
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name_prefix}-runtime"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-runtime" })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.runtime.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "bedrock" {
  statement {
    sid     = "InvokeApprovedExplanationModel"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
      "arn:aws:bedrock:*:*:inference-profile/${var.bedrock_model_id}",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock_live ? 1 : 0

  name   = "${var.name_prefix}-bedrock"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.bedrock.json
}

resource "aws_iam_instance_profile" "runtime" {
  name = "${var.name_prefix}-runtime"
  role = aws_iam_role.runtime.name

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-runtime" })
}

resource "aws_instance" "runtime" {
  ami           = data.aws_ssm_parameter.al2023_ami.value
  instance_type = var.instance_type
  subnet_id = var.enable_aws_https_preview ? (
    aws_subnet.private_preview[0].id
  ) : aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.runtime.id]
  associate_public_ip_address = var.enable_aws_https_preview ? false : true
  iam_instance_profile        = aws_iam_instance_profile.runtime.name
  monitoring                  = false

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    auto_stop_minutes = var.auto_stop_minutes
  })
  user_data_replace_on_change          = true
  instance_initiated_shutdown_behavior = "stop"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    http_protocol_ipv6          = "disabled"
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    delete_on_termination = true
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = var.root_volume_gib
    iops                  = 3000
  }

  credit_specification {
    cpu_credits = "standard"
  }

  lifecycle {
    # Runtime releases are delivered through the reviewed SSM path. Preserve a
    # healthy short-lived host when the bootstrap template changes; a newly
    # created instance still receives the current template.
    ignore_changes = [user_data]

    precondition {
      condition = (
        var.enable_bedrock_live == false ||
        var.bedrock_live_acknowledgement == "JCAREER_SYNTHETIC_BEDROCK_APPROVED"
      )
      error_message = "Bedrock live에는 분리된 capability broker 경계와 별도 승인 문구가 필요하다."
    }

    precondition {
      condition = (
        var.enable_opendart_live == false ||
        var.opendart_live_acknowledgement == "JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED"
      )
      error_message = "OpenDART live에는 승인된 runtime-stage 배포와 별도 연결 승인 문구가 필요하다."
    }
  }

  tags = merge(local.common_tags, {
    Name             = "${var.name_prefix}-runtime"
    jk_bedrock_live  = tostring(var.enable_bedrock_live)
    jk_opendart_live = tostring(var.enable_opendart_live)
    jk_https_preview = tostring(var.enable_aws_https_preview)
  })

  depends_on = [
    aws_iam_role_policy_attachment.ssm,
    aws_iam_role_policy.bedrock,
    aws_vpc_security_group_egress_rule.internet,
    aws_route.internet,
    aws_route_table_association.public,
    aws_route.private_preview_internet,
    aws_route_table_association.private_preview,
  ]
}

resource "aws_cloudfront_vpc_origin" "preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  vpc_origin_endpoint_config {
    arn                    = aws_instance.runtime.arn
    http_port              = 3000
    https_port             = 443
    name                   = "${var.name_prefix}-vpc-origin"
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-vpc-origin" })

}

resource "aws_cloudfront_function" "preview_gate" {
  count = var.enable_aws_https_preview ? 1 : 0

  name    = "${var.name_prefix}-preview-gate"
  comment = "Short-lived synthetic preview cookie gate"
  runtime = "cloudfront-js-2.0"
  publish = true
  code = templatefile("${path.module}/preview_gate.js.tftpl", {
    access_token_sha256_json = jsonencode(var.preview_access_token_sha256)
    max_age_seconds          = var.auto_stop_minutes * 60
  })

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-preview-gate" })
}

resource "aws_cloudfront_distribution" "preview" {
  count = var.enable_aws_https_preview ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = false
  comment             = "J-Career short-lived synthetic HTTPS preview"
  default_root_object = ""
  price_class         = "PriceClass_200"
  http_version        = "http2and3"
  wait_for_deployment = true
  retain_on_delete    = false

  origin {
    domain_name = aws_instance.runtime.private_dns
    origin_id   = "jcareer-runtime-vpc-origin"

    vpc_origin_config {
      vpc_origin_id = aws_cloudfront_vpc_origin.preview[0].id
    }
  }

  default_cache_behavior {
    target_origin_id       = "jcareer-runtime-vpc-origin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = false

    cache_policy_id            = local.cloudfront_caching_disabled_policy_id
    origin_request_policy_id   = local.cloudfront_all_viewer_except_host_policy
    response_headers_policy_id = local.cloudfront_security_headers_policy_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.preview_gate[0].arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  lifecycle {
    precondition {
      condition = (
        var.https_preview_acknowledgement == "JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED" &&
        can(regex("^[0-9a-f]{64}$", var.preview_access_token_sha256))
      )
      error_message = "CloudFront 프리뷰는 별도 사람 승인과 단기 토큰 없이는 생성할 수 없다."
    }
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-https-preview" })

  depends_on = [aws_vpc_security_group_ingress_rule.cloudfront_preview]
}

resource "aws_budgets_budget" "lab" {
  name         = "${var.name_prefix}-monthly-observation"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:jk_layer$lab"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-budget" })
}
