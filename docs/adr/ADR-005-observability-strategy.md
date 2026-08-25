# ADR-005  Estratégia de Observabilidade: CloudWatch Nativo + X-Ray

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

O Wayfinder Cloud precisa de observabilidade em múltiplas camadas:

1. **Infraestrutura**  métricas de CPU, memória, throttling das Lambdas
2. **Compliance**  número de recursos NON_COMPLIANT por severidade, taxa de remediação
3. **Aplicação**  erros nas Lambdas, latência, rastreamento de chamadas distribuídas
4. **Auditoria**  logs estruturados de todas as ações tomadas pelo sistema

O projeto opera 100% na AWS sem agentes externos, com orçamento de observabilidade a minimizar.
A equipe é pequena (~2 engenheiros) e não pode operar uma plataforma de observabilidade adicional.

---

## Opções Avaliadas

### Opção 1: DataDog
- **Prós:** Dashboard excelente, correlação de logs/métricas/traces, APM avançado
- **Contras:** Custo ~$20-40/host/mês, requer agente instalado, dados saem da AWS, contrato longo prazo
- **Custo estimado:** ~$500-2.000/mês para o projeto

### Opção 2: New Relic
- **Prós:** Free tier generoso (100GB/mês), UI moderna, APM distribuído
- **Contras:** Dados de auditoria sairiam da AWS (problema regulatório LGPD), latência adicional de ingestion
- **Custo estimado:** $0 no free tier, mas com risco de lockout

### Opção 3: Grafana + Prometheus (auto-hospedado)
- **Prós:** Open source, extremamente flexível, sem custo de licença
- **Contras:** Requer EC2/ECS para hospedar (custo infra), operação manual de upgrades,
  sem integração nativa com Config/CloudTrail

### Opção 4: CloudWatch Nativo + X-Ray  **Escolhido**
- **Prós:** Zero agente, integração nativa com todos os serviços AWS usados, dashboards como código (Terraform),
  sem egress de dados fora da AWS, custo previsível
- **Contras:** UI do CloudWatch menos polida que DataDog, métricas customizadas têm custo por PutMetricData

---

## Decisão

**CloudWatch Logs + Metrics + Alarms + Dashboards + X-Ray** foi escolhido como stack de observabilidade.

---

## Justificativa

### Custo
CloudWatch tem custo por uso. Para o volume do Wayfinder Cloud (baixo número de eventos de compliance):
- Log Groups: ~$0.50/GB ingerido
- Métricas customizadas: ~$0.30/métrica/mês
- Dashboards: $3/dashboard/mês
- X-Ray: $5/milhão de traces

Custo estimado total: **< $50/mês** vs $500-2.000/mês de ferramentas externas.

### Integração Nativa
CloudTrail, Config, Lambda e EventBridge já publicam métricas e logs no CloudWatch sem
nenhuma configuração adicional. X-Ray se integra diretamente com Lambda via `tracing_config { mode = "Active" }`.

### Sem Agente Externo
Lambdas são efêmeras  instalar agentes DataDog/New Relic aumenta cold start e complexidade
de deployment. CloudWatch SDK é embutido no runtime Python.

### Dados Dentro da AWS (LGPD)
Logs de compliance contêm metadados de recursos com dados de saúde. Manter tudo no CloudWatch
garante que esses dados nunca saem da infraestrutura AWS controlada pela VitaCore Health.

### Dashboards como Código
`aws_cloudwatch_dashboard` no Terraform permite versionar e revisar mudanças no dashboard
via pull request, como qualquer outra mudança de infraestrutura.

---

## Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| UI menos rica que DataDog | Baixo  dashboards cumprem o necessário | CloudWatch tem melhorado continuamente |
| Custo por PutMetricData | Baixo  ~100 eventos/dia | Agrupamento de métricas em batch |
| Correlação logs-traces manual | Médio | X-Ray Service Map cobre a maioria dos casos |
| Sem anomaly detection automática | Médio | CloudWatch Anomaly Detection disponível como evolução futura |

---

## Estrutura de Namespaces

```
wayfinder/Compliance
  - NonCompliantResource [RuleName, Severity, Environment]
  - ComplianceScore [Environment]

wayfinder/Remediation
  - RemediationAttempt [RuleName, Status, Severity, Environment]

AWS/Lambda (automático)
  - Errors, Invocations, Duration, Throttles [FunctionName]
```

## Estrutura de Log Groups

```
/wayfinder/cloudtrail            Logs do CloudTrail (retenção: 365 dias)
/wayfinder/lambda/compliance-evaluator  (retenção: 90 dias)
/wayfinder/lambda/auto-remediation      (retenção: 90 dias)
/wayfinder/lambda/incident-notifier     (retenção: 90 dias)
/wayfinder/lambda/audit-reporter        (retenção: 90 dias)
```

---

## Consequências

- Todos os logs das Lambdas DEVEM usar formato JSON estruturado para facilitar queries no Logs Insights
- Alarmes DEVEM ser criados via Terraform (não manualmente no console)
- Métricas customizadas DEVEM usar os namespaces definidos acima para consistência
- X-Ray DEVE estar ativo em todas as Lambdas (`tracing_config { mode = "Active" }`)
- Evoluções futuras (dashboards de negócio, SLOs) podem adicionar Grafana Cloud como camada de visualização

---

## Evolução Futura

- **CloudWatch Contributor Insights** para identificar top contributors de violações
- **CloudWatch Synthetics** para monitorar endpoints de relatórios
- **AWS Health Dashboard** para correlacionar eventos de serviço com picos de violações
- **Grafana Cloud** (free tier) como frontend visual adicional conectando ao CloudWatch via datasource
