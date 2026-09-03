# F0 — Retificação de Matrícula/Turma por Erro Documental

> **Status:** PROPOSTA NORMATIVA / AUDITORIA READ-ONLY  
> **Baseline auditada:** `9954fe5a687a5cf4e661aec11725a7520e23c6f6`  
> **Issue de origem:** #346  
> **Nome canônico proposto da operação:** `retificacao_enturmacao`  
> **Escopo desta F0:** arquitetura, contrato, invariantes, modelo proposto e testes. **Nenhuma implementação funcional ou mutação de dados.**

---

## 1. Problema de domínio

Existe uma classe de ocorrência diferente de remanejamento, progressão, reclassificação ou transferência: o estudante foi vinculado documentalmente à turma/série errada, embora o vínculo correto devesse existir desde a matrícula original.

Exemplo abstrato: matrícula registrada no 6º ano quando, por erro documental, deveria ter sido registrada desde o início em turma do 7º ano.

A operação necessária não representa um percurso escolar real entre duas turmas. Ela corrige a **fonte de verdade** para remover da vida escolar oficial um vínculo que nunca deveria ter existido, preservando simultaneamente a evidência administrativa de que a correção ocorreu.

### 1.1 Regra de elegibilidade conceitual

`retificacao_enturmacao` **somente** pode ser usada quando houver base administrativa/documental para afirmar que a turma de origem é um erro de registro.

Ela NÃO pode ser usada para:

- promover estudante;
- reclassificar estudante;
- alterar retroativamente um percurso efetivamente cursado;
- contornar regras de avaliação, progressão ou transferência;
- fabricar frequência ou notas de outra série;
- corrigir simples insatisfação com enturmação.

Se o estudante efetivamente cursou a turma de origem durante algum período, o fluxo correto continua sendo o contrato de movimentação acadêmica (`remanejamento`, `reclassificacao`, `transfer`, etc.).

---

## 2. Decisão arquitetural principal: retificação ≠ movimentação acadêmica

O documento `docs/ACADEMIC_EVENT_CONTRACT.md` está congelado em V1 e estabelece, corretamente para movimentações reais, que:

- lançamentos anteriores permanecem vinculados à turma/professor de origem;
- `attendance.records[]` e `grades.class_id` históricos não são fisicamente movidos;
- a matrícula de origem não é apagada;
- o destino consulta o passado por lente temporal.

A retificação proposta possui semântica oposta em um ponto essencial: a turma errada **não pode continuar sendo apresentada como percurso acadêmico verdadeiro**.

Portanto:

### DEC-01 — Separação normativa

`retificacao_enturmacao` NÃO será adicionada silenciosamente a `academic_events` V1 e NÃO reutilizará o motor temporal de movimentação como se fosse um novo evento ordinário.

A retificação terá contrato e trilho próprios. O contrato V1 de eventos acadêmicos permanece inalterado.

Uma futura unificação com `academic_events` somente poderá ocorrer mediante revisão normativa explícita e bump de `contract_version`.

---

## 3. Estado atual comprovado por código

### 3.1 Matrícula

`backend/services/enrollment_service.py` já declara:

- `enrollments` = fonte canônica do vínculo estudante ↔ turma ↔ ano;
- `students.class_id/school_id/status/enrollment_number` = projeção conveniente da matrícula regular ativa;
- `class_students` = legado de leitura, sem novas escritas;
- matrículas de programas especiais coexistem sem substituir a matrícula regular.

Consequência: a nova funcionalidade deve operar a partir de `enrollments`, e não criar mais um writer direto de `students.class_id`.

### 3.2 Remanejamento/progressão/reclassificação atuais

`backend/routers/students.py` cria uma nova matrícula ativa e inativa a matrícula anterior. O número de matrícula é carregado para a nova matrícula. Em seguida, o backend chama `consolidate_student_movement()`.

`backend/services/pedagogical_consolidation.py` explicita seu contrato atual:

- origem é preservada;
- destino recebe cópia idempotente;
- frequência, notas e conteúdo são copiados.

Esse comportamento é adequado à continuidade de uma movimentação real, mas inadequado à retificação de um vínculo incorreto.

### 3.3 Frequência

`backend/routers/attendance.py` mantém a frequência oficial em documentos de aula, com `records[]` por estudante. Nos Anos Finais, a identidade lógica pode incluir:

- `class_id`;
- `date`;
- `course_id`;
- `aula_numero`.

O DVD aprofunda essa identidade com `assignment_id`, proveniência do vínculo docente e índices únicos próprios em `backend/services/attendance_assignment_scope.py`.

Logo, um status individual de frequência não pode ser reatribuído para uma sessão da turma destino sem prova de que aquela sessão existiu.

### 3.4 Notas

`grades` permanece fonte canônica, com um documento por estudante/turma/componente/ano. Os campos de valor incluem `b1..b4`, `rec_s1`, `rec_s2`, `recovery`.

O DVD (`backend/services/grade_assignment_scope.py`) preserva autoria/proveniência por campo em `grade_ownership`, pois professores/vínculos diferentes podem responder por períodos diferentes do mesmo documento.

### 3.5 Histórico Escolar

`backend/services/history_consolidator.py` deriva a vida escolar principalmente das matrículas e agrega notas/frequência. Isso reforça que uma retificação documental não deve criar o padrão "origem inativa + destino ativa" próprio de uma movimentação real: isso perpetuaria duas turmas como percurso do ano.

### 3.6 Documentos e snapshots

`backend/services/verifiable_docs_service.py` possui estados de revogação e supersessão para documentos verificáveis.

`backend/services/diary_snapshot_service.py` estabelece imutabilidade absoluta do snapshot publicado: payload/hash não são reescritos após emissão.

### 3.7 Persistência/atomicidade

`docker-compose.coolify.yml` executa um único `mongo:7`, sem configuração de replica set no repositório. A auditoria não encontrou uso de `start_session`/`with_transaction`.

A F1, portanto, **não pode presumir transação ACID multi-documento**.

O projeto já possui `backend/lib/critical_mutation.py`, que fornece:

- `Idempotency-Key`;
- lock distribuído por target;
- trilha de runs/diff;
- 409 em concorrência;
- replay idempotente.

A retificação deve reutilizar esse ativo, complementado por saga/checkpoints e compensação.

---

## 4. Semântica canônica da retificação

### DEC-02 — Corrigir a matrícula canônica em vez de criar uma movimentação

Na primeira versão, quando o erro documental for confirmado, a matrícula regular canônica existente deverá ser **retificada em lugar**:

Preservar, sempre que tecnicamente válido:

- `enrollment.id`;
- `enrollment_number`;
- `enrollment_date` original;
- `academic_year`;
- `created_at` original;
- identidade do estudante e da escola/mantenedora.

Retificar:

- `class_id`;
- `student_series`;
- `course_ids`, quando aplicável e após mapeamento validado;
- metadados derivados da turma.

Depois, reconstruir `students.*` pela SSoT de matrícula (`rebuild_student_home_projection` ou serviço equivalente), nunca por writer paralelo.

### ENR-01

Após sucesso, deve existir exatamente **uma** matrícula regular ativa para o estudante no ano letivo e ela deve apontar para a turma correta.

### ENR-02

A matrícula errada não deve permanecer como `relocated`, `transferred`, `progressed` ou outro status que implique percurso acadêmico real.

### ENR-03

Se já existir outra matrícula regular ativa no destino/ano, a operação é bloqueada até saneamento explícito.

### ENR-04

`class_students` não receberá novas escritas. Resíduos dessa estrutura legada serão diagnosticados e classificados para saneamento, não utilizados como nova fonte da verdade.

---

## 5. Escopo V1 e precondições

A primeira versão somente poderá operar quando TODAS as condições abaixo forem verdadeiras:

1. estudante existente e dentro do tenant operacional;
2. uma única matrícula regular ativa no ano alvo;
3. turma origem existente;
4. turma destino existente;
5. origem e destino na **mesma mantenedora**;
6. origem e destino na **mesma escola**;
7. origem e destino no **mesmo ano letivo**;
8. turmas regulares, não turmas especiais AEE/reforço/recomposição;
9. nenhuma retificação concorrente para estudante+ano;
10. mapeamento curricular completo para todos os dados que exigem componente;
11. ausência de colisões não resolvidas no destino;
12. inventário documental concluído;
13. nenhuma dependência acadêmica ou evento acadêmico incompatível sem revisão;
14. contexto MT-1 válido e ativo;
15. base documental/administrativa da correção registrada.

### RET-00 — Uso restrito à correção documental

O operador deve declarar que a ação corrige erro de registro e não representa progressão/reclassificação retroativa.

### RET-01 — Dry-run obrigatório

Nenhuma execução será aceita sem dry-run válido, não expirado e revalidado imediatamente antes da escrita.

### RET-02 — Fail-closed

Qualquer ambiguidade estrutural, curricular, documental ou de tenant interrompe a operação antes da primeira mutação destrutiva.

---

## 6. Matriz coleção/estrutura × ação futura

| Estrutura | Vínculo relevante | Ação V1 proposta | Risco/observação |
|---|---|---|---|
| `enrollments` | student/class/year | **rewrite** da matrícula regular canônica | Crítico; preservar identidade/data/número |
| `students` | `class_id`, projeção | **rebuild projection** pela SSoT | Não escrever como fonte independente |
| `class_students` | student/class legado | `manual_review` / higiene de legado | Não criar novas escritas |
| `attendance` | class/date/course/aula + `records[]` | remover somente o record do estudante da origem | Nunca mover documento inteiro |
| `attendance_rectifications` (nova) | student/enrollment/date/evidência | **create** evidência administrativa contabilizável | Nova SSoT complementar para frequência efetiva |
| `grades` | student/class/course/year | mover/mesclar com mapa curricular validado; remover origem | Preservar valores e autoria; colisão bloqueia |
| `content_entries` | class/course/date | **preserve** sem alteração | Conteúdo é da turma/aula, não do estudante |
| `student_dependencies` | student/class/course | `manual_review` / bloqueio V1 se relacionado | Sem migração automática |
| `academic_events` | student/origin/dest | **preserve**; retificação não cria evento V1 | Evento existente relacionado pode bloquear |
| `academic_event_audit` | evento | **preserve** | Imutável/auditável |
| `student_history` | student/class/action | preservar; entradas incorretas podem ser marcadas como superseded/admin-only | Nunca apagar trilha administrativa |
| `medical_certificates` | student/date | **preserve** | Student-anchored |
| AEE (`planos_aee`, atendimentos etc.) | student | **preserve** | Nenhuma alteração funcional nesta iniciativa |
| `bolsa_familia_tracking` | student | **preserve** | Não reescrever tracking; atualizar apenas leitura de frequência efetiva |
| `diary_snapshots` | class/período/payload | **immutable**; detectar impacto e supersede/revoke por workflow documental | Nunca editar payload/hash |
| `verifiable_documents` | student/entity/snapshot | detectar, revogar/supersede conforme tipo | Nunca alterar silenciosamente documento emitido |
| `document_render_jobs`/arquivos | snapshot/doc | preserve; nova emissão usa nova derivação | Artefato antigo continua como evidência histórica inválida/substituída |
| `grades.grade_ownership` | campo/assignment | **preserve provenance** | Não atribuir autoria retroativa ao professor destino |
| `attendance_documentary` | assignment/session | `manual_review` se houver vínculo individual relevante | Não faz frequência acadêmica oficial |
| caches/offline frontend | student/class | invalidar/recarregar na F2 | Backend deve rejeitar replay stale |
| `audit_logs` | operação | **append** | Nunca apagar |

A F1 deverá repetir busca estática no repositório antes de implementar para detectar novas coleções/consumidores introduzidos após esta baseline.

---

## 7. Frequência — decisão arquitetural

### Problema

As datas e sessões das turmas origem e destino dificilmente coincidem. O registro de frequência prova o status do estudante em determinada data/sessão da origem, mas não prova que o professor da turma destino ministrou a mesma aula naquele dia.

A implementação atual de `consolidate_student_movement()` pode criar no destino um documento de frequência usando a data da origem. Isso é aceitável apenas no legado de continuidade existente; é **expressamente proibido** para a nova retificação.

### DEC-03 — `attendance` continua sendo a verdade do diário da turma

Nenhum documento histórico de `attendance` da origem será convertido em documento de aula do destino.

Na origem:

- localizar cada documento cujo `records[]` contenha o estudante;
- snapshotar documento/record/proveniência;
- remover **somente** o elemento do estudante em `records[]`;
- preservar aula, data, professor, componente e frequência dos demais estudantes;
- nunca excluir o documento inteiro apenas porque o estudante foi retificado.

No destino:

- NÃO inserir frequência histórica falsa no diário;
- registrar a evidência individual em uma nova estrutura administrativa: `attendance_rectifications`.

### 7.1 Modelo lógico proposto: `attendance_rectifications`

Campos mínimos propostos:

```json
{
  "id": "uuid",
  "protocol": "RET-...",
  "mantenedora_id": "...",
  "student_id": "...",
  "target_enrollment_id": "...",
  "target_class_id": "...",
  "academic_year": 2026,
  "source_class_id": "...",
  "source_attendance_id": "...",
  "source_date": "YYYY-MM-DD",
  "source_course_id": "...",
  "target_course_id": "...",
  "source_aula_numero": 2,
  "source_assignment_id": "...",
  "status": "P|F|J|L|...",
  "dependency_id": null,
  "source_record_snapshot": {},
  "source_evidence_hash": "sha256...",
  "counting_mode": "administrative_rectification",
  "created_at": "ISO",
  "created_by": "user-id"
}
```

`source_date` e `source_aula_numero` são **proveniência**, não afirmação de sessão no destino.

### FREQ-01 — Proibição de aula fictícia

Nenhuma retificação pode criar, deslocar ou atribuir frequência individual a aula/data da turma destino que não esteja comprovadamente registrada naquela turma.

### FREQ-02 — Preservação integral da evidência

Toda frequência válida da origem deve ser preservada como evidência administrativa contabilizável. Nunca descartar status válido e nunca inventar data/aula.

### FREQ-03 — Origem zerada para o estudante

Após sucesso, nenhum `attendance.records[]` da turma errada no escopo da retificação pode conter `student_id` do estudante.

### FREQ-04 — Outros estudantes imutáveis

A sequência/conteúdo dos registros dos demais estudantes deve permanecer semanticamente idêntica.

### FREQ-05 — Idempotência de evidência

A mesma evidência de origem não pode produzir duas retificações contabilizáveis. Deve existir chave/índice único baseado, no mínimo, em protocolo + `source_attendance_id` + `student_id` ou hash equivalente.

### FREQ-06 — Sem dupla contagem

Se já existir frequência ordinária do estudante no destino para uma data que também possua evidência retificada, o dry-run deve detectar a sobreposição.

V1 recomendada: conflito/ambiguidade de sobreposição bloqueia execução. Não fazer merge automático de statuses concorrentes.

### FREQ-07 — Dependência

Record de frequência com `dependency_id` relacionado ao vínculo incorreto não será convertido automaticamente na V1. Deve aparecer como bloqueio de revisão pedagógica.

### 7.2 Frequência efetiva do estudante

O cálculo da vida escolar deverá distinguir:

- **diário da turma:** somente `attendance` ordinário real;
- **frequência efetiva individual:** `attendance` válido da matrícula correta + `attendance_rectifications` válidas.

Deve surgir um serviço canônico, conceitualmente:

`services/effective_attendance.py`

Responsabilidades:

1. carregar lançamentos ordinários do estudante no escopo correto;
2. carregar evidências administrativas de retificação;
3. normalizar as duas fontes;
4. deduplicar por chave de evidência;
5. fornecer shape único para os cálculos existentes;
6. alimentar a regra diária institucional já consolidada em `attendance_utils.compute_monthly_valid_absences`;
7. expor proveniência (`ordinary` vs `rectification`) para relatórios/documentos.

### 7.3 Consumidores que precisam ser atualizados/testados

No mínimo:

- declaração/relatórios de frequência;
- Histórico Escolar;
- boletim/ficha quando exibirem frequência;
- Bolsa Família;
- CMDE/MIG batch builder;
- Analytics/KPIs de estudante;
- consultas DVD de frequência individual;
- qualquer fechamento/relatório que consulte `attendance` diretamente por estudante.

A F1 deve incluir busca estática de consultas diretas para impedir que um consumidor ignore `attendance_rectifications`.

---

## 8. Notas/conceitos — mapeamento curricular e proveniência

### DEC-04 — Não trocar apenas `class_id`

A nota é vinculada a `course_id`. Uma retificação 6º→7º pode exigir outro cadastro de componente, mesmo quando o nome humano é igual.

### 8.1 Resolver componentes válidos do destino

A F1 deverá criar um resolvedor canônico específico, sem fuzzy-match silencioso.

Hierarquia proposta:

1. **mesmo `course_id`**, somente se o componente for comprovadamente elegível para a série/nível/turma destino;
2. **`course.code` idêntico e único**, dentro do escopo da escola/tenant/nível e série destino;
3. **nome normalizado idêntico e único**, somente quando não houver código confiável e todos os demais atributos forem compatíveis;
4. nenhuma ou múltiplas candidatas ⇒ **bloquear**.

A validação de elegibilidade deve cruzar, conforme disponibilidade:

- `courses.grade_levels`;
- `nivel_ensino`;
- escola/tenant;
- componentes/vínculos reais de `teacher_class_assignments` no destino;
- matriz/currículo aplicável;
- componentes já presentes na matrícula/turma destino.

Não usar similaridade aproximada para autorizar escrita.

### GRD-01 — Mapa 1:1 obrigatório

Todo `course_id` com dado avaliativo a retificar deve possuir exatamente um `target_course_id` válido.

### GRD-02 — Colisão fail-closed

Se origem e destino possuem valor não-nulo para o mesmo período/campo após o mapeamento, a operação bloqueia. Não sobrescrever, não tirar média e não escolher por timestamp.

### GRD-03 — Migração por campo

Quando já existir documento de nota no destino, somente campos vazios poderão receber valores de origem, após validação de ausência de colisão.

### GRD-04 — Proveniência docente preservada

`grade_ownership` existente nos campos da origem deve acompanhar os valores retificados. O professor do destino não se torna autor retroativo da nota.

### GRD-05 — Campos retificados explícitos

A F1 não deve depender apenas de `migrated_from_class_id`. O comportamento atual congela todos os campos não-nulos de um documento marcado como migrado, podendo congelar indevidamente nota legítima já lançada no destino.

Adicionar conceito explícito, por exemplo:

```json
{
  "rectification_protocol": "RET-...",
  "rectified_from_class_id": "...",
  "rectified_from_course_id": "...",
  "rectified_fields": ["b1", "b2"],
  "rectified_at": "ISO"
}
```

O guard de edição deve congelar para professores somente os campos `rectified_fields`; gestão autorizada mantém fluxo explícito de correção/auditoria.

### GRD-06 — Origem zerada

Após a operação aplicada, nenhum documento de `grades` da turma errada no escopo deve continuar representando nota ativa do estudante.

### GRD-07 — Dependências/políticas incompatíveis

`dependency_id`, ownership ambíguo, assignment incompatível ou política avaliativa que não possa ser preservada de forma demonstrável bloqueiam V1.

---

## 9. Conteúdo ministrado

### DEC-05 — `content_entries` não é dado individual do estudante

A retificação de uma matrícula não altera o fato histórico de que a turma origem recebeu determinado conteúdo naquela aula.

Portanto:

- não copiar conteúdo para o 7º ano por causa de um estudante;
- não excluir conteúdo do 6º ano;
- não marcar `content_entries` como retificado.

A vida escolar individual deve ser corrigida por matrícula, frequência efetiva, notas e documentos — não por reescrita do diário coletivo.

---

## 10. Histórico e trilha administrativa

### DEC-06 — Vida escolar oficial e auditoria são planos distintos

A vida escolar oficial deve deixar de afirmar que a turma errada foi percurso real.

A trilha administrativa deve preservar a existência da correção.

### 10.1 `student_history`

Não apagar entradas históricas silenciosamente.

Quando uma entrada interna de matrícula/movimentação for comprovadamente produto do vínculo documental incorreto, a F1 poderá marcá-la como, por exemplo:

```json
{
  "rectified": true,
  "rectification_protocol": "RET-...",
  "visibility": "administrative_only"
}
```

O documento original permanece auditável, mas não deve contaminar documentos escolares oficiais.

Registros de histórico importado/manual com semântica externa não serão alterados automaticamente.

### HIST-01

Após retificação, o Histórico Escolar oficial para o ano/série deve derivar exclusivamente da matrícula correta e das evidências pedagógicas válidas correspondentes.

### HIST-02

A retificação administrativa não pode aparecer como se o estudante tivesse cursado e depois sido transferido/remanejado do ano errado.

---

## 11. Documentos emitidos e snapshots

### DOC-01 — Imutabilidade

Documento verificável ou snapshot publicado nunca será reescrito para esconder o erro.

### DOC-02 — Inventário obrigatório no dry-run

O dry-run deve procurar, por estudante/turma/período e relações de snapshot/job:

- `verifiable_documents`;
- `diary_snapshots`;
- `document_render_jobs`/arquivos;
- histórico/boletim/ficha verificáveis;
- outros documentos oficiais indexados por student/class/snapshot.

### DOC-03 — Tratamento explícito

Documento incompatível com a matrícula retificada deve ser:

1. identificado;
2. marcado como revogado ou superseded conforme natureza;
3. vinculado ao protocolo/motivo da retificação;
4. reemitido a partir do estado correto quando aplicável.

Nunca alterar hash/payload do documento antigo.

### DOC-04 — Rollback e irreversibilidade

Como revogação de documento pode ser institucionalmente irreversível, rollback automático da retificação somente será elegível enquanto nenhuma consequência documental irreversível tiver ocorrido — ou deverá adotar política de correção para frente (nova supersessão), nunca “desrevogar” silenciosamente.

---

## 12. AEE, Bolsa Família, atestados e dados student-anchored

### DEC-07 — Preservar por padrão

Na V1, mesma escola/tenant/ano:

- AEE permanece intacto e fora da mutação funcional desta iniciativa;
- Bolsa Família tracking permanece intacto;
- atestados permanecem vinculados ao estudante/data;
- outros dados genuinamente student-anchored são preservados.

O efeito nos módulos sociais ocorre apenas porque seus cálculos de frequência deverão consumir a frequência efetiva canônica.

Qualquer registro AEE que possua referência de turma inconsistente deverá aparecer no diagnóstico, mas **não será automaticamente alterado** sem fase/autorização específica para AEE.

---

## 13. Segurança, RBAC e multi-tenancy

### RBAC-01

Perfis de produção autorizados à futura Retificação:

- `super_admin`;
- `admin`;
- `gerente`.

`admin_teste` não fica implicitamente autorizado nesta F0; eventual inclusão exige decisão explícita ou confinamento ao sandbox.

### RBAC-02

A Transferência Institucional de Turmas existente continua `super_admin only`. Nenhuma mudança de rota/UI da retificação pode ampliar o endpoint `/api/admin/school-transfer`.

### MT-01

Toda rota operacional usa o contexto MT-1 canônico. `super_admin` deve selecionar exatamente uma mantenedora ativa.

### MT-02

`admin` e `gerente` não podem sobrescrever tenant por header e operam somente na própria mantenedora.

### MT-03

Origem/destino/documentos sem `mantenedora_id` resolvível ou pertencentes a outro tenant bloqueiam a operação. Não existe fallback cross-tenant.

### SEC-01 — Reautenticação

Execução e rollback exigem reautenticação por senha imediatamente antes da ação. Senha nunca é persistida/logada.

### SEC-02 — Justificativa

`rationale` obrigatório, recomendado mínimo de 30 caracteres.

### SEC-03 — Confirmação textual

Frase proposta para execução:

`CONFIRMO A RETIFICAÇÃO DA MATRÍCULA`

Frase proposta para rollback:

`CONFIRMO A REVERSÃO DA RETIFICAÇÃO`

### SEC-04 — Base documental

A execução deve possuir referência administrativa/documental da correção. Recomendação: `documentary_basis` estruturado + possibilidade de `file_id` de evidência. A obrigatoriedade de anexo físico é decisão humana pendente (§22).

---

## 14. Concorrência, stale clients e barreira pós-retificação

Corrigir dados no banco não é suficiente. Um navegador/PWA com cache antigo pode tentar sincronizar novamente frequência ou nota na turma errada.

### DEC-08 — Write barrier permanente

A F1 deve criar um guard canônico de escopo acadêmico que consulte retificações aplicadas antes de aceitar escrita de matrícula/frequência/nota para o estudante na turma retificada como origem.

Exemplo de resposta:

```json
HTTP 409
{
  "detail": {
    "code": "ENROLLMENT_RECTIFIED",
    "protocol": "RET-...",
    "student_id": "...",
    "source_class_id": "...",
    "target_class_id": "..."
  }
}
```

O guard deve valer para:

- HTTP normal;
- sincronização offline;
- lote de notas;
- gravação canônica de frequência;
- qualquer writer que possa reintroduzir o vínculo errado.

A F2 invalida/recarrega caches de UI, mas o backend continua sendo a proteção definitiva.

---

## 15. Atomicidade: saga compensável, não transação presumida

### DEC-09 — Não depender de Mongo transaction

A baseline de produção não demonstra replica set/transações multi-documento. A implementação deve funcionar com operações atômicas por documento e uma saga persistida.

### 15.1 Reutilizar `with_critical_mutation`

Target recomendado:

`retificacao_enturmacao:{mantenedora_id}:{student_id}:{academic_year}`

Coleções auxiliares propostas:

- `enrollment_rectification_runs`;
- `enrollment_rectification_locks`;
- `enrollment_rectification_idempotency`.

### 15.2 Estado principal da operação

Coleção proposta: `enrollment_rectifications`.

Estados sugeridos:

- `dry_run`;
- `prepared`;
- `applying`;
- `core_applied`;
- `document_resolution_pending`;
- `applied`;
- `rollback_pending`;
- `rolled_back`;
- `failed_needs_recovery`.

Cada fase concluída deve possuir checkpoint persistido e hash dos objetos relevantes.

### 15.3 Snapshots

Para evitar limite de 16 MB e permitir rollback por documento, usar coleção separada:

`enrollment_rectification_snapshots`

Um snapshot por objeto afetado, por exemplo:

```json
{
  "protocol": "RET-...",
  "collection": "attendance",
  "document_key": "attendance-id",
  "scope": "student-record",
  "before": {},
  "before_hash": "...",
  "after_hash": "...",
  "captured_at": "ISO"
}
```

Acesso a esses snapshots é administrativo e tenant-scoped; não são documentos públicos.

### 15.4 Sequência recomendada da saga

1. **Dry-run read-only** — inventário, mapa curricular, blockers, hash de precondições.
2. **Lock + revalidação** — impedir TOCTOU.
3. **Snapshot PREPARED** — matrícula, projeção, notas, records de frequência, histórico e manifesto documental.
4. **Retificar matrícula canônica** e reconstruir projeção do estudante.
5. **Migrar notas** com mapa/colisão/proveniência.
6. **Extrair frequência individual da origem** para `attendance_rectifications` e remover somente os records do estudante.
7. **Marcar histórico interno aplicável** como retificado/admin-only.
8. **Pós-validação estrutural**.
9. Marcar `core_applied`.
10. **Resolver documentos/snapshots** conforme manifesto.
11. **Pós-validação final** + recibo/protocolo.
12. Marcar `applied`.

Falha em qualquer etapa deve produzir estado explícito; retry com mesma Idempotency-Key retoma de checkpoint seguro ou executa compensação prevista. Nunca continuar “best effort” silenciosamente.

---

## 16. Pós-condições formais

Uma execução somente pode terminar `applied` quando TODAS forem verdadeiras.

### POST-01 — Matrícula

- uma única matrícula regular ativa do estudante/ano;
- matrícula aponta ao destino;
- `students.class_id` projeta o destino;
- identidade/data/número preservados conforme plano.

### POST-02 — Turma errada sem vínculo acadêmico oficial

No escopo do ano retificado:

- zero matrícula regular do estudante apontando à origem;
- zero `attendance.records[].student_id` na origem;
- zero `grades` do estudante na origem;
- zero projeção ativa para origem;
- zero artefato vivo derivado que ainda apresente origem como matrícula válida sem ser marcado para resolução.

### POST-03 — Destino íntegro

- notas esperadas presentes com mapa/proveniência corretos;
- frequência administrativa preservada em ledger sem criar aulas fictícias;
- frequência ordinária do destino inalterada para os demais estudantes;
- histórico oficial resolve a série/turma correta.

### POST-04 — Preservações

- `content_entries` das duas turmas inalterados pela retificação;
- dados AEE não alterados;
- Bolsa Família tracking não alterado;
- atestados não alterados;
- documentos antigos nunca reescritos silenciosamente.

### POST-05 — Resíduos

Detector de resíduos deve retornar `0` para vínculos acadêmicos vivos do estudante com a turma errada, salvo estruturas explicitamente classificadas como auditoria imutável/administrativa.

---

## 17. Rollback

### DEC-10 — Rollback não é garantido após qualquer consequência externa/imutável

O endpoint de rollback deve primeiro calcular elegibilidade.

Elegível somente quando, entre outros:

- dentro da janela definida;
- nenhuma nova nota/frequência legítima foi lançada no destino após a retificação ou toda mudança é comprovadamente compensável;
- hashes/versões dos documentos tocados permanecem compatíveis;
- não houve nova movimentação/reclassificação;
- não houve resolução documental irreversível incompatível;
- nenhuma operação concorrente alterou matrícula/grades/attendance relacionados.

Rollback elegível:

- restaura matrícula/projeção do snapshot;
- restaura grades da origem/destino conforme snapshot;
- reinsere o student-record original em cada documento de frequência sem alterar os demais estudantes;
- remove/desativa `attendance_rectifications` criadas pelo protocolo;
- restaura marcações administrativas reversíveis;
- grava auditoria completa.

Se inelegível, o sistema exige **nova retificação/correção para frente**, não força restauração destrutiva.

Janela inicial recomendada: 7 dias, alinhada ao precedente da Transferência Institucional, mas a decisão final é humana (§22).

---

## 18. Endpoints propostos para F1

Prefixo recomendado:

`/api/admin/enrollment-rectification`

### `POST /dry-run`

Entrada mínima:

```json
{
  "student_id": "...",
  "destination_class_id": "..."
}
```

Origem deve ser inferida da matrícula regular canônica, não aceita livremente do cliente sem validação.

Retorno:

- `dry_run_token` + expiração;
- matrícula origem/destino;
- contagens por coleção;
- mapa curricular;
- manifesto de notas;
- manifesto de frequências;
- sobreposições/conflitos;
- dependências/eventos;
- documentos/snapshots afetados;
- bloqueios/warnings;
- pós-condições esperadas;
- frase de confirmação.

### `POST /execute`

Entrada:

- `dry_run_token`;
- senha;
- rationale;
- confirmation_text;
- documentary_basis;
- header `Idempotency-Key`.

### `GET /{protocol}`

Estado, fases, resultado e resíduos (sem expor snapshot sensível indevido).

### `GET /{protocol}/rollback-eligibility`

Somente leitura; retorna razões explícitas.

### `POST /{protocol}/rollback`

Senha + rationale + frase explícita + idempotência.

### `GET /{protocol}/receipt`

Recibo administrativo verificável, separado de documento escolar da vida acadêmica.

---

## 19. UX proposta para F2

Não ampliar silenciosamente a permissão da página existente de Transferência Institucional.

Opção recomendada:

### Central “Movimentações Acadêmicas”

Rota neutra futura, por exemplo `/admin/movimentacoes`, com cards separados:

1. **Transferência Institucional de Turmas** — `super_admin` only;
2. **Retificação de Matrícula/Turma** — `super_admin/admin/gerente`.

Fluxo de Retificação:

1. localizar estudante;
2. mostrar matrícula regular atual;
3. selecionar turma correta elegível;
4. executar dry-run;
5. exibir relatório de impacto por categoria;
6. bloquear execução enquanto houver pendência crítica;
7. apresentar mapa de componentes;
8. apresentar frequência como “evidência administrativa”, deixando claro que datas/sessões não serão fabricadas no destino;
9. mostrar documentos que serão invalidados/substituídos;
10. coletar base documental e justificativa;
11. reautenticar;
12. exigir frase explícita;
13. executar e acompanhar fases;
14. mostrar pós-validação origem=zero/destino=íntegro;
15. emitir protocolo/recibo;
16. oferecer rollback somente quando elegível.

Se for decidido manter `/admin/transferencias` como hub, o componente/route guard deve ser refatorado para separar permissões sem alterar o backend `school-transfer`.

---

## 20. Matriz de testes obrigatórios para F1

### 20.1 Contrato básico

1. estudante sintético 6º→7º, mesma escola/tenant/ano;
2. preserva `enrollment.id`, número, data e ano;
3. `students` passa a projetar destino;
4. origem deixa de existir como matrícula acadêmica oficial.

### 20.2 Frequência

5. múltiplas aulas/datas/componentes na origem;
6. datas que não existem no destino;
7. prova de que **nenhum documento de `attendance` é fabricado no destino**;
8. student-record removido da origem, demais estudantes byte/semanticamente preservados;
9. ledger `attendance_rectifications` recebe todas as evidências válidas;
10. idempotência não duplica evidência;
11. sobreposição com frequência ordinária do destino é detectada e bloqueada;
12. `dependency_id` relacionado bloqueia;
13. cálculo mensal/anual preserva resultado institucional sem dupla contagem;
14. Bolsa Família e CMDE enxergam frequência efetiva correta;
15. replay offline para origem após retificação retorna 409.

### 20.3 Notas

16. mesmo `course_id` válido para destino;
17. mapeamento por código único;
18. mapeamento por nome normalizado único quando permitido;
19. 0 correspondências bloqueia;
20. >1 correspondência bloqueia;
21. colisão de valor no destino bloqueia sem mutação parcial;
22. campos vazios do destino recebem somente valores não conflitantes;
23. `grade_ownership` original preservado;
24. somente `rectified_fields` ficam congelados para professor;
25. campos futuros legítimos do destino continuam editáveis;
26. origem fica sem documento de nota ativo do estudante.

### 20.4 Histórico/documentos

27. Histórico Escolar mostra somente série correta;
28. nenhuma linha artificial “6º → 7º” como percurso real;
29. snapshot publicado permanece imutável;
30. documento verificável afetado é detectado;
31. supersessão/revogação segue política e nunca altera hash antigo.

### 20.5 Preservações

32. `content_entries` inalterado;
33. AEE inalterado;
34. Bolsa tracking inalterado;
35. atestados inalterados.

### 20.6 Segurança

36. `super_admin` sem tenant selecionado → fail-closed;
37. tenant A não consegue retificar estudante/turma B;
38. `admin` restrito ao próprio tenant;
39. `gerente` restrito ao próprio tenant;
40. perfil não autorizado → 403;
41. senha errada → operação não iniciada;
42. frase errada → operação não iniciada;
43. dry-run expirado → reprocessar;
44. mudança entre dry-run e execute → revalidação bloqueia.

### 20.7 Saga/concorrência

45. mesma Idempotency-Key retorna mesmo protocolo;
46. lock concorrente → 409;
47. falha simulada após matrícula;
48. falha simulada após notas;
49. falha simulada após frequência;
50. retry retoma/compensa sem duplicar;
51. pós-validação com resíduo força estado `failed_needs_recovery`, nunca `applied`.

### 20.8 Rollback

52. rollback elegível restaura snapshot;
53. nova nota legítima após retificação torna rollback inelegível;
54. consequência documental irreversível torna rollback inelegível/conduz a correção para frente;
55. rollback idempotente.

---

## 21. Plano incremental

### F1.0 — Contrato executável e infraestrutura

- modelos DTO;
- serviço puro de dry-run;
- coleção de operações/snapshots;
- `with_critical_mutation`;
- RBAC/MT-1;
- nenhuma execução real ainda.

### F1.1 — Matrícula + notas em sandbox

- rewrite canônico da matrícula;
- rebuild projection;
- course mapper fail-closed;
- migração de grades + `rectified_fields`;
- testes sintéticos.

### F1.2 — Frequência retificada

- `attendance_rectifications`;
- extração segura de `records[]`;
- effective attendance SSoT;
- consumidores institucionais;
- write barrier anti-replay.

### F1.3 — Documentos, pós-validação e rollback

- manifesto documental;
- supersessão/revogação governada;
- detector de resíduos;
- rollback eligibility/compensação;
- recibo/protocolo.

### F2 — Interface administrativa

- central de movimentações;
- wizard;
- dry-run visual;
- RBAC separado;
- acompanhamento do protocolo;
- cache invalidation.

### F3 — Homologação

Executar somente com dados sintéticos/isolados:

- cenário completo 6º→7º;
- datas de frequência não coincidentes;
- conflitos propositais;
- documentos emitidos;
- falhas em cada checkpoint;
- rollback.

Somente depois de F3 aprovada poderá ser avaliada uma retificação real em produção, mediante autorização humana específica para o protocolo exato.

---

## 22. Decisões humanas pendentes

A arquitetura técnica recomenda as opções abaixo, mas a implementação deve aguardar decisão explícita quando necessário:

1. **Base documental:** basta referência administrativa estruturada ou será obrigatório anexar arquivo comprobatório (`file_id`)?  
   **Recomendação:** exigir referência e tornar anexo obrigatório quando houver documento formal disponível.

2. **`admin_teste`:** deve executar retificação fora do sandbox?  
   **Recomendação:** NÃO em produção; manter apenas `super_admin/admin/gerente`.

3. **Janela de rollback:** 7 dias?  
   **Recomendação:** 7 dias como teto, sempre subordinado à elegibilidade por estado/hash.

4. **UX:** manter `/admin/transferencias` como hub ampliado ou criar `/admin/movimentacoes`?  
   **Recomendação:** criar hub neutro `/admin/movimentacoes`, evitando ampliar semanticamente/visualmente uma rota hoje associada a operação `super_admin only`.

5. **Documentos já publicados:** bloquear toda retificação até a F1.3 ou permitir `core_applied` com pendência documental?  
   **Recomendação:** a operação não pode atingir status final `applied` enquanto houver obrigação documental crítica. Pode existir estado intermediário `document_resolution_pending`.

---

## 23. Critérios de saída da F0

A F0 está pronta para aprovação quando:

- este contrato for revisado;
- decisões humanas pendentes forem resolvidas ou explicitamente postergadas;
- nenhum código funcional tiver sido incluído no PR;
- nenhuma mutação tiver ocorrido em produção;
- o próximo PR F1 tiver escopo fechado e matriz de testes derivada deste documento.

### Confirmação de segurança desta F0

Esta etapa:

- NÃO altera estudantes;
- NÃO altera matrículas;
- NÃO altera frequência;
- NÃO altera notas;
- NÃO altera AEE;
- NÃO altera banco/schema/índices;
- NÃO cria endpoint funcional;
- NÃO executa script de mutação;
- NÃO realiza merge;
- NÃO realiza deploy.

---

## 24. Referências técnicas auditadas

- `backend/services/enrollment_service.py`
- `backend/routers/students.py`
- `backend/services/pedagogical_consolidation.py`
- `backend/routers/attendance.py`
- `backend/services/attendance_assignment_scope.py`
- `backend/services/attendance_utils.py`
- `backend/routers/grades.py`
- `backend/services/grade_assignment_scope.py`
- `backend/services/history_consolidator.py`
- `backend/services/verifiable_docs_service.py`
- `backend/services/diary_snapshot_service.py`
- `backend/lib/critical_mutation.py`
- `backend/tenant_scope.py`
- `backend/models.py`
- `backend/startup/indexes.py`
- `docs/ACADEMIC_EVENT_CONTRACT.md`
- `memory/AUDITORIA_MOVIMENTACAO_ALUNOS.md`
- `memory/AUDITORIA_TRANSFERENCIA_INSTITUCIONAL.md`
- `memory/audit/05_BANCO_DADOS.md`
- `docker-compose.coolify.yml`

---

**Resultado da F0:** o SIGESC deve implementar `retificacao_enturmacao` como **correção administrativa canônica e compensável**, separada das movimentações acadêmicas temporais. A matrícula canônica é corrigida em lugar; a frequência individual é retirada da turma errada sem fabricar aulas no destino e preservada em ledger administrativo contabilizável; notas são transferidas apenas mediante mapa curricular 1:1 e proveniência por campo; documentos emitidos permanecem imutáveis e são superseded/revogados; toda operação é tenant-scoped, idempotente, bloqueada por concorrência, auditada e sujeita a pós-validação origem=zero/destino=íntegro.