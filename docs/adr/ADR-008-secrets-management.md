# ADR-008  Estratégia de Gestão de Segredos

**Status:** Aceito  
**Data:** 2026-04-15  
**Autores:** Bruno Oliveira (SecOps Lead), Carla Mendes (Dev Lead)  
**Revisores:** Rafael Santos (CTO), Ana Lima (DPO)  
**Motivação:** Credenciais hardcoded e sem rotação encontradas durante análise forense do incidente de março

---

## 1. Contexto

Durante a investigação forense do incidente de março de 2026, a equipe de segurança
identificou um problema adicional ao bucket público: **credenciais de banco de dados
hardcoded em variáveis de ambiente de Lambda functions**.

Especificamente, foram encontradas:
```
Lambda: vitacore-report-generator
Variáveis de ambiente:
  DB_HOST=aurora-vitacore-legacy.cluster-xxx.us-east-1.rds.amazonaws.com
  DB_USER=admin
  DB_PASSWORD=V1t@c0r3#2022   CREDENCIAL EM TEXTO PURO
  
Lambda: vitacore-lab-integration
Variáveis de ambiente:
  LAB_API_KEY=sk_live_xxxxxxxxxxxxxxxxxxx   API KEY EXTERNA
  LAB_WEBHOOK_SECRET=whs_xxxxxxxxxxxxxxxx   SECRET DE WEBHOOK
```

Além disso, o inventário revelou:
- 67 IAM Users com access keys sem rotação há mais de 180 dias
- 3 scripts de deploy com credenciais hardcoded em repositórios privados
- 1 credencial de banco em plain text em um arquivo de configuração no S3

**Impacto potencial:** Se um atacante tivesse obtido as credenciais durante o
período de exposição do bucket S3, poderia ter acessado o banco de dados Aurora
com privilégios de administrador  expondo os 127.000 prontuários completos.

---

## 2. Opções Consideradas

### Opção A: AWS Secrets Manager (ESCOLHIDA)

**Descrição:** Serviço gerenciado da AWS para armazenar, rotacionar e recuperar
credenciais e segredos de forma segura.

**Prós:**
- Rotação automática nativa para Aurora MySQL (sem downtime via dual-password)
- Integração nativa com ECS (envFrom em task definitions) e Lambda (SDK call)
- Versionamento de segredos (AWSCURRENT, AWSPENDING, AWSPREVIOUS)
- Auditoria via CloudTrail de cada GetSecretValue
- KMS CMK para criptografia do valor do segredo
- Replicação multi-region (para futuro disaster recovery)

**Contras:**
- Custo: $0.40/secret/mês + $0.05/10.000 chamadas de API
- Latência adicional de ~1-5ms no startup do serviço (mitigado com cache)
- 15 segredos = $6/mês  custo aceitável dado o risco

### Opção B: AWS Systems Manager Parameter Store SecureString

**Descrição:** Parameter Store com criptografia KMS para valores sensíveis.

**Prós:**
- Custo: $0.05/parâmetro advanced/mês (mais barato que Secrets Manager)
- Integrado ao SSM Agent e Lambda natively
- Hierarquia de parâmetros com paths (/vitacore/prod/db/password)

**Contras:**
- **Sem rotação automática**  exige Lambda customizado para rotação
- Sem versionamento explícito com labels (AWSCURRENT/AWSPENDING)
- Sem suporte nativo a multi-region
- Sem built-in rotation para RDS/Aurora  ponto crítico para a VitaCore

**Descartado:** A ausência de rotação automática para Aurora é um bloqueador.
O time não tem capacidade de manter Lambdas de rotação customizados.

### Opção C: HashiCorp Vault

**Descrição:** Solução open-source de gestão de segredos, self-hosted ou HCP Vault.

**Prós:**
- Extremamente flexível, suporta qualquer tipo de segredo
- Dynamic secrets: credenciais temporárias geradas on-demand (ideal para banco)
- Audit log granular, políticas complexas
- Vendor-agnostic

**Contras:**
- **Overhead operacional:** requer cluster dedicado, HA, backup, patching
- **Equipe sem experiência:** nenhum dos 23 engenheiros tem experiência com Vault
- Custo de infra: ~$200/mês para cluster HA + HCP Vault custo adicional
- HCP Vault (managed): $0.03/hora + $0.003/secret/mês  mais caro que Secrets Manager para este volume

**Descartado:** Overhead operacional inaceitável para time sem dedicated SRE.

### Opção D: Variáveis de Ambiente Criptografadas (status quo melhorado)

**Descrição:** Manter env vars mas criptografar com KMS antes de armazenar.

**Prós:**
- Sem mudança na forma de acesso pelo código
- Sem custo adicional além do KMS

**Contras:**
- **Sem rotação automática**  mesma limitação da Opção B
- Credencial ainda visível (decriptada) para qualquer pessoa com acesso à Lambda
- Não resolve o problema de inventário (como saber onde estão todos os segredos?)
- CloudTrail não registra acesso ao valor da variável de ambiente

**Descartado:** Não resolve os problemas identificados de forma adequada.

---

## 3. Decisão

**Secrets Manager para credenciais de banco de dados e API keys externas.**
**Parameter Store (SecureString) para configurações não-sensíveis.**

### 3.1 O que vai para o Secrets Manager

| Segredo | Tipo | Rotação | Intervalo |
|---|---|---|---|
| Aurora writer credentials (3 clusters) | RDS | Lambda built-in | 30 dias |
| Aurora reader credentials | RDS | Lambda built-in | 30 dias |
| ElastiCache Redis AUTH token | Outro | Manual (alert) | 90 dias |
| API keys de laboratórios (12 labs) | Outro | Manual (alert) | 90 dias |
| Chaves de integração operadoras (3) | Outro | Manual (alert) | 90 dias |
| Cognito Client Secret | Outro | Manual (alert) | 180 dias |
| Webhook secrets (2) | Outro | Manual (alert) | 90 dias |

**Total: ~15 segredos × $0.40 = $6/mês**

### 3.2 O que vai para o Parameter Store

| Parâmetro | Tipo | Exemplo |
|---|---|---|
| URLs de serviços externos | String | /vitacore/prod/lab/endpoint |
| Feature flags | String | /vitacore/prod/features/telehealth-enabled |
| Configurações de timeout | String | /vitacore/prod/api/timeout-ms |
| Endereços de endpoints internos | String | /vitacore/prod/redis/endpoint |

---

## 4. Rotação Automática de Credenciais Aurora

O Secrets Manager oferece rotação nativa para Aurora MySQL usando a estratégia
**dual-password** (zero downtime):

```
Rotação automática (a cada 30 dias):
  1. Secrets Manager cria nova senha temporária
  2. Atualiza o usuário no Aurora MySQL (mantém senha anterior ativa)
  3. Testa nova senha via AWSPENDING rotation Lambda
  4. Se teste ok: AWSPENDING  AWSCURRENT, antiga  AWSPREVIOUS
  5. Aurora aceita ambas as senhas por 24h (janela de transição)
  6. Serviços buscam AWSCURRENT no próximo cold start/refresh

Resultado: zero downtime, zero intervenção manual, sem exposição de senha.

Terraform:
resource "aws_secretsmanager_secret_rotation" "aurora_writer" {
  secret_id           = aws_secretsmanager_secret.aurora_writer.id
  rotation_lambda_arn = data.aws_lambda_function.rds_rotation.arn
  rotation_rules {
    automatically_after_days = 30
  }
}
```

---

## 5. Migração das Credenciais Existentes

### 5.1 Inventário e Migração (Plano de 30 dias)

```
Semana 1: Inventário completo
   Audit de todas as Lambdas: variáveis de ambiente suspeitas
   Audit de todos os repositórios Git: grep por senha/password/key
   Audit de S3 (arquivos de configuração)
   Output: planilha com todos os segredos identificados e localização

Semana 2: Migração das credenciais de banco (prioridade máxima)
   Criar secrets no Secrets Manager para 3 clusters Aurora
   Habilitar rotação automática
   Atualizar task definitions ECS e Lambdas para usar envFrom/SDK
   Testar em dev  staging  prod
   Deletar variáveis de ambiente antigas

Semana 3: Migração de API keys externas
   Criar secrets para chaves de laboratórios e operadoras
   Atualizar código de integração para buscar do Secrets Manager
   Rotar todas as keys no sistema de origem (invalidar antigas)

Semana 4: Validação e controle
   WAYFINDER-007 e WAYFINDER-014 habilitados em todas as Lambdas
   Zero findings dessas rules = migração completa
   Documentar cada segredo no Secrets Manager com tags e owner
```

### 5.2 Padrão de Código para Busca de Segredos

```python
# Padrão recomendado: cache local com TTL para evitar latência
import boto3
import json
from functools import lru_cache
from datetime import datetime, timedelta

_secrets_cache = {}
_cache_ttl = timedelta(hours=1)

def get_secret(secret_name: str) -> dict:
    """Busca segredo do Secrets Manager com cache de 1 hora."""
    now = datetime.utcnow()
    
    if secret_name in _secrets_cache:
        value, cached_at = _secrets_cache[secret_name]
        if now - cached_at < _cache_ttl:
            return value  # Cache hit  sem latência adicional
    
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    value = json.loads(response['SecretString'])
    _secrets_cache[secret_name] = (value, now)
    
    return value

# Uso:
db_creds = get_secret('vitacore/prod/aurora/writer')
connection = mysql.connect(
    host=db_creds['host'],
    user=db_creds['username'],
    password=db_creds['password'],
    database='vitacore'
)
```

---

## 6. Controles Detectivos  WAYFINDER-007 e WAYFINDER-014

### WAYFINDER-007  Credenciais em Variáveis de Ambiente Lambda

```python
# Lógica do compliance-evaluator para WAYFINDER-007
SENSITIVE_PATTERNS = re.compile(
    r'(password|passwd|secret|db_pass|api_key|token|credential|auth)',
    re.IGNORECASE
)
ARN_PATTERN = re.compile(r'^arn:aws:secretsmanager:')

def evaluate_lambda_env_vars(config_item):
    env_vars = config_item.get('configuration', {}).get('environment', {}).get('variables', {})
    
    for key, value in env_vars.items():
        if SENSITIVE_PATTERNS.search(key):
            if not ARN_PATTERN.match(str(value)):
                return {
                    'compliance': 'NON_COMPLIANT',
                    'annotation': f'Variável {key} parece conter credencial. '
                                  f'Use Secrets Manager ARN em vez do valor direto.',
                    'severity': 'HIGH',
                    'lgpd': 'Art. 46'
                }
    
    return {'compliance': 'COMPLIANT'}
```

### WAYFINDER-014  Recursos sem Referência ao Secrets Manager

```
Lógica: um recurso com tag data-classification=health-* que não tem nenhuma
referência a Secrets Manager ARN em suas configurações é suspeito.

Para Lambdas: verificar se environment.variables tem algum value com
             padrão arn:aws:secretsmanager:

Para ECS Task Definitions: verificar se containerDefinitions tem
             secrets[] com valueFrom apontando para Secrets Manager

Para EC2: verificar se user-data ou tags têm referência (heurística)
```

---

## 7. Custos Detalhados

| Item | Custo |
|---|---|
| 15 segredos × $0.40/mês | $6.00/mês |
| 100k chamadas GetSecretValue/mês × $0.05/10k | $0.50/mês |
| Rotação Lambda (inclusa no Secrets Manager) | $0.00 |
| KMS para criptografia dos segredos (inclusa no vitacore-infra-key) | ~$0.10/mês |
| **Total mensal** | **~$6.60/mês** |

**Comparação com custo de um incidente similar ao de março:**
- Custo de prevenção anual: ~$79/ano
- Custo de 1 incidente: ~R$ 2.107.000
- O Secrets Manager paga o ROI em 12 anos de prevenção  ou um único incidente evitado

---

## 8. Consequências

**Positivas:**
- Zero credenciais em plain text no código ou variáveis de ambiente
- Rotação automática de credenciais Aurora sem intervenção manual
- Auditoria granular: CloudTrail registra cada GetSecretValue com quem acessou
- WAYFINDER-007/014 detectam regressões (novo código com credencial hardcoded)
- Conformidade com ISO 27001 A.8.11 (gestão de informação sigilosa)
- LGPD art. 46: medidas técnicas para proteção de dados implementadas

**Negativas:**
- Latência adicional de ~1-5ms no startup de cada serviço (mitigado com cache)
- Desenvolvedores precisam aprender novo padrão de acesso a credenciais
- $6.60/mês de custo adicional  justificado pelo ROI

**Métricas de sucesso:**
- Zero findings WAYFINDER-007 e WAYFINDER-014 após semana 4 da migração
- 100% das credenciais Aurora com rotação automática habilitada
- Zero credenciais expostas em repositórios Git (audit com git-secrets)
- Config Rule `secretsmanager-rotation-enabled` com 100% compliance
