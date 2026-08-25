# Wayfinder Cloud

**EN** | Cloud governance and compliance platform for regulated AWS environments.

**PT** | Plataforma de governança e conformidade cloud para ambientes AWS regulados.

---

> **EN** "As Wayfinders chart precise routes through unknown regions of space,
> Wayfinder Cloud guides AWS infrastructure through LGPD complexity,
> ensuring visibility, immutable audit trails, and real-time auto-remediation."
>
> **PT** "Assim como os Orientadores traçam rotas precisas por regioes desconhecidas do espaco,
> o Wayfinder Cloud guia a infraestrutura AWS pelas exigencias da LGPD,
> garantindo visibilidade, auditabilidade imutavel e auto-remediacao em tempo real."

---

## Overview / Visao Geral

**EN**
Wayfinder Cloud is a cloud governance platform designed for AWS environments
in regulated sectors. The initial focus is **digital health** under
**LGPD (Brazilian Data Protection Law - Lei 13.709/2018)**.

**PT**
Wayfinder Cloud e uma plataforma de governanca cloud projetada para ambientes
AWS em setores regulados. O foco inicial e **saude digital** sob a
**LGPD (Lei Geral de Protecao de Dados - Lei 13.709/2018)**.

**EN** This project demonstrates a Solutions Architect's ability to:
- Design event-driven architecture for continuous compliance
- Connect AWS technical controls to real legal obligations
- Automate remediation without manual intervention
- Document architectural decisions with professional ADRs
- Provision infrastructure as code with Terraform

**PT** Este projeto demonstra a capacidade de um Arquiteto de Solucoes de:
- Projetar arquitetura orientada a eventos para compliance continuo
- Conectar controles tecnicos AWS a obrigacoes legais reais
- Automatizar remediacao sem intervencao manual
- Documentar decisoes arquiteturais com ADRs profissionais
- Provisionar infraestrutura como codigo com Terraform

---

## The Problem / O Problema

**EN**
VitaCore Health is a fictional digital health startup processing records for
127,000 patients. In March 2026, a junior developer accidentally made an S3
bucket with 2,340 imaging reports publicly accessible. Nobody noticed for 18 days.
A patient discovered their own CT scan result via Google.

**PT**
VitaCore Health e uma startup ficticia de saude digital que processa dados de
127.000 pacientes. Em marco de 2026, um desenvolvedor junior tornou um bucket S3
com 2.340 laudos de imagem publicamente acessivel. Ninguem percebeu por 18 dias.
Um paciente encontrou seu proprio resultado de tomografia via Google.

| | Without Wayfinder / Sem Wayfinder | With Wayfinder / Com Wayfinder |
|---|---|---|
| Time to detect / Tempo de deteccao | 18 days / 18 dias | < 5 minutes / < 5 minutos |
| Auto-remediation / Remediacao auto | None / Nenhuma | Yes - Block Public Access |
| Audit trail / Trilha de auditoria | Unavailable / Indisponivel | Immutable 5 years / Imutavel 5 anos |
| ANPD notification / Notificacao ANPD | 67 days late / 67 dias apos | Template ready < 48h |
| Financial impact / Impacto financeiro | R$ 2,107,000 | R$ 0 |

---

## Architecture / Arquitetura

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
    |                    13 VPC Interface Endpoints (no internet for AWS)|
    |                                                                    |
    |  Private data:     Aurora MySQL Multi-AZ (patient records)        |
    |                    ElastiCache Redis (sessions, cache)             |
    |                    DynamoDB (wearable data, guardrails)            |
    +--------------------------------------------------------------------+

Compliance pipeline / Pipeline de conformidade:

    AWS Resource changes / Mudancas de recursos AWS
        |
        v
    AWS Config (37 rules: 23 managed + 14 custom WAYFINDER-001..014)
        |
        v
    Amazon EventBridge (wayfinder-events bus)
        |
        +---> Lambda compliance-evaluator --> SNS (CRITICAL / WARNING / INFO)
        |                                 --> Lambda auto-remediation
        |
        +---> CloudTrail --> S3 Object Lock --> Glue --> Athena
        |
        +---> GuardDuty + Security Hub (FSBP + CIS 1.4)
```

---

## LGPD Controls / Controles LGPD

**EN** Each AWS technical control is mapped to a specific LGPD article.
**PT** Cada controle tecnico AWS e mapeado para um artigo especifico da LGPD.

| LGPD Article / Artigo | Obligation / Obrigacao | AWS Control / Controle AWS |
|---|---|---|
| Art. 6, IV - Necessity | Minimum necessary access / Acesso minimo necessario | IAM Least Privilege, SCPs |
| Art. 37 - Records | Log all data operations / Registrar operacoes | CloudTrail multi-region |
| Art. 46 - Security | Technical protection / Protecao tecnica | KMS CMK, 37 Config Rules |
| Art. 48 - Incident notification | Notify ANPD in 72h / Notificar ANPD em 72h | SNS + Lambda, alert < 5 min |
| Art. 49 - Secure systems | Security by design / Seguranca desde a concepcao | IaC-only provisioning |
| Art. 50 - Best practices | Governance program / Programa de governanca | Security Hub FSBP + CIS 1.4 |

Full mapping / Mapeamento completo: [docs/compliance/lgpd-controls-mapping.md](docs/compliance/lgpd-controls-mapping.md)

---

## The 14 WAYFINDER Rules / As 14 Regras WAYFINDER

**EN** Custom AWS Config Rules built specifically for VitaCore's LGPD obligations.
**PT** Regras customizadas do AWS Config construidas para as obrigacoes LGPD da VitaCore.

| Rule / Regra | Description / Descricao | Auto-fix |
|---|---|---|
| WAYFINDER-001 | S3 health data without KMS CMK encryption | Yes |
| WAYFINDER-002 | S3 health data with public access enabled (March incident) | Yes |
| WAYFINDER-003 | CloudTrail disabled (was off 43 days unnoticed) | Yes |
| WAYFINDER-004 | RDS without encryption at rest | No |
| WAYFINDER-005 | IAM with admin permissions (Action: *) | No |
| WAYFINDER-006 | EC2 with health data in public subnet | Yes |
| WAYFINDER-007 | Credentials pattern in Lambda env vars | No |
| WAYFINDER-008 | CloudWatch Logs without KMS encryption | Yes |
| WAYFINDER-009 | Security Group with SSH/RDP open to internet | Yes |
| WAYFINDER-010 | DynamoDB without encryption at rest | No |
| WAYFINDER-011 | ECS Task with privileged=true | No |
| WAYFINDER-012 | IAM Access Key older than 90 days | No |
| WAYFINDER-013 | S3 without Object Lock for retention-required data | No |
| WAYFINDER-014 | Secrets Manager not used (possible hardcoded credentials) | No |

---

## Well-Architected Review Summary

**EN** Scored against the AWS Well-Architected Framework 2024 (6 pillars).
**PT** Avaliado com base no AWS Well-Architected Framework 2024 (6 pilares).

| Pillar / Pilar | Score | Status |
|---|---|---|
| Operational Excellence / Excelencia Operacional | 72/100 | Good / Bom |
| Security / Seguranca | 85/100 | Strong / Forte |
| Reliability / Confiabilidade | 70/100 | Good / Bom |
| Performance Efficiency / Eficiencia de Performance | 68/100 | Good / Bom |
| Cost Optimization / Otimizacao de Custos | 80/100 | Strong / Forte |
| Sustainability / Sustentabilidade | 45/100 | In development / Em desenvolvimento |

Full review / Revisao completa: [docs/architecture/well-architected-review.md](docs/architecture/well-architected-review.md)

---

## Technology Stack / Stack Tecnologica

```
IaC:       Terraform >= 1.6  (remote state: S3 + DynamoDB lock)
Runtime:   Python 3.12       (Lambdas with type hints, structured logging, X-Ray)
CI/CD:     GitHub Actions    (plan on PR, apply on merge, approval gate for prod)
Docs:      Markdown + ADRs + Mermaid + Runbooks
```

---

## Repository Structure / Estrutura do Repositorio

```
wayfinder-cloud/
+-- README.md
+-- CONTRIBUTING.md
+-- LICENSE
+--
+-- docs/
|   +-- adr/                          # 9 Architecture Decision Records
|   +-- architecture/
|   |   +-- architecture-overview.md  # Full diagram + data flows / Diagrama completo
|   |   +-- well-architected-review.md
|   |   +-- service-catalog.md        # 35+ AWS services documented
|   +-- compliance/
|   |   +-- lgpd-controls-mapping.md  # LGPD to AWS controls / LGPD para controles AWS
|   +-- business/
|   |   +-- vitacore-scenario.md      # Incident post-mortem / Post-mortem do incidente
|   +-- runbooks/
|       +-- RB-001 to RB-005          # Operational procedures / Procedimentos operacionais
|
+-- infra/
|   +-- modules/                      # 8 reusable Terraform modules / 8 modulos reutilizaveis
|   |   +-- networking/               # VPC, subnets, endpoints
|   |   +-- iam/                      # Roles with least privilege
|   |   +-- storage/                  # KMS + S3 Object Lock
|   |   +-- notifications/            # SNS + Chatbot Slack
|   |   +-- compliance/               # Config Recorder + 37 Rules
|   |   +-- observability/            # CloudTrail + EventBridge + Lambda + CloudWatch
|   |   +-- remediation/              # Auto-remediation + DynamoDB guardrail
|   |   +-- security/                 # GuardDuty + Security Hub + Inspector + Budgets
|   +-- environments/
|       +-- dev/                      # Object Lock GOVERNANCE, force_destroy=true
|       +-- prod/                     # Object Lock COMPLIANCE, approval required
|
+-- src/
|   +-- lambdas/
|   |   +-- compliance-evaluator/     # Evaluates events + LGPD context
|   |   +-- auto-remediation/         # Fixes with guardrails / Corrige com guardrails
|   |   +-- incident-notifier/        # Slack + email alerts / Alertas Slack + email
|   |   +-- audit-reporter/           # Weekly Athena reports / Relatorios Athena semanais
|   +-- tests/
|
+-- scripts/
|   +-- bootstrap_state.py            # One-time state backend setup
|
+-- .github/
    +-- workflows/
        +-- terraform-plan.yml        # Plan on every PR
        +-- terraform-apply.yml       # Deploy pipeline with approval gates
        +-- lambda-deploy.yml         # Lambda test, package, deploy, smoke test
```

---

## Architecture Decision Records

**EN** Every significant architectural choice is documented with context, options, decision, and trade-offs.
**PT** Cada escolha arquitetural significativa e documentada com contexto, opcoes, decisao e trade-offs.

| ADR | Decision / Decisao | Status |
|---|---|---|
| ADR-001 | Terraform over CDK/CloudFormation | Accepted |
| ADR-002 | Event-driven compliance vs periodic polling | Accepted |
| ADR-003 | S3 Object Lock COMPLIANCE + Athena for audit trail | Accepted |
| ADR-004 | Selective auto-remediation with risk matrix | Accepted |
| ADR-005 | CloudWatch native over DataDog/New Relic | Accepted |
| ADR-006 | Security Hub with FSBP + CIS 1.4 | Accepted |
| ADR-007 | Defense in depth - 7 independent security layers | Accepted |
| ADR-008 | Secrets Manager (post-incident: hardcoded creds found) | Accepted |
| ADR-009 | VPC Endpoints strategy (177x security ROI vs NAT-only) | Accepted |

---

## Quick Start / Inicio Rapido

```bash
# EN: Clone the repository / PT: Clone o repositorio
git clone https://github.com/guinatural/wayfinder-cloud.git
cd wayfinder-cloud

# EN: Configure AWS credentials / PT: Configure as credenciais AWS
aws configure --profile wayfinder-dev

# EN: Bootstrap Terraform state backend (one-time only)
# PT: Inicializar o backend do estado Terraform (apenas uma vez)
python scripts/bootstrap_state.py --env dev --region us-east-1

# EN: Copy and fill variables / PT: Copie e preencha as variaveis
cp infra/environments/dev/terraform.tfvars.example \
   infra/environments/dev/terraform.tfvars

# EN: Initialize and apply / PT: Inicialize e aplique
cd infra/environments/dev
terraform init
terraform plan
terraform apply
```

Full guide / Guia completo: [docs/runbooks/RB-002-terraform-operations.md](docs/runbooks/RB-002-terraform-operations.md)

---

## Cost Estimate / Estimativa de Custo

| Environment / Ambiente | Monthly / Mensal (USD) |
|---|---|
| Dev (governance only / apenas governanca) | ~$38 |
| Prod (full VitaCore stack / stack completo) | ~$870 |
| Annual prevention cost / Custo anual de prevencao | ~$1,236 |
| Cost of one similar incident / Custo de um incidente similar | ~$420,000+ |
| Return on investment / Retorno sobre investimento | 340x |

---

## Author / Autor

**Guilherme Barreto Gomes**

AWS Solutions Architect | Cloud Security | LGPD

[GitHub](https://github.com/guinatural)

---

## License / Licenca

MIT - see [LICENSE](LICENSE) for details / veja [LICENSE](LICENSE) para detalhes.
