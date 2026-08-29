# P0-F7.9C — Auditoria Geral Read-only de Compatibilidade Curricular

Data: 2026-08-29

## Objetivo

Medir a extensão do passivo histórico de `teacher_assignments` curricularmente incompatíveis em toda a mantenedora/ano letivo, sem corrigir dados e sem repetir o padrão de alto consumo observado nas etapas antigas.

## Estado de entrada

- P0-F7.9A confirmou incompatibilidades reais na turma forense de EJA.
- P0-F7.9B implantou contenção fail-closed na fronteira de escrita e foi validada em produção.
- Nenhum vínculo histórico foi alterado.

## Estratégia em duas fases

### P0-F7.9C0 — inventário de dimensionamento

Produção executa somente seis `countDocuments`, todos presos ao `mantenedora_id` e ao ano letivo derivados do snapshot P0-F7.9A já copiado para a estação local.

Contagens:

1. escolas do tenant;
2. turmas do ano;
3. turmas do ano sem nível explícito;
4. `teacher_assignments` do ano;
5. `teacher_assignments` ativos do ano;
6. componentes curriculares do tenant.

Nenhum documento acadêmico sensível é lido. Nenhum `find`, `aggregate`, `toArray` ou método de mutação é permitido nesta fase.

### P0-F7.9C1 — snapshot curricular da rede

Somente após o inventário local validado será escolhida uma das estratégias:

- `SINGLE_BOUNDED_TENANT_SNAPSHOT` quando classes <= 300, teacher_assignments <= 1000 e courses <= 500;
- `PAGED_BY_SCHOOL_SNAPSHOT` quando qualquer limite for excedido.

A estratégia é decidida offline; não há Python de auditoria em produção.

## Segurança

- produção: apenas `mongosh` read-only e bounded;
- nenhuma execução Python no backend de produção;
- sem estudantes, matrículas, notas ou frequência;
- sem `insert`, `update`, `delete`, `replace` ou `bulkWrite`;
- tenant fail-closed derivado do snapshot P0-F7.9A;
- nenhuma remediação de banco autorizada;
- MongoDB, host e containers não devem ser reiniciados para a auditoria.

## Saídas locais

Diretório recomendado: `C:\SIGESC\private\p0f7_9c\`

- `p0f7_9c-inventory.js` — coletor counts-only gerado localmente;
- `p0f7_9c-inventory.json` — resposta mínima copiada da produção;
- `p0f7_9c-inventory-report.json` — validação offline e escolha de estratégia.

## Gate para P0-F7.9C1

P0-F7.9C1 somente pode começar quando o relatório local retornar:

- `status=PASS`;
- `query_budget=6` e `query_calls=6` no inventário;
- cadeia SHA válida com o snapshot P0-F7.9A;
- tenant e ano sem drift;
- estratégia de coleta explicitamente escolhida.

Esta etapa não autoriza correção de `teacher_assignments` nem retomada do executor P0-F7.9.
