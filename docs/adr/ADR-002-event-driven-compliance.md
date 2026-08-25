# ADR-002  Arquitetura Event-Driven para Avaliação de Compliance

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

O sistema de compliance precisa avaliar recursos AWS continuamente e reagir a
desvios de conformidade sem polling ativo. Existem duas abordagens principais:

1. **Polling periódico**  Lambda agendada que varre recursos periodicamente
2. **Event-driven**  Config Rules + EventBridge reagem a mudanças em tempo real

O contexto de saúde digital impõe requisito adicional: o tempo entre um desvio
de conformidade ocorrer e a resposta (alerta + remediação) deve ser o menor
possível para cumprir o espírito do art. 48 da LGPD (comunicação de incidentes).

---

## Decisão

**Arquitetura event-driven** usando AWS Config + EventBridge como backbone de eventos,
com Lambda como executor de lógica de avaliação e remediação.

---

## Justificativa

**Latência de detecção:**
- Polling a cada 5 min: desvio pode existir por até 5 min antes de detectado
- Event-driven (Config  EventBridge): detecção em segundos após a mudança de configuração

**Custo:**
- Lambda on-demand: cobrança apenas por execução real
- Polling com Lambda a cada 5 min: ~8.640 execuções/mês mesmo sem eventos

**Escalabilidade:**
- EventBridge processa múltiplos eventos simultâneos sem gargalo
- Regras de roteamento permitem encaminhar tipos diferentes de eventos para Lambdas específicas

**Desacoplamento:**
- AWS Config, EventBridge e Lambda são independentes
- Falha em uma Lambda de remediação não impacta a detecção
- Novos tipos de compliance podem ser adicionados criando nova Config Rule + EventBridge Rule
  sem modificar componentes existentes (Open/Closed Principle)

---

## Fluxo Arquitetural Detalhado

```
Recurso AWS modificado
        
        
AWS Config detecta mudança de configuração
        
        
Config Rule avalia: COMPLIANT ou NON_COMPLIANT
        
        
EventBridge Rule (on Config Rule change)
        
         NON_COMPLIANT + CRITICAL  Lambda compliance-evaluator
                                               
                                                SNS Topic CRITICAL
                                                Lambda auto-remediation
        
         NON_COMPLIANT + HIGH  Lambda compliance-evaluator
                                               
                                                SNS Topic WARNING
        
         COMPLIANT  CloudWatch metric (conformidade %)
```

---

## Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| Config tem delay de alguns segundos para detectar mudanças | Baixo  segundos, não minutos | Aceitável para o contexto |
| EventBridge tem limite de 300 rules por event bus | Baixo  projeto usa ~20 rules | Monitorar conforme projeto escala |
| Complexidade de debugar fluxo event-driven | Médio | X-Ray tracing em todas as Lambdas + CloudWatch Logs estruturados |

---

## Consequências

- Config DEVE ser habilitado em todas as regiões ativas com gravação de todos os recursos
- EventBridge DEVE ter regras para cada tipo de violação classificada por severidade
- Todas as Lambdas DEVEM ter X-Ray ativo para rastreabilidade do fluxo de eventos
- Dead Letter Queues (SQS) DEVEM ser configuradas em todas as Lambdas para capturar falhas
- CloudWatch DEVE ter métricas customizadas para conformidade (% recursos COMPLIANT)
