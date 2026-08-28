# Catálogo de Serviços AWS  Wayfinder Cloud / VitaCore Health

**Versão:** 1.0 | **Data:** 2026-08-21  
**Responsável:** Rafael Santos (CTO) | **Revisor:** Bruno Oliveira (SecOps)

---

## Legenda

- **Tier Core:** serviços sem os quais a aplicação VitaCore não funciona
- **Tier Supporting:** serviços que melhoram resiliência, segurança ou experiência
- **Tier Governance:** serviços do Wayfinder Cloud (Compliance e Audit)

---

## 1. Serviços Core  Aplicação VitaCore Health

### 1.1 Amazon ECS Fargate

| Atributo | Detalhe |
|---|---|
| **Categoria** | Compute  Containers |
| **Tier** | Core |
| **Função VitaCore** | Executa os microserviços da plataforma: vitacore-api (Spring Boot), vitacore-worker (processamento assíncrono), vitacore-telehealth (servidor de mídia) |
| **Configuração prod** | 4 tasks vitacore-api (0.5 vCPU/1GB), 2 tasks vitacore-worker (1 vCPU/2GB), 2 AZs |
| **Integração** | ECR (imagens), ALB (tráfego), Aurora (dados), ElastiCache (cache), Secrets Manager (credenciais), X-Ray (tracing), CloudWatch (logs) |
| **Config Rule** | WAYFINDER-006 (não em subnet pública), WAYFINDER-011 (não privileged) |
| **Cost mensal** | ~$35 (prod) / ~$4 (dev, 1 task) |
| **Justification** | Serverless  sem gerenciamento de SO, patching automático, escala por CPU/memória, integração nativa com IAM roles por task |
| **Alternativa descartada** | EKS: overhead operacional excessivo para time de 23 engenheiros sem experiência Kubernetes |

### 1.2 Amazon Aurora MySQL

| Atributo | Detalhe |
|---|---|
| **Categoria** | Database  Relacional |
| **Tier** | Core |
| **Função VitaCore** | 3 clusters: (1) prontuários + dados clínicos `health-critical`, (2) telemedicina + agendamentos, (3) legacy histórico (migração pendente para criptografia) |
| **Configuração** | db.r6g.large, Multi-AZ (writer us-east-1a / reader us-east-1b), backup retention 35 dias |
| **Integração** | ECS (cliente), Secrets Manager (credenciais rotadas 30d), KMS CMK (criptografia), AWS Backup (backup centralizado), CloudTrail (API audit) |
| **Config Rule** | WAYFINDER-004, `rds-storage-encrypted` |
| **Cost mensal** | ~$380 (prod) / ~$55 (dev, db.t4g.medium) |
| **Justification** | Failover automático < 30s vs RDS MySQL padrão (1-2 min), Performance Insights incluído, Serverless v2 para picos de carga |
| **Alternativa descartada** | DynamoDB: modelo relacional dos prontuários com JOINs complexos inviabiliza NoSQL |

### 1.3 Amazon ElastiCache Redis

| Atributo | Detalhe |
|---|---|
| **Categoria** | Cache  In-Memory |
| **Tier** | Core |
| **Função VitaCore** | Cache de sessões Cognito (TTL 30min), cache de queries frequentes de prontuários (TTL 5min), rate limiting de API (sliding window), pubsub para notificações internas |
| **Configuração** | cache.r6g.large, cluster mode desabilitado, 1 replica em us-east-1b, automatic-failover habilitado |
| **Integração** | ECS (cliente via TLS + AUTH token), KMS (at-rest encryption), AWS Backup |
| **Config Rule** | `elasticache-redis-cluster-automatic-backup` |
| **Cost mensal** | ~$145 (prod) / ~$15 (dev, cache.t4g.micro) |
| **Justification** | Reduz carga Aurora em 60% para queries repetitivas, TTL gerenciado automaticamente, persistência opcional para sessões |
| **Alternativa descartada** | DAX: específico para DynamoDB; não cobre cache de sessões e rate limiting |

### 1.4 Amazon S3  Buckets de Dados de Saúde

| Atributo | Detalhe |
|---|---|
| **Categoria** | Storage  Objeto |
| **Tier** | Core |
| **Função VitaCore** | 8 buckets: laudos de imagem (health-critical), gravações telemedicina (health-critical), backups Aurora (health-critical), dados wearables agregados (health-standard), relatórios financeiros (financial-sensitive), assets estáticos (public), Lambda packages (operational), Config reports (operational) |
| **Config aplicada** | SSE-KMS com CMK, Block Public Access habilitado em todos, Object Lock COMPLIANCE para buckets health-critical (7.305 dias) e financial-sensitive (3.650 dias) |
| **Integração** | CloudFront (signed URLs para laudos), Lambda (leitura/escrita), Glue (catalogação), Athena (queries), AWS Backup |
| **Config Rule** | WAYFINDER-001, WAYFINDER-002, WAYFINDER-013, `s3-bucket-public-read-prohibited` |
| **Cost mensal** | ~$11.50 (prod, 500GB) / ~$0.12 (dev) |
| **Justification** | 11 9s de durabilidade; Object Lock COMPLIANCE mode é o único mecanismo que garante imutabilidade legal dos prontuários por 20 anos |
| **Alternativa descartada** | EFS: desnecessário para objetos não estruturados; Cost 10x superior ao S3 |

### 1.5 Amazon DynamoDB

| Atributo | Detalhe |
|---|---|
| **Categoria** | Database  NoSQL |
| **Tier** | Core + Governance |
| **Função VitaCore** | (1) vitacore-wearable-data: dados de wearables (health-standard, partition: patient_id, sort: timestamp); (2) wayfinder-guardrail-state: estado de remediações em andamento para evitar loops (partition: resource_arn) |
| **Configuração** | PAY_PER_REQUEST, SSE com CMK, PITR habilitado |
| **Integração** | Lambda (leitura/escrita), Kinesis (ingestão wearable), Terraform state lock (tabela separada) |
| **Config Rule** | WAYFINDER-010, `dynamodb-table-encrypted-at-rest` |
| **Cost mensal** | ~$8 (prod, wearable volume) / ~$0.25 (dev) |
| **Justification** | Schema-less ideal para dados de wearables com Structure variável por dispositivo; PAY_PER_REQUEST elimina over-provisioning |

### 1.6 Amazon Kinesis Data Streams

| Atributo | Detalhe |
|---|---|
| **Categoria** | Streaming  Dados em Tempo Real |
| **Tier** | Core |
| **Função VitaCore** | Ingestão de ~2,4M eventos/dia de wearables (Garmin, Apple Watch, Fitbit) com garantia de ordem por patient_id |
| **Configuração** | 2 shards (1MB/s in, 2MB/s out por shard), retention 7 dias, server-side encryption KMS |
| **Integração** | API Gateway (produtor), Lambda (consumidor com batching 100 records), DynamoDB (destino), CloudWatch (métricas de shard) |
| **Config Rule** | Monitorado via CloudWatch Alarms (IteratorAgeMilliseconds) |
| **Cost mensal** | ~$22 (prod) / ~$0 (dev, on-demand) |
| **Justification** | Ordering por partition key (patient_id) que SQS não oferece; replay de 7 dias para reprocessamento; múltiplos consumidores (Lambda + Glue) |
| **Alternativa descartada** | SQS FIFO: limite de 300 msg/s por group ID inviabiliza volume de wearables; sem replay |

---

## 2. Serviços Supporting  Borda, Autenticação e Network

### 2.1 Amazon CloudFront

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | CDN para assets estáticos do app, entrega segura de laudos via signed URLs (validade 1h), proteção DDoS Layer 3/4 automática |
| **Configuração** | Price Class All (latência mínima), HTTPS only, TLS 1.2 min (1.3 preferido), Origin Shield habilitado, cache behaviors por path |
| **Integração** | Route 53, WAF, ACM, S3 (laudos), ALB (API origin) |
| **Config Rule** | `wafv2-webacl-not-empty` (WAF associado ao distribution) |
| **Cost mensal** | ~$4.25 (prod, 50GB transfer) |

### 2.2 AWS WAF

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | Proteção OWASP Top 10, rate limiting (1000 req/min por IP), bloqueio de bots maliciosos, proteção contra SQL injection e XSS |
| **Rules ativas** | AWSManagedRulesCommonRuleSet, AWSManagedRulesKnownBadInputsRuleSet, AWSManagedRulesSQLiRuleSet, rate-based rule |
| **Integração** | CloudFront, ALB |
| **Config Rule** | `wafv2-webacl-not-empty` |
| **Cost mensal** | ~$18 (2 WebACLs + Rules managed) |

### 2.3 Amazon Cognito

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | 2 User Pools: médicos (MFA TOTP obrigatório, sessão 8h) e pacientes (MFA SMS opcional, sessão 30 dias). Identity Pool para acesso temporário a S3 signed URLs |
| **Configuração** | Password policy: 12 chars min, upper+lower+digit+symbol; advanced security (bot detection) habilitado |
| **Integração** | ALB (JWT authorizer), API Gateway (authorizer), CloudFront (Lambda@Edge para autorização) |
| **Config Rule** | Monitorado via CloudWatch Insights (failed logins > 10/min  alarme) |
| **Cost mensal** | ~$5.50 (prod, 5k MAU médicos + 50k MAU pacientes) |
| **Justification** | Eliminação de código de auth customizado; HIPAA eligible service; integração nativa com ALB |
| **Alternativa descartada** | Auth0: Cost 5x superior em escala; dados fora da AWS (compliance LGPD preferência in-cloud) |

### 2.4 Amazon Route 53

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | DNS autoritativo para *.vitacore.health, health checks a cada 30s, failover para página de manutenção se ALB unhealthy |
| **Configuração** | Latency-based routing, private hosted zone para comunicação interna VPC, health checks HTTP + HTTPS |
| **Integração** | CloudFront (distribuição principal), ACM (validação de certificados) |
| **Cost mensal** | ~$1.00 (1 hosted zone + health checks) |

### 2.5 AWS Secrets Manager

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | 15 secrets: 3 credenciais Aurora (writer + reader + legacy), Redis AUTH token, 8 API keys de laboratórios e wearables, 2 chaves de integração operadoras, 1 Cognito client secret |
| **Rotação automática** | Aurora: Lambda rotator built-in a cada 30 dias; API keys externos: manual com alerta via WAYFINDER-012 |
| **Integração** | ECS (envFrom em task definition), Lambda (SDK call no init), Secrets Manager Rotation Lambda |
| **Config Rule** | WAYFINDER-014, `secretsmanager-rotation-enabled` |
| **Cost mensal** | ~$6.00 (15 secrets × $0.40) |
| **Justification** | Eliminação de credenciais hardcoded (origem do WAYFINDER-007); rotação automática sem downtime via dual-password strategy |
| **Alternativa descartada** | SSM Parameter Store SecureString: sem rotação automática, sem versionamento de segredos |

### 2.6 Amazon ECR

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | Registry privado para imagens Docker: vitacore-api, vitacore-worker, vitacore-telehealth, wayfinder-lambdas (para Lambdas empacotadas em container) |
| **Configuração** | Image scanning on push (Inspector v2), lifecycle policy: keep 10 latest + 30 days untagged, cross-region replication (futuro) |
| **Integração** | ECS (pull no deploy), Inspector v2 (scan), GitHub Actions (push no CI/CD), KMS (criptografia) |
| **Cost mensal** | ~$2.50 (10GB storage) |

### 2.7 AWS Certificate Manager (ACM)

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | Certificados TLS para vitacore.health, *.vitacore.health, APIs internas |
| **Configuração** | Renovação automática, validação via DNS (Route 53), certificados em us-east-1 (CloudFront) e us-east-1 (ALB) |
| **Cost mensal** | $0 (gratuito para certificados públicos ACM) |

### 2.8 AWS Systems Manager

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função VitaCore** | (1) Session Manager: acesso SSH-less a ECS tasks e EC2 para debug  substitui Bastion Host; (2) Parameter Store: feature flags, URLs de serviços externos, configs não-sensíveis; (3) Patch Manager: baseline de patches para AMIs base |
| **Integração** | IAM (roles com ssm:StartSession), CloudTrail (Audit de sessões), EC2 (SSM Agent) |
| **Config Rule** | `ec2-instance-managed-by-ssm` |
| **Cost mensal** | ~$0 (Session Manager e Parameter Store Standard gratuitos) |
| **Justification** | Elimina Bastion Host (economia de ~$15/mês por EC2 t3.micro) e acesso SSH na internet; Session Manager registra sessão no CloudTrail |

---

## 3. Serviços Governance  Wayfinder Core

### 3.1 AWS Config

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Motor central do Wayfinder Cloud: rastreia mudanças de configuração em todos os recursos, avalia Compliance contra 24 rules, dispara eventos para remediação |
| **Configuração** | all-supported resources, include_global_resource_types, continuous recording, snapshot diário, delivery channel S3 + SNS |
| **Rules** | 10 managed (pré-existentes) + 12 managed (novas) + 14 custom WAYFINDER-001 a 014 |
| **Integração** | EventBridge (eventos de non-compliance), S3 (snapshots), SNS (delivery notifications), Lambda (custom rules) |
| **Cost mensal** | ~$18 (prod) / ~$5 (dev) |

### 3.2 AWS CloudTrail

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Trilha imutável de TODA atividade da conta AWS: quem fez o quê, quando e de onde. Base para investigação forense e relatórios LGPD |
| **Configuração** | Multi-region trail, log file validation SHA-256, S3 data events para buckets health-*, RDS management events, CloudTrail Insights (anomalias) |
| **Destino** | S3 audit-trail (Object Lock COMPLIANCE 1.825 dias / 5 anos) criptografado com CMK |
| **Integração** | S3 (storage), Glue + Athena (análise), CloudWatch (métricas de uso), WAYFINDER-003 (Monitoring) |
| **Cost mensal** | ~$5 (data events) / $0 (management events no primeiro trail) |

### 3.3 Amazon EventBridge

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Barramento de eventos central do Wayfinder: roteia Config NON_COMPLIANT events, GuardDuty findings, Security Hub findings e CloudTrail events críticos para as Lambdas corretas |
| **Configuração** | Custom event bus `wayfinder-events`, 8 rules de roteamento por pattern matching, EventBridge Scheduler para relatório semanal |
| **Integração** | Config (fonte), GuardDuty (fonte), Security Hub (fonte), Lambda (destino), SQS DLQ (fallback) |
| **Cost mensal** | ~$0.01 (100k events) |

### 3.4 AWS Lambda  Funções de Governança

| Função | Papel | Trigger | Runtime | Cost/mês |
|---|---|---|---|---|
| `compliance-evaluator` | Enriquece e classifica eventos, aciona remediação | EventBridge direto (CRITICAL) + SQS (demais) | Python 3.12, 512MB, X-Ray | ~$0.10 |
| `auto-remediation` | Executa correções automáticas via SDK com guardrails | compliance-evaluator (invoke) | Python 3.12, 256MB, X-Ray | ~$0.05 |
| `incident-notifier` | Formata e envia alertas multi-canal (Slack, email, PagerDuty) | EventBridge (CRITICAL/HIGH) | Python 3.12, 128MB | ~$0.05 |
| `audit-reporter` | Gera relatório semanal de postura consultando Athena | EventBridge Scheduler (sexta 17h UTC) | Python 3.12, 512MB | ~$0.01 |

### 3.5 Amazon GuardDuty

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Detecção de ameaças com ML: reconhecimento de credenciais comprometidas, exfiltração de dados, comunicação com IPs maliciosos, acesso anômalo ao S3 |
| **Configuração** | finding_publishing_frequency = SIX_HOURS, S3 protection, EKS protection (futuro), Malware protection |
| **Integração** | EventBridge (findings  Lambda incident-notifier), Security Hub (findings centralizados), CloudTrail + DNS logs + VPC Flow Logs (fontes de análise) |
| **Config Rule** | `guardduty-enabled-centralized` |
| **Cost mensal** | ~$15 (prod, análise de VPC Flow Logs + DNS + CloudTrail) |
| **Justification** | GuardDuty teria detectado acesso anômalo ao bucket durante o incidente de março em ~1h via finding UnauthorizedAccess:S3/MaliciousIPCaller |

### 3.6 AWS Security Hub

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Visão consolidada de postura de segurança: agrega findings de GuardDuty, Inspector, Config, Macie. Score FSBP e CIS permite benchmark de maturidade |
| **Standards ativos** | AWS Foundational Security Best Practices v1.0.0, CIS AWS Foundations Benchmark v1.4.0 |
| **Meta de score** | FSBP > 85%, CIS > 80% em produção |
| **Integração** | EventBridge (findings HIGH/CRITICAL  Lambda), GuardDuty (fonte), Inspector (fonte), Config (fonte) |
| **Config Rule** | `securityhub-enabled` |
| **Cost mensal** | ~$3.50 (prod) |

### 3.7 AWS Inspector v2

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Varredura contínua de vulnerabilidades: CVEs em EC2 (OS + pacotes), vulnerabilidades em imagens ECR (no push e continuamente), network reachability |
| **Configuração** | EC2 scanning + ECR scanning habilitados, continuous scanning (não one-time) |
| **Integração** | Security Hub (findings), EventBridge (findings CRITICAL), ECR (trigger no push de imagem) |
| **Config Rule** | `inspector-ec2-scan-enabled` |
| **Cost mensal** | ~$4.50 (prod) |

### 3.8 Amazon Athena

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | SQL sobre CloudTrail logs, Config snapshots e dados de wearables. Investigação forense em incidentes, geração de relatórios LGPD, análise de postura semanal |
| **Workgroup** | `wayfinder-audit`: limite de $5/query (proteção contra scans acidentais), output criptografado com CMK |
| **Queries salvas** | 12 queries pré-construídas no Runbook RB-003 para cenários comuns |
| **Integração** | Glue Data Catalog (schema), S3 (source + results), Lambda audit-reporter |
| **Cost mensal** | ~$2.50 (50GB scan/mês) |

### 3.9 AWS Budgets

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Alertas de orçamento: Budget #1 Cost total (80% WARNING, 100% CRITICAL), Budget #2 EC2+RDS (70% WARNING para detectar over-provisioning) |
| **Integração** | SNS WARNING/CRITICAL, Cost Explorer (análise manual), Lambda audit-reporter (Cost semanal no relatório) |
| **Cost mensal** | $0 (até 2 budgets gratuitos) |

### 3.10 AWS Glue

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Crawler diário (03h UTC) que cataloga CloudTrail logs no Data Catalog do Athena. ETL job semanal para consolidar dados de wearables em Parquet particionado |
| **Configuração** | Crawler `wayfinder-cloudtrail-crawler`, database `wayfinder_audit`, trigger agendado |
| **Integração** | S3 (source), Data Catalog (output), Athena (consumidor) |
| **Cost mensal** | ~$1.50 (1 DPU × 2h/semana) |

### 3.11 Amazon SNS  Topics de Notificação

| Topic | Uso | Subscribers | Cost/mês |
|---|---|---|---|
| `wayfinder-critical` | Violações CRITICAL + incidentes LGPD | Email DPO + CTO + SecOps + PagerDuty + Slack (Chatbot) | ~$0.10 |
| `wayfinder-warning` | Violações HIGH + alertas de Cost | Email SecOps + Dev Lead + Slack | ~$0.05 |
| `wayfinder-info` | Violações MEDIUM + Config delivery | Email time de engenharia | ~$0.02 |

### 3.12 Amazon SQS  Dead Letter Queue

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | DLQ para eventos que falharam no processamento da Lambda compliance-evaluator após 3 tentativas. Preserva eventos para reprocessamento manual sem perda |
| **Configuração** | Standard queue, MessageRetentionPeriod 7 dias, alarme CloudWatch se profundidade > 10 |
| **Cost mensal** | ~$0 (< 1M mensagens) |

### 3.13 Amazon CloudWatch

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | (1) Log Groups para todas as Lambdas com KMS CMK (WAYFINDER-008); (2) Custom metrics namespace `wayfinder/Compliance`; (3) Dashboard "Wayfinder Command Center"; (4) 13 alarmes; (5) Log Insights queries pré-construídas |
| **Dashboard widgets** | % Compliant por serviço, violações por severidade 24h/7d/30d, top 5 recursos violadores, MTTR de remediação, status CloudTrail + Config Recorder |
| **Cost mensal** | ~$25 (prod: logs + metrics + dashboard + alarms) |

### 3.14 AWS X-Ray

| Atributo | Detalhe |
|---|---|
| **Tier** | Governance |
| **Função Wayfinder** | Tracing distribuído nas 4 Lambdas de governança para identificar gargalos e falhas no pipeline de Compliance |
| **Configuração** | Sampling: 5% + 100% para erros; trace propagation entre Lambdas via X-Ray SDK |
| **Cost mensal** | ~$0.50 |

---

## 4. Serviços de Infraestrutura

### 4.1 AWS KMS  Customer Managed Keys

| CMK | Dados Protegidos | Rotação | Política |
|---|---|---|---|
| `vitacore-health-critical-key` | S3 laudos/prontuários, Aurora clusters principais | Anual automática | Acesso: ECS task role + Lambda roles + DPO role |
| `vitacore-health-standard-key` | DynamoDB wearables, S3 health-standard | Anual automática | Acesso: Lambda processor role |
| `vitacore-financial-key` | RDS faturamento, S3 relatórios financeiros | Anual automática | Acesso: ECS billing role |
| `vitacore-audit-key` | S3 audit trail, CloudWatch Logs, CloudTrail | Anual automática | Acesso: CloudTrail service + Lambda audit-reporter |
| `vitacore-infra-key` | ECR, Secrets Manager, EBS, Kinesis | Anual automática | Acesso: ECS execution role + deploy pipeline |

### 4.2 AWS Backup

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função** | Backup centralizado com Vault Lock para Aurora (diário 35d + semanal 1a + mensal 7a), DynamoDB (diário 35d), EFS (se usado) |
| **Vault Lock** | COMPLIANCE mode  backup não pode ser deletado antes do período de retenção |
| **Config Rule** | `backup-plan-min-frequency-and-min-retention-check` |
| **Cost mensal** | ~$25 (prod, 1TB backup storage) |

### 4.3 AWS Organizations + SCPs

| SCP | Efeito | Justification |
|---|---|---|
| `deny-root-account-actions` | Bloqueia todas as ações da root account exceto billing | Nenhum humano deve usar root account |
| `require-mfa-for-console` | Nega console se não tiver MFA | Previne acesso comprometido |
| `require-encryption-at-rest` | Nega criação de recursos sem criptografia | Privacy by Default (LGPD art. 49) |
| `restrict-regions-to-us-east-1` | Nega ações fora de us-east-1 (exceto globais) | Soberania de dados no Brasil/EUA |
| `deny-s3-public-access-enable` | Nega desabilitar Block Public Access na conta | Previne o incidente de março |

### 4.4 IAM Identity Center (SSO)

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função** | Acesso humano com SSO via Google Workspace. Permission sets por função: ReadOnly, Developer, SecOps, DPO, Admin. MFA obrigatório para todos |
| **Justification** | Elimina IAM Users individuais (67 usuários legacy da VitaCore); centraliza Audit de acesso humano |

### 4.5 Amazon VPC + VPC Endpoints

| Atributo | Detalhe |
|---|---|
| **CIDR** | 10.0.0.0/16 (prod) / 10.10.0.0/16 (dev) |
| **Subnets** | Public (ALB, NAT GW): /24 × 2 AZs; Private App (ECS, Lambda): /24 × 2 AZs; Private Data (Aurora, Redis, DynamoDB): /24 × 2 AZs |
| **VPC Endpoints** | 2 Gateway (S3, DynamoDB  gratuito) + 9 Interface (Config, CloudTrail, CloudWatch, KMS, SNS, SQS, Secrets Manager, ECR, SSM) |
| **Justification** | Lambdas de governança não precisam de NAT GW para acessar APIs AWS  economiza ~$45/mês em prod e mantém tráfego dentro da Network AWS |

### 4.6 GitHub Actions + CI/CD

| Atributo | Detalhe |
|---|---|
| **Tier** | Supporting |
| **Função** | terraform-plan.yml: plan no PR + checagem de policy (OPA/Conftest); terraform-apply.yml: apply no merge para main (produção: requer aprovação manual) |
| **Segurança** | OIDC com IAM (sem access keys hardcoded no GitHub), environment secrets para tfvars sensíveis |
| **Integração** | ECR (push de imagens), ECS (deploy rolling update), Terraform state (S3 + DynamoDB) |
