# RB-004  Resposta a GuardDuty Findings

**Runbook:** RB-004 | **Versão:** 1.0  
**Responsável primário:** Bruno Oliveira (SecOps Lead)  
**Backup:** Rafael Santos (CTO)  
**Classificação:** Operacional  Confidencial  
**Última revisão:** 2026-08-21

---

## 1. Visão Geral

Este runbook documenta os procedimentos de resposta a findings do Amazon GuardDuty
no contexto da VitaCore Health. Dado o volume e sensibilidade dos dados processados
(127.000 pacientes, dados classificados como health-critical), findings de segurança
devem ser tratados com urgência máxima.

**Tempo máximo de resposta por severidade:**
| Severidade GuardDuty | Severidade Wayfinder | SLA de Triagem | SLA de Contenção |
|---|---|---|---|
| HIGH (7.08.9) | CRITICAL | < 15 minutos | < 1 hora |
| MEDIUM (4.06.9) | HIGH | < 1 hora | < 4 horas |
| LOW (1.03.9) | MEDIUM | < 4 horas | < 24 horas |

---

## 2. Finding Types Mais Comuns  Ambiente de Saúde Digital

### 2.1 Mapa de Finding Types por Família

| Família | Finding Type | Frequência Estimada | Risco VitaCore |
|---|---|---|---|
| **Recon** | Recon:EC2/PortProbing | Média | Médio |
| **Recon** | Recon:EC2/Portscan | Baixa | Médio |
| **UnauthorizedAccess** | UnauthorizedAccess:EC2/SSHBruteForce | Alta | Alto |
| **UnauthorizedAccess** | UnauthorizedAccess:IAMUser/ConsoleLoginSuccess | Baixa | CRÍTICO |
| **UnauthorizedAccess** | UnauthorizedAccess:S3/MaliciousIPCaller | Baixa | CRÍTICO |
| **UnauthorizedAccess** | UnauthorizedAccess:IAMUser/MaliciousIPCaller | Baixa | CRÍTICO |
| **Trojan** | Trojan:EC2/BlackholeTraffic | Baixa | Alto |
| **Trojan** | Trojan:EC2/DropPoint | Baixa | Alto |
| **CryptoCurrency** | CryptoCurrency:EC2/BitcoinTool.B | Baixa | Médio |
| **Backdoor** | Backdoor:EC2/C&CActivity.B | Muito Baixa | CRÍTICO |
| **PenTest** | PenTest:IAMUser/KaliLinux | Baixa | Médio |
| **Discovery** | Discovery:S3/AnomalousBehavior | Média | Alto (pós-incidente) |
| **Exfiltration** | Exfiltration:S3/AnomalousBehavior | Muito Baixa | CRÍTICO |
| **Impact** | Impact:S3/AnomalousBehavior | Muito Baixa | CRÍTICO |

---

## 3. Procedimentos por Finding Type

### 3.1 Recon  Reconhecimento de Infraestrutura

**Aplicável a:** Recon:EC2/PortProbing, Recon:EC2/Portscan

```
PASSO 1  Identificar recurso alvo
   Console GuardDuty  Finding details  Resource affected
   Anote: instance ID, IP público, Security Groups

PASSO 2  Verificar se EC2 é legítima
   SSM Session Manager: aws ssm start-session --target <instance-id>
   Verifique tags: deve ter Environment, Project, Owner
   Se EC2 não tem tags  possivelmente recurso órfão  ESCALAR para CTO

PASSO 3  Verificar VPC Flow Logs
   Athena query (ver seção 5.1)
   Identifique quais portas foram sondadas
   Se porta 3306, 5432, 6379  dados de banco acessados?  ESCALAR

PASSO 4  Ação
   Se EC2 em subnet pública COM dados de saúde  ativar WAYFINDER-006 manualmente
   Se reconhecimento externo sem acesso bem-sucedido  registrar + monitorar
   Atualizar Security Groups: remover regras desnecessárias (WAYFINDER-009)
   Timeout de 24h sem incidente adicional  resolver finding

SEVERIDADE WAYFINDER: MEDIUM (sem acesso confirmado) / HIGH (se porta DB sondada)
```

### 3.2 UnauthorizedAccess  Acesso Não Autorizado

**Aplicável a:** UnauthorizedAccess:EC2/SSHBruteForce, UnauthorizedAccess:IAMUser/*, UnauthorizedAccess:S3/*

```
CASO A: SSHBruteForce
PASSO 1  Verificar se porta 22 está aberta publicamente
   aws ec2 describe-security-groups --group-ids <sg-id>
   Se yes  auto-remediation WAYFINDER-009 deve ter fechado  confirmar
   Se ainda aberta  fechar IMEDIATAMENTE via CLI

PASSO 2  Verificar acessos bem-sucedidos
   Athena query 5.2: login bem-sucedido nas últimas 4h no instance?
   Se sim  INCIDENTE DE SEGURANÇA  seguir RB-001

CASO B: IAMUser/ConsoleLoginSuccess de IP suspeito
PASSO 1  CRÍTICO  Revogar sessões ativas imediatamente
   aws iam delete-user-login-profile --user-name <user>
   Ou: aws cognito-idp admin-user-global-sign-out (se via Identity Center)

PASSO 2  Revogar credenciais
   aws iam deactivate-mfa-device (se MFA comprometido)
   aws iam delete-access-key --access-key-id <key>
   Forçar reset de senha

PASSO 3  Investigar ações realizadas
   Athena query 5.3: todas as ações do usuário nas últimas 24h
   Escopo da comprometimento: quais recursos foram acessados?
   Se dados de saúde acessados  INCIDENTE LGPD  notificar DPO

CASO C: S3/MaliciousIPCaller (exatamente o incidente de março)
PASSO 1  VERIFICAR SE BUCKET ESTÁ PÚBLICO (15 minutos)
   aws s3api get-public-access-block --bucket <bucket-name>
   Se todos false  INCIDENTE LGPD em andamento
   WAYFINDER-002 deve ter remediado  se não  remediar manualmente:
    aws s3api put-public-access-block --bucket <bucket> \
      --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

PASSO 2  Identificar dados acessados
   CloudTrail S3 data events: quais objetos foram GET?
   Athena query 5.4: objetos acessados com classificação health-*
   Conta objetos únicos + pacientes afetados

PASSO 3  Notificação LGPD
   Se dados de saúde acessados por IP externo  INCIDENTE LGPD
   Notificar DPO Ana Lima IMEDIATAMENTE (< 15 min)
   DPO inicia processo art. 48 (72h para ANPD)
   Ver RB-001 seção 5 para template de comunicação

SEVERIDADE WAYFINDER: CRITICAL para S3 e IAMUser/Console
```

### 3.3 Trojan  Atividade Maliciosa em EC2

**Aplicável a:** Trojan:EC2/BlackholeTraffic, Trojan:EC2/DropPoint

```
PASSO 1  ISOLAMENTO IMEDIATO da instância
   aws ec2 create-security-group --description "QUARANTINE-$(date +%Y%m%d)" ...
   aws ec2 modify-instance-attribute --instance-id <id> --groups <quarantine-sg>
   A instância fica sem ingress/egress (quarentena total)

PASSO 2  Snapshot forense antes de qualquer ação destrutiva
   aws ec2 create-snapshot --volume-id <volume-id> \
      --description "ForensicSnapshot-$(date +%Y%m%d-%H%M)"
   Registrar snapshot ID no ticket de incidente

PASSO 3  Análise de tráfego suspeito
   Athena query 5.5: VPC Flow Logs da instância nas últimas 24h
   Identifique IPs de C&C (Command and Control)
   Verifique se instância tem acesso a Aurora/DynamoDB

PASSO 4  Escalar para análise forense
   Engajar consultoria de forense digital (se disponível)
   AWS Security IR Team (suporte Premium) se necessário
   NÃO fazer login na instância  pode contaminar evidências

PASSO 5  Criar nova instância limpa (se necessário)
   Deploy via GitHub Actions com imagem ECR nova
   Terminar instância comprometida após análise forense

SEVERIDADE WAYFINDER: HIGH  CRITICAL se dados acessados
```

### 3.4 CryptoCurrency  Mineração de Criptomoeda

**Aplicável a:** CryptoCurrency:EC2/BitcoinTool.B

```
PASSO 1  Verificar uso de CPU (indicador principal)
   aws cloudwatch get-metric-statistics --namespace AWS/EC2 \
      --metric-name CPUUtilization --statistics Maximum \
      --dimensions Name=InstanceId,Value=<id>
   Se CPU > 90% consistente  forte indicação de mineração

PASSO 2  Identificar processo responsável (via SSM)
   aws ssm send-command --instance-ids <id> \
      --document-name AWS-RunShellScript \
      --parameters commands='["ps aux --sort=-%cpu | head -20"]'
   Procure por processos desconhecidos (xmrig, minergate, etc.)

PASSO 3  Verificar vetor de comprometimento
   Athena query 5.6: como o processo foi iniciado? (SSM history, SSH logs)
   Identificar vulnerabilidade explorada (Inspector findings pendentes?)

PASSO 4  Remediar
   Se ECS Fargate: force new deployment (mata task comprometida)
   Se EC2: seguir procedimento Trojan (isolamento + snapshot + nova instância)
   Abrir ticket de segurança com Inspector finding associado

IMPACTO FINANCEIRO: Mineração pode inflar custo AWS em 200-400%
NOTIFICAR: CTO (custo) + SecOps (segurança)
SEVERIDADE WAYFINDER: MEDIUM (sem acesso a dados) / HIGH (se comprometido há > 24h)
```

### 3.5 Backdoor  Atividade de C&C

**Aplicável a:** Backdoor:EC2/C&CActivity.B

```
ATENÇÃO: Este é o finding mais grave  indica comprometimento persistente.

PASSO 1  ISOLAMENTO IMEDIATO (< 5 minutos)
   Seguir procedimento de isolamento do Trojan PASSO 1

PASSO 2  NOTIFICAÇÃO IMEDIATA
   Ligar para CTO Rafael Santos (não apenas email)
   Notificar DPO Ana Lima (possível exfiltração de dados)
   Considerar envolver AWS Security IR (via AWS Support)

PASSO 3  PRESERVAÇÃO DE EVIDÊNCIAS
   Snapshot de todos os volumes da instância
   Exportar VPC Flow Logs, CloudTrail e GuardDuty findings para S3 imutável
   NÃO reiniciar ou modificar a instância

PASSO 4  AVALIAÇÃO DE ESCOPO
   Athena query 5.3: todas as ações realizadas pela instância nas últimas 72h
   Quais dados foram acessados? Há exfiltração confirmada?
   Há outros recursos comprometidos? (lateral movement)

PASSO 5  Se dados de saúde exfiltrados  INCIDENTE LGPD
   Acionar RB-001 completo
   DPO inicia processo de notificação ANPD (art. 48)
   CEO deve ser informado diretamente

SEVERIDADE WAYFINDER: CRITICAL  incidente de segurança ativo
```

---

## 4. Correlação GuardDuty Findings × CloudTrail

GuardDuty identifica o "o quê e quem", CloudTrail detalha "exatamente o que foi feito":

```
GuardDuty Finding
    
     resource.type = "AwsEc2Instance"
        Correlacionar via: aws ec2 describe-instances --instance-ids <id>
            Tags, Security Groups, VPC, Subnet (pública/privada?)
    
     resource.type = "AwsIamUser"
        Athena: CloudTrail com userIdentity.userName = <user>
            Todas as actions realizadas no período do finding
    
     resource.type = "AwsS3Bucket"
         Athena: CloudTrail S3 data events com requestParameters.bucketName = <bucket>
             GET requests no período (quais objetos foram baixados?)
             Source IPs que acessaram

Campos do GuardDuty Finding relevantes para correlação:
  - finding.service.eventFirstSeen / eventLastSeen  janela temporal do CloudTrail
  - finding.service.remoteIpDetails.ipAddressV4  filtrar no CloudTrail por sourceIPAddress
  - finding.service.action.awsApiCallAction.api  API específica chamada
  - finding.accountId + finding.region  contexto do CloudTrail
```

---

## 5. Queries Athena para Investigação

**Pré-requisito:** Workgroup `wayfinder-audit`, Database `wayfinder_audit`

### 5.1 VPC Flow Logs  Tráfego de Reconhecimento

```sql
-- Query 5.1: Conexões de reconhecimento para instância específica (últimas 24h)
SELECT
  srcaddr,
  dstport,
  COUNT(*) as connection_attempts,
  SUM(CASE WHEN action = 'ACCEPT' THEN 1 ELSE 0 END) as accepted,
  SUM(CASE WHEN action = 'REJECT' THEN 1 ELSE 0 END) as rejected
FROM vpc_flow_logs
WHERE dstaddr = '<ec2-private-ip>'
  AND start >= to_unixtime(now() - interval '24' hour)
  AND dstport IN (22, 3306, 5432, 6379, 443, 80, 8080, 27017)
GROUP BY srcaddr, dstport
ORDER BY connection_attempts DESC
LIMIT 50;
```

### 5.2 SSH  Tentativas e Sucessos

```sql
-- Query 5.2: Tentativas SSH na instância com distinção aceitos/rejeitados
SELECT
  DATE_FORMAT(from_unixtime(start), '%Y-%m-%d %H:%i') as timestamp,
  srcaddr as source_ip,
  dstport,
  action,
  protocol
FROM vpc_flow_logs
WHERE dstaddr = '<ec2-private-ip>'
  AND dstport = 22
  AND start >= to_unixtime(now() - interval '4' hour)
ORDER BY start DESC;
```

### 5.3 Ações IAM  Usuário Comprometido

```sql
-- Query 5.3: Todas as ações de um usuário IAM (janela temporal do GuardDuty finding)
SELECT
  eventtime,
  eventsource,
  eventname,
  sourceipaddress,
  useragent,
  requestparameters,
  responseelements,
  errorcode
FROM cloudtrail_logs
WHERE useridentity.username = '<iam-username>'
  AND eventtime BETWEEN '<finding.firstSeen>' AND '<finding.lastSeen>'
  AND errorcode IS NULL  -- ações bem-sucedidas apenas
ORDER BY eventtime DESC;
```

### 5.4 S3 Data Events  Objetos Acessados (Incidente de Exposição)

```sql
-- Query 5.4: Objetos S3 acessados por IPs externos (contexto do incidente de março)
SELECT
  eventtime,
  eventname,
  sourceipaddress,
  requestparameters,
  JSON_EXTRACT(requestparameters, '$.bucketName') as bucket_name,
  JSON_EXTRACT(requestparameters, '$.key') as object_key,
  useragent
FROM cloudtrail_logs
WHERE eventsource = 's3.amazonaws.com'
  AND eventname IN ('GetObject', 'ListObjects', 'ListObjectsV2')
  AND sourceipaddress NOT LIKE '%.amazonaws.com'
  AND JSON_EXTRACT(requestparameters, '$.bucketName') = '<bucket-name>'
  AND eventtime >= '<date>'
ORDER BY eventtime;
```

### 5.5 VPC Flow Logs  Tráfego de Saída Suspeito (Trojan/Backdoor)

```sql
-- Query 5.5: Tráfego de saída anômalo de instância (C&C ou exfiltração)
SELECT
  dstaddr as destination_ip,
  dstport,
  SUM(bytes) as total_bytes_sent,
  COUNT(*) as connection_count,
  MIN(from_unixtime(start)) as first_seen,
  MAX(from_unixtime(end)) as last_seen
FROM vpc_flow_logs
WHERE srcaddr = '<ec2-private-ip>'
  AND action = 'ACCEPT'
  AND dstaddr NOT LIKE '10.%'
  AND dstaddr NOT LIKE '172.16.%'
  AND start >= to_unixtime(now() - interval '24' hour)
GROUP BY dstaddr, dstport
ORDER BY total_bytes_sent DESC
LIMIT 30;
```

### 5.6 CloudTrail  Vetor de Comprometimento (Mineração/Backdoor)

```sql
-- Query 5.6: Ações recentes em instância via SSM ou EC2 (identificar comprometimento)
SELECT
  eventtime,
  eventname,
  useridentity.arn as actor,
  sourceipaddress,
  requestparameters
FROM cloudtrail_logs
WHERE (eventsource = 'ssm.amazonaws.com' OR eventsource = 'ec2.amazonaws.com')
  AND (requestparameters LIKE '%<instance-id>%'
       OR responseelements LIKE '%<instance-id>%')
  AND eventtime >= DATE_FORMAT(now() - interval '72' hour, '%Y-%m-%dT%H:%i:%sZ')
ORDER BY eventtime DESC;
```

---

## 6. Matriz de Contenção por Finding Type

| Finding Type | Contenção Automática (Wayfinder) | Contenção Manual | Notificação |
|---|---|---|---|
| Recon:EC2/PortProbing | Nenhuma | Security Group review | SNS WARNING |
| UnauthorizedAccess:EC2/SSHBruteForce | WAYFINDER-009 fecha porta 22 | Verificar acessos bem-sucedidos | SNS CRITICAL |
| UnauthorizedAccess:S3/MaliciousIPCaller | WAYFINDER-002 ativa Block Public Access | Investigar dados acessados | SNS CRITICAL + DPO |
| UnauthorizedAccess:IAMUser/ConsoleLoginSuccess | Nenhuma automática | Revogar sessão + credenciais | SNS CRITICAL + CTO |
| Trojan:EC2/* | Nenhuma automática | Isolamento manual + snapshot | SNS CRITICAL |
| CryptoCurrency:EC2/* | Nenhuma automática | Investigar + redeploy | SNS HIGH |
| Backdoor:EC2/C&CActivity.B | Nenhuma automática | Isolamento IMEDIATO | SNS CRITICAL + CTO + DPO |
| Exfiltration:S3/* | WAYFINDER-002 (se via public access) | Investigação forense | SNS CRITICAL + DPO (art. 48) |
| Discovery:S3/AnomalousBehavior | Nenhuma automática | Revisar permissões IAM | SNS WARNING |

---

## 7. Integração GuardDuty  EventBridge  Lambda

O módulo `security` do Wayfinder Cloud configura a seguinte integração automática:

```hcl
# EventBridge rule: GuardDuty findings  compliance-evaluator Lambda
# Filtra apenas MEDIUM, HIGH e CRITICAL para evitar ruído
resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      severity = [{ numeric = [">=", 4.0] }]  # MEDIUM e acima
    }
  })
}
```

A Lambda `incident-notifier` formata o finding em mensagem legível:
```
[WAYFINDER SECURITY ALERT]
Severidade: HIGH
Finding: UnauthorizedAccess:S3/MaliciousIPCaller
Recurso: s3://vitacore-laudos-imagens-prod
Conta: 123456789012 | Região: us-east-1
Horário: 2026-03-15T14:34:00Z

Descrição: Acesso ao bucket S3 a partir de IP associado a atividade maliciosa.
IP origem: 45.33.32.156 (VirusTotal: malicious)

Ações tomadas automaticamente:
 Block Public Access reativado (WAYFINDER-002)
 CloudWatch Alarm disparado

Próximos passos:
1. Verificar CloudTrail: quais objetos foram acessados?
2. Confirmar número de pacientes afetados
3. Se dados de saúde: notificar DPO (LGPD art. 48)

Athena query sugerida: RB-004 Query 5.4
Runbook: https://wiki.vitacore.health/runbooks/RB-004
```
