# LUIZ-GOMES-F6.3c.1 — Baseline documental de 19/08/2026

**Data:** 2026-09-05  
**Tracking:** #357  
**Escopo:** Luiz Gomes dos Santos — Matemática — 8º ANO A e 9º ANO A — fevereiro a abril/2026

## Motivo

A primeira execução F6.3c terminou corretamente como `INCONCLUSIVE / BACKUP_FORENSICS_PROBE_ERROR`, antes de qualquer restore, porque o runner assumiu `daily/weekly/monthly` diretamente sob `/root/sigesc-backups` e encontrou `F63C_TIER_MISSING:daily`.

Esse resultado não contém evidência negativa sobre os registros do Luiz.

A documentação histórica do incidente DVD registra uma fonte mais forte e com identidade completa:

```text
/root/sigesc-backups/database/sigesc-full-20260819T140519Z.archive.gz
SHA-256=f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a
database=sigesc
image=mongo:7
```

O backup foi criado em produção em 2026-08-19 antes da implementação corretiva do bridge legado DVD.

## Estratégia

Antes de tentar reconstruir o layout completo dos backups gerenciados, F6.3c.1 restaura somente esse baseline documentado e verifica se, naquela fotografia de 19/08, ainda existiam registros de fevereiro–abril atribuíveis ao Luiz nas turmas 8º ANO A e 9º ANO A.

Se houver `Luiz + Matemática + payload_present`, isso estabelece prova histórica forte de que os lançamentos existiam em 19/08 e fornece uma fonte concreta para eventual recuperação posterior. Não implica restauração automática em produção.

## Proveniência fail-closed

A execução exige simultaneamente:

1. arquivo no caminho documentado;
2. `gzip -t` PASS;
3. SHA-256 exatamente igual ao valor documentado;
4. imagem Mongo do runtime de produção igual a `mongo:7`.

Qualquer divergência resulta em `INCONCLUSIVE / DOCUMENTED_BASELINE_PROBE_ERROR`.

## Isolamento

- Mongo temporário descartável;
- `--network none`;
- zero portas publicadas;
- `/root/sigesc-backups` montado read-only;
- `mongorestore` nunca executado no container Mongo de produção;
- cleanup via `trap`;
- produção não recebe escrita.

## Coleções restauradas

Somente:

- `users`
- `staff`
- `schools`
- `classes`
- `courses`
- `teacher_assignments`
- `teacher_class_assignments`
- `learning_objects`
- `content_entries`
- `audit_logs`

Estudantes, matrículas, frequência e notas permanecem excluídos.

## Conteúdo pedagógico

O probe reutilizado da F6.3c não emite `content`, `methodology`, `observations` ou outros textos pedagógicos. O Mongo temporário calcula somente `payload_present` booleano. Nenhum ID técnico é emitido.

## Taxonomia agregada

- `DOCUMENTED_BASELINE_RECOVERY_SOURCE_CONFIRMED`
- `DOCUMENTED_BASELINE_LUIZ_MATH_ROWS_WITHOUT_PAYLOAD`
- `DOCUMENTED_BASELINE_LUIZ_NONMATH_ROWS_PRESENT`
- `DOCUMENTED_BASELINE_UNATTRIBUTED_MATH_CONTENT_CANDIDATES`
- `DOCUMENTED_BASELINE_NO_RECOVERABLE_LUIZ_MATH`
- `INCONCLUSIVE / DOCUMENTED_BASELINE_PROBE_ERROR`

## Governança

Runtime somente após merge e gate owner-only com SHAs exatos de `main` e `production`. Nenhum deploy ou mutação de produção faz parte desta fase.
