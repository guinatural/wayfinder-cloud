# Mapeamento LGPD  Controles Técnicos AWS

**Projeto:** Wayfinder Cloud  
**Versão:** 2.0 | **Status:** Aprovado pelo DPO  
**Referências legais:**
- Lei n 13.709/2018  LGPD (Lei Geral de Proteção de Dados Pessoais)
- CFM 1821/2007  Normas técnicas para uso de sistemas informatizados em prontuários médicos
- RDC ANVISA 204/2017  Rastreabilidade de medicamentos prescritos digitalmente
- CFM 2314/2022  Regulamentação da telemedicina no Brasil
- ISO/IEC 27001:2022  Gestão de Segurança da Informação

**Contexto:** VitaCore Health  plataforma de saúde digital processando dados de
127.000 pacientes ativos em SP, RJ e MG. Incidente de segurança em 15/03/2026
resultou em multa de R$ 420.000 da ANPD e perda de R$ 1,68M em contratos.

---

## 1. Premissa Arquitetural  Dados de Saúde como Dados Sensíveis

### 1.1 Classificação Legal (LGPD art. 5, II)

Dados de saúde são **dados pessoais sensíveis** sob o art. 5, II da LGPD:

> "dado pessoal sensível: dado pessoal sobre origem racial ou étnica, convicção
> religiosa, opinião política, filiação a sindicato ou a organização de caráter
> religioso, filosófico ou político, dado referente à saúde ou à vida sexual,
> dado genético ou biométrico, quando vinculado a uma pessoa natural"*

Implicações arquiteturais diretas:
- **Criptografia obrigatória** em repouso e em trânsito para todos os dados de saúde
- **Base legal explícita** para cada operação de tratamento (art. 11, II, f  proteção à saúde)
- **Privacy by Design**: controles de segurança devem ser nativos à arquitetura, não adicionados
- **Menor privilégio**: cada serviço acessa apenas os dados estritamente necessários à sua função

### 1.2 Base Legal para Tratamento (LGPD art. 11, II, f)

A VitaCore trata dados de saúde com base no art. 11, II, f:
*"proteção da vida ou da incolumidade física do titular ou de terceiro"* e
complementarmente no art. 11, II, g: *"tutela da saúde"*.

O consentimento explícito do paciente (art. 11, I) é coletado na admissão e
armazenado em Aurora MySQL com versionamento e timestamp imutável.

### 1.3 Período de Retenção Legal  Prontuários Médicos

O CFM 1821/2007 e o CFM 1638/2002 estabelecem:
- **Prontuário digital: mínimo de 20 anos** após o último registro
- **Menores de idade**: mínimo até 25 anos de idade ou 5 anos após a maioridade
- **Exames de imagem (DICOM)**: mínimo 5 anos (alguns estados exigem 10 anos)

Implicação técnica crítica para o Wayfinder Cloud:
```
S3 Object Lock  COMPLIANCE mode (não pode ser removido nem pelo root)
  Prontuários:          retention = 20 anos (7.305 dias)
  Laudos de imagem:     retention = 5 anos  (1.825 dias)
  Gravações telemedicina: retention = 5 anos (1.825 dias)
  Prescrições digitais: retention = 5 anos  (1.825 dias)
  Dados de auditoria:   retention = 5 anos  (1.825 dias)   requisito contratual
```

**Por que COMPLIANCE mode e não GOVERNANCE mode?**
Em COMPLIANCE mode, nem mesmo o usuário root da conta AWS pode reduzir o
retention period ou deletar o objeto antes do vencimento. Em GOVERNANCE mode,
usuários com permissão `s3:BypassGovernanceRetention` podem contornar o lock.
Para dados de saúde sujeitos a obrigações legais de 20 anos, COMPLIANCE mode é
a única opção que oferece garantia jurídica de imutabilidade.

---

## 2. Tabela de Mapeamento LGPD × Controles AWS

### 2.1 Artigo 5  Definições Fundamentais

| Conceito LGPD | Definição Aplicada na VitaCore | Controle Técnico |
|---|---|---|
| Dado pessoal sensível (art. 5, II) | CPF + diagnóstico + resultado de exame + gravação de teleconsulta | Tag `data-classification=health-critical` em todos os recursos |
| Controlador (art. 5, VI) | VitaCore Health  define finalidade e meios do tratamento | IAM policies com escopo por serviço; DPO responsável |
| Operador (art. 5, VII) | AWS (infraestrutura), laboratórios integrados (processamento de laudos) | Acordo de Operador de Dados (DPA) com AWS, contratos com laboratórios |
| Agentes de tratamento (art. 5, IX) | VitaCore (controlador) + AWS + laboratórios + operadoras | IAM Identity Center com SSO; roles com escopo mínimo |

### 2.2 Artigo 6  Princípios do Tratamento

| Princípio (art. 6) | Implementação Técnica | Config Rule / Controle |
|---|---|---|
| **Finalidade** (I)  propósitos legítimos e explícitos | Dados de saúde usados exclusivamente para assistência médica | SCPs bloqueiam compartilhamento fora da conta sem aprovação |
| **Adequação** (II)  compatível com a finalidade | Wearable data usada apenas para monitoramento do paciente | IAM conditions `aws:ResourceTag/data-classification` |
| **Necessidade** (III)  mínimo necessário | Apenas campos clínicos relevantes retornados por API | Lambda validação de escopo antes de retornar dados |
| **Livre acesso** (IV)  acesso a informações | Paciente pode consultar seus dados via app VitaCore Patient | Cognito com portabilidade de dados implementada |
| **Qualidade** (V)  dados exatos e atualizados | Aurora com constraints de integridade + validação de entrada | CloudWatch alarms para inconsistências de dados |
| **Transparência** (VI)  informações claras | Política de privacidade pública + aviso no app | Fora do escopo técnico (jurídico/comunicação) |
| **Segurança** (VII)  proteção técnica e administrativa | KMS CMK + TLS 1.3 + VPC + MFA + auditoria | WAYFINDER-001 a WAYFINDER-014 |
| **Prevenção** (VIII)  prevenção de danos | Config Rules detectam antes de chegar em prod | AWS Config + GitHub Actions guardrails |
| **Não discriminação** (IX)  sem fins discriminatórios | Dados de saúde não usados para scoring ou seleção | SCP bloqueia cross-account data sharing sem aprovação |
| **Responsabilização** (X)  demonstrar conformidade | Trilha de auditoria imutável + relatórios semanais | CloudTrail + S3 Object Lock + Athena + relatórios DPO |

### 2.3 Artigo 11  Tratamento de Dados Sensíveis

| Requisito (art. 11) | Implementação | Evidência Técnica |
|---|---|---|
| Base legal explícita (II, f) | Consentimento armazenado em Aurora com timestamp imutável | CloudTrail data events no registro de consentimento |
| Proteção adicional para dados sensíveis | CMK dedicado `vitacore-health-critical-key` separado de outros dados | KMS Key Policy com `aws:ResourceTag` condition |
| Comunicação a terceiros com base legal | API de integração com laboratórios exige Cognito JWT + DPA assinado | API Gateway authorizer + CloudTrail de chamadas |
| Registro de operações com dados sensíveis | CloudTrail habilitado com data events S3 e Aurora | `cloudtrail-s3-dataevents-enabled` Config Rule |

### 2.4 Artigo 37  Registro de Operações de Tratamento

| Requisito | Implementação AWS | Config Rule |
|---|---|---|
| Registro de atividades de tratamento | CloudTrail All Regions + S3 Data Events + RDS API | `cloud-trail-enabled` + `cloudtrail-s3-dataevents-enabled` |
| Registro deve estar disponível para ANPD | S3 bucket de auditoria com acesso via IAM Role dedicada para DPO | IAM Policy `vitacore-dpo-audit-access` |
| Período de guarda do registro | S3 Object Lock COMPLIANCE 5 anos (requisito contratual) | WAYFINDER-013 + Config Rule `s3-bucket-object-lock-enabled` |

### 2.5 Artigo 38  Relatório de Impacto à Proteção de Dados (RIPD)

| Requisito | Implementação | Responsável |
|---|---|---|
| RIPD para operações de alto risco | Documento gerado via Athena + auditoria manual | DPO Ana Lima |
| Revisão periódica do RIPD | Agendada semestralmente via EventBridge Scheduler | DPO + SecOps |
| RIPD disponível para ANPD | S3 bucket de documentação DPO com acesso controlado | DPO |

### 2.6 Artigo 46  Segurança no Tratamento

| Obrigação (art. 46) | Controle Técnico | Config Rules |
|---|---|---|
| Medidas técnicas e administrativas para proteger dados | Criptografia KMS CMK + TLS 1.3 + MFA + VPC privada | WAYFINDER-001, 004, 008, 010 |
| Proteção contra acessos não autorizados | IAM Least Privilege + SCPs + Security Groups restritivos | WAYFINDER-005, 006, 009 |
| Proteção contra situações acidentais (como o incidente de março) | Config Rules + remediação automática + S3 Block Public Access | WAYFINDER-002 |
| Proteção contra destruição ilícita | S3 Object Lock COMPLIANCE + Backup Vault Lock | WAYFINDER-013 |
| Proteção contra perda | AWS Backup com vault lock + Aurora Multi-AZ | `backup-plan-min-frequency-and-min-retention-check` |

### 2.7 Artigo 47  Responsabilidade dos Agentes de Tratamento

| Obrigação | Implementação | Controle |
|---|---|---|
| Operadores garantem segurança equivalente | DPA com AWS + contratos com laboratórios com cláusulas de segurança | Revisão jurídica anual + IAM permission boundaries |
| Colaboradores acessam somente dados necessários | IAM Identity Center com roles por função (médico, admin, dev, auditoria) | WAYFINDER-005 + `iam-no-inline-policy` |
| Treinamento de equipe | LGPD onboarding obrigatório + simulações de incidente | Fora do escopo técnico  documentado no programa DPO |

### 2.8 Artigo 48  Comunicação de Incidentes de Segurança

**Prazo legal: 72 horas após a ciência do incidente**

O incidente de março expôs a ausência de detecção automática. O Wayfinder Cloud
implementa o seguinte pipeline de resposta:

```
Detecção automática (Config Rule / GuardDuty / CloudWatch Alarm)
    
     EventBridge  Lambda incident-notifier
           
            Severidade CRITICAL (dados de saúde expostos)
                SNS  Email DPO + CTO + SecOps (< 2 min)
                SNS  PagerDuty (alerta 24/7)
                Lambda auto-remediation (contenção automática)
                Ticket Jira criado automaticamente com template LGPD art.48
           
            Documentação para ANPD gerada via Lambda audit-reporter
                   Template de comunicação pré-preenchido com:
                       - Natureza dos dados afetados
                       - Número de titulares afetados
                       - Medidas de contenção adotadas
                       - Medidas de prevenção para o futuro
```

**SLA interno de notificação ANPD: máximo 48h após ciência** (folga de 24h do prazo legal).

### 2.9 Artigo 49  Sistemas de Tratamento

| Requisito | Implementação | Evidência |
|---|---|---|
| Privacy by Design | IaC com controles de segurança obrigatórios; dev não pode criar bucket sem criptografia | Config Rules + GitHub Actions policy check |
| Privacy by Default | Tags `data-classification` obrigatórias; KMS default encryption na conta | SCP `require-encryption-at-rest` |
| Segurança desde a concepção | Módulo compliance obrigatório em todos os ambientes | Terraform modules com controles integrados |
| Avaliação periódica | Relatório semanal de postura + audit trimestral | Lambda audit-reporter + Athena |

### 2.10 Artigo 50  Boas Práticas e Governança

| Programa | Implementação | Métricas |
|---|---|---|
| AWS Foundational Security Best Practices | Security Hub FSBP Standard habilitado | Score FSBP > 85% em prod |
| CIS AWS Foundations Benchmark v1.4 | Security Hub CIS Standard habilitado | Score CIS > 80% em prod |
| Programa de governança documentado | Este documento + ADRs + Runbooks | Revisão trimestral pelo DPO |
| Auditorias periódicas | Athena queries semanais + auditoria externa semestral | Relatórios exportados do Athena |

---

## 3. Config Rules Customizadas WAYFINDER-001 a WAYFINDER-014

Todas as rules customizadas são implementadas via Lambda `compliance-evaluator`
e registradas no AWS Config como `CUSTOM_LAMBDA` rules.

### WAYFINDER-001  S3 com Dados de Saúde sem Criptografia KMS CMK

```
ID:            WAYFINDER-001
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Avaliação:     Bucket com tag data-classification=health-* DEVE ter
               SSE-KMS com CMK gerenciado pelo cliente (não SSE-S3 nem AWS Managed Key)
Não-conforme:  Severidade CRITICAL
Remediação:    Automática  habilita SSE-KMS com CMK health-critical
Prazo:         Remediação em < 5 minutos após detecção
LGPD:          Art. 46, 49 | ISO 27001: A.8.24
Evidência:     CloudTrail: s3:PutBucketEncryption + Config timeline
Lição do incidente: Bucket vitacore-laudos-imagens-prod usava SSE-S3
```

### WAYFINDER-002  S3 com Dados de Saúde com Acesso Público Habilitado

```
ID:            WAYFINDER-002
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Avaliação:     Bucket com tag data-classification=health-* DEVE ter
               BlockPublicAcls=true, IgnorePublicAcls=true,
               BlockPublicPolicy=true, RestrictPublicBuckets=true
Não-conforme:  Severidade CRITICAL
Remediação:    Automática  ativa Block Public Access em 4 dimensões
Prazo:         Remediação em < 5 minutos após detecção
LGPD:          Art. 46 | ISO 27001: A.8.20
Evidência:     CloudTrail: s3:PutPublicAccessBlock
LIÇÃO DIRETA DO INCIDENTE DE MARÇO 2026: Esta rule teria detectado e
remediado o incidente em < 5 minutos em vez de 18 dias.
```

### WAYFINDER-003  CloudTrail Desabilitado

```
ID:            WAYFINDER-003
Tipo:          CUSTOM_LAMBDA (complementa Managed Rule cloud-trail-enabled)
Trigger:       Periódico (a cada 30 minutos) + ConfigurationItemChangeNotification
Avaliação:     CloudTrail trail deve estar IsLogging=true em todas as regiões ativas.
               Avalia também: S3 data events habilitados para buckets health-*
               Multi-region trail, log file validation habilitada
Não-conforme:  Severidade CRITICAL
Remediação:    Automática  reabilita trail e notifica SecOps
Prazo:         Detecção em < 30 minutos (avaliação periódica)
LGPD:          Art. 37, 48 | ISO 27001: A.8.15
LIÇÃO DO INCIDENTE: CloudTrail ficou desabilitado 43 dias sem detecção.
Esta rule garante que máximo 30 minutos de downtime do trail sem alerta.
```

### WAYFINDER-004  RDS sem Criptografia em Repouso

```
ID:            WAYFINDER-004
Tipo:          CUSTOM_LAMBDA (complementa Managed Rule rds-storage-encrypted)
Trigger:       ConfigurationItemChangeNotification (RDS DBInstance, DBCluster)
Avaliação:     RDS Instance/Cluster DEVE ter StorageEncrypted=true
               Avalia também: KmsKeyId deve ser CMK (não AWS managed key)
               para clusters com tag data-classification=health-*
Não-conforme:  Severidade HIGH (CRITICAL para clusters health-critical)
Remediação:    Semi-automática  cria snapshot criptografado e notifica para
               recriação do cluster (não é possível criptografar in-place)
LGPD:          Art. 46 | ISO 27001: A.8.24
Contexto VitaCore: 1 cluster Aurora sem criptografia (histórico legacy) identificado
```

### WAYFINDER-005  IAM com Permissões Administrativas Excessivas

```
ID:            WAYFINDER-005
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (IAM Policy, IAM Role)
Avaliação:     Nenhuma IAM Policy deve ter:
               Effect=Allow, Action=["*"] ou Action=["*:*"], Resource="*"
               em ambiente prod. Em dev, alertar mas não remediar.
               Avalia roles inline policies e managed policies attachadas.
Não-conforme:  Severidade HIGH
Remediação:    Semi-automática  detach da policy ofensora + notificação com
               sugestão de política com least privilege
LGPD:          Art. 6, IV (necessidade), Art. 47 | ISO 27001: A.8.2, A.5.15
Contexto VitaCore: 12 IAM Roles com AdministratorAccess em produção
```

### WAYFINDER-006  EC2 com Dados de Saúde em Subnet Pública

```
ID:            WAYFINDER-006
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (EC2 Instance)
Avaliação:     EC2 Instance com tag data-classification=health-* NÃO DEVE
               estar em subnet pública (definida como subnet com route para IGW)
Não-conforme:  Severidade CRITICAL
Remediação:    Automática  adiciona Security Group de quarentena (bloqueia
               todo tráfego de entrada) + notificação imediata para SecOps
LGPD:          Art. 46, 49 | ISO 27001: A.8.20
Contexto VitaCore: 4 instâncias EC2 em subnets públicas processando dados de pacientes
```

### WAYFINDER-007  Credenciais Potenciais em Variáveis de Ambiente Lambda

```
ID:            WAYFINDER-007
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (Lambda Function)
Avaliação:     Variáveis de ambiente de Lambda NÃO DEVEM conter padrões como:
               - PASSWORD, PASSWD, SECRET, KEY, TOKEN, CREDENTIAL (case-insensitive)
               com valores não-ARN (valores que não são arn:aws:secretsmanager:...)
               Regex: /(password|passwd|secret|db_pass|api_key|token)/i
Não-conforme:  Severidade HIGH
Remediação:    Notificação com guia de migração para Secrets Manager
LGPD:          Art. 46 | ISO 27001: A.8.11 (gestão de segredos)
```

### WAYFINDER-008  CloudWatch Logs sem Criptografia KMS

```
ID:            WAYFINDER-008
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (CloudWatch Log Group)
Avaliação:     Log Groups com prefixo /vitacore/ ou /aws/lambda/wayfinder*
               DEVEM ter kmsKeyId configurado
Não-conforme:  Severidade MEDIUM
Remediação:    Automática  associa CMK ao Log Group
LGPD:          Art. 46 | ISO 27001: A.8.24
```

### WAYFINDER-009  Security Group com SSH/RDP Aberto para a Internet

```
ID:            WAYFINDER-009
Tipo:          CUSTOM_LAMBDA (complementa restricted-ssh Managed Rule)
Trigger:       ConfigurationItemChangeNotification (EC2 SecurityGroup)
Avaliação:     Nenhum Security Group deve ter inbound rule:
               Port 22 (SSH) ou 3389 (RDP) com source 0.0.0.0/0 ou ::/0
               Extensão: também avalia 3306 (MySQL), 5432 (PostgreSQL), 6379 (Redis)
Não-conforme:  Severidade CRITICAL (SSH/RDP) | HIGH (DB ports)
Remediação:    Automática  remove a regra ofensora + registra no audit trail
LGPD:          Art. 46 | ISO 27001: A.8.20, A.8.21
```

### WAYFINDER-010  DynamoDB sem Criptografia em Repouso

```
ID:            WAYFINDER-010
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (DynamoDB Table)
Avaliação:     Tabelas DynamoDB com tag data-classification=health-* DEVEM ter
               SSESpecification.SSEType = KMS (com CMK, não AWS_OWNED_KMS)
Não-conforme:  Severidade HIGH
Remediação:    Semi-automática  DynamoDB pode mudar SSE in-place; Lambda
               executa update-table para habilitar CMK
LGPD:          Art. 46 | ISO 27001: A.8.24
Contexto VitaCore: DynamoDB para wearable data processando health-standard
```

### WAYFINDER-011  ECS Task com Privilégio Elevado (privileged=true)

```
ID:            WAYFINDER-011
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (ECS TaskDefinition)
Avaliação:     Container definitions em ECS Task Definitions NÃO DEVEM ter
               privileged=true em ambientes não-explicitamente isentos
               Também avalia: user="root", readonlyRootFilesystem=false
Não-conforme:  Severidade HIGH
Remediação:    Notificação para Dev Lead com guia de segurança de containers
LGPD:          Art. 49 (segurança desde a concepção) | ISO 27001: A.8.9
```

### WAYFINDER-012  IAM Access Key com mais de 90 Dias sem Rotação

```
ID:            WAYFINDER-012
Tipo:          CUSTOM_LAMBDA (complementa access-keys-rotated Managed Rule)
Trigger:       Periódico (diário)
Avaliação:     IAM Users com access keys com LastUsedDate > 90 dias sem rotação
               Alerta em 75 dias, non-compliant em 90, desativa em 95 dias
Não-conforme:  Severidade MEDIUM (75d), HIGH (90d), CRITICAL (95d com desativação)
Remediação:    Semi-automática  desativa a key aos 95 dias + notificação ao owner
LGPD:          Art. 47 | ISO 27001: A.5.17 (gestão de credenciais)
Contexto VitaCore: 67 IAM Users, sem processo de rotação de keys
```

### WAYFINDER-013  S3 sem Object Lock para Dados com Retenção Obrigatória

```
ID:            WAYFINDER-013
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (S3 Bucket)
Avaliação:     Buckets com tag retention-required=true DEVEM ter:
               Object Lock habilitado com modo COMPLIANCE
               Retention period  valor da tag retention-days
Não-conforme:  Severidade HIGH
Remediação:    Notificação (Object Lock não pode ser habilitado em bucket existente
               sem dados  requer criação de novo bucket)
LGPD:          Art. 37 (registro de operações) | CFM 1821/2007 (20 anos)
Contexto: Prontuários exigem Object Lock COMPLIANCE por 20 anos
```

### WAYFINDER-014  Secrets Manager não Usado (Possíveis Credenciais Hardcoded)

```
ID:            WAYFINDER-014
Tipo:          CUSTOM_LAMBDA
Trigger:       ConfigurationItemChangeNotification (Lambda, ECS TaskDefinition, EC2)
Avaliação:     Recursos com tag data-classification=health-* DEVEM referenciar
               pelo menos 1 secret do Secrets Manager via ARN em suas configurações.
               Recursos sem nenhuma referência a Secrets Manager são suspeitos.
Não-conforme:  Severidade HIGH
Remediação:    Notificação com guia de migração + criação de ticket Jira automático
LGPD:          Art. 46 (segurança no tratamento) | ISO 27001: A.8.11
```

---

## 4. Managed Rules Adicionais

| Rule Key | AWS Identifier | Propósito | Artigo LGPD |
|---|---|---|---|
| `guardduty-enabled-centralized` | GUARDDUTY_ENABLED_CENTRALIZED | Detecção de ameaças ML | Art. 46 |
| `securityhub-enabled` | SECURITYHUB_ENABLED | Postura consolidada | Art. 50 |
| `inspector-ec2-scan-enabled` | INSPECTOR_EC2_SCANNING_ENABLED | Vulns em EC2/ECR | Art. 46, 49 |
| `access-keys-rotated` | ACCESS_KEYS_ROTATED | Rotação de access keys | Art. 47 |
| `iam-password-policy` | IAM_PASSWORD_POLICY | Política de senha forte | Art. 46 |
| `restricted-ssh` | RESTRICTED_INCOMING_TRAFFIC | Bloqueia SSH público | Art. 46 |
| `restricted-common-ports` | RESTRICTED_COMMON_PORTS | Portas DB não expostas | Art. 46 |
| `dynamodb-table-encrypted-at-rest` | DYNAMODB_TABLE_ENCRYPTED_AT_REST | DynamoDB criptografado | Art. 46 |
| `elasticache-redis-cluster-backup` | ELASTICACHE_REDIS_CLUSTER_AUTOMATIC_BACKUP_CHECK | Redis com backup | Art. 46 |
| `wafv2-webacl-not-empty` | WAFV2_WEBACL_NOT_EMPTY | WAF configurado | Art. 46 |
| `secretsmanager-rotation-enabled` | SECRETSMANAGER_ROTATION_ENABLED_CHECK | Rotação de secrets | Art. 47 |
| `backup-plan-min-frequency` | BACKUP_PLAN_MIN_FREQUENCY_AND_MIN_RETENTION_CHECK | Backup adequado | Art. 46 |

---

## 5. Matriz de Impacto  Incidente de Março 2026

Esta matriz responde: "Se o Wayfinder Cloud estivesse operacional em 15/03/2026,
o que teria acontecido?"

| Controle | Teria Detectado? | Teria Remediado? | Tempo Estimado de Detecção | Resultado com Wayfinder |
|---|---|---|---|---|
| WAYFINDER-002 (S3 público) |  Sim |  Sim (automático) | < 5 minutos | Block Public Access reativado antes de qualquer acesso externo |
| WAYFINDER-001 (sem KMS CMK) |  Sim |  Sim (automático) | < 5 minutos | SSE-KMS habilitado  dados ilegíveis mesmo se acessados |
| Managed: s3-bucket-public-read-prohibited |  Sim |  Não | < 15 minutos | Alerta enviado; remediação manual necessária |
| WAYFINDER-003 (CloudTrail) | N/A | N/A |  | CloudTrail habilitado; acesso ao bucket teria sido registrado |
| GuardDuty (acesso anômalo) |  Sim (após 1h de acessos) |  Não | ~1 hora | Finding UnauthorizedAccess:S3/MaliciousIPCaller |
| CloudWatch Alarm (S3 requests spike) |  Sim |  Não | ~30 minutos | Alarme disparado por volume anormal de GET requests |

**Conclusão:** Com o Wayfinder Cloud ativo, o incidente teria sido contido em menos
de 5 minutos, com 0 dados efetivamente expotos a acessos externos (graças à
remediação automática). Custo evitado: ~R$ 2,1 milhões.

---

## 6. Classificação de Dados  5 Níveis

| Nível | Tag Value | Exemplos | Controles Obrigatórios | Período de Retenção |
|---|---|---|---|---|
| **health-critical** | `health-critical` | Prontuários, laudos de imagem, diagnósticos, gravações de teleconsulta, prescrições | KMS CMK dedicado, VPC subnet privada, CloudTrail data events, MFA obrigatório, S3 Object Lock COMPLIANCE, backup diário | 20 anos (prontuários/CFM), 5 anos (outros) |
| **health-standard** | `health-standard` | Dados de wearables, sinais vitais agregados, dados de saúde não identificados diretamente | KMS AWS Managed Key, subnet privada, CloudTrail, backup semanal | 3 anos |
| **financial-sensitive** | `financial-sensitive` | Dados de faturamento, cobranças, informações de plano de saúde | KMS CMK, subnet privada, CloudTrail management events | 10 anos (legislação fiscal) |
| **operational** | `operational` | Logs de aplicação, métricas de sistema, traces X-Ray | SSE-S3, CloudWatch, lifecycle para Glacier em 90 dias | 90 dias hot, 1 ano Glacier |
| **public** | `public` | Assets estáticos (CSS, JS, imagens de marketing), documentação pública | Sem restrições especiais | Sem retenção mínima obrigatória |

---

## 7. Período de Retenção Legal por Tipo de Dado

| Tipo de Dado | Período Mínimo | Base Legal | Implementação Técnica |
|---|---|---|---|
| Prontuário eletrônico completo | **20 anos** após último registro | CFM 1821/2007, CFM 1638/2002 | S3 Object Lock COMPLIANCE 7.305 dias |
| Laudo de imagem (RX, TC, RM) | **5 anos** (alguns estados: 10 anos) | CFM 1821/2007 | S3 Object Lock COMPLIANCE 1.825 dias |
| Gravação de teleconsulta | **5 anos** | CFM 2314/2022 | S3 Object Lock COMPLIANCE 1.825 dias |
| Prescrição eletrônica | **5 anos** | CFM + RDC ANVISA 204/2017 | S3 Object Lock COMPLIANCE 1.825 dias |
| Consentimento LGPD | Durante relação + **5 anos** após | LGPD art. 8 | Aurora MySQL + backup S3 Object Lock |
| Trilha de auditoria (CloudTrail) | **5 anos** (contratual com operadoras) | Contrato VitaCore + LGPD art. 37 | S3 Object Lock COMPLIANCE 1.825 dias |
| Dados de faturamento | **10 anos** | Lei 9.430/1996 (fiscal), RFB | S3 Intelligent-Tiering + lifecycle |
| Dados de wearables brutos | **3 anos** | Política interna VitaCore | S3 lifecycle: Glacier em 90 dias, expirar em 3 anos |
| Logs de aplicação | **90 dias** hot, **1 ano** total | Política interna | CloudWatch Logs 90d + exportar para S3 Glacier |

---

## 8. Processo de Resposta a Incidentes  LGPD Art. 48

```
FASE 1: DETECÇÃO (< 5 min)

 Config Rule NON_COMPLIANT ou GuardDuty CRITICAL finding      
  EventBridge  Lambda incident-notifier                     
  SNS CRITICAL  Email DPO + CTO + SecOps + PagerDuty       
  Lambda auto-remediation (contenção automática se aplicável)


FASE 2: AVALIAÇÃO (< 30 min)

 SecOps (Bruno Oliveira) executa Runbook RB-001               
  Athena query: quais dados foram acessados?                 
  Athena query: quais IPs acessaram os dados?                
  Conta número de titulares afetados                         
  Classifica como Incidente LGPD se dados sensíveis          


FASE 3: CONTENÇÃO (< 1h)

 Remediação automática já executada (se WAYFINDER-002)        
 Se manual: SecOps segue Runbook RB-001 seção 4               
  Isolamento do recurso afetado                              
  Preservação de evidências (snapshot, logs)                 


FASE 4: NOTIFICAÇÃO INTERNA (< 4h após ciência)

 DPO Ana Lima notifica CEO Marcos Ferreira                    
  Ticket Jira tipo "LGPD Incident" criado                    
  Template de comunicação interna preenchido                 


FASE 5: NOTIFICAÇÃO ANPD (< 48h após ciência  SLA interno)

 DPO submete comunicação via portal ANPD (art. 48 1)       
 Dados obrigatórios na comunicação:                           
   a) Natureza dos dados pessoais afetados                    
   b) Informações sobre os titulares                          
   c) Indicação das medidas técnicas e de segurança           
   d) Riscos relacionados ao incidente                        
   e) Motivos da demora (se não foi comunicado em 72h)        
 Lambda audit-reporter gera relatório pré-preenchido          


FASE 6: DOCUMENTAÇÃO E LIÇÕES APRENDIDAS (< 7 dias)

 Post-mortem documentado em Confluence                        
  Nova Config Rule criada para prevenir recorrência          
  Relatório final armazenado em S3 com Object Lock           

```

---

## 9. Referências

- [LGPD  Lei n 13.709/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [CFM 1821/2007  Prontuário Eletrônico](https://www.cfm.org.br/index.php/noticias/item/290-resolucao-cfm-no-18212007.html)
- [AWS FSBP  Foundational Security Best Practices](https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html)
- [CIS AWS Foundations Benchmark v1.4](https://www.cisecurity.org/benchmark/amazon_web_services)
- [ANPD  Guia Orientativo para Definições dos Agentes de Tratamento](https://www.gov.br/anpd)
- [AWS Config Developer Guide  Custom Rules](https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config_develop-rules.html)
- [S3 Object Lock COMPLIANCE mode](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
