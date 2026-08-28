# P1 — Autorização da escola de destino para estudante transferido

Data: 2026-08-28

## Origem

O PR #178 (`fix(students): autorizar matrícula de transferido pela escola de destino`) foi validado por CI, porém permaneceu aberto/draft e nunca foi integrado em `main`.

Após sua criação, `main` recebeu a camada `student_legacy_compat`, que passou a ser a SSoT da projeção não persistente de documentos históricos de estudantes. Por isso, o PR #178 não deve ser integrado tardiamente sem adaptação.

## Regra institucional preservada

- estudante ativo continua restrito ao escopo escolar do secretário;
- estudante transferido pode ser consultado por secretário de outra escola da mesma mantenedora para matrícula de entrada;
- transferido cross-tenant é bloqueado fail-closed;
- consulta do transferido não concede acesso à escola histórica de origem;
- mudança de escola ou reativação por secretário exige `AuthMiddleware.verify_school_access()` na escola final/de destino;
- edição meramente cadastral de estudante transferido não exige vínculo com a escola histórica;
- fluxo existente continua responsável por matrícula, histórico, turma e demais regras de domínio.

## Adaptação ao `main` atual

A nova camada reutiliza `normalize_legacy_student_doc()` de `student_legacy_compat` na leitura direta do estudante transferido. Isso evita que a autorização de destino reintroduza incompatibilidade de resposta para documentos históricos com endereço e Literals legados.

A composição final de `setup_students_router` fica:

1. router base;
2. identity guard;
3. identity continuity;
4. audit semantics;
5. legacy compatibility;
6. transfer destination access.

## Segurança

O adaptador de autorização de destino:

- não possui `insert_one`, `update_one`, `delete_one` ou `bulk_write`;
- não altera JWT ou lotações;
- não amplia acesso cross-tenant;
- delega qualquer gravação ao fluxo canônico já existente;
- valida a escola de destino antes de delegar a operação de reativação/mudança de escola.

## Regressões obrigatórias

- secretário carrega transferido de outra escola da mesma mantenedora;
- transferido de outra mantenedora é bloqueado;
- transferido sem tenant explícito é bloqueado;
- ativo continua no fluxo anterior de autorização;
- documento transferido legado é normalizado antes da resposta;
- `transferred -> active` valida a escola de destino;
- escola de destino não vinculada bloqueia antes da escrita delegada;
- edição cadastral do transferido não exige acesso à escola histórica;
- instalação é idempotente e sem superfície de escrita direta;
- gate histórico de Transferência continua verde.

## Governança

Esta mudança corrige o gap funcional do PR #178. Merge em `main` e deploy continuam sujeitos à autorização humana explícita.
