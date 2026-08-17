# Diário por Vínculo Docente v1.0 — Fase 0 — Matriz

## Escopo

| Contexto | DVD v1.0 |
|---|---:|
| Educação Infantil | SIM |
| 1º ao 5º Ano EF | SIM |
| EJA 1ª e 2ª Etapa | SIM |
| 6º ao 9º Ano | NÃO |
| EJA 3ª e 4ª Etapa | NÃO |
| Ensino Médio/outros | NÃO |
| AEE | NÃO |

A entrada no DVD não modifica o regime avaliativo da etapa.

Na Educação Infantil, `education_level=educacao_infantil` é a autoridade de enquadramento; rótulos locais não precisam existir na canonicalização institucional. No Fundamental e na EJA, série/etapa não reconhecida permanece bloqueada para classificação automática.

## Capacidades

| Perfil | Conteúdo | Frequência | Obrigatória | Modo da frequência | Purpose | Avaliação |
|---|---:|---:|---:|---|---|---:|
| `regular` | SIM | SIM | SIM | `class_daily` | `official` | SIM conforme etapa |
| `integrator` | SIM | SIM | NÃO | `assignment_session` | `pdf_only` | NÃO |
| `shared` | SIM | SIM | SIM | `assignment_session` | `official` | SIM conforme etapa |

## Modos e efeitos de frequência

- `class_daily`: preserva a frequência canônica atual da turma/data; não cria cópia por professor.
- `assignment_session`: isola o registro por vínculo/sessão docente. No perfil `integrator`, é `pdf_only`; no perfil `shared`, é `official`.

Somente `official` pode alimentar percentual, presenças/faltas oficiais, Busca Ativa, Bolsa Família, promoção/reprovação, documentos e indicadores.

`pdf_only` é opcional e exclusivamente pedagógico/documental: sua ausência não gera pendência, incompletude nem falta; presença e ausência registradas não entram no numerador nem no denominador da frequência oficial; o registro só pode ser utilizado no diário/PDF do próprio vínculo.

Conteúdo e frequência do integrador são independentes: registrar conteúdo não obriga o lançamento de frequência.

## Migração/autoria

Ordem de evidência para atribuição automática:

1. `teacher_id` explícito e compatível;
2. professor + componente explícitos e compatíveis;
3. único vínculo vigente para turma/componente/data;
4. auditoria que determine inequivocamente o vínculo;
5. `created_by` somente quando for professor e houver vínculo compatível;
6. caso ambíguo: `needs_review`, sem inferência arbitrária.

`created_by` e `updated_by` representam autoria operacional; não substituem a propriedade pedagógica.

## PDF

A unidade do PDF operacional é `assignment_id`. Cada PDF contém somente os registros daquele vínculo. No perfil `integrator`, o PDF contém os registros pedagógicos de conteúdo e, quando houver lançamento, sua frequência `pdf_only`, identificada como acompanhamento documental sem efeito na frequência escolar oficial.

## Multisseriadas

Guardrail da Fase 0: migração automática em bloco somente quando todas as séries/etapas informadas estiverem no escopo. Combinações que atravessem a fronteira do escopo são bloqueadas. No Fundamental/EJA, valor vazio ou não reconhecido bloqueia a classificação automática. Na Educação Infantil, rótulos locais preenchidos podem não ser canônicos porque o nível de ensino é a autoridade de enquadramento.

## Testes de proteção

Novo arquivo: `backend/tests/test_diary_assignment_contract_phase0.py`.

Ele protege: Educação Infantil; 1º–5º Ano; EJA 1ª/2ª; exclusão de 6º–9º, EJA 3ª/4ª, Ensino Médio e AEE; escola integral; multisseriadas; matriz dos perfis; modos `class_daily`/`assignment_session`; `official`/`pdf_only`; regra positiva de frequência oficial; enums de migração.

A suíte específica da Fase 0 deve coletar **54 casos**.

Suítes existentes que devem permanecer verdes nas fases seguintes incluem:

- `test_teacher_class_assignments.py`
- `test_teacher_allocation_integral.py`
- `test_status_conceitual.py`
- `test_serie_canonical.py`
- `test_content_canonical.py`
- `test_content_entries_v1.py`
- `test_content_workflow_v1.py`
- `test_legacy_content_bridge.py`
- `test_grade_integrity.py`
- `test_grade_legacy_migration.py`
- `test_grades_migrated_granular.py`
- `test_attendance_audit_v1.py`
- `test_attendance_consolidation_bolsa_familia.py`
- `test_bolsa_familia_frequency_canonical.py`
- `test_attendance_pdf_bimestre.py`
- `test_attendance_pdf_blank_cells_regression.py`
- `test_multi_grade.py`
- `test_multisseriada_grades.py`
- `test_multigrade_series_pdf.py`

## Gate da Fase 1

A Fase 1 só começa após revisão deste contrato, **54 testes específicos** verdes, regressões conceituais/canonicalização verdes, ausência de alteração no AEE e confirmação de que a Fase 0 não modificou routers, persistência, frontend ou PDFs.
