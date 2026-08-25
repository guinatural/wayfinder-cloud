output "kms_key_arn"         { value = aws_kms_key.wayfinder.arn }
output "kms_key_id"          { value = aws_kms_key.wayfinder.key_id }
output "audit_bucket_arn"    { value = aws_s3_bucket.audit_trail.arn }
output "audit_bucket_id"     { value = aws_s3_bucket.audit_trail.id }
output "lambda_bucket_id"    { value = aws_s3_bucket.lambda_packages.id }
output "lambda_bucket_arn"   { value = aws_s3_bucket.lambda_packages.arn }
