# LUIZ-GOMES-F6.3c.2 — Inventário read-only de backups

**Data:** 2026-09-05  
**Tracking:** #357

## Contexto

A F6.3c.1 restaurou com sucesso o baseline documental de 19/08/2026 e não encontrou, para 8º ANO A e 9º ANO A, registros de Matemática atribuíveis ao Luiz, registros do Luiz sob outro componente ou candidatos de Matemática sem autoria.

Isso prova que os registros investigados já não estavam presentes naquela fotografia de 19/08, mas não prova que nunca tenham existido antes.

## Objetivo

Descobrir, sem acessar MongoDB e sem restaurar qualquer archive, se o host retém algum `*.archive.gz` com data efetiva anterior a 19/08/2026 que possa servir como fonte forense mais antiga.

## Boundary

- somente leitura do filesystem;
- busca limitada a `/root/sigesc-backups`, mesmo filesystem (`-xdev`) e profundidade máxima 6;
- identidade física por `device:inode`, evitando duplicidade de hard links;
- limite de segurança de 100 archives físicos;
- nenhum `mongosh`, `mongorestore`, `docker run` ou `docker exec`;
- nenhum caminho completo ou nome de archive emitido;
- somente metadados sanitizados: data inferida do nome, mtime, tamanho, classe de origem e presença de sidecars SHA/metadata.

## Interpretação

Se houver archive com data efetiva anterior a 19/08, ele será apenas candidato. Qualquer restauração continuará exigindo uma fase separada com validação de integridade/proveniência e Mongo temporário isolado.

Se não houver candidato anterior, a evidência local conhecida ficará limitada ao baseline de 19/08 e aos pontos posteriores; isso ainda não autoriza concluir que o professor nunca lançou conteúdos em fevereiro–abril.

## Taxonomia

- `COMPLETED / BACKUP_INVENTORY_COMPLETED`
- `INCONCLUSIVE / BACKUP_INVENTORY_PROBE_ERROR`

Falha operacional nunca é convertida em ausência de backup.
