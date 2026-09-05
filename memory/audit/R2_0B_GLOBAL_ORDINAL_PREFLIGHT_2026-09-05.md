# R2.0b — Pareamento Ordinal Global — 2026-09-05

## Contexto

A R2.0a confirmou conteúdo institucional nas turmas-espelho 8º B e 9º B e bindings legados resolvidos nos destinos 8º A e 9º A. As diferenças mensais foram tratadas pelo usuário como deslocamento de calendário entre turmas paralelas.

## Decisão administrativa

O pareamento passa a usar a estratégia `GLOBAL_ORDINAL_CONTINUOUS_PERIOD`: todos os conteúdos-fonte de fevereiro a abril são ordenados cronologicamente numa sequência única e associados, na mesma ordem, às datas reais de frequência do professor na turma-alvo. A mudança de mês não reinicia o ordinal.

## Restrições

- nenhuma repetição, descarte, fusão ou reordenação automática de conteúdo;
- igualdade mensal deixa de ser gate;
- igualdade da quantidade total do período permanece gate para `READY_TO_APPLY`;
- se os totais divergirem, o preflight pode mostrar o pareamento diagnóstico até `min(fonte,destino)`, mas o apply permanece bloqueado;
- `number_of_classes` é agregado como diagnóstico e não autoriza expansão automática de um registro-fonte para várias datas;
- nenhuma escrita acadêmica ocorre na R2.0b.

## Boundary

Read-only em produção; sem `attendance.records`; sem estudantes, matrículas ou notas; sem IDs técnicos brutos; plaintext pedagógico lido apenas internamente para fingerprint e nunca emitido; sem deploy.

Tracking: #444 → #439 → #438 → #418. Trilha investigativa: #357.
