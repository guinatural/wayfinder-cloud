#  Guia de Publicação no GitHub  Wayfinder Cloud

**Para:** Guilherme Barreto Gomes  
**Objetivo:** Publicar o projeto em partes, de forma profissional, construindo  
o histórico de commits como um arquiteto sênior faria num projeto real.

---

## Por que publicar em partes (e não tudo de uma vez)

Publicar tudo em um commit `initial commit` desperdiça o maior ativo do repositório:
o **histórico de decisões**. Qualquer pessoa que visitar o repo vai ver que as
escolhas arquiteturais foram feitas com intenção, não jogadas de uma vez.

Um histórico bem construído responde, sem você precisar explicar:
- Por que Terraform e não CDK?
- Por que event-driven e não polling?
- Por que S3 Object Lock para auditoria?

---

## Sequência de Publicação (12 commits)

### Fase 1  Fundação (commits 13)

**Commit 1  Scaffold inicial**
```bash
git init
git add README.md .gitignore LICENSE CONTRIBUTING.md
git commit -m "docs: add project scaffold and README

Wayfinder Cloud  plataforma de governança cloud para saúde digital
sob LGPD. Inclui README com pitch técnico, cenário VitaCore Health
e arquitetura em alto nível."
```

**Commit 2  Cenário de negócio e documentação**
```bash
git add docs/business/ docs/compliance/ docs/architecture/
git commit -m "docs: add business context, LGPD mapping and architecture

- VitaCore Health scenario: incidente de março 2026, impacto R$ 2.1M
- LGPD controls mapping v2.0: arts. 5, 6, 11, 37, 46-50
- Architecture overview: diagrama Mermaid completo, 35+ serviços AWS
- Service catalog: justificativa técnica por serviço"
```

**Commit 3  ADRs**
```bash
git add docs/adr/
git commit -m "docs(adr): add architecture decision records 001-009

ADR-001: Terraform over CDK/CloudFormation
ADR-002: Event-driven compliance (Config -> EventBridge -> Lambda)
ADR-003: S3 Object Lock + Athena for immutable audit trail
ADR-004: Selective auto-remediation strategy
ADR-005: CloudWatch native vs DataDog/New Relic
ADR-006: Security Hub with FSBP + CIS 1.4
ADR-007: Defense in depth (7 security layers)
ADR-008: Secrets Manager over env vars (post-incident lesson)
ADR-009: VPC Endpoints strategy (ROI 177x vs NAT-only)"
```

---

### Fase 2  Infraestrutura Base (commits 46)

**Commit 4  Módulos storage e IAM**
```bash
git add infra/modules/storage/ infra/modules/iam/
git commit -m "feat(infra): add storage and IAM modules

storage:
- KMS CMK with annual rotation (CIS 3.8)
- S3 audit trail with Object Lock COMPLIANCE mode
- S3 lifecycle: Standard -> Glacier after 90 days
- Bucket policy: deny HTTP, restrict to account

iam:
- AWS Config role with least privilege
- Lambda evaluator role: SNS, CW, EventBridge, Config, X-Ray
- Lambda remediation role: S3, CloudTrail, EC2, DynamoDB
- Lambda reporter role: Athena, S3, Glue, SNS"
```

**Commit 5  Módulos networking e notifications**
```bash
git add infra/modules/networking/ infra/modules/notifications/
git commit -m "feat(infra): add networking and notifications modules

networking:
- VPC 10.0.0.0/16 with public/private subnets across 2 AZs
- NAT Gateway for external API calls
- 13 VPC Interface Endpoints (Config, CloudTrail, KMS, SNS, etc.)
- S3 and DynamoDB Gateway Endpoints (free)
- Lambda SG: egress HTTPS only, no ingress

notifications:
- SNS Topics: CRITICAL, WARNING, INFO (all KMS-encrypted)
- Email subscriptions with topic policies
- AWS Chatbot Slack integration (conditional)"
```

**Commit 6  Módulos compliance e security**
```bash
git add infra/modules/compliance/ infra/modules/security/
git commit -m "feat(infra): add compliance and security modules

compliance:
- AWS Config Recorder (all resources, global)
- Delivery channel to S3 audit bucket
- 23 Managed Rules (CloudTrail, KMS, IAM, RDS, S3, WAF, Backup...)
- 14 Custom Rules WAYFINDER-001..014 (LGPD art. 46-50, CFM)

security:
- GuardDuty with S3 protection and malware scan
- Security Hub: FSBP v1.0.0 + CIS 1.4 standards
- Inspector v2: EC2 + ECR continuous scanning
- AWS Budgets: monthly total (80%/100% alerts) + compute breakdown
- EventBridge: GuardDuty/SecHub findings -> compliance-evaluator"
```

---

### Fase 3  Observabilidade e Remediação (commits 78)

**Commit 7  Módulo observability**
```bash
git add infra/modules/observability/
git commit -m "feat(infra): add observability module

- CloudTrail multi-region with log file validation
- CloudTrail S3 data events for health-classified buckets
- EventBridge bus 'wayfinder-events' with 5 routing rules:
  Config NON_COMPLIANT, root login, IAM changes, GuardDuty, SecHub
- Lambda compliance-evaluator (Python 3.12, X-Ray, VPC)
- Lambda audit-reporter (weekly Athena queries, scheduled)
- CloudWatch: 4 log groups (KMS), 3 alarms, dashboard
- Athena workgroup 'wayfinder-audit' with scan limits
- Glue crawler for CloudTrail log cataloging"
```

**Commit 8  Módulo remediation**
```bash
git add infra/modules/remediation/
git commit -m "feat(infra): add remediation module

- Lambda auto-remediation: Python 3.12, X-Ray, VPC, DLQ
- Lambda incident-notifier: Slack Block Kit, structured logging
- DynamoDB guardrail table: anti-loop, TTL, PITR, KMS
- SQS DLQ for both Lambdas (14-day retention)
- EventBridge rule: WayfinderAutoRemediation -> Lambda
- Remediation actions: S3 public access, S3 KMS, CloudTrail, EC2 SG"
```

---

### Fase 4  Ambientes e CI/CD (commits 911)

**Commit 9  Ambiente dev**
```bash
git add infra/environments/dev/
git commit -m "feat(env): add dev environment configuration

- Remote state: S3 + DynamoDB lock (wayfinder-cloud-tfstate-dev)
- All 7 modules wired with correct dependencies
- Object Lock GOVERNANCE mode (dev-safe, reversible)
- Budget limit: $150/month
- audit_retention_days: 90
- Force destroy enabled (dev only)"
```

**Commit 10  Ambiente prod**
```bash
git add infra/environments/prod/
git commit -m "feat(env): add prod environment configuration

- Remote state: S3 + DynamoDB lock (wayfinder-cloud-tfstate-prod)
- Object Lock COMPLIANCE mode (legally immutable, irreversible)
- Budget limit: $1050/month
- audit_retention_days: 365
- Force destroy disabled (production safeguard)
- Dual NAT Gateway for high availability"
```

**Commit 11  CI/CD e scripts**
```bash
git add .github/ scripts/
git commit -m "ci: add GitHub Actions workflows and bootstrap script

terraform-plan.yml: runs on PR, posts plan as comment
terraform-apply.yml: dev -> prod pipeline with manual approval gate
lambda-deploy.yml: test -> package -> deploy -> smoke test

scripts/bootstrap_state.py:
- Creates S3 state bucket (versioning, encryption, HTTPS-only policy)
- Creates DynamoDB lock table
- One-time setup before first terraform init"
```

---

### Fase 5  Lambda Code e Testes (commit 12)

**Commit 12  Código das Lambdas e testes**
```bash
git add src/
git commit -m "feat(lambda): add governance Lambda functions and unit tests

compliance-evaluator:
- Processes Config NON_COMPLIANT and GuardDuty events
- Maps 14 WAYFINDER rules to LGPD articles
- Publishes CloudWatch metrics and SNS notifications
- Triggers auto-remediation for eligible violations

auto-remediation:
- Guardrails: remediation-exempt tag, 3-attempt limit
- Actions: S3 Block Public Access, SSE-KMS, CloudTrail restart, EC2 SG
- Structured JSON logging for audit trail

incident-notifier:
- Slack Block Kit with severity emoji/color
- LGPD article context in every alert
- urllib native (no extra dependencies)

audit-reporter:
- Weekly Athena queries: violations, MTTR, compliance %
- JSON report saved to S3 with immutable metadata
- Executive summary published to SNS INFO

tests:
- conftest.py with moto fixtures
- test_compliance_evaluator.py covering parsing, severity, SNS"
```

---

## Comandos Git para executar

```bash
# 1. Criar o repositório no GitHub (via gh CLI ou interface web)
gh repo create wayfinder-cloud --public --description "Cloud governance platform for regulated environments (LGPD + AWS)"

# 2. Conectar o repositório local
cd c:\Users\barre\Documents\Codex\2026-08-15\me-ajude\work\wayfinder-cloud
git init
git remote add origin https://github.com/SEU_USUARIO/wayfinder-cloud.git

# 3. Executar os commits na sequência acima (commits 1-12)
# Cada commit conta a história de uma decisão

# 4. Push final
git push -u origin main

# 5. Criar tags de versão
git tag -a v0.1.0 -m "MVP: compliance + observability core modules"
git push origin v0.1.0
```

---

## Configurar o repositório no GitHub

Após o push, configure:

**Settings > Secrets and variables > Actions:**
```
AWS_ACCESS_KEY_ID_DEV       credencial IAM para wayfinder-dev
AWS_SECRET_ACCESS_KEY_DEV   credencial IAM para wayfinder-dev
AWS_ACCESS_KEY_ID_PROD      credencial IAM para wayfinder-prod
AWS_SECRET_ACCESS_KEY_PROD  credencial IAM para wayfinder-prod
ALERT_EMAIL                 seu email para alertas SNS
```

**Settings > Environments:**
- Criar `dev` (sem proteção)
- Criar `prod` (com required reviewer: você mesmo)
- Criar `prod-approval` (com required reviewer: você mesmo)

**Settings > General:**
- Branch protection em `main`: require PR, require status checks (terraform-plan)

**About (sidebar):**
```
Description: Cloud governance platform for AWS regulated environments (LGPD)
Topics: aws terraform python compliance lgpd cloud-security guardduty
Website: (deixar vazio por enquanto)
```

---

## Ordem de publicação recomendada para LinkedIn

Ao publicar cada fase, pode mencionar:

- **Fase 1 (commits 1-3):** "Documentei o problema de negócio antes de escrever uma linha de código."
- **Fase 2 (commits 4-6):** "IaC com Terraform: módulos de storage, IAM, rede e compliance."
- **Fase 3 (commits 7-8):** "Pipeline de conformidade event-driven: Config  EventBridge  Lambda."
- **Fase 4 (commits 9-11):** "Ambientes dev e prod com CI/CD completo e aprovação manual em prod."
- **Fase 5 (commit 12):** "Código Python das Lambdas com testes unitários usando moto."

---

## Checklist antes do primeiro push

- [ ] Copiar `terraform.tfvars.example` para `terraform.tfvars` e preencher localmente
- [ ] Confirmar que `terraform.tfvars` está no `.gitignore`
- [ ] Executar `scripts/bootstrap_state.py --env dev` para criar o backend
- [ ] Executar `terraform init && terraform validate` em `infra/environments/dev`
- [ ] Revisar que nenhum dado pessoal ou credencial está em nenhum arquivo
- [ ] Confirmar que `LICENSE` tem seu nome correto
- [ ] Atualizar links do LinkedIn e GitHub no `README.md`
