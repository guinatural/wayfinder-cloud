output "critical_topic_arn" { value = aws_sns_topic.critical.arn }
output "warning_topic_arn"  { value = aws_sns_topic.warning.arn }
output "info_topic_arn"     { value = aws_sns_topic.info.arn }
