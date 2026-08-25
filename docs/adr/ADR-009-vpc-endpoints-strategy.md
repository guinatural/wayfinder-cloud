# ADR-009  Estratégia de VPC Endpoints vs NAT Gateway

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** Rafael Santos (CTO), Bruno Oliveira (SecOps)

---

## 1. Contexto

As Lambdas do Wayfinder Cloud precisam se comunicar com múltiplos serviços AWS
(Config, CloudTrail, CloudWatch, KMS, SNS, SQS, Secrets Manager, EventBridge, S3)
para executar as funções de compliance e observabilidade.

Existem duas formas de viabilizar esse acesso a partir de Lambdas em VPC privada:

1. **NAT Gateway**  roteia o tráfego para a internet pública onde os endpoints AWS estão
2. **VPC Endpoints**  comunicação direta com os serviços AWS dentro da rede AWS, sem internet

Ambas as opções têm implicações de custo, segurança e latência que precisam ser avaliadas.

---

## 2. Opções Avaliadas

### Opção A  NAT Gateway (única solução)

**Arquitetura:** Lambdas em subnet privada  NAT GW em subnet pública  internet  APIs AWS

**Prós:**
- Configuração simples  um NAT Gateway cobre todos os serviços
- Nenhum endpoint extra para gerenciar
- Permite acesso à internet para casos legítimos (ex: webhook externo)

**Contras:**
- **Custo:** $0.045/hora por NAT GW × 730h/mês = $32.85/mês + $0.045/GB processado
- **Segurança:** tráfego de dados sensíveis (credenciais KMS, logs CloudTrail) trafega pela internet pública antes de ser criptografado em nível de aplicação
- **Performance:** latência adicional por roteamento via internet
- **Risco regulatório:** para dados sensíveis de saúde (LGPD art. 46), preferível manter tráfego na rede privada AWS

### Opção B  VPC Interface Endpoints para serviços críticos (ESCOLHIDA para segurança)

**Arquitetura:** Lambdas em subnet privada  VPC Interface Endpoint  API AWS (rede AWS interna)

**Prós:**
- Tráfego nunca sai da rede AWS  nenhum dado percorre a internet pública
- Latência menor (~1-2ms vs ~10-20ms via NAT)
- Auditável: conexões aos endpoints aparecem no VPC Flow Logs
- Permite bloquear acesso a serviços AWS específicos via endpoint policy
- S3 e DynamoDB: Gateway Endpoints gratuitos

**Contras:**
- **Custo:** $0.01/hora por endpoint × 730h = $7.30/endpoint/mês
- 9 Interface Endpoints = ~$65.70/mês (prod, 2 AZs)
- Complexidade: cada endpoint precisa de Security Group e DNS resolution
- Nem todos os serviços AWS têm VPC Endpoint disponível (ex: QuickSight)

### Opção C  Híbrido: Endpoints para serviços críticos + NAT para demais

**Arquitetura:** VPC Endpoints para Config, CloudTrail, KMS, Secrets Manager (dados sensíveis) + NAT GW para demais

**Prós:** Custo reduzido vs opção B total

**Contras:** Complexidade de gerenciar dois caminhos de saída; risco de roteamento incorreto

---

## 3. Decisão

**Opção B  VPC Interface Endpoints para todos os serviços AWS utilizados pelas Lambdas,**
**mais Gateway Endpoints para S3 e DynamoDB (gratuitos).**

Mantemos também 1 NAT Gateway por ambiente (1 em dev, 2 em prod) para:
- Lambdas que precisam chamar APIs externas (webhooks de laboratórios, PagerDuty)
- Updates de pacotes durante o build (não usa NAT em runtime)
- Fallback para serviços sem VPC Endpoint

---

## 4. Justificativa

### 4.1 Segurança (razão principal para o contexto VitaCore)

```
Com NAT Gateway:
Lambda  NAT GW  internet pública  api.kms.us-east-1.amazonaws.com
   tráfego KMS (chave de descriptografia de dados de saúde) via internet

Com VPC Interface Endpoint:
Lambda  VPC Endpoint (ENI privado)  AWS network  KMS
   tráfego KMS nunca sai da rede AWS
```

Para dados de saúde sob LGPD art. 46, o tráfego de operações criptográficas
(KMS), credenciais (Secrets Manager) e logs de auditoria (CloudTrail) deve,
idealmente, nunca percorrer redes públicas  mesmo que o TLS proteja o conteúdo.

### 4.2 Conformidade com AWS Security Best Practices

O AWS Foundational Security Best Practices (FSBP) e o CIS AWS Benchmark recomendam
o uso de VPC Endpoints para acesso a serviços AWS a partir de VPCs privadas.
O Security Hub detectaria como finding se Lambdas em VPC não tivessem endpoints configurados.

### 4.3 Análise de Custo (dev vs prod)

| Ambiente | NAT GW | Interface Endpoints | Gateway Endpoints | Total/mês |
|---|---|---|---|---|
| Dev | 1 × $32.85 | 9 × $7.30 (1 AZ) | $0 | ~$98 |
| Prod | 2 × $32.85 | 9 × $14.60 (2 AZs) | $0 | ~$197 |

**Custo evitado por segurança:**
- Um incidente como o de março custa ~R$ 2,1M
- Custo anual de todos os endpoints em prod: ~$197 × 12 = $2.364  R$ 11.820
- ROI de segurança: 177x

### 4.4 Redução de Superfície de Ataque

Com VPC Endpoints e Security Group sem egress para internet (exceto via NAT para APIs externas):

```
Security Group sg-lambda:
  egress 443  pl-xxxxx (S3 prefix list via Gateway Endpoint)   S3
  egress 443  ENI VPC Endpoints (via SG rule)                  todos os serviços
  egress 443  0.0.0.0/0 via NAT (apenas para APIs externas)
  ingress:   NONE (Lambdas não recebem tráfego direto)
```

Isso significa que mesmo se uma Lambda for comprometida, ela não consegue
alcançar serviços não autorizados fora da rede AWS.

---

## 5. Endpoints Configurados

| Endpoint | Tipo | Custo/AZ/mês | Serviço que usa |
|---|---|---|---|
| `com.amazonaws.us-east-1.s3` | Gateway (gratuito) | $0 | Todas as Lambdas, CloudTrail |
| `com.amazonaws.us-east-1.dynamodb` | Gateway (gratuito) | $0 | Lambda auto-remediation, guardrail |
| `com.amazonaws.us-east-1.config` | Interface | $7.30 | compliance-evaluator |
| `com.amazonaws.us-east-1.cloudtrail` | Interface | $7.30 | auto-remediation |
| `com.amazonaws.us-east-1.monitoring` | Interface | $7.30 | Todas as Lambdas (CloudWatch) |
| `com.amazonaws.us-east-1.logs` | Interface | $7.30 | Todas as Lambdas (CW Logs) |
| `com.amazonaws.us-east-1.kms` | Interface | $7.30 | Todas as Lambdas |
| `com.amazonaws.us-east-1.sns` | Interface | $7.30 | compliance-evaluator, incident-notifier |
| `com.amazonaws.us-east-1.sqs` | Interface | $7.30 | DLQ |
| `com.amazonaws.us-east-1.secretsmanager` | Interface | $7.30 | ECS, Lambdas |
| `com.amazonaws.us-east-1.events` | Interface | $7.30 | compliance-evaluator |
| `com.amazonaws.us-east-1.lambda` | Interface | $7.30 | EventBridge  Lambda invocation |
| `com.amazonaws.us-east-1.ssm` | Interface | $7.30 | Systems Manager Session Manager |
| `com.amazonaws.us-east-1.ssmmessages` | Interface | $7.30 | SSM Session Manager |
| `com.amazonaws.us-east-1.ec2messages` | Interface | $7.30 | SSM Agent |

**Total Interface Endpoints: 13 × $7.30 = $94.90/AZ/mês em prod (2 AZs = $189.80)**

> **Nota de otimização:** Em dev, os endpoints são provisionados em apenas 1 AZ,
> reduzindo para $94.90/mês. A alta disponibilidade de endpoints em 2 AZs é
> reservada para prod, onde a resilência é requisito contratual.

---

## 6. Endpoint Policy (Exemplo  KMS)

Para máxima segurança, cada endpoint pode ter uma policy que restringe quais
chamadas são permitidas. Exemplo para o endpoint KMS:

```json
{
  "Statement": [
    {
      "Sid": "AllowOnlyVitaCoreAccount",
      "Effect": "Allow",
      "Principal": "*",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
      "Resource": "arn:aws:kms:us-east-1:123456789012:key/*",
      "Condition": {
        "StringEquals": {
          "aws:PrincipalAccount": "123456789012"
        }
      }
    }
  ]
}
```

Isso impede que, mesmo com credenciais de outra conta injetadas maliciosamente
na Lambda, o endpoint KMS responda a requisições fora da conta VitaCore.

---

## 7. Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| Custo maior vs NAT-only ($95 vs $33/mês em dev) | Médio | Justificado pelo ROI de segurança (177x) |
| Mais recursos para gerenciar (13 endpoints) | Baixo | Terraform `for_each` gerencia todos com um bloco |
| Nem todos os serviços têm VPC Endpoint | Baixo | NAT GW permanece para APIs externas (PagerDuty, Slack) |
| DNS resolution requer `enableDnsSupport = true` na VPC | Nenhum | Já configurado no módulo networking |

---

## 8. Consequências

- Módulo `networking` DEVE provisionar os 13 VPC Endpoints listados
- Security Group `sg-lambda` DEVE ter egress restrito a endpoints conhecidos
- Todo novo serviço AWS adicionado ao projeto DEVE ter endpoint avaliado
- Custo dos endpoints DEVE ser monitorado via Budget #1 (incluído no total)
- VPC Flow Logs DEVEM estar habilitados para auditoria de tráfego via endpoints
