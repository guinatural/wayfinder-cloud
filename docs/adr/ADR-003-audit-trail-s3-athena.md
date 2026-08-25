# ADR-003  Trilha de Auditoria com S3 + Object Lock + Athena

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

A LGPD (art. 37) exige que o controlador de dados mantenha registro das operações
de tratamento de dados pessoais. Para dados de saúde (art. 11), esse requisito
é ainda mais crítico. A trilha de auditoria precisa ser:

1. **Imutável**  ninguém pode deletar ou modificar logs após geração
2. **Consultável**  equipe de segurança precisa investigar incidentes com SQL
3. **Centralizada**  todos os logs (API calls, data access, Config changes) em um lugar
4. **Econômica**  logs históricos de anos não devem custar uma fortuna

As opções avaliadas para armazenamento:

1. S3 + Object Lock + Athena
2. CloudWatch Logs Insights
3. OpenSearch (Elasticsearch)
4. RDS para logs estruturados

---

## Decisão

**S3 com Object Lock (COMPLIANCE mode) + AWS Glue Data Catalog + Amazon Athena**
para armazenamento e consulta da trilha de auditoria.

---

## Justificativa

**Imutabilidade:**
- S3 Object Lock em modo COMPLIANCE impede que qualquer usuário, incluindo root,
  delete ou modifique objetos durante o período de retenção
- Isso garante a cadeia de custódia dos logs exigida para fins jurídicos
- CloudWatch Logs não oferece Object Lock  logs podem ser deletados

**Custo:**
- S3 Standard: ~$0.023/GB/mês  S3 Glacier: ~$0.004/GB/mês (lifecycle após 90 dias)
- CloudWatch Logs: ~$0.50/GB ingerido + $0.03/GB armazenado  muito mais caro para volumes altos
- OpenSearch: requer instâncias dedicadas, custo fixo independente do volume

**Consultabilidade:**
- Athena permite SQL diretamente sobre arquivos Parquet/JSON no S3
- Sem servidor para gerenciar, sem custo de idle
- CloudWatch Logs Insights tem sintaxe proprietária e limitações de escala

**Escalabilidade:**
- S3 escala infinitamente sem configuração
- Athena escala automaticamente para queries em PB de dados

---

## Estrutura de Particionamento no S3

```
s3://vitacore-audit-trail-{account-id}/
 cloudtrail/
    AWSLogs/{account-id}/CloudTrail/{region}/
        {year}/{month}/{day}/
            {account-id}_CloudTrail_{region}_{timestamp}.json.gz
 config/
    {year}/{month}/{day}/
        config-snapshot-{timestamp}.json.gz
 compliance-events/
     {year}/{month}/{day}/
         wayfinder-events-{timestamp}.json
```

Particionamento por `year/month/day` reduz custo de scan do Athena
porque queries filtradas por data não leem partições irrelevantes.

---

## Política de Retenção

| Tipo de Log | Retenção S3 Standard | Retenção S3 Glacier | Object Lock |
|---|---|---|---|
| CloudTrail management events | 90 dias | 5 anos | 5 anos |
| CloudTrail data events (S3) | 30 dias | 2 anos | 2 anos |
| Config snapshots | 90 dias | 1 ano | 1 ano |
| Compliance events (Sentinel) | 90 dias | 5 anos | 5 anos |

Retenção de 5 anos para CloudTrail alinha com prazo prescricional do Código Civil
(art. 205) e com práticas de compliance de saúde.

---

## Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| Athena não é real-time | Baixo  auditoria é histórica, não real-time | Alertas em tempo real ficam no CloudWatch/SNS |
| Object Lock impede correção de logs com erro | Baixo  logs são append-only, não são editados | Processo de geração de logs deve ser testado antes de habilitar lock |
| Glue Crawler tem custo por DPU-hora | Baixo | Crawler agendado 1x/dia, não contínuo |

---

## Consequências

- S3 bucket de audit trail DEVE ser criado com Object Lock habilitado (não pode ser habilitado depois)
- Versioning DEVE estar habilitado (requisito do Object Lock)
- Lifecycle rules DEVEM mover objetos para Glacier após 90 dias
- Athena workgroup DEVE ter resultado de queries salvo em S3 separado com custo controlado
- CloudTrail DEVE ter S3 data events habilitados para buckets com dados de saúde
- KMS CMK DEVE ser usado para criptografar todos os logs
