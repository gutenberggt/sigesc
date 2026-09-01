# ANA-LUCIA-F2.1 — Auditoria Runtime Legacy Read-only

Data: 2026-09-01
Tracking: #314

## Objetivo

Determinar em qual camada os registros legados de conteúdo e frequência dos 17 pares de Ana Lucia Faria Pinto deixam de ser projetados: Mongo legado → endpoint legado → resposta HTTP → resolver frontend → tela.

## Escopo e fronteiras

- ano letivo 2026;
- exatamente os 17 pares já selados na ANA-LUCIA-F1/F2;
- MongoDB somente leitura;
- HTTP somente GET;
- nenhum login: tokens efêmeros são gerados em memória a partir de identidades existentes;
- nenhuma leitura de `attendance.records`;
- nenhuma leitura de PII de aluno;
- o corpo pedagógico de `learning_objects` não é decodificado/inspecionado: a auditoria conta estruturalmente os objetos do array HTTP;
- nenhum ID técnico é emitido no relatório público;
- nenhuma mutação, backfill, reconciliação, migração ou exclusão;
- Transferência Institucional e MT-1 permanecem intocados.

## Modelo de diagnóstico

### Mongo legado

Conteúdo: contagem de `learning_objects` por turma/componente/ano, segmentada por `mantenedora_id` correta, ausente ou divergente e por tipo de `academic_year`.

Frequência: contagem estrutural de documentos/datas nas coleções `attendance` e `attendance_documentary`, sem projetar `records`.

### Endpoint legado / resposta HTTP

Conteúdo: `GET /learning-objects` mensal e component-scoped, comparando professora e Super Administrador tenant-scoped.

Frequência: `GET /attendance/dates-with-records` e status de `GET /attendance/by-class/{class}/{date}`, sem ler o corpo deste último.

Também são consultados `GET /professor/turmas` e `GET /professor/diarios` para separar entitlement legado de projeção DVD.

### Resolver frontend

O gate sela estaticamente os contratos atuais:

- `contentDvdBridge`: zero diário canônico autorizado preserva o request legado;
- `attendanceDvdBridge`: sem `assignment_id` preserva as rotas legadas;
- `attendance_dvd.py`: o guard anual bruto `_has_dvd_year` é identificado separadamente para verificar eventual divergência com o escopo DVD v1.

### Tela

- `LearningObjects.js`: a resposta de listagem é colocada em `records` e o calendário identifica registro por data;
- `Attendance.js`: falha em `dates-with-records` é atualmente convertida em conjunto vazio de datas.

## Hipóteses a confirmar em produção

1. `learning_objects` sem `mantenedora_id` podem ficar invisíveis após o fail-closed da MT-1, pois o endpoint legado aplica o tenant ativo.
2. Um `teacher_class_assignment` bruto habilitado em turma fora do DVD v1 pode fazer `_has_dvd_year` retornar verdadeiro e bloquear a frequência legada do professor com HTTP 409, mesmo quando `/professor/diarios` não autoriza nenhum diário DVD.
3. Se Mongo e HTTP estiverem em paridade e o registro chegar ao estado usado pela tela, a ausência visual restante deverá ser investigada como versão/cache/renderização do frontend, não como perda de dados.

## Governança

Esta fase produz somente diagnóstico. Qualquer correção funcional ou saneamento de dados será uma etapa posterior, com autorização própria quando envolver código de regra de negócio, multi-tenancy ou mutação de produção.