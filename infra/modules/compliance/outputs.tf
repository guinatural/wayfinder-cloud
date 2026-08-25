output "config_recorder_name" { value = aws_config_configuration_recorder.wayfinder.name }
output "managed_rule_arns"   { value = { for k, v in aws_config_config_rule.managed : k => v.arn } }
output "custom_rule_arns"    { value = { for k, v in aws_config_config_rule.custom  : k => v.arn } }
