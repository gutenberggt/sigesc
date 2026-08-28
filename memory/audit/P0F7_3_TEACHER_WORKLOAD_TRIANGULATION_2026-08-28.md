# P0-F7.3 — Triangulação read-only da carga docente

Data: 2026-08-28  
Escopo: blocker de `teacher_assignments` remanescente do grupo **Geografia**.

## Contexto

A P0-F7.2 documentou exatamente três pares divergentes do mesmo professor, escola e ano letivo. Em todos os casos, o único campo divergente é `carga_horaria_semanal`: `2` no source e `3` no target. A P0-F7.2 não recomenda nem escolhe um lado.

## Objetivo

Cruzar os três casos com evidências já existentes no SIGESC, sem criar uma nova regra de negócio:

1. snapshot vivo das duas `teacher_assignments`;
2. `class.course_ids` como matriz explícita da turma;
3. `class_schedules.schedule_slots`;
4. metadados dos dois `courses`, inclusive `workload` anual e `carga_horaria_por_serie`;
5. contagens de documentos de `grades`;
6. contagens agregadas de documentos/registros de `attendance`.

A etapa pode indicar para qual **identidade de componente** a evidência externa tende, mas não converte automaticamente carga anual em semanal e não transforma número de slots em horas-relógio.

## Invariantes

- READ-ONLY.
- Sem `--apply`.
- Sem `insert`, `update`, `replace`, `delete`, `bulk_write` ou `find_one_and_*`.
- Fail-closed se o tenant da turma estiver ausente.
- Toda leitura operacional dos pares usa `mantenedora_id`.
- Falha se qualquer assignment tiver drift em relação ao snapshot P0-F7.2.
- Não imprime identificadores de estudantes, notas ou valores de frequência.
- Relatório privado em modo `0600`.
- Nenhuma recomendação automática de `2h` ou `3h`.
- Não autoriza executor.

## Classificação de evidência de identidade

São observados sinais independentes:

- matriz da turma;
- slots do horário;
- documentos de notas;
- documentos de frequência;
- quantidade agregada de registros de frequência.

A classificação pode ser:

- `IDENTITY_EVIDENCE_LEANS_SOURCE`;
- `IDENTITY_EVIDENCE_LEANS_TARGET`;
- `MIXED_IDENTITY_EVIDENCE_REQUIRES_REVIEW`;
- `LIMITED_IDENTITY_EVIDENCE_SOURCE`;
- `LIMITED_IDENTITY_EVIDENCE_TARGET`;
- `SHARED_IDENTITY_EVIDENCE_REQUIRES_REVIEW`;
- `NO_EXTERNAL_IDENTITY_EVIDENCE`.

Mesmo quando a identidade tende a um lado, `automatic_workload_decision=false`.

## Execução prevista em produção

```bash
python /app/scripts/audit_p0f7_3_teacher_workload_triangulation.py \
  --forensic /tmp/p0f7_2-private-report.json \
  --json /tmp/p0f7_3-private-report.json
```

O relatório P0-F7.2 é privado e deve permanecer fora de GitHub/chat. O stdout P0-F7.3 é deliberadamente agregado e não contém dados de estudantes.

## Próximo gate

Somente depois da triangulação será decidido se há evidência canônica suficiente para uma adjudicação determinística ou se os três valores exigem decisão humana/política explícita. Nenhuma escrita em produção faz parte desta fase.
