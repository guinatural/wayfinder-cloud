################################################################################
# Módulo: security  Outputs
# Projeto: Wayfinder Cloud  VitaCore Health
################################################################################

output "guardduty_detector_id" {
  description = "ID do detector GuardDuty criado. Necessário para configurar findings export e integrações com SIEM externo."
  value       = aws_guardduty_detector.wayfinder.id
}

output "guardduty_detector_arn" {
  description = "ARN do detector GuardDuty. Usado para configurar S3 findings export e cross-account sharing."
  value       = aws_guardduty_detector.wayfinder.arn
}

output "securityhub_arn" {
  description = "ARN da conta Security Hub habilitada. Usado para referenciar o hub em integrações com SIEM e relatórios."
  value       = aws_securityhub_account.wayfinder.id  # Security Hub retorna account ID como resource ID
}

output "securityhub_fsbp_subscription_arn" {
  description = "ARN da subscription AWS FSBP no Security Hub. Referenciado no relatório de postura de segurança."
  value       = aws_securityhub_standards_subscription.fsbp.id
}

output "securityhub_cis_subscription_arn" {
  description = "ARN da subscription CIS Benchmark 1.4 no Security Hub."
  value       = aws_securityhub_standards_subscription.cis_v14.id
}

output "inspector_enabled" {
  description = "Indica se Inspector v2 está habilitado (true/false). Usado para validação em pipelines de CI/CD."
  value       = length(aws_inspector2_enabler.wayfinder.resource_types) > 0
}

output "monthly_budget_id" {
  description = "ID do Budget de custo mensal total. Referenciado em dashboards de governança de custo."
  value       = aws_budgets_budget.monthly_total.id
}

output "guardduty_event_rule_arn" {
  description = "ARN da EventBridge Rule que roteia GuardDuty findings para a Lambda compliance-evaluator."
  value       = aws_cloudwatch_event_rule.guardduty_findings.arn
}
