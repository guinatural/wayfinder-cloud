# ADR-004  Automatic Remediation Strategy

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

When a Config Rule detects a compliance deviation, there are three possible strategies:

1. **Notify only** - human alert, manual remediation
2. **Fully automatic remediation** - system fixes without human intervention
3. **Selective automatic remediation** - automatic for safe cases, notification for ambiguous cases

In a digital health environment, incorrect remediation can be as damaging as
the deviation itself. For example: automatically deleting an EC2 instance to "remediate"
a security group violation can take down a critical care service.

---

## Decision

**Selective automatic remediation** based on risk classification and reversibility.

---

## Remediation Matrix

| Violation | Severity | Auto-Remediation | Justification |
|---|---|---|---|
| S3 Block Public Access disabled | CRITICAL | YES - enable Block Public Access | Reversible action, risk too high to wait |
| S3 without KMS encryption | CRITICAL | YES - enable SSE-KMS | Reversible, no operational impact |
| CloudTrail disabled | CRITICAL | YES - re-enable CloudTrail | Reversible, no operational impact |
| Security Group with 0.0.0.0/0 on port 22 | HIGH | PARTIAL - revoke rule + notify | Reversible but may impact legitimate access |
| EC2 in public subnet with health data | CRITICAL | PARTIAL - isolate via SG + notify | Moving EC2 subnet is disruptive |
| IAM with excessive admin permissions | HIGH | NO - notify only | Removing permission can break workflows |
| RDS without encryption | HIGH | NO - notify only | Encrypting existing RDS requires recreation |
| MFA disabled for IAM user | HIGH | NO - notify only | Cannot force MFA remotely |

---

## Remediation Guardrails

To prevent cascading remediations or loops:

```python
# Lambda auto-remediation must check:
# 1. Tag "remediation-exempt=true" on resource -> skip remediation
# 2. Environment = prod -> require manual approval via SNS + Lambda approval
# 3. Limit of 3 attempts per resource in 1h -> prevent loop
# 4. Active maintenance window -> defer non-critical remediation
```

---

## Approval Process for Prod

```
Violation detected in prod
        |
        v
Lambda compliance-evaluator classifies
        |
        +-- CRITICAL --> Immediate automatic remediation
        |                     + Post-fact notification
        |
        +-- HIGH/MEDIUM --> SNS notification with approval link
                                        |
                            +-----------+-----------+
                            |                       |
                     Approved (2h)           No response (2h)
                            |                       |
                            v                       v
                   Auto-remediation          Escalation to
                   executes                  higher level
```

---

## Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| Automatic remediation may cause interruption | Medium | Conservative matrix - only clearly safe actions are automatic |
| Manual notification has latency | Medium | CRITICAL is always automatic; HIGH has 2h SLA |
| False positive may remediate a legitimate resource | Low | Tag `remediation-exempt=true` allows explicit exclusion |

---

## Consequences

- Every remediation Lambda MUST log the action taken in CloudWatch with structured JSON format
- Every remediation action MUST generate an event in EventBridge for traceability
- Tag `remediation-exempt=true` MUST be documented as a controlled exclusion mechanism
- Response SLA MUST be defined by severity and monitored via CloudWatch
- A manual remediation runbook MUST exist for each case where automation is not applied
