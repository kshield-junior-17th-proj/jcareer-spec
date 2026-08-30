locals {
  enabled       = var.deployment_stage == "windows_three"
  endpoint_refs = ["WIN-01", "WIN-02", "WIN-03"]
  common_tags = {
    Project            = "jcareer"
    jk_layer           = "workplace-endpoint-demo"
    jk_purpose         = "synthetic-consultant-desktop"
    jk_approval_ref    = var.approval_ref
    jk_image_build_ref = var.image_build_ref
  }
}

resource "aws_security_group" "endpoints" {
  count = local.enabled ? 1 : 0

  name        = "${var.name_prefix}-windows"
  description = "Three synthetic Windows endpoints; no inbound, SSM access only"
  vpc_id      = var.vpc_id

  lifecycle {
    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_THREE_WINDOWS_ENDPOINTS_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref)) &&
        can(regex("^IMAGE-[A-Z0-9_-]{8,64}$", var.image_build_ref))
      )
      error_message = "endpoint deployment requires exact-plan and image-build human references."
    }
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-windows" })
}

resource "aws_vpc_security_group_egress_rule" "https_and_ssm" {
  count = local.enabled ? 1 : 0

  security_group_id = aws_security_group.endpoints[0].id
  description       = "Public Internet HTTPS egress; domain allowlisting is not implemented"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"

  tags = local.common_tags
}

resource "aws_iam_role" "endpoint" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-windows"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  count = local.enabled ? 1 : 0

  role       = aws_iam_role.endpoint[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "endpoint" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-windows"
  role = aws_iam_role.endpoint[0].name

  tags = local.common_tags
}

resource "aws_instance" "windows" {
  count = local.enabled ? 3 : 0

  ami                         = var.windows_ami_id
  instance_type               = "t3.small"
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.endpoints[0].id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.endpoint[0].name
  key_name                    = var.key_pair_name
  monitoring                  = false

  user_data = <<-POWERSHELL
    <powershell>
    $ErrorActionPreference = 'Stop'
    $action = New-ScheduledTaskAction -Execute 'shutdown.exe' -Argument '/s /t 0'
    $trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(${var.auto_stop_minutes}))
    Register-ScheduledTask -TaskName 'JCareerLabAutoStop' -Action $action -Trigger $trigger -User 'SYSTEM' -RunLevel Highest -Force
    </powershell>
    <persist>true</persist>
  POWERSHELL

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
    volume_size           = 40
    iops                  = 3000
  }

  credit_specification {
    cpu_credits = "standard"
  }

  lifecycle {
    precondition {
      condition = (
        can(regex("^vpc-[0-9a-f]+$", var.vpc_id)) &&
        can(regex("^subnet-[0-9a-f]+$", var.subnet_id)) &&
        can(regex("^ami-[0-9a-f]+$", var.windows_ami_id)) &&
        var.key_pair_name != ""
      )
      error_message = "endpoint deployment requires a reviewed VPC, subnet, AMI, and existing key pair."
    }
  }

  tags = merge(local.common_tags, {
    Name            = "${var.name_prefix}-${lower(local.endpoint_refs[count.index])}"
    jk_endpoint_ref = local.endpoint_refs[count.index]
    jk_os_contract  = "windows-server-desktop-simulation"
    jk_access       = "ssm-only-no-inbound"
  })

  depends_on = [aws_iam_role_policy_attachment.ssm]
}

resource "aws_budgets_budget" "endpoints" {
  count = local.enabled ? 1 : 0

  name         = "${var.name_prefix}-windows-monthly-observation"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:jk_layer$workplace-endpoint-demo"]
  }

  tags = local.common_tags
}
