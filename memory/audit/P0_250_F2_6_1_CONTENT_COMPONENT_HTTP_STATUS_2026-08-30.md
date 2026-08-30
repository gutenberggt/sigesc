# P0 #250 — F2.6.1 paridade HTTP/status por componente

## Motivo
A primeira execução F2.6 em produção, no SHA `dcdaae885a710541085ec3300ef7701ea2d0de29`, passou pelos gates de autorização, checkout exato, SSH e resolução do backend, mas o coletor encerrou ao receber HTTP 409 no primeiro `GET /learning-objects` class-wide da professora.

Esse 409 é evidência diagnóstica e não deve ser tratado como falha do coletor.

## Objetivo
Medir abril, maio e junho de 2026, para os 9 componentes legados de Abadia Alves Martins no 5º ANO A da E M E I E F Jose Pereira Barbosa:

- contagem Mongo no tenant da turma;
- status/contagem do GET class-wide como professora;
- status/contagem do GET component-scoped como professora;
- status/contagem do GET tenant-scoped como Super Administrador;
- contagens estruturais de `teacher_assignments` e `teacher_class_assignments`;
- destaque nominal apenas para Português e Matemática.

## Segurança
- MongoDB somente leitura;
- HTTP somente GET;
- sem login;
- tokens efêmeros apenas em memória;
- sem conteúdo textual;
- sem IDs de registros, vínculos ou docentes;
- sem dados de estudantes;
- sem mutação de produção.

## Classificações principais
- `CONTENT_COMPONENT_PROFESSOR_COMPONENT_BLOCKED`
- `CONTENT_COMPONENT_PROFESSOR_CLASSWIDE_BLOCKED`
- `CONTENT_COMPONENT_HTTP_PROFESSOR_GAP`
- `CONTENT_COMPONENT_HTTP_MANAGEMENT_GAP`
- `CONTENT_COMPONENT_HTTP_DB_PARITY`
- `PROFESSOR_CONTENT_ENTITLEMENT_DRIFT`

A coleta live permanece owner-only e presa ao SHA exato de `main` após merge.
