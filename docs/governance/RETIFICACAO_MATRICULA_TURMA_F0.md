# F0 — Retificação de Matrícula/Turma por Erro Documental: Auditoria Read-Only e Contrato de Domínio

> **Status:** AUDITORIA (sem implementação). Nenhum código funcional, endpoint, writer, migration ou índice foi criado/alterado nesta etapa.
> **Base:** `main` em `9954fe5a687a5cf4e661aec11725a7520e23c6f6`.
> **Escopo:** Issue #346. Esta operação **não** é o remanejamento atual e **não** é a Transferência Institucional de Turmas.
> **Método:** leitura de código, modelos, routers, services e contratos vigentes (sem execução em produção, sem dados reais de estudantes).

---

## 1. Estado atual comprovado por código

### 1.1 O mecanismo canônico de movimentação hoje é "copy-data" (aditivo, nunca remove)

Remanejamento, progressão e reclassificação percorrem o **mesmo caminho de código**: `PUT /api/students/{id}` (`backend/routers/students.py:1695-1791`, `action_hint` ∈ `{remanejamento, progressao, reclassificacao}`) seguido da consolidação pedagógica canônica `consolidate_student_movement()` (`backend/services/pedagogical_consolidation.py:16-102`), também exposta diretamente em `POST /api/students/{student_id}/copy-data` (`students.py:2308-2359`).

O próprio docstring do serviço declara os dois princípios de design (`pedagogical_consolidation.py:1-8`):

> **Princípio 1 (Preservação):** a turma de ORIGEM nunca é alterada/removida.
> **Princípio 2 (Continuidade):** a turma de DESTINO recebe cópia idempotente de frequência, notas e conteúdo do aluno.

Comportamento comprovado (`pedagogical_consolidation.py:29-99`):
- **Frequência:** para cada documento `attendance` da origem contendo um `records[]` do aluno, extrai só o registro do aluno, marca `migrated_from_class_id`/`migrated_at`, e faz merge em um documento de destino localizado por `class_id+date+academic_year` (**sem** filtrar por `course_id`/`aula_numero` — risco já identificado, ver §3). A origem nunca é tocada.
- **Notas:** se já existe registro no destino para `class_id+student_id+course_id+academic_year`, só preenche campos `None` (nunca sobrescreve valor já lançado); senão, insere cópia completa marcada como migrada. Origem nunca é tocada.
- **Conteúdo (`content_entries`):** copia por `(class_id, course_id, date)` se ainda não existir no destino. Origem nunca é tocada.

Este comportamento está normatizado como princípio arquitetural **congelado** em `docs/ACADEMIC_EVENT_CONTRACT.md` (V1, `contract_version: 1`, `status: FROZEN`, fev/2026):

> §1: **"Movimentações escolares NÃO removem o estudante da turma de origem."**
> §6.1: "Proibido mover registros históricos entre turmas."
> §6.4: "Proibido apagar vínculo do estudante com turma de origem."
> §16: "Nenhum evento acadêmico pode causar perda documental, sobrescrita histórica ou exclusão silenciosa de frequência/notas."

**Achado crítico:** este contrato define `db.academic_events` como fonte única de verdade para bloqueios/lentes temporais (`resolve_student_class_state`, `utils/academic_event_lens.py`; fechamento composto em `utils/temporal_closure.py` + `routers/closure.py`, somente leitura), com testes próprios (`backend/tests/test_academic_event_lens.py`, `test_temporal_closure.py`, `test_academic_events_e2e_http.py`). **Porém está desconectado da produção real**: nem `students.py` nem `enrollment_service.py` escrevem em `db.academic_events` — confirmado por comentário explícito em `students.py:2162-2164` ("NÃO cria nenhum bloqueio acadêmico... não há `academic_events` associados"). O contrato também especifica que a matrícula de origem deveria receber `status='moved_out'` (§6.4, §16.3) — valor que **não existe** no enum real (`EnrollmentBase.status`, `backend/models.py:1742`: `active|completed|cancelled|transferred|relocated|progressed|dropout`). Ou seja: existe um contrato normativo aprovado e testado, mas **arquiteturalmente dormente** — um artefato paralelo ao código que efetivamente roda.

### 1.2 Por que o comportamento atual (copy-data) NÃO serve para retificação

O copy-data e o `ACADEMIC_EVENT_CONTRACT.md` foram desenhados para **movimentações legítimas**: o aluno **de fato** cursou a turma de origem por um período real, e a exigência legal/pedagógica é preservar essa autoria e esse histórico para sempre. Preservar a origem é, nesse caso, o comportamento **correto**.

O caso motivador desta Issue é o oposto: a estudante **nunca deveria ter tido vínculo real** com a turma de origem (6º ANO A) — foi um erro documental de matrícula. Preservar o vínculo na origem, copiar frequência/notas "herdadas", manter `enrollments` de origem com status ativo-histórico (`relocated`/`progressed`) — tudo isso **perpetua um vínculo que nunca deveria ter existido**, viola o objetivo do caso motivador ("a turma incorreta deixe de possuir vínculos acadêmicos da estudante") e pode gerar documentos oficiais (histórico, boletim) que **mentem sobre o percurso real** da estudante.

Logo: **não podemos reutilizar `consolidate_student_movement`/copy-data como está**. A retificação precisa de um motor **próprio**, com semântica de **correção** (mover e depois zerar a origem, ou anular/reclassificar o vínculo indevido), não de **continuidade** (copiar e preservar ambos os lados). Isso é consistente com a orientação de SSoT do CLAUDE.md §3: não duplicar comportamento existente quando a semântica de domínio é distinta.

### 1.3 O precedente estrutural mais próximo é a Transferência Institucional de Turmas

`backend/routers/school_transfer.py` (751 linhas) já implementa uma re-homing **sem duplicação** (rehoma `school_id` mantendo `class_id` estável, sem copiar registros) para as coleções `CLASS_ANCHORED` (`students, enrollments, attendance, grades, content_entries, student_dependencies, teacher_class_assignments`, `school_transfer.py:41-44`) e preserva as `STUDENT_ANCHORED` (AEE, `bolsa_familia_tracking`, `school_transfer.py:46-49`) intactas. Já possui: dry-run com token, `idempotency_key`, reautenticação por senha, frase de confirmação literal (`CONFIRMATION_PHRASE = "CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL"`, linha 51), lock por operação (`transfer_in_progress` no documento `classes`, linhas 326/341/384), snapshot pré-mutação para rollback compensatório manual (linhas 305-324), janela de rollback de 7 dias (`ROLLBACK_WINDOW_DAYS=7`, linha 53) e trilha de auditoria própria (`school_transfer_audit`). É restrito a `super_admin` (`_require_super_admin`, linhas 85-89, aplicado em 182/242/454/466/525/544/700) e move a **turma inteira** entre escolas — não um único aluno entre turmas da mesma escola.

Este é o padrão estrutural mais próximo do que a retificação precisa (correção sem duplicação, com trilha auditável), mas sua granularidade (turma inteira, entre escolas) e seu RBAC (super_admin only) **não** se aplicam diretamente — a retificação opera em **um único aluno**, dentro da **mesma escola/mantenedora/ano letivo**, e precisa ser acessível também a `admin`/`gerente`.

### 1.4 Comparativo com os fluxos citados na Issue

| Fluxo | Código | Âncora | Semântica | RBAC hoje |
|---|---|---|---|---|
| Remanejamento/Progressão/Reclassificação | `students.py:1695-1791` + `pedagogical_consolidation.py` | `student_id` | **Copy-data aditivo** — origem preservada, destino recebe cópia | admin/admin_teste/super_admin/gerente/secretario (`copy-data`, students.py) |
| Transferência Institucional de Turmas | `routers/school_transfer.py` | `class_id` (turma inteira) | **Re-homing sem cópia** — `school_id` migra, `class_id` estável | `super_admin` only (`_require_super_admin`) |
| Reconstrução de Histórico Pedagógico | `routers/history_reconstruction.py` | `student_id`, para dados legados | Reprocessa idempotentemente via `consolidate_student_movement` — nunca toca origem | `super_admin` only |
| `academic_events` (contrato) | `docs/ACADEMIC_EVENT_CONTRACT.md` + `routers/academic_events.py` | `student_id` + evento temporal | Lente/projeção — nunca duplica fisicamente, nunca remove vínculo de origem | Contrato prevê `super_admin/admin/gerente/secretario` para alteração de evento (§10.2), **mas está desconectado da produção** |
| **Retificação de Matrícula/Turma (proposta)** | inexistente | `student_id`, vínculo único errado | **Correção — remove/anula o vínculo indevido na origem**, preserva proveniência só em trilha administrativa | proposto: `super_admin/admin/gerente`, mesma mantenedora/escola/ano |

---

## 2. Inventário de coleções/estruturas afetáveis

Matriz **coleção/estrutura × chave de vínculo × ação futura proposta × risco**. Ações: `move` (transferir o vínculo ativo para o destino), `rewrite` (corrigir campo denormalizado), `preserve` (manter como está, sem tocar), `revoke` (anular/invalidar), `ignore` (fora do escopo — não anexado por class_id), `manual_review` (exige decisão humana caso a caso).

| Coleção/estrutura | Chave de vínculo | Ação futura proposta | Risco |
|---|---|---|---|
| `students` (`class_id` projetado) | `student_id`, `class_id`, `school_id` | `rewrite` — projeção recalculada via `rebuild_student_home_projection` (`enrollment_service.py:199`) | Baixo — já é fonte derivada, não SSoT |
| `enrollments` | `student_id`, `class_id`, `school_id`, `academic_year`, `enrollment_number` | `manual_review` → provável `revoke` da matrícula errônea (não `cancelled` genérico — precisa de status/motivo específico de retificação) + `move`/criação de matrícula correta preservando `enrollment_number`/`enrollment_date` originais quando possível | **Alto** — hoje não existe status de enum para "matrícula anulada por erro documental"; `router/enrollments.py:193-205` já bloqueia troca de `class_id` via `PUT` genérico (por design) |
| `attendance` (`records[].student_id`) | `class_id`, `date`, `course_id`, `aula_numero`, `records[].student_id` | `move` seletivo do `records[]` do aluno (extração + remoção da origem) + `manual_review` para correspondência de aula real no destino (ver §6, FREQ-01/02/03) | **Alto** — granularidade fina (array aninhado, documento compartilhado por turma inteira); nenhuma auto-transação disponível (ver §10) |
| `grades` | `student_id`, `class_id`, `course_id`, `academic_year`, `dependency_id?` | `manual_review` por componente — `move` só quando mapeamento curricular origem→destino for 1:1 comprovado (ver §7); senão `preserve` (registro fica arquivado, fora do boletim ativo do destino) | **Alto** — 1 doc por (aluno,turma,componente,ano); sem campo de bimestre separado; colisão no destino é possível |
| `student_dependencies` | `student_id`, `class_id`, `course_id`, `status` | `manual_review` — dependência foi aberta contra um vínculo (turma/componente) que pode não existir no destino | Médio — poucos registros, mas decisão pedagógica sensível (reprovação em componente específico) |
| `content_entries` | `class_id`, `course_id`, `date`, `teacher_id`, `assignment_id?` (DVD) | `preserve` — é diário **da turma**, não do aluno; conteúdo lançado na turma errada não pertence ao aluno individualmente e não deve ser "movido" para o destino (o professor do destino não ministrou aquele conteúdo àquele aluno) | Médio — diferente de `attendance`/`grades`: aqui a ação correta é **não mover nada**, só quebrar o vínculo do aluno com a lista de presença da turma errada (efeito indireto via `enrollments`/`students`) |
| `academic_events` (contrato, não plugado na produção) | `student_id`, `origin_class_id`, `destination_class_id`, `event_type` | `manual_review` — decidir se a retificação usa um novo `event_type` (`retificacao_enturmacao`) dentro deste contrato (exigiria bump de `contract_version`, §14 do contrato) OU se cria trilha própria fora dele, dado que o contrato está desconectado da produção real hoje | Médio-alto — decisão arquitetural (§15 questões humanas) |
| `student_history` | `student_id`, `records[].serie`, `action_date` | `manual_review`/`rewrite` — usado tanto para consolidação do histórico oficial quanto para trava de edição por bimestre (`attendance.py:571-599`, `grades.py:280-386`); precisa de uma entrada nova de retificação para não confundir com movimentações reais | Alto — impacta histórico oficial e travas de edição |
| `audit_logs` | `document_id`, `collection`, `user_id`, `school_id` | `preserve`/append — toda mutação da retificação deve gerar entradas aqui (padrão existente) | Baixo (é o próprio mecanismo de auditoria) |
| Documentos verificáveis (`verifiable_documents`) | `entity_type`, `entity_id`, `student_id`, `school_id`, `public_hash` | `manual_review` → `revoke`/`supersede_document` quando o documento foi emitido citando a turma errada (ver §8) | **Alto** — documento já pode ter sido entregue à família/órgão externo |
| `attendance` agregações/relatórios (`bulletin_builder.py`, `analytics.py`, `monthly_report_service.py`, `history_consolidator.py`, `diary_snapshot_service.py`) | leem `attendance` ao vivo, filtram por `class_id`+`student_id` em memória | `ignore` (sem persistência própria) — mas **dependem** de a correção em `attendance` estar certa; nenhuma invalidação de cache é necessária pois não há cache dedicado | Médio — qualquer reader que ainda não trate frequência administrativa (ver §6) pode sub/super contar |
| DVD (`attendance_dvd.py`, `grades_dvd.py`, `attendance_historical_backfill_dvd.py`) | `assignment_id` (vínculo professor+turma+componente+ano, `TeacherAssignment`) | `manual_review` — se o vínculo DVD (assignment) da origem não existir/for incompatível no destino, a retificação de notas/frequência sob DVD é **bloqueada** (fail-closed) até haver assignment correspondente | Alto — protegido por CLAUDE.md §4 (DVD é migração/cutover controlado) |
| AEE (`aee_v2/*`) | `student_id` (sem `class_id` na identidade — confirmado em `aee_v2/contracts.py:173`, `aee_v2/repository.py:153`) | `preserve` — confirma-se student-anchored; **nenhuma alteração funcional prevista nesta feature** (AEE é módulo protegido, CLAUDE.md §4) | Baixo para a retificação em si; alto se qualquer implementação futura tocar AEE sem autorização |
| Bolsa Família (`bolsa_familia_tracking`) | `student_id` (chave dedup `school_id_student_id_month`); `class_id` só como filtro de consulta efêmero | `preserve` — student-anchored, sem FK física para `class_id` | Baixo |
| `teacher_class_assignments` / `TeacherAssignment` (vínculo DVD) | `staff_id`, `class_id`, `course_id`, `academic_year` | `ignore` (não é vínculo do aluno) — mas é a chave que valida se destino tem professor/componente ativo para lançar retificação de notas/frequência | Médio — pré-condição de viabilidade, não alvo direto de mutação |
| `classes` (`school_history[]` etc.) | `class_id`, `school_id` | `ignore` — a retificação não move a turma, só o vínculo de um aluno | Baixo |
| Caches/materializações (`business_intelligence/`, dashboards, `analytics.py` agregações) | leem `attendance`/`grades`/`enrollments` ao vivo | `ignore` — nenhuma projeção materializada persistente foi encontrada; toda leitura é live query | Baixo, condicionado à correção de origem estar completa |
| `student_history` usado por travas de edição (`_block_if_changing_migrated_attendance`, freeze por bimestre) | `student_id`, `class_id`, `action_type`, `action_date` | `manual_review` — precisa de um `action_type` próprio (`retificacao_matricula`) para não ser confundido com remanejamento real nas travas de bimestre | Médio |

---

## 3. Riscos e lacunas identificados

1. **Sem transação multi-documento disponível.** `AsyncIOMotorClient(mongo_url)` (`backend/server.py:138-139`) conecta em MongoDB **standalone** — nenhum `docker-compose*.yml` (produção, Coolify, homologação) configura `--replSet`, e não há `replicaSet=` em nenhuma connection string. Busca por `start_session`/`start_transaction`/`with_transaction` em `backend/` (fora de testes) retornou **zero ocorrências**. Logo, a retificação **não pode presumir atomicidade ACID** — precisa de saga/compensação manual, como já faz `school_transfer.py` (snapshot + lock + rollback compensatório manual, sem auto-rollback em falha parcial).
2. **`attendance.records[]` é aninhado e compartilhado por turma inteira.** Mutação segura exige `arrayFilters`/leitura-modificação-escrita por `student_id`, nunca `update_many` cru sobre o documento (confirmado pelo padrão já usado em `consolidate_student_movement` e em `_block_if_changing_migrated_attendance`, `attendance.py:32-61`).
3. **Não existe calculadora canônica única de frequência anual.** Ao menos 6 pontos recalculam frequência por `class_id`+`records[]` de forma independente: `attendance.py:1014-1199` (relatório), `bulletin_builder.py:190-220` (boletim), `analytics.py` (múltiplas agregações Mongo), `monthly_report_service.py:211`, `history_consolidator.py:105`, `diary_snapshot_service.py:261`. Isso é uma violação de SSoT preexistente (não introduzida por esta feature) que **se agrava** com uma retificação: se a "frequência administrativa retificada" não for incorporada de forma idêntica em todos os 6 pontos, boletim/relatório/histórico podem divergir entre si. Ver §6 para decisão proposta.
4. **`enrollments.status` não tem valor para "matrícula anulada por erro documental".** O enum real (`models.py:1742`) é `active|completed|cancelled|transferred|relocated|progressed|dropout`. Usar `cancelled` genérico esconde a causa raiz (confundível com desistência/abandono); o próprio `ACADEMIC_EVENT_CONTRACT.md` já previu e não implementou um valor `moved_out`.
5. **`academic_events` é um contrato normativo aprovado (FROZEN V1) mas não conectado à produção real.** Decisão arquitetural pendente: construir a retificação sobre esse contrato (reaproveitando `academic_event_lens`, `temporal_closure`, auditoria) — o que exigiria primeiro religar o contrato aos fluxos reais, um esforço maior e fora do escopo desta Issue — ou tratá-la como um subsistema paralelo e mais simples, específico de correção de erro documental. Recomendação preliminar em §4.
6. **Mapeamento curricular origem→destino não é trivial.** `course_id` não é necessariamente compartilhado entre séries (`backend/utils/curriculum_resolver.py`, `_curricular_fit()` classifica `EXPLICIT_SERIES_FULL_MATCH`, `NO_SERIES_MATCH`, `SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW`, entre outros). Um "Matemática" do 6º ano pode ser um `course_id` distinto do "Matemática" do 7º ano.
7. **DVD (vínculo professor+turma+componente) pode não existir/ser incompatível no destino.** `grades_dvd.py` amarra notas a `assignment_id` (`TeacherAssignment`, `models.py:2263-2311`). Retificar notas sob DVD sem `assignment_id` válido no destino quebra a proveniência de autoria.
8. **`content_entries` é por turma, não por aluno** — não existe "conteúdo do aluno" para mover; a ação correta é preservar (não replicar conteúdo que o destino nunca ministrou), o que é conceitualmente diferente de attendance/grades.
9. **Documentos verificáveis já emitidos** citando a turma errada não têm hoje um fluxo automático de detecção por `class_id`/`student_id` afetado — precisa de busca ativa em `verifiable_documents` por `entity_id=student_id` no momento da retificação (mecanismo de revogação/supersessão já existe, ver §8, mas não é acionado automaticamente por nenhum fluxo de movimentação hoje).
10. **`audit_logs` (schema genérico) não tem campo de primeira classe para `mantenedora_id`.** Operações sensíveis multi-tenant (como `school_transfer_audit`) usam coleção de auditoria própria com tenant explícito — a retificação deve seguir esse padrão (coleção de auditoria dedicada) em vez de depender só do `audit_logs` genérico.
11. **Consolidação de histórico (`history_consolidator.py`) já deduplica por (ano, série)** (linhas 245-278) — isto **pode já ter corrigido** a lacuna #2 apontada na auditoria anterior (`memory/AUDITORIA_MOVIMENTACAO_ALUNOS.md`, que registrava duplicação de linha por turma no mesmo ano). **Precisa reverificação empírica** antes de a F1 assumir esse comportamento como garantido — incluir como item de teste de regressão (§13).

---

## 4. Contrato de domínio proposto — `retificacao_enturmacao`

### 4.1 Definição

Operação administrativa que corrige um vínculo `student_id` × `class_id` estabelecido por **erro documental de matrícula** (não por evolução pedagógica real), transferindo o vínculo ativo para a turma correta e **eliminando** o vínculo acadêmico ativo na turma incorreta, preservando toda a proveniência exclusivamente em trilha de auditoria administrativa — nunca como histórico pedagógico "cursado".

### 4.2 Precondições

- Usuário autenticado com papel `super_admin`, `admin` ou `gerente` (ver §9).
- Origem e destino pertencem à **mesma mantenedora**, à **mesma escola** e ao **mesmo ano letivo** (restrição de v1, ver §9).
- Existe matrícula ativa (`enrollments.status='active'`) do estudante na turma de origem.
- Turma de destino existe, está ativa, no mesmo `school_id`/`academic_year`, e é **elegível** (série/etapa compatível com o destino pretendido — validação análoga à usada em matrícula nova).
- Nenhuma outra operação de movimentação (`retificacao_enturmacao`, remanejamento, transferência institucional, reconstrução de histórico) está em andamento para o mesmo `student_id` (lock).
- Dry-run executado e relatório de impacto revisado pelo operador antes de qualquer execução real.

### 4.3 Pós-condições

- `attendance`: zero documentos com `records[].student_id` do estudante sob o `class_id` de origem (FREQ-03).
- `grades`: zero documentos `grades` ativos vinculando o estudante ao `class_id`/`course_id` de origem sem correspondência curricular válida no destino — registros sem mapeamento seguro ficam **arquivados** (não visíveis no boletim ativo), nunca apagados.
- `enrollments`: matrícula de origem com status de retificação (não `cancelled` genérico — ver §3.4/§15), referenciando o protocolo da retificação; matrícula de destino `active`, preservando `enrollment_number`/`enrollment_date` originais quando tecnicamente possível (decisão jurídica, ver §15).
- `students.class_id` (projeção) recalculado para o destino via mecanismo existente (`rebuild_student_home_projection`).
- Documentos verificáveis emitidos citando a turma de origem identificados e, quando aplicável, revogados/superseded (§8) — nunca silenciosamente reescritos.
- Trilha de auditoria dedicada e imutável (append-only) com snapshot antes/depois, protocolo, justificativa, autor, timestamps.
- AEE e Bolsa Família permanecem **absolutamente intocados** (são student-anchored, confirmado em §1/§2).

### 4.4 Invariantes

- **INV-1 (Nunca inventar dado):** nenhuma frequência, nota, conteúdo ou evento é criado como se tivesse ocorrido na turma/professor de destino quando de fato ocorreu na turma de origem.
- **INV-2 (Zerar a origem):** ao final, a turma de origem não mantém nenhum vínculo acadêmico ativo do estudante (FREQ-03 generalizado a notas/matrícula).
- **INV-3 (Proveniência auditável e não editável):** todo dado migrado/anulado preserva registro imutável de onde veio, quando e por quem foi corrigido.
- **INV-4 (Nunca sobrescrever documento verificável):** documentos já emitidos são revogados/superseded, nunca reescritos in-place.
- **INV-5 (Fail-closed):** qualquer ambiguidade de tenant, mapeamento curricular, colisão de dados ou autorização aborta a operação sem mutação parcial silenciosa.
- **INV-6 (Escopo de tenant):** origem e destino sempre na mesma mantenedora (v1: mesma escola e mesmo ano letivo).

### 4.5 Idempotência

Cada execução recebe um `idempotency_key` determinístico (padrão já usado em `school_transfer.py` e no núcleo MIG, `mig/core/ids.py::compute_idempotency_key`). Reexecutar a mesma chave após sucesso retorna o resultado já processado (replay), sem duplicar mutações — mesmo padrão do dry-run token/idempotency-key de `school_transfer.py:200-266`.

### 4.6 Dry-run obrigatório

Todo `execute` exige um `dry-run` prévio bem-sucedido, cujo token é obrigatório no `execute` (mesmo padrão de `school_transfer.py`). O dry-run **nunca** grava nas coleções de domínio — só simula e retorna relatório de impacto (§9 do fluxo de UX da Issue).

### 4.7 Snapshot antes/depois

Snapshot completo (subset relevante de `enrollments`, `attendance.records[]` do estudante, `grades`, `student_dependencies`, `content_entries` referenciados) persistido antes da mutação, no padrão já usado por `school_transfer.py:305-324`, habilitando rollback compensatório dentro da janela elegível.

### 4.8 Protocolo

Cada execução gera um protocolo único (`RET-YYYYMMDD-XXXX` ou similar, seguindo o padrão `SIGESC-XXXX-XXXX` de `verifiable_docs_service.py`), rastreável via endpoint de consulta e usado no recibo (§9.12 do fluxo de UX da Issue).

### 4.9 Auditoria

Coleção de auditoria dedicada (`retificacao_enturmacao_audit`, análoga a `school_transfer_audit`), com `mantenedora_id` explícito (lacuna #10 de §3), protocolo, `snapshot_before`/`snapshot_after`, ação, ator, papel, IP, user agent, timestamps, resultado por sub-etapa (frequência/notas/matrícula/documentos).

### 4.10 Reautenticação

Reautenticação por senha exigida no `execute` (mesmo padrão de `school_transfer.py:248-259`), independente da sessão já autenticada.

### 4.11 Justificativa obrigatória

Campo de texto livre, comprimento mínimo (sugestão: alinhar aos 10 caracteres de `school_transfer.py` `MIN_REASON_LEN` ou aos 30 do `academic_events` contract §10.1 — decisão humana, ver §15), persistido no protocolo e na auditoria.

### 4.12 Frase de confirmação

Frase literal distinta das já existentes (nunca reaproveitar `"CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL"`, que é semanticamente outra operação) — sugestão: `"CONFIRMO A RETIFICAÇÃO DE MATRÍCULA/TURMA"`.

### 4.13 Política de rollback

Janela de rollback elegível (sugestão: alinhar aos 7 dias de `school_transfer.py` `ROLLBACK_WINDOW_DAYS`, decisão humana em §15). Rollback restaura o snapshot pré-mutação; **inelegível** quando: (a) já foi emitido documento verificável usando o dado pós-retificação e o documento não foi revogado; (b) já houve nova movimentação subsequente do mesmo estudante que dependa do estado pós-retificação; (c) janela expirada.

### 4.14 Política de documentos previamente emitidos

Ver §8.

### 4.15 Detecção de resíduos pós-operação

Verificação automática pós-execução (parte do `execute`, não etapa manual): `db.attendance.count_documents({class_id: origem, "records.student_id": student_id})==0`, equivalente para `grades` ativos e `enrollments.status='active'` na origem. Falha nessa verificação **não desfaz automaticamente** (dado ausência de transação, ver §10) — mas marca o protocolo como `status=inconsistent`, bloqueia novas operações sobre o mesmo estudante até resolução manual, e dispara alerta de observabilidade.

### 4.16 Concorrência / optimistic locking

Lock por operação em documento de controle (padrão `transfer_in_progress` de `school_transfer.py`), escopado por `student_id` (não por `class_id`, pois aqui a granularidade é o aluno). Qualquer tentativa concorrente de nova retificação, remanejamento, transferência institucional ou reconstrução de histórico sobre o mesmo `student_id` é bloqueada (`409`) enquanto o lock estiver ativo.

---

## 5. Invariantes formais

Ver §4.4 (INV-1 a INV-6) e §6 (FREQ-01 a FREQ-03, adotados literalmente da Issue). Complementarmente:

- **GRADE-01:** nenhuma nota é atribuída à turma/professor de destino como se tivesse sido lançada por ele, quando na verdade foi lançada na origem — toda migração de nota preserva `migrated_from_class_id`/`migrated_at` e autoria original (`created_by_user_id` imutável, mesmo princípio de `ACADEMIC_EVENT_CONTRACT.md §6.2`).
- **GRADE-02:** colisão de nota já existente e ativa no destino é **fail-closed** — a operação não sobrescreve; requer decisão humana explícita (`manual_review`) por componente colidente.
- **DOC-01:** nenhum documento verificável já emitido é alterado in-place; toda correção documental é `revoke` ou `supersede`, nunca update silencioso.
- **TENANT-01:** toda leitura/escrita usa `apply_tenant_filter`/`resolve_tenant_id_for_create` (`tenant_scope.py`); ausência de tenant resolvido aborta com sentinela fail-closed (mesmo padrão hoje aplicado a outras rotas sensíveis).

---

## 6. Decisão para frequência (FREQ-01/02/03)

Adotando literalmente os requisitos da Issue:

- **FREQ-01** (não inventar aula/data no destino) e **FREQ-02** (preservar como correspondência real OU retificação administrativa contabilizável) e **FREQ-03** (zero `records[].student_id` na turma errada após a operação) são adotados como invariantes formais desta operação (ver §5).

### 6.1 Arquitetura proposta: nova coleção `attendance_rectifications`

Proposta preliminar (a decidir, ver §15): criar `attendance_rectifications` como estrutura **separada** de `attendance`, em vez de tentar encaixar frequência retificada dentro de documentos `attendance` do destino (o que exigiria fabricar `date`/`aula_numero` no destino — proibido por FREQ-01).

Cada documento representaria: `student_id`, `origin_class_id`, `origin_course_id`, `origin_date`, `origin_aula_numero`, `original_status` (present/absent/justified/late — valor original preservado verbatim), `academic_year`, `rectification_protocol`, `destination_class_id`, `created_at`, `created_by_user_id`, `justification_ref`. Não é uma frequência "da turma destino" — é uma frequência **administrativamente contabilizável para o aluno**, com proveniência explícita na origem.

**Vantagens:** não força correspondência inexistente com aulas do destino (respeita FREQ-01); mantém `attendance` como fonte fiel só de frequência real por turma+data+aula; auditável por natureza (coleção própria, não misturada a registros operacionais do dia a dia).

**Riscos:** introduz uma **segunda fonte** que todo cálculo de frequência anual precisa conhecer — o que **exacerba a lacuna #3 de §3** (ausência de calculadora canônica única). Sem consolidar os ~6 pontos de cálculo hoje dispersos, o risco de sub/dupla contagem é real e não cosmético.

### 6.2 Alternativa considerada e não recomendada

Injetar registros sintéticos em documentos `attendance` do destino marcados com uma flag `administrative_rectification=true`. **Rejeitada** preliminarmente porque viola o espírito de FREQ-01 (mistura frequência real da turma com um registro que não corresponde a nenhuma aula real daquela turma) e tornaria os ~6 pontos de leitura de `attendance` propensos a contar a retificação como se fosse frequência real do professor de destino, sem qualquer mudança de código — o que é sedutor (não exige tocar nos consumidores) mas semanticamente incorreto.

### 6.3 Cálculo anual combinado — pré-requisito arquitetural

Antes de a F1 poder **executar** (não apenas simular) uma retificação de frequência, recomenda-se — como **P0 paralelo, não bloqueante para a documentação/dry-run da F1, mas bloqueante para qualquer execução real** — consolidar os pontos de cálculo de frequência anual (§3, item 3) em uma função canônica única que:
1. some registros reais de `attendance.records[]` por `student_id`+`class_id`+`academic_year` (comportamento atual);
2. una, sem duplicar, registros administrativos de `attendance_rectifications` do mesmo `student_id`+`academic_year` referentes à turma de destino "efetiva" no período correspondente;
3. seja consumida por todos os ~6 pontos hoje dispersos (relatório, boletim, analytics, monthly_report, history_consolidator, diary_snapshot).

Sem esse pré-requisito, a Issue não pode ser considerada "pronta para F1 executar mutações reais" com segurança — pode, no entanto, avançar com dry-run/relatório de impacto que **apenas leia** e **não persista** `attendance_rectifications`.

---

## 7. Decisão para notas/mapeamento curricular

### 7.1 Algoritmo de mapeamento proposto

Reaproveitar `backend/utils/curriculum_resolver.py::_curricular_fit()` (já é a SSoT de compatibilidade curricular por série/etapa, usada por PDF/boletim/render jobs) como motor de decisão origem→destino, componente a componente:

1. Para cada `course_id` com nota ativa do aluno na turma de origem, resolver o(s) `course_id` candidato(s) da turma de destino usando `_curricular_fit()`.
2. **`EXPLICIT_SERIES_FULL_MATCH`** (ou equivalente de correspondência inequívoca) → elegível a `move` condicionado a ausência de colisão (§7.2).
3. **`NO_SERIES_MATCH`**, **`SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW`** ou qualquer resultado não-inequívoco → `manual_review` obrigatório; a nota **não é movida automaticamente** — fica **preservada** (arquivada, fora do boletim ativo do destino), com o vínculo de origem ainda assim removido/anulado (a nota não desaparece, só deixa de aparecer como "cursado no destino").
4. Se o vínculo DVD (`assignment_id`/`TeacherAssignment`) do componente não existir/for incompatível no destino → fail-closed (`manual_review`), mesmo que o componente em si tenha match curricular.

### 7.2 Fail-closed obrigatório (conforme exigido na Issue)

A operação é fail-closed quando:
- não houver correspondência inequívoca de componente (§7.1, passo 3);
- houver **colisão** de nota já existente e não-vazia no destino para o mesmo `course_id`+`academic_year` (GRADE-02, §5) — ao contrário do `copy-data` atual, que faz merge silencioso só em campos vazios, a retificação **não decide sozinha**; expõe o conflito para decisão humana;
- houver política/assignment (DVD) incompatível (§7.1, passo 4);
- o mapeamento 1:1 não puder ser provado algoritmicamente.

### 7.3 Preservação de proveniência sem vínculo acadêmico ativo

Notas não movidas (por qualquer fail-closed acima) permanecem no banco vinculadas à turma de origem, mas: (a) a matrícula de origem deixa de estar `active` (INV-2); (b) o registro passa a ser tratado como historicamente arquivado — visível apenas em auditoria/consulta administrativa, não no boletim corrente do aluno, evitando que a turma errada continue "aparecendo" como percurso pedagógico ativo, sem apagar o dado.

---

## 8. Política documental

Reaproveitar o mecanismo já existente e maduro em `backend/services/verifiable_docs_service.py`:
- **Identificar:** buscar em `verifiable_documents` por `entity_type` relevante (`declaracao_matricula`, `historico_escolar`, `boletim`, `ficha_individual` — nomes exatos a confirmar no router `documents.py`) com `student_id` igual ao do vínculo retificado e `entity_id`/payload referenciando a turma de origem.
- **Revogar quando aplicável:** usar `revoke_document()` (já existente, `revoked`/`revoked_at`/`revoked_reason`/`revoked_by`, ação **definitiva/não-reversível** conforme já documentado no serviço) quando o documento emitido está factualmente errado e sua permanência ativa induziria terceiros a erro.
- **Registrar motivo/protocolo:** `revoked_reason` referencia o protocolo da retificação (§4.8).
- **Permitir reemissão correta:** nova emissão gera novo documento verificável (novo `code`/`verification_token`), opcionalmente ligado via `supersede_document()` (já existente: `superseded_by_document_id`/`superseded_at`, mantendo o antigo visível como histórico, não apagado).
- **Nunca alterar silenciosamente:** confirmado como invariante já suportado pelo serviço (não há `update` in-place de `public_hash`/`server_signature` em documento já emitido) — a retificação deve **usar** esse mecanismo, não criar um novo.

Ação por padrão: `manual_review` (não há hoje busca automática por `student_id`+turma afetada nos routers de documentos — precisa ser construída na F1, mas o mecanismo de revogação/supersessão de baixo nível já existe).

---

## 9. RBAC / multi-tenancy

### 9.1 Papéis e escopo

- `super_admin`, `admin`, `gerente` — conforme pedido na Issue.
- `admin`/`gerente`: escopo travado à própria mantenedora, resolvido por `tenant_scope.py::get_mantenedora_scope()` (`backend/tenant_scope.py:155-191`) — usam sempre `user.mantenedora_id`, ignorando qualquer header de seleção.
- `super_admin`: opera **um** tenant por requisição, selecionado via `X-Mantenedora-Id`/`mantenedora_id` (mesmo mecanismo hoje usado nas rotas institucionais, `tenant_scope.py:137-152`) — a retificação **não** deve entrar na lista `CONTROL_PLANE_PATH_PREFIXES` (`tenant_scope.py:35-40`), pois opera sobre dados de tenant, não sobre o control plane.

### 9.2 Padrão de enforcement

Reaproveitar `auth_middleware.py::require_roles`/`require_permission` (`backend/auth_middleware.py:139-208`) com `allowed_roles={"super_admin","admin","gerente"}` — **contrastando** deliberadamente com `_require_super_admin` de `school_transfer.py:85-89`, que permanece exclusivo da Transferência Institucional (a Issue exige explicitamente que nenhuma abertura de permissão vaze para lá).

### 9.3 Restrição de escopo v1

Origem e destino na **mesma mantenedora + mesma escola + mesmo ano letivo**. Validar com `assert_same_tenant()` (`tenant_scope.py:315-357`) tanto na turma de origem quanto na de destino, e `verify_school_access()` (`auth_middleware.py:264-329`, já trata divergência de tenant com 403 mesmo para `super_admin` cross-tenant sem seleção) para o usuário operador.

### 9.4 Fail-closed

Ausência de tenant válido resolvido → sentinela fail-closed de `apply_tenant_filter` (`tenant_scope.py:293-312`), consistente com o restante do sistema; nenhuma query "solta" sem filtro de mantenedora.

---

## 10. Atomicidade / rollback

### 10.1 Evidência

MongoDB roda **standalone** em todos os ambientes auditados (`docker-compose.yml`, `docker-compose.coolify.yml`, `docker-compose.homolog.yml` — todos `image: mongo:7` sem `--replSet`); nenhuma connection string usa `replicaSet=`; nenhuma ocorrência de `start_session`/`start_transaction`/`with_transaction` em `backend/` fora de testes. **Não há suporte a transação multi-documento disponível hoje.**

### 10.2 Estratégia saga/compensação proposta

Reaproveitar o padrão já validado em produção por `school_transfer.py`:
1. **Estado da operação:** documento de controle `retificacao_enturmacao_audit` com `status` (`dry_run|pending|in_progress|executed|failed|rolled_back|inconsistent`).
2. **Lock:** flag `rectification_in_progress` (compare-and-set atômico via `find_one_and_update`) escopado por `student_id` (§4.16).
3. **Idempotência:** `idempotency_key` determinístico (§4.5).
4. **Snapshot:** subset relevante das coleções afetadas, persistido antes de qualquer escrita (§4.7).
5. **Execução ordenada e auditável por sub-etapa:** ordem sugerida — (a) validar precondições e mapeamento curricular (fail-closed antes de qualquer escrita); (b) extrair/mover `attendance.records[]`; (c) mover/arquivar `grades`; (d) atualizar `enrollments`/`students` projeção; (e) pós-validação (§4.15); cada sub-etapa grava resultado parcial na auditoria, permitindo diagnóstico exato de onde uma falha ocorreu.
6. **Rollback compensatório:** restaura o snapshot pré-mutação; **não é automático em falha parcial** (mesmo comportamento hoje de `school_transfer.py:382-389`, que marca `status=failed` e para, sem desfazer sozinho) — decisão deliberada de segurança: preferir estado `inconsistent`/`failed` explícito e visível a uma reversão automática que pode mascarar uma escrita parcial já observada por outro processo.
7. **Recuperação após falha parcial:** operação fica bloqueada (lock mantido) até um operador revisar o protocolo `failed`/`inconsistent` e decidir entre rollback manual (dentro da janela) ou correção manual assistida.
8. **Pós-validação obrigatória:** §4.15, executada sempre ao final de um `execute` bem-sucedido.

---

## 11. Endpoints propostos para F1 (não implementados nesta F0)

Nomenclatura alinhada ao padrão de `school_transfer.py` (prefixo de router sugerido: `/api/admin/rectifications` ou `/api/enrollment-rectification`, a decidir):

| Método | Rota (proposta) | Propósito |
|---|---|---|
| `GET` | `/lookup?student_id=` | Localizar estudante e vínculo atual (turma, matrícula, escola, ano) |
| `GET` | `/eligible-classes?student_id=&origin_class_id=` | Listar turmas de destino elegíveis (mesma escola/ano/mantenedora, série compatível) |
| `POST` | `/dry-run` | Simula a retificação; retorna relatório de impacto (frequência a arquivar, notas por componente com status match/colisão/no-match, documentos afetados, bloqueios) sem gravar nada |
| `POST` | `/execute` | Executa mediante `dry_run_token`, reautenticação, justificativa (§4.11), frase de confirmação (§4.12) |
| `GET` | `/{protocol}` | Consulta status/detalhe do protocolo |
| `GET` | `/{protocol}/rollback-eligibility` | Verifica elegibilidade de rollback (§4.13) |
| `POST` | `/{protocol}/rollback` | Executa rollback compensatório dentro da janela elegível |
| `GET` | `/{protocol}/receipt` | Recibo/protocolo em PDF (reaproveitando `verifiable_docs_service`) |

Todos os endpoints exigem `require_roles({"super_admin","admin","gerente"})` + validação de tenant (§9), e nenhum é implementado nesta F0.

---

## 12. Modelo de dados proposto (sem implementar)

### 12.1 `retificacao_enturmacao_audit` (nova coleção — proposta)

```
{
  id, protocol, mantenedora_id, school_id, academic_year,
  student_id, origin_class_id, destination_class_id,
  status: dry_run|pending|in_progress|executed|failed|rolled_back|inconsistent,
  idempotency_key, dry_run_token,
  justification, confirmation_phrase_confirmed: bool,
  requested_by_user_id, requested_role, reauth_verified: bool,
  snapshot_before: {...}, snapshot_after: {...},
  substeps: [{name, status, started_at, finished_at, detail}],
  created_at, updated_at, executed_at, rolled_back_at,
  post_validation: {origin_attendance_count, origin_grades_active_count, origin_enrollment_status, passed: bool}
}
```

### 12.2 `attendance_rectifications` (nova coleção — proposta, ver §6.1)

```
{
  id, student_id, mantenedora_id, school_id, academic_year,
  origin_class_id, origin_course_id, origin_date, origin_aula_numero,
  original_status, destination_class_id,
  rectification_protocol, created_at, created_by_user_id
}
```

### 12.3 Alterações aditivas propostas (não obrigatórias para dry-run, necessárias para execução)

- `enrollments.status`: avaliar novo valor de enum (ex.: `voided_documentary_error`) — decisão humana (§15), pois altera contrato de dados existente (`EnrollmentBase`) e qualquer código que hoje trata `status` como `Literal` fechado.
- `grades`: campo aditivo opcional `archived_from_rectification: {protocol, at}` para notas não movidas (§7.3), sem remover nenhum campo existente.
- `attendance` (registro individual dentro de `records[]`): nenhuma alteração de schema — a extração/remoção usa os campos já existentes.

Nenhuma migration, índice ou alteração de schema é executada nesta F0 — apenas proposta para avaliação humana antes da F1.

---

## 13. Matriz de testes exigida para F1

| # | Cenário | Verifica |
|---|---|---|
| 1 | Sintético 6º→7º (caso motivador, dados fictícios) | Fluxo feliz completo, pós-condições §4.3 |
| 2 | Frequência com datas/aulas coincidentes entre origem e destino | FREQ-02 (correspondência inequívoca aceita) |
| 3 | Frequência com datas/aulas **não** coincidentes | FREQ-01/02 (vira retificação administrativa, nunca fabrica aula) |
| 4 | Componente curricular sem correspondência (`NO_SERIES_MATCH`) | GRADE fail-closed, `manual_review` |
| 5 | Colisão de nota já existente no destino | GRADE-02 fail-closed, sem merge silencioso |
| 6 | Matrícula de destino já existente (ativa) para o aluno | Precondição/fail-closed |
| 7 | Dados órfãos (attendance/grades sem enrollment correspondente) | Comportamento definido explicitamente, não é `KeyError`/exceção |
| 8 | Documentos verificáveis já emitidos citando a turma errada | Identificação + revogação/supersessão, nunca reescrita silenciosa |
| 9 | AEE e Bolsa Família preservados | Nenhuma mutação nessas coleções após a operação |
| 10 | Fail-closed de tenant (origem/destino em mantenedoras diferentes) | Bloqueio antes de qualquer escrita |
| 11 | RBAC — `super_admin`/`admin`/`gerente` permitido; outros papéis bloqueados | 403 correto |
| 12 | Idempotência — reexecução da mesma `idempotency_key` | Sem duplicar mutação, retorna resultado já processado |
| 13 | Falha parcial simulada (ex.: falha após mover frequência, antes de notas) + recuperação | Estado `inconsistent`/`failed` visível, sem mutação silenciosa incompleta despercebida |
| 14 | Rollback elegível (dentro da janela, sem documento emitido pós-mutação) | Restaura snapshot corretamente |
| 15 | Rollback inelegível (fora da janela ou documento já emitido) | Bloqueio explícito com motivo |
| 16 | Pós-condição — origem com zero vínculos acadêmicos ativos do estudante | FREQ-03 generalizado (§4.3), verificação automática (§4.15) |
| 17 (adicional) | Concorrência — segunda retificação/remanejamento/transferência sobre o mesmo `student_id` durante lock ativo | 409, sem corrida |
| 18 (adicional) | DVD — `assignment_id` incompatível/inexistente no destino | Fail-closed em notas sob DVD |
| 19 (adicional) | Regressão do `history_consolidator` dedup por (ano, série) (item 11 de §3) | Confirmar que a retificação não reintroduz duplicação de linha de histórico já corrigida |

---

## 14. Plano incremental F1/F2/F3 (proposto)

- **F1 (requer aprovação humana):** modelo de dados + endpoints `lookup`/`eligible-classes`/`dry-run` (read-only, sem persistir `attendance_rectifications`/mutar nada) + relatório de impacto completo (frequência, notas por componente, documentos afetados, bloqueios). Nenhuma mutação real ainda. Testes 1-11, 17-19 da matriz (parte read-only).
- **F2 (requer aprovação humana, após F1 validada):** `execute`/`rollback`/`receipt` com saga/compensação completa (§10), coleções `retificacao_enturmacao_audit` e `attendance_rectifications` persistidas, política documental (§8) acionada automaticamente. Pré-requisito duro: consolidação da calculadora canônica de frequência anual (§6.3) — sem isso, F2 não deve liberar mutação real de frequência em produção. Testes 12-16 da matriz.
- **F3 (opcional, requer decisão humana separada):** decidir se a retificação passa a usar `db.academic_events`/lens (religando o contrato congelado à produção) em vez de trilha própria — mudança arquitetural maior, fora do escopo imediato.

---

## 15. Questões que ainda precisam de decisão humana

1. **`enrollments.status` para matrícula anulada por erro documental:** criar novo valor de enum (ex.: `voided_documentary_error`) ou reutilizar `cancelled` com metadado adicional? Afeta contrato de dados existente e qualquer consumidor do `Literal` fechado.
2. **Religar ou não `db.academic_events`:** construir a retificação como um novo `event_type` dentro do contrato `ACADEMIC_EVENT_CONTRACT.md` (exigiria bump de `contract_version` + religar o contrato à produção, hoje dormente) versus trilha própria e mais simples focada só nesta operação. Tem implicação direta em esforço e em consistência de longo prazo com o restante do domínio.
3. **Prazo da janela de rollback:** alinhar aos 7 dias de `school_transfer.py` ou definir prazo próprio?
4. **Comprimento mínimo de justificativa:** 10 caracteres (padrão `school_transfer.py`) ou 30 (padrão `academic_events` contract §10.1)?
5. **Preservar `enrollment_number`/`enrollment_date` original** na matrícula de destino é juridicamente correto para o caso de erro documental, ou a correção deve gerar nova numeração com referência cruzada ao número original? Depende de norma de escrituração escolar que a equipe de secretaria/jurídico deve confirmar.
6. **Arquitetura de frequência administrativa (`attendance_rectifications` vs. alternativa):** validar a proposta de §6.1 ou explorar alternativa antes de comprometer schema.
7. **Pré-requisito da calculadora canônica de frequência (§6.3, §14 F2):** aceitar como bloqueante de F2, ou aceitar risco documentado de divergência entre relatórios enquanto os 6 pontos de cálculo não forem consolidados?
8. **Nomenclatura final e prefixo de rota dos endpoints F1** (§11) — alinhamento com convenções já em uso no repositório.
9. **Alcance de "mesma escola" na v1:** a Issue já fixa mesma mantenedora+escola+ano; confirmar se há caso real (ex.: escolas multisseriadas com sedes anexas) que precise de exceção documentada antes da F1.
10. **Confirmação empírica do item 11 de §3** (se a deduplicação de histórico por ano/série do `history_consolidator.py:245-278` já resolveu a lacuna registrada em `memory/AUDITORIA_MOVIMENTACAO_ALUNOS.md`) — recomenda-se rodar um teste de regressão dedicado antes de assumir esse comportamento como garantido na F1.

---

## Referências de código citadas

- `backend/routers/students.py:1695-1791, 2308-2359, 2162-2164`
- `backend/services/pedagogical_consolidation.py` (arquivo completo)
- `backend/routers/school_transfer.py:41-53, 85-89, 180-700`
- `backend/routers/history_reconstruction.py`
- `backend/routers/enrollments.py:193-205`
- `backend/services/enrollment_service.py:167, 199, 253, 397`
- `backend/models.py:1724-1837 (EnrollmentBase, GradeBase), 2263-2311 (TeacherAssignment), 2612-2650 (AuditLog)`
- `docs/ACADEMIC_EVENT_CONTRACT.md` (contrato completo, FROZEN V1)
- `backend/utils/academic_event_lens.py`, `backend/utils/temporal_closure.py`, `backend/routers/closure.py`
- `backend/routers/attendance.py:32-61, 77-87, 258-334, 571-599, 1014-1199`
- `backend/services/attendance_audit_diary.py`
- `backend/routers/attendance_dvd.py`, `backend/routers/attendance_historical_backfill_dvd.py`
- `backend/routers/grades.py:280-386`, `backend/routers/grades_dvd.py`
- `backend/assessment_policy/operational_binding.py`
- `backend/utils/curriculum_resolver.py:159-257`
- `backend/services/history_consolidator.py:69-281`
- `backend/services/snapshot_service.py`, `backend/services/verifiable_docs_service.py:163-396`
- `backend/aee_v2/contracts.py:173`, `backend/aee_v2/repository.py:153`
- `backend/routers/bolsa_familia.py:356-358, 774-818, 854, 975`
- `backend/utils/dependency_validator.py:34-80`, `backend/routers/dependency_completions.py:605`
- `backend/routers/content_entries.py:45-86`
- `backend/tenant_scope.py:35-40, 91-97, 137-191, 214-312, 315-378`
- `backend/auth_middleware.py:139-329`
- `backend/role_context.py:12-18`
- `backend/server.py:138-139`; `docker-compose.yml`, `docker-compose.coolify.yml`, `docker-compose.homolog.yml`
- `backend/aee_v2/versioning.py:10`
- `backend/audit_service.py:100-194`; `backend/startup/indexes.py:276-292`
- `mig/core/ids.py::compute_idempotency_key`
- `memory/AUDITORIA_MOVIMENTACAO_ALUNOS.md`, `memory/AUDITORIA_TRANSFERENCIA_INSTITUCIONAL.md`

---

## Confirmação de restrições respeitadas

- Nenhum dado de `students`, `enrollments`, `attendance`, `grades` ou qualquer coleção real foi alterado.
- Nenhuma retificação da estudante motivadora foi executada.
- Nenhum endpoint funcional foi criado.
- Nenhum writer/migration/script de mutação foi criado.
- Nenhuma alteração funcional em AEE foi realizada (apenas confirmação read-only de que é student-anchored).
- Nenhuma alteração de schema/índice foi realizada.
- Nenhum merge, auto-merge ou deploy foi realizado.
