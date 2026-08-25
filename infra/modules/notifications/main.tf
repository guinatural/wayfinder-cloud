################################################################################
# Módulo: notifications
# Responsabilidade: SNS Topics (CRITICAL/WARNING/INFO), subscriptions, Chatbot
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# SNS Topics com criptografia KMS
################################################################################

resource "aws_sns_topic" "critical" {
  name              = "${local.name_prefix}-critical"
  kms_master_key_id = var.kms_key_arn
  tags = { Name = "${local.name_prefix}-critical", Severity = "CRITICAL" }
}

resource "aws_sns_topic" "warning" {
  name              = "${local.name_prefix}-warning"
  kms_master_key_id = var.kms_key_arn
  tags = { Name = "${local.name_prefix}-warning", Severity = "WARNING" }
}

resource "aws_sns_topic" "info" {
  name              = "${local.name_prefix}-info"
  kms_master_key_id = var.kms_key_arn
  tags = { Name = "${local.name_prefix}-info", Severity = "INFO" }
}

################################################################################
# SNS Topic Policies  permitir Lambda e EventBridge publicar
################################################################################

data "aws_iam_policy_document" "critical_policy" {
  statement {
    sid     = "AllowLambdaAndEB"
    effect  = "Allow"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com", "events.amazonaws.com", "cloudwatch.amazonaws.com"]
    }
    resources = [aws_sns_topic.critical.arn]
  }
  statement {
    sid     = "AllowAccountPublish"
    effect  = "Allow"
    actions = ["SNS:Publish", "SNS:Subscribe", "SNS:GetTopicAttributes"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    resources = [aws_sns_topic.critical.arn]
  }
}

data "aws_iam_policy_document" "warning_policy" {
  statement {
    sid     = "AllowLambdaAndEB"
    effect  = "Allow"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com", "events.amazonaws.com", "cloudwatch.amazonaws.com"]
    }
    resources = [aws_sns_topic.warning.arn]
  }
  statement {
    sid     = "AllowAccountPublish"
    effect  = "Allow"
    actions = ["SNS:Publish", "SNS:Subscribe", "SNS:GetTopicAttributes"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    resources = [aws_sns_topic.warning.arn]
  }
}

data "aws_iam_policy_document" "info_policy" {
  statement {
    sid     = "AllowLambdaAndEB"
    effect  = "Allow"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com", "events.amazonaws.com", "config.amazonaws.com"]
    }
    resources = [aws_sns_topic.info.arn]
  }
  statement {
    sid     = "AllowAccountPublish"
    effect  = "Allow"
    actions = ["SNS:Publish", "SNS:Subscribe", "SNS:GetTopicAttributes"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
    resources = [aws_sns_topic.info.arn]
  }
}

resource "aws_sns_topic_policy" "critical" {
  arn    = aws_sns_topic.critical.arn
  policy = data.aws_iam_policy_document.critical_policy.json
}

resource "aws_sns_topic_policy" "warning" {
  arn    = aws_sns_topic.warning.arn
  policy = data.aws_iam_policy_document.warning_policy.json
}

resource "aws_sns_topic_policy" "info" {
  arn    = aws_sns_topic.info.arn
  policy = data.aws_iam_policy_document.info_policy.json
}

data "aws_caller_identity" "current" {}

################################################################################
# Email Subscriptions
################################################################################

resource "aws_sns_topic_subscription" "critical_email" {
  topic_arn = aws_sns_topic.critical.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_sns_topic_subscription" "warning_email" {
  topic_arn = aws_sns_topic.warning.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_sns_topic_subscription" "info_email" {
  topic_arn = aws_sns_topic.info.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

################################################################################
# AWS Chatbot  Slack (condicional)
################################################################################

resource "aws_chatbot_slack_channel_configuration" "wayfinder" {
  count = var.slack_workspace_id != "" && var.slack_channel_id != "" ? 1 : 0

  configuration_name = "${local.name_prefix}-slack"
  iam_role_arn       = aws_iam_role.chatbot[0].arn
  slack_workspace_id = var.slack_workspace_id
  slack_channel_id   = var.slack_channel_id
  sns_topic_arns     = [aws_sns_topic.critical.arn, aws_sns_topic.warning.arn]

  guardrail_policy_arns = [
    "arn:aws:iam::aws:policy/ReadOnlyAccess",
  ]

  tags = { Name = "${local.name_prefix}-chatbot" }
}

resource "aws_iam_role" "chatbot" {
  count = var.slack_workspace_id != "" ? 1 : 0
  name  = "${local.name_prefix}-chatbot-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "chatbot.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "chatbot_sns" {
  count = var.slack_workspace_id != "" ? 1 : 0
  name  = "${local.name_prefix}-chatbot-sns"
  role  = aws_iam_role.chatbot[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["cloudwatch:Describe*", "cloudwatch:Get*", "cloudwatch:List*"]
      Resource = "*"
    }]
  })
}
