# ADR-009  VPC Endpoints vs NAT Gateway Strategy

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:** Rafael Santos (CTO), Bruno Oliveira (SecOps)

---

## 1. Context

Wayfinder Cloud Lambdas need to communicate with multiple AWS services
(Config, CloudTrail, CloudWatch, KMS, SNS, SQS, Secrets Manager, EventBridge, S3)
to perform compliance and observability functions.

There are two ways to enable this access from Lambdas in a private VPC:

1. **NAT Gateway** - routes traffic to the public internet where AWS endpoints are
2. **VPC Endpoints** - direct communication with AWS services inside the AWS network, without internet

Both options have cost, security, and latency implications that need to be evaluated.

---

## 2. Options Evaluated

### Option A - NAT Gateway (only solution)

**Architecture:** Lambdas in private subnet -> NAT GW in public subnet -> internet -> AWS APIs

**Pros:**
- Simple setup - one NAT Gateway covers all services
- No extra endpoints to manage
- Allows internet access for legitimate cases (e.g., external webhook)

**Cons:**
- **Cost:** $0.045/hour per NAT GW x 730h/month = $32.85/month + $0.045/GB processed
- **Security:** traffic for sensitive data (KMS credentials, CloudTrail logs) goes through the public internet before being encrypted at the application level
- **Performance:** additional latency due to internet routing
- **Regulatory risk:** for LGPD Art. 46 sensitive health data, it is preferable to keep traffic in the private AWS network

### Option B - VPC Interface Endpoints for critical services (CHOSEN for security)

**Architecture:** Lambdas in private subnet -> VPC Interface Endpoint -> AWS API (internal AWS network)

**Pros:**
- Traffic never leaves the AWS network - no data travels the public internet
- Lower latency (~1-2ms vs ~10-20ms via NAT)
- Auditable: connections to endpoints appear in VPC Flow Logs
- Allows blocking access to specific AWS services via endpoint policy
- S3 and DynamoDB: free Gateway Endpoints

**Cons:**
- **Cost:** $0.01/hour per endpoint x 730h = $7.30/endpoint/month
- 9 Interface Endpoints = ~$65.70/month (prod, 2 AZs)
- Complexity: each endpoint needs a Security Group and DNS resolution
- Not all AWS services have a VPC Endpoint available (e.g., QuickSight)

### Option C - Hybrid: Endpoints for critical services + NAT for others

**Architecture:** VPC Endpoints for Config, CloudTrail, KMS, Secrets Manager (sensitive data) + NAT GW for the rest

**Pros:** Reduced cost vs full Option B

**Cons:** Complexity of managing two outbound paths; risk of incorrect routing

---

## 3. Decision

**Option B - VPC Interface Endpoints for all AWS services used by Lambdas,**
**plus Gateway Endpoints for S3 and DynamoDB (free).**

We also keep 1 NAT Gateway per environment (1 in dev, 2 in prod) for:
- Lambdas that need to call external APIs (laboratory webhooks, PagerDuty)
- Package updates during build (does not use NAT at runtime)
- Fallback for services without a VPC Endpoint

---

## 4. Justification

### 4.1 Security (main reason for the VitaCore context)

```
With NAT Gateway:
Lambda -> NAT GW -> public internet -> api.kms.us-east-1.amazonaws.com
   KMS traffic (health data decryption key) via internet

With VPC Interface Endpoint:
Lambda -> VPC Endpoint (private ENI) -> AWS network -> KMS
   KMS traffic never leaves the AWS network
```

For health data under LGPD Art. 46, traffic for cryptographic operations
(KMS), credentials (Secrets Manager), and audit logs (CloudTrail) should,
ideally, never travel through public networks - even if TLS protects the content.

### 4.2 Compliance with AWS Security Best Practices

AWS Foundational Security Best Practices (FSBP) and the CIS AWS Benchmark recommend
using VPC Endpoints for access to AWS services from private VPCs.
Security Hub would detect it as a finding if Lambdas in VPC did not have endpoints configured.

### 4.3 Cost Analysis (dev vs prod)

| Environment | NAT GW | Interface Endpoints | Gateway Endpoints | Total/month |
|---|---|---|---|---|
| Dev | 1 x $32.85 | 9 x $7.30 (1 AZ) | $0 | ~$98 |
| Prod | 2 x $32.85 | 9 x $14.60 (2 AZs) | $0 | ~$197 |

**Cost avoided through security:**
- One incident like March costs ~R$ 2.1M
- Annual cost of all endpoints in prod: ~$197 x 12 = $2,364 = R$ 11,820
- Security ROI: 177x

### 4.4 Attack Surface Reduction

With VPC Endpoints and Security Group without internet egress (except via NAT for external APIs):

```
Security Group sg-lambda:
  egress 443  pl-xxxxx (S3 prefix list via Gateway Endpoint)   -> S3
  egress 443  ENI VPC Endpoints (via SG rule)                  -> all services
  egress 443  0.0.0.0/0 via NAT (only for external APIs)
  ingress:   NONE (Lambdas do not receive direct traffic)
```

This means that even if a Lambda is compromised, it cannot reach
unauthorized services outside the AWS network.

---

## 5. Configured Endpoints

| Endpoint | Type | Cost/AZ/month | Service that uses it |
|---|---|---|---|
| `com.amazonaws.us-east-1.s3` | Gateway (free) | $0 | All Lambdas, CloudTrail |
| `com.amazonaws.us-east-1.dynamodb` | Gateway (free) | $0 | Lambda auto-remediation, guardrail |
| `com.amazonaws.us-east-1.config` | Interface | $7.30 | compliance-evaluator |
| `com.amazonaws.us-east-1.cloudtrail` | Interface | $7.30 | auto-remediation |
| `com.amazonaws.us-east-1.monitoring` | Interface | $7.30 | All Lambdas (CloudWatch) |
| `com.amazonaws.us-east-1.logs` | Interface | $7.30 | All Lambdas (CW Logs) |
| `com.amazonaws.us-east-1.kms` | Interface | $7.30 | All Lambdas |
| `com.amazonaws.us-east-1.sns` | Interface | $7.30 | compliance-evaluator, incident-notifier |
| `com.amazonaws.us-east-1.sqs` | Interface | $7.30 | DLQ |
| `com.amazonaws.us-east-1.secretsmanager` | Interface | $7.30 | ECS, Lambdas |
| `com.amazonaws.us-east-1.events` | Interface | $7.30 | compliance-evaluator |
| `com.amazonaws.us-east-1.lambda` | Interface | $7.30 | EventBridge -> Lambda invocation |
| `com.amazonaws.us-east-1.ssm` | Interface | $7.30 | Systems Manager Session Manager |
| `com.amazonaws.us-east-1.ssmmessages` | Interface | $7.30 | SSM Session Manager |
| `com.amazonaws.us-east-1.ec2messages` | Interface | $7.30 | SSM Agent |

**Total Interface Endpoints: 13 x $7.30 = $94.90/AZ/month in prod (2 AZs = $189.80)**

> **Optimization note:** In dev, endpoints are provisioned in only 1 AZ,
> reducing to $94.90/month. High endpoint availability in 2 AZs is
> reserved for prod, where resilience is a contractual requirement.

---

## 6. Endpoint Policy (Example - KMS)

For maximum security, each endpoint can have a policy that restricts which
calls are allowed. Example for the KMS endpoint:

```json
{
  "Statement": [
    {
      "Sid": "AllowOnlyVitaCoreAccount",
      "Effect": "Allow",
      "Principal": "*",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
      "Resource": "arn:aws:kms:us-east-1:123456789012:key/*",
      "Condition": {
        "StringEquals": {
          "aws:PrincipalAccount": "123456789012"
        }
      }
    }
  ]
}
```

This prevents the KMS endpoint from responding to requests from outside the VitaCore
account, even if credentials from another account were maliciously injected into the Lambda.

---

## 7. Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| Higher cost vs NAT-only ($95 vs $33/month in dev) | Medium | Justified by security ROI (177x) |
| More resources to manage (13 endpoints) | Low | Terraform `for_each` manages all with one block |
| Not all AWS services have a VPC Endpoint | Low | NAT GW remains for external APIs (PagerDuty, Slack) |
| DNS resolution requires `enableDnsSupport = true` in the VPC | None | Already configured in networking module |

---

## 8. Consequences

- `networking` module MUST provision the 13 listed VPC Endpoints
- Security Group `sg-lambda` MUST have egress restricted to known endpoints
- Every new AWS service added to the project MUST have an endpoint evaluated
- Endpoint cost MUST be monitored via Budget #1 (included in total)
- VPC Flow Logs MUST be enabled for traffic audit via endpoints
