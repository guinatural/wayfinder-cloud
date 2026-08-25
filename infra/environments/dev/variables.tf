################################################################################
# Wayfinder Cloud  Variables: dev environment
################################################################################

variable "aws_region" {
  description = "Região AWS para deploy"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile para autenticação"
  type        = string
  default     = "wayfinder-dev"
}

variable "environment" {
  description = "Nome do ambiente (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment deve ser dev, staging ou prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block da VPC"
  type        = string
  default     = "10.10.0.0/16"
}

variable "availability_zones" {
  description = "Lista de AZs para subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "alert_email" {
  description = "Email para receber alertas de segurança"
  type        = string
  # Defina via terraform.tfvars ou variável de ambiente TF_VAR_alert_email
  # Não colocar valor default para não expor email no código
}

variable "slack_workspace_id" {
  description = "ID do workspace Slack para AWS Chatbot (opcional)"
  type        = string
  default     = ""
}

variable "slack_channel_id" {
  description = "ID do canal Slack para alertas (opcional)"
  type        = string
  default     = ""
}

variable "audit_retention_days" {
  description = "Dias de retenção de logs no S3 Standard antes de mover para Glacier"
  type        = number
  default     = 90

  validation {
    condition     = var.audit_retention_days >= 30
    error_message = "Retenção mínima de 30 dias exigida para conformidade LGPD."
  }
}

variable "monthly_budget_limit" {
  description = "Limite mensal de custo AWS em USD para alertas de orçamento. Em dev, padrão é $150."
  type        = string
  default     = "150"

  validation {
    condition     = can(tonumber(var.monthly_budget_limit)) && tonumber(var.monthly_budget_limit) > 0
    error_message = "monthly_budget_limit deve ser um número positivo em string. Ex: '150'."
  }
}
