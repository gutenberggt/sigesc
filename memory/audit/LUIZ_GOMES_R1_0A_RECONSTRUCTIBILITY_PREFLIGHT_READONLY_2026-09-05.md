# LUIZ-GOMES-R1.0A — Preflight read-only de reconstruibilidade

Data: 2026-09-05  
Tracking: #418  
Parent investigation: #357

## Objetivo

A R1.0A é a primeira subfase da **Reconstrução Controlada dos Lançamentos do Luiz Gomes dos Santos — Matemática — 8º ANO A / 9º ANO A**.

Ela não reconstrói, remapeia nem cria registros. Seu único objetivo é produzir uma matriz determinística, data a data, indicando qual nível de evidência ainda existe para fevereiro–abril/2026.

## Base diagnóstica

A cadeia F6→F6.4 já demonstrou que:

- 8º ANO A possui 33 datas de frequência de Matemática atribuíveis ao Luiz no período;
- 9º ANO A possui 34 datas de frequência de Matemática atribuíveis ao Luiz no período;
- não existem `learning_objects` nem `content_entries` de Matemática nas duas turmas no período, mesmo sem usar professor como filtro;
- os 111 registros de outros componentes do 8º A e os 98 do 9º A possuem autoria estrangeira e não podem ser convertidos em registros do Luiz;
- o baseline documental de 19/08 não contém Matemática recuperável do Luiz para esses alvos;
- o dump BSON de 18/08 não preserva schema estrutural suficiente para uma restauração segura.

Portanto, a R1 não pode começar com remapeamento. Primeiro é necessário saber se existe alguma evidência que permita reconstrução sem fabricação de conteúdo acadêmico.

## Classificação por data

Cada data encontrada nas fontes permitidas recebe exatamente uma classificação:

- `RECOVERABLE_EXACT`: fonte histórica íntegra com payload original suficiente para reconstrução exata;
- `RECOVERABLE_METADATA_ONLY`: metadados demonstram lançamento atribuível ao Luiz, mas o payload pedagógico original não está disponível;
- `ATTENDANCE_ANCHOR_ONLY`: há frequência de Matemática atribuível ao Luiz, porém nenhuma evidência de conteúdo;
- `CONFLICTING_EVIDENCE`: há evidência concorrente/estrangeira; fail-closed;
- `NO_EVIDENCE`: nenhuma base suficiente para reconstrução.

### Restrição deliberada da R1.0A

A R1.0A usa somente fontes atuais metadata-only e, por contrato, **não pode emitir `RECOVERABLE_EXACT`**. Ela não lê payload histórico e não restaura backups/dumps.

O valor desta subfase é separar com precisão:

1. datas em que existe apenas âncora de frequência;
2. datas com metadados adicionais atribuíveis ao Luiz;
3. conflitos que devem permanecer intocados;
4. ausência completa de evidência.

Se nenhum dado além da frequência sobreviver, a conclusão correta não será “recriar os conteúdos”, mas sim documentar que a reconstrução automática não é tecnicamente defensável.

## Fontes lidas

- `attendance`: somente turma, componente, data e metadados de autoria/assignment; `records` não é projetado;
- `learning_objects` e `content_entries`: somente identidade, data, status e autoria; payload pedagógico não é projetado;
- `audit_logs`: somente identidade, data, ação e autoria; sem valores pedagógicos;
- `diary_snapshots`: somente metadados top-level; nenhum conteúdo interno é projetado;
- `users`, `staff`, `schools`, `classes`, `courses`, `teacher_assignments` e `teacher_class_assignments`: somente para resolução fail-closed de contexto e autoria.

## Regras fail-closed

- qualquer autoria estrangeira na evidência de uma data => `CONFLICTING_EVIDENCE`;
- snapshot sem autoria do Luiz não eleva a data a recuperável;
- período de snapshot não é expandido artificialmente para datas individuais;
- ausência de payload preservado impede `RECOVERABLE_EXACT`;
- nenhuma inferência pedagógica é feita a partir da frequência;
- os 111/98 registros de outros atores não são reutilizados.

## Boundary

- Mongo somente leitura;
- nenhuma escrita em produção;
- nenhuma criação/alteração de `learning_objects`, `content_entries` ou frequência;
- `attendance.records` não lido;
- estudantes, matrículas e notas não lidos;
- nenhum plaintext pedagógico lido ou emitido;
- nenhum ID técnico bruto emitido;
- nenhum restore histórico nesta subfase;
- nenhum deploy funcional.

## Gate

A R1.1, que seria o plano de reconstrução efetiva, permanece bloqueada. Pela política da #418, ela só pode ser aberta se uma subfase posterior do R1.0 demonstrar ao menos um `RECOVERABLE_EXACT` com fonte histórica íntegra.

A eventual execução da R1.0A em produção exige:

- código previamente integrado e revisado;
- issue owner-only com título e contrato exatos;
- SHA exato de `main` e `production`;
- environment `production`;
- execução somente read-only;
- resultado publicado em #418.
