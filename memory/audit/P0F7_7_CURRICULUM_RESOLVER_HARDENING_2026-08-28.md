# P0-F7.7 — Curriculum Resolver Hardening

## Objetivo

Corrigir na SSoT `backend/utils/curriculum_resolver.py` o gap confirmado pela P0-F7.6: componentes homônimos podiam ser deduplicados por evidência operacional sem que compatibilidade curricular explícita por nível/série participasse da escolha.

Esta fase altera **política de resolução**, não dados. Não remapeia componente, não modifica `teacher_assignments`, não consolida documentos e não executa escrita MongoDB.

## Política canônica

Para candidatos com o mesmo nome normalizado, a precedência passa a ser:

1. `curricular_rank`;
2. `evidence_score`;
3. `active=true`;
4. `created_at` mais recente;
5. `course_id` estável.

A evidência acadêmica continua sendo o primeiro sinal operacional, mas deixa de poder sobrepor um candidato de compatibilidade curricular comprovadamente mais forte.

## Tiers de compatibilidade

### Rank 3 — forte

- `EXPLICIT_SERIES_FULL_MATCH`;
- `PER_SERIES_MATRIX_FULL_MATCH`;
- `EXPLICIT_AND_MATRIX_FULL_MATCH`.

### Rank 2 — inconclusivo / revisão

- `UNKNOWN_CLASS_LEVEL`;
- `LEVEL_MATCH_SERIES_UNKNOWN`;
- `LEVEL_MATCH_NO_SERIES_SCOPE`;
- `PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW`;
- `PARTIAL_MATRIX_SERIES_MATCH_REQUIRES_REVIEW`;
- `SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW`.

### Rank 1 — incompatível

- `LEVEL_MISMATCH`;
- `NO_SERIES_MATCH`.

O resolver **não cria candidato novo** para resolver conflito. Somente classifica e ordena os candidatos que já chegaram pelo fluxo canônico: evidência, `class.course_ids`, `teacher_assignments` ou fallback previamente permitido.

## Comportamento nos três casos P0-F7.x

### Caso 1 — MULTI 8º E 9º

O source possui cobertura explícita completa de 8º/9º e recebe rank forte. O target possui matriz que cobre as séries, mas `grade_levels` explícito conflitante, permanecendo em review. O source deve prevalecer mesmo que o target possua maior evidência operacional.

### Caso 2 — EJA 3ª/4ª Etapa

Source e target `fundamental_anos_finais` recebem `LEVEL_MISMATCH`. A P0-F7.7 não injeta automaticamente o terceiro curso EJA no conjunto de candidatos. Se o curso `eja_final` vier a integrar legitimamente a matriz/vínculo após adjudicação, sua compatibilidade de nível passa a superar os candidatos incompatíveis.

### Caso 3 — MULTI 6º E 7º

Source parcial e target com conflito entre escopo explícito e matriz permanecem ambos em rank de revisão. Portanto a P0-F7.7 não fabrica uma decisão curricular. Dentro do mesmo rank, aplica-se a precedência histórica de evidência.

## Observabilidade

Em colisões homônimas com qualquer candidato abaixo de rank forte, o resolver emite `CURRICULAR_COMPATIBILITY_REVIEW_REQUIRED`, contendo nível/séries da turma, classificações dos candidatos, vencedor e razão de desempate.

`debug.final_resolution` passa a expor `curricular_rank` e `curricular_classification` para auditoria, sem alterar o contrato principal de `components`/`warnings`.

## Compatibilidade e segurança

- nenhuma escrita MongoDB;
- nenhum `--apply`;
- tenant scoping existente preservado;
- fallback histórico preservado;
- filtro de atendimento preservado;
- nenhuma busca automática por curso homônimo externo ao conjunto de candidatos;
- nenhum remapeamento automático;
- nenhum cálculo automático de carga horária semanal;
- nenhum executor de consolidação autorizado por esta fase.

## Gate de saída

A P0-F7.7 somente pode ser integrada se:

- testes focados cobrirem os três padrões P0-F7.x;
- CI geral estiver verde;
- regressões existentes estiverem verdes;
- o guard confirmar `curricular_rank` antes de `evidence_score` em `_pick_winner()`;
- o resolver permanecer read-only.

Após integração e deploy, os três vínculos de Geografia devem ser **reavaliados** sob a nova SSoT antes de qualquer executor de dados.
