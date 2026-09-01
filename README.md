# Wayfinder Cloud

A cloud governance project I built to study AWS architecture through a real problem.

---

## Why I built this

I was finishing the AWS Solutions Architect training and had completed 23 hands-on labs.
Each lab taught one piece: KMS encryption, VPC security groups, event-driven pipelines,
CloudTrail logging. But none of them asked me to combine everything with a reason behind it.

So I built something that forced me to make real decisions.

The scenario I used: a digital health company called VitaCore Health.
In March 2026, a developer ran one wrong AWS CLI command.
An S3 bucket with 2,340 patient imaging reports went public.
Nobody caught it for 18 days. A patient found their own CT scan via Google.
The ANPD fine was R$ 420,000. Lost contracts added another R$ 1.6M.

If I had finished this project before March, that would not have happened.
The rule I call WAYFINDER-002 detects that exact misconfiguration in under 5 minutes
and fixes it without anyone needing to do anything.

That is the project.

---

## What it does

Wayfinder Cloud continuously monitors an AWS account for security and compliance
violations, maps each violation to a LGPD article, auto-remediates the ones that
are safe to fix automatically, and keeps a legally immutable audit trail.

```
AWS resource changes
    |
    v
AWS Config evaluates 37 rules (23 AWS managed + 14 I wrote)
    |
    v
EventBridge routes the violation by severity
    |
    +---> Lambda compliance-evaluator
              |
              +---> SNS alert (email + Slack)
              |
              +---> Lambda auto-remediation (for reversible violations)
              |
              +---> CloudTrail --> S3 Object Lock --> Athena
                    (immutable audit trail, queryable with SQL)
```

---

## The 14 custom rules I wrote (WAYFINDER series)

Each one was written for a specific LGPD requirement.
I did not start from the AWS service. I started from what the law requires.

| Rule | What it catches | LGPD article |
|---|---|---|
| WAYFINDER-001 | S3 bucket with health data and no KMS CMK | Art. 46 |
| WAYFINDER-002 | S3 bucket with health data and public access on | Art. 46 |
| WAYFINDER-003 | CloudTrail disabled (happened for 43 days at VitaCore) | Art. 37, 48 |
| WAYFINDER-004 | RDS instance without encryption at rest | Art. 46 |
| WAYFINDER-005 | IAM policy with Action:* and Resource:* | Art. 6, 47 |
| WAYFINDER-006 | EC2 with health data tag sitting in a public subnet | Art. 46, 49 |
| WAYFINDER-007 | Lambda env variable that looks like a hardcoded password | Art. 46 |
| WAYFINDER-008 | CloudWatch log group without KMS encryption | Art. 46 |
| WAYFINDER-009 | Security Group with SSH or RDP open to 0.0.0.0/0 | Art. 46 |
| WAYFINDER-010 | DynamoDB table without encryption | Art. 46 |
| WAYFINDER-011 | ECS task definition with privileged=true | Art. 49 |
| WAYFINDER-012 | IAM access key older than 90 days | Art. 47 |
| WAYFINDER-013 | S3 without Object Lock when retention tag is set | CFM + Art. 37 |
| WAYFINDER-014 | Resource with health data tag but no Secrets Manager reference | Art. 46 |

Rules that auto-remediate: 001, 002, 003, 006, 008, 009.
The rest send an alert. Auto-remediating IAM permissions or RDS encryption
without human review can cause worse problems than the original violation.
I documented that reasoning in ADR-004.

---

## Architecture decisions I had to make

Every major decision is in a separate file under docs/adr/.
Short version of the nine decisions:

**Why Terraform and not CDK:** CDK generates CloudFormation under the hood.
I wanted to understand what is actually deployed, not what an abstraction generates.
Also shows up in more PJ job listings in Brazil.

**Why event-driven and not scheduled polling:** A scheduled Lambda running every
5 minutes would cost more and detect violations up to 5 minutes late.
EventBridge reacts to the actual change within seconds.

**Why S3 Object Lock in COMPLIANCE mode:** Brazilian law (CFM 1821/2007) requires
medical records to be kept for 20 years. COMPLIANCE mode means not even the
AWS root account can delete those logs before the period expires.
GOVERNANCE mode can be bypassed by admins. That is not good enough.

**Why VPC Endpoints instead of just NAT Gateway:** The Lambda functions talk to
KMS, CloudTrail, and Config constantly. With NAT Gateway, that traffic goes through
the public internet before TLS encrypts it. With VPC Endpoints, it stays inside
the AWS network the entire time. For health data that is the right call.

**Why selective auto-remediation:** I almost built full auto-remediation for everything.
Then I thought through: what if the Lambda removes an IAM permission that a medical
record system depends on? A doctor cannot log in. That is a different kind of incident.
So I wrote a decision matrix based on reversibility without operational impact.

Full ADRs: docs/adr/

---

## How to run this

```bash
git clone https://github.com/guinatural/wayfinder-cloud.git
cd wayfinder-cloud

# First time only: create the S3 bucket and DynamoDB table for Terraform state
python scripts/bootstrap_state.py --env dev --region us-east-1

# Copy the example and fill in your email
cp infra/environments/dev/terraform.tfvars.example \
   infra/environments/dev/terraform.tfvars

cd infra/environments/dev
terraform init
terraform plan
terraform apply
```

Detailed walkthrough: docs/runbooks/RB-002-terraform-operations.md

---

## Project structure

```
infra/modules/     8 Terraform modules
infra/environments/dev + prod
src/lambdas/       4 Python 3.12 functions
src/tests/         unit tests with moto
docs/adr/          9 architecture decision records
docs/runbooks/     5 operational runbooks
docs/compliance/   LGPD article to AWS control mapping
docs/business/     VitaCore scenario and incident post-mortem
.github/workflows/ 3 CI/CD pipelines
scripts/           bootstrap script for Terraform state
```

---

## Cost

Dev environment with just the governance layer: about $38/month.
Full VitaCore production stack: about $870/month.
One incident like March 2026: R$ 2,107,000.

---

## Author

Guilherme Barreto Gomes

[GitHub](https://github.com/guinatural)

---

MIT License
