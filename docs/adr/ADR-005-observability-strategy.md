# ADR-005  Observability Strategy: Native CloudWatch + X-Ray

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

Wayfinder Cloud needs observability across multiple layers:

1. **Infrastructure** - CPU, memory, Lambda throttling metrics
2. **Compliance** - number of NON_COMPLIANT resources by severity, remediation rate
3. **Application** - Lambda errors, latency, distributed call tracing
4. **Audit** - structured logs of all actions taken by the system

The project runs 100% on AWS with no external agents, and has a minimized observability budget.
The team is small (~2 engineers) and cannot operate an additional observability platform.

---

## Options Evaluated

### Option 1: DataDog
- **Pros:** Excellent dashboard, logs/metrics/traces correlation, advanced APM
- **Cons:** Cost ~$20-40/host/month, requires installed agent, data leaves AWS, long-term contract
- **Estimated cost:** ~$500-2,000/month for the project

### Option 2: New Relic
- **Pros:** Generous free tier (100GB/month), modern UI, distributed APM
- **Cons:** Audit data would leave AWS (LGPD regulatory issue), additional ingestion latency
- **Estimated cost:** $0 on free tier, but with lockout risk

### Option 3: Grafana + Prometheus (self-hosted)
- **Pros:** Open source, extremely flexible, no license cost
- **Cons:** Requires EC2/ECS to host (infra cost), manual upgrade operations,
  no native integration with Config/CloudTrail

### Option 4: Native CloudWatch + X-Ray - **Chosen**
- **Pros:** Zero agent, native integration with all AWS services used, dashboards as code (Terraform),
  no data egress outside AWS, predictable cost
- **Cons:** CloudWatch UI less polished than DataDog, custom metrics have cost per PutMetricData

---

## Decision

**CloudWatch Logs + Metrics + Alarms + Dashboards + X-Ray** was chosen as the observability stack.

---

## Justification

### Cost
CloudWatch has usage-based cost. For Wayfinder Cloud volume (low number of compliance events):
- Log Groups: ~$0.50/GB ingested
- Custom metrics: ~$0.30/metric/month
- Dashboards: $3/dashboard/month
- X-Ray: $5/million traces

Estimated total cost: **< $50/month** vs $500-2,000/month for external tools.

### Native Integration
CloudTrail, Config, Lambda, and EventBridge already publish metrics and logs to CloudWatch without
any additional configuration. X-Ray integrates directly with Lambda via `tracing_config { mode = "Active" }`.

### No External Agent
Lambdas are ephemeral - installing DataDog/New Relic agents increases cold start and deployment
complexity. CloudWatch SDK is built into the Python runtime.

### Data Inside AWS (LGPD)
Compliance logs contain resource metadata with health data. Keeping everything in CloudWatch
ensures that data never leaves the AWS infrastructure controlled by VitaCore Health.

### Dashboards as Code
`aws_cloudwatch_dashboard` in Terraform allows versioning and reviewing dashboard changes
via pull request, like any other infrastructure change.

---

## Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| Less rich UI than DataDog | Low - dashboards meet the need | CloudWatch has been improving continuously |
| Cost per PutMetricData | Low - ~100 events/day | Batch metric grouping |
| Manual logs-traces correlation | Medium | X-Ray Service Map covers most cases |
| No automatic anomaly detection | Medium | CloudWatch Anomaly Detection available as future enhancement |

---

## Namespace Structure

```
wayfinder/Compliance
  - NonCompliantResource [RuleName, Severity, Environment]
  - ComplianceScore [Environment]

wayfinder/Remediation
  - RemediationAttempt [RuleName, Status, Severity, Environment]

AWS/Lambda (automatic)
  - Errors, Invocations, Duration, Throttles [FunctionName]
```

## Log Group Structure

```
/wayfinder/cloudtrail                         CloudTrail logs (retention: 365 days)
/wayfinder/lambda/compliance-evaluator        (retention: 90 days)
/wayfinder/lambda/auto-remediation            (retention: 90 days)
/wayfinder/lambda/incident-notifier           (retention: 90 days)
/wayfinder/lambda/audit-reporter              (retention: 90 days)
```

---

## Consequences

- All Lambda logs MUST use structured JSON format to enable Logs Insights queries
- Alarms MUST be created via Terraform (not manually in the console)
- Custom metrics MUST use the namespaces defined above for consistency
- X-Ray MUST be active on all Lambdas (`tracing_config { mode = "Active" }`)
- Future enhancements (business dashboards, SLOs) can add Grafana Cloud as a visualization layer

---

## Future Enhancements

- **CloudWatch Contributor Insights** to identify top violation contributors
- **CloudWatch Synthetics** to monitor report endpoints
- **AWS Health Dashboard** to correlate service events with violation spikes
- **Grafana Cloud** (free tier) as an additional visual frontend connecting to CloudWatch via datasource
