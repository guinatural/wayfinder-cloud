# Runbook RB-003  Queries Athena de Compliance

**Projeto:** Wayfinder Cloud  
**Versão:** 1.0  
**Classificação:** OPERACIONAL

---

## Pré-requisitos

- Acesso ao Athena Workgroup `wayfinder-audit`
- Permissão `athena:StartQueryExecution` e `s3:GetObject` no bucket de auditoria
- Database Glue: `wayfinder_audit`
- Tabela principal: `cloudtrail_logs` (catalogada pelo Glue Crawler)

### Acessar o Athena Console

```
AWS Console  Athena  Workgroups  wayfinder-audit  Query Editor
```

Selecionar database: `wayfinder_audit`

---

## Query 1: Top Violações dos Últimos 7 Dias

Identifica as Config Rules que mais dispararam NON_COMPLIANT nos últimos 7 dias,
agrupadas por severidade.

```sql
SELECT
  json_extract_scalar(message, '$.rule_name')  AS rule_name,
  json_extract_scalar(message, '$.severity')   AS severity,
  json_extract_scalar(message, '$.lgpd_article') AS lgpd_article,
  COUNT(*)                                     AS violation_count,
  MAX(eventtime)                               AS last_seen
FROM cloudtrail_logs
WHERE
  eventsource = 'config.amazonaws.com'
  AND eventname = 'PutEvaluations'
  AND from_iso8601_timestamp(eventtime) >= CURRENT_TIMESTAMP - INTERVAL '7' DAY
GROUP BY 1, 2, 3
ORDER BY
  CASE severity
    WHEN 'CRITICAL' THEN 1
    WHEN 'HIGH'     THEN 2
    WHEN 'MEDIUM'   THEN 3
    ELSE 4
  END,
  violation_count DESC
LIMIT 20
```

---

## Query 2: Histórico de Acessos a Dados Sensíveis por Usuário

Rastreia quem acessou buckets S3 com dados de saúde nas últimas N horas.
Essencial para investigação de incidentes (LGPD Art. 37 e Art. 48).

```sql
-- Substituir <BUCKET_NAME> pelo bucket específico ou usar LIKE '%health%'
-- Substituir <HOURS> pelo número de horas desejado (ex: 24, 48, 168)

SELECT
  DATE_TRUNC('hour', from_iso8601_timestamp(eventtime)) AS hour_bucket,
  useridentity.arn                                       AS accessor_arn,
  useridentity.type                                      AS identity_type,
  eventname                                              AS action,
  sourceipaddress                                        AS source_ip,
  requestparameters                                      AS request_details,
  COUNT(*)                                               AS access_count
FROM cloudtrail_logs
WHERE
  eventsource = 's3.amazonaws.com'
  AND eventname IN ('GetObject', 'PutObject', 'DeleteObject', 'ListBucket', 'CopyObject')
  AND resources LIKE '%<BUCKET_NAME>%'
  AND from_iso8601_timestamp(eventtime) >= CURRENT_TIMESTAMP - INTERVAL '<HOURS>' HOUR
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1 DESC, 7 DESC
```

---

## Query 3: Recursos Sem Criptografia (Snapshot Atual)

Lista recursos que estão sem criptografia habilitada, baseado nos eventos Config
mais recentes. Útil para relatórios de conformidade LGPD Art. 46.

```sql
WITH latest_evaluations AS (
  SELECT
    json_extract_scalar(message, '$.resource_type') AS resource_type,
    json_extract_scalar(message, '$.resource_id')   AS resource_id,
    json_extract_scalar(message, '$.rule_name')     AS rule_name,
    MAX(from_iso8601_timestamp(eventtime))           AS last_evaluation
  FROM cloudtrail_logs
  WHERE
    eventsource = 'config.amazonaws.com'
    AND json_extract_scalar(message, '$.rule_name') IN (
      'WAYFINDER-001',
      'encrypted-volumes',
      'rds-storage-encrypted',
      'wayfinder-dev-encrypted-volumes',
      'wayfinder-dev-rds-storage-encrypted'
    )
  GROUP BY 1, 2, 3
)
SELECT
  resource_type,
  resource_id,
  rule_name,
  last_evaluation,
  DATEDIFF('day', last_evaluation, CURRENT_TIMESTAMP) AS days_non_compliant
FROM latest_evaluations
ORDER BY days_non_compliant DESC, resource_type, resource_id
```

---

## Query 4: Mudanças de IAM nos Últimos 30 Dias

Auditoria completa de mudanças em IAM  criação/deleção de usuários, roles, policies
e access keys. Mapeado ao LGPD Art. 47 (segurança no tratamento).

```sql
SELECT
  eventtime,
  useridentity.arn            AS who_made_change,
  useridentity.type           AS identity_type,
  eventname                   AS change_type,
  requestparameters           AS change_details,
  sourceipaddress             AS from_ip,
  useragent                   AS tool_used,
  errorcode,
  errormessage
FROM cloudtrail_logs
WHERE
  eventsource = 'iam.amazonaws.com'
  AND eventname IN (
    'CreateUser', 'DeleteUser', 'UpdateUser',
    'CreateRole', 'DeleteRole', 'UpdateRole',
    'AttachUserPolicy', 'DetachUserPolicy',
    'AttachRolePolicy', 'DetachRolePolicy',
    'PutUserPolicy', 'DeleteUserPolicy',
    'CreateAccessKey', 'DeleteAccessKey', 'UpdateAccessKey',
    'CreateLoginProfile', 'DeleteLoginProfile',
    'AddUserToGroup', 'RemoveUserFromGroup',
    'CreateGroup', 'DeleteGroup'
  )
  AND from_iso8601_timestamp(eventtime) >= CURRENT_TIMESTAMP - INTERVAL '30' DAY
ORDER BY eventtime DESC
LIMIT 500
```

---

## Query 5: Root Account Usage

Detecta qualquer uso da conta root  violação grave de controles de segurança
(CIS AWS 1.1, mapeado ao LGPD Art. 46).

```sql
SELECT
  eventtime,
  eventname,
  eventsource,
  sourceipaddress,
  useragent,
  useridentity.invokedby  AS invoked_by,
  errorcode,
  CASE
    WHEN errorcode IS NULL THEN ' SUCCEEDED'
    ELSE ' FAILED'
  END AS outcome,
  requestparameters
FROM cloudtrail_logs
WHERE
  useridentity.type = 'Root'
  AND useridentity.invokedby IS NULL  -- Exclui serviços AWS que usam root internamente
  AND from_iso8601_timestamp(eventtime) >= CURRENT_TIMESTAMP - INTERVAL '90' DAY
ORDER BY eventtime DESC
```

>  **Qualquer resultado nesta query deve ser investigado imediatamente.**
> Root account não deve ser usado para operações rotineiras.

---

## Query 6: Recursos Criados Sem Tags Obrigatórias

Identifica recursos que foram criados sem as tags mandatórias de governança.
Afeta rastreabilidade de custo e compliance.

Tags obrigatórias por política: `Environment`, `Project`, `Owner`, `ManagedBy`

```sql
WITH resource_events AS (
  SELECT
    eventtime,
    eventsource,
    eventname,
    useridentity.arn AS creator,
    requestparameters,
    responselements,
    -- Extrai tags do campo requestParameters (formato varia por serviço)
    json_extract(requestparameters, '$.tagSpecificationSet') AS tags_s3,
    json_extract(requestparameters, '$.Tags')               AS tags_direct
  FROM cloudtrail_logs
  WHERE
    eventname IN (
      'CreateBucket', 'RunInstances', 'CreateFunction20150331',
      'CreateDBInstance', 'CreateTable', 'CreateKey'
    )
    AND errorcode IS NULL  -- Apenas criações bem-sucedidas
    AND from_iso8601_timestamp(eventtime) >= CURRENT_TIMESTAMP - INTERVAL '30' DAY
)
SELECT
  eventtime,
  eventsource,
  eventname,
  creator,
  COALESCE(tags_s3, tags_direct, 'SEM TAGS') AS tags_applied,
  CASE
    WHEN COALESCE(tags_s3, tags_direct) IS NULL THEN ' SEM TAGS'
    WHEN tags_s3 NOT LIKE '%Environment%'
      OR tags_s3 NOT LIKE '%Project%' THEN ' TAGS INCOMPLETAS'
    ELSE ' OK'
  END AS tag_compliance
FROM resource_events
WHERE
  COALESCE(tags_s3, tags_direct) IS NULL
  OR tags_s3 NOT LIKE '%Environment%'
ORDER BY eventtime DESC
LIMIT 100
```

---

## Dicas de Performance

1. **Sempre use filtros de data**  a tabela `cloudtrail_logs` é particionada por data
2. **Prefira `LIMIT`** em queries exploratórias para evitar custo excessivo
3. **Use o Workgroup `wayfinder-audit`**  tem limite de scan configurado para proteção
4. **Salve queries frequentes**  Athena permite salvar named queries no workgroup
5. **Use CTAS para relatórios grandes:**

```sql
-- Criar tabela temporária para análise pesada
CREATE TABLE wayfinder_audit.weekly_violations
WITH (
  format = 'PARQUET',
  external_location = 's3://wayfinder-dev-audit-trail-ACCOUNT/athena-temp/',
  partitioned_by = ARRAY['year', 'month']
) AS
SELECT ... FROM cloudtrail_logs
WHERE ...
```
