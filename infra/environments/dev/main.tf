################################################################################
# Wayfinder Cloud  Environment: dev
# Orquestra todos os módulos para o ambiente de desenvolvimento
################################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Remote state: S3 + DynamoDB lock
  # IMPORTANTE: o bucket e a tabela DynamoDB devem existir antes do primeiro apply
  # Execute: cd ../../../scripts && python bootstrap_state.py
  backend "s3" {
    bucket         = "wayfinder-cloud-tfstate-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "wayfinder-cloud-tfstate-lock"
    profile        = "wayfinder-dev"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "wayfinder-cloud"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = "guilherme-barreto"
      CostCenter  = "engineering"
    }
  }
}

################################################################################
# Data sources
################################################################################

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

################################################################################
# Módulo: Storage
# Cria S3 buckets (audit trail, relatórios, lambda packages) + KMS CMKs
################################################################################

module "storage" {
  source = "../../modules/storage"

  environment        = var.environment
  account_id         = data.aws_caller_identity.current.account_id
  region             = data.aws_region.current.name
  audit_retention_days = var.audit_retention_days
}

################################################################################
# Módulo: IAM
# Cria roles e policies com least privilege para todas as Lambdas
################################################################################

module "iam" {
  source = "../../modules/iam"

  environment        = var.environment
  account_id         = data.aws_caller_identity.current.account_id
  region             = data.aws_region.current.name
  audit_bucket_arn   = module.storage.audit_bucket_arn
  kms_key_arn        = module.storage.kms_key_arn
}

################################################################################
# Módulo: Networking
# VPC, subnets privadas, NAT Gateway, VPC Endpoints para serviços AWS
################################################################################

module "networking" {
  source = "../../modules/networking"

  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  azs         = var.availability_zones
}

################################################################################
# Módulo: Notifications
# SNS Topics (CRITICAL, WARNING, INFO) + AWS Chatbot (Slack) + subscrições
################################################################################

module "notifications" {
  source = "../../modules/notifications"

  environment       = var.environment
  kms_key_arn       = module.storage.kms_key_arn
  alert_email       = var.alert_email
  slack_workspace_id = var.slack_workspace_id
  slack_channel_id  = var.slack_channel_id
}

################################################################################
# Módulo: Compliance
# AWS Config Recorder, Delivery Channel, Managed Rules + Custom Rules
################################################################################

module "compliance" {
  source = "../../modules/compliance"

  environment              = var.environment
  account_id               = data.aws_caller_identity.current.account_id
  region                   = data.aws_region.current.name
  config_bucket_arn        = module.storage.audit_bucket_arn
  config_bucket_id         = module.storage.audit_bucket_id
  kms_key_arn              = module.storage.kms_key_arn
  config_delivery_sns_arn  = module.notifications.info_topic_arn
  config_role_arn          = module.iam.config_role_arn
  evaluator_function_arn   = module.observability.compliance_evaluator_arn
}

################################################################################
# Módulo: Observability
# CloudWatch (Logs, Metrics, Alarms, Dashboard), CloudTrail, X-Ray, Lambdas
################################################################################

module "observability" {
  source = "../../modules/observability"

  environment            = var.environment
  account_id             = data.aws_caller_identity.current.account_id
  region                 = data.aws_region.current.name
  audit_bucket_id        = module.storage.audit_bucket_id
  audit_bucket_arn       = module.storage.audit_bucket_arn
  kms_key_arn            = module.storage.kms_key_arn
  critical_topic_arn     = module.notifications.critical_topic_arn
  warning_topic_arn      = module.notifications.warning_topic_arn
  info_topic_arn         = module.notifications.info_topic_arn
  lambda_role_arn        = module.iam.lambda_evaluator_role_arn
  lambda_subnet_ids      = module.networking.private_subnet_ids
  lambda_security_group_id = module.networking.lambda_sg_id
}

################################################################################
# Módulo: Remediation
# Lambda auto-remediation + EventBridge rules de gatilho
################################################################################

module "remediation" {
  source = "../../modules/remediation"

  environment              = var.environment
  account_id               = data.aws_caller_identity.current.account_id
  region                   = data.aws_region.current.name
  lambda_role_arn          = module.iam.lambda_remediation_role_arn
  lambda_subnet_ids        = module.networking.private_subnet_ids
  lambda_security_group_id = module.networking.lambda_sg_id
  kms_key_arn              = module.storage.kms_key_arn
  critical_topic_arn       = module.notifications.critical_topic_arn
  warning_topic_arn        = module.notifications.warning_topic_arn
  wayfinder_event_bus_arn   = module.observability.wayfinder_event_bus_arn
}

################################################################################
# Módulo: Security
# GuardDuty, Security Hub (FSBP + CIS 1.4), Inspector v2, Budgets,
# EventBridge rules para findings de ameaça  Lambda compliance-evaluator
################################################################################

module "security" {
  source = "../../modules/security"

  environment          = var.environment
  account_id           = data.aws_caller_identity.current.account_id
  region               = data.aws_region.current.name
  kms_key_arn          = module.storage.kms_key_arn
  critical_topic_arn   = module.notifications.critical_topic_arn
  warning_topic_arn    = module.notifications.warning_topic_arn
  monthly_budget_limit = var.monthly_budget_limit
  lambda_evaluator_arn = module.observability.compliance_evaluator_arn
}
