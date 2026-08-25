# ADR-007  Segurança em Múltiplas Camadas (Defense in Depth)

**Status:** Aceito  
**Data:** 2026-04-10  
**Autores:** Bruno Oliveira (SecOps Lead), Rafael Santos (CTO)  
**Revisores:** Ana Lima (DPO), Carla Mendes (Dev Lead)  
**Motivação:** Post-mortem do incidente de 15/03/2026  bucket S3 público por 18 dias

---

## 1. Contexto

O incidente de março de 2026 expôs uma falha crítica de arquitetura: a VitaCore Health
dependia de **uma única camada de segurança**  Block Public Access configurado
manualmente. Quando essa camada foi desabilitada acidentalmente por um desenvolvedor,
não havia nenhuma outra barreira, nenhuma detecção e nenhuma remediação automática.

O resultado: 2.340 laudos de pacientes expostos publicamente por 18 dias, multa de
R$ 420.000 da ANPD, e R$ 1,68M em contratos perdidos.

**Lição aprendida:** Uma arquitetura robusta nunca deve depender de um único controle.
Qualquer controle pode falhar  por erro humano, bug de software ou ação maliciosa.
A questão não é "como evitamos que o controle falhe?" mas "o que acontece quando falha?"

### 1.1 Análise de Falha do Incidente

```
Única linha de defesa:
  S3 Block Public Access (configuração manual, sem IaC)
      
       Dev júnior executa o comando errado
              
               Sem detecção  18 dias de exposição

Com Defense in Depth (o que deveria existir):
  Camada 1: S3 Block Public Access (configuração)
  Camada 2: SCP conta deny-s3-public-access-enable (conta)
  Camada 3: AWS Config WAYFINDER-002 (detecção < 5 min)
  Camada 4: KMS CMK (dados ilegíveis mesmo se acessados)
  Camada 5: CloudTrail data events (audit trail)
  Camada 6: GuardDuty S3 protection (comportamento anômalo)
  Camada 7: Processo de revisão de mudanças (humano)

Com todas as 7 camadas ativas:
  Mesmo que a Camada 1 falhe (erro humano)
   Camada 2 impede ou dificulta a falha
   Camada 3 detecta e remedia em < 5 minutos
   Camada 4 garante que dados acessados são ilegíveis
  Resultado: zero exposição efetiva de dados
```

---

## 2. Decisão

**Implementar 7 camadas independentes de segurança** para cada tipo de dado e recurso
da VitaCore Health, onde a falha de qualquer camada individual seja detectada e
remediada automaticamente antes que cause impacto.

Este ADR documenta a arquitetura de Defense in Depth para a plataforma VitaCore
monitorada pelo Wayfinder Cloud.

---

## 3. As 7 Camadas de Segurança

### Camada 1  Borda de Rede (CloudFront + WAF + Route 53)

**O que protege:** Tráfego externo antes de chegar à aplicação.

```
Route 53 Health Checks
   CloudFront (TLS 1.3 obrigatório, HTTPS only)
   WAF (OWASP Top 10, rate limiting, bot protection)
   ACM (certificados gerenciados com renovação automática)

Controles:
  - TLS 1.3: sem downgrade para protocolos inseguros
  - WAF SQL Injection rule: bloqueia tentativas antes de chegar à API
  - Rate limiting: 1000 req/min por IP (proteção contra força bruta)
  - HTTPS only: sem tráfego HTTP não criptografado

Monitoramento Wayfinder:
  - Config Rule: wafv2-webacl-not-empty
  - CloudWatch Alarm: WAF BlockedRequests > 100/min  SNS WARNING
```

### Camada 2  Isolamento de Rede (VPC + Security Groups + Endpoints)

**O que protege:** Comunicação lateral entre serviços.

```
VPC 10.0.0.0/16 com segregação de subnets:
  Public:     ALB, NAT GW (sem dados de saúde)
  Private App: ECS, Lambda (dados transitando)
  Private Data: Aurora, Redis, DynamoDB (dados em repouso)

Security Groups (mínimo privilégio):
  sg-alb:  ingress 443 ONLY from CloudFront IP ranges
  sg-app:  ingress 8080 from sg-alb ONLY
  sg-data: ingress 3306/6379 from sg-app ONLY; NO egress

VPC Endpoints: serviços AWS sem tráfego pela internet
VPC Flow Logs: habilitado em TODAS as VPCs

Monitoramento Wayfinder:
  - Config Rule: WAYFINDER-009 (SSH/DB portas expostas)
  - Config Rule: vpc-flow-logs-enabled
  - Config Rule: WAYFINDER-006 (EC2 health em subnet pública)
```

### Camada 3  Autenticação e Autorização (Cognito + IAM + SCPs)

**O que protege:** Quem pode fazer o quê em cada recurso.

```
Para usuários humanos:
  - Cognito User Pools com MFA obrigatório para médicos
  - IAM Identity Center (SSO) para acesso de engenheiros
  - Permission sets com least privilege por função

Para serviços e sistemas:
  - IAM Roles com escopo mínimo por task ECS e Lambda
  - Resource-based policies com condition tags
  - SCPs na conta: deny-root-account, require-mfa, deny-public-s3

Monitoramento Wayfinder:
  - Config Rule: WAYFINDER-005 (IAM Action:*)
  - Config Rule: iam-root-access-key-check
  - Config Rule: mfa-enabled-for-iam-console-access
  - Config Rule: WAYFINDER-012 (access key > 90 dias)
```

### Camada 4  Criptografia (KMS + TLS + Secrets Manager)

**O que protege:** Confidencialidade dos dados mesmo se acessados indevidamente.

```
Dados em repouso:
  - S3: SSE-KMS com CMK por classificação de dado
  - Aurora: criptografia KMS at-rest obrigatória
  - DynamoDB: SSE com CMK para dados health-*
  - ElastiCache Redis: criptografia at-rest + in-transit
  - EBS: criptografia habilitada por default na conta

Dados em trânsito:
  - TLS 1.3 em todos os endpoints externos
  - TLS em comunicação ECS  Aurora (enforce_ssl=1)
  - HTTPS entre todos os componentes internos

Segredos:
  - Secrets Manager para credenciais DB e API keys
  - Rotação automática de credenciais Aurora (30 dias)
  - Sem hardcoded secrets (detectado por WAYFINDER-007/014)

Lição do incidente: mesmo com S3 público, dados com KMS CMK
são ilegíveis sem a chave. Camada 4 seria a salvaguarda final.

Monitoramento Wayfinder:
  - WAYFINDER-001 (S3 sem KMS CMK)
  - WAYFINDER-004 (RDS sem criptografia)
  - WAYFINDER-007/014 (credenciais hardcoded)
  - Config Rule: encrypted-volumes
```

### Camada 5  Conformidade Contínua (AWS Config + Wayfinder Rules)

**O que protege:** Garante que desvios das camadas 1-4 sejam detectados e corrigidos.

```
Motor central: AWS Config com 24 rules
  - Detecção de mudança de configuração em < 2 minutos
  - WAYFINDER-002: detecta S3 público em < 5 minutos (teria salvado o incidente)
  - Remediação automática para 8 categorias críticas

Pipeline de conformidade:
  Config  EventBridge  Lambda compliance-evaluator
     SNS (alerta) + Lambda auto-remediation (correção)

Monitoramento de self:
  - WAYFINDER-003 garante que o próprio CloudTrail está ativo
  - CloudWatch Alarm se Config Recorder desabilitar

Esta é a camada mais importante do Wayfinder Cloud 
é a meta-camada que monitora todas as outras camadas.
```

### Camada 6  Detecção de Ameaças (GuardDuty + Security Hub + Inspector)

**O que protege:** Ataques ativos, credenciais comprometidas, vulnerabilidades.

```
GuardDuty (ML-based):
  - Analisa CloudTrail + VPC Flow Logs + DNS logs
  - Detecta: credenciais comprometidas, reconhecimento, C&C
  - S3 Protection: acesso anômalo a buckets (incluindo cenário de março)
  - Tempo de detecção: 15 min a 2h dependendo do finding type

Security Hub:
  - Agrega findings de GuardDuty, Inspector, Config
  - Score FSBP e CIS: benchmark de maturidade da postura
  - Meta: FSBP > 85% em produção

Inspector v2:
  - Vulnerabilidades CVE em EC2 e imagens ECR
  - Scan contínuo (não apenas no deploy)
  - Integra com pipeline CI/CD via ECR on-push scan

Monitoramento Wayfinder:
  - EventBridge: GuardDuty findings  Lambda incident-notifier
  - Config Rule: guardduty-enabled-centralized, securityhub-enabled
  - RB-004: runbook de resposta a GuardDuty findings
```

### Camada 7  Auditoria e Resposta (CloudTrail + S3 Object Lock + Processo)

**O que protege:** Evidência forense imutável, responsabilização, conformidade legal.

```
Trilha técnica:
  - CloudTrail: 100% das API calls registradas (não pode ser desabilitado
    sem WAYFINDER-003 alertar em 30 minutos)
  - S3 data events: cada GET/PUT em dados health-critical registrado
  - S3 Object Lock COMPLIANCE: trilha não pode ser alterada ou deletada

Resposta a incidentes:
  - RB-001: processo de resposta a incidentes
  - RB-004: resposta a GuardDuty findings
  - Template LGPD art. 48 pré-preenchido pelo Lambda audit-reporter
  - SLA interno: notificação ANPD em < 48h (folga de 24h do prazo legal)

Lição do incidente: CloudTrail ativo com data events teria registrado
cada GetObject do bucket exposto, permitindo quantificar o escopo exato
da exposição (quantos objetos foram baixados e por quem).

Monitoramento Wayfinder:
  - WAYFINDER-003 (CloudTrail status)
  - WAYFINDER-013 (S3 Object Lock para retention-required)
  - Relatório semanal automático via Lambda audit-reporter
```

---

## 4. Mapeamento Camadas × Serviços Wayfinder

| Camada | Serviços AWS | Config Rules | Lambda | SNS |
|---|---|---|---|---|
| 1  Borda | CloudFront, WAF, Route 53, ACM | wafv2-webacl-not-empty | incident-notifier | WARNING |
| 2  Rede | VPC, SG, Endpoints, VPC Flow Logs | vpc-flow-logs-enabled, WAYFINDER-006/009 | auto-remediation | CRITICAL |
| 3  AuthN/AuthZ | Cognito, IAM, IAM IC, SCPs | WAYFINDER-005/012, iam-root-access-key-check | auto-remediation | CRITICAL/HIGH |
| 4  Criptografia | KMS, ACM, Secrets Manager | WAYFINDER-001/004/007/008/010/014 | auto-remediation | CRITICAL |
| 5  Conformidade | AWS Config, EventBridge | WAYFINDER-001 a 015 | compliance-evaluator | CRITICAL/HIGH/MEDIUM |
| 6  Ameaças | GuardDuty, Security Hub, Inspector | guardduty-enabled, securityhub-enabled | incident-notifier | CRITICAL |
| 7  Auditoria | CloudTrail, S3 Object Lock, Athena | WAYFINDER-003/013, cloud-trail-enabled | audit-reporter | INFO |

---

## 5. Trade-offs e Custos

### 5.1 Custo Adicional das 7 Camadas

| Serviço Adicional | Custo Mensal Prod | Custo Mensal Dev |
|---|---|---|
| GuardDuty | $15 | $1.25 |
| Security Hub | $3.50 | $0.75 |
| Inspector v2 | $4.50 | $0.09 |
| AWS Config (adicional) | $8 (novas rules) | $3 |
| VPC Endpoints (10 interface) | $72 | $14.40 |
| **Total camadas adicionais** | **~$103/mês** | **~$20/mês** |

### 5.2 Custo do Incidente de Março vs Custo de Prevenção

```
Custo do incidente de março: R$ 2.107.000 (estimado)
Custo anual das 7 camadas (prod): ~$103/mês × 12 = $1.236/ano  R$ 6.180/ano
Custo anual das 7 camadas (dev):  ~$20/mês × 12  = $240/ano   R$ 1.200/ano

ROI da Defense in Depth:
  Investimento: R$ 7.380/ano
  Custo evitado (1 incidente similar): R$ 2.107.000
  ROI: 285x (28.500%)

Decisão: custo-benefício justifica amplamente o investimento.
```

### 5.3 Impacto Operacional

| Aspecto | Impacto | Mitigação |
|---|---|---|
| Latência adicional (WAF) | +2-5ms por request | Irrelevante para aplicação de saúde |
| Overhead de desenvolvimento | +10% tempo de setup de recurso | Módulos Terraform pré-configurados |
| Falsos positivos de alertas | Risco de alert fatigue | Tuning de regras + supressão por tag |
| Custo de storage (audit trail) | +$11/mês (500GB/5 anos) | S3 Intelligent-Tiering reduz custo |

---

## 6. Consequências

**Positivas:**
- Qualquer falha em uma camada é detectada e corrigida automaticamente (camadas 1-6)
- Evidência forense imutável para qualquer incidente futuro (camada 7)
- Conformidade com LGPD art. 46 ("medidas técnicas e administrativas") demonstrada
- Base para certificação ISO 27001 (controles A.8.20, A.8.21, A.8.24, A.5.15)
- O incidente de março com Wayfinder ativo: 0 dados expostos em vez de 2.340 laudos

**Negativas:**
- Custo adicional de ~$103/mês em prod (justificado pelo ROI demonstrado)
- Maior complexidade arquitetural  mitigada por IaC e documentação
- Time de desenvolvimento precisa considerar as 7 camadas ao criar novos recursos

**Métricas de sucesso:**
- Zero incidentes de exposição de dados de saúde por 12 meses
- P99 de detecção de desvio de conformidade < 5 minutos
- Score FSBP > 85% e CIS > 80% em produção
- 100% dos recursos com as 5 tags obrigatórias
