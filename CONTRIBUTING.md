# Contributing to Wayfinder Cloud
# Contribuindo para o Wayfinder Cloud

**EN** Thank you for your interest in contributing to Wayfinder Cloud.
This guide explains the conventions and processes used in this project.

**PT** Obrigado pelo interesse em contribuir para o Wayfinder Cloud.
Este guia explica as convencoes e processos usados neste projeto.

---

## Commit Convention / Convencao de Commits

**EN** We use Conventional Commits. Every commit must follow this format:
**PT** Usamos Conventional Commits. Todo commit deve seguir este formato:

```
type(scope): short description in English

Longer explanation if needed.
```

**Types / Tipos:**

| Type / Tipo | When to use / Quando usar |
|---|---|
| `feat` | New feature / Nova funcionalidade |
| `fix` | Bug fix / Correcao de bug |
| `docs` | Documentation only / Apenas documentacao |
| `refactor` | Code change without new feature / Mudanca sem nova funcionalidade |
| `test` | Adding or fixing tests / Adicionando ou corrigindo testes |
| `ci` | CI/CD pipeline changes / Mudancas no pipeline |
| `chore` | Maintenance tasks / Tarefas de manutencao |

**Examples / Exemplos:**

```
feat(compliance): add WAYFINDER-015 rule for untagged resources
fix(lambda): handle missing resource tags in compliance-evaluator
docs(adr): add ADR-010 for multi-region disaster recovery
```

---

## Adding a New Config Rule / Adicionando uma Nova Regra Config

**EN** Follow these steps to add a new WAYFINDER rule.
**PT** Siga estes passos para adicionar uma nova regra WAYFINDER.

**Step 1 / Passo 1 - Document the rule / Documente a regra**

Add the rule specification to `docs/compliance/lgpd-controls-mapping.md`:

```
WAYFINDER-XXX - Short description
  Trigger:        What event triggers evaluation
  Evaluation:     What condition is checked
  Non-compliant:  Severity level (CRITICAL / HIGH / MEDIUM)
  Remediation:    Auto or manual
  LGPD:           Applicable article
```

**Step 2 / Passo 2 - Add to Terraform / Adicione no Terraform**

In `infra/modules/compliance/main.tf`, add to `custom_rules`:

```hcl
"WAYFINDER-XXX" = "Description matching LGPD article (LGPD Art.XX)"
```

**Step 3 / Passo 3 - Add evaluation logic / Adicione a logica de avaliacao**

In `src/lambdas/compliance-evaluator/handler.py`, add to `RULE_LGPD_MAP`:

```python
"WAYFINDER-XXX": {
    "article":          "Art. XX",
    "description":      "What this rule checks",
    "severity":         "CRITICAL",   # or HIGH, MEDIUM
    "auto_remediation": True,         # or False
    "remediation_action": "action_name",  # or None
},
```

**Step 4 / Passo 4 - Write a test / Escreva um teste**

Add a test case in `src/tests/test_compliance_evaluator.py`.

**Step 5 / Passo 5 - Add ADR if architectural / Adicione ADR se for decisao arquitetural**

If the rule introduces a new architectural pattern, create an ADR in `docs/adr/`.

---

## Naming Conventions / Convencoes de Nomenclatura

**EN** All AWS resources follow this pattern for consistency.
**PT** Todos os recursos AWS seguem este padrao para consistencia.

| Resource type / Tipo de recurso | Pattern / Padrao | Example / Exemplo |
|---|---|---|
| Terraform module resource | `wayfinder-${environment}` | `wayfinder-dev` |
| Custom Config Rules | `WAYFINDER-{NNN}` | `WAYFINDER-007` |
| Lambda functions | `wayfinder-{env}-{name}` | `wayfinder-dev-compliance-evaluator` |
| S3 buckets | `wayfinder-{env}-{purpose}-{account}` | `wayfinder-dev-audit-trail-123456789012` |
| CloudWatch metrics | `Wayfinder/Compliance`, `Wayfinder/Remediation` | |
| EventBridge bus | `wayfinder-events` | |
| KMS aliases | `alias/wayfinder-{env}` | `alias/wayfinder-prod` |

---

## ADR Policy / Politica de ADR

**EN** Any decision that affects system architecture, data flow, security model,
or cost structure must be documented as an ADR before implementation.

**PT** Qualquer decisao que afete a arquitetura do sistema, fluxo de dados,
modelo de seguranca ou estrutura de custo deve ser documentada como ADR antes
da implementacao.

**ADR file naming / Nomenclatura do arquivo ADR:**
`docs/adr/ADR-{NNN}-{short-title}.md`

**Required sections / Secoes obrigatorias:**
- Context / Contexto
- Options evaluated / Opcoes avaliadas
- Decision / Decisao
- Justification / Justificativa
- Trade-offs accepted / Trade-offs aceitos
- Consequences / Consequencias

---

## Pull Request Process / Processo de Pull Request

**EN**
1. Create a branch from `main` with a descriptive name
2. Make your changes following the conventions above
3. Ensure `terraform validate` passes for any infrastructure changes
4. Ensure tests pass: `pytest src/tests/`
5. Open a PR with a clear description of what changes and why
6. Wait for the automated `terraform plan` comment on the PR
7. Request review if the change affects security or compliance controls

**PT**
1. Crie uma branch a partir de `main` com nome descritivo
2. Faca suas mudancas seguindo as convencoes acima
3. Garanta que `terraform validate` passa para mudancas de infraestrutura
4. Garanta que os testes passam: `pytest src/tests/`
5. Abra um PR com descricao clara do que muda e por que
6. Aguarde o comentario automatico do `terraform plan` no PR
7. Solicite revisao se a mudanca afeta controles de seguranca ou compliance

---

## Questions / Perguntas

**EN** Open an issue with the label `question` or reach out via LinkedIn.
**PT** Abra uma issue com a label `question` ou entre em contato via LinkedIn.

[GitHub Issues](https://github.com/guinatural/wayfinder-cloud/issues)
