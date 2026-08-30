locals {
  enabled = var.deployment_stage == "definition"
  common_tags = {
    Project            = "jcareer"
    jk_layer           = "workplace-image-definition"
    jk_purpose         = "synthetic-consultant-desktop"
    jk_approval_ref    = var.approval_ref
    jk_image_build_ref = var.image_build_ref
  }
}

resource "aws_imagebuilder_component" "build" {
  count = local.enabled ? 1 : 0

  name        = "${var.name_prefix}-build"
  description = "Credential-free J-Career consultant workplace build component"
  platform    = "Windows"
  version     = "1.0.0"
  data = templatefile("${path.module}/../../fleet/images/windows/build-component.yaml", {
    configure_session_script_b64 = textencodebase64(file("${path.module}/../../fleet/images/windows/Configure-JCareerSession.ps1"), "UTF-8")
    remove_session_script_b64    = textencodebase64(file("${path.module}/../../fleet/images/windows/Remove-JCareerSession.ps1"), "UTF-8")
  })

  lifecycle {
    precondition {
      condition = (
        var.activation_acknowledgement == "JCAREER_WINDOWS_IMAGE_DEFINITION_APPROVED" &&
        can(regex("^APPROVAL-[A-Z0-9_-]{8,64}$", var.approval_ref)) &&
        can(regex("^IMAGE-[A-Z0-9_-]{8,64}$", var.image_build_ref))
      )
      error_message = "Windows image definitions require a separate human acknowledgement and approval reference."
    }
  }

  tags = local.common_tags
}

resource "aws_imagebuilder_component" "test" {
  count = local.enabled ? 1 : 0

  name        = "${var.name_prefix}-test"
  description = "J-Career consultant workplace image boundary tests"
  platform    = "Windows"
  version     = "1.0.0"
  data        = file("${path.module}/../../fleet/images/windows/test-component.yaml")

  tags = local.common_tags
}

resource "aws_iam_role" "builder" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-builder"
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

resource "aws_iam_role_policy_attachment" "image_builder" {
  count = local.enabled ? 1 : 0

  role       = aws_iam_role.builder[0].name
  policy_arn = "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilder"
}

resource "aws_iam_role_policy_attachment" "ssm" {
  count = local.enabled ? 1 : 0

  role       = aws_iam_role.builder[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role" "lifecycle" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-lifecycle"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "imagebuilder.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "lifecycle" {
  count = local.enabled ? 1 : 0

  role       = aws_iam_role.lifecycle[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/EC2ImageBuilderLifecycleExecutionPolicy"
}

resource "aws_iam_instance_profile" "builder" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-builder"
  role = aws_iam_role.builder[0].name

  tags = local.common_tags
}

resource "aws_imagebuilder_image_recipe" "windows" {
  count = local.enabled ? 1 : 0

  name         = "${var.name_prefix}-recipe"
  version      = "1.0.0"
  parent_image = var.windows_parent_image

  component {
    component_arn = aws_imagebuilder_component.build[0].arn
  }

  component {
    component_arn = aws_imagebuilder_component.test[0].arn
  }

  block_device_mapping {
    device_name = "/dev/sda1"
    ebs {
      delete_on_termination = true
      encrypted             = true
      volume_size           = 40
      volume_type           = "gp3"
    }
  }

  lifecycle {
    precondition {
      condition = (
        var.windows_parent_image != "" &&
        can(regex("^subnet-[0-9a-f]+$", var.build_subnet_id)) &&
        can(regex("^sg-[0-9a-f]+$", var.build_security_group_id))
      )
      error_message = "definition requires a reviewed Windows parent, subnet, and security group."
    }
  }

  tags = local.common_tags
}

resource "aws_imagebuilder_infrastructure_configuration" "windows" {
  count = local.enabled ? 1 : 0

  name                          = "${var.name_prefix}-infrastructure"
  instance_profile_name         = aws_iam_instance_profile.builder[0].name
  instance_types                = ["t3.small"]
  subnet_id                     = var.build_subnet_id
  security_group_ids            = [var.build_security_group_id]
  terminate_instance_on_failure = true
  resource_tags                 = local.common_tags

  instance_metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = local.common_tags
}

resource "aws_imagebuilder_distribution_configuration" "windows" {
  count = local.enabled ? 1 : 0

  name = "${var.name_prefix}-distribution"
  distribution {
    region = var.aws_region
    ami_distribution_configuration {
      name = "${var.name_prefix}-{{ imagebuilder:buildDate }}"
      ami_tags = merge(local.common_tags, {
        jk_image_state = "BUILT_PENDING_HUMAN_RELEASE"
        jk_os_contract = "windows-server-desktop-simulation"
      })
    }
  }

  tags = local.common_tags
}

resource "aws_imagebuilder_image_pipeline" "windows" {
  count = local.enabled ? 1 : 0

  name                             = "${var.name_prefix}-manual"
  image_recipe_arn                 = aws_imagebuilder_image_recipe.windows[0].arn
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.windows[0].arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.windows[0].arn
  status                           = "ENABLED"
  enhanced_image_metadata_enabled  = true

  image_tests_configuration {
    image_tests_enabled = true
    timeout_minutes     = 60
  }

  tags = local.common_tags
}
