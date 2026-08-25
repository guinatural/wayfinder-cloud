################################################################################
# Módulo: remediation  Outputs
################################################################################

output "auto_remediation_arn" {
  description = "ARN da Lambda auto-remediation"
  value       = aws_lambda_function.auto_remediation.arn
}

output "incident_notifier_arn" {
  description = "ARN da Lambda incident-notifier"
  value       = aws_lambda_function.incident_notifier.arn
}

output "remediation_attempts_table_name" {
  description = "Nome da tabela DynamoDB de tentativas de remediação"
  value       = aws_dynamodb_table.remediation_attempts.name
}
