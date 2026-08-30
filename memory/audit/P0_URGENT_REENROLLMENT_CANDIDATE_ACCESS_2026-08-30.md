# P0 — Acesso inter-escolas para candidatos de matrícula/rematrícula

Data: 2026-08-30

## Solicitação operacional

Estudantes com status **Transferido**, **Desistente**, **Inativo** e **Cancelado** devem poder ser matriculados em qualquer escola da mesma mantenedora por um secretário vinculado à escola de destino, sem exigir vínculo desse secretário com a escola histórica/de origem.

## Diagnóstico

O frontend já classificava como aptos à ação `matricular` os estados canônicos e legados:

- `transferred` / `transferido`;
- `dropout` / `desistente`;
- `inactive` / `inativo`;
- `cancelled` / `cancelado`.

A divergência estava no backend. A camada `student_transfer_destination_access` liberava leitura tenant-wide somente para `transferred/transferido`. Assim, desistentes, inativos e cancelados ainda caíam no GET legado, que exige acesso à escola histórica.

O PUT base já permite ao secretário editar estudantes não ativos fora de suas escolas, mas a guarda explícita de mantenedora da camada de destino era aplicada somente aos transferidos. O reparo amplia essa proteção para todo o conjunto de candidatos, fechando também uma superfície cross-tenant antes da delegação à escrita legada.

## Regra institucional após o reparo

1. **Ativo** continua restrito ao escopo escolar normal do secretário.
2. **Transferido, Desistente, Inativo e Cancelado** podem ser consultados por secretário de outra escola da **mesma mantenedora**.
3. O secretário **não precisa ter vínculo com a escola de origem** desses candidatos.
4. Para mudar de escola ou reativar/matricular, o secretário precisa ter acesso à **escola final/de destino** via `AuthMiddleware.verify_school_access()`.
5. Candidato de outra mantenedora ou sem `mantenedora_id` explícita é bloqueado fail-closed no GET e no PUT.
6. A liberação de consulta não concede autorização sobre a escola histórica.
7. Nenhuma escrita MongoDB é adicionada pela camada; criação de matrícula, turma, histórico e demais regras continuam delegadas ao fluxo canônico existente.
8. Status fora do conjunto autorizado, inclusive `active/ativo`, `deceased` e vazio, permanecem no fluxo anterior.

## Implementação

A composição existente foi preservada para reduzir risco. O módulo e a função `install_student_transfer_destination_access` mantêm seus nomes por compatibilidade, mas a constante interna passa a representar todos os candidatos de nova matrícula.

A SSoT do conjunto autorizado é `REENROLLMENT_CANDIDATE_STATUSES` em:

`backend/routers/student_transfer_destination_access.py`

Nenhuma regra foi duplicada no frontend; ele já possuía a mesma classificação operacional.

## Regressões obrigatórias

- secretário lê cada um dos oito valores canônicos/legados de candidato em outra escola da mesma mantenedora;
- candidato cross-tenant é bloqueado;
- candidato sem tenant explícito é bloqueado;
- ativo e outros estados não autorizados continuam delegados à autorização anterior;
- compatibilidade de documento histórico continua aplicada;
- candidato -> ativo valida exclusivamente a escola de destino;
- destino não vinculado bloqueia antes da escrita delegada;
- edição cadastral de candidato não exige vínculo com a escola histórica;
- PUT cross-tenant bloqueia antes de validar destino ou escrever;
- instalação continua idempotente e sem primitivas diretas de escrita;
- `Gate - Transferência (Regressão)` continua executando a suíte desta camada.

## Produção

Este reparo não autoriza deploy por si só. Merge em `main` pode ocorrer após CI verde conforme a governança vigente; promoção de `production` continua exigindo autorização explícita para o SHA exato.
