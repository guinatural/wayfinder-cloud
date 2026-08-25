# ADR-001  Escolha do Terraform como ferramenta de IaC

**Status:** Aceito  
**Data:** 2026-08-21  
**Autor:** Guilherme Barreto Gomes  
**Revisores:** 

---

## Contexto

O projeto Wayfinder Cloud precisa provisionar e gerenciar ~15 tipos de recursos AWS
de forma reproduzível, versionada e auditável. A infraestrutura precisa ser
consistente entre os ambientes `dev` e `prod` e deve ser modificável por qualquer
membro técnico da equipe sem necessidade de acesso direto ao console AWS.

As opções avaliadas foram:

1. **Terraform (HashiCorp)**  IaC declarativo, multi-cloud, HCL
2. **AWS CDK (Python)**  IaC imperativo, AWS-native, Python/TypeScript
3. **AWS CloudFormation**  IaC declarativo nativo AWS, YAML/JSON
4. **Pulumi**  IaC imperativo, multi-cloud, Python

---

## Decisão

**Terraform** foi escolhido como ferramenta principal de IaC.

---

## Justificativa

**Em favor do Terraform:**

- Maior adoção no mercado de trabalho PJ/CLT  aparece em ~70% das vagas de Cloud/DevOps
- Ecossistema maduro com Registry de módulos públicos verificados
- State management explícito (remote state no S3 + DynamoDB lock) torna o estado da infra auditável
- Separação clara entre módulos reutilizáveis e configurações de ambiente
- Provider AWS atualizado frequentemente pela HashiCorp e comunidade
- Permite import de recursos existentes criados manualmente (`terraform import`)
- Plan/Apply separados permitem revisão de mudanças antes da aplicação

**Contra AWS CDK:**
CDK seria mais natural dado o background Python, mas gera CloudFormation internamente,
adicionando uma camada de abstração que dificulta debugging em entrevistas técnicas.
Além disso, CDK requer Node.js mesmo para projetos Python, adicionando dependência.

**Contra CloudFormation:**
YAML verboso dificulta reutilização modular. Não tem suporte a outros providers,
limitando portabilidade de conhecimento. Menos valorizado em vagas que não são AWS-only.

**Contra Pulumi:**
Ecossistema menor, menor adoção no mercado brasileiro. Custo adicional para features
de state management em times.

---

## Trade-offs Aceitos

| Trade-off | Impacto | Mitigação |
|---|---|---|
| HCL é uma linguagem a aprender | Baixo  sintaxe simples | Documentação excelente, curva rápida |
| State file precisa de backend remoto | Médio  configuração inicial | Módulo `storage` cria S3 + DynamoDB para state |
| Não é AWS-native | Baixo para este projeto | Projeto é AWS-only, sem necessidade multi-cloud |

---

## Consequências

- Todos os recursos AWS do projeto DEVEM ser criados via Terraform
- Recursos criados manualmente no console DEVEM ser importados ou destruídos
- O estado Terraform DEVE ser armazenado remotamente (S3 + DynamoDB)
- Mudanças de infraestrutura DEVEM passar por `terraform plan` no CI/CD antes de `apply`
- Módulos reutilizáveis DEVEM ser documentados com `variables.tf` e `outputs.tf` completos
