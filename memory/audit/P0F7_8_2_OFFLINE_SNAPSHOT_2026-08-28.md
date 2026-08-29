# P0-F7.8.2 — Offline Snapshot Re-evaluation

Data: 2026-08-28
Status: implementação de segurança operacional

## Motivo

A execução das variantes anteriores da P0-F7.8 dentro do ambiente de produção provocou pressão severa de memória e um evento OOM no host. O kernel registrou encerramento de um processo `uvicorn` por falta de memória. A partir deste incidente, a cadeia P0-F7.8 adota uma fronteira operacional mais forte: **nenhum auditor Python desta fase poderá ser executado dentro do backend de produção**.

## Arquitetura da P0-F7.8.2

A fase passa a ser dividida em duas partes independentes:

1. **Coleta mínima em produção**
   - executada exclusivamente por `mongosh` no container MongoDB;
   - exatamente 3 casos selados;
   - exatamente 3 leituras por caso;
   - coleções permitidas: `classes`, `courses`, `teacher_assignments`;
   - orçamento total: 9 consultas;
   - nenhuma consulta a `students`, `enrollments`, `grades` ou `attendance`;
   - nenhuma escrita;
   - nenhuma execução Python no backend;
   - nenhum replay de `resolve_curriculum()`.

2. **Análise local/offline**
   - executada no computador do operador, preferencialmente via PowerShell;
   - usa o relatório selado P0-F7.5 e o snapshot mínimo exportado;
   - reutiliza as funções puras da SSoT `curriculum_resolver.py`;
   - valida drift de turma, tenant, escola, ano, cursos e vínculos;
   - classifica os três pares curriculares;
   - não possui cliente MongoDB e não realiza acesso à produção.

## Entry points

- Gerador local do coletor: `backend/scripts/build_p0f7_8_2_snapshot_js.py`
- Núcleo offline: `backend/scripts/audit_p0f7_8_2_offline_snapshot.py`
- Runner oficial offline: `backend/scripts/audit_p0f7_8_2_offline_runner.py`
- Wrapper PowerShell local: `scripts/p0f7_8_2_analyze_local.ps1`

Os entrypoints de produção das versões anteriores ficam removidos:

- `backend/scripts/audit_p0f7_8_post_hardening_reevaluation.py`
- `backend/scripts/audit_p0f7_8_1_bounded_reevaluation.py`

## Invariantes

- `read_only = true`
- `production_python_executions = 0`
- `production_backend_exec_calls = 0`
- `production_snapshot_query_calls = 9`
- `student_records_read = 0`
- `enrollment_records_read = 0`
- `grade_records_read = 0`
- `attendance_records_read = 0`
- `automatic_course_mutations = 0`
- `automatic_workload_decisions = 0`
- `production_writes_executed = false`
- `not_authorization_for_executor = true`

## Escopo dos três casos

A P0-F7.8.2 não altera as conclusões de política já estabelecidas. Ela somente revalida, contra um snapshot mínimo atual, se o estado cadastral continua compatível com a cadeia P0-F7.5/P0-F7.7:

1. MULTI 8º E 9º — expectativa de preferência curricular forte pelo source.
2. MULTI 3º E 4º ETAPA — source e target incompatíveis com `eja_final`, exigindo adjudicação.
3. MULTI 6º E 7º — source e target permanecem em tier de revisão, exigindo adjudicação.

A divergência de carga horária semanal 2h versus 3h permanece separada e não é resolvida nesta fase.

## Regra operacional permanente

Auditorias forenses que percorram dados acadêmicos ou executem resolvers por estudante não devem ser executadas no container de aplicação de produção. Quando uma confirmação live for necessária, preferir snapshot mínimo, projeções explícitas, orçamento fixo de consultas e processamento offline.
