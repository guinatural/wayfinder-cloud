# ADR-008  Secrets Management Strategy

**Status:** Accepted
**Date:** 2026-04-15
**Authors:** Bruno Oliveira (SecOps Lead), Carla Mendes (Dev Lead)
**Reviewers:** Rafael Santos (CTO), Ana Lima (DPO)
**Motivation:** Hardcoded and unrotated credentials found during forensic analysis of the March incident

---

## 1. Context

During the forensic investigation of the March 2026 incident, the security team
identified an additional problem beyond the public bucket: **database credentials
hardcoded in Lambda function environment variables**.

Specifically, they found:
```
Lambda: vitacore-report-generator
Environment variables:
  DB_HOST=aurora-vitacore-legacy.cluster-xxx.us-east-1.rds.amazonaws.com
  DB_USER=admin
  DB_PASSWORD=V1t@c0r3#2022   PLAIN TEXT CREDENTIAL

Lambda: vitacore-lab-integration
Environment variables:
  LAB_API_KEY=sk_live_xxxxxxxxxxxxxxxxxxx   EXTERNAL API KEY
  LAB_WEBHOOK_SECRET=whs_xxxxxxxxxxxxxxxx   WEBHOOK SECRET
```

The inventory also revealed:
- 67 IAM Users with access keys not rotated for more than 180 days
- 3 deploy scripts with hardcoded credentials in private repositories
- 1 plain text database credential in a configuration file on S3

**Potential impact:** If an attacker had obtained the credentials during the S3 bucket
exposure period, they could have accessed the Aurora database with administrator privileges,
exposing all 127,000 complete patient records.

---

## 2. Options Considered

### Option A: AWS Secrets Manager (CHOSEN)

**Description:** AWS managed service to securely store, rotate, and retrieve
credentials and secrets.

**Pros:**
- Native automatic rotation for Aurora MySQL (zero downtime via dual-password)
- Native integration with ECS (envFrom in task definitions) and Lambda (SDK call)
- Secret versioning (AWSCURRENT, AWSPENDING, AWSPREVIOUS)
- CloudTrail audit of each GetSecretValue call
- KMS CMK for encrypting the secret value
- Multi-region replication (for future disaster recovery)

**Cons:**
- Cost: $0.40/secret/month + $0.05/10,000 API calls
- Additional ~1-5ms latency on service startup (mitigated with cache)
- 15 secrets = $6/month - acceptable cost given the risk

### Option B: AWS Systems Manager Parameter Store SecureString

**Description:** Parameter Store with KMS encryption for sensitive values.

**Pros:**
- Cost: $0.05/advanced parameter/month (cheaper than Secrets Manager)
- Natively integrated with SSM Agent and Lambda
- Parameter hierarchy with paths (/vitacore/prod/db/password)

**Cons:**
- **No automatic rotation** - requires a custom Lambda for rotation
- No explicit versioning with labels (AWSCURRENT/AWSPENDING)
- No native multi-region support
- No built-in rotation for RDS/Aurora - critical blocker for VitaCore

**Discarded:** The absence of automatic rotation for Aurora is a blocker.
The team does not have capacity to maintain custom rotation Lambdas.

### Option C: HashiCorp Vault

**Description:** Open-source secrets management solution, self-hosted or HCP Vault.

**Pros:**
- Extremely flexible, supports any type of secret
- Dynamic secrets: temporary credentials generated on-demand (ideal for database)
- Granular audit log, complex policies
- Vendor-agnostic

**Cons:**
- **Operational overhead:** requires a dedicated cluster, HA, backup, patching
- **No team experience:** none of the 23 engineers has experience with Vault
- Infrastructure cost: ~$200/month for HA cluster + HCP Vault additional cost
- HCP Vault (managed): $0.03/hour + $0.003/secret/month - more expensive than Secrets Manager for this volume

**Discarded:** Unacceptable operational overhead for a team without dedicated SRE.

### Option D: Encrypted Environment Variables (improved status quo)

**Description:** Keep env vars but encrypt with KMS before storing.

**Pros:**
- No change in how the code accesses the value
- No additional cost beyond KMS

**Cons:**
- **No automatic rotation** - same limitation as Option B
- Credential still visible (decrypted) to anyone with Lambda access
- Does not solve the inventory problem (how to know where all secrets are?)
- CloudTrail does not record access to the environment variable value

**Discarded:** Does not adequately solve the identified problems.

---

## 3. Decision

**Secrets Manager for database credentials and external API keys.**
**Parameter Store (SecureString) for non-sensitive configurations.**

### 3.1 What Goes to Secrets Manager

| Secret | Type | Rotation | Interval |
|---|---|---|---|
| Aurora writer credentials (3 clusters) | RDS | Built-in Lambda | 30 days |
| Aurora reader credentials | RDS | Built-in Lambda | 30 days |
| ElastiCache Redis AUTH token | Other | Manual (alert) | 90 days |
| Laboratory API keys (12 labs) | Other | Manual (alert) | 90 days |
| Health plan integration keys (3) | Other | Manual (alert) | 90 days |
| Cognito Client Secret | Other | Manual (alert) | 180 days |
| Webhook secrets (2) | Other | Manual (alert) | 90 days |

**Total: ~15 secrets x $0.40 = $6/month**

### 3.2 What Goes to Parameter Store

| Parameter | Type | Example |
|---|---|---|
| External service URLs | String | /vitacore/prod/lab/endpoint |
| Feature flags | String | /vitacore/prod/features/telehealth-enabled |
| Timeout configurations | String | /vitacore/prod/api/timeout-ms |
| Internal endpoint addresses | String | /vitacore/prod/redis/endpoint |

---

## 4. Automatic Aurora Credential Rotation

Secrets Manager offers native rotation for Aurora MySQL using the
**dual-password** strategy (zero downtime):

```
Automatic rotation (every 30 days):
  1. Secrets Manager creates a new temporary password
  2. Updates the user in Aurora MySQL (keeps previous password active)
  3. Tests new password via AWSPENDING rotation Lambda
  4. If test OK: AWSPENDING -> AWSCURRENT, old -> AWSPREVIOUS
  5. Aurora accepts both passwords for 24h (transition window)
  6. Services fetch AWSCURRENT on next cold start/refresh

Result: zero downtime, zero manual intervention, no password exposure.

Terraform:
resource "aws_secretsmanager_secret_rotation" "aurora_writer" {
  secret_id           = aws_secretsmanager_secret.aurora_writer.id
  rotation_lambda_arn = data.aws_lambda_function.rds_rotation.arn
  rotation_rules {
    automatically_after_days = 30
  }
}
```

---

## 5. Migration of Existing Credentials

### 5.1 Inventory and Migration (30-day Plan)

```
Week 1: Full inventory
   Audit all Lambdas: suspicious environment variables
   Audit all Git repositories: grep for password/key
   Audit S3 (configuration files)
   Output: spreadsheet with all identified secrets and locations

Week 2: Database credential migration (highest priority)
   Create secrets in Secrets Manager for 3 Aurora clusters
   Enable automatic rotation
   Update ECS task definitions and Lambdas to use envFrom/SDK
   Test in dev -> staging -> prod
   Delete old environment variables

Week 3: External API key migration
   Create secrets for laboratory and health plan keys
   Update integration code to fetch from Secrets Manager
   Rotate all keys in the source system (invalidate old ones)

Week 4: Validation and control
   WAYFINDER-007 and WAYFINDER-014 enabled on all Lambdas
   Zero findings from these rules = migration complete
   Document each secret in Secrets Manager with tags and owner
```

### 5.2 Code Pattern for Secret Retrieval

```python
# Recommended pattern: local cache with TTL to avoid latency
import boto3
import json
from functools import lru_cache
from datetime import datetime, timedelta

_secrets_cache = {}
_cache_ttl = timedelta(hours=1)

def get_secret(secret_name: str) -> dict:
    """Retrieves secret from Secrets Manager with 1-hour cache."""
    now = datetime.utcnow()

    if secret_name in _secrets_cache:
        value, cached_at = _secrets_cache[secret_name]
        if now - cached_at < _cache_ttl:
            return value  # Cache hit - no additional latency

    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    value = json.loads(response['SecretString'])
    _secrets_cache[secret_name] = (value, now)

    return value

# Usage:
db_creds = get_secret('vitacore/prod/aurora/writer')
connection = mysql.connect(
    host=db_creds['host'],
    user=db_creds['username'],
    password=db_creds['password'],
    database='vitacore'
)
```

---

## 6. Detective Controls - WAYFINDER-007 and WAYFINDER-014

### WAYFINDER-007 - Credentials in Lambda Environment Variables

```python
# compliance-evaluator logic for WAYFINDER-007
SENSITIVE_PATTERNS = re.compile(
    r'(password|passwd|secret|db_pass|api_key|token|credential|auth)',
    re.IGNORECASE
)
ARN_PATTERN = re.compile(r'^arn:aws:secretsmanager:')

def evaluate_lambda_env_vars(config_item):
    env_vars = config_item.get('configuration', {}).get('environment', {}).get('variables', {})

    for key, value in env_vars.items():
        if SENSITIVE_PATTERNS.search(key):
            if not ARN_PATTERN.match(str(value)):
                return {
                    'compliance': 'NON_COMPLIANT',
                    'annotation': f'Variable {key} appears to contain a credential. '
                                  f'Use Secrets Manager ARN instead of the direct value.',
                    'severity': 'HIGH',
                    'lgpd': 'Art. 46'
                }

    return {'compliance': 'COMPLIANT'}
```

### WAYFINDER-014 - Resources without Secrets Manager Reference

```
Logic: a resource with tag data-classification=health-* that has no reference
to a Secrets Manager ARN in its configurations is suspicious.

For Lambdas: check if environment.variables has any value with
             pattern arn:aws:secretsmanager:

For ECS Task Definitions: check if containerDefinitions has
             secrets[] with valueFrom pointing to Secrets Manager

For EC2: check if user-data or tags have reference (heuristic)
```

---

## 7. Detailed Costs

| Item | Cost |
|---|---|
| 15 secrets x $0.40/month | $6.00/month |
| 100k GetSecretValue calls/month x $0.05/10k | $0.50/month |
| Rotation Lambda (included in Secrets Manager) | $0.00 |
| KMS for secret encryption (included in vitacore-infra-key) | ~$0.10/month |
| **Monthly total** | **~$6.60/month** |

**Comparison with cost of an incident similar to March:**
- Annual prevention cost: ~$79/year
- Cost of 1 incident: ~R$ 2,107,000
- Secrets Manager pays its ROI in 12 years of prevention - or a single avoided incident

---

## 8. Consequences

**Positive:**
- Zero plain text credentials in code or environment variables
- Automatic Aurora credential rotation without manual intervention
- Granular audit: CloudTrail records each GetSecretValue with who accessed
- WAYFINDER-007/014 detect regressions (new code with hardcoded credential)
- Compliance with ISO 27001 A.8.11 (sensitive information management)
- LGPD Art. 46: technical measures for data protection implemented

**Negative:**
- Additional ~1-5ms latency on each service startup (mitigated with cache)
- Developers need to learn new credential access pattern
- $6.60/month additional cost - justified by ROI

**Success metrics:**
- Zero WAYFINDER-007 and WAYFINDER-014 findings after week 4 of migration
- 100% of Aurora credentials with automatic rotation enabled
- Zero credentials exposed in Git repositories (audit with git-secrets)
- Config Rule `secretsmanager-rotation-enabled` at 100% compliance
