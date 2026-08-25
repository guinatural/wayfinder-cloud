################################################################################
# Módulo: iam
# Responsabilidade: IAM Roles com least privilege para AWS Config e Lambdas
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# AWS Config Role
################################################################################

data "aws_iam_policy_document" "config_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["config.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "config" {
  name               = "${local.name_prefix}-config-role"
  assume_role_policy = data.aws_iam_policy_document.config_assume_role.json

  tags = {
    Name    = "${local.name_prefix}-config-role"
    Purpose = "aws-config-recorder"
  }
}

resource "aws_iam_role_policy_attachment" "config_managed" {
  role       = aws_iam_role.config.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

# Permissão adicional para gravar no bucket de auditoria
data "aws_iam_policy_document" "config_s3" {
  statement {
    sid    = "AllowConfigS3Write"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetBucketAcl",
    ]
    resources = [
      var.audit_bucket_arn,
      "${var.audit_bucket_arn}/*",
    ]
  }
  statement {
    sid    = "AllowConfigKMS"
    effect = "Allow"
    actions = [
      "kms:GenerateDataKey",
      "kms:Decrypt",
    ]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "config_s3" {
  name   = "${local.name_prefix}-config-s3-policy"
  role   = aws_iam_role.config.id
  policy = data.aws_iam_policy_document.config_s3.json
}

################################################################################
# Lambda Role  compliance-evaluator
################################################################################

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_evaluator" {
  name               = "${local.name_prefix}-lambda-evaluator-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name    = "${local.name_prefix}-lambda-evaluator-role"
    Purpose = "compliance-evaluator-lambda"
  }
}

data "aws_iam_policy_document" "lambda_evaluator" {
  # SNS  publicar notificações por severidade
  statement {
    sid    = "AllowSNSPublish"
    effect = "Allow"
    actions = ["sns:Publish"]
    resources = [
      "arn:aws:sns:${var.region}:${var.account_id}:${local.name_prefix}-critical",
      "arn:aws:sns:${var.region}:${var.account_id}:${local.name_prefix}-warning",
      "arn:aws:sns:${var.region}:${var.account_id}:${local.name_prefix}-info",
    ]
  }
  # CloudWatch  métricas de compliance
  statement {
    sid    = "AllowCWMetrics"
    effect = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["wayfinder/Compliance"]
    }
  }
  # EventBridge  publicar eventos de remediação
  statement {
    sid    = "AllowEventBridgePut"
    effect = "Allow"
    actions = ["events:PutEvents"]
    resources = [
      "arn:aws:events:${var.region}:${var.account_id}:event-bus/wayfinder-events",
    ]
  }
  # Config  descrever regras para contexto
  statement {
    sid    = "AllowConfigDescribe"
    effect = "Allow"
    actions = ["config:DescribeConfigRules"]
    resources = ["*"]
  }
  # Resource Groups Tagging  obter tags dos recursos avaliados
  statement {
    sid    = "AllowTaggingAPI"
    effect = "Allow"
    actions = ["tag:GetResources"]
    resources = ["*"]
  }
  # X-Ray  tracing distribuído
  statement {
    sid    = "AllowXRay"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
  # CloudWatch Logs  escrita de logs estruturados
  statement {
    sid    = "AllowCWLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/compliance-evaluator",
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/compliance-evaluator:*",
    ]
  }
  # KMS  descriptografar dados dos recursos analisados
  statement {
    sid    = "AllowKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }
  # VPC  necessário para Lambdas em VPC
  statement {
    sid    = "AllowVPCAccess"
    effect = "Allow"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_evaluator" {
  name   = "${local.name_prefix}-lambda-evaluator-policy"
  role   = aws_iam_role.lambda_evaluator.id
  policy = data.aws_iam_policy_document.lambda_evaluator.json
}

################################################################################
# Lambda Role  auto-remediation
################################################################################

resource "aws_iam_role" "lambda_remediation" {
  name               = "${local.name_prefix}-lambda-remediation-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name    = "${local.name_prefix}-lambda-remediation-role"
    Purpose = "auto-remediation-lambda"
  }
}

data "aws_iam_policy_document" "lambda_remediation" {
  # S3  bloquear acesso público e habilitar criptografia
  statement {
    sid    = "AllowS3Remediation"
    effect = "Allow"
    actions = [
      "s3:PutBucketPublicAccessBlock",
      "s3:PutEncryptionConfiguration",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetEncryptionConfiguration",
    ]
    resources = ["arn:aws:s3:::*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [var.account_id]
    }
  }
  # CloudTrail  reabilitar logging
  statement {
    sid    = "AllowCloudTrailStart"
    effect = "Allow"
    actions = ["cloudtrail:StartLogging", "cloudtrail:GetTrailStatus"]
    resources = [
      "arn:aws:cloudtrail:${var.region}:${var.account_id}:trail/*",
    ]
  }
  # EC2  modificar atributos de segurança de instâncias
  statement {
    sid    = "AllowEC2Remediation"
    effect = "Allow"
    actions = [
      "ec2:ModifyInstanceAttribute",
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceAttribute",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "ec2:Region"
      values   = [var.region]
    }
  }
  # CloudWatch  métricas de remediação
  statement {
    sid    = "AllowCWMetrics"
    effect = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["wayfinder/Remediation"]
    }
  }
  # DynamoDB  registrar tentativas de remediação (guardrail)
  statement {
    sid    = "AllowDynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      "arn:aws:dynamodb:${var.region}:${var.account_id}:table/${local.name_prefix}-remediation-attempts",
    ]
  }
  # EventBridge  publicar resultados de remediação
  statement {
    sid    = "AllowEventBridgePut"
    effect = "Allow"
    actions = ["events:PutEvents"]
    resources = [
      "arn:aws:events:${var.region}:${var.account_id}:event-bus/wayfinder-events",
    ]
  }
  # CloudWatch Logs
  statement {
    sid    = "AllowCWLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/auto-remediation",
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/auto-remediation:*",
    ]
  }
  # KMS
  statement {
    sid    = "AllowKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }
  # X-Ray
  statement {
    sid    = "AllowXRay"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
  # VPC
  statement {
    sid    = "AllowVPCAccess"
    effect = "Allow"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_remediation" {
  name   = "${local.name_prefix}-lambda-remediation-policy"
  role   = aws_iam_role.lambda_remediation.id
  policy = data.aws_iam_policy_document.lambda_remediation.json
}

################################################################################
# Lambda Role  audit-reporter
################################################################################

resource "aws_iam_role" "lambda_reporter" {
  name               = "${local.name_prefix}-lambda-reporter-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name    = "${local.name_prefix}-lambda-reporter-role"
    Purpose = "audit-reporter-lambda"
  }
}

data "aws_iam_policy_document" "lambda_reporter" {
  # Athena  executar queries de auditoria
  statement {
    sid    = "AllowAthena"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
    ]
    resources = [
      "arn:aws:athena:${var.region}:${var.account_id}:workgroup/wayfinder-audit",
    ]
  }
  # S3  ler logs de auditoria e gravar relatórios
  statement {
    sid    = "AllowS3AuditRead"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      var.audit_bucket_arn,
      "${var.audit_bucket_arn}/*",
    ]
  }
  statement {
    sid    = "AllowS3ReportWrite"
    effect = "Allow"
    actions = ["s3:PutObject"]
    resources = ["${var.audit_bucket_arn}/compliance-reports/*"]
  }
  # Glue  catalogar dados para Athena
  statement {
    sid    = "AllowGlue"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetPartitions",
    ]
    resources = [
      "arn:aws:glue:${var.region}:${var.account_id}:catalog",
      "arn:aws:glue:${var.region}:${var.account_id}:database/wayfinder_audit",
      "arn:aws:glue:${var.region}:${var.account_id}:table/wayfinder_audit/*",
    ]
  }
  # SNS  publicar resumo do relatório
  statement {
    sid    = "AllowSNSPublish"
    effect = "Allow"
    actions = ["sns:Publish"]
    resources = [
      "arn:aws:sns:${var.region}:${var.account_id}:${local.name_prefix}-info",
    ]
  }
  # CloudWatch Logs
  statement {
    sid    = "AllowCWLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/audit-reporter",
      "arn:aws:logs:${var.region}:${var.account_id}:log-group:/wayfinder/lambda/audit-reporter:*",
    ]
  }
  # KMS
  statement {
    sid    = "AllowKMS"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [var.kms_key_arn]
  }
  # VPC
  statement {
    sid    = "AllowVPCAccess"
    effect = "Allow"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_reporter" {
  name   = "${local.name_prefix}-lambda-reporter-policy"
  role   = aws_iam_role.lambda_reporter.id
  policy = data.aws_iam_policy_document.lambda_reporter.json
}
