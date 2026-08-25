################################################################################
# Módulo: remediation
# Responsabilidade: Lambdas de remediação/notificação, DynamoDB, SQS DLQ
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# SQS Dead Letter Queues  capturar invocações com falha
################################################################################

resource "aws_sqs_queue" "dlq_remediation" {
  name                      = "${local.name_prefix}-auto-remediation-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = 1209600 # 14 dias

  tags = {
    Name        = "${local.name_prefix}-auto-remediation-dlq"
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "dlq_notifier" {
  name                      = "${local.name_prefix}-incident-notifier-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = 1209600

  tags = {
    Name        = "${local.name_prefix}-incident-notifier-dlq"
    Environment = var.environment
  }
}

################################################################################
# DynamoDB  Tabela de tentativas de remediação (guardrail anti-loop)
################################################################################

resource "aws_dynamodb_table" "remediation_attempts" {
  name         = "${local.name_prefix}-remediation-attempts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "resource_id"
  range_key    = "rule_name"

  attribute {
    name = "resource_id"
    type = "S"
  }

  attribute {
    name = "rule_name"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "${local.name_prefix}-remediation-attempts"
    Environment = var.environment
  }
}

################################################################################
# Lambda  auto-remediation
################################################################################

data "archive_file" "auto_remediation" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/lambdas/auto-remediation"
  output_path = "${path.module}/../../../src/lambdas/auto-remediation/handler.zip"
  excludes    = ["handler.zip", "__pycache__", "*.pyc"]
}

resource "aws_lambda_function" "auto_remediation" {
  function_name    = "${local.name_prefix}-auto-remediation"
  description      = "Executa ações de remediação automática com guardrails de segurança"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 120
  memory_size      = 256
  filename         = data.archive_file.auto_remediation.output_path
  source_code_hash = data.archive_file.auto_remediation.output_base64sha256

  tracing_config {
    mode = "Active" # X-Ray
  }

  vpc_config {
    subnet_ids         = var.lambda_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq_remediation.arn
  }

  environment {
    variables = {
      ENVIRONMENT               = var.environment
      REMEDIATION_ATTEMPTS_TABLE = aws_dynamodb_table.remediation_attempts.name
      WARNING_TOPIC_ARN         = var.warning_topic_arn
      CRITICAL_TOPIC_ARN        = var.critical_topic_arn
      WAYFINDER_EVENT_BUS_NAME   = split("/", var.wayfinder_event_bus_arn)[1]
    }
  }

  tags = {
    Name        = "${local.name_prefix}-auto-remediation"
    Environment = var.environment
  }
}

################################################################################
# Lambda  incident-notifier
################################################################################

data "archive_file" "incident_notifier" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/lambdas/incident-notifier"
  output_path = "${path.module}/../../../src/lambdas/incident-notifier/handler.zip"
  excludes    = ["handler.zip", "__pycache__", "*.pyc"]
}

resource "aws_lambda_function" "incident_notifier" {
  function_name    = "${local.name_prefix}-incident-notifier"
  description      = "Formata e envia notificações ricas para Slack e email"
  role             = var.lambda_role_arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  timeout          = 60
  memory_size      = 128
  filename         = data.archive_file.incident_notifier.output_path
  source_code_hash = data.archive_file.incident_notifier.output_base64sha256

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq_notifier.arn
  }

  environment {
    variables = {
      ENVIRONMENT               = var.environment
      SLACK_WEBHOOK_URL         = ""
      CLOUDWATCH_DASHBOARD_URL  = "https://console.aws.amazon.com/cloudwatch/home#dashboards:name=wayfinder-command-center-${var.environment}"
    }
  }

  tags = {
    Name        = "${local.name_prefix}-incident-notifier"
    Environment = var.environment
  }
}

################################################################################
# EventBridge Rule  WayfinderAutoRemediation no bus customizado
################################################################################

resource "aws_cloudwatch_event_rule" "auto_remediation" {
  name           = "${local.name_prefix}-auto-remediation-trigger"
  description    = "Roteia eventos WayfinderAutoRemediation para a Lambda de remediação"
  event_bus_name = var.wayfinder_event_bus_arn

  event_pattern = jsonencode({
    source        = ["wayfinder.compliance-evaluator"]
    "detail-type" = ["WayfinderAutoRemediation"]
  })

  tags = {
    Name = "${local.name_prefix}-auto-remediation-trigger"
  }
}

resource "aws_cloudwatch_event_target" "auto_remediation" {
  rule           = aws_cloudwatch_event_rule.auto_remediation.name
  event_bus_name = var.wayfinder_event_bus_arn
  target_id      = "AutoRemediationLambda"
  arn            = aws_lambda_function.auto_remediation.arn
}

resource "aws_lambda_permission" "eventbridge_remediation" {
  statement_id  = "AllowEventBridgeInvokeRemediation"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auto_remediation.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.auto_remediation.arn
}
