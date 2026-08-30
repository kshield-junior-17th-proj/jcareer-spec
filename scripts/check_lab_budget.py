#!/usr/bin/env python3
"""terraform/lab 비용·노출 plan 가드레일 — V2.3.

V2 결함: denylist 방식이라 목록 밖 서비스(SageMaker ml.p4d.24xlarge 등)가 전부 통과했다.
         region 이 변수 참조면 검사를 건너뛰고, root_block_device 미명세면 gp3 검사도 건너뛰었다.
         aws_instance.ebs_block_device 는 아예 보지 않았다.

V2.1: 사람이 승인한 low-cost allowlist 로 전환. 목록 밖 리소스는 전부 실패.
      리전은 상수 ap-northeast-2 만 허용(변수·미지정도 실패).
      root/추가 EBS 를 모두 검사하고 미명세 root volume 은 실패.
      태그 지원 여부를 리소스 타입별로 처리한다.

V2.2: 현재 단기 lab의 exact managed-resource/data-source 목록으로 축소하고 key pair,
      managed SSM parameter, ingress 계열, local/private-key 리소스를 제거했다. EC2의
      IMDSv2·hop limit·암호화 root·standard credit·상세 모니터링 계약도 plan에서 검사한다.

V2.4: HTTPS 프리뷰 origin을 조건부 private subnet으로 옮기고 단기 NAT egress 6개와
      CloudFront VPC-origin 4개 리소스를 exact address 목록에 둔다. EC2 ingress는
      VPC origin 생성 후 AWS가 만든 service-managed SG의 TCP/3000 한 건만 허용한다.
"""
import argparse, json, re, sys

REGION = "ap-northeast-2"
ALLOWED_INSTANCE_TYPES = {"t3.small"}
REQUIRED_EC2_COUNT = 1
MAX_EBS_TOTAL_GB = 30
MAX_EBS_PER_VOL_GB = 30
ALLOWED_VOLUME_TYPES = {"gp3"}
MAX_IOPS = 3000
MAX_RESOURCES = 40
CLOUDFRONT_CACHING_DISABLED_POLICY_ID = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
CLOUDFRONT_ALL_VIEWER_EXCEPT_HOST_POLICY_ID = "b689b0a8-53d0-40ab-baf2-68738e2966ac"

# 사람이 승인한 low-cost 리소스만. 여기 없으면 실패한다.
ALLOWED_RESOURCE_TYPES = {
    "aws_instance",
    "aws_vpc", "aws_subnet", "aws_internet_gateway", "aws_route_table",
    "aws_route", "aws_route_table_association", "aws_security_group",
    "aws_eip", "aws_nat_gateway",
    "aws_vpc_security_group_egress_rule",
    "aws_vpc_security_group_ingress_rule",
    "aws_iam_role",
    "aws_iam_role_policy", "aws_iam_role_policy_attachment", "aws_iam_instance_profile",
    "aws_budgets_budget",
    "aws_cloudfront_vpc_origin", "aws_cloudfront_function",
    "aws_cloudfront_distribution",
}
ALLOWED_DATA_ADDRESSES = {
    "data.aws_ssm_parameter.al2023_ami",
    "data.aws_iam_policy_document.ec2_assume",
    "data.aws_iam_policy_document.bedrock",
    "data.aws_security_group.cloudfront_vpc_origin_service[0]",
}
BASE_MANAGED_ADDRESSES = {
    "aws_vpc.lab",
    "aws_subnet.public",
    "aws_internet_gateway.lab",
    "aws_route_table.public",
    "aws_route.internet",
    "aws_route_table_association.public",
    "aws_security_group.runtime",
    "aws_vpc_security_group_egress_rule.internet",
    "aws_iam_role.runtime",
    "aws_iam_role_policy_attachment.ssm",
    "aws_iam_instance_profile.runtime",
    "aws_instance.runtime",
    "aws_budgets_budget.lab",
}
HTTPS_PREVIEW_ADDRESSES = {
    "aws_subnet.private_preview[0]",
    "aws_eip.preview_nat[0]",
    "aws_nat_gateway.preview[0]",
    "aws_route_table.private_preview[0]",
    "aws_route.private_preview_internet[0]",
    "aws_route_table_association.private_preview[0]",
    "aws_vpc_security_group_ingress_rule.cloudfront_preview[0]",
    "aws_cloudfront_vpc_origin.preview[0]",
    "aws_cloudfront_function.preview_gate[0]",
    "aws_cloudfront_distribution.preview[0]",
}
BEDROCK_MANAGED_ADDRESSES = {"aws_iam_role_policy.bedrock[0]"}
# 태그를 지원하지 않는 타입 — 태그 요구에서 제외한다 (오탐 방지)
NO_TAG_SUPPORT = {
    "aws_route", "aws_route_table_association", "aws_iam_role_policy",
    "aws_iam_role_policy_attachment",
}


def walk(mod):
    for r in mod.get("resources", []):
        yield r
    for c in mod.get("child_modules", []):
        yield from walk(c)


def provider_region(plan):
    cfg = (plan.get("configuration") or {}).get("provider_config") or {}
    for name, pc in cfg.items():
        if not str(name).startswith("aws"):
            continue
        expr = (pc.get("expressions") or {}).get("region") or {}
        if "constant_value" in expr:
            return ("constant", expr["constant_value"])
        if expr:
            return ("non_constant", None)
        return ("missing", None)
    return ("missing", None)


def _walk_configuration(module):
    for resource in module.get("resources", []) or []:
        if isinstance(resource, dict):
            yield resource
    for child in (module.get("module_calls") or {}).values():
        if isinstance(child, dict) and isinstance(child.get("module"), dict):
            yield from _walk_configuration(child["module"])


def _nested_expression(resource, path):
    value = resource.get("expressions") or {}
    for component in path:
        if isinstance(component, int):
            if not isinstance(value, list) or component >= len(value):
                return {}
            value = value[component]
        else:
            if not isinstance(value, dict):
                return {}
            value = value.get(component) or {}
    return value if isinstance(value, dict) else {}


def _expression_references(resource, path):
    expression = _nested_expression(resource, path)
    references = {str(value) for value in expression.get("references") or []}
    # terraform show -json includes every traversal prefix as well as the final
    # attribute (resource, resource[0], resource[0].id). Compare only maximal
    # traversals so a legitimate prefix closure neither fails nor hides a second
    # unrelated terminal reference.
    return {
        reference
        for reference in references
        if not any(
            other != reference
            and (other.startswith(reference + ".") or other.startswith(reference + "["))
            for other in references
        )
    }


def audit_https_configuration_bindings(plan):
    """Check exact source/target references that planned values may leave unknown."""
    root = ((plan.get("configuration") or {}).get("root_module") or {})
    resources = {}
    for resource in _walk_configuration(root):
        address = re.sub(r"\[\d+\]$", "", str(resource.get("address", "")))
        resources[address] = resource

    requirements = {
        ("aws_vpc_security_group_ingress_rule.cloudfront_preview", ("security_group_id",)): {
            "aws_security_group.runtime.id"
        },
        (
            "aws_vpc_security_group_ingress_rule.cloudfront_preview",
            ("referenced_security_group_id",),
        ): {"data.aws_security_group.cloudfront_vpc_origin_service[0].id"},
        ("aws_nat_gateway.preview", ("allocation_id",)): {"aws_eip.preview_nat[0].id"},
        ("aws_nat_gateway.preview", ("subnet_id",)): {"aws_subnet.public.id"},
        ("aws_route.private_preview_internet", ("route_table_id",)): {
            "aws_route_table.private_preview[0].id"
        },
        ("aws_route.private_preview_internet", ("nat_gateway_id",)): {
            "aws_nat_gateway.preview[0].id"
        },
        ("aws_route_table_association.private_preview", ("subnet_id",)): {
            "aws_subnet.private_preview[0].id"
        },
        ("aws_route_table_association.private_preview", ("route_table_id",)): {
            "aws_route_table.private_preview[0].id"
        },
        ("aws_instance.runtime", ("subnet_id",)): {
            "var.enable_aws_https_preview",
            "aws_subnet.private_preview[0].id",
            "aws_subnet.public.id",
        },
        ("aws_instance.runtime", ("vpc_security_group_ids",)): {
            "aws_security_group.runtime.id"
        },
        (
            "aws_cloudfront_vpc_origin.preview",
            ("vpc_origin_endpoint_config", 0, "arn"),
        ): {"aws_instance.runtime.arn"},
        (
            "aws_cloudfront_distribution.preview",
            ("origin", 0, "domain_name"),
        ): {"aws_instance.runtime.private_dns"},
        (
            "aws_cloudfront_distribution.preview",
            ("origin", 0, "vpc_origin_config", 0, "vpc_origin_id"),
        ): {"aws_cloudfront_vpc_origin.preview[0].id"},
        (
            "aws_cloudfront_distribution.preview",
            (
                "default_cache_behavior", 0, "function_association", 0,
                "function_arn",
            ),
        ): {"aws_cloudfront_function.preview_gate[0].arn"},
    }
    errors = []
    for (address, path), expected in requirements.items():
        resource = resources.get(address)
        if resource is None:
            errors.append(f"HTTPS configuration binding resource is missing ({address})")
            continue
        observed = _expression_references(resource, path)
        if observed != expected:
            field = ".".join(f"[{part}]" if isinstance(part, int) else part for part in path)
            errors.append(
                f"HTTPS configuration binding drift ({address}.{field}): "
                f"expected={sorted(expected)!r} observed={sorted(observed)!r}"
            )
    return errors


def audit_cloudfront_planned_topology(address, values):
    """Require one VPC origin and one default behavior routed to that origin."""
    errors = []
    expected_origin_id = "jcareer-runtime-vpc-origin"
    origins = values.get("origin") or []
    if not isinstance(origins, list) or len(origins) != 1:
        return [f"CloudFront preview origin cardinality must be exactly one ({address})"]
    origin = origins[0] if isinstance(origins[0], dict) else {}
    if origin.get("origin_id") != expected_origin_id:
        errors.append(f"CloudFront preview origin_id drift ({address})")
    vpc_origins = origin.get("vpc_origin_config") or []
    if not isinstance(vpc_origins, list) or len(vpc_origins) != 1:
        errors.append(f"CloudFront preview must use exactly one VPC-origin config ({address})")
    for field in ("custom_origin_config", "s3_origin_config", "custom_header"):
        if origin.get(field):
            errors.append(f"CloudFront preview origin has an unreviewed {field} ({address})")
    behaviors = values.get("default_cache_behavior") or []
    if not isinstance(behaviors, list) or len(behaviors) != 1:
        errors.append(f"CloudFront preview default behavior cardinality drift ({address})")
    else:
        behavior = behaviors[0] if isinstance(behaviors[0], dict) else {}
        if behavior.get("target_origin_id") != expected_origin_id:
            errors.append(f"CloudFront preview default behavior retargeted ({address})")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--region", default=REGION)
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    res = list(walk((plan.get("planned_values") or {}).get("root_module") or {}))
    errs, ec2, ebs_total = [], 0, 0
    managed = [
        item
        for item in res
        if item.get("mode") != "data" and not str(item.get("address", "")).startswith("data.")
    ]
    managed_addresses = {str(item.get("address")) for item in managed}
    preview_enabled = bool(managed_addresses & HTTPS_PREVIEW_ADDRESSES)
    bedrock_enabled = bool(managed_addresses & BEDROCK_MANAGED_ADDRESSES)
    expected_managed = (
        BASE_MANAGED_ADDRESSES
        | (HTTPS_PREVIEW_ADDRESSES if preview_enabled else set())
        | (BEDROCK_MANAGED_ADDRESSES if bedrock_enabled else set())
    )
    # Repository fixtures intentionally isolate individual guard conditions. A
    # real `terraform show -json` document carries format_version; enforce the
    # exact deployed graph only for that real-plan contract.
    if plan.get("format_version") and managed_addresses != expected_managed:
        missing = sorted(expected_managed - managed_addresses)
        unexpected = sorted(managed_addresses - expected_managed)
        errs.append(
            "managed resource exact-address drift: "
            f"missing={missing!r} unexpected={unexpected!r}"
        )
    if plan.get("format_version") and preview_enabled:
        errs.extend(audit_https_configuration_bindings(plan))

    kind, val = provider_region(plan)
    if kind == "constant":
        if val != a.region:
            errs.append(f"리전이 {val} — {a.region} 만 허용")
    elif kind == "non_constant":
        errs.append("provider region 이 변수/표현식이다 — 상수 "
                    f"{a.region} 만 허용 (검증 불가한 값은 통과시키지 않는다)")
    else:
        errs.append(f"provider region 이 지정되지 않았다 — 상수 {a.region} 를 명시하라")

    for r in res:
        t, addr = r.get("type"), r.get("address")
        v = r.get("values") or {}

        if r.get("mode") == "data" or str(addr).startswith("data."):
            if addr not in ALLOWED_DATA_ADDRESSES:
                errs.append(f"승인 목록 밖 data source {t} ({addr})")
            elif addr == "data.aws_ssm_parameter.al2023_ami" and v.get("name") not in {
                None,
                "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
            }:
                errs.append("AMI data source가 승인된 AL2023 public parameter를 가리키지 않는다")
            continue

        if t not in ALLOWED_RESOURCE_TYPES:
            errs.append(f"승인 목록 밖 리소스 {t} ({addr}) — lab allowlist 에 없다. "
                        f"필요하면 사람이 ALLOWED_RESOURCE_TYPES 에 추가해야 한다")
            continue

        if t == "aws_instance":
            ec2 += 1
            it = v.get("instance_type")
            if it not in ALLOWED_INSTANCE_TYPES:
                errs.append(f"허용되지 않은 인스턴스 타입 {it} ({addr})")
            if v.get("key_name") not in {None, ""}:
                errs.append(f"EC2 key pair 사용 금지 ({addr})")
            if v.get("monitoring") is not False:
                errs.append(f"상세 모니터링은 false여야 한다 ({addr})")
            expected_public_ip = not preview_enabled
            if v.get("associate_public_ip_address") is not expected_public_ip:
                errs.append(
                    f"EC2 public-IP mode={v.get('associate_public_ip_address')!r}; "
                    f"HTTPS preview={preview_enabled} requires {expected_public_ip!r} ({addr})"
                )

            metadata = v.get("metadata_options") or []
            metadata = metadata[0] if isinstance(metadata, list) and metadata else metadata
            if not isinstance(metadata, dict):
                metadata = {}
            expected_metadata = {
                "http_endpoint": "enabled",
                "http_tokens": "required",
                "http_put_response_hop_limit": 1,
                "http_protocol_ipv6": "disabled",
                "instance_metadata_tags": "disabled",
            }
            for field, expected in expected_metadata.items():
                if metadata.get(field) != expected:
                    errs.append(
                        f"metadata_options.{field}={metadata.get(field)!r}; "
                        f"{expected!r} 필요 ({addr})"
                    )

            credits = v.get("credit_specification") or []
            credits = credits[0] if isinstance(credits, list) and credits else credits
            if not isinstance(credits, dict) or credits.get("cpu_credits") != "standard":
                errs.append(f"T3 cpu_credits=standard 필요 ({addr})")
            root = v.get("root_block_device") or []
            if not root:
                errs.append(f"root_block_device 미명세 ({addr}) — 크기·종류를 명시하라")
            for blk in root:
                sz, vt = blk.get("volume_size") or 0, blk.get("volume_type")
                iops = blk.get("iops") or 0
                ebs_total += sz
                if sz == 0:
                    errs.append(f"root volume_size 미명세 ({addr})")
                if sz > MAX_EBS_PER_VOL_GB:
                    errs.append(f"root 볼륨 {sz}GB > {MAX_EBS_PER_VOL_GB}GB ({addr})")
                if vt not in ALLOWED_VOLUME_TYPES:
                    errs.append(f"root 볼륨 종류 {vt} 금지 — {sorted(ALLOWED_VOLUME_TYPES)} ({addr})")
                if iops > MAX_IOPS:
                    errs.append(f"root IOPS {iops} > {MAX_IOPS} ({addr})")
                if blk.get("encrypted") is not True:
                    errs.append(f"root 볼륨 암호화 필요 ({addr})")
                if blk.get("delete_on_termination") is not True:
                    errs.append(f"root delete_on_termination=true 필요 ({addr})")
                if iops != 3000:
                    errs.append(f"root IOPS는 정확히 3000이어야 한다 ({addr})")
            if v.get("ebs_block_device"):
                errs.append(f"추가 ebs_block_device는 현재 lab 계약 밖이다 ({addr})")

        if t == "aws_vpc_security_group_ingress_rule":
            if addr != "aws_vpc_security_group_ingress_rule.cloudfront_preview[0]":
                errs.append(f"승인되지 않은 ingress address ({addr})")
            if v.get("ip_protocol") != "tcp" or v.get("from_port") != 3000 or v.get("to_port") != 3000:
                errs.append(f"HTTPS preview ingress는 TCP/3000만 허용한다 ({addr})")
            if any(v.get(field) not in {None, ""} for field in (
                "cidr_ipv4", "cidr_ipv6", "prefix_list_id"
            )):
                errs.append(f"HTTPS preview ingress에 CIDR/prefix-list source가 있다 ({addr})")

        if t == "aws_subnet":
            if addr == "aws_subnet.public" and v.get("map_public_ip_on_launch") is not True:
                errs.append(f"NAT subnet은 public-IP mapping이 필요하다 ({addr})")
            if (
                addr == "aws_subnet.private_preview[0]"
                and v.get("map_public_ip_on_launch") is not False
            ):
                errs.append(f"VPC origin subnet은 public-IP mapping이 없어야 한다 ({addr})")

        if t == "aws_eip" and (
            addr != "aws_eip.preview_nat[0]" or v.get("domain") != "vpc"
        ):
            errs.append(f"승인되지 않은 EIP 경계 ({addr})")

        if t == "aws_nat_gateway" and addr != "aws_nat_gateway.preview[0]":
            errs.append(f"승인되지 않은 NAT gateway address ({addr})")

        if t == "aws_route" and addr == "aws_route.private_preview_internet[0]":
            if v.get("destination_cidr_block") != "0.0.0.0/0":
                errs.append(f"private preview route must target only 0.0.0.0/0 ({addr})")

        if t == "aws_cloudfront_function":
            if v.get("runtime") != "cloudfront-js-2.0" or v.get("publish") is not True:
                errs.append(f"CloudFront preview gate는 published runtime 2.0이어야 한다 ({addr})")

        if t == "aws_cloudfront_vpc_origin":
            endpoint = v.get("vpc_origin_endpoint_config") or []
            endpoint = endpoint[0] if isinstance(endpoint, list) and endpoint else {}
            if (
                endpoint.get("http_port") != 3000
                or endpoint.get("origin_protocol_policy") != "http-only"
            ):
                errs.append(f"CloudFront VPC origin은 내부 HTTP/3000만 허용한다 ({addr})")

        if t == "aws_cloudfront_distribution":
            errs.extend(audit_cloudfront_planned_topology(addr, v))
            if v.get("enabled") is not True or v.get("is_ipv6_enabled") is not False:
                errs.append(f"CloudFront preview는 enabled IPv4-only여야 한다 ({addr})")
            if v.get("web_acl_id") not in {None, ""}:
                errs.append(f"승인되지 않은 CloudFront Web ACL이 연결됐다 ({addr})")
            if v.get("aliases"):
                errs.append(f"승인되지 않은 CloudFront 별칭/도메인이 있다 ({addr})")
            if v.get("logging_config"):
                errs.append(f"CloudFront access logging은 이번 토큰 프리뷰 범위 밖이다 ({addr})")
            behavior = v.get("default_cache_behavior") or []
            behavior = behavior[0] if isinstance(behavior, list) and behavior else {}
            if not isinstance(behavior, dict):
                behavior = {}
            if set(behavior.get("allowed_methods") or []) != {
                "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT",
            }:
                errs.append(f"CloudFront preview가 앱의 exact HTTP method 집합을 전달하지 않는다 ({addr})")
            if behavior.get("viewer_protocol_policy") != "redirect-to-https":
                errs.append(f"CloudFront preview는 viewer HTTPS redirect가 필요하다 ({addr})")
            if behavior.get("cache_policy_id") != CLOUDFRONT_CACHING_DISABLED_POLICY_ID:
                errs.append(f"CloudFront preview cache가 명시적으로 비활성화되지 않았다 ({addr})")
            if (
                behavior.get("origin_request_policy_id")
                != CLOUDFRONT_ALL_VIEWER_EXCEPT_HOST_POLICY_ID
            ):
                errs.append(f"CloudFront preview가 viewer request 문맥을 보존하지 않는다 ({addr})")
            functions = behavior.get("function_association") or []
            if (
                len(functions) != 1
                or functions[0].get("event_type") != "viewer-request"
            ):
                errs.append(f"CloudFront preview viewer-request gate 연결이 exact하지 않다 ({addr})")
            certificates = v.get("viewer_certificate") or []
            certificate = certificates[0] if isinstance(certificates, list) and certificates else {}
            if (
                not isinstance(certificate, dict)
                or certificate.get("cloudfront_default_certificate") is not True
                or certificate.get("minimum_protocol_version") != "TLSv1.2_2021"
            ):
                errs.append(f"CloudFront preview viewer TLS 최소 정책이 TLSv1.2_2021이 아니다 ({addr})")

        if t == "aws_iam_role_policy":
            if addr != "aws_iam_role_policy.bedrock[0]":
                errs.append(f"승인되지 않은 inline role policy address ({addr})")
            try:
                policy = json.loads(v.get("policy") or "")
                statements = policy.get("Statement") or []
                statement = statements[0] if len(statements) == 1 else {}
                actions = statement.get("Action")
                actions = {actions} if isinstance(actions, str) else set(actions or [])
                resources = statement.get("Resource")
                resources = {resources} if isinstance(resources, str) else set(resources or [])
                if actions != {"bedrock:InvokeModel"} or len(resources) != 2:
                    errs.append(f"Bedrock inline policy action/resource boundary drift ({addr})")
                if not all(
                    isinstance(resource, str)
                    and (
                        resource.endswith(":foundation-model/amazon.nova-lite-v1:0")
                        or ":inference-profile/apac.amazon.nova-lite-v1:0" in resource
                    )
                    for resource in resources
                ):
                    errs.append(f"Bedrock inline policy model allowlist drift ({addr})")
            except (TypeError, ValueError, json.JSONDecodeError):
                errs.append(f"Bedrock inline policy JSON is invalid ({addr})")

        if t == "aws_security_group" and v.get("ingress"):
            errs.append(f"inline security-group ingress는 허용되지 않는다 ({addr})")

        if t.startswith("aws_") and t not in NO_TAG_SUPPORT:
            tags = v.get("tags") or v.get("tags_all") or {}
            if tags.get("jk_layer") != "lab":
                errs.append(f"태그 누락 jk_layer=lab ({addr})")

    if ec2 != REQUIRED_EC2_COUNT:
        errs.append(f"EC2 인스턴스 {ec2}대 — 정확히 {REQUIRED_EC2_COUNT}대여야 한다")
    if ebs_total > MAX_EBS_TOTAL_GB:
        errs.append(f"EBS 총량 {ebs_total}GB > {MAX_EBS_TOTAL_GB}GB")
    if len(managed) > MAX_RESOURCES:
        errs.append(f"managed 리소스 총수 {len(managed)} > {MAX_RESOURCES}")

    print(
        f"lab managed {len(managed)}건 · Bedrock={bedrock_enabled} · HTTPS preview={preview_enabled} · "
        f"EC2 {ec2}대 · EBS {ebs_total}GB · region={kind}:{val}"
    )
    for e in errs:
        print(f"::error::{e}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
