# R1.0B.1 — Bridge Temporal de Identidade — Luiz 8º A/9º A

Data: 2026-09-05
Tracking: #425, pai #418, trilha #357, precedente #422. Hardening de envelope: #432.

## Motivo

A R1.0B concluiu `HISTORICAL_SCHEMA_BRIDGE_INCONCLUSIVE` por `CLASS_LABEL_VALUE_OR_COMPOSITE_NOT_RESOLVED`. O dump BSON de 18/08 não ofereceu rótulos escalares de turma suficientes para mapear 6º A, 6º B, 7º A, 7º B, 8º A e 9º A por nome ou por composição série+seção.

A R1.0B.1 não repete essa estratégia. Ela testa **continuidade temporal de identidade técnica** entre a base viva e o dump histórico.

## Desenho

1. Um coletor `mongosh` bounded lê na produção somente `schools`, `classes` e `courses`.
2. A escola Jose Pereira Barbosa e as seis turmas são resolvidas pelo schema atual, conhecido e canônico.
3. As identidades técnicas são gravadas somente em arquivo efêmero privado no host. Elas não podem aparecer em logs, comentários, artefatos ou resultado sanitizado.
4. O dump de 18/08 é restaurado em Mongo temporário `--network none`, sem portas, a partir de source read-only.
5. O probe histórico procura exatamente as seis identidades atuais dentro dos documentos históricos e das referências de `learning_objects`.
6. Matemática é resolvida primeiro por identidade temporal de curso; se isso não estiver preservado, usa-se fallback relacional pelo valor histórico `Matemática` em `courses` e sua referência em `learning_objects`.
7. O período permanece `2026-02-01 <= date < 2026-05-01`.

## Regra probatória

O bridge de turma somente é aceito se **as seis identidades** forem preservadas e mapeadas de forma não ambígua. Os quatro controles (6º A/B e 7º A/B) devem possuir Matemática no período para que a relação final seja aceita.

Se IDs atuais não estiverem preservados no dump, a conclusão é `TEMPORAL_IDENTITY_NOT_PRESERVED`; isso não prova ausência de conteúdo e não autoriza inferência por semelhança.

## Privacidade e segurança

- produção: apenas leitura metadata-only de `schools`, `classes`, `courses`;
- nenhuma leitura de estudantes, matrículas, frequência ou notas;
- nenhum Python no backend de produção;
- nenhuma escrita na base viva;
- identidades técnicas somente internas e efêmeras;
- cleanup obrigatório das identidades técnicas;
- nenhum ID técnico bruto externalizado;
- nenhum plaintext pedagógico emitido;
- o probe não infere autoria docente;
- qualquer ambiguidade encerra fail-closed.

## Taxonomia

- `TEMPORAL_IDENTITY_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT`
- `TEMPORAL_IDENTITY_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD`
- `TEMPORAL_IDENTITY_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS`
- `TEMPORAL_IDENTITY_NOT_PRESERVED`
- `TEMPORAL_IDENTITY_BRIDGE_INCONCLUSIVE`
- `TEMPORAL_IDENTITY_RUNTIME_OR_BOUNDARY_ERROR`

## R1.0B.1a — envelope diagnóstico do live seed

O gate #431 / run `33988088851` mostrou `R1B1_REMOTE_SCAN_RC=21`: o processo `mongosh` retornou zero, mas o marcador final do live seed não foi localizado. O fluxo parou antes da seleção/restauração do dump histórico.

A microfase R1.0B.1a endurece apenas o envelope de execução:

1. o live seed passa a ser executado como arquivo não interativo via `mongosh --quiet --file /dev/stdin`;
2. o JavaScript é envolvido por `try/catch` fail-closed;
3. qualquer falha controlada pode emitir somente um diagnóstico sanitizado com `reason`, `diagnostic_stage` e `error_name` normalizados;
4. a mensagem de exceção e a stack nunca são externalizadas;
5. nenhum ID técnico, documento Mongo ou conteúdo pedagógico integra o diagnóstico;
6. o workflow só aceita o diagnóstico antecipado para os códigos controlados `12` ou `21`, com schema e tokens estritamente validados;
7. quando esse diagnóstico é aceito, a classificação permanece `TEMPORAL_IDENTITY_RUNTIME_OR_BOUNDARY_ERROR`, `R1.0C` continua fechada e o dump histórico não é acessado.

Esse hardening não transforma erro de runtime em evidência de domínio e não altera a taxonomia probatória da investigação.

## Gate subsequente

R1.0C só poderá ser aberta se o bridge temporal mapear deterministicamente as seis turmas e localizar ao menos uma linha histórica de Matemática no 8º A ou 9º A.

R1.1 continua bloqueada: presença de linha ou payload não equivale automaticamente a `RECOVERABLE_EXACT`; autoria e integridade do conteúdo ainda terão de ser demonstradas em fase própria.
