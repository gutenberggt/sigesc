# Luiz Gomes — F6.3 Audit Log Recovery Read-only

Data: 2026-09-05  
Tracking: #357

## Contexto

F6.2 eliminou a hipótese de que os 209 `learning_objects` encontrados em outros componentes no 8º ANO A e 9º ANO A fossem conteúdos de Matemática do professor Luiz Gomes dos Santos. Todos os candidatos possuíam metadados de outros atores, enquanto os `learning_objects` atribuídos ao Luiz em fevereiro–abril/2026 estavam restritos ao 6º e 7º anos.

O usuário observou que a tela **Logs de Auditoria**, ao filtrar **Conteúdos**, pode preservar uma evidência independente de que o professor realizou lançamentos para fevereiro, março e abril.

## Hipótese F6.3

Os documentos vivos podem ter desaparecido ou deixado de ser alcançáveis, mas `audit_logs` pode preservar eventos de criação/alteração de `content_entries` com:

- ator (`user_id`);
- turma;
- data pedagógica da aula;
- componente;
- professor;
- número da aula;
- tipo de mudança (`content_created`, `content_updated`, etc.).

Uma ocorrência positiva com ator Luiz + 8º/9º A + data em fev–abr/2026 + identidade atual de Matemática é evidência histórica forte de que o lançamento existiu.

## Limite metodológico

Ausência de log **não prova que o lançamento nunca existiu**. O motor legado `learning_objects` não possui hoje chamada direta equivalente ao `audit_service` no CRUD básico, enquanto o motor canônico `content_entries` possui auditoria rica e foi consolidado a partir de maio/2026.

Portanto:

- `AUDIT_LOG_MATH_REGISTRATION_CONFIRMED` = evidência positiva forte;
- `NO_AUDIT_LOG_EVIDENCE_FOR_TARGET_PERIOD` = ausência de evidência nesta fonte, não prova negativa;
- em caso negativo, a F6.3 deve prosseguir para snapshots/backups históricos.

## Escopo

- professor: Luiz Gomes dos Santos;
- escola: E M E I E F Jose Pereira Barbosa;
- turmas: 8º ANO A e 9º ANO A;
- componente: Matemática;
- período pedagógico: 2026-02-01 a 2026-04-30;
- coleções de auditoria consideradas: `content_entries` e `learning_objects`;
- consulta centrada no `user_id` do Luiz.

## Boundary

A execução em produção é exclusivamente read-only:

- MongoDB somente leitura;
- nenhuma chamada HTTP do produto;
- nenhuma escrita, remapeamento, restore ou backfill;
- nenhuma leitura de `attendance.records`;
- nenhuma leitura de estudantes, matrículas ou notas;
- projeção de `audit_logs` exclui `content`, `previous_content`, `new_content`, metodologia, observações e recursos;
- nenhum ID técnico bruto é emitido; componentes podem aparecer por nome e fingerprint SHA-256 truncado;
- nenhuma evidência pedagógica textual sai do processo.

## Gate

Runtime somente depois do merge em `main`, por issue owner-only com:

```text
LUIZ_GOMES_F6_3_AUDIT_RECOVERY=AUTHORIZED
CONFIRMATION=TRACE_CONTENT_AUDIT_LOGS_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<main exato>
EXPECTED_PRODUCTION_SHA=<production exata>
```

A produção deve permanecer no SHA observado e #357 deve estar aberto.

## Próxima decisão

- Se houver evidência forte: tratar o `audit_log` como fonte de proveniência para uma etapa de recuperação controlada, ainda sem executar restore automático.
- Se não houver: avançar para `diary_snapshots` e, depois, para backups Mongo restaurados em ambiente isolado, preservando o mesmo princípio fail-closed.
