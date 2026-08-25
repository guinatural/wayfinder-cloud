################################################################################
# Módulo: storage
# Responsabilidade: KMS CMK + S3 buckets (audit, reports, lambda packages)
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# KMS  Customer Managed Key (CMK)
# Uma CMK dedicada para o projeto permite auditoria granular de uso de criptografia
################################################################################

resource "aws_kms_key" "wayfinder" {
  description             = "Wayfinder Cloud CMK  ${var.environment}"
  deletion_window_in_days = 7
  enable_key_rotation     = true # CIS AWS 3.8  rotação anual obrigatória

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudTrailEncrypt"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey*",
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringLike = {
            "kms:EncryptionContext:aws:cloudtrail:arn" = "arn:aws:cloudtrail:*:${var.account_id}:trail/*"
          }
        }
      },
      {
        Sid    = "AllowConfigServiceEncrypt"
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey*",
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name            = "${local.name_prefix}-cmk"
    DataClassification = "security-critical"
  }
}

resource "aws_kms_alias" "wayfinder" {
  name          = "alias/wayfinder-cloud-${var.environment}"
  target_key_id = aws_kms_key.wayfinder.key_id
}

################################################################################
# S3  Audit Trail Bucket
# Object Lock em COMPLIANCE mode  imutabilidade jurídica
################################################################################

resource "aws_s3_bucket" "audit_trail" {
  bucket = "${local.name_prefix}-audit-trail-${var.account_id}"

  # Force destroy apenas em dev  prod nunca pode ter isso ativado
  force_destroy = var.environment == "dev" ? true : false

  tags = {
    Name               = "${local.name_prefix}-audit-trail"
    DataClassification = "health-critical"
    LGPDArticle        = "Art.37-48"
    Immutable          = "true"
  }
}

resource "aws_s3_bucket_versioning" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id
  versioning_configuration {
    status = "Enabled" # Obrigatório para Object Lock
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  rule {
    default_retention {
      mode  = var.environment == "prod" ? "COMPLIANCE" : "GOVERNANCE"
      days  = var.audit_retention_days
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.wayfinder.arn
    }
    bucket_key_enabled = true # Reduz custo de KMS em ~99%
  }
}

resource "aws_s3_bucket_public_access_block" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  rule {
    id     = "cloudtrail-to-glacier"
    status = "Enabled"

    filter {
      prefix = "cloudtrail/"
    }

    transition {
      days          = var.audit_retention_days
      storage_class = "GLACIER"
    }

    expiration {
      # Logs expiram após 5 anos (1825 dias)  art. 205 CC
      days = 1825
    }
  }

  rule {
    id     = "config-to-glacier"
    status = "Enabled"

    filter {
      prefix = "config/"
    }

    transition {
      days          = var.audit_retention_days
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "compliance-events-to-glacier"
    status = "Enabled"

    filter {
      prefix = "compliance-events/"
    }

    transition {
      days          = var.audit_retention_days
      storage_class = "GLACIER"
    }

    expiration {
      days = 1825
    }
  }
}

resource "aws_s3_bucket_policy" "audit_trail" {
  bucket = aws_s3_bucket.audit_trail.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyNonTLSRequests"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.audit_trail.arn,
          "${aws_s3_bucket.audit_trail.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid    = "AllowCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.audit_trail.arn}/cloudtrail/AWSLogs/${var.account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      },
      {
        Sid    = "AllowCloudTrailBucketCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.audit_trail.arn
      },
      {
        Sid    = "AllowConfigWrite"
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action = [
          "s3:PutObject",
          "s3:GetBucketAcl"
        ]
        Resource = [
          aws_s3_bucket.audit_trail.arn,
          "${aws_s3_bucket.audit_trail.arn}/config/AWSLogs/${var.account_id}/*"
        ]
      }
    ]
  })
}

################################################################################
# S3  Lambda Packages Bucket (código das funções)
################################################################################

resource "aws_s3_bucket" "lambda_packages" {
  bucket = "${local.name_prefix}-lambda-packages-${var.account_id}"
}

resource "aws_s3_bucket_versioning" "lambda_packages" {
  bucket = aws_s3_bucket.lambda_packages.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_packages" {
  bucket = aws_s3_bucket.lambda_packages.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.wayfinder.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_packages" {
  bucket                  = aws_s3_bucket.lambda_packages.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
