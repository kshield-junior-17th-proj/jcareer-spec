#!/usr/bin/env python3
"""terraform/lab 비용·노출 plan 가드레일 — V2.2.

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
"""
import argparse, json, sys

REGION = "ap-northeast-2"
ALLOWED_INSTANCE_TYPES = {"t3.small"}
REQUIRED_EC2_COUNT = 1
MAX_EBS_TOTAL_GB = 30
MAX_EBS_PER_VOL_GB = 30
ALLOWED_VOLUME_TYPES = {"gp3"}
MAX_IOPS = 3000
MAX_RESOURCES = 40

# 사람이 승인한 low-cost 리소스만. 여기 없으면 실패한다.
ALLOWED_RESOURCE_TYPES = {
    "aws_instance",
    "aws_vpc", "aws_subnet", "aws_internet_gateway", "aws_route_table",
    "aws_route", "aws_route_table_association", "aws_security_group",
    "aws_vpc_security_group_egress_rule",
    "aws_iam_role",
    "aws_iam_role_policy_attachment", "aws_iam_instance_profile",
    "aws_budgets_budget",
}
ALLOWED_DATA_ADDRESSES = {
    "data.aws_ssm_parameter.al2023_ami",
    "data.aws_iam_policy_document.ec2_assume",
    "data.aws_iam_policy_document.bedrock",
}
# 태그를 지원하지 않는 타입 — 태그 요구에서 제외한다 (오탐 방지)
NO_TAG_SUPPORT = {
    "aws_route", "aws_route_table_association", "aws_iam_role_policy_attachment",
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--region", default=REGION)
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    res = list(walk((plan.get("planned_values") or {}).get("root_module") or {}))
    errs, ec2, ebs_total = [], 0, 0

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
            if v.get("associate_public_ip_address") is not True:
                errs.append(f"NAT 없는 단기 lab의 명시적 public egress 구성이 확인되지 않는다 ({addr})")

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

        if t == "aws_security_group" and v.get("ingress"):
            errs.append(f"security group inbound 규칙 금지 ({addr})")

        if t.startswith("aws_") and t not in NO_TAG_SUPPORT:
            tags = v.get("tags") or v.get("tags_all") or {}
            if tags.get("jk_layer") != "lab":
                errs.append(f"태그 누락 jk_layer=lab ({addr})")

    if ec2 != REQUIRED_EC2_COUNT:
        errs.append(f"EC2 인스턴스 {ec2}대 — 정확히 {REQUIRED_EC2_COUNT}대여야 한다")
    if ebs_total > MAX_EBS_TOTAL_GB:
        errs.append(f"EBS 총량 {ebs_total}GB > {MAX_EBS_TOTAL_GB}GB")
    if len(res) > MAX_RESOURCES:
        errs.append(f"리소스 총수 {len(res)} > {MAX_RESOURCES}")

    print(f"lab 리소스 {len(res)}건 · EC2 {ec2}대 · EBS {ebs_total}GB · region={kind}:{val}")
    for e in errs:
        print(f"::error::{e}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
