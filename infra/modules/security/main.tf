################################################################################
# Módulo: security
# Responsabilidade: GuardDuty, Security Hub, Inspector v2, Budgets,
#                   integração EventBridge  Lambda para findings de ameaça
# Projeto: Wayfinder Cloud  VitaCore Health
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# Amazon GuardDuty  Detecção de Ameaças com ML
################################################################################

resource "aws_guardduty_detector" "wayfinder" {
  enable = true

  # Publicar findings a cada 6 horas (equilibrio entre volume e latência)
  finding_publishing_frequency = "SIX_HOURS"

  datasources {
    s3_logs {
      enable = true  # Monitora acesso anômalo a S3  crítico pós-incidente de março
    }
    kubernetes {
      audit_logs { enable = false }  # EKS não usado na VitaCore
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes { enable = true }
      }
    }
  }

  tags = {
    Name           = "${local.name_prefix}-guardduty"
    Environment    = var.environment
    Project        = "wayfinder-cloud"
    ManagedBy      = "terraform"
    DataClassification = "operational"
  }
}

################################################################################
# AWS Security Hub  Postura de Segurança Consolidada
################################################################################

resource "aws_securityhub_account" "wayfinder" {
  enable_default_standards = false  # Habilitamos standards individualmente abaixo

  auto_enable_controls = true  # Habilita novos controles automaticamente

  tags = {
    Name        = "${local.name_prefix}-securityhub"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

# AWS Foundational Security Best Practices v1.0.0
resource "aws_securityhub_standards_subscription" "fsbp" {
  standards_arn = "arn:aws:securityhub:${var.region}::standards/aws-foundational-security-best-practices/v/1.0.0"

  depends_on = [aws_securityhub_account.wayfinder]
}

# CIS AWS Foundations Benchmark v1.4.0
resource "aws_securityhub_standards_subscription" "cis_v14" {
  standards_arn = "arn:aws:securityhub:${var.region}::standards/cis-aws-foundations-benchmark/v/1.4.0"

  depends_on = [aws_securityhub_account.wayfinder]
}

################################################################################
# AWS Inspector v2  Vulnerabilidades em EC2 e ECR
################################################################################

resource "aws_inspector2_enabler" "wayfinder" {
  account_ids    = [var.account_id]
  resource_types = ["EC2", "ECR"]  # Scan de vulnerabilidades em instâncias e imagens

  depends_on = [aws_securityhub_account.wayfinder]  # Inspector integra com Security Hub
}

################################################################################
# AWS Budgets  Controle de Custo com Alertas Automatizados
################################################################################

# Budget #1: Custo total mensal  WARNING em 80%, CRITICAL em 100%
resource "aws_budgets_budget" "monthly_total" {
  name         = "${local.name_prefix}-monthly-total-budget"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_sns_topic_arns  = [var.warning_topic_arn]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_sns_topic_arns  = [var.critical_topic_arn]
  }

  # Alerta proativo: projeção de 120% indica que o budget será estourado
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 120
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_sns_topic_arns  = [var.warning_topic_arn]
  }

  tags = {
    Name        = "${local.name_prefix}-monthly-total-budget"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

# Budget #2: EC2 + RDS + ElastiCache  detecção de over-provisioning
resource "aws_budgets_budget" "compute_database" {
  name         = "${local.name_prefix}-compute-database-budget"
  budget_type  = "COST"
  limit_amount = tostring(tonumber(var.monthly_budget_limit) * 0.6)  # 60% do total
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Elastic Compute Cloud - Compute", "Amazon Relational Database Service", "Amazon ElastiCache"]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 70
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [var.warning_topic_arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [var.critical_topic_arn]
  }

  tags = {
    Name        = "${local.name_prefix}-compute-database-budget"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

################################################################################
# EventBridge Rule  GuardDuty Findings  Lambda compliance-evaluator
################################################################################

resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  name        = "${local.name_prefix}-guardduty-findings"
  description = "Roteia GuardDuty findings MEDIUM/HIGH/CRITICAL para Lambda de avaliação"

  # Filtra apenas MEDIUM (>= 4.0) e acima para evitar ruído de findings LOW
  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      severity = [{ numeric = [">=", 4.0] }]
    }
  })

  tags = {
    Name        = "${local.name_prefix}-guardduty-findings-rule"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_target" "guardduty_to_lambda" {
  rule      = aws_cloudwatch_event_rule.guardduty_findings.name
  target_id = "GuardDutyFindingsToLambda"
  arn       = var.lambda_evaluator_arn
}

################################################################################
# Lambda Permission  EventBridge pode invocar o compliance-evaluator
################################################################################

resource "aws_lambda_permission" "eventbridge_guardduty" {
  statement_id  = "AllowEventBridgeInvokeForGuardDutyFindings"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_evaluator_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.guardduty_findings.arn
}

################################################################################
# EventBridge Rule  Security Hub Findings CRITICAL  Lambda
################################################################################

resource "aws_cloudwatch_event_rule" "securityhub_critical" {
  name        = "${local.name_prefix}-securityhub-critical"
  description = "Roteia Security Hub findings CRITICAL para Lambda de avaliação"

  event_pattern = jsonencode({
    source      = ["aws.securityhub"]
    detail-type = ["Security Hub Findings - Imported"]
    detail = {
      findings = {
        Severity = {
          Label = ["CRITICAL", "HIGH"]
        }
        Workflow = {
          Status = ["NEW"]  # Apenas novos findings, não os já em tratamento
        }
      }
    }
  })

  tags = {
    Name        = "${local.name_prefix}-securityhub-critical-rule"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_target" "securityhub_to_lambda" {
  rule      = aws_cloudwatch_event_rule.securityhub_critical.name
  target_id = "SecurityHubCriticalToLambda"
  arn       = var.lambda_evaluator_arn
}

resource "aws_lambda_permission" "eventbridge_securityhub" {
  statement_id  = "AllowEventBridgeInvokeForSecurityHubCritical"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_evaluator_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.securityhub_critical.arn
}
