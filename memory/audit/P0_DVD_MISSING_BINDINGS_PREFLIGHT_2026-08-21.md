# P0 — Preflight pós-cutover de vínculos DVD ausentes

Data: 2026-08-21

## Incidente sentinela

Professor com atuação em duas escolas tentou copiar conteúdo de um 5º Ano para outro 5º Ano. O fluxo canônico não encontrou `target_assignment_id` no destino e a tentativa de fallback para `learning_objects` foi corretamente bloqueada por `DVD_CONTENT_LEGACY_BLOCKED`.

A auditoria de produção confirmou, para o professor sentinela:

- duas lotações escolares ativas no `role_context`;
- 18 `teacher_assignments` ativos de 5º Ano, sendo 9 em cada escola;
- somente 8 `teacher_class_assignments` DVD, todos em uma das escolas;
- 10 gaps lógicos entre alocação pedagógica ativa e vínculo DVD: 1 em uma turma e 9 na outra.

## Decisão desta etapa

Nenhuma escrita será executada antes de explicar por que esses 10 vínculos ficaram fora da onda 38G.

Foi criado `backend/scripts/audit_dvd_missing_bindings_p0.py`, estritamente READ-ONLY, que:

1. restringe a análise a um `teacher_user_id` explícito;
2. reutiliza `collect_cutover_plan` e `collect_recovery`;
3. reutiliza `first_wave_blocker`, preservando os gates da 38E;
4. verifica reconstrução determinística de `weekly_slots`;
5. cruza os targets com DVDs já existentes;
6. identifica evidência de perfil `regular` em DVD vigente do mesmo professor e mesmo nível de ensino;
7. distingue:
   - `already_has_dvd`;
   - `missing_first_wave_ready_now`;
   - `missing_regular_sibling_evidence`;
   - `missing_blocked`.

## Invariantes

- Zero `insert`, `update`, `delete` ou `replace` no MongoDB.
- Nenhum vínculo é criado por inferência silenciosa.
- O preflight não altera o cutover selado da 38G.
- Uma futura remediação só poderá ser preparada depois de o preflight de produção demonstrar os bloqueadores de cada gap.
- O fluxo legado continua read-only quando DVD está ativo.

## Execução esperada em produção

```bash
cd /app/backend
python scripts/audit_dvd_missing_bindings_p0.py \
  --teacher-user-id 66d3ee7f-535a-4e2d-8088-5b2e611db640 \
  --academic-year 2026 \
  --reference-date 2026-08-21
```

A saída deve ser preservada como evidência antes de qualquer etapa de apply.

## Critério para avançar

Somente após classificar os 10 gaps:

- se os 10 forem reconstruíveis com evidência suficiente, criar remediação controlada com manifesto/hash, dry-run, confirmação explícita, pós-check e rollback;
- se houver bloqueados, tratar a causa objetiva (ex.: horário, identidade, compartilhamento, perfil) antes de criar qualquer `teacher_class_assignment`.
