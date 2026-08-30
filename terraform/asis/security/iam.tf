# terraform/asis/security — 최소 IAM 역할·정책
#
# 이 모듈이 만드는 역할은 세 개다. 전부 도면에 이미 있는 서비스가 동작하기 위해
# 반드시 있어야 하는 것들이고, 그 밖의 역할은 만들지 않는다.
#   1. ECS task execution role   — Fargate 태스크 4종의 이미지 pull · 로그 전송
#   2. ECS task role             — 애플리케이션 런타임 자격 + 경로 B 의 셸 접근
#   3. VPC Flow Logs 전달 role   — Flow Logs → CloudWatch Logs 전달
#
# aws_flow_log · aws_cloudwatch_log_group · aws_cloudtrail 리소스 자체는
# observability 모듈 소유다. 여기서는 그쪽이 필요로 하는 역할만 만든다.
#
# AS-IS 관찰 메모(판정 아님): J사 인프라는 콘솔 수동 구성이고 IaC 가 없다
# (context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5 · GAP-IAC-01).
# 아래 정책의 와일드카드 범위와 조건 키 부재는 콘솔 마법사 기본값을 그대로 옮긴 결과다.
# 충족/미충족 판정은 사람이 docs/current/CONTROL_ASSESSMENT.yaml 에서 한다.

# ──────────────────────────────────────────────────────────────────────────────
# 1. ECS task execution role
# ──────────────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    sid     = "EcsTasksAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.name_prefix}-ecs-task-execution"
  description        = "ECS Fargate 태스크 실행 역할 — ECR pull · awslogs 전송"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-ecs-task-execution"
    jk_source = "context/raw/인프라컨텍스트-외부협업용.md#2.2"
  })
}

# AWS 관리형 정책 ARN 은 계정과 무관한 고정 문자열이다. data source 를 쓰지 않는다.
resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# GAP-SEC-01 [ABSENCE] Secrets Manager 미사용 — API 키는 GitHub Actions Secrets 에 있다
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#5.2
#       context/raw/인프라컨텍스트-외부협업용.md#2.2  (Secrets Manager 미사용)
#
# 여기가 그 부재가 드러나는 자리다. Secrets Manager 를 쓴다면 이 실행 역할에
# secretsmanager:GetSecretValue 가 붙고 태스크 정의에 secrets 블록이 생긴다. 둘 다 없다.
# LLM API 키와 AWS 배포 자격증명은 GitHub Actions Secrets 에서 환경변수로 주입된다.
#   aws_secretsmanager_secret         — 의도적 미선언
#   aws_secretsmanager_secret_version — 의도적 미선언
#   secretsmanager:* 를 허용하는 정책문 — 의도적 미선언
# 이 리소스들을 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.

# ──────────────────────────────────────────────────────────────────────────────
# 2. ECS task role (애플리케이션 런타임)
# ──────────────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "ecs_task" {
  # 경로 B — SSM Session Manager 로 컨테이너 셸에 붙는 채널.
  # 이 네 액션은 AWS 가 리소스 수준 제한을 지원하지 않아 "*" 로만 쓸 수 있다.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4
  statement {
    sid    = "SessionManagerDataChannel"
    effect = "Allow"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }

  # 이력서 첨부 원본 버킷. 객체 접근은 이 버킷 하나로 한정한다.
  # GAP-KMS-01 [ABSENCE] 고객관리형 키(CMK) 미사용 · 회전 정책 없음
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2
  #       context/raw/인프라컨텍스트-외부협업용.md#2.2  (CMK 미사용, 회전 정책 없음)
  #
  # 이 정책문에 kms:Decrypt · kms:GenerateDataKey 가 없는 이유가 곧 그 부재다.
  # S3·RDS·EBS 저장 암호화는 전부 AWS 관리형 키로 되어 있어 호출자 측 KMS 권한이
  # 필요하지 않다. CMK 로 바꾸는 순간 이 정책문에 kms 액션이 생긴다.
  #   aws_kms_key       — 의도적 미선언
  #   aws_kms_alias     — 의도적 미선언
  #   aws_kms_key_policy — 의도적 미선언
  # 이 리소스들을 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.
  statement {
    sid    = "ResumeObjectAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["arn:aws:s3:::${var.resume_bucket_name}/*"]
  }

  statement {
    sid       = "ResumeBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.resume_bucket_name}"]
  }
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.name_prefix}-ecs-task"
  description        = "ECS Fargate 태스크 런타임 역할 — 첨부 원본 접근 · 경로 B 셸 채널"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-ecs-task"
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.4"
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name   = "${var.name_prefix}-ecs-task"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task.json
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. VPC Flow Logs 전달 role
# ──────────────────────────────────────────────────────────────────────────────
# AS-IS 관찰값: Flow Logs 활성 · CloudWatch Logs · 보존 30일.
#   context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2  (VPC Flow Logs · Q04)
# aws_flow_log 와 대상 로그그룹은 observability 모듈이 만든다. 여기는 역할만 만든다.
data "aws_iam_policy_document" "vpc_flow_logs_assume" {
  statement {
    sid     = "VpcFlowLogsAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

# 관찰 메모(판정 아님): 콘솔의 Flow Logs 생성 마법사가 만드는 기본 정책 그대로다.
# 대상 로그그룹으로 좁히는 조건도, aws:SourceAccount / aws:SourceArn 조건 키도 없다.
# 좁히면 AS-IS 가 바뀐다. 스캐너가 잡는 대로 두고 사람이 판정한다
# (context/findings/unexpected_asis.json 로 흘러간다).
data "aws_iam_policy_document" "vpc_flow_logs" {
  statement {
    sid    = "FlowLogsToCloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "vpc_flow_logs" {
  name               = "${var.name_prefix}-vpc-flow-logs"
  description        = "VPC Flow Logs → CloudWatch Logs 전달 역할"
  assume_role_policy = data.aws_iam_policy_document.vpc_flow_logs_assume.json

  tags = merge(var.common_tags, {
    Name      = "${var.name_prefix}-vpc-flow-logs"
    jk_source = "context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2"
  })
}

resource "aws_iam_role_policy" "vpc_flow_logs" {
  name   = "${var.name_prefix}-vpc-flow-logs"
  role   = aws_iam_role.vpc_flow_logs.id
  policy = data.aws_iam_policy_document.vpc_flow_logs.json
}

# GAP-CFG-01 [ABSENCE] AWS Config 미활성
# 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.2  (위협 탐지 · Q12 — GuardDuty 활성, Config 미활성)
#       context/raw/인프라컨텍스트-외부협업용.md#2.2      (AWS Config 미활성)
#
# Config 를 켠다면 이 파일에 네 번째 역할이 생긴다 — 레코더가 assume 하는 서비스 역할
# (AWS_ConfigRole) 과 전달 채널이 쓰는 S3 버킷 정책이다. 그 역할이 없는 것이 곧 이 부재다.
#   aws_config_configuration_recorder        — 의도적 미선언
#   aws_config_delivery_channel              — 의도적 미선언
#   aws_config_configuration_recorder_status — 의도적 미선언
#   aws_config_config_rule                   — 의도적 미선언
#   Config 서비스 역할 (config.amazonaws.com 신뢰) — 의도적 미선언
# 이 리소스들을 선언하지 않는 것이 AS-IS 다. 추가하지 말 것.
#
# 대비 지점: GuardDuty 는 켜져 있다 (observability 모듈). 탐지는 있고 구성 이력은 없다.
