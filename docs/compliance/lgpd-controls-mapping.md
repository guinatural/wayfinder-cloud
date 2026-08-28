# LGPD - AWS Technical Controls Mapping

**Project:** Wayfinder Cloud
**Version:** 2.0 | **Status:** Approved by DPO
**Legal references:**
- Lei n 13.709/2018 - LGPD (Brazilian General Data Protection Law)
- CFM 1821/2007 - Technical standards for computerized medical records
- RDC ANVISA 204/2017 - Traceability of digitally prescribed medications
- CFM 2314/2022 - Regulation of telemedicine in Brazil
- ISO/IEC 27001:2022 - Information Security Management

**Context:** VitaCore Health - digital health platform processing data for
127,000 active patients in SP, RJ, and MG. A security incident on 2026-03-15
resulted in a fine of R$ 420,000 from ANPD and a loss of R$ 1.68M in contracts.

---

## 1. Architectural Premise - Health Data as Sensitive Data

### 1.1 Legal Classification (LGPD Art. 5, II)

Health data is **sensitive personal data** under LGPD Art. 5, II:

> "sensitive personal data: personal data concerning racial or ethnic origin, religious
> belief, political opinion, membership of a union or organization of a religious,
> philosophical or political nature, data relating to health or sexual life, genetic
> or biometric data, when linked to a natural person"

Direct architectural implications:
- **Mandatory encryption** at rest and in transit for all health data
- **Explicit legal basis** for each processing operation (Art. 11, II, f - health protection)
- **Privacy by Design**: security controls must be native to the architecture, not added later
- **Least privilege**: each service accesses only the data strictly necessary for its function

### 1.2 Legal Basis for Processing (LGPD Art. 11, II, f)

VitaCore processes health data under Art. 11, II, f:
"protection of the life or physical integrity of the data subject or a third party" and
complementarily under Art. 11, II, g: "health care".

Explicit patient consent (Art. 11, I) is collected at admission and
stored in Aurora MySQL with versioning and an immutable timestamp.

### 1.3 Legal Retention Period - Medical Records

CFM 1821/2007 and CFM 1638/2002 establish:
- **Digital medical record: minimum 20 years** after the last entry
- **Minors**: minimum until age 25 or 5 years after reaching adulthood
- **Imaging exams (DICOM)**: minimum 5 years (some states require 10 years)

Critical technical implication for Wayfinder Cloud:
```
S3 Object Lock - COMPLIANCE mode (cannot be removed even by root)
  Medical records:            retention = 20 years (7,305 days)
  Imaging reports:            retention = 5 years  (1,825 days)
  Telemedicine recordings:    retention = 5 years  (1,825 days)
  Digital prescriptions:      retention = 5 years  (1,825 days)
  Audit data:                 retention = 5 years  (1,825 days) - contractual requirement
```

**Why COMPLIANCE mode and not GOVERNANCE mode?**
In COMPLIANCE mode, not even the AWS account root user can reduce the
retention period or delete the object before expiration. In GOVERNANCE mode,
users with `s3:BypassGovernanceRetention` permission can bypass the lock.
For health data subject to 20-year legal obligations, COMPLIANCE mode is
the only option that provides legal immutability guarantee.

---

## 2. LGPD x AWS Controls Mapping Table

### 2.1 Art. 5 - Fundamental Definitions

| LGPD Concept | Definition Applied at VitaCore | Technical Control |
|---|---|---|
| Sensitive personal data (Art. 5, II) | CPF + diagnosis + exam result + telemedicine recording | Tag `data-classification=health-critical` on all resources |
| Controller (Art. 5, VI) | VitaCore Health - defines purpose and means of processing | IAM policies scoped per service; DPO responsible |
| Processor (Art. 5, VII) | AWS (infrastructure), integrated labs (report processing) | Data Processing Agreement (DPA) with AWS, contracts with labs |
| Processing agents (Art. 5, IX) | VitaCore (controller) + AWS + labs + health plans | IAM Identity Center with SSO; roles with minimum scope |

### 2.2 Art. 6 - Processing Principles

| Principle (Art. 6) | Technical Implementation | Config Rule / Control |
|---|---|---|
| **Purpose** (I) - legitimate and explicit purposes | Health data used exclusively for medical care | SCPs block sharing outside the account without approval |
| **Adequacy** (II) - compatible with purpose | Wearable data used only for patient monitoring | IAM conditions `aws:ResourceTag/data-classification` |
| **Necessity** (III) - minimum necessary | Only relevant clinical fields returned by API | Lambda scope validation before returning data |
| **Free access** (IV) - access to information | Patient can access their data via VitaCore Patient app | Cognito with data portability implemented |
| **Quality** (V) - accurate and updated data | Aurora with integrity constraints + input validation | CloudWatch alarms for data inconsistencies |
| **Transparency** (VI) - clear information | Public privacy policy + in-app notice | Outside technical scope (legal/communications) |
| **Security** (VII) - technical and administrative protection | KMS CMK + TLS 1.3 + VPC + MFA + audit | WAYFINDER-001 to WAYFINDER-014 |
| **Prevention** (VIII) - damage prevention | Config Rules detect before reaching prod | AWS Config + GitHub Actions guardrails |
| **Non-discrimination** (IX) - no discriminatory purposes | Health data not used for scoring or selection | SCP blocks cross-account data sharing without approval |
| **Accountability** (X) - demonstrate compliance | Immutable audit trail + weekly reports | CloudTrail + S3 Object Lock + Athena + DPO reports |

### 2.3 Art. 11 - Processing of Sensitive Data

| Requirement (Art. 11) | Implementation | Technical Evidence |
|---|---|---|
| Explicit legal basis (II, f) | Consent stored in Aurora with immutable timestamp | CloudTrail data events on consent record |
| Additional protection for sensitive data | Dedicated CMK `vitacore-health-critical-key` separate from other data | KMS Key Policy with `aws:ResourceTag` condition |
| Data sharing with third parties with legal basis | Lab integration API requires Cognito JWT + signed DPA | API Gateway authorizer + CloudTrail of calls |
| Recording operations with sensitive data | CloudTrail enabled with S3 and Aurora data events | `cloudtrail-s3-dataevents-enabled` Config Rule |

### 2.4 Art. 37 - Processing Operations Record

| Requirement | AWS Implementation | Config Rule |
|---|---|---|
| Record of processing activities | CloudTrail All Regions + S3 Data Events + RDS API | `cloud-trail-enabled` + `cloudtrail-s3-dataevents-enabled` |
| Record must be available to ANPD | S3 audit bucket with access via dedicated IAM Role for DPO | IAM Policy `vitacore-dpo-audit-access` |
| Record retention period | S3 Object Lock COMPLIANCE 5 years (contractual requirement) | WAYFINDER-013 + Config Rule `s3-bucket-object-lock-enabled` |

### 2.5 Art. 38 - Data Protection Impact Assessment (DPIA)

| Requirement | Implementation | Responsible |
|---|---|---|
| DPIA for high-risk operations | Document generated via Athena + manual audit | DPO Ana Lima |
| Periodic DPIA review | Scheduled semi-annually via EventBridge Scheduler | DPO + SecOps |
| DPIA available to ANPD | DPO documentation S3 bucket with controlled access | DPO |

### 2.6 Art. 46 - Security in Processing

| Obligation (Art. 46) | Technical Control | Config Rules |
|---|---|---|
| Technical and administrative measures to protect data | KMS CMK encryption + TLS 1.3 + MFA + private VPC | WAYFINDER-001, 004, 008, 010 |
| Protection against unauthorized access | IAM Least Privilege + SCPs + restrictive Security Groups | WAYFINDER-005, 006, 009 |
| Protection against accidental situations (like the March incident) | Config Rules + automatic remediation + S3 Block Public Access | WAYFINDER-002 |
| Protection against unlawful destruction | S3 Object Lock COMPLIANCE + Backup Vault Lock | WAYFINDER-013 |
| Protection against loss | AWS Backup with vault lock + Aurora Multi-AZ | `backup-plan-min-frequency-and-min-retention-check` |

### 2.7 Art. 47 - Responsibility of Processing Agents

| Obligation | Implementation | Control |
|---|---|---|
| Processors guarantee equivalent security | DPA with AWS + contracts with labs with security clauses | Annual legal review + IAM permission boundaries |
| Collaborators access only necessary data | IAM Identity Center with roles per function (doctor, admin, dev, audit) | WAYFINDER-005 + `iam-no-inline-policy` |
| Team training | Mandatory LGPD onboarding + incident simulations | Outside technical scope - documented in DPO program |

### 2.8 Art. 48 - Security Incident Notification

**Legal deadline: 72 hours after becoming aware of the incident**

The March incident exposed the absence of automatic detection. Wayfinder Cloud
implements the following response pipeline:

```
Automatic detection (Config Rule / GuardDuty / CloudWatch Alarm)
    |
    v
EventBridge -> Lambda incident-notifier
              |
              +--> CRITICAL severity (health data exposed)
                       SNS -> Email DPO + CTO + SecOps (< 2 min)
                       SNS -> PagerDuty (24/7 alert)
                       Lambda auto-remediation (automatic containment)
                       Jira ticket created automatically with LGPD Art. 48 template
              |
              +--> ANPD notification document generated via Lambda audit-reporter
                         Pre-filled communication template with:
                             - Nature of affected personal data
                             - Number of affected data subjects
                             - Containment measures adopted
                             - Future prevention measures
```

**Internal ANPD notification SLA: maximum 48h after becoming aware** (24h buffer from legal deadline).

### 2.9 Art. 49 - Processing Systems

| Requirement | Implementation | Evidence |
|---|---|---|
| Privacy by Design | IaC with mandatory security controls; dev cannot create bucket without encryption | Config Rules + GitHub Actions policy check |
| Privacy by Default | Mandatory `data-classification` tags; KMS default encryption on account | SCP `require-encryption-at-rest` |
| Security from conception | Compliance module mandatory in all environments | Terraform modules with integrated controls |
| Periodic evaluation | Weekly posture report + quarterly audit | Lambda audit-reporter + Athena |

### 2.10 Art. 50 - Best Practices and Governance

| Program | Implementation | Metrics |
|---|---|---|
| AWS Foundational Security Best Practices | Security Hub FSBP Standard enabled | FSBP score > 85% in prod |
| CIS AWS Foundations Benchmark v1.4 | Security Hub CIS Standard enabled | CIS score > 80% in prod |
| Documented governance program | This document + ADRs + Runbooks | Quarterly review by DPO |
| Periodic audits | Weekly Athena queries + semi-annual external audit | Reports exported from Athena |

---

## 3. Custom Config Rules WAYFINDER-001 to WAYFINDER-014

All custom rules are implemented via Lambda `compliance-evaluator`
and registered in AWS Config as `CUSTOM_LAMBDA` rules.

### WAYFINDER-001 - S3 with Health Data without KMS CMK Encryption

```
ID:            WAYFINDER-001
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Evaluation:    Bucket with tag data-classification=health-* MUST have
               SSE-KMS with customer managed key (not SSE-S3 or AWS Managed Key)
Non-compliant: Severity CRITICAL
Remediation:   Automatic - enables SSE-KMS with health-critical CMK
Deadline:      Remediation in < 5 minutes after detection
LGPD:          Art. 46, 49 | ISO 27001: A.8.24
Evidence:      CloudTrail: s3:PutBucketEncryption + Config timeline
Incident note: vitacore-laudos-imagens-prod bucket was using SSE-S3
```

### WAYFINDER-002 - S3 with Health Data with Public Access Enabled

```
ID:            WAYFINDER-002
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Evaluation:    Bucket with tag data-classification=health-* MUST have
               BlockPublicAcls=true, IgnorePublicAcls=true,
               BlockPublicPolicy=true, RestrictPublicBuckets=true
Non-compliant: Severity CRITICAL
Remediation:   Automatic - enables Block Public Access on all 4 dimensions
Deadline:      Remediation in < 5 minutes after detection
LGPD:          Art. 46 | ISO 27001: A.8.20
Evidence:      CloudTrail: s3:PutPublicAccessBlock
DIRECT LESSON FROM THE MARCH 2026 INCIDENT: This rule would have detected and
remediated the incident in < 5 minutes instead of 18 days.
```

### WAYFINDER-003 - CloudTrail Disabled

```
ID:            WAYFINDER-003
Type:          CUSTOM_LAMBDA (complements managed rule cloud-trail-enabled)
Trigger:       Periodic (every 30 minutes) + ConfigurationItemChangeNotification
Evaluation:    CloudTrail trail must be IsLogging=true in all active regions.
               Also evaluates: S3 data events enabled for health-* buckets,
               multi-region trail, log file validation enabled
Non-compliant: Severity CRITICAL
Remediation:   Automatic - re-enables trail and notifies SecOps
Deadline:      Detection in < 30 minutes (periodic evaluation)
LGPD:          Art. 37, 48 | ISO 27001: A.8.15
INCIDENT NOTE: CloudTrail was disabled for 43 days without detection.
This rule ensures a maximum of 30 minutes of trail downtime without an alert.
```

### WAYFINDER-004 - RDS without Encryption at Rest

```
ID:            WAYFINDER-004
Type:          CUSTOM_LAMBDA (complements managed rule rds-storage-encrypted)
Trigger:       ConfigurationItemChangeNotification (RDS DBInstance, DBCluster)
Evaluation:    RDS Instance/Cluster MUST have StorageEncrypted=true.
               Also evaluates: KmsKeyId must be a CMK (not AWS managed key)
               for clusters with tag data-classification=health-*
Non-compliant: Severity HIGH (CRITICAL for health-critical clusters)
Remediation:   Semi-automatic - creates encrypted snapshot and notifies for
               cluster recreation (cannot encrypt in-place)
LGPD:          Art. 46 | ISO 27001: A.8.24
VitaCore context: 1 Aurora cluster without encryption identified (legacy history)
```

### WAYFINDER-005 - IAM with Excessive Administrative Permissions

```
ID:            WAYFINDER-005
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (IAM Policy, IAM Role)
Evaluation:    No IAM Policy should have:
               Effect=Allow, Action=["*"] or Action=["*:*"], Resource="*"
               in prod environment. In dev, alert but do not remediate.
               Evaluates inline policies and attached managed policies.
Non-compliant: Severity HIGH
Remediation:   Semi-automatic - detach the offending policy + notification with
               least privilege policy suggestion
LGPD:          Art. 6, IV (necessity), Art. 47 | ISO 27001: A.8.2, A.5.15
VitaCore context: 12 IAM Roles with AdministratorAccess in production
```

### WAYFINDER-006 - EC2 with Health Data in Public Subnet

```
ID:            WAYFINDER-006
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (EC2 Instance)
Evaluation:    EC2 Instance with tag data-classification=health-* MUST NOT
               be in a public subnet (defined as a subnet with a route to IGW)
Non-compliant: Severity CRITICAL
Remediation:   Automatic - adds quarantine Security Group (blocks all inbound
               traffic) + immediate SecOps notification
LGPD:          Art. 46, 49 | ISO 27001: A.8.20
VitaCore context: 4 EC2 instances in public subnets processing patient data
```

### WAYFINDER-007 - Potential Credentials in Lambda Environment Variables

```
ID:            WAYFINDER-007
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (Lambda Function)
Evaluation:    Lambda environment variables MUST NOT contain patterns like:
               - PASSWORD, PASSWD, SECRET, KEY, TOKEN, CREDENTIAL (case-insensitive)
               with non-ARN values (values that are not arn:aws:secretsmanager:...)
               Regex: /(password|passwd|secret|db_pass|api_key|token)/i
Non-compliant: Severity HIGH
Remediation:   Notification with Secrets Manager migration guide
LGPD:          Art. 46 | ISO 27001: A.8.11 (secrets management)
```

### WAYFINDER-008 - CloudWatch Logs without KMS Encryption

```
ID:            WAYFINDER-008
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (CloudWatch Log Group)
Evaluation:    Log Groups with prefix /vitacore/ or /aws/lambda/wayfinder*
               MUST have kmsKeyId configured
Non-compliant: Severity MEDIUM
Remediation:   Automatic - associates CMK with the Log Group
LGPD:          Art. 46 | ISO 27001: A.8.24
```

### WAYFINDER-009 - Security Group with SSH/RDP Open to Internet

```
ID:            WAYFINDER-009
Type:          CUSTOM_LAMBDA (complements restricted-ssh managed rule)
Trigger:       ConfigurationItemChangeNotification (EC2 SecurityGroup)
Evaluation:    No Security Group should have inbound rule:
               Port 22 (SSH) or 3389 (RDP) with source 0.0.0.0/0 or ::/0
               Extension: also evaluates 3306 (MySQL), 5432 (PostgreSQL), 6379 (Redis)
Non-compliant: Severity CRITICAL (SSH/RDP) | HIGH (DB ports)
Remediation:   Automatic - removes the offending rule + records in audit trail
LGPD:          Art. 46 | ISO 27001: A.8.20, A.8.21
```

### WAYFINDER-010 - DynamoDB without Encryption at Rest

```
ID:            WAYFINDER-010
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (DynamoDB Table)
Evaluation:    DynamoDB tables with tag data-classification=health-* MUST have
               SSESpecification.SSEType = KMS (with CMK, not AWS_OWNED_KMS)
Non-compliant: Severity HIGH
Remediation:   Semi-automatic - DynamoDB can change SSE in-place; Lambda
               executes update-table to enable CMK
LGPD:          Art. 46 | ISO 27001: A.8.24
VitaCore context: DynamoDB for wearable data processing health-standard
```

### WAYFINDER-011 - ECS Task with Elevated Privileges (privileged=true)

```
ID:            WAYFINDER-011
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (ECS TaskDefinition)
Evaluation:    Container definitions in ECS Task Definitions MUST NOT have
               privileged=true in non-explicitly-exempt environments.
               Also evaluates: user="root", readonlyRootFilesystem=false
Non-compliant: Severity HIGH
Remediation:   Notification to Dev Lead with container security guide
LGPD:          Art. 49 (security from conception) | ISO 27001: A.8.9
```

### WAYFINDER-012 - IAM Access Key More Than 90 Days Without Rotation

```
ID:            WAYFINDER-012
Type:          CUSTOM_LAMBDA (complements access-keys-rotated managed rule)
Trigger:       Periodic (daily)
Evaluation:    IAM Users with access keys with LastUsedDate > 90 days without rotation.
               Alert at 75 days, non-compliant at 90, disable at 95 days.
Non-compliant: Severity MEDIUM (75d), HIGH (90d), CRITICAL (95d with disabling)
Remediation:   Semi-automatic - disables key at 95 days + notification to owner
LGPD:          Art. 47 | ISO 27001: A.5.17 (credential management)
VitaCore context: 67 IAM Users, no key rotation process
```

### WAYFINDER-013 - S3 without Object Lock for Data with Mandatory Retention

```
ID:            WAYFINDER-013
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Evaluation:    Buckets with tag retention-required=true MUST have:
               Object Lock enabled with COMPLIANCE mode.
               Retention period >= value of the retention-days tag.
Non-compliant: Severity HIGH
Remediation:   Notification (Object Lock cannot be enabled on existing bucket
               with data - requires creating a new bucket)
LGPD:          Art. 37 (processing records) | CFM 1821/2007 (20 years)
Context: Medical records require Object Lock COMPLIANCE for 20 years
```

### WAYFINDER-014 - Secrets Manager Not Used (Possible Hardcoded Credentials)

```
ID:            WAYFINDER-014
Type:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (Lambda, ECS TaskDefinition, EC2)
Evaluation:    Resources with tag data-classification=health-* MUST reference
               at least 1 Secrets Manager secret via ARN in their configurations.
               Resources with no reference to Secrets Manager are suspicious.
Non-compliant: Severity HIGH
Remediation:   Notification with migration guide + automatic Jira ticket creation
LGPD:          Art. 46 (security in processing) | ISO 27001: A.8.11
```

---

## 4. Additional Managed Rules

| Rule Key | AWS Identifier | Purpose | LGPD Article |
|---|---|---|---|
| `guardduty-enabled-centralized` | GUARDDUTY_ENABLED_CENTRALIZED | ML threat detection | Art. 46 |
| `securityhub-enabled` | SECURITYHUB_ENABLED | Consolidated posture | Art. 50 |
| `inspector-ec2-scan-enabled` | INSPECTOR_EC2_SCANNING_ENABLED | Vulns in EC2/ECR | Art. 46, 49 |
| `access-keys-rotated` | ACCESS_KEYS_ROTATED | Access key rotation | Art. 47 |
| `iam-password-policy` | IAM_PASSWORD_POLICY | Strong password policy | Art. 46 |
| `restricted-ssh` | RESTRICTED_INCOMING_TRAFFIC | Blocks public SSH | Art. 46 |
| `restricted-common-ports` | RESTRICTED_COMMON_PORTS | DB ports not exposed | Art. 46 |
| `dynamodb-table-encrypted-at-rest` | DYNAMODB_TABLE_ENCRYPTED_AT_REST | DynamoDB encrypted | Art. 46 |
| `elasticache-redis-cluster-backup` | ELASTICACHE_REDIS_CLUSTER_AUTOMATIC_BACKUP_CHECK | Redis with backup | Art. 46 |
| `wafv2-webacl-not-empty` | WAFV2_WEBACL_NOT_EMPTY | WAF configured | Art. 46 |
| `secretsmanager-rotation-enabled` | SECRETSMANAGER_ROTATION_ENABLED_CHECK | Secret rotation | Art. 47 |
| `backup-plan-min-frequency` | BACKUP_PLAN_MIN_FREQUENCY_AND_MIN_RETENTION_CHECK | Adequate backup | Art. 46 |

---

## 5. Impact Matrix - March 2026 Incident

This matrix answers: "If Wayfinder Cloud had been operational on 2026-03-15,
what would have happened?"

| Control | Would have Detected? | Would have Remediated? | Estimated Detection Time | Result with Wayfinder |
|---|---|---|---|---|
| WAYFINDER-002 (public S3) | Yes | Yes (automatic) | < 5 minutes | Block Public Access re-enabled before any external access |
| WAYFINDER-001 (no KMS CMK) | Yes | Yes (automatic) | < 5 minutes | SSE-KMS enabled - data unreadable even if accessed |
| Managed: s3-bucket-public-read-prohibited | Yes | No | < 15 minutes | Alert sent; manual remediation needed |
| WAYFINDER-003 (CloudTrail) | N/A | N/A | - | CloudTrail enabled; bucket access would have been recorded |
| GuardDuty (anomalous access) | Yes (after 1h of accesses) | No | ~1 hour | Finding UnauthorizedAccess:S3/MaliciousIPCaller |
| CloudWatch Alarm (S3 requests spike) | Yes | No | ~30 minutes | Alarm triggered by abnormal GET request volume |

**Conclusion:** With Wayfinder Cloud active, the incident would have been contained in less
than 5 minutes, with 0 data effectively exposed to external access (thanks to
automatic remediation). Avoided cost: ~R$ 2.1 million.

---

## 6. Data Classification - 5 Levels

| Level | Tag Value | Examples | Required Controls | Retention Period |
|---|---|---|---|---|
| **health-critical** | `health-critical` | Medical records, imaging reports, diagnoses, telemedicine recordings, prescriptions | Dedicated KMS CMK, VPC private subnet, CloudTrail data events, mandatory MFA, S3 Object Lock COMPLIANCE, daily backup | 20 years (records/CFM), 5 years (others) |
| **health-standard** | `health-standard` | Wearable data, aggregated vital signs, non-directly-identified health data | KMS AWS Managed Key, private subnet, CloudTrail, weekly backup | 3 years |
| **financial-sensitive** | `financial-sensitive` | Billing data, charges, health plan information | KMS CMK, private subnet, CloudTrail management events | 10 years (tax legislation) |
| **operational** | `operational` | Application logs, system metrics, X-Ray traces | SSE-S3, CloudWatch, lifecycle to Glacier after 90 days | 90 days hot, 1 year Glacier |
| **public** | `public` | Static assets (CSS, JS, marketing images), public documentation | No special restrictions | No minimum retention |

---

## 7. Legal Retention Period by Data Type

| Data Type | Minimum Period | Legal Basis | Technical Implementation |
|---|---|---|---|
| Complete electronic medical record | **20 years** after last entry | CFM 1821/2007, CFM 1638/2002 | S3 Object Lock COMPLIANCE 7,305 days |
| Imaging report (X-Ray, CT, MRI) | **5 years** (some states: 10 years) | CFM 1821/2007 | S3 Object Lock COMPLIANCE 1,825 days |
| Telemedicine recording | **5 years** | CFM 2314/2022 | S3 Object Lock COMPLIANCE 1,825 days |
| Electronic prescription | **5 years** | CFM + RDC ANVISA 204/2017 | S3 Object Lock COMPLIANCE 1,825 days |
| LGPD consent | During relationship + **5 years** after | LGPD Art. 8 | Aurora MySQL + backup S3 Object Lock |
| Audit trail (CloudTrail) | **5 years** (contractual with health plans) | VitaCore contract + LGPD Art. 37 | S3 Object Lock COMPLIANCE 1,825 days |
| Billing data | **10 years** | Lei 9.430/1996 (tax), RFB | S3 Intelligent-Tiering + lifecycle |
| Raw wearable data | **3 years** | VitaCore internal policy | S3 lifecycle: Glacier at 90 days, expire at 3 years |
| Application logs | **90 days** hot, **1 year** total | Internal policy | CloudWatch Logs 90d + export to S3 Glacier |

---

## 8. Incident Response Process - LGPD Art. 48

```
PHASE 1: DETECTION (< 5 min)

 Config Rule NON_COMPLIANT or GuardDuty CRITICAL finding
  EventBridge -> Lambda incident-notifier
  SNS CRITICAL -> Email DPO + CTO + SecOps + PagerDuty
  Lambda auto-remediation (automatic containment if applicable)


PHASE 2: EVALUATION (< 30 min)

 SecOps (Bruno Oliveira) executes Runbook RB-001
  Athena query: which data was accessed?
  Athena query: which IPs accessed the data?
  Count number of affected data subjects
  Classify as LGPD Incident if sensitive data involved


PHASE 3: CONTAINMENT (< 1h)

 Automatic remediation already executed (if WAYFINDER-002)
 If manual: SecOps follows Runbook RB-001 section 4
  Isolation of affected resource
  Evidence preservation (snapshot, logs)


PHASE 4: INTERNAL NOTIFICATION (< 4h after becoming aware)

 DPO Ana Lima notifies CEO Marcos Ferreira
  Jira ticket type "LGPD Incident" created
  Internal communication template filled out


PHASE 5: ANPD NOTIFICATION (< 48h after becoming aware - internal SLA)

 DPO submits communication via ANPD portal (Art. 48 paragraph 1)
 Required data in the communication:
   a) Nature of the affected personal data
   b) Information about the data subjects
   c) Technical and security measures taken
   d) Risks related to the incident
   e) Reasons for delay (if not reported within 72h)
 Lambda audit-reporter generates pre-filled report


PHASE 6: DOCUMENTATION AND LESSONS LEARNED (< 7 days)

 Post-mortem documented
  New Config Rule created to prevent recurrence
  Final report stored in S3 with Object Lock
```

---

## 9. References

- [LGPD - Lei n 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [CFM 1821/2007 - Electronic Medical Record](https://www.cfm.org.br/index.php/noticias/item/290-resolucao-cfm-no-18212007.html)
- [AWS FSBP - Foundational Security Best Practices](https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html)
- [CIS AWS Foundations Benchmark v1.4](https://www.cisecurity.org/benchmark/amazon_web_services)
- [ANPD - Guidance on Processing Agents](https://www.gov.br/anpd)
- [AWS Config Developer Guide - Custom Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules.html)
- [S3 Object Lock COMPLIANCE mode](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
