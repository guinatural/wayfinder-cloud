# Runbook RB-001  Resposta a Incidente de Segurança

**Project:** Wayfinder Cloud  
**Versão:** 1.0  
**Classificação:** OPERACIONAL  
**SLA de execução:** CRITICAL  15 min | HIGH  2h | MEDIUM  24h

---

## Objective

Documentar o procedimento de resposta a incidentes detectados pelo Wayfinder Cloud,
garantindo Compliance com o art. 48 da LGPD (comunicação de incidentes em 72h).

---

## Severidades e SLAs

| Severidade | Definição | SLA Inicial | Notificação ANPD |
|---|---|---|---|
| CRITICAL | Dados de saúde expostos ou risco iminente de exposição | 15 min | Obrigatória se confirmado |
| HIGH | Controle de segurança desabilitado, potencial exposição | 2h | Avaliar após investigação |
| MEDIUM | Desvio de Compliance sem risco imediato | 24h | Normalmente não necessária |
| LOW | Drift de configuração de baixo risco | 72h | Não necessária |

---

## Fase 1  Detecção (automática)

O Wayfinder Cloud detecta e classifica automaticamente. Esta fase não requer intervenção humana.

```
1. Config Rule avalia recurso  NON_COMPLIANT
2. EventBridge recebe evento  roteia para compliance-evaluator
3. Lambda enriquece evento com Context e classifica severidade
4. SNS notifica SecOps via email + Slack
5. Se CRITICAL: Lambda auto-remediation executa ação segura
```

**Verificação:** CloudWatch Dashboard  aba "Incidents" mostra o evento.

---

## Fase 2  Triagem (humana  SecOps)

### 2.1 Receber o alerta

O alerta SNS contém:
```json
{
  "severity": "CRITICAL",
  "rule_id": "WAYFINDER-002",
  "resource_type": "AWS::S3::Bucket",
  "resource_id": "vitacore-prontuarios-prod",
  "account_id": "123456789012",
  "region": "us-east-1",
  "detected_at": "2026-08-21T14:32:00Z",
  "lgpd_article": "Art. 46",
  "description": "S3 Bucket com dados de saúde sem Block Public Access",
  "auto_remediation_applied": true,
  "auto_remediation_action": "EnableS3BlockPublicAccess",
  "investigation_query": "https://console.aws.amazon.com/athena/..."
}
```

### 2.2 Confirmar se auto-remediação foi aplicada

```bash
# Via AWS CLI
aws configservice describe-remediation-execution-statuses \
  --config-rule-name WAYFINDER-002 \
  --resource-keys resourceType=AWS::S3::Bucket,resourceId=vitacore-prontuarios-prod
```

### 2.3 Verificar se houve acesso indevido antes da remediação

```sql
-- Athena: acessos ao bucket nas últimas 2h antes do incidente
SELECT
  eventTime,
  userIdentity.arn as accessor,
  eventName,
  sourceIPAddress,
  requestParameters
FROM cloudtrail_logs
WHERE
  resources LIKE '%vitacore-prontuarios-prod%'
  AND eventTime BETWEEN '2026-08-21T12:00:00Z' AND '2026-08-21T14:32:00Z'
  AND eventName IN ('GetObject', 'ListBucket', 'PutObject')
ORDER BY eventTime DESC
```

---

## Fase 3  Contenção

### Se houve acesso não autorizado confirmado:

```bash
# 1. Revogar credenciais comprometidas
aws iam delete-access-key --user-name <user> --access-key-id <key-id>

# 2. Adicionar policy de negação explícita
aws iam put-user-policy \
  --user-name <user> \
  --policy-name EmergencyDeny \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Action":"*","Resource":"*"}]}'

# 3. Invalidar sessões ativas
aws iam update-login-profile --user-name <user> --password-reset-required

# 4. Notificar stakeholders
#  Acionar SNS manualmente via console ou CLI
```

### Se foi apenas desvio de configuração sem acesso:

- Confirmar que auto-remediação corrigiu o desvio
- Verificar se Config Rule voltou a COMPLIANT
- Documentar no relatório de incidente

---

## Fase 4  Investigação

### Consultas Athena padrão para investigação

**Quem modificou o recurso:**
```sql
SELECT
  eventTime,
  userIdentity.arn as who,
  eventName as what,
  requestParameters as details,
  sourceIPAddress as from_ip
FROM cloudtrail_logs
WHERE
  resources LIKE '%vitacore-prontuarios-prod%'
  AND eventName IN ('PutBucketPublicAccessBlock', 'DeleteBucketPublicAccessBlock',
                     'PutBucketPolicy', 'DeleteBucketPolicy')
ORDER BY eventTime DESC
LIMIT 50
```

**Histórico completo de acessos a dados sensíveis (30 dias):**
```sql
SELECT
  DATE_TRUNC('day', from_iso8601_timestamp(eventTime)) as day,
  userIdentity.arn as accessor,
  eventName,
  COUNT(*) as access_count
FROM cloudtrail_logs
WHERE
  resources LIKE '%vitacore%health%'
  AND eventName = 'GetObject'
  AND from_iso8601_timestamp(eventTime) >= CURRENT_TIMESTAMP - INTERVAL '30' DAY
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC
```

---

## Fase 5  Comunicação LGPD (se aplicável)

### Critérios para notificação à ANPD (art. 48 LGPD)

Notificação é obrigatória quando o incidente:
- Envolver dados pessoais sensíveis de saúde (art. 11)
- Puder acarretar risco ou dano relevante aos titulares
- O prazo é de 72h a partir da ciência do incidente

### Template de notificação interna (pré-ANPD)

```
INCIDENTE DE SEGURANÇA  VITACORE HEALTH
Data da ciência: [DATA]
Deadline ANPD: [DATA + 72h]

1. NATUREZA DO INCIDENTE
   [descrição técnica]

2. DADOS AFETADOS
   Type: [prontuários / laudos / dados wearable]
   Volume estimado: [número de registros]
   Titulares afetados: [número estimado]

3. MEDIDAS DE CONTENÇÃO APLICADAS
   [lista de ações tomadas]

4. AVALIAÇÃO DE RISCO AOS TITULARES
   [alto / médio / baixo  Justification]

5. PRÓXIMOS PASSOS
   [ações planejadas]
```

---

## Fase 6  Pós-incidente

1. Atualizar Config Rule ou Policy para prevenir recorrência
2. Gerar relatório pós-mortem em `docs/runbooks/incidents/`
3. Revisar se SENTINEL rule existente capturou a causa raiz
4. Criar nova SENTINEL rule se necessário
5. Atualizar este runbook com lições aprendidas

---

## Contatos de Escalonamento

| Nível | Responsável | Quando acionar |
|---|---|---|
| L1 | SecOps on-call | Qualquer incidente CRITICAL/HIGH |
| L2 | Cloud Architect | Incidente que requer mudança arquitetural |
| L3 | DPO / Jurídico | Quando notificação ANPD é necessária |
| L4 | Diretoria | Incidente com impacto a pacientes confirmado |
