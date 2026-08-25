################################################################################
# Módulo: observability
# Responsabilidade: CloudTrail, EventBridge, Lambdas, CloudWatch, Athena
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# CloudWatch Log Groups  com KMS e retenção de 90 dias
################################################################################

resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = toset([
    "compliance-evaluator",
    "auto-remediation",
    "incident-notifier",
    "audit-reporter",
  ])

  name              = "/wayfinder/lambda/${each.value}"
  retention_in_days = 90
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "/wayfinder/lambda/${each.value}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/wayfinder/cloudtrail"
  retention_in_days = 365
  kms_key_id        = var.kms_key_arn

  tags = {
    Name        = "/wayfinder/cloudtrail"
    Environment = var.environment
  }
}

################################################################################
# IAM Role para CloudTrail  CloudWatch Logs
################################################################################

resource "aws_iam_role" "cloudtrail_cw" {
  name = "${local.name_prefix}-cloudtrail-cw-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "cloudtrail_cw" {
  name = "${local.name_prefix}-cloudtrail-cw-policy"
  role = aws_iam_role.cloudtrail_cw.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
    }]
  })
}

################################################################################
# CloudTrail  Multi-region, validação de integridade, data events S3
################################################################################

resource "aws_cloudtrail" "wayfinder" {
  name                          = "${local.name_prefix}-trail"
  s3_bucket_name                = var.audit_bucket_id
  s3_key_prefix                 = "cloudtrail"
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  kms_key_id                    = var.kms_key_arn
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_cw.arn

  # Data events: registrar acessos a S3 (GetObject, PutObject)  LGPD Art.37
  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["arn:aws:s3:::"]
    }
  }

  depends_on = [aws_cloudwatch_log_group.cloudtrail]

  tags = {
    Name        = "${local.name_prefix}-trail"
    Environment = var.environment
  }
}

################################################################################
# EventBridge  Custom Event Bus
################################################################################

resource "aws_cloudwatch_event_bus" "wayfinder" {
  name = "wayfinder-events"

  tags = {
    Name        = "wayfinder-events"
    Environment = var.environment
  }
}

################################################################################
# EventBridge Rules  Config NON_COMPLIANT
################################################################################

resource "aws_cloudwatch_event_rule" "config_noncompliant" {
  name           = "${local.name_prefix}-config-noncompliant"
  description    = "Captura eventos de NON_COMPLIANT do AWS Config"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["aws.config"]
    "detail-type" = ["Config Rules Compliance Change"]
    detail = {
      newEvaluationResult = {
        complianceType = ["NON_COMPLIANT"]
      }
    }
  })

  tags = {
    Name = "${local.name_prefix}-config-noncompliant"
  }
}

resource "aws_cloudwatch_event_target" "config_to_evaluator" {
  rule      = aws_cloudwatch_event_rule.config_noncompliant.name
  target_id = "ComplianceEvaluator"
  arn       = aws_lambda_function.compliance_evaluator.arn
}

# Permissão para EventBridge invocar a Lambda
resource "aws_lambda_permission" "eventbridge_evaluator" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compliance_evaluator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.config_noncompliant.arn
}

################################################################################
# EventBridge Rules  CloudTrail: Root Login e IAM Changes
################################################################################

resource "aws_cloudwatch_event_rule" "root_login" {
  name           = "${local.name_prefix}-root-login"
  description    = "Detecta login da conta root  violação LGPD Art.46"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["aws.signin"]
    "detail-type" = ["AWS Console Sign In via CloudTrail"]
    detail = {
      userIdentity = { type = ["Root"] }
    }
  })
}

resource "aws_cloudwatch_event_target" "root_login_to_evaluator" {
  rule      = aws_cloudwatch_event_rule.root_login.name
  target_id = "RootLoginEvaluator"
  arn       = aws_lambda_function.compliance_evaluator.arn
}

resource "aws_lambda_permission" "root_login_evaluator" {
  statement_id  = "AllowRootLoginEvent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compliance_evaluator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.root_login.arn
}

resource "aws_cloudwatch_event_rule" "iam_changes" {
  name           = "${local.name_prefix}-iam-changes"
  description    = "Detecta mudanças críticas em IAM (criar/deletar role, policy, user)"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["aws.iam"]
    "detail-type" = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource = ["iam.amazonaws.com"]
      eventName = [
        "CreateUser", "DeleteUser",
        "AttachRolePolicy", "DetachRolePolicy",
        "CreateAccessKey", "DeleteAccessKey",
        "PutUserPolicy", "DeleteUserPolicy",
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "iam_changes_to_evaluator" {
  rule      = aws_cloudwatch_event_rule.iam_changes.name
  target_id = "IAMChangesEvaluator"
  arn       = aws_lambda_function.compliance_evaluator.arn
}

resource "aws_lambda_permission" "iam_changes_evaluator" {
  statement_id  = "AllowIAMChangesEvent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.compliance_evaluator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.iam_changes.arn
}

################################################################################
# Lambda  compliance-evaluator
################################################################################

data "archive_file" "compliance_evaluator" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/lambdas/compliance-evaluator"
  output_path = "${path.module}/../../../src/lambdas/compliance-evaluator/handler.zip"
  excludes    = ["handler.zip", "__pycache__", "*.pyc"]
}

resource "aws_lambda_function" "compliance_evaluator" {
  function_name    = "${local.name_prefix}-compliance-evaluator"
  description      = "Avalia eventos de NON_COMPLIANT, enriquece com contexto LGPD e publica no SNS"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 60
  memory_size      = 256
  filename         = data.archive_file.compliance_evaluator.output_path
  source_code_hash = data.archive_file.compliance_evaluator.output_base64sha256

  tracing_config {
    mode = "Active" # X-Ray
  }

  vpc_config {
    subnet_ids         = var.lambda_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      CRITICAL_TOPIC_ARN       = var.critical_topic_arn
      WARNING_TOPIC_ARN        = var.warning_topic_arn
      INFO_TOPIC_ARN           = var.info_topic_arn
      WAYFINDER_EVENT_BUS_NAME  = aws_cloudwatch_event_bus.wayfinder.name
      ENVIRONMENT              = var.environment
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_logs]

  tags = {
    Name        = "${local.name_prefix}-compliance-evaluator"
    Environment = var.environment
  }
}

################################################################################
# Lambda  audit-reporter (agendada semanalmente)
################################################################################

data "archive_file" "audit_reporter" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/lambdas/audit-reporter"
  output_path = "${path.module}/../../../src/lambdas/audit-reporter/handler.zip"
  excludes    = ["handler.zip", "__pycache__", "*.pyc"]
}

resource "aws_lambda_function" "audit_reporter" {
  function_name    = "${local.name_prefix}-audit-reporter"
  description      = "Gera relatórios semanais de compliance a partir de queries Athena"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 300
  memory_size      = 512
  filename         = data.archive_file.audit_reporter.output_path
  source_code_hash = data.archive_file.audit_reporter.output_base64sha256

  tracing_config {
    mode = "Active"
  }

  vpc_config {
    subnet_ids         = var.lambda_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      AUDIT_BUCKET_NAME  = var.audit_bucket_id
      ATHENA_WORKGROUP   = aws_athena_workgroup.wayfinder.name
      ATHENA_DATABASE    = aws_glue_catalog_database.wayfinder_audit.name
      INFO_TOPIC_ARN     = var.info_topic_arn
      ENVIRONMENT        = var.environment
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_logs]

  tags = {
    Name        = "${local.name_prefix}-audit-reporter"
    Environment = var.environment
  }
}

# EventBridge Schedule  toda segunda-feira às 08:00 UTC
resource "aws_cloudwatch_event_rule" "audit_reporter_schedule" {
  name                = "${local.name_prefix}-audit-reporter-schedule"
  description         = "Agenda execução semanal do audit-reporter"
  schedule_expression = "cron(0 8 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "audit_reporter_schedule" {
  rule      = aws_cloudwatch_event_rule.audit_reporter_schedule.name
  target_id = "AuditReporter"
  arn       = aws_lambda_function.audit_reporter.arn
}

resource "aws_lambda_permission" "audit_reporter_schedule" {
  statement_id  = "AllowScheduledInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.audit_reporter.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.audit_reporter_schedule.arn
}

################################################################################
# CloudWatch Metric Alarms
################################################################################

resource "aws_cloudwatch_metric_alarm" "noncompliant_critical" {
  alarm_name          = "${local.name_prefix}-noncompliant-critical"
  alarm_description   = "Ao menos 1 recurso CRITICAL NON_COMPLIANT detectado"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "NonCompliantResource"
  namespace           = "wayfinder/Compliance"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    Severity    = "CRITICAL"
    Environment = var.environment
  }

  alarm_actions = [var.warning_topic_arn]
  ok_actions    = [var.info_topic_arn]

  tags = {
    Name = "${local.name_prefix}-noncompliant-critical"
  }
}

resource "aws_cloudwatch_metric_alarm" "noncompliant_high_volume" {
  alarm_name          = "${local.name_prefix}-noncompliant-high-volume"
  alarm_description   = "Mais de 10 recursos NON_COMPLIANT em 1 hora  possível incidente"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "NonCompliantResource"
  namespace           = "wayfinder/Compliance"
  period              = 3600
  statistic           = "Sum"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    Environment = var.environment
  }

  alarm_actions = [var.critical_topic_arn]

  tags = {
    Name = "${local.name_prefix}-noncompliant-high-volume"
  }
}

resource "aws_cloudwatch_metric_alarm" "evaluator_errors" {
  alarm_name          = "${local.name_prefix}-evaluator-errors"
  alarm_description   = "compliance-evaluator com mais de 5 erros em 5 minutos"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.compliance_evaluator.function_name
  }

  alarm_actions = [var.warning_topic_arn]

  tags = {
    Name = "${local.name_prefix}-evaluator-errors"
  }
}

################################################################################
# CloudWatch Dashboard  Wayfinder Command Center
################################################################################

resource "aws_cloudwatch_dashboard" "wayfinder" {
  dashboard_name = "wayfinder-command-center-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type       = "metric"
        x          = 0
        y          = 0
        width      = 12
        height     = 6
        properties = {
          title   = "Compliance Score (menor = mais crítico)"
          metrics = [
            ["wayfinder/Compliance", "ComplianceScore", "Environment", var.environment]
          ]
          period = 300
          stat   = "Average"
          view   = "timeSeries"
          region = var.region
        }
      },
      {
        type       = "metric"
        x          = 12
        y          = 0
        width      = 12
        height     = 6
        properties = {
          title = "Recursos NON_COMPLIANT por Severidade"
          metrics = [
            ["wayfinder/Compliance", "NonCompliantResource", "Severity", "CRITICAL", "Environment", var.environment],
            ["wayfinder/Compliance", "NonCompliantResource", "Severity", "HIGH",     "Environment", var.environment],
            ["wayfinder/Compliance", "NonCompliantResource", "Severity", "MEDIUM",   "Environment", var.environment],
          ]
          period = 3600
          stat   = "Sum"
          view   = "timeSeries"
          region = var.region
        }
      },
      {
        type       = "metric"
        x          = 0
        y          = 6
        width      = 12
        height     = 6
        properties = {
          title = "Tentativas de Remediação Automática"
          metrics = [
            ["wayfinder/Remediation", "RemediationAttempt", "Status", "success",   "Environment", var.environment],
            ["wayfinder/Remediation", "RemediationAttempt", "Status", "error",     "Environment", var.environment],
            ["wayfinder/Remediation", "RemediationAttempt", "Status", "skipped",   "Environment", var.environment],
          ]
          period = 3600
          stat   = "Sum"
          view   = "bar"
          region = var.region
        }
      },
      {
        type       = "metric"
        x          = 12
        y          = 6
        width      = 12
        height     = 6
        properties = {
          title = "Lambda Errors  compliance-evaluator"
          metrics = [
            ["AWS/Lambda", "Errors",      "FunctionName", aws_lambda_function.compliance_evaluator.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.compliance_evaluator.function_name],
            ["AWS/Lambda", "Duration",    "FunctionName", aws_lambda_function.compliance_evaluator.function_name],
          ]
          period = 300
          stat   = "Sum"
          view   = "timeSeries"
          region = var.region
        }
      },
    ]
  })
}

################################################################################
# Athena Workgroup
################################################################################

resource "aws_athena_workgroup" "wayfinder" {
  name        = "wayfinder-audit"
  description = "Workgroup Athena para queries de auditoria Wayfinder Cloud"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${var.audit_bucket_id}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = var.kms_key_arn
      }
    }
  }

  tags = {
    Name        = "wayfinder-audit"
    Environment = var.environment
  }
}

################################################################################
# Glue Catalog Database e Crawler
################################################################################

resource "aws_glue_catalog_database" "wayfinder_audit" {
  name        = "wayfinder_audit"
  description = "Database Glue para catálogo de logs CloudTrail e eventos de compliance"
}

# IAM Role para o Glue Crawler
resource "aws_iam_role" "glue_crawler" {
  name = "${local.name_prefix}-glue-crawler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_crawler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3" {
  name = "${local.name_prefix}-glue-s3-policy"
  role = aws_iam_role.glue_crawler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [var.audit_bucket_arn, "${var.audit_bucket_arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = [var.kms_key_arn]
      },
    ]
  })
}

resource "aws_glue_crawler" "cloudtrail" {
  name          = "${local.name_prefix}-cloudtrail-crawler"
  role          = aws_iam_role.glue_crawler.arn
  database_name = aws_glue_catalog_database.wayfinder_audit.name
  description   = "Cataloga logs CloudTrail no S3 para queries Athena"

  s3_target {
    path = "s3://${var.audit_bucket_id}/cloudtrail/"
  }

  schedule = "cron(0 6 * * ? *)" # Diariamente às 06:00 UTC

  tags = {
    Name        = "${local.name_prefix}-cloudtrail-crawler"
    Environment = var.environment
  }
}
