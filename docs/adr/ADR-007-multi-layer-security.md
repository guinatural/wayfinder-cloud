# ADR-007  Multi-Layer Security (Defense in Depth)

**Status:** Accepted
**Date:** 2026-04-10
**Authors:** Bruno Oliveira (SecOps Lead), Rafael Santos (CTO)
**Reviewers:** Ana Lima (DPO), Carla Mendes (Dev Lead)
**Motivation:** Post-mortem of the 2026-03-15 incident - S3 bucket public for 18 days

---

## 1. Context

The March 2026 incident exposed a critical architectural failure: VitaCore Health
depended on **a single security layer** - Block Public Access configured manually.
When that layer was accidentally disabled by a developer, there was no other barrier,
no detection, and no automatic remediation.

The result: 2,340 patient reports publicly exposed for 18 days, a fine of
R$ 420,000 from ANPD, and R$ 1.68M in lost contracts.

**Lesson learned:** A robust architecture must never depend on a single control.
Any control can fail - by human error, software bug, or malicious action.
The question is not "how do we prevent the control from failing?" but "what happens when it fails?"

### 1.1 Incident Failure Analysis

```
Single line of defense:
  S3 Block Public Access (manual configuration, no IaC)
      |
      v
       Junior dev runs the wrong command
              |
               v
                No detection -> 18 days of exposure

With Defense in Depth (what should have existed):
  Layer 1: S3 Block Public Access (configuration)
  Layer 2: SCP account deny-s3-public-access-enable (account)
  Layer 3: AWS Config WAYFINDER-002 (detection < 5 min)
  Layer 4: KMS CMK (data unreadable even if accessed)
  Layer 5: CloudTrail data events (audit trail)
  Layer 6: GuardDuty S3 protection (anomalous behavior)
  Layer 7: Change review process (human)

With all 7 layers active:
  Even if Layer 1 fails (human error)
   Layer 2 prevents or hinders the failure
   Layer 3 detects and remediates in < 5 minutes
   Layer 4 ensures accessed data is unreadable
  Result: zero effective data exposure
```

---

## 2. Decision

**Implement 7 independent security layers** for each type of data and resource
at VitaCore Health, where the failure of any individual layer is detected and
automatically remediated before it causes impact.

This ADR documents the Defense in Depth architecture for the VitaCore platform
monitored by Wayfinder Cloud.

---

## 3. The 7 Security Layers

### Layer 1 - Network Edge (CloudFront + WAF + Route 53)

**What it protects:** External traffic before reaching the application.

```
Route 53 Health Checks
   CloudFront (TLS 1.3 required, HTTPS only)
   WAF (OWASP Top 10, rate limiting, bot protection)
   ACM (managed certificates with automatic renewal)

Controls:
  - TLS 1.3: no downgrade to insecure protocols
  - WAF SQL Injection rule: blocks attempts before reaching the API
  - Rate limiting: 1000 req/min per IP (brute force protection)
  - HTTPS only: no unencrypted HTTP traffic

Wayfinder monitoring:
  - Config Rule: wafv2-webacl-not-empty
  - CloudWatch Alarm: WAF BlockedRequests > 100/min -> SNS WARNING
```

### Layer 2 - Network Isolation (VPC + Security Groups + Endpoints)

**What it protects:** Lateral communication between services.

```
VPC 10.0.0.0/16 with subnet segregation:
  Public:      ALB, NAT GW (no health data)
  Private App: ECS, Lambda (data in transit)
  Private Data: Aurora, Redis, DynamoDB (data at rest)

Security Groups (minimum privilege):
  sg-alb:  ingress 443 ONLY from CloudFront IP ranges
  sg-app:  ingress 8080 from sg-alb ONLY
  sg-data: ingress 3306/6379 from sg-app ONLY; NO egress

VPC Endpoints: AWS services without internet traffic
VPC Flow Logs: enabled on ALL VPCs

Wayfinder monitoring:
  - Config Rule: WAYFINDER-009 (SSH/DB ports exposed)
  - Config Rule: vpc-flow-logs-enabled
  - Config Rule: WAYFINDER-006 (EC2 health data in public subnet)
```

### Layer 3 - Authentication and Authorization (Cognito + IAM + SCPs)

**What it protects:** Who can do what on each resource.

```
For human users:
  - Cognito User Pools with mandatory MFA for doctors
  - IAM Identity Center (SSO) for engineer access
  - Permission sets with least privilege per role

For services and systems:
  - IAM Roles with minimum scope per ECS task and Lambda
  - Resource-based policies with condition tags
  - SCPs on the account: deny-root-account, require-mfa, deny-public-s3

Wayfinder monitoring:
  - Config Rule: WAYFINDER-005 (IAM Action:*)
  - Config Rule: iam-root-access-key-check
  - Config Rule: mfa-enabled-for-iam-console-access
  - Config Rule: WAYFINDER-012 (access key > 90 days)
```

### Layer 4 - Encryption (KMS + TLS + Secrets Manager)

**What it protects:** Data confidentiality even if accessed inappropriately.

```
Data at rest:
  - S3: SSE-KMS with CMK per data classification
  - Aurora: KMS at-rest encryption required
  - DynamoDB: SSE with CMK for health-* data
  - ElastiCache Redis: at-rest + in-transit encryption
  - EBS: encryption enabled by default on the account

Data in transit:
  - TLS 1.3 on all external endpoints
  - TLS on ECS to Aurora communication (enforce_ssl=1)
  - HTTPS between all internal components

Secrets:
  - Secrets Manager for DB credentials and API keys
  - Automatic Aurora credential rotation (30 days)
  - No hardcoded secrets (detected by WAYFINDER-007/014)

Incident lesson: even with a public S3, data with KMS CMK
is unreadable without the key. Layer 4 would be the final safeguard.

Wayfinder monitoring:
  - WAYFINDER-001 (S3 without KMS CMK)
  - WAYFINDER-004 (RDS without encryption)
  - WAYFINDER-007/014 (hardcoded credentials)
  - Config Rule: encrypted-volumes
```

### Layer 5 - Continuous Compliance (AWS Config + Wayfinder Rules)

**What it protects:** Ensures deviations from layers 1-4 are detected and fixed.

```
Central engine: AWS Config with 24 rules
  - Configuration change detection in < 2 minutes
  - WAYFINDER-002: detects public S3 in < 5 minutes (would have saved the incident)
  - Automatic remediation for 8 critical categories

Compliance pipeline:
  Config -> EventBridge -> Lambda compliance-evaluator
     SNS (alert) + Lambda auto-remediation (fix)

Self-monitoring:
  - WAYFINDER-003 ensures CloudTrail itself is active
  - CloudWatch Alarm if Config Recorder disables

This is the most important layer in Wayfinder Cloud -
it is the meta-layer that monitors all other layers.
```

### Layer 6 - Threat Detection (GuardDuty + Security Hub + Inspector)

**What it protects:** Active attacks, compromised credentials, vulnerabilities.

```
GuardDuty (ML-based):
  - Analyzes CloudTrail + VPC Flow Logs + DNS logs
  - Detects: compromised credentials, reconnaissance, C&C
  - S3 Protection: anomalous bucket access (including the March scenario)
  - Detection time: 15 min to 2h depending on finding type

Security Hub:
  - Aggregates findings from GuardDuty, Inspector, Config
  - FSBP and CIS score: security posture maturity benchmark
  - Target: FSBP > 85% in production

Inspector v2:
  - CVE vulnerabilities in EC2 and ECR images
  - Continuous scanning (not just on deploy)
  - Integrates with CI/CD pipeline via ECR on-push scan

Wayfinder monitoring:
  - EventBridge: GuardDuty findings -> Lambda incident-notifier
  - Config Rule: guardduty-enabled-centralized, securityhub-enabled
  - RB-004: runbook for GuardDuty findings response
```

### Layer 7 - Audit and Response (CloudTrail + S3 Object Lock + Process)

**What it protects:** Immutable forensic evidence, accountability, legal compliance.

```
Technical trail:
  - CloudTrail: 100% of API calls recorded (cannot be disabled
    without WAYFINDER-003 alerting within 30 minutes)
  - S3 data events: each GET/PUT on health-critical data recorded
  - S3 Object Lock COMPLIANCE: trail cannot be altered or deleted

Incident response:
  - RB-001: incident response process
  - RB-004: GuardDuty findings response
  - LGPD Art. 48 template pre-filled by Lambda audit-reporter
  - Internal SLA: ANPD notification in < 48h (24h buffer from legal deadline)

Incident lesson: CloudTrail active with data events would have recorded
each GetObject from the exposed bucket, allowing exact scope quantification
(how many objects were downloaded and by whom).

Wayfinder monitoring:
  - WAYFINDER-003 (CloudTrail status)
  - WAYFINDER-013 (S3 Object Lock for retention-required)
  - Weekly automatic report via Lambda audit-reporter
```

---

## 4. Layer x Service Mapping

| Layer | AWS Services | Config Rules | Lambda | SNS |
|---|---|---|---|---|
| 1 - Edge | CloudFront, WAF, Route 53, ACM | wafv2-webacl-not-empty | incident-notifier | WARNING |
| 2 - Network | VPC, SG, Endpoints, VPC Flow Logs | vpc-flow-logs-enabled, WAYFINDER-006/009 | auto-remediation | CRITICAL |
| 3 - AuthN/AuthZ | Cognito, IAM, IAM IC, SCPs | WAYFINDER-005/012, iam-root-access-key-check | auto-remediation | CRITICAL/HIGH |
| 4 - Encryption | KMS, ACM, Secrets Manager | WAYFINDER-001/004/007/008/010/014 | auto-remediation | CRITICAL |
| 5 - Compliance | AWS Config, EventBridge | WAYFINDER-001 to 015 | compliance-evaluator | CRITICAL/HIGH/MEDIUM |
| 6 - Threats | GuardDuty, Security Hub, Inspector | guardduty-enabled, securityhub-enabled | incident-notifier | CRITICAL |
| 7 - Audit | CloudTrail, S3 Object Lock, Athena | WAYFINDER-003/013, cloud-trail-enabled | audit-reporter | INFO |

---

## 5. Trade-offs and Costs

### 5.1 Additional Cost of the 7 Layers

| Additional Service | Monthly Cost Prod | Monthly Cost Dev |
|---|---|---|
| GuardDuty | $15 | $1.25 |
| Security Hub | $3.50 | $0.75 |
| Inspector v2 | $4.50 | $0.09 |
| AWS Config (additional) | $8 (new rules) | $3 |
| VPC Endpoints (10 interface) | $72 | $14.40 |
| **Total additional layers** | **~$103/month** | **~$20/month** |

### 5.2 March Incident Cost vs Prevention Cost

```
Cost of the March incident: R$ 2,107,000 (estimated)
Annual cost of 7 layers (prod): ~$103/month x 12 = $1,236/year  = R$ 6,180/year
Annual cost of 7 layers (dev):  ~$20/month x 12  = $240/year    = R$ 1,200/year

Defense in Depth ROI:
  Investment: R$ 7,380/year
  Avoided cost (1 similar incident): R$ 2,107,000
  ROI: 285x (28,500%)

Decision: cost-benefit widely justifies the investment.
```

### 5.3 Operational Impact

| Aspect | Impact | Mitigation |
|---|---|---|
| Additional latency (WAF) | +2-5ms per request | Irrelevant for health application |
| Development overhead | +10% resource setup time | Pre-configured Terraform modules |
| Alert false positives | Risk of alert fatigue | Rule tuning + tag-based suppression |
| Storage cost (audit trail) | +$11/month (500GB/5 years) | S3 Intelligent-Tiering reduces cost |

---

## 6. Consequences

**Positive:**
- Any failure in a layer is detected and corrected automatically (layers 1-6)
- Immutable forensic evidence for any future incident (layer 7)
- LGPD Art. 46 compliance ("technical and administrative measures") demonstrated
- Foundation for ISO 27001 certification (controls A.8.20, A.8.21, A.8.24, A.5.15)
- The March incident with Wayfinder active: 0 data exposed instead of 2,340 reports

**Negative:**
- Additional cost of ~$103/month in prod (justified by demonstrated ROI)
- Greater architectural complexity - mitigated by IaC and documentation
- Development team must consider the 7 layers when creating new resources

**Success metrics:**
- Zero health data exposure incidents for 12 months
- P99 compliance deviation detection < 5 minutes
- FSBP score > 85% and CIS > 80% in production
- 100% of resources with the 5 required tags
