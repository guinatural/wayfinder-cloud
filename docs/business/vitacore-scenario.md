# Cenário de Negócio  VitaCore Health

**Documento:** Contexto Empresarial e Motivação Técnica  
**Versão:** 1.0 | **Classificação:** Interno  Restrito  
**Autor:** Equipe de Arquitetura  
**Última atualização:** 2026-08-21

---

## 1. Perfil da Empresa

**VitaCore Health** é uma startup de saúde digital fundada em março de 2022 em São Paulo, SP.
A empresa desenvolve e opera uma plataforma integrada de saúde que conecta pacientes,
médicos, clínicas, laboratórios e operadoras de planos de saúde em um ecossistema digital.

| Atributo | Valor |
|---|---|
| Fundação | Março de 2022, São Paulo  SP |
| Estágio | Série A em andamento (R$ 45 milhões) |
| Funcionários | 180 (crescimento de 340% em 18 meses) |
| Pacientes ativos | 127.000 em SP, RJ e MG |
| Receita anual | R$ 8,2 milhões (modelo SaaS B2B) |
| Clínicas parceiras | 47 clínicas em 3 estados |
| Laboratórios | 12 laboratórios integrados via HL7/FHIR |
| Operadoras de plano | 3 (Amil, SulAmérica, Bradesco Saúde) |
| Equipe de TI | 23 engenheiros (full-stack, backend, DevOps) |
| Segurança | 1 analista de segurança part-time (20h/semana) |

### 1.1 Produtos e Serviços

**Prontuário Eletrônico do Paciente (PEP):**
Sistema web para médicos e clínicas com histórico clínico completo, prescrições eletrônicas,
encaminhamentos e integração com laboratórios. Processamento de ~4.200 consultas/dia.
Dados armazenados em Aurora MySQL com classificação `health-critical`.

**App de Saúde para Pacientes (VitaCore Patient):**
Aplicativo iOS/Android com acesso a resultados de exames, agendamento de consultas,
histórico de medicações e sincronização com wearables. 89.000 downloads, NPS de 71.
Dados de wearables ingeridos via Kinesis  Lambda  DynamoDB (`health-standard`).

**Plataforma de Telemedicina:**
Videoconsultas com gravação de sessão e anexação ao prontuário. Integração com
prescrição digital certificada. ~850 teleconsultas/semana. Gravações armazenadas
em S3 com tag `data-classification=health-critical`.

**Integrações com Wearables:**
Coleta de dados de Garmin, Apple Watch e Fitbit: frequência cardíaca, SpO2, passos,
qualidade do sono. Processamento em tempo real via Kinesis Data Streams.
~2,4 milhões de eventos/dia ingeridos.

### 1.2 Modelo de Negócio e SLA

O modelo SaaS B2B cobra por clínica parceira (R$ 8904.200/mês por plano) e por
operadora de plano de saúde (R$ 12.00048.000/mês). Contratos incluem SLA de
**99,5% de disponibilidade mensal** com penalidade de **0,5% do MRR por hora**
de indisponibilidade acima do limite.

```
MRR atual: ~R$ 683.000
Penalidade máxima por hora de downtime: ~R$ 3.415
Janela de indisponibilidade permitida/mês: 3h 39min
Impacto financeiro de incidente de 24h: ~R$ 81.960
```

---

## 2. Infraestrutura AWS  Estado Antes do Wayfinder Cloud

A infraestrutura da VitaCore foi construída de forma incremental e reativa ao longo de
dois anos, sem padrões de segurança formalizados. O resultado é um ambiente com
147 recursos AWS em `us-east-1`, criados manualmente, sem IaC e sem controles de conformidade.

### 2.1 Inventário de Recursos

| Serviço | Quantidade | Problemas Identificados |
|---|---|---|
| S3 Buckets | 23 | 6 sem criptografia, 2 com acesso público acidentalmente habilitado |
| Aurora MySQL | 3 clusters | 1 cluster sem criptografia em repouso (banco de histórico legacy) |
| EC2 Instances | 18 | 4 em subnets públicas processando dados de pacientes |
| IAM Users | 67 | Maioria com permissões excessivas herdadas do início da empresa |
| IAM Roles | 12 com AdministratorAccess | Ativas em ambientes de produção |
| VPCs | 4 | Sem VPC Flow Logs em 2 delas |
| CloudTrail | 1 trail | Ficou desabilitado por 43 dias após migração  não detectado |
| GuardDuty | Não habilitado |  |
| Security Hub | Não habilitado |  |
| MFA | Habilitado para 36/67 usuários | 31 usuários sem MFA, incluindo acesso a prod |
| Root Account Keys | 3 access keys criadas | "Nunca usadas mas nunca deletadas" |

### 2.2 Análise de Risco por Recurso

**Buckets S3 críticos sem proteção:**
```
vitacore-laudos-imagens-prod     acesso público (INCIDENTE DE MARÇO)
vitacore-backups-pacientes       sem criptografia KMS CMK
vitacore-exames-laboratoriais    sem criptografia, sem versionamento
vitacore-gravacoes-telemedicina  sem Object Lock, sem lifecycle
vitacore-prontuarios-archive     sem criptografia, acesso via IAM excessivo
vitacore-dados-wearables-raw     sem criptografia
```

**IAM Roles com AdministratorAccess em produção:**
```
arn:aws:iam::123456789012:role/vitacore-app-role-prod     (AdministratorAccess)
arn:aws:iam::123456789012:role/vitacore-deploy-role       (AdministratorAccess)
arn:aws:iam::123456789012:role/vitacore-lambda-all        (AdministratorAccess)
```

**Custo AWS crescente sem controle:**
O custo AWS cresceu 23% ao mês nos últimos 4 meses. Sem tags de custo padronizadas,
é impossível identificar qual produto ou equipe é responsável pelo crescimento.
Estimativa: 30% dos recursos são ociosos ou superdimensionados.

---

## 3. O Incidente de Março de 2026  Post-Mortem Detalhado

Este incidente foi o catalisador direto para o projeto Wayfinder Cloud. Ele expõe
todas as falhas sistêmicas de governança de cloud da VitaCore.

### 3.1 Linha do Tempo

| Data/Hora | Evento |
|---|---|
| **15/03/2026 14h32** | Dev júnior executa `aws s3api put-public-access-block` no bucket errado enquanto configura website estático para landing page de marketing |
| **15/03/2026 14h34** | Bucket `vitacore-laudos-imagens-prod` torna-se publicamente listável e legível |
| **15/03/2026 14h3518h** | Dev percebe que a landing page ficou errada e corrige, mas não percebe que alterou o bucket errado |
| **15/03/2026  02/04/2026** | **18 dias** de exposição pública sem detecção interna |
| **02/04/2026 09h17** | Paciente Carlos M. encontra seu resultado de tomografia via busca no Google e entra em contato com a VitaCore pelo formulário do site |
| **02/04/2026 11h30** | Time de suporte escala para o CTO Rafael Santos |
| **02/04/2026 13h45** | Block Public Access reativado. Exposição encerrada |
| **02/04/2026 14h00** | Início da análise forense  equipe sem ferramentas adequadas, análise manual |
| **05/04/2026** | Escopo confirmado: 2.340 laudos expostos (2.340 pacientes únicos afetados) |
| **20/05/2026 (67 dias após)** | ANPD notificada  prazo legal é 72h (art. 48 1 LGPD) |
| **15/06/2026** | ANPD aplica multa de R$ 420.000 (art. 52 LGPD, 1, III) |
| **Abril/Maio 2026** | 3 clínicas parceiras cancelam contratos  alegam "falha de confiança" |

### 3.2 Dados Expostos

```
Bucket: vitacore-laudos-imagens-prod
Região: us-east-1
Período de exposição: 15/03/2026 14h34  02/04/2026 13h45 (18 dias, 23h, 11 min)
Arquivos expostos: 2.340 laudos + metadados
Formato: PDF, DICOM (imagens médicas), JSON (metadados)

Dados pessoais sensíveis expostos por laudo:
  - Nome completo do paciente
  - CPF (identificador único)
  - Data de nascimento
  - Nome do médico solicitante
  - Nome da clínica
  - Data do exame
  - Resultado do exame (RX, TC ou RM)
  - Impressão diagnóstica (conclusão médica)
  - Número do CRM do médico

Tipos de exame expostos:
  - Radiografias (RX): 1.127 exames
  - Tomografias computadorizadas (TC): 891 exames
  - Ressonâncias magnéticas (RM): 322 exames
```

### 3.3 Causa Raiz e Fatores Contribuintes

**Causa raiz (técnica):** Ausência de Block Public Access nas configurações padrão
da conta AWS e ausência de detecção automática de mudanças de configuração.

**Fatores contribuintes:**
1. Sem AWS Config habilitado  nenhuma rule detectou a mudança
2. Sem GuardDuty  nenhuma análise de comportamento anômalo de acesso ao bucket
3. CloudTrail existia mas sem alertas configurados para mudanças críticas em S3
4. Sem política de least privilege  dev júnior tinha permissão para modificar ACLs de S3
5. Sem processo de revisão de mudanças em recursos de produção
6. Sem naming convention clara  `vitacore-laudos-imagens-prod` e `vitacore-landing-static` são nomes similares
7. Sem VPC Endpoints para S3  não era possível bloquear acesso direto via internet

### 3.4 Impacto Financeiro Total

| Categoria | Valor |
|---|---|
| Multa ANPD | R$ 420.000 |
| Receita perdida (3 contratos cancelados, 12 meses) | R$ 1.260.000 |
| Custos de resposta ao incidente (consultoria jurídica, forense) | R$ 180.000 |
| Notificação individual de 2.340 pacientes (LGPD art. 48) | R$ 47.000 |
| Reputação e potencial impacto na captação Série A | R$ 200.000 (est.) |
| **Total estimado** | **R$ 2.107.000** |

### 3.5 Comprometimento do CEO

> "Nenhum dado de paciente deve ficar exposto por mais de 5 minutos sem que alguém
> na VitaCore seja alertado. Em 90 dias, teremos controles automáticos que tornam
> este tipo de incidente impossível."*
>  Marcos Ferreira, CEO VitaCore Health, comunicado interno de 05/04/2026

---

## 4. Objetivos do Projeto Wayfinder Cloud

### 4.1 Objetivos Primários (90 dias  compromisso CEO)

| # | Objetivo | Métrica de Sucesso | Responsável |
|---|---|---|---|
| O1 | Detectar qualquer desvio de conformidade em menos de 5 minutos | P99 de detecção < 5 min (medido via CloudWatch) | Bruno Oliveira (SecOps) |
| O2 | Remediação automática para 8 categorias de violações críticas | 100% das WAYFINDER-001/002/003/006/009 remediadas automaticamente | Bruno Oliveira |
| O3 | Trilha de auditoria imutável de 5 anos | S3 Object Lock COMPLIANCE mode, 5 anos, auditado pelo externo | Ana Lima (DPO) |
| O4 | Processo formal de resposta a incidentes conforme LGPD art. 48 | SLA de notificação < 72h documentado e testado | Ana Lima |
| O5 | Relatório semanal de postura de segurança para o Board | 100% dos relatórios entregues às sextas-feiras | Rafael Santos (CTO) |

### 4.2 Objetivos Secundários (6 meses)

| # | Objetivo | Métrica de Sucesso |
|---|---|---|
| O6 | Reduzir custo AWS em 15% | De ~R$ 47k/mês para ~R$ 40k/mês via rightsizing + lifecycle |
| O7 | Zero recursos sem tags obrigatórias | Config Rule WAYFINDER-015, 100% compliance |
| O8 | Preparação para ISO 27001 | Evidências de controles exportáveis via Athena |
| O9 | Habilitar GuardDuty + Security Hub + Inspector v2 | 100% dos recursos cobertos, 0 findings CRITICAL não tratados |
| O10 | Rotação automática de todas as credenciais de banco | Secrets Manager + Lambda rotator para todos os clusters Aurora |

### 4.3 Objetivos Estratégicos (18 meses)

- Certificação ISO 27001 obtida (requisito para contratos com planos de saúde)
- Habilitar expansão para 4 e 5 estados (RS, PR) com governança cloud como pré-requisito
- Oferecer relatórios de postura de segurança como diferencial competitivo para clínicas
- Pipeline de captação Série A: demonstrar maturidade de governança como parte do due diligence

---

## 5. Personas e Stakeholders

### 5.1 Ana Lima  DPO (Data Protection Officer)

**Perfil:** Advogada especializada em privacidade, 8 anos de experiência, ingressou na
VitaCore após o incidente de março. Responsável pela relação com a ANPD.

**Necessidades do Wayfinder Cloud:**
- Relatórios semanais de compliance exportáveis em PDF (para o Board)
- Evidências de controles para auditoria ISO 27001 (logs, configurações, histórico)
- Alertas imediatos quando dado sensível é exposto (< 5 minutos para acionar art. 48)
- Dashboard com status de conformidade por artigo da LGPD
- Trilha imutável de todas as ações de remediação

**Citação:** *"Preciso saber imediatamente se um bucket com dados de paciente ficou
público, não 18 dias depois por email de um paciente."*

### 5.2 Rafael Santos  CTO

**Perfil:** Engenheiro de software com 15 anos de experiência, cofundador da VitaCore.
Responsável pela decisão de aprovação de mudanças em produção.

**Necessidades:**
- Visibilidade de custo AWS em tempo real com breakdown por produto
- Resumo executivo semanal de risco (não técnico, orientado a negócio)
- Aprovação de remediações automáticas via runbook versionado
- KPIs de segurança para apresentar a investidores (Série A)

### 5.3 Bruno Oliveira  SecOps Lead

**Perfil:** Engenheiro de segurança sênior, certificado AWS Security Specialty e CISSP.
Único profissional de segurança full-time da VitaCore (promovido após o incidente).

**Necessidades:**
- Alertas em tempo real com contexto suficiente para triagem (sem falsos positivos)
- Playbooks de investigação para cada tipo de violação
- Integração com ferramentas existentes: Slack, PagerDuty, Jira
- Queries Athena pré-construídas para investigação forense
- Correlação entre GuardDuty findings e CloudTrail events

### 5.4 Carla Mendes  Dev Lead

**Perfil:** Engenheira de software sênior, lidera o time de backend (9 pessoas).
Resistência inicial ao projeto ("mais burocracia para o time").

**Necessidades:**
- Feedback rápido quando criar recurso não conforme (< 5 min, antes do deploy em prod)
- Mensagens de alerta claras com "o que fazer" (não apenas "o que está errado")
- Remediação automática para erros comuns (sem precisar abrir ticket)
- Integração com GitHub Actions (fail fast no CI/CD antes de chegar em prod)

**Citação:** *"Se eu precisar abrir um ticket para cada alerta, vou ignorar os alertas."*

### 5.5 Auditores Externos (ISO 27001)

**Perfil:** Consultoria de certificação ISO 27001, auditarão controles da VitaCore
em Q2/2027 para emissão de certificado.

**Necessidades:**
- Evidências exportáveis de cada controle ISO 27001 mapeado
- Histórico de pelo menos 6 meses de operação conforme
- Demonstração de resposta a incidentes (simulações documentadas)
- Logs imutáveis de auditoria (não editáveis pela empresa)

---

## 6. Fluxos de Dados Sensíveis

```
Fluxo 1: Prontuário Eletrônico
Médico (HTTPS/TLS 1.3)
   Route 53  CloudFront (WAF)  ALB  ECS Fargate
   Aurora MySQL writer (health-critical, KMS CMK)
   Backup noturno: S3 (health-critical, SSE-KMS, Object Lock)
   Replicação para Aurora reader (us-east-1b)

Fluxo 2: Laudo de Imagem
Laboratório (API REST autenticada via Cognito)
   API Gateway  Lambda ingestor
   S3 laudos (health-critical, SSE-KMS)
   CloudFront signed URL (validade 1h)  médico solicitante
   CloudTrail data events: cada PUT/GET registrado

Fluxo 3: Dados de Wearable
Dispositivo (HTTPS)  API Gateway  Kinesis Data Streams
   Lambda processor (health-standard)  DynamoDB
   Agregação diária via Glue  S3 analytics (health-standard)

Fluxo 4: Telemedicina
Médico/Paciente (WebRTC criptografado)
   ECS Fargate (servidor de mídia)  gravação S3 (health-critical)
   Transcrição via Transcribe Medical  Aurora MySQL (prontuário)

Fluxo 5: Faturamento
Sistema de cobrança  RDS MySQL (financial-sensitive)
   Lambda gerador de relatórios  S3 relatórios (financial-sensitive)
   Entrega para operadoras via SES/S3 signed URLs
```

---

## 7. Requisitos Legais e Regulatórios

| Regulação | Aplicabilidade | Requisito Específico para Wayfinder |
|---|---|---|
| **LGPD art. 48** | Direta  notificação de incidentes | Detecção < 5 min; notificação ANPD em 72h |
| **LGPD art. 46** | Direta  segurança no tratamento | Criptografia, controle de acesso, audit trail |
| **LGPD art. 37** | Direta  registro de operações | CloudTrail + Glue + Athena |
| **CFM 1821/2007** | Prontuários digitais devem ser preservados por **20 anos** | S3 Object Lock por 20 anos para dados de prontuário |
| **RDC ANVISA 204/2017** | Rastreabilidade de medicamentos prescritos | Imutabilidade de prescrições eletrônicas |
| **CFM Telemedicina (2022/2023)** | Requisitos de gravação e prontuário | Gravações S3 com Object Lock + associação ao prontuário |
| **ISO 27001** | Meta de certificação | Evidências de controles A.8, A.9, A.12, A.16 |

---

## 8. Critérios de Aceitação do Projeto

O projeto Wayfinder Cloud será considerado bem-sucedido quando:

1. **Nenhum bucket S3 com dados de saúde fica público por mais de 5 minutos** sem alerta e remediação automática. Testado via drill mensal (Game Day).

2. **100% dos recursos AWS possuem as 5 tags obrigatórias**: Environment, Project, Owner, CostCenter, DataClassification.

3. **CloudTrail habilitado em 100% das regiões ativas** com alerta automático se desabilitado.

4. **Processo de notificação ANPD documentado e testado**: simulação de incidente com tempo de resposta < 72h medido e registrado.

5. **Relatórios semanais entregues** com 100% de cobertura dos artigos LGPD mapeados.

6. **Custo AWS reduzido em  15%** em 6 meses com documentação de cada ação de otimização.

7. **Todas as credenciais de banco armazenadas no Secrets Manager** com rotação automática habilitada.

8. **Zero IAM Roles com AdministratorAccess em produção**  confirmado via Config Rule WAYFINDER-005.
