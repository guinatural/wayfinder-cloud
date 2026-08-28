# ADR-001  Choosing Terraform as the IaC Tool

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

The Wayfinder Cloud project needs to provision and manage ~15 types of AWS resources
in a reproducible, versioned, and auditable way. The infrastructure must be
consistent across `dev` and `prod` environments and must be modifiable by any
technical team member without needing direct console access.

Options evaluated:

1. **Terraform (HashiCorp)** - declarative IaC, multi-cloud, HCL
2. **AWS CDK (Python)** - imperative IaC, AWS-native, Python/TypeScript
3. **AWS CloudFormation** - declarative native AWS IaC, YAML/JSON
4. **Pulumi** - imperative IaC, multi-cloud, Python

---

## Decision

**Terraform** was chosen as the primary IaC tool.

---

## Justification

**In favor of Terraform:**

- Highest market adoption - appears in ~70% of Cloud/DevOps job listings
- Mature ecosystem with verified public module registry
- Explicit state management (remote state on S3 + DynamoDB lock) makes infra state auditable
- Clear separation between reusable modules and environment configurations
- AWS provider updated frequently by HashiCorp and community
- Supports importing existing manually created resources (`terraform import`)
- Separate Plan/Apply steps allow reviewing changes before applying

**Against AWS CDK:**
CDK would be more natural given the Python background, but it generates CloudFormation
internally, adding an abstraction layer that complicates debugging in technical interviews.
CDK also requires Node.js even for Python projects, adding a dependency.

**Against CloudFormation:**
Verbose YAML makes modular reuse harder. No support for other providers,
limiting knowledge portability. Less valued in jobs that are not AWS-only.

**Against Pulumi:**
Smaller ecosystem, lower adoption in the market. Additional cost for state management
features in teams.

---

## Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| HCL is a language to learn | Low - simple syntax | Excellent documentation, fast learning curve |
| State file needs a remote backend | Medium - initial setup | `storage` module creates S3 + DynamoDB for state |
| Not AWS-native | Low for this project | Project is AWS-only, no multi-cloud need |

---

## Consequences

- All AWS resources in the project MUST be created via Terraform
- Resources created manually in the console MUST be imported or destroyed
- Terraform state MUST be stored remotely (S3 + DynamoDB)
- Infrastructure changes MUST go through `terraform plan` in CI/CD before `apply`
- Reusable modules MUST be documented with complete `variables.tf` and `outputs.tf`
