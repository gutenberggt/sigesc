# Integração Claude Code ↔ GitHub — SIGESC

**Objetivo:** permitir que Claude Code leia e edite o SIGESC por branch/PR, preservando CI e aprovação humana antes de qualquer integração em `main`.

## Estado versionado pelo repositório

A integração usa:

- instruções persistentes em `CLAUDE.md`;
- workflow `.github/workflows/claude-code.yml`;
- Claude GitHub App oficial;
- autenticação armazenada somente em GitHub Actions Secrets;
- ruleset já existente de proteção da branch `main`.

## Modelo operacional

```text
Gutenberg
   |
   +-- GitHub Issue / PR: @claude <tarefa>
             |
             v
       Claude Code Action
             |
       branch / commits
             |
             v
            PR
             |
       CI obrigatório
             |
       revisão humana
             |
     autorização explícita
             |
             v
            main
```

O agente não está autorizado a fazer merge autônomo em `main` nem deploy implícito.

## Etapas manuais que não devem ser automatizadas por agentes

### 1. Instalar/autorizar o Claude GitHub App

Instale o aplicativo oficial da Anthropic para o repositório `gutenberggt/sigesc` e conceda somente as permissões necessárias ao repositório selecionado.

Referência oficial: `https://github.com/apps/claude`

Evite conceder acesso a todos os repositórios quando apenas o SIGESC for necessário.

### 2. Configurar autenticação no GitHub Actions

No GitHub:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Configure **uma** das opções abaixo.

#### Opção A — OAuth Claude Code

Nome:

```text
CLAUDE_CODE_OAUTH_TOKEN
```

O token pode ser gerado pelo Claude Code conforme documentação oficial, quando a conta/plano suportar esse método.

#### Opção B — Anthropic API

Nome:

```text
ANTHROPIC_API_KEY
```

Use uma API key da Anthropic destinada a automação/CI.

Nunca grave o valor do token ou da API key em arquivo do repositório, Issue, PR ou comentário.

> O workflow aceita os dois nomes para permitir escolha de autenticação sem novo commit. Prefira manter apenas o método efetivamente utilizado configurado.

## Segurança do gatilho

O workflow possui uma barreira adicional:

```text
github.actor == 'gutenberggt'
```

Assim, comentários de terceiros em um repositório público não devem disparar execução paga do Claude. O gatilho também exige menção explícita a `@claude`.

## Formas de uso

### Issue

Exemplo:

```text
@claude

Faça o preflight desta Issue, localize a SSoT, implemente a menor mudança compatível,
adicione/atualize testes, execute os checks relevantes e deixe o PR pronto para revisão.
Não faça merge em main.
```

### Pull Request

Em comentário/review de PR:

```text
@claude analise a falha do CI, corrija apenas a causa raiz dentro do escopo deste PR,
execute os testes relevantes e atualize o PR. Não faça merge.
```

## Regras específicas do SIGESC

O `CLAUDE.md` é obrigatório para o agente e consolida, entre outros:

- multi-tenancy e RBAC;
- postura fail-closed;
- preservação de SSoT;
- AEE como módulo protegido;
- guards de Diário por Vínculo;
- arquitetura e bloqueios de envio real MIG/MEC/CMDE;
- proteção de segredos e dados pessoais;
- branch/PR/CI/revisão antes do merge.

## Diagnóstico quando o Claude não responder

Verifique nesta ordem:

1. o Claude GitHub App está instalado para `gutenberggt/sigesc`;
2. existe exatamente um método de autenticação válido configurado em Actions Secrets;
3. o comentário foi feito por `gutenberggt`;
4. o comentário contém `@claude`;
5. o workflow `Claude Code` foi disparado em `Actions`;
6. o job possui permissões para `contents`, `pull-requests`, `issues` e leitura de `actions`;
7. a autenticação Anthropic permanece válida;
8. o ruleset/CI não está bloqueando a operação esperada.

## Governança de merge

A integração do Claude não altera a regra do projeto: nenhuma integração em `main` deve ocorrer sem autorização humana explícita. O ruleset da `main` e os checks obrigatórios continuam sendo a barreira técnica principal; `CLAUDE.md` adiciona a barreira comportamental do agente.

## Referências

- `README.md`
- `CLAUDE.md`
- `docs/governance/KNOWLEDGE_AND_CONVERSATION_GOVERNANCE.md`
- `docs/governance/PROJECT_STATE_BASELINE_2026-08-27.md`
- documentação oficial do `anthropics/claude-code-action`
