################################################################################
# Wayfinder Cloud  Outputs: prod environment
################################################################################

output "audit_bucket_id" {
  description = "Nome do bucket S3 de trilha de auditoria (prod)"
  value       = module.storage.audit_bucket_id
}

output "kms_key_arn" {
  description = "ARN da KMS CMK principal (prod)"
  value       = module.storage.kms_key_arn
}

output "critical_topic_arn" {
  description = "ARN do SNS Topic para alertas críticos (prod)"
  value       = module.notifications.critical_topic_arn
}

output "wayfinder_event_bus_arn" {
  description = "ARN do EventBridge Event Bus do Wayfinder (prod)"
  value       = module.observability.wayfinder_event_bus_arn
}

output "cloudwatch_dashboard_url" {
  description = "URL do CloudWatch Dashboard Wayfinder Command Center (prod)"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=wayfinder-command-center-${var.environment}"
}

output "athena_workgroup" {
  description = "Nome do Athena workgroup para consultas de auditoria (prod)"
  value       = module.observability.athena_workgroup_name
}

output "config_recorder_name" {
  description = "Nome do AWS Config Recorder (prod)"
  value       = module.compliance.config_recorder_name
}

output "guardduty_detector_id" {
  description = "ID do detector GuardDuty (prod)"
  value       = module.security.guardduty_detector_id
}

output "securityhub_arn" {
  description = "ARN do Security Hub (prod)"
  value       = module.security.securityhub_arn
}

output "inspector_enabled" {
  description = "Inspector v2 habilitado em prod"
  value       = module.security.inspector_enabled
}

output "cloudtrail_arn" {
  description = "ARN do CloudTrail trail (prod)"
  value       = module.observability.cloudtrail_arn
}
