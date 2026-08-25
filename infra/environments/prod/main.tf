################################################################################
# Wayfinder Cloud  Environment: prod
# ATENÇÃO: Este arquivo gerencia infraestrutura de PRODUÇÃO.
#
# Diferenças em relação ao dev:
#   - Object Lock em COMPLIANCE mode (imutabilidade jurídica  não pode ser desfeita)
#   - audit_retention_days = 365 (vs 90 no dev)
#   - force_destroy = false em TODOS os buckets S3
#   - NAT Gateway em AMBAS as AZs (alta disponibilidade)
#   - DynamoDB com Point-in-Time Recovery obrigatório
#   - Não há terraform destroy disponível (proteção humana)
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

  # Remote state prod  bucket e tabela DynamoDB separados do dev
  backend "s3" {
    bucket         = "wayfinder-cloud-tfstate-prod"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "wayfinder-cloud-tfstate-lock"
    profile        = "wayfinder-prod"
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
################################################################################

module "storage" {
  source = "../../modules/storage"

  environment          = var.environment
  account_id           = data.aws_caller_identity.current.account_id
  region               = data.aws_region.current.name
  audit_retention_days = var.audit_retention_days
  # force_destroy = false é o default  não sobrescrever em prod
}

################################################################################
# Módulo: IAM
################################################################################

module "iam" {
  source = "../../modules/iam"

  environment      = var.environment
  account_id       = data.aws_caller_identity.current.account_id
  region           = data.aws_region.current.name
  audit_bucket_arn = module.storage.audit_bucket_arn
  kms_key_arn      = module.storage.kms_key_arn
}

################################################################################
# Módulo: Networking
################################################################################

module "networking" {
  source = "../../modules/networking"

  environment = var.environment
  vpc_cidr    = var.vpc_cidr
  azs         = var.availability_zones
}

################################################################################
# Módulo: Notifications
################################################################################

module "notifications" {
  source = "../../modules/notifications"

  environment        = var.environment
  kms_key_arn        = module.storage.kms_key_arn
  alert_email        = var.alert_email
  slack_workspace_id = var.slack_workspace_id
  slack_channel_id   = var.slack_channel_id
}

################################################################################
# Módulo: Compliance
################################################################################

module "compliance" {
  source = "../../modules/compliance"

  environment             = var.environment
  account_id              = data.aws_caller_identity.current.account_id
  region                  = data.aws_region.current.name
  config_bucket_arn       = module.storage.audit_bucket_arn
  config_bucket_id        = module.storage.audit_bucket_id
  kms_key_arn             = module.storage.kms_key_arn
  config_delivery_sns_arn = module.notifications.info_topic_arn
  config_role_arn         = module.iam.config_role_arn
  evaluator_function_arn  = module.observability.compliance_evaluator_arn
}

################################################################################
# Módulo: Observability
################################################################################

module "observability" {
  source = "../../modules/observability"

  environment              = var.environment
  account_id               = data.aws_caller_identity.current.account_id
  region                   = data.aws_region.current.name
  audit_bucket_id          = module.storage.audit_bucket_id
  audit_bucket_arn         = module.storage.audit_bucket_arn
  kms_key_arn              = module.storage.kms_key_arn
  critical_topic_arn       = module.notifications.critical_topic_arn
  warning_topic_arn        = module.notifications.warning_topic_arn
  info_topic_arn           = module.notifications.info_topic_arn
  lambda_role_arn          = module.iam.lambda_evaluator_role_arn
  lambda_subnet_ids        = module.networking.private_subnet_ids
  lambda_security_group_id = module.networking.lambda_sg_id
}

################################################################################
# Módulo: Remediation
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
# GuardDuty, Security Hub (FSBP + CIS 1.4), Inspector v2, Budgets
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
