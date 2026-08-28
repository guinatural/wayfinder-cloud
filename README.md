# Wayfinder Cloud

Cloud governance and compliance platform for regulated AWS environments.

---

> "As Wayfinders chart precise routes through unknown regions of space,
> Wayfinder Cloud guides AWS infrastructure through LGPD complexity,
> ensuring visibility, immutable audit trails, and real-time auto-remediation."

---

## Overview

Wayfinder Cloud is a cloud governance platform built for AWS environments
in regulated sectors. The initial focus is **digital health** under
**LGPD (Brazilian Data Protection Law - Lei 13.709/2018)**.

This project demonstrates a Solutions Architect's ability to:

- Design event-driven architecture for continuous compliance monitoring
- Connect AWS technical controls to real legal obligations (LGPD)
- Automate remediation of security deviations without manual intervention
- Provision infrastructure as code with Terraform following AWS best practices
- Document every architectural decision with professional ADRs

---

## The Business Problem

**VitaCore Health** is a fictional digital health startup processing
electronic medical records, imaging reports, and wearable data for
127,000 active patients across three Brazilian states.

**The March 2026 Incident:**

A junior developer accidentally disabled Block Public Access on the wrong
S3 bucket while configuring a static website. A bucket containing
2,340 imaging reports became publicly accessible. Nobody noticed for 18 days.
A patient discovered their own CT scan result via Google.

**Financial impact: R$ 2,107,000 in fines and lost contracts.**

| | Without Wayfinder | With Wayfinder |
|---|---|---|
| Time to detect | 18 days | under 5 minutes |
| Auto-remediation | None | Yes (Block Public Access) |
| Audit trail | Unavailable | Immutable for 5 years |
| ANPD notification | 67 days late | Pre-filled template ready in 48h |
| Financial impact | R$ 2,107,000 | R$ 0 |

---

## Architecture

```
Internet
    |
    Route 53 --> CloudFront --> AWS WAF --> ALB
                                            |
    +------- VPC 10.0.0.0/16 ------------------------------------------+
    |                                                                    |
    |  Public subnets:   ALB, NAT Gateways                              |
    |                                                                    |
    |  Private app:      ECS Fargate (VitaCore API)                     |
    |                    Lambda functions (Wayfinder governance)         |
    |                    13 VPC Interface Endpoints (no internet for AWS)|
    |                                                                    |
    |  Private data:     Aurora MySQL Multi-AZ (patient records)        |
    |                    ElastiCache Redis (sessions and cache)          |
    |                    DynamoDB (wearable data and guardrails)         |
    +--------------------------------------------------------------------+

Compliance pipeline:

    AWS resource changes
        |
        v
    AWS Config (37 rules: 23 managed + 14 custom WAYFINDER-001..014)
        |
        v
    Amazon EventBridge (wayfinder-events bus)
        |
        +---> Lambda compliance-evaluator --> SNS (CRITICAL / WARNING / INFO)
        |                                 --> Lambda auto-remediation
        |
        +---> CloudTrail --> S3 Object Lock --> Glue --> Athena
        |
        +---> GuardDuty + Security Hub (FSBP + CIS 1.4)
```

---

## LGPD Controls Mapping

Each AWS technical control is mapped to a specific LGPD article.

| LGPD Article | Obligation | AWS Control |
|---|---|---|
| Art. 6, IV - Necessity | Minimum necessary access only | IAM Least Privilege, SCPs |
| Art. 37 - Records | Log all data processing operations | CloudTrail multi-region + S3 data events |
| Art. 46 - Security | Technical protection measures | KMS CMK, 37 Config Rules, WAF |
| Art. 48 - Incident notification | Notify ANPD within 72 hours | SNS + Lambda, alert in under 5 min |
| Art. 49 - Secure systems | Security by design, not added later | IaC-only provisioning, WAYFINDER rules |
| Art. 50 - Best practices | Documented governance program | Security Hub FSBP + CIS 1.4 |

Full mapping: [docs/compliance/lgpd-controls-mapping.md](docs/compliance/lgpd-controls-mapping.md)

---

## The 14 WAYFINDER Rules

Custom AWS Config Rules built specifically for VitaCore's compliance requirements.

| Rule | Description | Auto-fix |
|---|---|---|
| WAYFINDER-001 | S3 health data without KMS CMK encryption | Yes |
| WAYFINDER-002 | S3 health data with public access enabled (March incident direct cause) | Yes |
| WAYFINDER-003 | CloudTrail disabled (was off for 43 days unnoticed at VitaCore) | Yes |
| WAYFINDER-004 | RDS without encryption at rest | No |
| WAYFINDER-005 | IAM with admin permissions (Action: *) | No |
| WAYFINDER-006 | EC2 with health data in public subnet | Yes |
| WAYFINDER-007 | Credentials pattern found in Lambda environment variables | No |
| WAYFINDER-008 | CloudWatch Logs without KMS encryption | Yes |
| WAYFINDER-009 | Security Group with SSH or RDP open to internet | Yes |
| WAYFINDER-010 | DynamoDB without encryption at rest | No |
| WAYFINDER-011 | ECS Task with privileged=true | No |
| WAYFINDER-012 | IAM Access Key older than 90 days without rotation | No |
| WAYFINDER-013 | S3 without Object Lock for legally required retention data | No |
| WAYFINDER-014 | Secrets Manager not used (possible hardcoded credentials) | No |

---

## AWS Well-Architected Review

Scored against the AWS Well-Architected Framework 2024 (6 pillars).

| Pillar | Score | Status |
|---|---|---|
| Operational Excellence | 72/100 | Good |
| Security | 85/100 | Strong |
| Reliability | 70/100 | Good |
| Performance Efficiency | 68/100 | Good |
| Cost Optimization | 80/100 | Strong |
| Sustainability | 45/100 | In development |

Full review: [docs/architecture/well-architected-review.md](docs/architecture/well-architected-review.md)

---

## Technology Stack

```
IaC:       Terraform >= 1.6  (remote state: S3 + DynamoDB lock)
Runtime:   Python 3.12       (Lambdas with type hints, structured logging, X-Ray)
CI/CD:     GitHub Actions    (plan on PR, apply on merge, manual approval for prod)
Docs:      Markdown + ADRs + Mermaid diagrams + Operational Runbooks
```

---

## Repository Structure

```
wayfinder-cloud/
+-- README.md
+-- CONTRIBUTING.md
+-- LICENSE
+--
+-- docs/
|   +-- adr/                          # 9 Architecture Decision Records
|   +-- architecture/
|   |   +-- architecture-overview.md  # Full Mermaid diagram and data flows
|   |   +-- well-architected-review.md
|   |   +-- service-catalog.md        # 35+ AWS services with technical justification
|   +-- compliance/
|   |   +-- lgpd-controls-mapping.md  # LGPD articles mapped to AWS controls
|   +-- business/
|   |   +-- vitacore-scenario.md      # Full incident post-mortem and business context
|   +-- runbooks/
|       +-- RB-001-incident-response.md
|       +-- RB-002-terraform-operations.md
|       +-- RB-003-compliance-queries.md
|       +-- RB-004-guardduty-findings.md
|       +-- RB-005-cost-governance.md
|
+-- infra/
|   +-- modules/                      # 8 reusable Terraform modules
|   |   +-- networking/               # VPC, subnets, NAT, VPC Endpoints
|   |   +-- iam/                      # Roles with least privilege per function
|   |   +-- storage/                  # KMS CMK + S3 with Object Lock
|   |   +-- notifications/            # SNS Topics + AWS Chatbot Slack
|   |   +-- compliance/               # Config Recorder + 37 Rules
|   |   +-- observability/            # CloudTrail, EventBridge, Lambda, CloudWatch
|   |   +-- remediation/              # Auto-remediation Lambda + DynamoDB guardrail
|   |   +-- security/                 # GuardDuty, Security Hub, Inspector, Budgets
|   +-- environments/
|       +-- dev/                      # Object Lock GOVERNANCE, force_destroy=true
|       +-- prod/                     # Object Lock COMPLIANCE, manual approval required
|
+-- src/
|   +-- lambdas/
|   |   +-- compliance-evaluator/     # Evaluates events and adds LGPD context
|   |   +-- auto-remediation/         # Executes fixes with guardrails
|   |   +-- incident-notifier/        # Formats and sends Slack and email alerts
|   |   +-- audit-reporter/           # Weekly Athena queries and reports
|   +-- tests/
|
+-- scripts/
|   +-- bootstrap_state.py            # One-time Terraform state backend setup
|
+-- .github/
    +-- workflows/
        +-- terraform-plan.yml        # Plan on every PR, posts result as comment
        +-- terraform-apply.yml       # Deploy pipeline with dev to prod approval gate
        +-- lambda-deploy.yml         # Test, package, deploy, smoke test per Lambda
```

---

## Architecture Decision Records

Every significant architectural choice is documented with context,
options considered, the decision made, and trade-offs accepted.

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | Terraform over CDK and CloudFormation | Accepted |
| ADR-002 | Event-driven compliance over periodic polling | Accepted |
| ADR-003 | S3 Object Lock COMPLIANCE mode + Athena for audit trail | Accepted |
| ADR-004 | Selective auto-remediation with risk matrix | Accepted |
| ADR-005 | CloudWatch native over DataDog and New Relic | Accepted |
| ADR-006 | Security Hub with FSBP and CIS 1.4 standards | Accepted |
| ADR-007 | Defense in depth with 7 independent security layers | Accepted |
| ADR-008 | Secrets Manager after hardcoded credentials found post-incident | Accepted |
| ADR-009 | VPC Endpoints strategy providing 177x security ROI vs NAT-only | Accepted |

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/guinatural/wayfinder-cloud.git
cd wayfinder-cloud

# Configure AWS credentials
aws configure --profile wayfinder-dev

# Bootstrap Terraform state backend (one-time only)
python scripts/bootstrap_state.py --env dev --region us-east-1

# Copy and fill in your variables
cp infra/environments/dev/terraform.tfvars.example \
   infra/environments/dev/terraform.tfvars

# Initialize and apply
cd infra/environments/dev
terraform init
terraform plan
terraform apply
```

Operations guide: [docs/runbooks/RB-002-terraform-operations.md](docs/runbooks/RB-002-terraform-operations.md)

---

## Cost Estimate

| Environment | Monthly (USD) |
|---|---|
| Dev - governance only | ~$38 |
| Prod - full VitaCore stack | ~$870 |
| Annual prevention cost | ~$1,236 |
| Cost of one similar incident | ~$420,000 |
| Return on investment | 340x |

---

## Author

**Guilherme Barreto Gomes**

AWS Solutions Architect | Cloud Security | LGPD

[GitHub](https://github.com/guinatural)

---

## License

MIT - see [LICENSE](LICENSE) for details.
