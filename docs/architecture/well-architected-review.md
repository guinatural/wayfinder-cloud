# AWS Well-Architected Review - Wayfinder Cloud

**Project:** Wayfinder Cloud - Cloud Governance Platform for Digital Health
**Fictional client:** VitaCore Health
**Date:** 2026-08-21 | **Version:** 2.0
**Reviewer:** Guilherme Barreto Gomes (AWS Solutions Architect)
**Framework:** AWS Well-Architected Framework 2024 - 6 Pillars
**Reference tool:** [AWS Well-Architected Tool](https://console.aws.amazon.com/wellarchitected/)

---

## Executive Summary

| Pillar | Score (0-100) | Maturity | High Risk | Medium Risk |
|---|---|---|---|---|
| Operational Excellence | 72 | Good | 0 | 3 |
| Security | 85 | Strong | 0 | 2 |
| Reliability | 70 | Good | 0 | 4 |
| Performance Efficiency | 68 | Good | 0 | 3 |
| Cost Optimization | 80 | Strong | 0 | 2 |
| Sustainability | 45 | In development | 0 | 3 |
| **Overall** | **70** | **Good** | **0** | **17** |

> Methodology: questions answered based on controls implemented in Terraform.
> Score = (controls implemented / total relevant controls) x 100.

---

## Pillar 1 - Operational Excellence

> "The ability to support development and run workloads effectively, gain insight
> into operations, and continuously improve processes and procedures to deliver
> business value."

**Score: 72/100 | Maturity: Good**

### OPS 1 - How do you determine the business priorities that guide your operations?

**Answer:** The project explicitly maps technical controls to LGPD obligations
(Arts. 46, 48, 50) and business risk (VitaCore incident of R$ 2.1M). Operational
priority is defined by compliance severity: CRITICAL > HIGH > MEDIUM > LOW.

**Implemented controls:**
- LGPD to technical controls mapping in `docs/compliance/lgpd-controls-mapping.md`
- Incident impact matrix documented with estimated avoided cost
- Project OKRs defined in `docs/business/vitacore-scenario.md` (section 4)
- SLAs defined by severity: CRITICAL < 15 min, HIGH < 2h, MEDIUM < 24h

**Gaps (Medium Risk):**
- No business metrics connected to compliance alarms (e.g., "X violations = Y fine risk")
- No onboarding runbook for new team members

### OPS 2 - How do you structure your organization to support your business objectives?

**Answer:** 5 documented personas with clear responsibilities (DPO, CTO, SecOps, Dev Lead, Auditors).
Runbooks RB-001 to RB-005 cover the main operational scenarios.

**Implemented controls:**
- Personas and responsibilities in `docs/business/vitacore-scenario.md` (section 5)
- RB-001: LGPD Art. 48 incident response
- RB-002: Terraform operations (bootstrap, plan, apply, rollback)
- RB-003: Athena queries for forensic investigation
- RB-004: GuardDuty findings response
- RB-005: Cost governance

### OPS 3 - How do you design your workload to understand its state?

**Answer:** All Lambdas emit structured JSON logs compatible with
CloudWatch Logs Insights. Custom metrics in the `Wayfinder/Compliance` namespace
enable dashboards and alarms about compliance state.

**Implemented controls:**
- Structured logging (JSON) in compliance-evaluator, auto-remediation, incident-notifier, audit-reporter
- CloudWatch custom metrics: `NonCompliantResource`, `ComplianceScore`, `RemediationAttempt`
- AWS X-Ray tracing on critical Lambdas (5% sampling + 100% on errors)
- CloudWatch Dashboard "Wayfinder Command Center" with 12 widgets
- Multi-region CloudTrail captures 100% of API calls

### OPS 4 - How do you reduce defects, ease remediation, and improve flow in production?

**Implemented controls:**
- 100% IaC Terraform - no manual changes to managed resources
- GitHub Actions: `terraform-plan.yml` blocks merge without approved plan
- `terraform-apply.yml`: pipeline dev -> approval -> prod
- Conventional Commits as history standard
- ADR-001 to ADR-009 document all relevant decisions

**Gaps (Medium Risk):**
- No automated `terraform test` on modules
- Python unit tests created but without integration coverage

### OPS 5 - How do you mitigate deployment risks?

**Implemented controls:**
- Separate environments: dev (force_destroy=true, GOVERNANCE) / prod (COMPLIANCE)
- GitHub Environments with required reviewer for prod
- `terraform plan` exposed as PR comment before any apply
- Lambda deploy separate from Terraform (lambda-deploy.yml)
- Automatic smoke test after each Lambda deploy

### OPS 6 - How do you understand operational events that affect your workload?

**Implemented controls:**
- CloudWatch Alarms: 3 critical alarms + 5 warnings
- SNS 3 topics with documented response SLAs
- AWS Chatbot integrates with Slack for real-time alerts
- GuardDuty findings -> EventBridge -> Lambda incident-notifier (< 2 min)
- Config NON_COMPLIANT -> EventBridge -> compliance-evaluator (< 5 min)

**Gaps (Medium Risk):**
- No Game Day runbook (incident simulation to test alerts)

---

## Pillar 2 - Security

> "The ability to protect data, systems, and assets to take advantage of cloud
> technologies and improve your security posture."

**Score: 85/100 | Maturity: Strong**

### SEC 1 - How do you manage identities for people and machines?

**Answer:** IAM Identity Center (SSO) for humans, IAM Roles with least privilege for machines.
No IAM Users with long-lived access keys for services (only for CI/CD temporarily).

**Implemented controls:**
- Separate IAM Roles per function: evaluator, remediation, reporter, config
- No `AdministratorAccess` in production (WAYFINDER-005 detects)
- IAM Identity Center (SSO) via Google Workspace for human access
- Mandatory MFA for console (Config Rule `mfa-enabled-for-iam-console-access`)
- Root account: no access keys (Config Rule `iam-root-access-key-check`)
- WAYFINDER-012: access keys rotated every 90 days
- SCPs: `deny-root-account-actions`, `require-mfa-for-console`

**Gaps (Medium Risk):**
- CI/CD still uses static access keys - migrate to OIDC + IAM Role

### SEC 2 - How do you manage permissions for people and machines?

**Implemented controls:**
- `data "aws_iam_policy_document"` with conditions where possible (`aws:ResourceAccount`, `cloudwatch:namespace`)
- SCP `require-encryption-at-rest` applies encryption as an account-level condition
- Resource-based policies on S3 with `DenyNonTLS` and `AllowOnlyAccount`
- Permission Boundaries documented for development team
- WAYFINDER-005 detects `Action: "*", Resource: "*"` in any policy

### SEC 3 - How do you detect and investigate security events?

**Implemented controls:**
- CloudTrail multi-region + log file validation (SHA-256)
- CloudTrail data events for S3 (all GET/PUT on health-* buckets)
- GuardDuty: CloudTrail + VPC Flow Logs + DNS Logs + S3 protection
- Security Hub: FSBP v1.0 + CIS 1.4 with target score > 85%
- Inspector v2: CVEs on EC2 and ECR (continuous scanning)
- Config + EventBridge: detection in < 5 min of any configuration change
- RB-004: documented procedure for each GuardDuty finding family
- RB-003: ready-to-use Athena queries for forensic investigation

### SEC 4 - How do you protect your networks?

**Implemented controls:**
- VPC with 3 subnet layers: public (ALB/NAT) / private app (ECS/Lambda) / private data (RDS/Redis)
- Security Groups with least privilege: sg-alb -> sg-app -> sg-data (no egress on sg-data)
- VPC Endpoints: 13 Interface + 2 Gateway - no sensitive data traffic via internet
- VPC Flow Logs enabled (Config Rule `vpc-flow-logs-enabled`)
- AWS WAF: OWASP Top 10, rate limiting, SQL Injection, Known Bad Inputs
- CloudFront as origin shield + automatic DDoS Layer 3/4
- WAYFINDER-009: Security Group with public SSH/RDP detected and remediated
- WAYFINDER-006: EC2 with health data in public subnet -> automatic quarantine
- ADR-009: VPC Endpoints strategy with cost-benefit analysis

### SEC 5 - How do you protect your compute resources?

**Implemented controls:**
- ECS Fargate: no OS management, automatic patches by AWS
- Inspector v2: CVE vulnerabilities on ECR images and EC2
- ECR: image scanning on push, lifecycle policy (keep 10 latest)
- Systems Manager Session Manager: no SSH/Bastion Host needed
- WAYFINDER-011: ECS Task with `privileged=true` detected

**Gaps (Medium Risk):**
- No Patch Manager configured for EC2 (if any)
- No AWS Shield Advanced (cost $3,000/month - roadmap for scale)

### SEC 6 - How do you classify your data?

**Implemented controls:**
- 5 classification levels: health-critical, health-standard, financial-sensitive, operational, public
- Mandatory `DataClassification` tags via SCP and WAYFINDER-015
- KMS CMK per classification: 5 dedicated keys
- S3 Object Lock COMPLIANCE for health-critical data (retention 20 years / CFM)
- Different technical controls per level (documented in lgpd-controls-mapping.md)

### SEC 7 - How do you protect your data at rest?

**Implemented controls:**
- S3: SSE-KMS with dedicated CMK per classification + `bucket_key_enabled=true`
- Aurora MySQL: StorageEncrypted=true + KMS CMK (WAYFINDER-004)
- DynamoDB: SSE with CMK (WAYFINDER-010)
- ElastiCache Redis: at-rest + in-transit encryption
- CloudWatch Logs: KMS CMK (WAYFINDER-008)
- SQS DLQ: KMS
- SNS Topics: KMS
- Annual KMS key rotation enabled on all CMKs (CIS 3.8)
- Managed Rule `encrypted-volumes`: encrypted EBS

### SEC 8 - How do you protect your data in transit?

**Implemented controls:**
- TLS 1.3 on CloudFront and ALB (TLS 1.2 minimum)
- S3 bucket policy: `DenyNonTLS` blocks HTTP
- VPC Endpoints: AWS API traffic never leaves the AWS network
- Aurora: `enforce_ssl=1` in parameter group
- ElastiCache: `in-transit-encryption=true`
- Lambda to AWS services: HTTPS required via default SDK

### SEC 9 - How do you anticipate, respond to, and recover from incidents?

**Implemented controls:**
- RB-001: complete 6-phase process (detection -> ANPD in 48h)
- Automatic pipeline: Config/GuardDuty -> Lambda -> SNS/remediation in < 5 min
- ANPD communication template pre-filled by audit-reporter
- Runbook RB-004 per GuardDuty finding family
- S3 Object Lock ensures preservation of forensic evidence

**Gaps (Medium Risk):**
- No documented Game Day (LGPD incident simulation)
- Individual data subject notification process (LGPD Art. 48) not automated

---

## Pillar 3 - Reliability

> "The ability of a workload to perform its intended function correctly and
> consistently when it is expected to."

**Score: 70/100 | Maturity: Good**

### REL 1 - How do you manage service limits?

**Implemented controls:**
- Lambda concurrency: no explicit reservation (account burst limit)
- DynamoDB PAY_PER_REQUEST: no throttling from provisioning
- Config Rules: limit of 300 rules - project uses ~37 (12%)
- EventBridge: limit of 300 rules per bus - project uses ~8 (< 3%)

**Gaps (Medium Risk):**
- No Service Quotas Alerts configured for Lambda concurrency and Config rules
- No Kinesis shard limit analysis for wearable volume

### REL 2 - How do you plan your network topology?

**Implemented controls:**
- VPC with 2 AZs: us-east-1a and us-east-1b
- Subnets per tier: public / private-app / private-data
- IGW + NAT GW: controlled connectivity
- VPC Endpoints: eliminates internet dependency for AWS APIs
- Separate route tables per subnet tier

**Gaps (Medium Risk):**
- Single-AZ NAT Gateway in dev (intentional) - prod uses dual-AZ
- No IP exhaustion analysis on CIDRs (10.0.0.0/24 = 251 hosts/subnet)

### REL 3 - How do you design your workload to withstand failures?

**Implemented controls:**
- ECS Fargate: tasks distributed across 2 AZs with ALB health checks
- Aurora Multi-AZ: writer us-east-1a + reader us-east-1b, failover < 30s
- ElastiCache Redis: primary + replica in different AZs
- SQS DLQ: compliance events are not lost even if Lambda fails
- EventBridge automatic retry (up to 24h for undelivered events)
- Stateless Lambdas: any failure is idempotent, no side effects
- DynamoDB: Global Table option available for multi-region DR

**Gaps (Medium Risk):**
- No circuit breaker between compliance-evaluator and SNS
- No documented Aurora failover test

### REL 4 - How do you design your workload to recover from failures?

**Implemented controls:**
- AWS Backup: Aurora (daily/weekly/monthly), DynamoDB (PITR 35d), Vault Lock
- S3 Object Lock + versioning: recovery of deleted objects
- Terraform state on S3 with versioning: infra rollback possible
- Lambda DLQ + `terraform apply` = compliance pipeline recovery

**Gaps (Medium Risk):**
- RTO/RPO not formally defined per component
- No DR plan for complete us-east-1 region (future: us-east-2 failover)
- Aurora restore test not documented in runbook

### REL 5 - How do you monitor your workload?

**Implemented controls:**
- CloudWatch Alarms: noncompliant_critical, noncompliant_high_volume, evaluator_errors
- SNS alerts to CTO, DPO, and SecOps with defined response SLA
- CloudWatch Logs Insights: pre-built queries in RB-003
- X-Ray: service map and traces for debugging the pipeline

---

## Pillar 4 - Performance Efficiency

> "The ability to use computing resources efficiently to meet system requirements
> and to maintain that efficiency as demand changes."

**Score: 68/100 | Maturity: Good**

### PERF 1 - How do you select the best performing architecture?

**Answer:** Serverless event-driven architecture eliminates polling and processes events
only when they occur. Choice validated in ADR-002 with detection latency comparison
(< 2 min event-driven vs up to 5 min periodic polling).

**Implemented controls:**
- ADR-002: event-driven vs polling - documented detection latency
- Lambda Python 3.12: latest runtime, lower cold start
- DynamoDB PAY_PER_REQUEST: no over-provisioning
- EventBridge: asynchronous processing without blocking

### PERF 2 - How do you select and use compute resources?

**Implemented controls:**
- Lambda memory sizing per function: 256MB (evaluator), 128MB (notifier), 512MB (reporter)
- ECS Fargate: 0.5 vCPU/1GB per task (based on profiling)
- Aurora db.r6g.large (prod) / db.t4g.medium (dev): documented rightsizing
- X-Ray: profiling available to identify bottlenecks per function

**Gaps (Medium Risk):**
- No documented cold start benchmark per Lambda
- No Lambda Power Tuning run for memory/cost optimization

### PERF 3 - How do you select your data storage?

**Implemented controls:**
- Aurora MySQL: relational for records with complex JOINs (vs DynamoDB)
- DynamoDB: NoSQL for wearables with variable schema per device
- ElastiCache Redis: in-memory for sessions and frequent query cache
- S3: object storage for immutable logs and imaging reports
- S3 Bucket Key: reduces KMS overhead by ~99% (performance + cost)
- Athena + Parquet via Glue: efficient queries on historical logs

### PERF 4 - How do you select and use networking resources?

**Implemented controls:**
- CloudFront: static asset cache reduces global latency
- VPC Endpoints: eliminates NAT Gateway latency for AWS calls (< 1ms vs ~10ms)
- ALB: load balancing based on health checks every 10s

**Gaps (Medium Risk):**
- No documented latency analysis between ECS and Aurora
- No Connection Pooling configuration on Aurora (RDS Proxy as option)

### PERF 5 - How do you optimize performance over time?

**Implemented controls:**
- Lambda audit-reporter: weekly report includes pipeline performance metrics
- CloudWatch Dashboard: duration and invocations visible per Lambda

**Gaps (Medium Risk):**
- No formal quarterly performance review process
- Lambda Provisioned Concurrency not evaluated for compliance-evaluator in prod

---

## Pillar 5 - Cost Optimization

> "The ability to run systems to deliver business value at the lowest price point."

**Score: 80/100 | Maturity: Strong**

### COST 1 - How do you implement cloud financial management?

**Implemented controls:**
- Mandatory tags on all resources via `default_tags` on provider (WAYFINDER-015)
- AWS Budgets: total budget (80%/100%/120% forecast) + compute/DB budget (70%/100%)
- Cost Explorer enabled with analysis by `Project` and `CostCenter` tags
- RB-005: weekly cost analysis process with Athena queries
- Dev/prod separation: filter by `Environment` tag in Cost Explorer

### COST 2 - How do you govern usage?

**Implemented controls:**
- IaC Terraform: no ad-hoc provisioning - cost always approved in PR
- WAYFINDER-015: resources without required tags detected
- GitHub Actions: `terraform plan` exposes incremental cost before apply

### COST 3 - How do you monitor usage and costs?

**Implemented controls:**
- AWS Budgets with SNS alerts: WARNING at 80%, CRITICAL at 100%
- RB-005 Query 6.4: NAT Gateway cost analysis (largest variable item)
- RB-005 Query 6.5: S3 cost per bucket
- Lambda audit-reporter: weekly cost included in Board report

### COST 4 - How do you decommission resources?

**Implemented controls:**
- S3 lifecycle: Standard -> Glacier after 90 days, expiration by data type
- CloudWatch Logs: retention configured (90 days Lambdas, 365 days CloudTrail)
- `force_destroy = true` in dev: easy destroy without residues
- ECR lifecycle: keep 10 latest, expire untagged after 30 days

**Gaps (Medium Risk):**
- No automation for stopping/starting dev resources outside business hours

### COST 5 - How do you select the correct resource type and size?

**Implemented controls:**
- Lambda serverless: charges only per ms of execution
- DynamoDB PAY_PER_REQUEST: no over-provisioning
- ECS Fargate: no idle instances
- NAT Gateway: 1 per AZ in prod, 1 total in dev
- VPC Gateway Endpoints S3 and DynamoDB: free (vs paid Interface Endpoints)
- RB-005: rightsizing process with documented criteria (CPU < 10% for 7d)
- S3 Bucket Key: -99% KMS requests cost
- ADR-009: VPC Endpoints vs NAT-only cost analysis (177x ROI in security)

**Documented monthly cost estimate:**
- Dev: ~$38/month (Wayfinder module isolated)
- Prod full VitaCore: ~$870/month (application + governance)

---

## Pillar 6 - Sustainability

> "The ability to continually improve sustainability impacts by reducing energy
> consumption and increasing efficiency across all components of a workload."

**Score: 45/100 | Maturity: In development**

### SUS 1 - How do you choose Regions to support your sustainability goals?

**Answer:** `us-east-1` was chosen for latency requirements for Brazilian users
(via CloudFront) and for being the region with the widest AWS service coverage.
The percentage of renewable energy in the region was not evaluated.

**Implemented controls:**
- Serverless architecture eliminates idle servers (biggest sustainability factor)

**Gaps (Medium Risk):**
- `us-east-1` is not the region with the highest % of renewable energy (Oregon/Frankfurt have more)
- No AWS Customer Carbon Footprint Tool analysis

### SUS 2 - How do you align to user demand targets?

**Implemented controls:**
- Lambda executes only with real events - zero consumption at idle
- DynamoDB PAY_PER_REQUEST: resources allocated only when there is demand
- EventBridge + Lambda vs dedicated servers: ~95% fewer compute resources
- S3 lifecycle: data moved to Glacier (lower energy per stored byte)

### SUS 3 - How do you maximize resource utilization?

**Implemented controls:**
- ECS Fargate: automatic bin-packing by AWS
- Lambda memory optimized per function (no over-provisioning)
- ElastiCache Redis: reduces Aurora load by 60% for repeated queries
- CloudFront cache: reduces origin requests (~70% hit rate expected)

**Gaps (Medium Risk):**
- No Compute Optimizer enabled for rightsizing analysis
- No Graviton (ARM) analysis for ECS tasks and RDS (db.r7g vs db.r6g)

### SUS 4 - How do you anticipate and adopt new efficient offerings?

**Implemented controls:**
- Python 3.12: more efficient runtime than previous versions
- Terraform ~> 5.0: updated provider
- Aurora MySQL (vs self-managed MySQL): more efficient on shared hardware

**Gaps (Medium Risk):**
- No Graviton migration plan (potential -20% energy and -10% cost)
- No formal sustainability policy documented

---

## Prioritized Improvement Plan

| # | Pillar | Improvement | Effort | Impact | Risk Mitigated |
|---|---|---|---|---|---|
| 1 | Security | Migrate CI/CD from access keys to OIDC + IAM Role | Low | High | SEC-1 |
| 2 | Operational | Create Game Day runbook (incident simulation) | Medium | High | OPS-6, SEC-9 |
| 3 | Reliability | Formally define RTO/RPO per component | Low | Medium | REL-4 |
| 4 | Operational | Add `terraform test` to modules (TF 1.6+) | Medium | Medium | OPS-4 |
| 5 | Performance | Run Lambda Power Tuning (open source) | Low | Medium | PERF-2 |
| 6 | Reliability | Document and test Aurora restore | Low | High | REL-4 |
| 7 | Security | Enable GuardDuty EKS and Lambda protection | Low | Medium | SEC-3 |
| 8 | Cost | Evaluate Graviton for Aurora and ECS | Medium | Medium | COST-5 |
| 9 | Sustainability | Enable AWS Compute Optimizer | Low | Medium | SUS-3 |
| 10 | Sustainability | Run Customer Carbon Footprint Tool | Low | Low | SUS-1 |

---

## AWS Official References

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Well-Architected Tool](https://console.aws.amazon.com/wellarchitected/)
- [Security Pillar Whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html)
- [Reliability Pillar Whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html)
- [Operational Excellence Pillar](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)
- [Performance Efficiency Pillar](https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html)
- [Cost Optimization Pillar](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html)
- [Sustainability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html)
- [AWS Foundational Security Best Practices](https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html)
- [CIS AWS Foundations Benchmark v1.4](https://www.cisecurity.org/benchmark/amazon_web_services)

---

## Next Review

**Suggested date:** 2027-02-21 (6 months after prod deploy)

**Triggers for early review:**
- CRITICAL security incident in prod
- Significant architectural change (e.g., multi-region)
- Cost increase > 50% month over month for 2 months
- Obtaining ISO 27001 certification (new controls)
- FSBP score falls below 80% for 2 consecutive weeks
