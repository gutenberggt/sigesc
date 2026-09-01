# ANA-LUCIA-F2.2 — Rastreamento de origem/orfandade (read-only)

## Objetivo

Investigar, sem escrita em produção, os oito pares de **Língua Inglesa** dos 6º e 9º anos em que a F2.1 encontrou `learning_objects=0`, com foco adicional nos cinco pares em que a frequência oficial também estava ausente.

## Hipóteses verificadas

1. registro no par esperado, mas fora do escopo do ano letivo 2026;
2. registro na mesma turma sob outro `course_id` que também representa Língua Inglesa;
3. registro na mesma turma sob outro componente;
4. conteúdo já existente em `content_entries` em vez de `learning_objects`;
5. frequência salva sem `course_id` (class-daily);
6. frequência em `attendance_documentary`;
7. registros de Língua Inglesa atribuíveis à mesma professora em outra turma;
8. existência de eventos `create/update/delete` em `audit_logs` no mesmo ano/escola, sem ler `old_value`, `new_value` ou `description`.

## Boundary

- MongoDB somente leitura (`find`/`find_one`/projeções);
- nenhum HTTP e nenhum login;
- nunca lê `attendance.records`;
- não consulta coleções de estudantes, matrículas ou saúde;
- não lê texto pedagógico de `learning_objects` ou `content_entries`;
- não emite IDs técnicos brutos: somente fingerprints SHA-256 truncados;
- não lê `old_value`, `new_value` ou `description` de `audit_logs`;
- nenhuma mutação, backfill, reconciliação, migração, saneamento ou alteração de dados;
- Transferência Institucional e MT-1 permanecem fora do escopo e intocados.

## Saída esperada

Para cada um dos oito pares, a auditoria publica contagens estruturais e códigos causais, além de um mapa agregado das localizações de Língua Inglesa em 2026 atribuíveis à professora. A saída deve permitir distinguir `misrouting`, duplicidade de identidade de componente, deslocamento para coleção canônica, erro de escopo temporal, frequência class-daily/documental ou ausência efetiva de evidência nos metadados pesquisados.
