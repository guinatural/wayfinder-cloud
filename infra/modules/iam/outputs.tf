################################################################################
# Módulo: iam  Outputs
################################################################################

output "config_role_arn" {
  description = "ARN da IAM Role para o AWS Config Recorder"
  value       = aws_iam_role.config.arn
}

output "lambda_evaluator_role_arn" {
  description = "ARN da IAM Role para a Lambda compliance-evaluator"
  value       = aws_iam_role.lambda_evaluator.arn
}

output "lambda_remediation_role_arn" {
  description = "ARN da IAM Role para a Lambda auto-remediation"
  value       = aws_iam_role.lambda_remediation.arn
}

output "lambda_reporter_role_arn" {
  description = "ARN da IAM Role para a Lambda audit-reporter"
  value       = aws_iam_role.lambda_reporter.arn
}
