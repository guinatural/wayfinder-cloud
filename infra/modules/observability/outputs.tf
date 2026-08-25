output "sentinel_event_bus_arn" {
  description = "ARN do EventBridge Bus (alias para compatibilidade com módulo remediation)"
  value       = aws_cloudwatch_event_bus.wayfinder.arn
}

output "wayfinder_event_bus_arn" {
  description = "ARN do EventBridge Custom Bus wayfinder-events"
  value       = aws_cloudwatch_event_bus.wayfinder.arn
}

output "wayfinder_event_bus_name" {
  description = "Nome do EventBridge Custom Bus wayfinder-events"
  value       = aws_cloudwatch_event_bus.wayfinder.name
}

output "compliance_evaluator_arn" {
  description = "ARN da Lambda compliance-evaluator"
  value       = aws_lambda_function.compliance_evaluator.arn
}

output "audit_reporter_arn" {
  description = "ARN da Lambda audit-reporter"
  value       = aws_lambda_function.audit_reporter.arn
}

output "cloudtrail_arn" {
  description = "ARN do CloudTrail trail multi-region"
  value       = aws_cloudtrail.wayfinder.arn
}

output "athena_workgroup_name" {
  description = "Nome do Athena workgroup para queries de auditoria"
  value       = aws_athena_workgroup.wayfinder.name
}

output "cloudwatch_dashboard_name" {
  description = "Nome do CloudWatch Dashboard Wayfinder Command Center"
  value       = aws_cloudwatch_dashboard.wayfinder.dashboard_name
}
