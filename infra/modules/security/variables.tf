################################################################################
# Módulo: security  Variables
# Projeto: Wayfinder Cloud  VitaCore Health
################################################################################

variable "environment" {
  description = "Nome do ambiente (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment deve ser dev, staging ou prod."
  }
}

variable "account_id" {
  description = "ID da conta AWS onde os recursos serão criados"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id deve ser um número de 12 dígitos."
  }
}

variable "region" {
  description = "Região AWS onde os recursos serão criados"
  type        = string
  default     = "us-east-1"
}

variable "kms_key_arn" {
  description = "ARN do KMS CMK para criptografia de recursos de segurança (GuardDuty findings export, etc.)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:kms:", var.kms_key_arn))
    error_message = "kms_key_arn deve ser um ARN válido de KMS key."
  }
}

variable "critical_topic_arn" {
  description = "ARN do SNS Topic para alertas CRITICAL (DPO + CTO + SecOps + PagerDuty)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:sns:", var.critical_topic_arn))
    error_message = "critical_topic_arn deve ser um ARN válido de SNS topic."
  }
}

variable "warning_topic_arn" {
  description = "ARN do SNS Topic para alertas WARNING (SecOps + Dev Lead)"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:sns:", var.warning_topic_arn))
    error_message = "warning_topic_arn deve ser um ARN válido de SNS topic."
  }
}

variable "monthly_budget_limit" {
  description = "Limite mensal de custo AWS em USD para alertas de orçamento. Ex: '1050' para prod, '150' para dev"
  type        = string
  default     = "500"

  validation {
    condition     = can(tonumber(var.monthly_budget_limit)) && tonumber(var.monthly_budget_limit) > 0
    error_message = "monthly_budget_limit deve ser um número positivo em string. Ex: '500'."
  }
}

variable "lambda_evaluator_arn" {
  description = "ARN da Lambda compliance-evaluator que processa findings de GuardDuty e Security Hub"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:lambda:", var.lambda_evaluator_arn))
    error_message = "lambda_evaluator_arn deve ser um ARN válido de função Lambda."
  }
}
