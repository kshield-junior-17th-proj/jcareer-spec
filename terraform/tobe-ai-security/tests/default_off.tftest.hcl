mock_provider "aws" {}

mock_provider "aws" {
  alias = "cloudfront_control_plane"
}

override_data {
  target = data.aws_iam_role.broker
  values = {
    arn       = "arn:aws:iam::${join("", ["111122", "223333"])}:role/jcareer-capability-broker-role"
    unique_id = "AROASYNTHETICBROKER01"
  }
}

override_data {
  target = data.aws_iam_role.gateway
  values = {
    arn       = "arn:aws:iam::${join("", ["111122", "223333"])}:role/jcareer-llm-gateway-role"
    unique_id = "AROASYNTHETICGATEWAY1"
  }
}

override_data {
  target = data.aws_lambda_function.broker_published
  values = {
    qualified_arn = "arn:aws:lambda:ap-northeast-2:${join("", ["111122", "223333"])}:function:jcareer-capability-broker:7"
    code_sha256   = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    version       = "7"
  }
}

run "default_off_zero_resources" {
  command = plan

  assert {
    condition     = output.proposal_status == "PROPOSED_NOT_DEPLOYED"
    error_message = "The default proposal status must remain PROPOSED_NOT_DEPLOYED."
  }

  assert {
    condition     = length(output.selected_components) == 0
    error_message = "No component may be selected by default."
  }

  assert {
    condition = (
      output.edge.web_acl_id == null &&
      output.bedrock_boundary.guardrail_id == null &&
      output.metadata_observability.evidence_bucket == null &&
      output.metadata_observability.cloudtrail_name == null
    )
    error_message = "Default-off planning must expose no proposed AWS resource identifier."
  }
}

run "approved_input_shape_is_still_unverified" {
  command = plan

  variables {
    enable                           = true
    enable_edge                      = true
    enable_bedrock_boundary          = true
    enable_observability             = true
    activation_acknowledgement       = "JCAREER_TOBE_AI_SECURITY_APPROVED"
    approval_ref                     = "APPROVAL-SYNTHETIC_REVIEW_01"
    cloudfront_distribution_id       = "E1SYNTHETIC99"
    cloudfront_owner_binding_ref     = "EDGE-BINDING-SYNTHETIC_REVIEW_01"
    verify_cloudfront_binding        = false
    exact_model_id                   = "amazon.nova-lite-v1:0"
    bedrock_invocation_resource_arns = ["arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.nova-lite-v1:0"]
    broker_function_arn              = "arn:aws:lambda:ap-northeast-2:${join("", ["111122", "223333"])}:function:jcareer-capability-broker:7"
    broker_code_sha256               = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    broker_role_name                 = "jcareer-capability-broker-role"
    broker_role_arn                  = "arn:aws:iam::${join("", ["111122", "223333"])}:role/jcareer-capability-broker-role"
    broker_role_unique_id            = "AROASYNTHETICBROKER01"
    gateway_role_name                = "jcareer-llm-gateway-role"
    gateway_role_arn                 = "arn:aws:iam::${join("", ["111122", "223333"])}:role/jcareer-llm-gateway-role"
    gateway_role_unique_id           = "AROASYNTHETICGATEWAY1"
    bedrock_approval_binding_sha256  = "b4210f15e293ca57997506593534b945cb1c241b93f35854b74e25d040869ba0"
  }

  assert {
    condition     = output.proposal_status == "PROPOSED_ACTIVATION_REQUESTED_NOT_VERIFIED"
    error_message = "Even a fully populated review input set must remain explicitly unverified."
  }

  assert {
    condition     = output.selected_components == tolist(["edge", "bedrock-boundary", "metadata-observability"])
    error_message = "The approved-shape fixture must select the three reviewed modules only."
  }

  assert {
    condition     = output.edge.association_mode == "EXTERNAL_REVIEWED_CLOUDFRONT_BINDING_REQUIRED"
    error_message = "ACL planning must not claim that CloudFront is already associated."
  }

  assert {
    condition     = output.bedrock_boundary.approval_input_sha256 == var.bedrock_approval_binding_sha256
    error_message = "Bedrock targets, Broker version/code, role identities, and region must remain bound to one digest."
  }

  assert {
    condition     = toset(keys(output.metadata_observability.publisher_policies)) == toset(["llm-gateway", "capability-broker"])
    error_message = "Gateway and Broker must retain separate metadata publisher policies."
  }
}
