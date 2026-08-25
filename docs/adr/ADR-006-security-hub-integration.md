# ADR-006  Integração com AWS Security Hub

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

O Wayfinder Cloud implementa controles de segurança focados em compliance LGPD, mas a VitaCore Health
precisa também demonstrar conformidade com frameworks internacionais reconhecidos para:

1. Auditorias externas de segurança e acreditação (SBIS, CFM)
2. Due diligence em parcerias com planos de saúde e hospitais
3. Mapeamento da postura de segurança em uma visão consolidada
4. Correlação entre Config Rules customizadas (WAYFINDER-001..014) e controles NIST/CIS

Sem uma visão consolidada, a equipe teria que cruzar manualmente resultados do AWS Config,
GuardDuty, Inspector e Macie  trabalho operacional sem escalabilidade.

---

## Decisão

**Habilitar AWS Security Hub** com os seguintes standards:

1. **AWS Foundational Security Best Practices (FSBP)**  padrão AWS-nativo, cobre ~280 controles
2. **CIS AWS Foundations Benchmark v1.4**  padrão amplamente reconhecido em auditorias

---

## Justificativa

### FSBP  AWS Foundational Security Best Practices
- Desenvolvido pela AWS com base em incidentes reais e melhores práticas operacionais
- Cobre todos os serviços usados pelo Wayfinder Cloud (S3, IAM, CloudTrail, Config, Lambda, KMS)
- Findings são gerados automaticamente e aparecem no EventBridge  integráveis com o pipeline existente
- Custo: $0.001 por verificação de controle/recurso/mês

### CIS AWS Foundations Benchmark v1.4
- Reconhecido internacionalmente por auditores de segurança (ISO 27001, SOC 2)
- Cobre especificamente: IAM, logging, monitoramento e rede
- Alinha com os controles de auditoria do Wayfinder Cloud (CloudTrail, Config, MFA)
- Ajuda a demonstrar "boas práticas e governança" exigidas pelo art. 50 da LGPD

### Integração com o Pipeline Existente
Security Hub publica findings no EventBridge com `source: aws.securityhub`.
A EventBridge Rule existente pode ser estendida para rotear findings CRITICAL do Security Hub
para o mesmo pipeline compliance-evaluator  SNS  SecOps.

---

## Mapeamento para LGPD Art. 50

O art. 50 da LGPD exige que controladores e operadores adotem "boas práticas e governança",
incluindo "políticas e salvaguardas baseadas em padrões técnicos que apliquem medidas de
segurança adequadas".

| Controle CIS/FSBP | Artigo LGPD | Implementação Sentinel |
|---|---|---|
| CIS 2.1  CloudTrail habilitado | Art. 37 (registro) | WAYFINDER-003 + managed rule CLOUD_TRAIL_ENABLED |
| CIS 3.x  S3 Block Public Access | Art. 46 (segurança) | WAYFINDER-002 + S3_BUCKET_PUBLIC_READ_PROHIBITED |
| CIS 1.5  MFA para root | Art. 46 (acesso) | MFA_ENABLED_FOR_IAM_CONSOLE_ACCESS |
| FSBP KMS.1  rotação de chaves | Art. 46 (criptografia) | KMS CMK com `enable_key_rotation = true` |
| FSBP Lambda.1  sem políticas de acesso público | Art. 46 | IAM least privilege nas Lambda roles |
| FSBP Config.1  Config habilitado | Art. 37 (rastreabilidade) | Config Recorder em todos os ambientes |

---

## Arquitetura de Integração

```
Security Hub Finding (CRITICAL)
    
EventBridge (source: aws.securityhub)
    
Rule: security-hub-critical-findings
    
Lambda: compliance-evaluator
    
SNS CRITICAL  SecOps email + Slack
```

A integração será implementada adicionando uma nova EventBridge Rule no módulo `observability`:

```hcl
resource "aws_cloudwatch_event_rule" "security_hub_critical" {
  name           = "${local.name_prefix}-securityhub-critical"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["aws.securityhub"]
    "detail-type" = ["Security Hub Findings - Imported"]
    detail = {
      findings = {
        Severity = { Label = ["CRITICAL", "HIGH"] }
      }
    }
  })
}
```

---

## Trade-offs

| Trade-off | Impacto | Mitigação |
|---|---|---|
| Custo adicional Security Hub | Baixo (~$10-30/mês para a conta) | ROI positivo: reduz horas de auditoria manual |
| Overlap com Config Rules customizadas | Médio  pode gerar alertas duplicados | Filtrar findings Security Hub por fonte antes de rotear |
| False positives iniciais | Alto no início | Período de 30 dias de calibração antes de habilitar alertas |
| Necessidade de habilitar GuardDuty | Baixo | GuardDuty já previsto na managed rule GUARDDUTY_ENABLED_CENTRALIZED |

---

## Decisão de Não Habilitar Agora (Implementação Futura)

A habilitação do Security Hub requer:
1. Habilitar GuardDuty e Inspector na conta (dependências do FSBP)
2. Período de 30 dias de calibração para reduzir false positives
3. Ajuste da EventBridge Rule para não duplicar alertas com Config Rules

Por esses motivos, a integração está documentada neste ADR mas será implementada
em sprint dedicado após o MVP do Wayfinder Cloud estar em produção.

---

## Consequências

- O módulo `observability` DEVE ser estendido com uma EventBridge Rule para Security Hub findings
- Os findings do Security Hub DEVEM ser correlacionados com as regras WAYFINDER-001..014 para evitar duplicatas
- O relatório semanal do `audit-reporter` DEVE incluir uma seção de Security Hub score
- Este ADR DEVE ser atualizado quando a integração for implementada (status  "Implementado")
