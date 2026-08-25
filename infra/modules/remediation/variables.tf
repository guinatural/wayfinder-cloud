################################################################################
# Módulo: remediation  Variáveis
################################################################################

variable "environment" {
  description = "Nome do ambiente (dev, staging, prod)"
  type        = string
}

variable "account_id" {
  description = "ID da conta AWS"
  type        = string
}

variable "region" {
  description = "Região AWS de deploy"
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN da IAM Role para as Lambdas de remediação"
  type        = string
}

variable "lambda_subnet_ids" {
  description = "IDs das subnets privadas para a Lambda auto-remediation"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "ID do Security Group para as Lambdas"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN da KMS CMK para DynamoDB, SQS e logs"
  type        = string
}

variable "critical_topic_arn" {
  description = "ARN do SNS Topic CRITICAL para notificações de falha na remediação"
  type        = string
}

variable "warning_topic_arn" {
  description = "ARN do SNS Topic WARNING para notificações de remediação"
  type        = string
}

variable "wayfinder_event_bus_arn" {
  description = "ARN do EventBridge Custom Bus 'wayfinder-events'"
  type        = string
}
