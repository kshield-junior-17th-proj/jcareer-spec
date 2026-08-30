# 이 모듈은 J사 콘솔 구성을 역으로 작성한 AS-IS 재현 명세이며 apply 대상이 아니다.
# 구성 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
# 2-AZ 근거: context/raw/D02-진단대상-아키텍처-정의.md#3.1

resource "aws_ecr_repository" "service" {
  for_each = local.services

  name                 = local.ecr_repository_names[each.key]
  image_tag_mutability = "MUTABLE"
  force_delete         = false

  # GAP-SBOM-01 [DOC] AS-IS에는 SBOM·취약점 스캔 절차가 없다.
  # 근거: context/raw/SCENARIO_FACTS-가상고객사J사.md#9.5
  image_scanning_configuration {
    scan_on_push = false
  }

  # GAP-KMS-01 [ABSENCE] 고객관리형 키를 만들거나 연결하지 않는다.
  # 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-ecr"
  })
}

resource "aws_lb" "public" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = var.alb_security_group_ids
  subnets            = var.public_subnet_ids

  access_logs {
    bucket  = var.alb_access_logs_bucket
    prefix  = var.alb_access_logs_prefix
    enabled = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-alb"
  })
}

resource "aws_lb_target_group" "service" {
  for_each = local.services

  name        = "${var.name_prefix}-${each.key}"
  port        = each.value.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    path                = each.value.health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-tg"
  })
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.public.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = local.effective_certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service["web"].arn
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-https"
  })
}

resource "aws_lb_listener_rule" "service_path" {
  for_each = local.services

  listener_arn = aws_lb_listener.https.arn
  priority     = each.value.priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service[each.key].arn
  }

  condition {
    path_pattern {
      values = each.value.path_patterns
    }
  }

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-path"
  })
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-cluster"
  })
}

resource "aws_ecs_task_definition" "service" {
  for_each = local.services

  family                   = "${var.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = local.effective_task_execution_role_arn
  task_role_arn            = local.effective_task_role_arns[each.key]

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  # GAP-SEC-01 [ABSENCE] Secrets Manager를 사용하지 않고 llm-gateway에 환경변수로 주입한다.
  # 근거: context/raw/인프라컨텍스트-외부협업용.md#2.2
  container_definitions = jsonencode([
    {
      name      = each.key
      image     = local.container_images[each.key]
      essential = true
      portMappings = [
        {
          name          = each.key
          containerPort = each.value.port
          hostPort      = each.value.port
          protocol      = "tcp"
        }
      ]
      environment = concat(
        [
          {
            name  = "AWS_REGION"
            value = var.region
          },
          {
            name  = "AWS_ACCOUNT_ID"
            value = local.mock_account_id
          },
        ],
        each.key == "llm-gateway" ? [
          {
            name  = "LLM_API_KEY"
            value = var.llm_api_key
          },
        ] : []
      )
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = var.cloudwatch_log_group_names[each.key]
          awslogs-region        = var.region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-task"
  })
}

resource "aws_ecs_service" "service" {
  for_each = local.services

  name                               = "${var.name_prefix}-${each.key}"
  cluster                            = aws_ecs_cluster.main.id
  task_definition                    = aws_ecs_task_definition.service[each.key].arn
  desired_count                      = 2
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  scheduling_strategy                = "REPLICA"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60
  enable_execute_command             = true
  propagate_tags                     = "SERVICE"

  network_configuration {
    subnets          = var.application_subnet_ids
    security_groups  = var.service_security_group_ids
    assign_public_ip = false
  }

  # Fargate 서비스는 placement strategy를 받지 않는다. 두 AZ의 subnet을 모두
  # 전달하면 ECS 서비스 스케줄러가 기본 동작으로 task를 AZ에 균형 배치한다.

  load_balancer {
    target_group_arn = aws_lb_target_group.service[each.key].arn
    container_name   = each.key
    container_port   = each.value.port
  }

  depends_on = [aws_lb_listener.https]

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-service"
  })
}

resource "aws_appautoscaling_target" "service" {
  for_each = local.services

  min_capacity       = 2
  max_capacity       = var.service_max_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = merge(local.common_tags, {
    Name = "${var.name_prefix}-${each.key}-scaling-target"
  })
}
