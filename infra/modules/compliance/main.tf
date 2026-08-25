################################################################################
# Módulo: compliance
# Responsabilidade: AWS Config Recorder, Delivery Channel, Rules (managed + custom)
# Projeto: Wayfinder Cloud  VitaCore Health
# Versão: 2.0  14 Custom Rules WAYFINDER-001 a WAYFINDER-014 + 22 Managed Rules
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"

  # ---------------------------------------------------------------------------
  # Managed Rules  identificadores AWS oficiais
  # Cobre controles LGPD, CIS AWS Foundations e AWS FSBP
  # ---------------------------------------------------------------------------
  managed_rules = {
    # Auditoria e trilha (LGPD art. 37)
    "cloud-trail-enabled"                          = "CLOUD_TRAIL_ENABLED"
    "cloudtrail-s3-dataevents-enabled"             = "CLOUDTRAIL_S3_DATAEVENTS_ENABLED"
    # Criptografia (LGPD art. 46)
    "encrypted-volumes"                            = "ENCRYPTED_VOLUMES"
    "rds-storage-encrypted"                        = "RDS_STORAGE_ENCRYPTED"
    # S3 proteção pública (LGPD art. 46)
    "s3-bucket-public-read-prohibited"             = "S3_BUCKET_PUBLIC_READ_PROHIBITED"
    "s3-bucket-public-write-prohibited"            = "S3_BUCKET_PUBLIC_WRITE_PROHIBITED"
    "s3-bucket-server-side-encryption-enabled"     = "S3_BUCKET_SERVER_SIDE_ENCRYPTION_ENABLED"
    # IAM e identidade (LGPD art. 47)
    "iam-root-access-key-check"                    = "IAM_ROOT_ACCESS_KEY_CHECK"
    "mfa-enabled-for-iam-console-access"           = "MFA_ENABLED_FOR_IAM_CONSOLE_ACCESS"
    "iam-no-inline-policy-check"                   = "IAM_NO_INLINE_POLICY_CHECK"
    # Rede (LGPD art. 46)
    "vpc-flow-logs-enabled"                        = "VPC_FLOW_LOGS_ENABLED"
    # Ameaças (LGPD art. 46, 50)
    "guardduty-enabled-centralized"                = "GUARDDUTY_ENABLED_CENTRALIZED"
    "securityhub-enabled"                          = "SECURITYHUB_ENABLED"
    "inspector-ec2-scan-enabled"                   = "INSPECTOR_EC2_SCANNING_ENABLED"
    # Credenciais e rotação (LGPD art. 47)
    "access-keys-rotated"                          = "ACCESS_KEYS_ROTATED"
    "iam-password-policy"                          = "IAM_PASSWORD_POLICY"
    "secretsmanager-rotation-enabled"              = "SECRETSMANAGER_ROTATION_ENABLED_CHECK"
    # Rede restrita (LGPD art. 46)
    "restricted-ssh"                               = "RESTRICTED_INCOMING_TRAFFIC"
    "restricted-common-ports"                      = "RESTRICTED_COMMON_PORTS"
    # Dados (LGPD art. 46)
    "dynamodb-table-encrypted-at-rest"             = "DYNAMODB_TABLE_ENCRYPTED_AT_REST"
    "elasticache-redis-cluster-automatic-backup"   = "ELASTICACHE_REDIS_CLUSTER_AUTOMATIC_BACKUP_CHECK"
    "wafv2-webacl-not-empty"                       = "WAFV2_WEBACL_NOT_EMPTY"
    # Backup (LGPD art. 46)
    "backup-plan-min-frequency-and-min-retention-check" = "BACKUP_PLAN_MIN_FREQUENCY_AND_MIN_RETENTION_CHECK"
  }

  # ---------------------------------------------------------------------------
  # Custom Rules WAYFINDER-001 a WAYFINDER-014
  # Implementadas via Lambda compliance-evaluator (CUSTOM_LAMBDA)
  # Específicas para contexto VitaCore Health + LGPD + CFM
  # ---------------------------------------------------------------------------
  custom_rules = {
    "WAYFINDER-001" = "S3 com dados de saude sem criptografia KMS CMK (LGPD Art.46,49)"
    "WAYFINDER-002" = "S3 com dados de saude com acesso publico habilitado (LGPD Art.46)"
    "WAYFINDER-003" = "CloudTrail desabilitado  licao do incidente 15/03/2026 (LGPD Art.37,48)"
    "WAYFINDER-004" = "RDS sem criptografia em repouso (LGPD Art.46)"
    "WAYFINDER-005" = "IAM com permissoes administrativas excessivas Action:* (LGPD Art.6IV,47)"
    "WAYFINDER-006" = "EC2 com dados de saude em subnet publica (LGPD Art.46,49)"
    "WAYFINDER-007" = "Credenciais potenciais em variaveis de ambiente Lambda (LGPD Art.46)"
    "WAYFINDER-008" = "CloudWatch Logs sem criptografia KMS (LGPD Art.46)"
    "WAYFINDER-009" = "Security Group com SSH/RDP aberto para internet (LGPD Art.46)"
    "WAYFINDER-010" = "DynamoDB sem criptografia em repouso (LGPD Art.46)"
    "WAYFINDER-011" = "ECS Task com privilegio elevado (privileged=true) (LGPD Art.49)"
    "WAYFINDER-012" = "IAM Access Key com mais de 90 dias sem rotacao (LGPD Art.47)"
    "WAYFINDER-013" = "S3 sem Object Lock para dados com retencao obrigatoria (CFM + LGPD)"
    "WAYFINDER-014" = "Secrets Manager nao usado  credenciais possivelmente hardcoded (LGPD Art.46)"
  }
}

################################################################################
# AWS Config  Configuration Recorder
################################################################################

resource "aws_config_configuration_recorder" "wayfinder" {
  name     = "${local.name_prefix}-recorder"
  role_arn = var.config_role_arn

  recording_group {
    all_supported                 = true
    include_global_resource_types = true
  }
}

################################################################################
# AWS Config  Delivery Channel
################################################################################

resource "aws_config_delivery_channel" "wayfinder" {
  name           = "${local.name_prefix}-delivery-channel"
  s3_bucket_name = var.config_bucket_id
  s3_key_prefix  = "config"
  sns_topic_arn  = var.config_delivery_sns_arn

  snapshot_delivery_properties {
    delivery_frequency = "TwentyFour_Hours"
  }

  depends_on = [aws_config_configuration_recorder.wayfinder]
}

################################################################################
# AWS Config  Recorder Status (habilitar gravação contínua)
################################################################################

resource "aws_config_configuration_recorder_status" "wayfinder" {
  name       = aws_config_configuration_recorder.wayfinder.name
  is_enabled = true

  depends_on = [aws_config_delivery_channel.wayfinder]
}

################################################################################
# Managed Config Rules  22 regras cobrindo LGPD, CIS e FSBP
################################################################################

resource "aws_config_config_rule" "managed" {
  for_each = local.managed_rules

  name        = "${local.name_prefix}-${each.key}"
  description = "Wayfinder Cloud: ${each.key} (${each.value})"

  source {
    owner             = "AWS"
    source_identifier = each.value
  }

  depends_on = [aws_config_configuration_recorder_status.wayfinder]

  tags = {
    Name        = "${local.name_prefix}-${each.key}"
    RuleType    = "managed"
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

################################################################################
# Custom Config Rules (Lambda-backed)  WAYFINDER-001 a WAYFINDER-014
################################################################################

resource "aws_config_config_rule" "custom" {
  for_each = local.custom_rules

  name        = "${local.name_prefix}-${each.key}"
  description = each.value

  source {
    owner             = "CUSTOM_LAMBDA"
    source_identifier = var.evaluator_function_arn

    source_detail {
      event_source = "aws.config"
      message_type = "ConfigurationItemChangeNotification"
    }

    source_detail {
      event_source = "aws.config"
      message_type = "OversizedConfigurationItemChangeNotification"
    }
  }

  depends_on = [
    aws_config_configuration_recorder_status.wayfinder,
    aws_lambda_permission.config_invoke[each.key],
  ]

  tags = {
    Name        = "${local.name_prefix}-${each.key}"
    RuleType    = "custom-wayfinder"
    LGPDControl = each.key
    Environment = var.environment
    Project     = "wayfinder-cloud"
    ManagedBy   = "terraform"
  }
}

################################################################################
# Lambda Permissions  Config pode invocar o compliance-evaluator para cada rule
################################################################################

resource "aws_lambda_permission" "config_invoke" {
  for_each = local.custom_rules

  statement_id   = "AllowConfigInvoke-${replace(each.key, "-", "")}"
  action         = "lambda:InvokeFunction"
  function_name  = var.evaluator_function_arn
  principal      = "config.amazonaws.com"
  source_account = var.account_id
}
