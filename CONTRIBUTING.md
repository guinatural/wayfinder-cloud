# Guia de Contribuição  Wayfinder Cloud

Obrigado por contribuir com o Wayfinder Cloud. Este guia define as convenções e
processos para manter o projeto organizado, seguro e auditável.

---

## Convenções de Commit (Conventional Commits)

Todos os commits devem seguir o padrão [Conventional Commits v1.0](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Tipos aceitos

| Tipo | Uso |
|---|---|
| `feat` | Nova funcionalidade (nova Config Rule, novo módulo Terraform) |
| `fix` | Correção de bug (Lambda com erro, policy IAM incorreta) |
| `docs` | Mudanças em documentação (ADR, runbook, README) |
| `refactor` | Refatoração sem mudança de comportamento |
| `test` | Adição ou correção de testes |
| `chore` | Tarefas de manutenção (bump de versão, atualização de provider) |
| `security` | Correção de vulnerabilidade ou melhoria de controle de segurança |

### Exemplos

```
feat(compliance): add WAYFINDER-007 rule for RDS public accessibility

Adiciona regra customizada que detecta instâncias RDS com
PubliclyAccessible=true contendo dados de saúde.

LGPD: Art. 46  medidas de segurança no tratamento

feat(iam): add least-privilege policy for audit-reporter Lambda

fix(observability): correct CloudWatch alarm period from 60 to 300s

docs(adr): add ADR-006 Security Hub integration decision

security(networking): restrict Lambda security group to VPC endpoints only
```

---

## Como Criar uma Nova Config Rule

### Passo 1: Abrir issue ou discutir

Antes de implementar, abra uma issue descrevendo:
- Qual violação a regra detecta
- Qual artigo LGPD (ou framework) justifica
- Se é Managed ou Custom
- Se admite remediação automática

### Passo 2: Criar o ADR (se necessário)

Para regras que envolvem decisões arquiteturais relevantes:

```bash
cp docs/adr/ADR-001-iac-terraform.md docs/adr/ADR-00X-nome-da-decisao.md
```

Preencher todas as seções: Contexto, Decisão, Justificativa, Trade-offs, Consequências.

### Passo 3: Adicionar ao módulo compliance

Edite `infra/modules/compliance/main.tf`  consulte o RB-002 para detalhes:

```hcl
# Para Custom Rule
"WAYFINDER-007" = {
  description = "LGPD Art.46  Descrição da violação"
}
```

### Passo 4: Adicionar mapeamento LGPD na Lambda

Edite `src/lambdas/compliance-evaluator/handler.py`:

```python
RULE_LGPD_MAP["WAYFINDER-007"] = {
    "article": "Art. 46",
    "description": "Descrição técnica da regra",
    "severity": "HIGH",        # CRITICAL | HIGH | MEDIUM | LOW
    "auto_remediation": False, # True apenas se ação for segura e reversível
    "remediation_action": None,
}
```

### Passo 5: Implementar remediação (se aplicável)

Se `auto_remediation = True`, adicionar a função em
`src/lambdas/auto-remediation/handler.py` e registrar no `REMEDIATION_DISPATCH`.

### Passo 6: Testar em dev

```bash
cd infra/environments/dev
terraform plan
# Revisar mudanças
terraform apply
# Verificar no Config Console se a regra aparece
```

### Passo 7: Abrir Pull Request

- Título: `feat(compliance): add WAYFINDER-007  descrição curta`
- Descrição: referenciar a issue, descrever o que muda e qual artigo LGPD

---

## Como Adicionar um Novo Módulo Terraform

1. **Criar a estrutura mínima:**
   ```
   infra/modules/<nome>/
     main.tf         recursos principais
     variables.tf    inputs do módulo
     outputs.tf      valores exportados
     README.md       descrição, inputs/outputs (opcional mas recomendado)
   ```

2. **Seguir o padrão de nomenclatura:**
   ```hcl
   locals {
     name_prefix = "wayfinder-${var.environment}"
   }
   ```

3. **Todas as variáveis devem ter `description`:**
   ```hcl
   variable "environment" {
     description = "Nome do ambiente (dev, staging, prod)"
     type        = string
   }
   ```

4. **Adicionar o módulo ao ambiente dev primeiro:**
   ```hcl
   # infra/environments/dev/main.tf
   module "novo_modulo" {
     source = "../../modules/novo-modulo"
     # ...
   }
   ```

5. **Documentar no README principal** se o módulo for significativo.

---

## Padrão de Nomenclatura de Recursos

| Recurso | Padrão | Exemplo |
|---|---|---|
| IAM Roles | `sentinel-{env}-{purpose}-role` | `wayfinder-dev-lambda-evaluator-role` |
| Lambda Functions | `sentinel-{env}-{function-name}` | `wayfinder-dev-compliance-evaluator` |
| S3 Buckets | `sentinel-{env}-{purpose}-{account_id}` | `wayfinder-dev-audit-trail-123456789` |
| DynamoDB Tables | `sentinel-{env}-{purpose}` | `wayfinder-dev-remediation-attempts` |
| CloudWatch Log Groups | `/wayfinder/{category}/{name}` | `/wayfinder/lambda/compliance-evaluator` |
| SNS Topics | `sentinel-{env}-{severity}` | `wayfinder-dev-critical` |
| CloudWatch Alarms | `sentinel-{env}-{description}` | `wayfinder-dev-noncompliant-critical` |
| Config Rules (custom) | `SENTINEL-{NNN}` | `WAYFINDER-007` |
| Config Rules (managed) | `sentinel-{env}-{rule-description}` | `wayfinder-dev-cloud-trail-enabled` |

---

## Obrigatoriedade de ADR para Decisões Arquiteturais

Um ADR **deve** ser criado para:

- Escolha de serviço AWS novo (ex: adicionar GuardDuty)
- Mudança de runtime das Lambdas
- Alteração na estratégia de retenção de logs
- Adição de integração com sistema externo
- Mudança no modelo de dados (DynamoDB schema)
- Qualquer decisão que afete segurança, custo ou conformidade

Um ADR **não precisa** ser criado para:
- Adição de nova Config Rule (segue o processo acima)
- Bumps de versão de provider
- Correções de bug que não mudam a arquitetura

### Template ADR

```markdown
# ADR-00X  Título da Decisão

**Status:** Proposto | Aceito | Depreciado | Substituído por ADR-00Y
**Data:** YYYY-MM-DD
**Autor:** Nome
**Revisores:** 

## Contexto
[O problema ou situação que levou a esta decisão]

## Opções Avaliadas
### Opção 1: ...
### Opção 2: ...

## Decisão
[A decisão tomada]

## Justificativa
[Por que esta opção foi escolhida]

## Trade-offs Aceitos
| Trade-off | Impacto | Mitigação |

## Consequências
[O que muda a partir desta decisão]
```

---

## Revisão de Pull Requests

Todo PR deve:

- [ ] Ter pelo menos 1 aprovação de outro engenheiro
- [ ] Passar no `terraform validate` e `terraform plan` no CI
- [ ] Não incluir credenciais ou valores sensíveis em texto plano
- [ ] Atualizar a documentação relevante (runbook, ADR, README)
- [ ] Ter título seguindo Conventional Commits
