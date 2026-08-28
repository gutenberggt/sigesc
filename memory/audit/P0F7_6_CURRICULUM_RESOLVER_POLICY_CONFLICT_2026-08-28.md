# P0-F7.6 — Curriculum Resolver Policy Conflict (READ-ONLY/OFFLINE)

## Objetivo

Verificar, antes de qualquer adjudicação ou executor, se a política central de resolução curricular do SIGESC pode favorecer evidência operacional de um componente que possua incompatibilidade ou escopo curricular ainda não resolvido por nível/série.

A fase nasce da combinação de duas evidências:

1. a P0-F7.3 apontou `IDENTITY_EVIDENCE_LEANS_TARGET` nos três casos divergentes de Geografia;
2. a P0-F7.5 demonstrou que o `target` não é curricularmente neutro: há `LEVEL_MISMATCH` no caso EJA e conflitos de escopo explícito de série nos outros casos.

## SSoT inspecionada

`backend/utils/curriculum_resolver.py`

O resolver declara a seguinte precedência operacional:

1. evidência acadêmica real (`grades` + `attendance`);
2. `class.course_ids`;
3. `teacher_assignments`;
4. fallback por `nivel_ensino` quando não houver evidência nem matriz;
5. deduplicação por nome usando `evidence_score`, `active`, `created_at` e `course_id`.

A P0-F7.6 não altera esse resolver. Ela apenas inspeciona estaticamente a política atual e cruza o resultado com a evidência já selada da P0-F7.5.

## Classificações de conflito

- `EVIDENCE_LEANS_TARGET_BUT_TARGET_CURRICULARLY_INCOMPATIBLE`: a evidência operacional favorece o target, mas o target falha no gate curricular de nível/série.
- `EVIDENCE_LEANS_TARGET_BUT_SOURCE_HAS_STRONGER_SERIES_SCOPE`: a evidência operacional favorece o target, enquanto o source possui cobertura explícita de série mais forte.
- `EVIDENCE_LEANS_TARGET_WITH_UNRESOLVED_TARGET_SERIES_SCOPE`: a evidência favorece o target, mas o escopo de série do target continua sujeito a revisão.
- `SOURCE_AND_TARGET_INCOMPATIBLE_ALTERNATE_LEVEL_CANDIDATE_EXISTS`: source e target são incompatíveis e existe terceiro candidato de mesmo nome e nível compatível.
- `SOURCE_AND_TARGET_CURRICULARLY_INCOMPATIBLE`: source e target são incompatíveis e não há terceiro candidato elegível identificado na evidência disponível.

Essas classificações representam **conflitos de política/evidência**, não decisões sobre qual componente manter.

## Gate de arquitetura

Se a inspeção confirmar simultaneamente:

- precedência `evidence > class.course_ids > teacher_assignments > fallback`;
- `_pick_winner()` baseado em sinais operacionais;
- ausência de gate explícito de `nivel_ensino`/série dentro da escolha final;
- ao menos um conflito significativo nos três casos;

então o relatório marca `requires_resolver_hardening_before_executor=true`.

Isso não significa que o resolver deva ser alterado automaticamente nesta fase. Significa apenas que qualquer executor de consolidação deve permanecer bloqueado até existir decisão arquitetural separada sobre a política curricular canônica.

## Segurança

- execução offline;
- entrada única: relatório privado P0-F7.5 + arquivo-fonte local do resolver;
- nenhum acesso MongoDB;
- nenhuma escrita em produção;
- nenhum estudante, nota ou frequência no relatório;
- nenhuma recomendação automática;
- nenhuma decisão automática de componente;
- nenhuma decisão automática de carga horária;
- nenhuma autorização de executor.

## Resultado esperado

A P0-F7.6 deve responder somente a esta pergunta:

> A política central atual de resolução curricular pode conflitar com os gates de compatibilidade curricular demonstrados pela P0-F7.5?

Se a resposta for positiva, a etapa posterior deverá tratar primeiro a **política canônica do resolver**, antes de adjudicar ou executar correções nos três vínculos de Geografia.
