# ADR-002  Event-Driven Architecture for Compliance Evaluation

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

The compliance system needs to evaluate AWS resources continuously and react to
configuration deviations without active polling. There are two main approaches:

1. **Periodic polling** - scheduled Lambda that scans resources periodically
2. **Event-driven** - Config Rules + EventBridge react to changes in real time

The digital health context adds an extra requirement: the time between a compliance
deviation and the response (alert + remediation) must be as short as possible to
comply with the spirit of LGPD Art. 48 (incident communication).

---

## Decision

**Event-driven architecture** using AWS Config + EventBridge as the event backbone,
with Lambda as the evaluation and remediation logic executor.

---

## Justification

**Detection latency:**
- Polling every 5 min: deviation can exist for up to 5 min before detection
- Event-driven (Config to EventBridge): detection in seconds after the configuration change

**Cost:**
- Lambda on-demand: charged only for real executions
- Polling with Lambda every 5 min: ~8,640 executions/month even without events

**Scalability:**
- EventBridge processes multiple simultaneous events without bottleneck
- Routing rules allow sending different event types to specific Lambdas

**Decoupling:**
- AWS Config, EventBridge, and Lambda are independent
- A failure in a remediation Lambda does not impact detection
- New compliance types can be added by creating a new Config Rule + EventBridge Rule
  without modifying existing components (Open/Closed Principle)

---

## Detailed Architectural Flow

```
AWS resource modified
        |
        v
AWS Config detects configuration change
        |
        v
Config Rule evaluates: COMPLIANT or NON_COMPLIANT
        |
        v
EventBridge Rule (on Config Rule change)
        |
        +-- NON_COMPLIANT + CRITICAL --> Lambda compliance-evaluator
        |                                           |
        |                                           +--> SNS Topic CRITICAL
        |                                           +--> Lambda auto-remediation
        |
        +-- NON_COMPLIANT + HIGH --> Lambda compliance-evaluator
        |                                           |
        |                                           +--> SNS Topic WARNING
        |
        +-- COMPLIANT --> CloudWatch metric (compliance %)
```

---

## Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| Config has a few seconds delay to detect changes | Low - seconds, not minutes | Acceptable for this context |
| EventBridge has a limit of 300 rules per event bus | Low - project uses ~20 rules | Monitor as project scales |
| Complexity of debugging event-driven flow | Medium | X-Ray tracing on all Lambdas + structured CloudWatch Logs |

---

## Consequences

- Config MUST be enabled in all active regions with all-resources recording
- EventBridge MUST have rules for each violation type classified by severity
- All Lambdas MUST have X-Ray active for event flow traceability
- Dead Letter Queues (SQS) MUST be configured on all Lambdas to capture failures
- CloudWatch MUST have custom metrics for compliance (% COMPLIANT resources)
