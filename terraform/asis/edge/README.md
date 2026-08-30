# terraform/asis/edge — 엣지 계층 AS-IS 재현 명세

Route 53 → CloudFront → AWS WAF 세 홉을 선언한다.
상위 규칙은 [`terraform/asis/README.md`](../README.md) 와 [`AGENTS.md`](../../../AGENTS.md) 에 있다.
**여기에 규칙을 중복 기술하지 않는다.** 이 문서는 이 모듈의 계약·근거·한계만 적는다.

```
구직자 / 기업 채용담당자
     │
  Route 53 ──▶ CloudFront ──▶ AWS WAF ──▶ ALB
  호스팅 영역    ALB 오리진      CLOUDFRONT scope   ← terraform/asis/compute 소관
  alias A       뷰어 TLS        Common + SQLi
```

근거:
`context/raw/인프라컨텍스트-외부협업용.md#2.2` ·
`context/raw/D02-진단대상-아키텍처-정의.md#3.1` ·
`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2`

이 코드는 J사가 보유한 IaC 가 아니다. J사 인프라는 콘솔 수동 구성이며
(`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5`) 컨설팅팀이 문서를 근거로 역으로 작성했다.
**apply 하지 않는다.**

---

## 1. provider 계약 — us-east-1 alias 를 요구한다

이 모듈은 aws provider 를 **두 개** 요구한다. 선언은 [`versions.tf`](versions.tf) 의
`configuration_aliases` 에 있다.

| provider | 리전 | 이 모듈에서 만드는 것 |
|---|---|---|
| `aws` | `ap-northeast-2` | `aws_route53_zone` · `aws_route53_record` · `aws_cloudfront_distribution` |
| `aws.us_east_1` | `us-east-1` | `aws_wafv2_web_acl` (scope `CLOUDFRONT`) · `aws_acm_certificate` |

**us-east-1 은 리전 선택이 아니라 AWS API 제약이다.**

- `scope = "CLOUDFRONT"` 인 `aws_wafv2_web_acl` 은 us-east-1 에만 만들 수 있다
- CloudFront 뷰어 인증서(ACM)는 us-east-1 에만 둘 수 있다

AS-IS 사실은 「리전 ap-northeast-2 (서울) 단일」
(`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2`) 이다. us-east-1 은 서비스 리전이 아니라
엣지 통제의 저장 위치이며, 「국내 리전 다중 AZ 구성」
(`context/raw/D02-진단대상-아키텍처-정의.md#3.1`) 진술과 모순되지 않는다.
**이 구분을 보고서에서 지운 채 쓰면 국외 이전 논점과 뒤섞인다.**

`configuration_aliases` 로 선언했으므로 이 요구는 README 문장이 아니라 **검증되는 계약**이다.
매핑 없이 호출하면 terraform 이 호출 시점에 실패한다.

### 호출 측이 넣어야 하는 것 — 사람에게 요청하는 변경

`terraform/asis/main.tf` 와 `terraform/asis/variables.tf` 는 **공유 파일**이고
이 브랜치는 그것을 고치지 않는다 (`BOOTSTRAP_PROMPT.md` Phase 1 · 모듈 배정).
아래를 사람이 반영해야 이 모듈이 루트에서 동작한다.

```hcl
# terraform/asis/main.tf 에 추가되어야 하는 것

provider "aws" {
  alias                       = "us_east_1"
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  access_key                  = "mock"
  secret_key                  = "mock"
}

module "edge" {
  source = "./edge"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  alb_origin_domain_name = module.compute.alb_dns_name   # terraform/asis/compute 출력
}
```

---

## 2. 입력

기본값은 **전량 가상값**이다. data source 를 쓰지 않으므로
(`terraform/asis/README.md` 「작성 규칙」) 평소 조회로 얻을 값을 상수 기본값으로 받는다.

| 이름 | 타입 | 기본값 | 근거 / 성격 |
|---|---|---|---|
| `domain_name` | `string` | `jcareer.example` | 합성 도메인. `.example` 은 RFC 2606 예약 TLD |
| `service_hostname` | `string` | `""` (apex) | 출처가 호스트명을 특정하지 않음 · `ASSUMED` |
| `hosted_zone_comment` | `string` | `J-Career AS-IS 재현 명세 — apply 금지` | 콘솔에서도 apply 금지를 드러낸다 |
| `alb_origin_domain_name` | `string` | 가상 ALB DNS | `인프라컨텍스트-외부협업용.md#2.2` · compute 모듈 출력을 받는 자리 |
| `alb_origin_id` | `string` | `asis-jcareer-alb-origin` | 캐시 동작이 참조 |
| `origin_ssl_protocols` | `list(string)` | `["TLSv1.2"]` | `SCENARIO_FACTS-가상고객사J사.md#9.2` 「ALB … TLS 1.2+ 종단」 |
| `cloudfront_minimum_protocol_version` | `string` | `TLSv1.2_2021` | 뷰어 구간은 출처에 없음 · `ASSUMED` |
| `cloudfront_price_class` | `string` | `PriceClass_200` | 출처에 없음 · `ASSUMED` |
| `cloudfront_cache_policy_id` | `string` | Managed-CachingDisabled | 동적 응답 재현. data source 대체 상수 |
| `cloudfront_origin_request_policy_id` | `string` | Managed-AllViewer | 인증 컨텍스트 전달. data source 대체 상수 |
| `web_acl_name` | `string` | `asis-jcareer-edge` | — |
| `web_acl_metric_prefix` | `string` | `asisJcareerEdge` | CloudWatch 지표 접두 |
| `common_tags` | `map(string)` | `jk_layer` · `jk_apply` | `terraform/asis/README.md` 「필수 태그」. `jk_source` 는 리소스마다 merge |

**`ASSUMED` 표기 세 건은 출처에 없는 값이다.** 사람이 확정하기 전까지 확정 사실로 인용하지 않는다.
`AGENTS.md` 의 상태 어휘를 그대로 쓴다.

## 3. 출력

| 이름 | 용도 |
|---|---|
| `service_fqdn` | 접속 FQDN |
| `hosted_zone_id` · `hosted_zone_name_servers` | 위임 좌표 |
| `cloudfront_distribution_id` · `_arn` · `_domain_name` · `_hosted_zone_id` | 배포 좌표 |
| `cloudfront_origin_id` | compute 모듈 ALB 와 짝 |
| `acm_certificate_arn` | 뷰어 인증서 (us-east-1) |
| `web_acl_arn` · `web_acl_id` | Web ACL 좌표 |
| `web_acl_managed_rule_groups` | 적용된 관리형 규칙 그룹 이름 목록 — GAP-WAF-01 증적 |

`web_acl_managed_rule_groups` 는 **사람이 읽는 증적값이지 판정값이 아니다.** `AGENTS.md` §0.

---

## 4. WAF — 관리형 두 개뿐인 것이 AS-IS 다

```
default_action  allow
  rule 1  AWSManagedRulesCommonRuleSet   priority 1  override_action none
  rule 2  AWSManagedRulesSQLiRuleSet     priority 2  override_action none
  (이 다음에 아무것도 없다)
```

근거:
`context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` —
「엣지 | Route 53 → CloudFront → AWS WAF 적용 (관리형 규칙셋 `AWSManagedRulesCommonRuleSet` + `SQLi`) | Q01」

Web ACL 은 **CloudFront 에 연결한다.** ALB 가 아니다
(`context/raw/인프라컨텍스트-외부협업용.md#2.2` 「Web ACL은 CloudFront에 연결」).
그래서 `aws_wafv2_web_acl_association` 을 쓰지 않고 배포의 `web_acl_id` 로 건다.

### GAP-WAF-01 [ABSENCE]

「WAF 자유서술 입력 커스텀 규칙 없음 — 관리형 규칙셋만」
근거: `context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2` ·
`context/raw/인프라컨텍스트-외부협업용.md#2.2` · `terraform/asis/ABSENCE_MANIFEST.md`

근거 주석은 [`main.tf`](main.tf) 의 규칙 2 바로 다음, 즉 **커스텀 규칙이 있었어야 할 자리**에 둔다.
아래를 추가하면 AS-IS 가 사라지고 재현이 실패한다.

```
aws_wafv2_regex_pattern_set                          — 의도적 미선언
rule.statement.regex_pattern_set_reference_statement — 의도적 미선언
rule.statement.byte_match_statement (커스텀)          — 의도적 미선언
rule.statement.rate_based_statement                  — 의도적 미선언
```

`scripts/check_expected_findings.py` 가 plan JSON 에서
`rule.statement.regex_pattern_set_reference_statement` 가 **전 규칙에** 없는지 확인한다.

## 5. 이 모듈에 있는 다른 미선언

| 미선언 | 성격 | 근거 |
|---|---|---|
| `aws_route53_resolver_firewall_rule_group` 외 2종 | **GAP-EGRESS-01** [ABSENCE] | `인프라컨텍스트-외부협업용.md#2.2` · `context/proposals/docs-current/CURRENT_DECISIONS_DELTA.md#D-07` (비권위 초안) |
| `aws_kms_key` | **GAP-KMS-01** [ABSENCE] | `SCENARIO_FACTS-가상고객사J사.md#9.2` |
| CloudFront 액세스 로그 (`logging_config`) | 명세된 GAP 아님. 출처의 로그 목록에 없음 | `SCENARIO_FACTS-가상고객사J사.md#9.2` · 인터뷰 Q02 |
| WAF 로깅 (`aws_wafv2_web_acl_logging_configuration`) | 명세된 GAP 아님. 출처에 없음 | 위와 같음 · 인터뷰 Q01 |
| Route 53 쿼리 로깅 (`aws_route53_query_log`) | 명세된 GAP 아님. 출처에 없음 | 위와 같음 |
| IPv6 AAAA alias | `UNVERIFIED`. 출처가 IPv6 여부를 기술하지 않음 | — |
| CloudFront 함수 · Lambda@Edge · OAC | 도면에 없음. 오리진이 S3 가 아니므로 OAC 는 성립하지 않음 | `terraform/asis/README.md` |
| DNS 검증 레코드 · `aws_acm_certificate_validation` | **재현 명세의 한계이지 AS-IS 결함이 아니다** | 아래 §6 |

**GAP ID 를 새로 만들지 않았다.** 위 「명세된 GAP 아님」 항목은 관찰이지 판정이 아니며,
`docs/current/EXPECTED_FINDINGS.yaml` 에 등재할지는 사람이 정한다. `AGENTS.md` §0 · §4.

## 6. 재현 명세의 한계 — 결함이 아닌 것

`aws_acm_certificate` 의 `domain_validation_options` 는 apply 전까지 값이 정해지지 않는다.
그 위에서 `for_each` 를 돌려 검증 레코드를 만들면 plan 이 깨지고, 자격증명 없는 plan 계약이
성립하지 않는다. 이 디렉토리는 apply 대상이 아니므로 검증 레코드를 만들 실익도 없다.
**이것은 J사의 결함이 아니라 이 재현 명세의 한계다.** 보고서에서 GAP 으로 옮기지 않는다.

---

## 7. 검증

이 모듈은 `configuration_aliases` 를 선언하므로 **단독 루트로는 `validate` 가 실패한다.**
그게 정상이다 — 계약이 동작한다는 증거다.

```
$ terraform -chdir=terraform/asis/edge validate
Error: Provider configuration not present
  ... provider["registry.terraform.io/hashicorp/aws"].us_east_1 is required
```

검증은 **호출 측 루트에서** 한다. 공유 `terraform/asis/main.tf` 가 생기면 그것이 루트다.
그 전까지는 저장소 밖 스크래치 하네스에 §1 의 provider 두 개와 `module "edge"` 호출을 두고 돌린다.

```bash
terraform fmt -check -recursive terraform/asis/edge     # 이 모듈만
terraform -chdir=<루트> init -backend=false
terraform -chdir=<루트> validate
terraform -chdir=<루트> plan -out=tfplan -input=false -lock=false
```

작성 시점 결과: `fmt` clean · `validate` Success · 자격증명 없는 `plan` 성공 (5 to add) ·
GAP-WAF-01 · GAP-EGRESS-01 · GAP-KMS-01 세 건 재현 확인.

### 아직 통과하지 못하는 것 — 공유 루트 선행 조건

```
python scripts/check_asis_contract.py . terraform/asis
  ::error::provider "aws" 블록을 찾지 못했다
```

이 검사는 `terraform/asis` **전체**에서 mock `provider "aws"` 블록을 찾는다.
그 블록의 자리는 공유 `terraform/asis/main.tf` 이고 아직 없다.
**모듈이 자기 안에 `provider` 블록을 두면 안 된다** — 자식 모듈의 provider 설정은
호출 측 매핑을 무력화하고 모듈 제거·이동을 막으며, 병렬로 작업하는 다른 5개 모듈과 충돌한다.
같은 이유로 CI 의 `terraform -chdir=terraform/asis init` 도 루트 `.tf` 가 생겨야 통과한다.

**이 두 건은 이 모듈의 결함이 아니라 공유 루트 파일의 선행 조건이다.**
`terraform/asis/main.tf` · `variables.tf` 는 사람이 관리한다 (`BOOTSTRAP_PROMPT.md` Phase 1).

확인한 사실 — `terraform/asis` 루트에 mock `provider "aws"` 블록 하나를 임시로 두고
검사를 돌리면 `exit=0` 이 된다. 그 파일은 커밋하지 않았다.
`tests/run_all_tests.sh` 의 L 마지막 케이스
「`.tf` 없으면 생략 (Phase 1 이전)」도 같은 이유로 실패한다. 그 케이스의 전제는
`terraform/asis` 에 `.tf` 가 하나도 없는 Phase 0 상태이며, Phase 1 이 시작되면
전제가 소멸한다. 루트 `main.tf` 가 들어오면 같은 케이스가 「생략」이 아니라
「실제로 검사해서 깨끗함」으로 다시 통과한다. 시험 파일은 고치지 않았다.

### 남기는 관찰 — `check_asis_contract.py` 가 주석을 걷어내지 않는다

`scripts/check_asis_contract.py` 는 `.tf` 원문에 정규식을 걸 뿐 주석을 제거하지 않는다.
그래서 **주석 안의 예시 `provider "aws" { ... }` 가 mock provider 요건을 충족시킨다.**
`terraform/asis` 어느 파일이든 주석 하나로 전체 계층의 `skip_*` 검사가 초록이 된다.

이 모듈의 `versions.tf` 초안이 실제로 그 상태였고, 걸린 뒤 예시를 README 로 옮겼다.
같은 함정을 다른 모듈이 밟을 수 있다. 검사기 수정은 이 모듈 범위 밖이므로
`scripts/` 를 고치지 않고 관찰만 남긴다. 판정과 조치는 사람이 정한다.
