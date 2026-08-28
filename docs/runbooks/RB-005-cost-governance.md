# RB-005  Governança de Cost AWS

**Runbook:** RB-005 | **Versão:** 1.0  
**Responsável primário:** Rafael Santos (CTO)  
**Colaboradores:** Bruno Oliveira (SecOps), Carla Mendes (Dev Lead)  
**Classificação:** Operacional  Interno  
**Última revisão:** 2026-08-21

---

## 1. Context e Motivação

O Cost AWS da VitaCore cresceu **23% ao mês** nos últimos 4 meses sem explicação
clara, passando de R$ 15k/mês para R$ 47k/mês. A ausência de tags de Cost
padronizadas impede identificar qual produto ou equipe é responsável.

Estimativa: **30% dos recursos são ociosos ou superdimensionados**, representando
~R$ 14k/mês em desperdício que este runbook visa identificar e eliminar.

**Meta:** Reduzir Cost AWS em 15% em 6 meses (de ~$1.050/mês para ~$890/mês USD).

---

## 2. Taxonomia de Tags Obrigatórias

Todos os recursos AWS da VitaCore DEVEM ter as 5 tags abaixo. A ausência de qualquer
uma delas é detectada pela Config Rule **WAYFINDER-015**.

| Tag | Valores Permitidos | Obrigatória | Example |
|---|---|---|---|
| `Environment` | `dev`, `staging`, `prod` |  Sim | `prod` |
| `Project` | `vitacore-pep`, `vitacore-patient-app`, `vitacore-telehealth`, `vitacore-wearables`, `wayfinder-cloud`, `shared` |  Sim | `vitacore-pep` |
| `Owner` | Email do time ou squad |  Sim | `backend-squad@vitacore.health` |
| `CostCenter` | `eng-backend`, `eng-frontend`, `eng-data`, `eng-security`, `product` |  Sim | `eng-backend` |
| `DataClassification` | `health-critical`, `health-standard`, `financial-sensitive`, `operational`, `public` |  Sim | `health-critical` |

**Tags adicionais recomendadas:**

| Tag | Propósito | Example |
|---|---|---|
| `retention-required` | Ativa WAYFINDER-013 | `true` |
| `retention-days` | Define período de Object Lock | `7305` |
| `remediation-exempt` | Isenta recurso de remediação automática (com aprovação) | `true` (requer ticket) |
| `created-by` | Identifica quem criou o recurso | `carla.mendes@vitacore.health` |
| `terraform-managed` | Confirma que o recurso é gerenciado por IaC | `true` |

---

## 3. Config Rule WAYFINDER-015  Recursos sem Tags Obrigatórias

```
ID:            WAYFINDER-015
Type:          CUSTOM_LAMBDA
Trigger:       Periódico (a cada 6h) + ConfigurationItemChangeNotification
Avaliação:     Todos os recursos suportados DEVEM ter as 5 tags obrigatórias.
               Recursos no namespace arn:aws:iam::*/root são isentos.
               Recursos criados há menos de 24h recebem grace period.
Não-conforme:  Severidade MEDIUM (< 7 dias sem tags)  HIGH (> 7 dias)
Remediação:    Notificação para Owner identificado via CloudTrail (quem criou?)
               + ticket Jira automático com lista de tags ausentes
LGPD:          Não aplicável diretamente  governança de Cost e rastreabilidade
ISO 27001:     A.8.1  Inventário de ativos
```

---

## 4. Processo de Análise de Cost Semanal

### 4.1 Cadência

| Evento | Quando | Responsável | Output |
|---|---|---|---|
| Coleta automática de dados | Toda segunda-feira 09h UTC | Lambda audit-reporter | Relatório JSON no S3 |
| Revisão de Cost semanal | Toda terça-feira 14h | CTO + Dev Lead | Decisões de rightsizing |
| Análise de tendência mensal | Primeiro dia útil do mês | CTO + DPO (Cost compliance) | Relatório para Board |

### 4.2 Passos da Revisão Semanal

```
Step 1  Abrir Cost Explorer
   Console AWS  Cost Management  Cost Explorer
   Período: últimos 7 dias comparado com 7 dias anteriores
   Agrupamento: por Tag (Project) + por Serviço

Step 2  Identificar variações > 10%
   Serviço com crescimento > 10% sem mudança de usage esperada = investigar
   Executar Athena Query 6.1 para identificar recursos sem tag

Step 3  Verificar instâncias ociosas
   CloudWatch: CPU < 5% por mais de 7 dias = candidato a rightsizing
   Executar Athena Query 6.2 para EC2/RDS subutilizados

Step 4  Revisar alarmes de Budget
   Budget #1: Cost total  se > 80%  análise imediata
   Budget #2: EC2+RDS  se > 70%  revisar rightsizing

Step 5  Documentar ações
   Criar ticket Jira Type "Cost Optimization" para cada ação identificada
   Registrar economia estimada vs Cost atual
   Atribuir ao Owner da tag do recurso
```

---

## 5. Queries Athena para Análise de Cost

**Nota:** Queries de Cost usam o Cost and Usage Report (CUR) exportado para S3.
Configurar export em Billing  Cost & Usage Reports  S3 bucket `vitacore-cur-data`.

### 6.1 Recursos sem Tags Obrigatórias

```sql
-- Query 6.1: Recursos sem as 5 tags obrigatórias via Config snapshots
SELECT
  resourcetype,
  resourceid,
  accountid,
  awsregion,
  configurationitemcapturetime,
  JSON_EXTRACT(tags, '$.Environment') as env_tag,
  JSON_EXTRACT(tags, '$.Project') as project_tag,
  JSON_EXTRACT(tags, '$.Owner') as owner_tag,
  JSON_EXTRACT(tags, '$.CostCenter') as cost_center_tag,
  JSON_EXTRACT(tags, '$.DataClassification') as data_class_tag
FROM aws_config_configuration_items
WHERE (
  JSON_EXTRACT(tags, '$.Environment') IS NULL OR
  JSON_EXTRACT(tags, '$.Project') IS NULL OR
  JSON_EXTRACT(tags, '$.Owner') IS NULL OR
  JSON_EXTRACT(tags, '$.CostCenter') IS NULL OR
  JSON_EXTRACT(tags, '$.DataClassification') IS NULL
)
AND configurationitemstatus != 'ResourceDeleted'
AND resourcetype NOT IN ('AWS::IAM::ManagedPolicy', 'AWS::CloudFormation::Stack')
ORDER BY configurationitemcapturetime DESC;
```

### 6.2 EC2 e RDS Subutilizados (via CloudWatch metrics)

```sql
-- Query 6.2: Instâncias com baixo CPU (candidatos a rightsizing)
-- Requer que métricas CloudWatch estejam exportadas para S3 via Metric Streams
SELECT
  dimensions.value as instance_id,
  AVG(value) as avg_cpu_7d,
  MAX(value) as max_cpu_7d,
  MIN(value) as min_cpu_7d
FROM cloudwatch_metrics
WHERE metric_name = 'CPUUtilization'
  AND namespace IN ('AWS/EC2', 'AWS/RDS')
  AND timestamp >= current_date - interval '7' day
GROUP BY dimensions.value
HAVING AVG(value) < 10  -- média < 10% CPU em 7 dias
ORDER BY avg_cpu_7d ASC;
```

### 6.3 Cost por Project (via CUR)

```sql
-- Query 6.3: Cost semanal por Project tag e serviço
SELECT
  resource_tags_user_project as project,
  line_item_product_code as aws_service,
  SUM(line_item_unblended_cost) as total_cost_usd,
  SUM(line_item_usage_amount) as total_usage
FROM cost_and_usage_report
WHERE line_item_usage_start_date >= current_date - interval '7' day
  AND resource_tags_user_project IS NOT NULL
GROUP BY resource_tags_user_project, line_item_product_code
ORDER BY total_cost_usd DESC
LIMIT 50;
```

### 6.4 NAT Gateway  Maior Cost de Network

```sql
-- Query 6.4: Detalhamento de Cost NAT Gateway (frequentemente o maior item)
SELECT
  DATE_FORMAT(line_item_usage_start_date, '%Y-%m-%d') as date,
  line_item_resource_id as nat_gateway_id,
  line_item_usage_type,
  line_item_usage_amount as gb_processed,
  line_item_unblended_cost as cost_usd
FROM cost_and_usage_report
WHERE line_item_product_code = 'AmazonVPC'
  AND line_item_usage_type LIKE '%NatGateway%'
  AND line_item_usage_start_date >= current_date - interval '7' day
ORDER BY cost_usd DESC;
```

### 6.5 S3 por Bucket  Identificar Buckets com Alto Cost

```sql
-- Query 6.5: Cost S3 por bucket (storage + requests + transfer)
SELECT
  line_item_resource_id as bucket_arn,
  SUM(CASE WHEN line_item_usage_type LIKE '%Storage%' THEN line_item_unblended_cost ELSE 0 END) as storage_cost,
  SUM(CASE WHEN line_item_usage_type LIKE '%Requests%' THEN line_item_unblended_cost ELSE 0 END) as requests_cost,
  SUM(CASE WHEN line_item_usage_type LIKE '%DataTransfer%' THEN line_item_unblended_cost ELSE 0 END) as transfer_cost,
  SUM(line_item_unblended_cost) as total_cost
FROM cost_and_usage_report
WHERE line_item_product_code = 'AmazonS3'
  AND line_item_usage_start_date >= current_date - interval '30' day
GROUP BY line_item_resource_id
ORDER BY total_cost DESC;
```

---

## 6. Alertas de Orçamento  AWS Budgets

### 6.1 Configuração dos Budgets

```hcl
# Budget #1  Cost total mensal
Budget: vitacore-monthly-total
Limite: $1.050/mês (prod) / $150/mês (dev)
Alertas:
  - 80% do limite  SNS WARNING  email CTO + Slack #eng-alerts
    Mensagem: "Cost AWS atingiu 80% do budget. Ação preventiva necessária."
  - 100% do limite  SNS CRITICAL  email CTO + PagerDuty
    Mensagem: "Budget AWS EXCEDIDO. Investigar imediatamente."
  - 120% (forecast)  SNS WARNING (projeção de estouro)

# Budget #2  EC2 + RDS (detecção de instâncias não gerenciadas)
Budget: vitacore-compute-database
Limite: $550/mês (EC2 + RDS + ElastiCache)
Alertas:
  - 70%  SNS WARNING  email CTO
    "Cost de compute/database em 70% do budget. Revisar rightsizing."
```

### 6.2 Fluxo de Resposta a Alertas de Budget

```
ALERT: Budget WARNING (80%)
    
     CTO revisa Cost Explorer (ver seção 4.2)
     Identifica 3 maiores centros de Cost da semana
     Verifica se há instâncias ociosas (Athena Query 6.2)
     Cria tickets de rightsizing se aplicável

ALERT: Budget CRITICAL (100%)
    
     CTO + Dev Lead reunião imediata (< 2h)
     Identificar o que mudou nos últimos 7 dias
     Verificar se há instâncias não-tagueadas (Athena Query 6.1)
     Verificar NAT Gateway (Athena Query 6.4  frequente culpado)
     Ações emergenciais:
       - Stop instâncias dev fora do horário (19h-09h + weekends)
       - Downsize RDS dev de r-series para t-series
       - Revisar Lambda com high invocation count
     Relatório para CEO com causa raiz e ação corretiva
```

---

## 7. Rightsizing Workflow

### 7.1 Processo de Identificação

```
1. Coleta de dados (automático, semanal):
    Lambda audit-reporter gera relatório de utilização
    Critérios de candidatos a rightsizing:
      EC2/ECS: CPU médio 7d < 10% + Memory 7d < 20%
      RDS:     CPU médio 7d < 5% + connections < 10% do max
      ElastiCache: hit ratio < 50% (possível underutilization)

2. Análise de impacto (manual, Dev Lead):
    Verificar se baixo uso é padrão esperado (ex: batch noturno)
    Verificar picos: P99 CPU nos últimos 30 dias
    Consultar Owner da tag do recurso

3. Proposta de rightsizing:
    Documentar: recurso atual  recurso proposto  economia estimada
    Criar PR no repositório IaC com mudança de instance type
    Dev Lead + CTO aprovam antes de aplicar em prod

4. Aplicação e Monitoring:
    Apply em dev primeiro (1 semana de observação)
    Apply em prod com janela de manutenção agendada
    CloudWatch Alarm: se P99 CPU > 80% após rightsizing  rollback automático
```

### 7.2 Tabela de Rightsizing Comum

| Type | Instância Atual | Proposta (menor carga) | Economia Estimada |
|---|---|---|---|
| EC2 app | c5.xlarge (4vCPU/8GB) | c5.large (2vCPU/4GB) | ~$60/mês |
| RDS dev | db.r6g.large (2vCPU/16GB) | db.t4g.medium (2vCPU/4GB) | ~$75/mês |
| ElastiCache dev | cache.r6g.large | cache.t4g.micro | ~$120/mês |
| Lambda | 1024MB (over-provisioned) | 512MB | ~$30/mês |

---

## 8. Lifecycle Policies por Type de Dado

S3 lifecycle policies automatizam a movimentação de dados para camadas de storage
mais baratas, reduzindo Cost sem afetar disponibilidade para dados ativos.

| Type de Dado | Tag | Classificação | Hot (S3 Standard) | Warm (S3 IA) | Cold (Glacier IR) | Expiração |
|---|---|---|---|---|---|---|
| Prontuários ativos | health-critical | Paciente ativo | Indefinido | Após inatividade 1 ano | Nunca (Object Lock 20 anos) | Não |
| Laudos de imagem | health-critical | Após exame | 90 dias | 90-365 dias | 365d-5 anos | Object Lock 5 anos |
| Gravações telemedicina | health-critical | Após sessão | 30 dias | 30-365 dias | 365d-5 anos | Object Lock 5 anos |
| Dados wearables brutos | health-standard | Após processamento | 30 dias | 30-90 dias | 90d-3 anos | Expirar após 3 anos |
| Dados wearables agregados | health-standard | Após agregação | 90 dias | 90-365 dias | 365d-3 anos | Expirar após 3 anos |
| Logs de aplicação | operational | Após geração | 30 dias |  |  | Expirar após 90 dias |
| Audit trail (CloudTrail) | operational | Após evento | 90 dias | 90-365 dias | 365d-5 anos | Object Lock 5 anos |
| Relatórios financeiros | financial-sensitive | Após geração | 1 ano | 1-5 anos | 5-10 anos | Expirar após 10 anos |

**Configuração Terraform:**
```hcl
lifecycle_rule {
  id     = "laudos-imagem-lifecycle"
  status = "Enabled"
  filter { tag { key = "data-classification"; value = "health-critical" } }
  transition { days = 90;  storage_class = "STANDARD_IA" }
  transition { days = 365; storage_class = "GLACIER_IR" }
  # Sem expiration  Object Lock COMPLIANCE garante retenção
}
```

**Economia estimada com lifecycle policies:**
- 500GB health-critical movendo para Glacier IR após 365 dias: -$8/mês
- 200GB wearables brutos expirando após 3 anos: -$4/mês (steady state)
- 50GB logs de aplicação expirando após 90 dias: -$1/mês
- **Total estimado: ~$13/mês** de redução com lifecycle policies
