# P0-F7.9D7.3.1 — Política Curricular Canônica de Carga Horária

Data: 2026-08-29

## Motivação

A D7.3 original tratava o conflito de `carga_horaria_semanal` (`2` × `3`) como decisão humana entre dois valores existentes no par duplicado. Nova regra institucional esclareceu que, para **Geografia, História e Ciências**, a carga deve ser determinada por **componente + nível de ensino + série/ano**. Em turma multissérie, prevalece a **maior carga horária anual** entre as séries representadas.

Consequência: a carga deixa de ser preferência/adjudicação humana quando a política possui cobertura suficiente. A única decisão humana remanescente na D7.3.1 é qual `teacher_assignment` duplicado sobreviverá.

## Matriz institucional

### Geografia

- Fundamental — Anos Iniciais: 80h.
- Fundamental — Anos Finais: 6º=120h; 7º=80h; 8º=80h; 9º=80h.
- EJA — Anos Iniciais: 80h.
- EJA — Anos Finais: 80h.

### História

- Fundamental — Anos Iniciais: 80h.
- Fundamental — Anos Finais: 6º=80h; 7º=80h; 8º=120h; 9º=80h.
- EJA — Anos Iniciais: 80h.
- EJA — Anos Finais: 80h.

### Ciências

- Fundamental — Anos Iniciais: 80h.
- Fundamental — Anos Finais: 6º=80h; 7º=120h; 8º=80h; 9º=120h.
- EJA — Anos Iniciais: 80h.
- EJA — Anos Finais: 120h.

## Representação semanal

A política registra explicitamente a correspondência usada por `teacher_assignments`:

- 80h anuais → `carga_horaria_semanal=2`;
- 120h anuais → `carga_horaria_semanal=3`.

Não é feita divisão genérica de qualquer valor anual. Somente as cargas institucionais 80h e 120h são mapeadas.

## Regra multissérie

Para uma turma com mais de uma série/etapa, resolve-se a CH anual aplicável a cada série e utiliza-se:

`CH_CANONICA = max(CH_SERIE_1, CH_SERIE_2, ...)`

A regra é identificada como `MAX_ANNUAL_WORKLOAD`.

## Aplicação ao caso D7.2

Turma: `MULTI 3º E 4º ETAPA`.

Contexto curricular já identificado: `eja_final` (EJA — Anos Finais), séries `EJA 3ª ETAPA` e `EJA 4ª ETAPA`.

Componente: Geografia.

- 3ª etapa: 80h;
- 4ª etapa: 80h;
- multissérie: `max(80, 80) = 80h`;
- representação semanal canônica: `2h`.

Portanto, o conflito `2` × `3` não exige mais decisão humana de carga. A carga canônica é `2`.

## Arquitetura

SSoT: `backend/utils/curricular_workload_policy.py`.

A D7.3.1 (`backend/scripts/adjudicate_p0f7_9d731_curricular_policy.py`) consome essa política e reutiliza a D7.3 base para construir o plano revisado. Ela não duplica a lógica de operações da D7.3.

A estação D7.3.1:

- exibe a resolução curricular de CH;
- não permite editar a carga;
- pede somente responsável, autoridade, survivor e justificativa do survivor;
- exporta decisão compatível com o `Seal` D7.3;
- rejeita adulteração manual da carga antes do `Seal` base.

## Segurança

- `PRODUCTION_ACCESS=NO`;
- `DATABASE_ACCESS=NO`;
- `DATABASE_MUTATION=NO`;
- `PRODUCTION_WRITES=NO`;
- `EXECUTOR_AUTHORIZED=NO`;
- sem SSH/SCP/Docker/mongosh;
- sem cliente de banco/rede;
- nenhum dado de estudante.

## Escopo de runtime

Esta subfase corrige imediatamente a adjudicação da remediação D7.3. A política foi criada como módulo canônico reutilizável para posterior conexão à fronteira `services/teacher_assignment_integrity.py`, evitando que futuras gravações aceitem cargas incompatíveis com componente + nível + série. Essa conexão de runtime deve ser feita em PR próprio, com regressões dos três caminhos ativos de escrita e sem misturar a remediação histórica com alteração operacional.

## Autorização

Este documento e o código D7.3.1 não autorizam escrita em produção nem reutilizam a autorização histórica de 23 writes. Qualquer execução futura continua exigindo fresh last-mile preflight, novo CAS dry-run e nova autorização humana explícita.
