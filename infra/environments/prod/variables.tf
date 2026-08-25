################################################################################
# Wayfinder Cloud  Variables: prod environment
################################################################################

variable "aws_region" {
  description = "Região AWS para deploy"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile para autenticação no ambiente de produção"
  type        = string
  default     = "wayfinder-prod"
}

variable "environment" {
  description = "Nome do ambiente"
  type        = string
  default     = "prod"

  validation {
    condition     = var.environment == "prod"
    error_message = "Este arquivo é exclusivo para o ambiente prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block da VPC de produção"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Lista de AZs para subnets (produção usa pelo menos 2)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "alert_email" {
  description = "Email para receber alertas de segurança em produção"
  type        = string
  # Definir via terraform.tfvars (não commitar) ou TF_VAR_alert_email
}

variable "slack_workspace_id" {
  description = "ID do workspace Slack para alertas em produção"
  type        = string
  default     = ""
}

variable "slack_channel_id" {
  description = "ID do canal Slack para alertas CRITICAL e WARNING em produção"
  type        = string
  default     = ""
}

variable "audit_retention_days" {
  description = "Dias de retenção de logs no S3 Standard antes de transição para Glacier"
  type        = number
  default     = 365 # Produção: 1 ano (vs 90 dias no dev)

  validation {
    condition     = var.audit_retention_days >= 365
    error_message = "Produção requer retenção mínima de 365 dias para conformidade regulatória."
  }
}

variable "monthly_budget_limit" {
  description = "Limite mensal de custo AWS em USD para alertas de orçamento em prod."
  type        = string
  default     = "1050"

  validation {
    condition     = can(tonumber(var.monthly_budget_limit)) && tonumber(var.monthly_budget_limit) > 0
    error_message = "monthly_budget_limit deve ser um número positivo em string. Ex: '1050'."
  }
}
