# Luiz Gomes — F6.3b Diary Snapshot Recovery Read-only

Data: 2026-09-05  
Tracking: #357

## Contexto

A F6.3 consultou `audit_logs` para `content_entries`/`learning_objects` atribuídos ao Luiz e encontrou zero eventos para o período-alvo. Esse resultado é apenas ausência de evidência nessa fonte: o CRUD legado `learning_objects` não possui garantia de auditoria equivalente ao mecanismo canônico `content_entries`.

A próxima fonte forense é `diary_snapshots`, cujo contrato arquitetural é imutável: o payload é congelado no momento da criação/publicação e não é recalculado a partir do banco vivo.

## Objetivo

Verificar se algum snapshot do 8º ANO A ou 9º ANO A, cobrindo fevereiro–abril/2026, preserva metadados suficientes para demonstrar que havia conteúdo de Matemática associado ao professor Luiz Gomes dos Santos.

## Evidência considerada

Para cada `payload.days[].entries[]`, sem abrir texto pedagógico:

- data;
- componente id/nome;
- professor id/nome;
- `content_status`;
- existência de `content_entry_id`;
- versão;
- `matched_by`;
- aula e expectativa por schedule.

`content_entry_id` congelado é tratado como evidência mais forte de conteúdo presente. Um `content_status` não vazio/não missing sem ID é evidência secundária.

Snapshots `published`, `superseded` ou `revoked` são classificados como evidência institucional mais forte do que `draft`.

## Classificações

- `INSTITUTIONAL_DIARY_SNAPSHOT_MATH_CONTENT_CONFIRMED`
- `DRAFT_DIARY_SNAPSHOT_MATH_CONTENT_EVIDENCE`
- `DIARY_SNAPSHOT_MATH_EXPECTATION_WITHOUT_CONTENT`
- `DIARY_SNAPSHOT_PRESENT_NO_LUIZ_MATH_ENTRY`
- `NO_DIARY_SNAPSHOT_COVERING_TARGET_PERIOD`

## Boundary

A execução é exclusivamente read-only:

- MongoDB somente leitura;
- sem HTTP;
- sem `attendance.records`;
- sem estudantes, matrículas ou notas;
- projeção de snapshot exclui `content_text`, `content_methodology`, `content_observations`, `attendance_records`, `student_id` e `dependency_id`;
- nenhum ID técnico bruto é emitido;
- nenhuma restauração, mutação, remapeamento, backfill ou deploy.

## Gate

Runtime somente após merge, por issue owner-only com:

```text
LUIZ_GOMES_F6_3B_SNAPSHOT_RECOVERY=AUTHORIZED
CONFIRMATION=TRACE_IMMUTABLE_DIARY_SNAPSHOTS_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<main exato>
EXPECTED_PRODUCTION_SHA=<production exata>
```

## Próxima decisão

- Evidência positiva em snapshot institucional: existe fonte congelada verificável e pode-se desenhar uma recuperação cirúrgica posterior.
- Evidência somente em draft: preservar como pista, sem promovê-la automaticamente a fonte institucional definitiva.
- Ausência de evidência: avançar para backups Mongo históricos, sempre restaurados apenas em container temporário isolado (`--network none`, sem portas, backup read-only), nunca sobre produção.
