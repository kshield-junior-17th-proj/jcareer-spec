# AWS 검증 Lab 재시도용 IAM 권한 — 2026-08-30

## 목적

2026-08-30 Lab 적용은 런타임 IAM 역할을 만들 권한이 없어 중단됐다. 이 문서는 다음
재시도에 필요한 권한을 소스 기준으로 좁혀 적은 체크리스트다. 계정 전체 관리자 권한을
요구하지 않으며, 계정 번호·ARN·리소스 ID·자격 증명은 기록하지 않는다.

삭제 전용 저장 계획 적용과 사후 재고 확인을 통과해 현재 Lab 상태는 0개다. 권한을 준비한
뒤에도 이전 계획 파일이나 해시를 재사용하지 않고 새 계획부터 다시 시작한다.

## 1. 이번 중단 지점을 통과하는 권한

런타임 역할과 인스턴스 프로필을 만들고 정리하려면 다음 작업이 필요하다. 아래 작업명에는
모두 `iam:` 접두사를 붙인다.

- 역할: `CreateRole`, `GetRole`, `DeleteRole`, `TagRole`, `UntagRole`,
  `ListRoleTags`, `ListRolePolicies`, `GetRolePolicy`, `ListAttachedRolePolicies`,
  `ListInstanceProfilesForRole`
- 관리형 정책 연결: `AttachRolePolicy`, `DetachRolePolicy`
- 인스턴스 전달: `PassRole`
- 인스턴스 프로필: `CreateInstanceProfile`, `GetInstanceProfile`,
  `DeleteInstanceProfile`, `TagInstanceProfile`, `UntagInstanceProfile`,
  `ListInstanceProfileTags`, `AddRoleToInstanceProfile`,
  `RemoveRoleFromInstanceProfile`
- Bedrock 경로를 켤 때만: `PutRolePolicy`, `DeleteRolePolicy`

새 역할을 만드는 현재 재시도에는 `UpdateAssumeRolePolicy`가 필요하지 않다. 나중에 신뢰
정책의 변경을 교정해야 한다면 그 작업을 별도로 검토한다.

## 2. 아직 적용이 도달하지 못한 구간

앞의 권한 문제가 해결된 뒤에는 아래 작업도 필요하다. 작업명에는 해당 서비스 접두사를
붙여 정책에 입력한다. 예를 들어 `RunInstances`는 `ec2:RunInstances`다.

| 구간 | 필요한 작업 |
|---|---|
| EC2 실행 서버 | `RunInstances`, `TerminateInstances`, `StopInstances`, `DescribeInstances`, `DescribeInstanceAttribute`, `DescribeInstanceStatus`, `DescribeInstanceTypes`, `DescribeImages`, `DescribeVolumes`, `DescribeInstanceCreditSpecifications`, `ModifyInstanceCreditSpecification`, `ModifyInstanceMetadataOptions` |
| EC2 보안 그룹의 CloudFront 전용 인바운드 | `AuthorizeSecurityGroupIngress`, `RevokeSecurityGroupIngress`; 보안 그룹 조회는 앞 단계에서 확인됨 |
| CloudFront VPC 원본 | `CreateVpcOrigin`, `GetVpcOrigin`, `ListVpcOrigins`, `UpdateVpcOrigin`, `DeleteVpcOrigin`, `TagResource`, `ListTagsForResource` |
| CloudFront 배포 | `CreateDistributionWithTags`, `CreateDistribution`, `GetDistribution`, `GetDistributionConfig`, `UpdateDistribution`, `DeleteDistribution`, `TagResource`, `ListTagsForResource` |
| SSM 런타임 전송 | `SendCommand`, `GetCommandInvocation`, `ListCommandInvocations`, `DescribeInstanceInformation` |

계획 단계에서는 STS 신원 확인과 SSM 공개 AMI 파라미터 조회가 통과했다. 부분 적용과
삭제에서는 앞 단계 네트워크, Budget, CloudFront Function 관련 작업이 통과했다. 이는
서비스 전체 권한이 충분하다는 뜻이 아니라, 관찰한 경로가 그 지점까지 진행됐다는 뜻이다.

## 3. 권한 범위를 좁히는 조건

- 역할과 인스턴스 프로필은 `jcareer-runtime-lab-runtime`, Bedrock 인라인 정책은
  `jcareer-runtime-lab-bedrock`으로 정확히 제한한다. 이름 설정을 바꿔야 할 때만
  `jcareer-runtime-lab-*` 접두사 범위를 검토한다.
- 관리형 정책 연결은 `AmazonSSMManagedInstanceCore` 하나만 허용한다.
- `PassRole`은 전달 대상 서비스를 `ec2.amazonaws.com`으로 제한한다.
- 생성 가능한 리소스는 요청 태그 `jk_layer=lab`, 변경·삭제는 리소스 태그
  `jk_layer=lab` 조건을 사용한다.
- 태그를 지원하지 않는 route, route-table association, inline-role-policy,
  role-policy-attachment는 코드의 상위 리소스와 이름 범위로 제한한다.
- 리전 조건을 서울 `ap-northeast-2`로 제한한다.
- SSM `SendCommand`는 대상 Lab 인스턴스와 고정 문서 `AWS-RunShellScript`로 제한한다.
- Bedrock 인라인 정책 작성 권한에는 permissions boundary 적용을 함께 검토한다.
- `AdministratorAccess`는 사용하지 않는다.

## 4. 재시도 순서

1. 위 범위로 만든 정책을 새 검증 계정의 배포 주체에 연결하고, Bedrock을 켠다면 대상
   모델 접근이 여전히 가능한지 확인한다.
2. 대상 AWS 프로필을 명시하고, 소비 마커나 이전 계획 파일이 남지 않았는지 확인한다.
3. Lab 정적 검사와 단위시험을 다시 통과시킨다.
4. 최종 HTTPS·Bedrock 설정으로 plan-only를 새로 실행한다.
5. HTTPS와 Bedrock을 함께 켜면 생성 24, Bedrock을 끄면 23이며 변경 0·삭제 0인지와
   새 해시 세 개를 대조한다.
6. 같은 설정·같은 임시 토큰·새 해시로 저장된 동일 계획만 적용한다.
7. 여섯 서비스, HTTPS 경계, Bedrock 전체 경로와 배포 직후 파일·소켓 소유권 단정을
   확인한 후 시연이 끝나면 저장된 삭제 계획으로 정리한다.

중간에 다시 실패하면 마커를 임의로 지우지 않는다. 실제 상태를 먼저 확인하고, 확인된
부분 리소스만 담은 삭제 전용 저장 계획으로 복구한다. EC2 자동 중지는 NAT Gateway와
CloudFront 비용을 멈추지 않는다.

## 검토 한계

이 목록은 Terraform AWS provider 6 계열과 현재 Lab 소스에서 도출했다. 다음 성공 실행 뒤
CloudTrail에서 실제 호출 작업을 확인하면 불필요한 작업을 더 줄일 수 있다. 이 문서는 권한
부여 결정, 운영 승인, 보안 통제 충족 판정을 대신하지 않는다.
