locals {
  common_tags = {
    Project    = "jcareer"
    jk_layer   = "lab"
    jk_purpose = "synthetic-runtime-validation"
  }
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
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.runtime.id]
  associate_public_ip_address = true
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
    precondition {
      condition     = var.enable_bedrock_live == false
      error_message = "Bedrock live는 컨테이너 전용 자격증명 경계가 승인·구현될 때까지 차단한다."
    }
  }

  tags = merge(local.common_tags, {
    Name            = "${var.name_prefix}-runtime"
    jk_bedrock_live = tostring(var.enable_bedrock_live)
  })

  depends_on = [
    aws_iam_role_policy_attachment.ssm,
    aws_iam_role_policy.bedrock,
    aws_route.internet,
  ]
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
