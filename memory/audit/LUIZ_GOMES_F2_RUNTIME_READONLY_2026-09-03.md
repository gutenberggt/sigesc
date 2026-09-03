# LUIZ-GOMES-F2 — Runtime read-only Mongo → HTTP → tela

Data: 2026-09-03  
Tracking: #357

## Objetivo

Após a F1 comparativa provar que os seis pares de Matemática de Luiz Gomes dos Santos **não** apresentam cisão de identidade de componente, esta etapa localiza a perda de visibilidade entre:

`Mongo legado → endpoint HTTP → resolver frontend → tela`.

Alvo exato:
- professor: **Luiz Gomes dos Santos**;
- escola: **E M E I E F Jose Pereira Barbosa**;
- ano: **2026**;
- pares: 6º ANO A, 6º ANO B, 7º ANO A, 7º ANO B, 8º ANO A e 9º ANO A × Matemática.

## Base metodológica

A F2 reutiliza o motor `ana_lucia_f2_1_runtime_legacy_audit.py`, que já foi executado e homologado no caso Ana Lúcia. O wrapper Luiz substitui somente professor/alvos e fortalece a resolução exigindo a escola exata.

São medidos:
- `learning_objects` no Mongo por mês/tenant/tipo de `academic_year`;
- `GET /learning-objects` mensal e component-scoped como professor e como Super Administrador tenant-scoped;
- `attendance` e `attendance_documentary` por documento/data, sem `records`;
- `GET /attendance/dates-with-records` como professor e gestão;
- status de `GET /attendance/by-class/{class}/{date}` para uma data sentinela, sem ler seu corpo;
- exposição do componente em `/professor/turmas`;
- presença de diário em `/professor/diarios`;
- eventual guard DVD anual bruto.

## Hipóteses discriminadas

Conteúdo:
- `CONTENT_REACHES_SCREEN`;
- `CONTENT_UI_COMPONENT_NOT_EXPOSED`;
- `CONTENT_TEACHER_HTTP_BLOCKED`;
- `CONTENT_ROLE_HTTP_PARITY_GAP`;
- `CONTENT_TENANT_METADATA_GAP`;
- `CONTENT_ACADEMIC_YEAR_TYPE_GAP`;
- `CONTENT_HTTP_ZERO_WITH_MONGO_RECORDS`.

Frequência:
- `ATTENDANCE_REACHES_SCREEN`;
- `ATTENDANCE_UI_COMPONENT_NOT_EXPOSED`;
- `ATTENDANCE_TEACHER_HTTP_BLOCKED`;
- `ATTENDANCE_ROLE_HTTP_PARITY_GAP`;
- `ATTENDANCE_RAW_DVD_YEAR_GUARD_OUT_OF_SCOPE`;
- `ATTENDANCE_HTTP_ZERO_WITH_MONGO_RECORDS`;
- `ATTENDANCE_DOCUMENTARY_ONLY_NOT_IN_LEGACY_READER`.

## Boundary

- MongoDB somente leitura;
- HTTP somente GET;
- nenhum login; JWT efêmero gerado em memória a partir das identidades existentes;
- sem `attendance.records`;
- sem estudantes/matrículas/notas;
- corpo pedagógico de conteúdo não é decodificado; a auditoria conta objetos JSON em streaming;
- nenhum ID técnico ou PII é emitido;
- nenhuma escrita, backfill, migração, remapeamento ou correção;
- MT-1, Transferência e AEE intocados.

## Gate de produção

Título:

`[LUIZ-GOMES-F2-RUNTIME] <SHA exato de main>`

Corpo:

```text
LUIZ_GOMES_F2_RUNTIME=AUTHORIZED
CONFIRMATION=AUDIT_LUIZ_RUNTIME_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<mesmo SHA do título>
```

A `main` deve continuar exatamente no SHA autorizado e a issue #357 deve permanecer aberta. O resultado é anexado como artifact por 90 dias e resumido na issue #357.
