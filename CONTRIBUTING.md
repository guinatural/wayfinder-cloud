# Contributing to Wayfinder Cloud

Thank you for your interest in contributing.
This guide explains the conventions and processes used in this project.

---

## Commit Convention

We use Conventional Commits. Every commit must follow this format:

```
type(scope): short description

Longer explanation if needed.
```

**Types:**

| Type | When to use |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation changes only |
| `refactor` | Code change without new feature |
| `test` | Adding or fixing tests |
| `ci` | CI/CD pipeline changes |
| `chore` | Maintenance tasks |

**Examples:**

```
feat(compliance): add WAYFINDER-015 rule for untagged resources
fix(lambda): handle missing resource tags in compliance-evaluator
docs(adr): add ADR-010 for multi-region disaster recovery
```

---

## Adding a New Config Rule

Follow these steps to add a new WAYFINDER rule.

**Step 1 - Document the rule**

Add the rule specification to `docs/compliance/lgpd-controls-mapping.md`:

```
WAYFINDER-XXX - Short description
  Trigger:      What event triggers evaluation
  Evaluation:   What condition is checked
  Severity:     CRITICAL / HIGH / MEDIUM
  Remediation:  Auto or manual
  LGPD:         Applicable article
```

**Step 2 - Add to Terraform**

In `infra/modules/compliance/main.tf`, add to `custom_rules`:

```hcl
"WAYFINDER-XXX" = "Description matching LGPD article (LGPD Art.XX)"
```

**Step 3 - Add evaluation logic**

In `src/lambdas/compliance-evaluator/handler.py`, add to `RULE_LGPD_MAP`:

```python
"WAYFINDER-XXX": {
    "article":            "Art. XX",
    "description":        "What this rule checks",
    "severity":           "CRITICAL",
    "auto_remediation":   True,
    "remediation_action": "action_name",
},
```

**Step 4 - Write a test**

Add a test case in `src/tests/test_compliance_evaluator.py`.

**Step 5 - Add an ADR if needed**

If the rule introduces a new architectural pattern, create an ADR in `docs/adr/`.

---

## Naming Conventions

All AWS resources follow this pattern for consistency.

| Resource type | Pattern | Example |
|---|---|---|
| Terraform module resource | `wayfinder-${environment}` | `wayfinder-dev` |
| Custom Config Rules | `WAYFINDER-{NNN}` | `WAYFINDER-007` |
| Lambda functions | `wayfinder-{env}-{name}` | `wayfinder-dev-compliance-evaluator` |
| S3 buckets | `wayfinder-{env}-{purpose}-{account}` | `wayfinder-dev-audit-trail-123456789012` |
| CloudWatch metrics namespace | `Wayfinder/Compliance`, `Wayfinder/Remediation` | |
| EventBridge bus | `wayfinder-events` | |
| KMS aliases | `alias/wayfinder-{env}` | `alias/wayfinder-prod` |

---

## ADR Policy

Any decision that affects architecture, data flow, security model, or cost
structure must be documented as an ADR before implementation.

**File naming:** `docs/adr/ADR-{NNN}-{short-title}.md`

**Required sections:**
- Context
- Options evaluated
- Decision
- Justification
- Accepted trade-offs
- Consequences

---

## Pull Request Process

1. Create a branch from `main` with a descriptive name
2. Follow the naming conventions and commit format above
3. Run `terraform validate` for any infrastructure changes
4. Run tests: `pytest src/tests/`
5. Open a PR with a clear description of what changes and why
6. Wait for the automated `terraform plan` comment on the PR
7. Request review if the change affects security or compliance controls

---

## Questions

Open an issue with the label `question`.

[GitHub Issues](https://github.com/guinatural/wayfinder-cloud/issues)
