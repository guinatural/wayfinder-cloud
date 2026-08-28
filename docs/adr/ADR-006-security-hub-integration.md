# ADR-006  AWS Security Hub Integration

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

Wayfinder Cloud implements security controls focused on LGPD compliance, but VitaCore Health
also needs to demonstrate conformance with internationally recognized frameworks for:

1. External security audits and accreditation (SBIS, CFM)
2. Due diligence in partnerships with health plans and hospitals
3. Mapping security posture in a consolidated view
4. Correlating custom Config Rules (WAYFINDER-001..014) with NIST/CIS controls

Without a consolidated view, the team would have to manually cross results from AWS Config,
GuardDuty, Inspector, and Macie - an unscalable operational effort.

---

## Decision

**Enable AWS Security Hub** with the following standards:

1. **AWS Foundational Security Best Practices (FSBP)** - AWS-native standard, covers ~280 controls
2. **CIS AWS Foundations Benchmark v1.4** - widely recognized standard in audits

---

## Justification

### FSBP - AWS Foundational Security Best Practices
- Developed by AWS based on real incidents and operational best practices
- Covers all services used by Wayfinder Cloud (S3, IAM, CloudTrail, Config, Lambda, KMS)
- Findings are generated automatically and appear in EventBridge - integrable with the existing pipeline
- Cost: $0.001 per control check/resource/month

### CIS AWS Foundations Benchmark v1.4
- Internationally recognized by security auditors (ISO 27001, SOC 2)
- Specifically covers: IAM, logging, monitoring, and networking
- Aligns with Wayfinder Cloud audit controls (CloudTrail, Config, MFA)
- Helps demonstrate "best practices and governance" required by LGPD Art. 50

### Integration with the Existing Pipeline
Security Hub publishes findings to EventBridge with `source: aws.securityhub`.
The existing EventBridge Rule can be extended to route CRITICAL Security Hub findings
to the same compliance-evaluator pipeline - SNS - SecOps.

---

## Mapping to LGPD Art. 50

LGPD Art. 50 requires controllers and processors to adopt "best practices and governance",
including "policies and safeguards based on technical standards that apply adequate security measures".

| CIS/FSBP Control | LGPD Article | Wayfinder Implementation |
|---|---|---|
| CIS 2.1 - CloudTrail enabled | Art. 37 (records) | WAYFINDER-003 + managed rule CLOUD_TRAIL_ENABLED |
| CIS 3.x - S3 Block Public Access | Art. 46 (security) | WAYFINDER-002 + S3_BUCKET_PUBLIC_READ_PROHIBITED |
| CIS 1.5 - MFA for root | Art. 46 (access) | MFA_ENABLED_FOR_IAM_CONSOLE_ACCESS |
| FSBP KMS.1 - key rotation | Art. 46 (encryption) | KMS CMK with `enable_key_rotation = true` |
| FSBP Lambda.1 - no public access policies | Art. 46 | IAM least privilege on Lambda roles |
| FSBP Config.1 - Config enabled | Art. 37 (traceability) | Config Recorder in all environments |

---

## Integration Architecture

```
Security Hub Finding (CRITICAL)
    |
    v
EventBridge (source: aws.securityhub)
    |
    v
Rule: security-hub-critical-findings
    |
    v
Lambda: compliance-evaluator
    |
    v
SNS CRITICAL -> SecOps email + Slack
```

The integration will be implemented by adding a new EventBridge Rule in the `observability` module:

```hcl
resource "aws_cloudwatch_event_rule" "security_hub_critical" {
  name           = "${local.name_prefix}-securityhub-critical"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["aws.securityhub"]
    "detail-type" = ["Security Hub Findings - Imported"]
    detail = {
      findings = {
        Severity = { Label = ["CRITICAL", "HIGH"] }
      }
    }
  })
}
```

---

## Trade-offs

| Trade-off | Impact | Mitigation |
|---|---|---|
| Additional Security Hub cost | Low (~$10-30/month for the account) | Positive ROI: reduces manual audit hours |
| Overlap with custom Config Rules | Medium - may generate duplicate alerts | Filter Security Hub findings by source before routing |
| Initial false positives | High at first | 30-day calibration period before enabling alerts |
| Need to enable GuardDuty | Low | GuardDuty already planned in managed rule GUARDDUTY_ENABLED_CENTRALIZED |

---

## Not Enabled Now (Future Implementation)

Enabling Security Hub requires:
1. Enabling GuardDuty and Inspector in the account (FSBP dependencies)
2. 30-day calibration period to reduce false positives
3. EventBridge Rule adjustment to avoid duplicating alerts with Config Rules

For these reasons, the integration is documented in this ADR but will be implemented
in a dedicated sprint after the Wayfinder Cloud MVP is in production.

---

## Consequences

- The `observability` module MUST be extended with an EventBridge Rule for Security Hub findings
- Security Hub findings MUST be correlated with WAYFINDER-001..014 rules to avoid duplicates
- The weekly `audit-reporter` report MUST include a Security Hub score section
- This ADR MUST be updated when the integration is implemented (status -> "Implemented")
