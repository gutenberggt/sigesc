# P0-F7.8.1 — Contrato de budget de recursos

Este arquivo torna verificável o limite operacional do auditor P0-F7.8.1.

## Budget máximo por execução

- casos: 3;
- consultas `classes`: 3 `find_one`;
- consultas `courses`: 3 `find` limitadas a no máximo 4 cursos por caso;
- consultas `teacher_assignments`: 3 `find` limitadas a no máximo 10 linhas por caso;
- total máximo de chamadas de consulta: 9;
- conexões Mongo simultâneas no pool: 2;
- `serverSelectionTimeoutMS`: 5000;
- `connectTimeoutMS`: 5000;
- `socketTimeoutMS`: 15000.

## Coleções proibidas nesta fase

- `students`;
- `enrollments`;
- `grades`;
- `attendance`.

## Operações proibidas

- replay do resolver por estudante;
- qualquer `insert`, `update`, `delete`, `replace` ou `bulk_write`;
- `--apply`;
- decisão automática de componente;
- decisão automática de carga horária.

Qualquer alteração futura que viole esse contrato deve falhar no workflow `P0-F7.8.1 Bounded Re-evaluation Guard`.
