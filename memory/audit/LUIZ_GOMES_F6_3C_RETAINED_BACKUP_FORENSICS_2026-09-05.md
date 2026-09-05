# LUIZ-GOMES-F6.3c — Forense dos backups Mongo retidos

**Data:** 2026-09-05  
**Tracking:** #357  
**Escopo:** Luiz Gomes dos Santos — Matemática — 8º ANO A e 9º ANO A — fevereiro a abril/2026  
**Natureza:** diagnóstico forense; nenhum deploy e nenhuma mutação do banco de produção

## Contexto

A F6.3 consultou `audit_logs` e encontrou zero eventos de conteúdo do Luiz para os dois alvos. Esse resultado não é prova de ausência histórica porque o caminho legado `learning_objects` não possuía garantia de auditoria equivalente ao `content_entries` canônico.

A F6.3b consultou `diary_snapshots` e encontrou zero snapshots cobrindo fevereiro–abril/2026 para 8º ANO A e 9º ANO A. Ausência de snapshot também não prova ausência histórica.

A próxima fonte forense é o conjunto de backups Mongo locais retidos e já homologados para restore isolado. A infraestrutura de backup começou a produzir pontos observados em agosto/2026; portanto a F6.3c pode provar se registros referentes a fevereiro–abril ainda existiam em algum ponto retido, mas não cria uma fotografia retroativa de fevereiro.

## Objetivo

Examinar todos os arquivos de backup **fisicamente únicos** ainda retidos nos tiers `daily`, `weekly` e `monthly`, procurando evidência recuperável de conteúdo de Matemática atribuível ao Luiz nas turmas 8º ANO A e 9º ANO A no intervalo `2026-02-01 <= date < 2026-05-01`.

## Deduplicação física

A política de promoção usa hard links. Por isso, a F6.3c não usa apenas nome de arquivo ou SHA como identidade de ponto físico. Cada archive é identificado por `device:inode` (`stat -Lc '%d:%i'`).

- hard links do mesmo archive são examinados uma única vez;
- SHA-256 continua sendo validado para integridade;
- o artifact expõe somente fingerprint curta do SHA, nunca caminho de arquivo ou inode;
- dois arquivos fisicamente distintos com bytes idênticos permanecem pontos separados.

## Proveniência e integridade

Antes de qualquer restore, cada archive precisa passar, fail-closed, por:

1. sidecar `*.sha256` presente;
2. `gzip -t`;
3. SHA calculado igual ao sidecar;
4. `*.metadata.txt` presente;
5. metadata contendo o nome do Mongo de produção identificado pelo runtime;
6. metadata contendo a imagem Mongo do runtime de produção.

Qualquer divergência resulta em erro de probe, nunca em conclusão negativa sobre os dados.

## Restore isolado

Cada ponto é restaurado em container Mongo temporário com:

- `--network none`;
- nenhuma porta publicada;
- diretório `/root/sigesc-backups` montado read-only em `/backup`;
- probe JS montado read-only;
- cleanup via `trap`, inclusive em falha;
- `mongorestore` executado exclusivamente contra o container temporário.

Namespaces permitidos:

- `sigesc.users`
- `sigesc.staff`
- `sigesc.schools`
- `sigesc.classes`
- `sigesc.courses`
- `sigesc.teacher_assignments`
- `sigesc.teacher_class_assignments`
- `sigesc.learning_objects`
- `sigesc.content_entries`
- `sigesc.audit_logs`

Namespaces explicitamente excluídos incluem estudantes, matrículas, frequência e notas.

## Boundary do conteúdo pedagógico

O probe não projeta nem emite `content`, `methodology`, `observations` ou `resources`.

Para distinguir um mero documento vazio de uma fonte realmente recuperável, o Mongo temporário calcula somente um booleano `payload_present` por documento, usando a existência de valor não vazio nos campos pedagógicos relevantes. O plaintext permanece dentro do Mongo temporário e não é impresso, persistido no artifact ou enviado ao GitHub.

Também não são emitidos IDs técnicos.

## Taxonomia por turma/ponto

- `RECOVERABLE_LUIZ_MATH_CONTENT_CONFIRMED`: há documento Luiz + Matemática com payload pedagógico presente.
- `LUIZ_MATH_ROWS_PRESENT_WITHOUT_PAYLOAD`: há linha Luiz + Matemática, porém sem payload detectável.
- `LUIZ_TARGET_ROWS_PRESENT_UNDER_NONMATH_COMPONENT`: há registros atribuíveis ao Luiz na turma/período, mas vinculados a componente cujo nome no backup não é Matemática.
- `UNATTRIBUTED_MATH_CONTENT_CANDIDATES_PRESENT`: há Matemática com payload, mas sem metadado de ator suficiente para atribuir ao Luiz.
- `UNATTRIBUTED_MATH_ROWS_WITHOUT_PAYLOAD`: há linhas de Matemática sem ator e sem payload.
- `NO_LUIZ_MATH_ROWS_IN_BACKUP`: nenhuma das evidências anteriores foi encontrada naquele alvo/ponto.

## Taxonomia agregada

Se a varredura concluir tecnicamente:

- `HISTORICAL_BACKUP_RECOVERY_SOURCE_CONFIRMED`
- `HISTORICAL_BACKUP_LUIZ_MATH_ROWS_WITHOUT_PAYLOAD`
- `HISTORICAL_BACKUP_LUIZ_NONMATH_ROWS_PRESENT`
- `HISTORICAL_BACKUP_UNATTRIBUTED_MATH_CONTENT_CANDIDATES`
- `HISTORICAL_BACKUP_UNATTRIBUTED_MATH_ROWS_WITHOUT_PAYLOAD`
- `NO_RECOVERABLE_LUIZ_MATH_IN_ALL_RETAINED_BACKUPS`

Se qualquer condição operacional impedir uma prova completa, a classificação obrigatória é:

- `INCONCLUSIVE / BACKUP_FORENSICS_PROBE_ERROR`

Probe error nunca pode ser convertido em ausência de dados.

## Gate e governança

O runtime de produção só executa quando um issue criado pelo owner contém exatamente:

```text
LUIZ_GOMES_F6_3C_BACKUP_FORENSICS=AUTHORIZED
CONFIRMATION=RESTORE_RETAINED_BACKUPS_IN_ISOLATED_TEMP_MONGO
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<40-hex-main>
EXPECTED_PRODUCTION_SHA=<40-hex-production>
```

O workflow valida `main`, `production` e o estado aberto do tracking #357 antes de acessar o host.

## Não objetivos

Esta fase não:

- restaura documentos na produção;
- altera `learning_objects` ou `content_entries` vivos;
- remapeia componente, turma ou professor;
- executa backfill;
- faz deploy;
- lê frequência individual;
- lê estudantes ou notas;
- publica texto pedagógico.

Se uma fonte recuperável for confirmada, qualquer recuperação para produção será uma etapa posterior, separada e cirúrgica, com prova de identidade, plano de rollback e autorização própria.
