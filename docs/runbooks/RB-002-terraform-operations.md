# Runbook RB-002  Operações Terraform

**Projeto:** Wayfinder Cloud  
**Versão:** 1.0  
**Classificação:** OPERACIONAL

---

## Pré-requisitos

| Ferramenta | Versão Mínima | Instalação |
|---|---|---|
| Terraform | >= 1.6.0 | `brew install terraform` ou [terraform.io/downloads](https://developer.hashicorp.com/terraform/downloads) |
| AWS CLI | >= 2.13.0 | `brew install awscli` |
| Python | >= 3.12 | Para os scripts de bootstrap |

### Credenciais AWS

Configure os profiles no `~/.aws/credentials`:

```ini
[wayfinder-dev]
aws_access_key_id     = AKIA...
aws_secret_access_key = ...
region                = us-east-1

[wayfinder-prod]
aws_access_key_id     = AKIA...
aws_secret_access_key = ...
region                = us-east-1
```

Ou use IAM Identity Center (SSO):

```bash
aws sso login --profile wayfinder-dev
```

---

## Bootstrap do Estado Remoto

**Execute este passo UMA VEZ antes do primeiro `terraform apply`.**

O estado Terraform é armazenado em S3 + DynamoDB. Esses recursos precisam existir antes
do primeiro apply (não podem ser criados pelo próprio Terraform  chicken-and-egg).

### Passo 1: Criar o bucket S3 de state

```bash
# Para dev
aws s3api create-bucket \
  --bucket wayfinder-cloud-tfstate-dev \
  --region us-east-1 \
  --profile wayfinder-dev

# Habilitar versionamento (obrigatório para recovery)
aws s3api put-bucket-versioning \
  --bucket wayfinder-cloud-tfstate-dev \
  --versioning-configuration Status=Enabled \
  --profile wayfinder-dev

# Bloquear acesso público
aws s3api put-public-access-block \
  --bucket wayfinder-cloud-tfstate-dev \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --profile wayfinder-dev

# Habilitar SSE-S3 (mínimo; trocar por SSE-KMS em prod)
aws s3api put-bucket-encryption \
  --bucket wayfinder-cloud-tfstate-dev \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' \
  --profile wayfinder-dev
```

### Passo 2: Criar tabela DynamoDB para lock

```bash
aws dynamodb create-table \
  --table-name wayfinder-cloud-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1 \
  --profile wayfinder-dev
```

---

## Comandos do Dia a Dia

### Inicializar workspace

```bash
cd infra/environments/dev
terraform init
```

Se mudar o backend ou adicionar um novo provider:

```bash
terraform init -upgrade
```

### Criar arquivo de variáveis

```bash
cp terraform.tfvars.example terraform.tfvars
# Edite com os valores do seu ambiente (alert_email, etc.)
```

### Verificar plano de mudanças (SEMPRE executar antes do apply)

```bash
terraform plan -out=tfplan.binary
```

Para salvar em formato legível:

```bash
terraform show -json tfplan.binary | jq . > tfplan.json
```

### Aplicar mudanças

```bash
# Usar o plano gerado (recomendado  garante que apply = exatamente o que foi revisado)
terraform apply tfplan.binary

# Apply direto (não recomendado em prod)
terraform apply
```

### Destruir ambiente (APENAS dev)

```bash
# Nunca executar em prod  destruição irreversível
terraform destroy
```

---

## Como Adicionar uma Nova Config Rule

### 1. Decidir: Managed ou Custom?

- **Managed**: Use se a AWS já tem um `source_identifier` pronto (ex: `S3_BUCKET_MFA_DELETE_ENABLED`)
- **Custom**: Use para regras específicas do negócio (ex: verificar tag `data-classification`)

### 2. Adicionar ao módulo compliance

Edite `infra/modules/compliance/main.tf`:

**Para Managed Rule**  adicione na seção `locals.managed_rules`:
```hcl
locals {
  managed_rules = {
    # ... regras existentes ...
    s3_mfa_delete = {
      source_identifier = "S3_BUCKET_MFA_DELETE_ENABLED"
      description       = "Verifica se S3 tem MFA Delete habilitado"
    }
  }
}
```

**Para Custom Rule**  adicione na seção `locals.custom_rules`:
```hcl
locals {
  custom_rules = {
    # ... regras existentes ...
    "WAYFINDER-007" = {
      description = "LGPD Art.XX  Descrição da nova violação"
    }
  }
}
```

### 3. Adicionar mapeamento LGPD na Lambda

Edite `src/lambdas/compliance-evaluator/handler.py`:
```python
RULE_LGPD_MAP["WAYFINDER-007"] = {
    "article": "Art. XX",
    "description": "Descrição técnica da regra",
    "severity": "HIGH",
    "auto_remediation": False,
    "remediation_action": None,
}
```

### 4. Criar ADR se necessário

Para regras que implicam decisões arquiteturais, crie um ADR em `docs/adr/`.

### 5. Testar e aplicar

```bash
cd infra/environments/dev
terraform plan
# Revisar mudanças: nova Config Rule + Lambda permission
terraform apply
```

---

## Como Fazer Rollback de uma Mudança

### Opção 1: Reverter via git (recomendado)

```bash
# Ver histórico de mudanças
git log --oneline infra/

# Reverter para o commit anterior
git revert HEAD
git push

# No pipeline CI/CD: terraform apply será executado com o estado anterior
```

### Opção 2: State manipulation (avançado  use com cuidado)

```bash
# Ver state atual
terraform state list

# Se um recurso foi criado incorretamente, remover do state sem destruir o recurso real
terraform state rm aws_config_config_rule.custom["WAYFINDER-007"]
```

### Opção 3: Import de recurso existente

Se um recurso foi criado manualmente e precisa ser importado para o state:
```bash
terraform import aws_config_config_rule.custom[\"WAYFINDER-007\"] WAYFINDER-007
```

---

## Troubleshooting Comum

### State Lock

**Sintoma:** `Error acquiring the state lock`

**Causa:** Apply anterior falhou sem liberar o lock, ou outro engenheiro está com apply aberto.

**Resolução:**
```bash
# Verificar quem tem o lock
aws dynamodb get-item \
  --table-name wayfinder-cloud-tfstate-lock \
  --key '{"LockID":{"S":"wayfinder-cloud-tfstate-dev/dev/terraform.tfstate"}}' \
  --profile wayfinder-dev

# Se o lock for órfão (apply falhou), forçar a liberação
terraform force-unlock <LOCK_ID>
```

### Drift Detection

**Sintoma:** Terraform quer recriar recursos que parecem idênticos.

**Causa:** Alguém modificou o recurso manualmente pelo console.

**Diagnóstico:**
```bash
terraform plan -detailed-exitcode
# Exit code 2 = há mudanças (drift detectado)
# Exit code 0 = sem mudanças
```

**Resolução:**
- Opção A: `terraform apply` para forçar o estado declarativo (preferido)
- Opção B: `terraform import` para aceitar a mudança manual no state

### Provider Timeout em VPC Endpoints

**Sintoma:** `Error: waiting for VPC Endpoint to reach target state`

**Causa:** VPC Interface Endpoints podem demorar 5-15 minutos para provisionar.

**Resolução:**
```bash
# Aguardar e re-executar
terraform apply -refresh=true
```

### Lambda: Package não encontrado

**Sintoma:** `Error: opening zip file`

**Causa:** O `data.archive_file` não encontrou os arquivos fonte.

**Resolução:**
```bash
# Verificar se os arquivos Python existem
ls src/lambdas/compliance-evaluator/
# handler.py deve existir

# Forçar re-criação do zip
terraform apply -replace=data.archive_file.compliance_evaluator
```
