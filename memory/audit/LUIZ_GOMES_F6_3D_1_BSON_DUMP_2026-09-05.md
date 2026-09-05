# LUIZ-GOMES-F6.3d.1 — dump BSON ad hoc de 18/08/2026

Data: 2026-09-05
Tracking: #357
Status: probe preparado; runtime somente após PR/CI/merge e gate owner-only exact-SHA.

## Evidência de origem

A F6.3d encontrou 31 arquivos `.bson` fisicamente únicos com data efetiva de 18/08/2026 fora de `/root/sigesc-backups`, todos sob a raiz operacional `root`. Nenhum conteúdo foi lido nessa descoberta.

A data é relevante porque antecede em um dia o baseline integral documentado de 19/08/2026, no qual 8º ANO A e 9º ANO A já não continham linhas recuperáveis de Luiz Gomes / Matemática.

## Objetivo

Determinar se os 31 BSON formam um dump Mongo coerente e, somente se houver um único grupo inequívoco com as coleções mínimas necessárias, restaurar uma allowlist em Mongo temporário isolado e executar o probe metadata-only já homologado da F6.3c.

## Seleção fail-closed

O runner:

1. procura `.bson` somente em `/root`, `/opt`, `/srv`, `/var/backups`, com `find -xdev -maxdepth 8`;
2. exclui `/root/sigesc-backups` e descendentes;
3. considera somente arquivos cujo `mtime` UTC seja 18/08/2026;
4. agrupa por diretório-pai sem emitir o caminho;
5. exige arquivos não vazios para `users`, `schools`, `classes`, `courses` e `learning_objects`;
6. exige spread de mtime do grupo <= 600 segundos;
7. exige exatamente um grupo elegível;
8. emite apenas fingerprint do diretório, contagem BSON, spread, proveniência estrutural e nomes das coleções permitidas.

Mais de um grupo, nenhum grupo, arquivo obrigatório ausente ou incoerência temporal => aborta antes de qualquer restore.

## Restore isolado

Se e somente se a seleção for inequívoca:

- imagem Mongo deve ser a mesma `mongo:7` usada pela produção, resolvida via identidade do container;
- novo container temporário com `--network none` e zero portas;
- diretório-fonte montado read-only;
- coleções obrigatórias: `users`, `schools`, `classes`, `courses`, `learning_objects`;
- opcionais quando presentes: `staff`, `teacher_assignments`, `teacher_class_assignments`, `content_entries`, `audit_logs`;
- `students`, matrículas, frequência, notas e `attendance_documentary` não entram na allowlist;
- `mongorestore` é executado somente contra o Mongo temporário;
- o probe não emite conteúdo/metodologia/observações; calcula apenas presença booleana de payload;
- cleanup por `trap` e remoção do container ao final.

## Proveniência

Esses arquivos não possuem sidecars SHA/metadata conhecidos. Portanto a proveniência é deliberadamente classificada como `structural_only_ad_hoc_bson_dump`, e não como backup institucional autenticado. A força probatória vem da coerência estrutural, data física e conteúdo metadata-only observado após restore isolado; nenhuma conclusão deve elevar essa proveniência além disso.

## Taxonomia

- `COMPLETED / BSON_20260818_RECOVERY_SOURCE_CONFIRMED`: há Luiz + Matemática + payload no período alvo;
- `COMPLETED / BSON_20260818_LUIZ_MATH_ROWS_WITHOUT_PAYLOAD`;
- `COMPLETED / BSON_20260818_LUIZ_NONMATH_ROWS_PRESENT`;
- `COMPLETED / BSON_20260818_UNATTRIBUTED_MATH_CONTENT_CANDIDATES`;
- `COMPLETED / BSON_20260818_NO_RECOVERABLE_LUIZ_MATH`;
- `INCONCLUSIVE / BSON_DUMP_PROBE_ERROR`: seleção, restore, probe ou boundary incompleto.

Nenhuma classificação autoriza escrita/restauração em produção.