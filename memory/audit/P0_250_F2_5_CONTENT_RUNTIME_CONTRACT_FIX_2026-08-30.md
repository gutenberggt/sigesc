# P0 #250 — F2.5 Correção do contrato runtime de Objetos de Conhecimento

Data: 2026-08-30

## Contexto

A F2.4 read-only em produção, no SHA `1465b92a82f0a9094dc0c28130d04b17d4022b19`, classificou o caso-canário como `CONTENT_RUNTIME_LEGACY_FALLBACK_BLOCKED`:

- `/professor/diarios` entregava **0** diários `content_enabled` para a turma;
- o `contentDvdBridge` portanto mantinha o GET legado `/learning-objects`;
- o guard backend encontrava **7** `teacher_class_assignments` brutos habilitados e bloqueava o mesmo GET com 409;
- junho/2026 possuía **45** registros legados, inclusive 30/06, 29/06, 27/06 e 26/06.

A divergência era de contrato de cutover, não de dados pedagógicos.

## Causa raiz

`legacy_content_dvd_guard.professor_has_active_dvd_content()` decidia o cutover a partir de um `find_one` bruto em `teacher_class_assignments` (`diary_settings.enabled=true` + vigência aproximada).

O frontend, porém, decide o rewrite a partir de `/professor/diarios`, cuja fonte é `list_teacher_diaries()`. Esse serviço submete os vínculos ao autorizador canônico e só expõe `capabilities.content_enabled=true` quando existe rota DVD de conteúdo efetivamente utilizável.

Logo, um vínculo podia bloquear o legado no backend sem existir como candidato de conteúdo no frontend.

## Correção F2.5

O guard de produção passa a reutilizar diretamente `list_teacher_diaries()` e espelha literalmente o matching do `contentDvdBridge`:

1. mesmo professor autenticado;
2. mesma data de referência;
3. mesma turma, quando informada;
4. quando a requisição informa componente, `component_id` precisa ser exatamente o mesmo;
5. vínculo class-wide (`component_id` nulo) participa apenas da leitura sem filtro de componente, exatamente como no bridge atual;
6. `capabilities.content_enabled is True`.

Somente quando existe esse candidato canônico o reader legado é bloqueado.

`build_professor_dvd_query()` é preservado apenas como helper estrutural/forense para auditorias; ele deixa de ser autoridade funcional de cutover.

## Invariante resultante

Para professor comum:

- se o frontend possui candidato DVD de conteúdo, o backend bloqueia `/learning-objects` e o bridge usa `content_entries`;
- se o frontend **não** possui candidato DVD de conteúdo, o backend não bloqueia o fallback legado e a tela pode ler `learning_objects` normalmente.

Isto elimina o estado contraditório `frontend -> legado` + `backend -> 409` identificado pela F2.4.

## Testes de regressão

`backend/tests/test_legacy_content_dvd_guard_f2_5.py` cobre:

- vínculo bruto sem diário canônico não bloqueia o legado;
- diário canônico com conteúdo habilitado bloqueia;
- capability de conteúdo desabilitada não bloqueia;
- componente diferente não bloqueia;
- vínculo class-wide não bloqueia requisição component-scoped;
- vínculo class-wide participa da requisição class-level sem componente;
- perfil não-professor não aciona o reader de diários.

O teste histórico `backend/tests/test_legacy_content_dvd_guard_phase38f.py` também foi adaptado para a nova autoridade canônica, mantendo os testes estruturais do helper bruto.

## Escopo e segurança

- nenhuma mutação ou migração de MongoDB;
- nenhum backfill/remapeamento;
- nenhum relaxamento de RBAC: a decisão passa a usar uma projeção **mais canônica**, não mais permissiva por perfil;
- nenhuma alteração em notas, frequência, conteúdo persistido ou vínculos;
- nenhuma publicação automática em produção.

## Estado visual stale

A F2.4 também identificou que `LearningObjects.loadRecords()` preserva `records` quando uma requisição falha. Isso é um hardening de UI independente da causa raiz. A F2.5 corrige a contradição que gerava o 409 no caso-canário; a limpeza explícita de estado em falhas pode ser tratada como F2.5.1, sem misturar a correção da SSoT de cutover com alteração de UX/estado da tela.

## Smoke pós-deploy previsto

No caso-canário `E M E I E F Jose Pereira Barbosa / 5º ANO A / 2026 / junho`:

- professor e gestão devem receber o reader legado permitido enquanto não houver diário canônico `content_enabled`;
- os registros de 30/06, 29/06, 27/06 e 26/06 devem permanecer acessíveis;
- não deve ocorrer 409 `DVD_CONTENT_LEGACY_BLOCKED` nesse fallback;
- em uma turma com diário canônico de conteúdo efetivamente habilitado, o legado deve continuar bloqueado e o bridge deve permanecer em `content_entries`.

A issue #250 permanece aberta até merge, deploy controlado e smoke funcional.