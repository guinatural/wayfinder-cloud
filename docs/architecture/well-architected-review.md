# AWS Well-Architected Review  Wayfinder Cloud

**Projeto:** Wayfinder Cloud  Plataforma de Governança Cloud para Saúde Digital  
**Cliente fictício:** VitaCore Health  
**Data:** 2026-08-21 | **Versão:** 2.0  
**Revisor:** Guilherme Barreto Gomes (AWS Solutions Architect)  
**Framework:** AWS Well-Architected Framework 2024  6 Pilares  
**Ferramenta de referência:** [AWS Well-Architected Tool](https://console.aws.amazon.com/wellarchitected/)

---

## Resumo Executivo

| Pilar | Score (0100) | Maturidade | Alto Risco | Médio Risco |
|---|---|---|---|---|
| Excelência Operacional | 72 |  Bom | 0 | 3 |
| Segurança | 85 |  Forte | 0 | 2 |
| Confiabilidade | 70 |  Bom | 0 | 4 |
| Eficiência de Performance | 68 |  Bom | 0 | 3 |
| Otimização de Custos | 80 |  Forte | 0 | 2 |
| Sustentabilidade | 45 |  Em desenvolvimento | 0 | 3 |
| **Geral** | **70** | ** Bom** | **0** | **17** |

> Metodologia: perguntas respondidas com base nos controles implementados no Terraform.
> Score = (controles implementados / total de controles relevantes) × 100.

---

## Pilar 1  Excelência Operacional

> "A capacidade de suportar o desenvolvimento e executar cargas de trabalho de forma  
> eficaz, obter insights sobre suas operações e melhorar continuamente processos e  
> procedimentos para gerar valor para o negócio."*

**Score: 72/100 | Maturidade:  Bom**

### OPS 1  Como você determina quais prioridades de negócio guiam suas operações?

**Resposta:** O projeto mapeia explicitamente os controles técnicos a obrigações da LGPD
(arts. 46, 48, 50) e ao risco de negócio (incidente VitaCore de R$ 2,1M). A prioridade
operacional é definida pela severidade do compliance: CRITICAL > HIGH > MEDIUM > LOW.

**Controles implementados:**
-  Mapeamento LGPD  controles técnicos em `docs/compliance/lgpd-controls-mapping.md`
-  Matriz de impacto do incidente de março documentada com custo evitado estimado
-  OKRs do projeto definidos em `docs/business/vitacore-scenario.md` (seção 4)
-  SLAs definidos por severidade: CRITICAL < 15 min, HIGH < 2h, MEDIUM < 24h

**Gaps (Médio Risco):**
-  Sem métricas de negócio conectadas aos alarmes de compliance (ex: "X violações = Y risco de multa")
-  Runbook de onboarding de novo membro do time não existe

### OPS 2  Como você estrutura sua organização para suportar seus objetivos de negócio?

**Resposta:** 5 personas documentadas com responsabilidades claras (DPO, CTO, SecOps, Dev Lead, Auditores).
Runbooks RB-001 a RB-005 cobrem os principais cenários operacionais.

**Controles implementados:**
-  Personas e responsabilidades em `docs/business/vitacore-scenario.md` (seção 5)
-  RB-001: Resposta a incidentes LGPD art. 48
-  RB-002: Operações Terraform (bootstrap, plan, apply, rollback)
-  RB-003: Queries Athena para investigação forense
-  RB-004: Resposta a GuardDuty findings
-  RB-005: Governança de custo

### OPS 3  Como você projeta sua carga de trabalho para entender seu estado?

**Resposta:** Todas as Lambdas emitem logs estruturados JSON compatíveis com
CloudWatch Logs Insights. Métricas customizadas no namespace `Wayfinder/Compliance`
permitem dashboards e alarmes sobre o estado do compliance.

**Controles implementados:**
-  Structured logging (JSON) em compliance-evaluator, auto-remediation, incident-notifier, audit-reporter
-  CloudWatch custom metrics: `NonCompliantResource`, `ComplianceScore`, `RemediationAttempt`
-  AWS X-Ray tracing nas Lambdas críticas (sampling 5% + 100% em erros)
-  CloudWatch Dashboard "Wayfinder Command Center" com 12 widgets
-  CloudTrail multi-region captura 100% das API calls

### OPS 4  Como você reduz defeitos, facilita remediação e melhora o fluxo em produção?

**Controles implementados:**
-  IaC 100% Terraform  sem mudanças manuais em recursos gerenciados
-  GitHub Actions: `terraform-plan.yml` bloqueia merge sem plan aprovado
-  `terraform-apply.yml`: pipeline dev  aprovação  prod
-  Conventional Commits como padrão de histórico
-  ADR-001 a ADR-009 documentam todas as decisões relevantes

**Gaps (Médio Risco):**
-  Sem `terraform test` automatizado nos módulos
-  Testes unitários Python criados mas sem cobertura de integração

### OPS 5  Como você mitiga riscos de implantação?

**Controles implementados:**
-  Ambientes separados: dev (force_destroy=true, GOVERNANCE) / prod (COMPLIANCE)
-  GitHub Environments com required reviewer para prod
-  `terraform plan` exposto como comentário no PR antes de qualquer apply
-  Lambda deploy separado do Terraform (lambda-deploy.yml)
-  Smoke test automático após deploy de cada Lambda

### OPS 6  Como você entende os eventos operacionais que afetam sua carga de trabalho?

**Controles implementados:**
-  CloudWatch Alarms: 3 alarmes críticos + 5 de aviso
-  SNS 3 topics com SLAs de resposta documentados
-  AWS Chatbot integra com Slack para alertas em tempo real
-  GuardDuty findings  EventBridge  Lambda incident-notifier (< 2 min)
-  Config NON_COMPLIANT  EventBridge  compliance-evaluator (< 5 min)

**Gaps (Médio Risco):**
-  Sem runbook de Game Day (simulação de incidente para testar os alertas)

---

## Pilar 2  Segurança

> "A capacidade de proteger dados, sistemas e ativos para aproveitar as tecnologias  
> de nuvem e melhorar sua postura de segurança."*

**Score: 85/100 | Maturidade:  Forte**

### SEC 1  Como você gerencia identidades para pessoas e máquinas?

**Resposta:** IAM Identity Center (SSO) para humanos, IAM Roles com least privilege para máquinas.
Sem IAM Users com access keys de longa duração para serviços (apenas para CI/CD temporariamente).

**Controles implementados:**
-  IAM Roles separadas por função: evaluator, remediation, reporter, config
-  Sem `AdministratorAccess` em produção (WAYFINDER-005 detecta)
-  IAM Identity Center (SSO) via Google Workspace para acesso humano
-  MFA obrigatório para console (Config Rule `mfa-enabled-for-iam-console-access`)
-  Root account: sem access keys (Config Rule `iam-root-access-key-check`)
-  WAYFINDER-012: access keys rotacionadas a cada 90 dias
-  SCPs: `deny-root-account-actions`, `require-mfa-for-console`

**Gaps (Médio Risco):**
-  CI/CD ainda usa access keys estáticas  migrar para OIDC + IAM Role

### SEC 2  Como você gerencia permissões para pessoas e máquinas?

**Controles implementados:**
-  `data "aws_iam_policy_document"` com conditions onde possível (`aws:ResourceAccount`, `cloudwatch:namespace`)
-  SCP `require-encryption-at-rest` aplica criptografia como condição de conta
-  Resource-based policies no S3 com `DenyNonTLS` e `AllowOnlyAccount`
-  Permission Boundaries documentados para equipe de desenvolvimento
-  WAYFINDER-005 detecta `Action: "*", Resource: "*"` em qualquer policy

### SEC 3  Como você detecta e investiga eventos de segurança?

**Controles implementados:**
-  CloudTrail multi-region + log file validation (SHA-256)
-  CloudTrail data events para S3 (todos os GET/PUT em buckets health-*)
-  GuardDuty: CloudTrail + VPC Flow Logs + DNS Logs + S3 protection
-  Security Hub: FSBP v1.0 + CIS 1.4 com score-alvo > 85%
-  Inspector v2: CVEs em EC2 e ECR (continuous scanning)
-  Config + EventBridge: detecção em < 5 min de qualquer mudança de configuração
-  RB-004: procedimento documentado para cada família de GuardDuty finding
-  RB-003: queries Athena prontas para investigação forense

### SEC 4  Como você protege suas redes?

**Controles implementados:**
-  VPC com 3 camadas de subnet: public (ALB/NAT) / private app (ECS/Lambda) / private data (RDS/Redis)
-  Security Groups com least privilege: sg-alb  sg-app  sg-data (sem egress em sg-data)
-  VPC Endpoints: 13 Interface + 2 Gateway  sem tráfego de dados pela internet
-  VPC Flow Logs habilitados (Config Rule `vpc-flow-logs-enabled`)
-  AWS WAF: OWASP Top 10, rate limiting, SQL Injection, Known Bad Inputs
-  CloudFront como origin shield + DDoS Layer 3/4 automático
-  WAYFINDER-009: Security Group com SSH/RDP público detectado e remediado
-  WAYFINDER-006: EC2 com dados de saúde em subnet pública  quarentena automática
-  ADR-009: VPC Endpoints strategy com análise de custo-benefício

### SEC 5  Como você protege seus recursos computacionais?

**Controles implementados:**
-  ECS Fargate: sem gerenciamento de SO, patches automáticos pela AWS
-  Inspector v2: vulnerabilidades CVE em imagens ECR e EC2
-  ECR: image scanning on push, lifecycle policy (keep 10 latest)
-  Systems Manager Session Manager: sem SSH/Bastion Host necessário
-  WAYFINDER-011: ECS Task com `privileged=true` detectado

**Gaps (Médio Risco):**
-  Sem Patch Manager configurado para EC2 (caso haja)
-  Sem AWS Shield Advanced (custo $3.000/mês  roadmap para scale)

### SEC 6  Como você classificar seus dados?

**Controles implementados:**
-  5 níveis de classificação: health-critical, health-standard, financial-sensitive, operational, public
-  Tags `DataClassification` obrigatórias via SCP e WAYFINDER-015
-  KMS CMK por classificação: 5 chaves dedicadas
-  S3 Object Lock COMPLIANCE para dados health-critical (retenção 20 anos / CFM)
-  Diferentes controles técnicos por nível (documentados em lgpd-controls-mapping.md)

### SEC 7  Como você protege seus dados em repouso?

**Controles implementados:**
-  S3: SSE-KMS com CMK dedicado por classificação + `bucket_key_enabled=true`
-  Aurora MySQL: StorageEncrypted=true + KMS CMK (WAYFINDER-004)
-  DynamoDB: SSE com CMK (WAYFINDER-010)
-  ElastiCache Redis: criptografia at-rest + in-transit
-  CloudWatch Logs: KMS CMK (WAYFINDER-008)
-  SQS DLQ: KMS
-  SNS Topics: KMS
-  KMS key rotation anual habilitada em todas as CMKs (CIS 3.8)
-  Managed Rule `encrypted-volumes`: EBS criptografados

### SEC 8  Como você proteger seus dados em trânsito?

**Controles implementados:**
-  TLS 1.3 em CloudFront e ALB (TLS 1.2 mínimo)
-  S3 bucket policy: `DenyNonTLS` bloqueia HTTP
-  VPC Endpoints: tráfego AWS APIs nunca sai da rede AWS
-  Aurora: `enforce_ssl=1` na parameter group
-  ElastiCache: `in-transit-encryption=true`
-  Lambda  serviços AWS: HTTPS obrigatório via SDK padrão

### SEC 9  Como você antecipar, responder e se recuperar de incidentes?

**Controles implementados:**
-  RB-001: processo completo de 6 fases (detecção  ANPD em 48h)
-  Pipeline automático: Config/GuardDuty  Lambda  SNS/remediação em < 5 min
-  Template de comunicação ANPD pré-preenchido pelo audit-reporter
-  Runbook RB-004 por família de GuardDuty finding
-  S3 Object Lock garante preservação de evidências forenses

**Gaps (Médio Risco):**
-  Sem Game Day documentado (simulação de incidente LGPD)
-  Processo de notificação individual de titulares (LGPD art. 48) não automatizado

---

## Pilar 3  Confiabilidade

> "A capacidade de uma carga de trabalho executar sua função pretendida corretamente  
> e de forma consistente quando é esperado."*

**Score: 70/100 | Maturidade:  Bom**

### REL 1  Como você gerencia os limites de serviço?

**Controles implementados:**
-  Lambda concurrency: sem reserva explícita (burst limit da conta)
-  DynamoDB PAY_PER_REQUEST: sem throttling por provisioning
-  Config Rules: limite de 300 rules  projeto usa ~37 (12%)
-  EventBridge: limite de 300 rules por bus  projeto usa ~8 (< 3%)

**Gaps (Médio Risco):**
-  Sem Service Quotas Alerts configurados para Lambda concurrency e Config rules
-  Sem análise de limites de Kinesis shards para volume de wearables

### REL 2  Como você planeja sua topologia de rede?

**Controles implementados:**
-  VPC com 2 AZs: us-east-1a e us-east-1b
-  Subnets por tier: public / private-app / private-data
-  IGW + NAT GW: conectividade controlada
-  VPC Endpoints: elimina dependência de internet para APIs AWS
-  Route tables separadas por subnet tier

**Gaps (Médio Risco):**
-  NAT Gateway single-AZ em dev (intencional)  prod usa dual-AZ
-  Sem análise de IP exhaustion nos CIDRs (10.0.0.0/24 = 251 hosts/subnet)

### REL 3  Como você projeta sua carga de trabalho para resistir a falhas?

**Controles implementados:**
-  ECS Fargate: tasks distribuídas em 2 AZs com ALB health checks
-  Aurora Multi-AZ: writer us-east-1a + reader us-east-1b, failover < 30s
-  ElastiCache Redis: primary + replica em AZs diferentes
-  SQS DLQ: eventos de compliance não são perdidos mesmo se Lambda falhar
-  EventBridge retry automático (até 24h para eventos não entregues)
-  Lambdas stateless: qualquer falha é idempotente, sem side effects
-  DynamoDB: Global Table option disponível para DR multi-region

**Gaps (Médio Risco):**
-  Sem circuit breaker entre compliance-evaluator e SNS
-  Sem teste de failover Aurora documentado

### REL 4  Como você projeta sua carga de trabalho para se recuperar de falhas?

**Controles implementados:**
-  AWS Backup: Aurora (diário/semanal/mensal), DynamoDB (PITR 35d), Vault Lock
-  S3 Object Lock + versionamento: recovery de objetos deletados
-  Terraform state em S3 com versionamento: rollback de infra possível
-  Lambda DLQ + `terraform apply` = recovery de pipeline de compliance

**Gaps (Médio Risco):**
-  RTO/RPO não definidos formalmente por componente
-  Sem DR plan para região us-east-1 completa (future: us-east-2 failover)
-  Teste de restore do Aurora não documentado no runbook

### REL 5  Como você monitorar a carga de trabalho?

**Controles implementados:**
-  CloudWatch Alarms: noncompliant_critical, noncompliant_high_volume, evaluator_errors
-  SNS alertas para CTO, DPO e SecOps com SLA de resposta definido
-  CloudWatch Logs Insights: queries pré-construídas no RB-003
-  X-Ray: service map e traces para debugging do pipeline

---

## Pilar 4  Eficiência de Performance

> "A capacidade de usar recursos de computação de forma eficiente para atender aos  
> requisitos do sistema e de manter essa eficiência à medida que a demanda muda."*

**Score: 68/100 | Maturidade:  Bom**

### PERF 1  Como você seleciona a arquitetura de melhor desempenho?

**Resposta:** Arquitetura serverless event-driven elimina polling e processa eventos
apenas quando ocorrem. Escolha validada no ADR-002 com comparação de latência de
detecção (< 2 min event-driven vs até 5 min polling periódico).

**Controles implementados:**
-  ADR-002: event-driven vs polling  latência de detecção documentada
-  Lambda Python 3.12: runtime mais recente, menor cold start
-  DynamoDB PAY_PER_REQUEST: sem over-provisioning
-  EventBridge: processamento assíncrono sem blocking

### PERF 2  Como você seleciona e usa os recursos de computação?

**Controles implementados:**
-  Lambda memory sizing por função: 256MB (evaluator), 128MB (notifier), 512MB (reporter)
-  ECS Fargate: 0.5 vCPU/1GB por task (baseado em profiling)
-  Aurora db.r6g.large (prod) / db.t4g.medium (dev): rightsizing documentado
-  X-Ray: profiling disponível para identificar gargalos por função

**Gaps (Médio Risco):**
-  Sem benchmark documentado de cold start por Lambda
-  Sem Lambda Power Tuning rodado para otimização de memory/cost

### PERF 3  Como você seleciona seu armazenamento de dados?

**Controles implementados:**
-  Aurora MySQL: relacional para prontuários com JOINs complexos (vs DynamoDB)
-  DynamoDB: NoSQL para wearables com schema variável por dispositivo
-  ElastiCache Redis: in-memory para sessões e cache de queries frequentes
-  S3: objeto para logs imutáveis e laudos de imagem
-  S3 Bucket Key: reduz overhead KMS em ~99% (performance + custo)
-  Athena + Parquet via Glue: queries eficientes sobre logs históricos

### PERF 4  Como você seleciona e usa os recursos de rede?

**Controles implementados:**
-  CloudFront: cache de assets estáticos reduz latência global
-  VPC Endpoints: elimina latência de NAT Gateway para chamadas AWS (< 1ms vs ~10ms)
-  ALB: load balancing baseado em health checks a cada 10s

**Gaps (Médio Risco):**
-  Sem análise de latência documentada entre ECS e Aurora
-  Sem configuração de Connection Pooling no Aurora (RDS Proxy como opção)

### PERF 5  Como você otimizar o desempenho ao longo do tempo?

**Controles implementados:**
-  Lambda audit-reporter: relatório semanal inclui métricas de performance do pipeline
-  CloudWatch Dashboard: duration e invocations visíveis por Lambda

**Gaps (Médio Risco):**
-  Sem processo formal de revisão de performance trimestral
-  Lambda Provisioned Concurrency não avaliada para compliance-evaluator em prod

---

## Pilar 5  Otimização de Custos

> "A capacidade de executar sistemas para fornecer valor de negócio ao preço mais baixo."*

**Score: 80/100 | Maturidade:  Forte**

### COST 1  Como você implementa gestão financeira da nuvem?

**Controles implementados:**
-  Tags obrigatórias em todos os recursos via `default_tags` no provider (WAYFINDER-015)
-  AWS Budgets: budget total (80%/100%/120% forecast) + budget compute/DB (70%/100%)
-  Cost Explorer habilitado com análise por tag `Project` e `CostCenter`
-  RB-005: processo semanal de análise de custo com queries Athena
-  Separação dev/prod: filtro por tag `Environment` no Cost Explorer

### COST 2  Como você governar o uso?

**Controles implementados:**
-  IaC Terraform: sem provisionamento ad-hoc  custo sempre aprovado em PR
-  WAYFINDER-015: recursos sem tags obrigatórias detectados
-  GitHub Actions: `terraform plan` expõe custo incremental antes do apply

### COST 3  Como você monitorar uso e custos?

**Controles implementados:**
-  AWS Budgets com SNS alerts: WARNING em 80%, CRITICAL em 100%
-  RB-005 Query 6.4: análise de custo NAT Gateway (maior item variável)
-  RB-005 Query 6.5: custo S3 por bucket
-  Lambda audit-reporter: custo semanal incluído no relatório do Board

### COST 4  Como você descomissionar recursos?

**Controles implementados:**
-  S3 lifecycle: Standard  Glacier após 90 dias, expiração por tipo de dado
-  CloudWatch Logs: retenção configurada (90 dias Lambdas, 365 dias CloudTrail)
-  `force_destroy = true` em dev: facilita destroy sem resíduos
-  ECR lifecycle: keep 10 latest, expirar untagged após 30 dias

**Gaps (Médio Risco):**
-  Sem automação de stop/start de recursos dev fora do horário comercial

### COST 5  Como você selecionar o tipo e tamanho correto do recurso?

**Controles implementados:**
-  Lambda serverless: cobra apenas por ms de execução
-  DynamoDB PAY_PER_REQUEST: sem over-provisioning
-  ECS Fargate: sem instâncias ociosas
-  NAT Gateway: 1 por AZ em prod, 1 total em dev
-  VPC Gateway Endpoints S3 e DynamoDB: gratuitos (vs Interface Endpoints pagos)
-  RB-005: processo de rightsizing com critérios documentados (CPU < 10% por 7d)
-  S3 Bucket Key: -99% custo de KMS requests
-  ADR-009: análise custo VPC Endpoints vs NAT-only (ROI 177x em segurança)

**Estimativa de custo mensal documentada:**
- Dev: ~$38/mês (módulo Wayfinder isolado)
- Prod completo VitaCore: ~$870/mês (aplicação + governança)

---

## Pilar 6  Sustentabilidade

> "A capacidade de melhorar continuamente os impactos de sustentabilidade reduzindo  
> consumo de energia e aumentando eficiência em todos os componentes da carga de trabalho."*

**Score: 45/100 | Maturidade:  Em desenvolvimento**

### SUS 1  Como você escolhe Regiões para dar suporte aos seus objetivos de sustentabilidade?

**Resposta:** `us-east-1` foi escolhida por requisito de latência para usuários brasileiros
(via CloudFront) e por ser a região com maior cobertura de serviços AWS. Não foi avaliado
o percentual de energia renovável da região.

**Controles implementados:**
-  Arquitetura serverless elimina servidores ociosos (maior fator de sustentabilidade)

**Gaps (Médio Risco):**
-  `us-east-1` não é a região com maior % de energia renovável (Oregon/Frankfurt têm mais)
-  Sem análise do AWS Customer Carbon Footprint Tool

### SUS 2  Como você alinhar metas de utilização do usuário?

**Controles implementados:**
-  Lambda executa apenas com eventos reais  zero consumo em idle
-  DynamoDB PAY_PER_REQUEST: recursos alocados apenas quando há demanda
-  EventBridge + Lambda vs servidores dedicados: ~95% menos recursos computacionais
-  S3 lifecycle: dados movidos para Glacier (menor energia por byte armazenado)

### SUS 3  Como você maximizar a utilização dos recursos?

**Controles implementados:**
-  ECS Fargate: bin-packing automático pela AWS
-  Lambda memory otimizado por função (sem over-provisioning)
-  ElastiCache Redis: reduz carga no Aurora (-60% queries repetitivas)
-  CloudFront cache: reduz requests ao origen (~70% hit rate esperado)

**Gaps (Médio Risco):**
-  Sem Compute Optimizer habilitado para análise de rightsizing
-  Sem análise de Graviton (ARM) para ECS tasks e RDS (db.r7g vs db.r6g)

### SUS 4  Como você antecipar e adotar novas ofertas eficientes?

**Controles implementados:**
-  Python 3.12: runtime mais eficiente que versões anteriores
-  Terraform ~> 5.0: provider atualizado
-  Aurora MySQL (vs MySQL autogerenciado): mais eficiente em hardware compartilhado

**Gaps (Médio Risco):**
-  Sem plano de migração para Graviton (potencial -20% energia e -10% custo)
-  Sem política formal de sustentabilidade documentada

---

## Plano de Melhoria Priorizado

| # | Pilar | Melhoria | Esforço | Impacto | Risco Mitigado |
|---|---|---|---|---|---|
| 1 | Segurança | Migrar CI/CD de access keys para OIDC + IAM Role | Baixo | Alto | SEC-1 |
| 2 | Operacional | Criar runbook de Game Day (simulação de incidente) | Médio | Alto | OPS-6, SEC-9 |
| 3 | Confiabilidade | Definir RTO/RPO formais por componente | Baixo | Médio | REL-4 |
| 4 | Operacional | Adicionar `terraform test` nos módulos (TF 1.6+) | Médio | Médio | OPS-4 |
| 5 | Performance | Executar Lambda Power Tuning (open source) | Baixo | Médio | PERF-2 |
| 6 | Confiabilidade | Documentar e testar restore do Aurora | Baixo | Alto | REL-4 |
| 7 | Segurança | Habilitar GuardDuty EKS e Lambda protection | Baixo | Médio | SEC-3 |
| 8 | Custo | Avaliar Graviton para Aurora e ECS | Médio | Médio | COST-5 |
| 9 | Sustentabilidade | Habilitar AWS Compute Optimizer | Baixo | Médio | SUS-3 |
| 10 | Sustentabilidade | Executar Customer Carbon Footprint Tool | Baixo | Baixo | SUS-1 |

---

## Referências Oficiais AWS

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [AWS Well-Architected Tool](https://console.aws.amazon.com/wellarchitected/)
- [Security Pillar Whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html)
- [Reliability Pillar Whitepaper](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html)
- [Operational Excellence Pillar](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)
- [Performance Efficiency Pillar](https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html)
- [Cost Optimization Pillar](https://docs.aws.amazon.com/wellarchitected/latest/cost-optimization-pillar/welcome.html)
- [Sustainability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/sustainability-pillar/sustainability-pillar.html)
- [AWS Foundational Security Best Practices](https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html)
- [CIS AWS Foundations Benchmark v1.4](https://www.cisecurity.org/benchmark/amazon_web_services)

---

## Próxima Revisão

**Data sugerida:** 2027-02-21 (6 meses após deploy em prod)

**Gatilhos para revisão antecipada:**
- Incidente de segurança CRITICAL em prod
- Mudança arquitetural significativa (ex: multi-region)
- Aumento de custo > 50% mês a mês por 2 meses
- Obtenção da certificação ISO 27001 (novos controles)
- Score FSBP cair abaixo de 80% por 2 semanas consecutivas
