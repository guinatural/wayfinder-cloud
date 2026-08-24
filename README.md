# Wayfinder Cloud

**Cloud governance and compliance platform for regulated AWS environments.**

> "As Wayfinders chart precise routes through unknown regions of space,
> Wayfinder Cloud guides AWS infrastructure through the complexities of
> LGPD, ensuring visibility, immutable auditability, and real-time
> auto-remediation."

---

## Overview

Wayfinder Cloud is a cloud governance platform for AWS environments in
regulated sectors, with an initial focus on **digital health** under the
requirements of **LGPD (Lei 13.709/2018)**.

The project demonstrates the capabilities of a Solutions Architect to:

- Design an event-driven architecture for continuous compliance
- Implement multi-layer observability (infrastructure, application, security)
- Connect AWS technical controls to real legal obligations (LGPD arts. 46, 48, 49)
- Automate remediation of compliance deviations without manual intervention
- Provision infrastructure as code with Terraform following AWS best practices
- Document architectural decisions with professional ADRs

---

## Business Problem

**Fictional company:** VitaCore Health — a digital health startup processing
electronic medical records, imaging reports, and wearable data for
~127,000 active patients across three Brazilian states.

**The March 2026 Incident:**

A junior developer accidentally disabled Block Public Access on the wrong
S3 bucket while configuring a static website. A bucket containing 2,340
imaging reports (X-ray, CT, MRI) became publicly accessible.

No one noticed for 18 days. The issue was discovered by a patient who
found their own CT result via Google.

**Impact:**
- ANPD fine: R$ 420,000 (LGPD art. 52)
- Lost contracts: R$ 1,260,000
- Incident response costs: R$ 427,000
- Total: R$ 2,107,000

**With Wayfinder Cloud active, WAYFINDER-002 would have detected and
remediated the exposure in under 5 minutes.**

| Metric | Without Wayfinder | With Wayfinder |
|---|---|---|
| Time to detect | 18 days | < 5 minutes |
| Auto-remediation | None | Yes (Block Public Access) |
| Audit trail | Unavailable | Immutable (S3 Object Lock) |
| ANPD notification | 67 days late | Template pre-filled < 48h |

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
    |                    13 VPC Interface Endpoints                      |
    |                                                                    |
    |  Private data:     Aurora MySQL (Multi-AZ)                        |
    |                    ElastiCache Redis                               |
    |                    DynamoDB                                        |
    +--------------------------------------------------------------------+

Compliance pipeline:

    AWS Resource changes
        |
        v
    AWS Config (37 rules: 23 managed + 14 custom WAYFINDER-001..014)
        |
        v
    Amazon EventBridge (wayfinder-events bus)
        |
        +---> Lambda compliance-evaluator  --> SNS (CRITICAL/WARNING/INFO)
        |                                  --> Lambda auto-remediation
        |
        +---> CloudTrail --> S3 Object Lock --> Glue --> Athena
        |
        +---> GuardDuty  --> Security Hub (FSBP + CIS 1.4)
```

---

## LGPD Controls Mapping

| LGPD Article | Obligation | AWS Control |
|---|---|---|
| Art. 6, IV - Necessity | Minimum necessary access | IAM Least Privilege, SCPs |
| Art. 37 - Records | Log all data processing operations | CloudTrail multi-region + data events |
| Art. 46 - Security | Technical protection measures | KMS CMK, Config Rules, WAF |
| Art. 48 - Incident notification | Notify ANPD within 72h | SNS + Lambda, alert < 5 min |
| Art. 49 - Secure systems | Security by design | IaC-only provisioning, WAYFINDER rules |
| Art. 50 - Best practices | Governance program | Security Hub FSBP + CIS 1.4 |

Full mapping: [docs/compliance/lgpd-controls-mapping.md](docs/compliance/lgpd-controls-mapping.md)

---

## AWS Well-Architected Review Summary

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
CI/CD:     GitHub Actions    (plan on PR, apply on merge, approval gate for prod)
Docs:      Markdown + ADRs + Mermaid diagrams + Runbooks
```

### AWS Services

| Service | Role in Wayfinder Cloud |
|---|---|
| AWS Config | Continuous compliance sensor - 37 rules |
| Amazon EventBridge | Event routing engine |
| AWS Lambda | Evaluation, remediation, notification, reporting |
| AWS CloudTrail | Immutable audit trail of all API calls |
| Amazon CloudWatch | Metrics, structured logs, alarms, dashboard |
| AWS Security Hub | Consolidated security posture (FSBP + CIS 1.4) |
| Amazon GuardDuty | ML-based threat detection |
| AWS Inspector v2 | Vulnerability scanning (EC2 + ECR) |
| Amazon S3 + Object Lock | Legally immutable audit storage (LGPD chain of custody) |
| Amazon Athena | SQL over audit logs for forensic investigation |
| AWS KMS | Customer Managed Keys per data classification |
| Amazon SNS | Multi-channel alerts (email, Slack) |
| Amazon DynamoDB | Remediation guardrail state (anti-loop) |
| Amazon SQS | Dead Letter Queue for resilience |
| Amazon VPC + Endpoints | Network isolation, zero internet for AWS API traffic |
| AWS Budgets | Cost governance with automated alerts |
| AWS Backup | Centralized backup with Vault Lock |
| AWS Secrets Manager | Credential management with auto-rotation |

---

## Repository Structure

```
wayfinder-cloud/
+-- README.md
+-- CONTRIBUTING.md
+-- LICENSE
+--
+-- docs/
|   +-- adr/                         # 9 Architecture Decision Records
|   +-- architecture/
|   |   +-- architecture-overview.md # Full Mermaid diagram, data flows
|   |   +-- well-architected-review.md
|   |   +-- service-catalog.md       # 35+ AWS services documented
|   +-- compliance/
|   |   +-- lgpd-controls-mapping.md # LGPD articles to AWS controls
|   +-- business/
|   |   +-- vitacore-scenario.md     # Business context, incident post-mortem
|   +-- runbooks/
|       +-- RB-001-incident-response.md
|       +-- RB-002-terraform-operations.md
|       +-- RB-003-compliance-queries.md
|       +-- RB-004-guardduty-findings.md
|       +-- RB-005-cost-governance.md
|
+-- infra/
|   +-- modules/                     # 8 reusable Terraform modules
|   |   +-- networking/
|   |   +-- iam/
|   |   +-- storage/
|   |   +-- notifications/
|   |   +-- compliance/
|   |   +-- observability/
|   |   +-- remediation/
|   |   +-- security/
|   +-- environments/
|       +-- dev/
|       +-- prod/
|
+-- src/
|   +-- lambdas/
|       +-- compliance-evaluator/    # Evaluates NON_COMPLIANT events + LGPD context
|       +-- auto-remediation/        # Executes fixes with guardrails
|       +-- incident-notifier/       # Slack/email alerts
|       +-- audit-reporter/          # Weekly Athena queries + reports
|   +-- tests/
|
+-- scripts/
|   +-- bootstrap_state.py           # Creates S3 + DynamoDB for Terraform state
|
+-- .github/
    +-- workflows/
        +-- terraform-plan.yml       # Plan on PR
        +-- terraform-apply.yml      # Apply on merge (manual approval for prod)
        +-- lambda-deploy.yml        # Test, package, deploy, smoke test
```

---

## Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | Terraform over CDK/CloudFormation | Accepted |
| ADR-002 | Event-driven compliance (vs periodic polling) | Accepted |
| ADR-003 | S3 Object Lock + Athena for immutable audit trail | Accepted |
| ADR-004 | Selective auto-remediation with risk matrix | Accepted |
| ADR-005 | CloudWatch native over DataDog/New Relic | Accepted |
| ADR-006 | Security Hub with FSBP + CIS 1.4 | Accepted |
| ADR-007 | Defense in depth - 7 independent security layers | Accepted |
| ADR-008 | Secrets Manager over hardcoded env vars | Accepted |
| ADR-009 | VPC Endpoints strategy (177x security ROI vs NAT-only) | Accepted |

---

## Quick Start

```bash
# Clone
git clone https://github.com/guinatural/wayfinder-cloud.git
cd wayfinder-cloud

# Configure AWS credentials
aws configure --profile wayfinder-dev

# Bootstrap Terraform state backend (one-time)
python scripts/bootstrap_state.py --env dev --region us-east-1

# Copy and fill variables
cp infra/environments/dev/terraform.tfvars.example \
   infra/environments/dev/terraform.tfvars

# Initialize and apply
cd infra/environments/dev
terraform init
terraform plan
terraform apply
```

Full operations guide: [docs/runbooks/RB-002-terraform-operations.md](docs/runbooks/RB-002-terraform-operations.md)

---

## Cost Estimate

| Environment | Monthly Cost (USD) |
|---|---|
| Dev (governance only) | ~$38 |
| Prod (full VitaCore stack) | ~$870 |
| Annual prevention cost | ~$1,236 |
| Cost of one similar incident | ~$420,000+ |

---

## Author

**Guilherme Barreto Gomes**
AWS Solutions Architect | Cloud Security | LGPD

[GitHub](https://github.com/guinatural)

---

## License

MIT - see [LICENSE](LICENSE) for details.
