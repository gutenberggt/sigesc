# Assessment Policy v1 — Sprint 008 — Fase 0
## Operational Binding + Publication Readiness — Architecture Contract

**Status:** arquitetura aprovada; nenhum código funcional pertence a esta fase.

## 1. Objetivo

Formalizar a separação entre:

1. `AssessmentPolicy`: regra pedagógica/normativa versionada;
2. `OperationalBinding`: adaptação técnica entre o schema operacional e uma versão exata da policy;
3. `PilotEvidence`: evidência imutável de um dry-run executado com policy + binding específicos;
4. `ReadinessReport`: decisão derivada de prontidão, sem publicar ou ativar regra.

## 2. Decisão central

`AssessmentPolicy` permanece a SSoT normativa em `assessment_policies`.

O mapping operacional **não integra** a policy e **não integra** o `rule_hash`.

O `OperationalBinding` deve carregar, de forma explícita:

- `mantenedora_id`;
- `policy_id`;
- `policy_key`;
- `policy_version`;
- `policy_rule_hash`;
- `binding_version`;
- `source_schema`;
- `period_field_map`;
- `recovery_field_map`;
- `mapping_hash`.

O `mapping_hash` deve reutilizar a canonicalização já existente do Shadow v1.

## 3. Lifecycle conceitual do binding

`DRAFT -> VALIDATED -> SUPERSEDED`

- `DRAFT`: mutável com optimistic concurrency;
- `VALIDATED`: imutável;
- `SUPERSEDED`: histórico e imutável.

O binding não possui status `PUBLISHED`. Quem é publicada é a policy.

## 4. Staleness

Um binding fica stale quando o conteúdo canônico da policy deixa de produzir o
`policy_rule_hash` ao qual ele foi vinculado.

Nenhuma atualização em cascata será feita.

Mudança de mapping produz novo `mapping_hash`; evidência antiga não pode ser
reutilizada para outro hash.

## 5. Evidência operacional

Qualquer futura `PilotEvidence` deve estar vinculada, no mínimo, ao par:

`policy_rule_hash + mapping_hash`

além das identidades de tenant, policy e binding.

`match_rate` é evidência técnica e não cria, sozinho, um threshold de aprovação.

## 6. Readiness

Estados conceituais:

- `BLOCKED`;
- `REVIEW_REQUIRED`;
- `READY`.

`READY != PUBLISHED`
`READY != ACTIVE`
`READY != CUTOVER`

Readiness deve ser derivado e fail-closed.

## 7. Bloqueios institucionais preservados

Nenhuma inferência é permitida para:

1. mapping operacional de recuperação;
2. `only_if_improves`;
3. base da frequência mínima (`global`, `stage` ou `component`);
4. fonte normativa/institucional.

## 8. Limites

A Sprint 008 não autoriza, por consequência desta arquitetura:

- endpoint de publish;
- endpoint de cutover;
- UI de ativação;
- alteração do `grade_calculator.py`;
- escrita em `grades`;
- backfill;
- alteração de frequência, matrícula, dependência ou promoção;
- substituição do runtime oficial.

## 9. Gate para Fase 1

A Fase 1 pode implementar apenas contratos puros, canonicalização,
validação sem IO, testes e guard de escopo do `OperationalBinding`.
