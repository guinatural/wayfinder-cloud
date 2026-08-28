# ADR-003  Audit Trail with S3 + Object Lock + Athena

**Status:** Accepted
**Date:** 2026-08-21
**Author:** Guilherme Barreto Gomes
**Reviewers:**

---

## Context

LGPD (Art. 37) requires the data controller to maintain records of personal data
processing operations. For health data (Art. 11), this requirement is even more critical.
The audit trail must be:

1. **Immutable** - nobody can delete or modify logs after generation
2. **Queryable** - the security team needs to investigate incidents with SQL
3. **Centralized** - all logs (API calls, data access, Config changes) in one place
4. **Cost-effective** - years of historical logs must not cost a fortune

Options evaluated for storage:

1. S3 + Object Lock + Athena
2. CloudWatch Logs Insights
3. OpenSearch (Elasticsearch)
4. RDS for structured logs

---

## Decision

**S3 with Object Lock (COMPLIANCE mode) + AWS Glue Data Catalog + Amazon Athena**
for audit trail storage and querying.

---

## Justification

**Immutability:**
- S3 Object Lock in COMPLIANCE mode prevents any user, including root,
  from deleting or modifying objects during the retention period
- This guarantees the chain of custody of logs required for legal purposes
- CloudWatch Logs does not offer Object Lock - logs can be deleted

**Cost:**
- S3 Standard: ~$0.023/GB/month -> S3 Glacier: ~$0.004/GB/month (lifecycle after 90 days)
- CloudWatch Logs: ~$0.50/GB ingested + $0.03/GB stored - much more expensive for high volumes
- OpenSearch: requires dedicated instances, fixed cost regardless of volume

**Queryability:**
- Athena allows SQL directly on Parquet/JSON files in S3
- No server to manage, no idle cost
- CloudWatch Logs Insights has a proprietary syntax and scale limitations

**Scalability:**
- S3 scales infinitely without configuration
- Athena scales automatically for queries on petabytes of data

---

## S3 Partitioning Structure

```
s3://vitacore-audit-trail-{account-id}/
  cloudtrail/
     AWSLogs/{account-id}/CloudTrail/{region}/
         {year}/{month}/{day}/
             {account-id}_CloudTrail_{region}_{timestamp}.json.gz
  config/
     {year}/{month}/{day}/
         config-snapshot-{timestamp}.json.gz
  compliance-events/
      {year}/{month}/{day}/
          wayfinder-events-{timestamp}.json
```

Partitioning by `year/month/day` reduces Athena scan cost
because date-filtered queries do not read irrelevant partitions.

---

## Retention Policy

| Log Type | S3 Standard Retention | S3 Glacier Retention | Object Lock |
|---|---|---|---|
| CloudTrail management events | 90 days | 5 years | 5 years |
| CloudTrail data events (S3) | 30 days | 2 years | 2 years |
| Config snapshots | 90 days | 1 year | 1 year |
| Compliance events (Wayfinder) | 90 days | 5 years | 5 years |

5-year retention for CloudTrail aligns with the statute of limitations
and health compliance best practices.

---

## Trade-offs Accepted

| Trade-off | Impact | Mitigation |
|---|---|---|
| Athena is not real-time | Low - auditing is historical, not real-time | Real-time alerts stay in CloudWatch/SNS |
| Object Lock prevents correcting logs with errors | Low - logs are append-only, not edited | Log generation process must be tested before enabling lock |
| Glue Crawler has a cost per DPU-hour | Low | Crawler scheduled 1x/day, not continuous |

---

## Consequences

- S3 audit trail bucket MUST be created with Object Lock enabled (cannot be enabled later)
- Versioning MUST be enabled (Object Lock requirement)
- Lifecycle rules MUST move objects to Glacier after 90 days
- Athena workgroup MUST have query results saved in a separate S3 bucket with cost control
- CloudTrail MUST have S3 data events enabled for health data buckets
- KMS CMK MUST be used to encrypt all logs
