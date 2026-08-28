# P0-C Semantic V3 — `legacy_migration` sem professor

Data de referência: 2026-08-27 (America/Belem)  
Produção observada em UTC: 2026-08-28  
Modo: READ-ONLY

## 1. Evidência de produção

Após o merge do PR #185 e deploy do P0-C Semantic V2, o preflight READ-ONLY produziu:

- `RAW_ACTIVE = 1457`
- `LEGACY_MIGRATION_SYNTHETIC = 1085`
- `LEGACY_MIGRATION_DRIFT = 97`
- `OPERATIONAL_DVD = 275`
- todos os 97 supostos drifts com razão única `TEACHER_ID_MISSING`
- exemplos com id determinístico `legacy::{class_id}::{component_id}::none`
- `teacher_id = null`
- nenhuma escrita MongoDB executada

Manifesto V2 canônico:
`bab5efcdbe0cc62ba8c355753d58a738dc4dfa0ff939d83f84d3031e1aa1a82d`

Arquivo preservado no host:
`/root/sigesc-p0-audits/p0c_semantic_preflight_20260828T022146Z.json`

## 2. Causa da classificação incorreta

O classificador V2 marcou qualquer `source=legacy_migration` sem `teacher_id` como drift.

Entretanto, o writer oficial `legacy_schedule_bridge.build_assignments_from_legacy()` admite explicitamente slots de grade sem professor ativo. Nesse caso ele:

1. resolve `teacher_id = None`;
2. mantém o slot/component na materialização;
3. gera id determinístico `legacy::{class_id}::{course_id}::none`;
4. retorna o artefato sintético com `synthetic_validity=True`.

O serviço `grade_legacy_migration_service` reutiliza esse bridge e persiste o resultado com:

- `source=legacy_migration`;
- `migrated_from_legacy=True`;
- `synthetic_validity=True`;
- `created_by=legacy_migration`.

Logo, `teacher_id=None` + sufixo `::none`, quando todos os demais marcadores estão íntegros e `diary_settings.enabled != true`, é um estado histórico legítimo de grade sem professor, não drift e não propriedade pedagógica DVD.

## 3. Semântica V3

A partição passa a ser explícita em quatro buckets:

- `OPERATIONAL_DVD`: vínculos operacionais, `teacher_id` com semântica `users.id`;
- `LEGACY_MIGRATION_SYNTHETIC`: materialização legada com professor, `teacher_id` com semântica `staff.id`;
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED`: materialização legada sem professor, `teacher_id=None` + id terminado em `::none`;
- `LEGACY_MIGRATION_DRIFT`: violação real dos marcadores institucionais.

## 4. Fail-closed preservado

Um artefato sem professor continua sendo drift se qualquer condição obrigatória falhar, incluindo:

- id não determinístico `legacy::...`;
- `teacher_id=None` sem sufixo `::none`;
- professor presente com id terminado em `::none`;
- `migrated_from_legacy != True`;
- `synthetic_validity != True`;
- `created_by != legacy_migration`;
- `diary_settings.enabled == True`;
- `class_id` ausente;
- `component_id` ausente.

## 5. Expectativa correta para nova execução em produção

Se o estado do banco não tiver mudado desde o manifesto V2, a expectativa V3 é:

- `LEGACY_MIGRATION_SYNTHETIC = 1085`
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED = 97`
- `LEGACY_MIGRATION_DRIFT = 0`
- `OPERATIONAL_DVD = 275`
- soma = `1457`

Somente `OPERATIONAL_DVD` entra no preflight de identidade.

Para os 39 `teacher_id` operacionais distintos, a expectativa derivada do P0-C anterior é:

- `ALREADY_CANONICAL = 33`
- `READY_SAFE = 6`
- `USER_NOT_FOUND = 0`
- `proposed_staff_user_id_backfills = 6`

## 6. Segurança

Esta etapa não contém executor de remediação e não possui `--apply`.

Não alterar:

- os 1.085 sintéticos com professor;
- os 97 sintéticos sem professor;
- `teacher_class_assignments.teacher_id` históricos;
- `teacher_allocations`;
- notas, frequência ou conteúdo;
- AEE.

Qualquer futura escrita dos 6 `READY_SAFE` exigirá manifesto V3 de produção, executor separado, snapshot/rollback, CAS e autorização humana explícita.