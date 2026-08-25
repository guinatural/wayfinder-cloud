# ADR-004  Estratégia de Remediação Automática

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

Quando uma Config Rule detecta um desvio de conformidade, existem três estratégias possíveis:

1. **Apenas notificar**  alerta humano, remediação manual
2. **Remediação totalmente automática**  sistema corrige sem intervenção humana
3. **Remediação automática seletiva**  automática para casos seguros, notificação para casos ambíguos

Em um ambiente de saúde digital, remediação incorreta pode ser tão danosa quanto
o desvio em si. Por exemplo: deletar automaticamente uma instância EC2 para "remediar"
uma violação de security group pode derrubar um serviço crítico de atendimento.

---

## Decisão

**Remediação automática seletiva** baseada em classificação de risco e reversibilidade.

---

## Matriz de Remediação

| Violação | Severidade | Remediação Automática | Justificativa |
|---|---|---|---|
| S3 Block Public Access desabilitado | CRITICAL |  SIM  ativar Block Public Access | Ação reversível, risco alto demais para esperar |
| S3 sem criptografia KMS | CRITICAL |  SIM  ativar SSE-KMS | Reversível, sem impacto operacional |
| CloudTrail desabilitado | CRITICAL |  SIM  reabilitar CloudTrail | Reversível, sem impacto operacional |
| Security Group com 0.0.0.0/0 na porta 22 | HIGH |  PARCIAL  revogar regra + notificar | Reversível mas pode impactar acesso legítimo |
| EC2 em subnet pública com dados de saúde | CRITICAL |  PARCIAL  isolar via SG + notificar | Mover EC2 de subnet é disruptivo |
| IAM com permissões admin excessivas | HIGH |  NÃO  apenas notificar | Remoção de permissão pode quebrar workflows |
| RDS sem criptografia | HIGH |  NÃO  apenas notificar | Criptografar RDS existente requer recriação |
| MFA desabilitado para IAM user | HIGH |  NÃO  apenas notificar | Não é possível forçar MFA remotamente |

---

## Guardrails de Remediação

Para evitar remediações em cascata ou loops:

```python
# Lambda auto-remediation deve verificar:
# 1. Tag "remediation-exempt=true" no recurso  pular remediação
# 2. Ambiente = prod  exigir aprovação manual via SNS + Lambda approval
# 3. Limite de 3 tentativas por recurso em 1h  evitar loop
# 4. Janela de manutenção ativa  postergar remediação não crítica
```

---

## Processo de Aprovação para Prod

```
Violação detectada em prod
        
        
Lambda compliance-evaluator classifica
        
         CRITICAL  Remediação automática imediata
                        + Notificação pós-fato
        
         HIGH/MEDIUM  SNS notificação com link de aprovação
                                    
                          
                                             
                    Aprovado (2h)       Não respondido (2h)
                                             
                                             
                   Auto-remediation    Escalation para
                   executa             nível superior
```

---

## Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| Remediação automática pode causar interrupção | Médio | Matriz conservadora  apenas ações claramente seguras são automáticas |
| Notificação manual tem latência | Médio | CRITICAL sempre é automático; HIGH tem SLA de 2h |
| Falso positivo pode remediar recurso legítimo | Baixo | Tag `remediation-exempt=true` permite exclusão explícita |

---

## Consequências

- Toda Lambda de remediação DEVE logar ação realizada no CloudWatch com formato estruturado JSON
- Toda ação de remediação DEVE gerar evento no EventBridge para rastreabilidade
- Tag `remediation-exempt=true` DEVE ser documentada como mecanismo de exclusão controlada
- SLA de resposta DEVE ser definido por severidade e monitorado via CloudWatch
- Runbook de remediação manual DEVE existir para cada caso onde automação não é aplicada
