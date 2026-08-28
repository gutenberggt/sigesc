# P0-C — Separação Semântica `legacy_migration` x DVD Operacional

Data de referência pedagógica: **2026-08-27**  
Estado: **CORREÇÃO DE AUDITORIA/PREFLIGHT — READ-ONLY**

## 1. Evidências de produção

### P0-B global

- 1.457 `teacher_class_assignments` vigentes;
- 1.182 resoluções de identidade inicialmente classificadas como `UNRESOLVED`;
- evidência P0-B SHA-256:
  `519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be`.

### P0-C preflight v1

- 173 `teacher_id` distintos;
- 39 existem em `users`;
- 134 foram classificados como `USER_NOT_FOUND`;
- 33 `ALREADY_CANONICAL`;
- 6 `READY_SAFE`;
- 134 `NEEDS_REVIEW` por usuário ausente.

Manifesto preservado no host:

`/root/sigesc-p0-audits/p0c_teacher_identity_20260828T015616Z.json`

SHA-256 canônico:

`186359a478c3bf968265adbf3bdb6f0c545598363fe73909d3ce8f40ca2e6db6`

### P0-C.1B dual identity

A auditoria adicional confirmou:

- os 134 IDs ausentes de `users` existem todos como `staff.id`;
- esses 134 IDs correspondem a 1.085 documentos;
- os 1.085 documentos têm `source=legacy_migration`;
- todos permanecem no mesmo tenant do respectivo staff;
- 122 staff possuem `user_id` apontando para usuário existente;
- 12 staff possuem `user_id` vazio;
- proveniência `cutover_provenance` ausente em todos, compatível com a origem diferente do cutover DVD.

## 2. Causa raiz semântica

O writer oficial `grade_legacy_migration_service.py` reutiliza
`legacy_schedule_bridge.build_assignments_from_legacy`.

O bridge produz o shape de `teacher_class_assignments` usando:

`teacher_id = teacher_assignments.staff_id`

A migração persiste esses documentos com marcadores:

- `source=legacy_migration`;
- `migrated_from_legacy=True`;
- `synthetic_validity=True`;
- `created_by=legacy_migration`;
- ID determinístico `legacy::{class}::{course}::{teacher}`.

Esses registros são materializações sintéticas da grade legada. Eles não
representam propriedade pedagógica DVD.

O próprio preflight `prepare_dvd_second_wave_2d_j_migration_aware.py` já havia
formalizado esta distinção e exige `diary_settings.enabled != true` para aceitar
um documento `legacy_migration` como artefato sintético válido.

## 3. Impacto operacional

O acesso operacional do professor ao DVD usa `current_user.id` e exige
`diary_settings.enabled=True`.

O autorizador canônico `diary_assignment_access.py` também rejeita qualquer
assignment sem `enabled=true` antes de avaliar propriedade pedagógica.

Conclusão: os 1.085 artefatos `legacy_migration` contaminaram o P0-B/P0-C v1,
mas não constituem, por si, perda operacional de Diário enquanto preservarem os
marcadores sintéticos oficiais.

A população operacional esperada após separação é:

- 1.457 total vigente
- 1.085 `legacy_migration` sintéticos
- **372 DVD operacionais**
- **39 usuários docentes operacionais**

A expectativa de decisão P0-C v2 é:

- 33 `ALREADY_CANONICAL`;
- 6 `READY_SAFE`;
- 0 `USER_NOT_FOUND`;

Essa expectativa deve ser confirmada em produção; não é autorização de escrita.

## 4. Regra SSoT implementada

Arquivo:

`backend/services/teacher_class_assignment_semantics.py`

Classificações:

- `OPERATIONAL_DVD`;
- `LEGACY_MIGRATION_SYNTHETIC`;
- `LEGACY_MIGRATION_DRIFT`.

Um `source=legacy_migration` só é reconhecido como sintético quando preserva:

1. ID começando por `legacy::`;
2. `migrated_from_legacy=True`;
3. `synthetic_validity=True`;
4. `created_by=legacy_migration`;
5. `diary_settings.enabled` diferente de `True`;
6. `teacher_id`, `class_id` e `component_id` presentes.

Qualquer divergência vira `LEGACY_MIGRATION_DRIFT`.

## 5. Auditor global semantic-aware

Arquivo:

`backend/scripts/audit_teacher_binding_integrity_p0_semantic.py`

Características:

- READ-ONLY;
- preserva a auditoria de referências a componentes em toda a collection;
- exclui `legacy_migration` apenas do scan de identidade/vínculo;
- expõe a partição semântica e migration runs;
- `LEGACY_MIGRATION_DRIFT > 0` fecha o gate de remediação.

## 6. P0-C preflight semantic-aware v2

Arquivo:

`backend/scripts/preflight_teacher_identity_remediation_p0c_semantic.py`

Características:

- READ-ONLY;
- sem `--apply`;
- reutiliza as regras conservadoras do P0-C v1;
- opera somente sobre `OPERATIONAL_DVD`;
- se houver drift sintético, retorna estado bloqueado e zero propostas;
- mantém manifesto determinístico e SHA-256.

## 7. O que NÃO deve ser feito

Não normalizar em massa os 1.085 documentos `legacy_migration` de
`teacher_id=staff.id` para `users.id`.

Tal alteração destruiria a semântica/proveniência da materialização da grade e
misturaria dois contratos diferentes.

Também não criar `teacher_allocations`, não inferir por nome e não alterar AEE.

## 8. Gate para futura escrita

Somente depois de executar o auditor semantic-aware e o preflight v2 em produção,
com `legacy_migration_drift=0`, será possível congelar um manifesto dos
`READY_SAFE` operacionais.

Qualquer executor futuro deverá ser separado, idempotente, com CAS, snapshot,
rollback, auditoria e autorização humana explícita antes da escrita em produção.
