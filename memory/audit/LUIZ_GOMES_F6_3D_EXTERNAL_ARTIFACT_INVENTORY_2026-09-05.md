# LUIZ-GOMES-F6.3d — inventário de artefatos históricos fora do backup canônico

Data: 2026-09-05
Tracking: #357
Status: probe preparado; execução somente após PR/CI/merge e gate owner-only exact-SHA.

## Contexto

A F6.3c.1 validou o backup integral documentado de 19/08/2026 e não encontrou linhas recuperáveis de Luiz Gomes / Matemática para 8º ANO A e 9º ANO A. A F6.3c.2 inventariou 16 archives físicos únicos em `/root/sigesc-backups`, com janela efetiva de 19/08/2026 a 05/09/2026 e zero candidatos anteriores a 19/08.

`audit_logs` e `diary_snapshots` também não forneceram prova histórica conclusiva do período fevereiro–abril/2026.

## Objetivo F6.3d

Descobrir, sem abrir arquivos, se existe no host algum dump/archive/tarball ad hoc fora da árvore canônica que possa representar um ponto histórico anterior a 19/08/2026.

## Boundary

- roots explícitos: `/root`, `/opt`, `/srv`, `/var/backups`;
- mesma filesystem only (`find -xdev`) e profundidade máxima 8;
- `/root/sigesc-backups` e descendentes excluídos;
- somente padrões de artefato compatíveis com dump/backup: `.archive.gz`, `.bson[.gz]`, `.dump[.gz]`, ou tar/zip nomeado `sigesc`, `mongo` ou `backup`;
- deduplicação física por `device:inode`;
- limite de segurança: 200 artefatos físicos;
- apenas `find`, `stat`, testes de existência de sidecars e fingerprint SHA-256 do texto do caminho;
- nenhum conteúdo de arquivo lido; nenhum `gzip -t`; nenhum hash do conteúdo;
- nenhum Mongo, Docker, restore, deploy, backfill, remapeamento ou mutação;
- caminhos e basenames não são emitidos; apenas fingerprint, classe da raiz, tipo, datas, tamanho e presença de sidecars.

## Taxonomia

- `COMPLETED / HISTORICAL_ARTIFACT_CANDIDATES_FOUND`: existe ao menos um candidato com data efetiva anterior a 19/08/2026;
- `COMPLETED / NO_PRE_0819_EXTERNAL_ARTIFACT_CANDIDATE`: inventário concluiu sem candidato anterior;
- `INCONCLUSIVE / EXTERNAL_ARTIFACT_INVENTORY_PROBE_ERROR`: falha operacional ou boundary incompleto.

Uma eventual descoberta não autoriza restore. O próximo passo, se houver candidato, deve selecionar por fingerprint e validar/restaurar somente em ambiente temporário isolado, mediante novo gate.