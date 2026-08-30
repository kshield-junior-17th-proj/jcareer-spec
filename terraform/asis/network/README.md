# AS-IS network module

이 모듈은 J-Career 서비스망의 2-AZ 네트워크 구성을 재현한다. `apply` 대상이 아니며,
AWS 자격증명 없이 정적 검증하는 명세다.

근거 앵커:

- `context/raw/인프라컨텍스트-외부협업용.md#2.2`
- `context/raw/D02-진단대상-아키텍처-정의.md#3.1`

## 구성

| 계층 | ap-northeast-2a | ap-northeast-2c | 라우팅 |
|---|---|---|---|
| Public | `10.0.0.0/24` | `10.0.1.0/24` | 공용 RT → IGW |
| Application | `10.0.10.0/24` | `10.0.11.0/24` | AZ별 RT → 같은 AZ의 NAT |
| Data | `10.0.20.0/24` | `10.0.21.0/24` | VPC-local 경로만 |

VPC는 `10.0.0.0/16`이고, IGW는 1개다. 각 Public subnet에 EIP와 NAT
Gateway를 하나씩 두므로 EIP 2개와 NAT Gateway 2개를 선언한다. 여섯 subnet 모두
명시적인 route table association을 가진다.

## Security groups

| SG | Ingress | Egress |
|---|---|---|
| ALB | TCP/443, IPv4 전체 | ECS SG의 TCP/3000 |
| ECS | ALB→3000, ECS self→8000/8100/8200 | 모든 IPv4 트래픽 |
| RDS | ECS SG→TCP/5432 | 미선언 |
| Cache | ECS SG→TCP/6379 | 미선언 |
| Endpoint | ECS SG→TCP/443 | 미선언 |

`GAP-EGRESS-01 [ABSENCE]`를 보존하기 위해 ECS 아웃바운드는 도메인 기반 필터 없이
`0.0.0.0/0`으로 선언한다. Network Firewall과 Route 53 Resolver Firewall은 이
모듈에 추가하지 않는다. 이 표와 주석은 구성 사실을 설명하며 적합성이나 잔여위험을
판정하지 않는다. 근거: `context/raw/인프라컨텍스트-외부협업용.md#2.2`

## Inputs and outputs

CIDR과 AZ 변수의 기본값 및 검증 조건은 승인된 2-AZ 범위를 고정한다.
`additional_tags`만 확장할 수 있으며 `jk_layer`, `jk_source`, `jk_apply` 태그는
덮어쓸 수 없다. subnet, NAT, route table, ALB/ECS/RDS/cache/endpoint SG ID를
후속 AS-IS 모듈에 출력한다.

## Validation

```text
terraform -chdir=terraform/asis/network fmt -check -recursive
terraform -chdir=terraform/asis/network init -backend=false
terraform -chdir=terraform/asis/network validate
python scripts/check_asis_contract.py . terraform/asis/network
```

`terraform apply`와 자격증명 사용은 금지한다. 이 모듈에는 data source가 없다.
