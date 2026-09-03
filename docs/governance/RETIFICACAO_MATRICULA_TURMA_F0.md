# F0 — Retificação de Matrícula/Turma por Erro Documental — Auditoria Técnica e Contrato de Domínio

- **Status**: DRAFT — auditoria read-only concluída. Nenhuma mutação funcional ou de produção foi realizada.
- **Base de código**: `main` em `9954fe5a687a5cf4e661aec11725a7520e23c6f6`.
- **Issue de origem**: #346.
- **Escopo desta etapa**: F0 (auditoria + contrato de domínio). Nenhum endpoint, writer, migration ou script de mutação foi criado. Nenhum schema/índice foi alterado.
- **Caso motivador (não executado)**: estudante matriculada documentalmente no 6º ANO A quando deveria ter sido matriculada em turma do 7º ano desde o início. Usado apenas como cenário de referência para o desenho do contrato — nenhum dado real dessa estudante foi alterado.

> Convenção de nomenclatura usada neste documento: a operação futura é referida pelo nome canônico proposto **`retificacao_enturmacao`**. "Turma de origem" é a turma documentalmente incorreta (6º ANO A no caso motivador); "turma de destino" é a turma correta (turma do 7º ano).

---

## 1. Estado atual comprovado por código

Esta seção resume, com citações `arquivo:linha`, o que o código realmente faz hoje — não o que o contrato normativo declara que deveria fazer (as duas coisas divergem em pontos identificados abaixo).

### 1.1 `enrollments` já é a SSoT declarada do vínculo aluno↔turma↔ano

Desde ago/2026, `enrollments` é a fonte canônica do vínculo estudante↔turma↔ano; `students.class_id`/`students.student_series` são mantidos apenas como **projeção** da matrícula regular ativa (`backend/routers/enrollments.py:1-7`, `backend/services/enrollment_service.py:4-9`). A reconstrução da projeção é feita por `rebuild_student_home_projection` (`backend/services/enrollment_service.py:199-240`).

Consequência direta para o F0: qualquer retificação **deve escrever primeiro em `enrollments`** e depois reconstruir a projeção em `students` — nunca editar `students.class_id` diretamente.

### 1.2 Já existe um guard-rail que bloqueia esta operação por edição genérica

`PUT /api/enrollments/{id}` recusa com **HTTP 409** qualquer tentativa de trocar `student_id`/`school_id`/`class_id`/`academic_year` de uma matrícula `active` por edição direta, com a mensagem explícita: *"Uma matrícula ativa não pode trocar estudante/escola/turma/ano por edição. Use o fluxo de remanejamento, transferência, progressão ou rematrícula."* (`backend/routers/enrollments.py:186-205`).

A `retificacao_enturmacao` precisa ser uma **rota nova e deliberada**, não uma flexibilização desse guard.

### 1.3 O padrão universal do código hoje é "copy-data preservando a origem" — e é semanticamente incompatível com retificação

Todos os fluxos de movimentação de turma hoje existentes (remanejamento, progressão, reclassificação, e o motor `consolidate_student_movement`) operam sob a premissa de que **a turma de origem foi um vínculo legítimo que deve ser preservado como prova histórica**:

- `PUT /api/students/{id}` (`backend/routers/students.py:1554` em diante) decide o `action_type` via `action_hint` no corpo da requisição e trata remanejamento/progressão/reclassificação como **o mesmo branch de código** (`students.py:1704-1792`), diferindo apenas no rótulo salvo. RBAC efetivo: `admin`, `admin_teste`, `secretario`, `auxiliar_secretaria`, `super_admin`, `gerente` (via `require_roles_with_coordinator_edit`, `students.py:1564-1567`; `coordenador` está em `COORDINATOR_VIEW_ONLY_AREAS`, `auth_middleware.py:16`, logo bloqueado na prática apesar de constar na lista).
- A matrícula de origem **nunca é apagada**: recebe apenas novo `status` (`relocated`/`progressed`/`reclassified`) e libera `enrollment_number` (preservado em `previous_enrollment_number`) — `students.py:1719-1747`.
- A consolidação pedagógica (`backend/services/pedagogical_consolidation.py:1-102`, docstring linhas 1-9) declara explicitamente: *"Princípio 1 (Preservação): a turma de ORIGEM nunca é alterada/removida. Princípio 2 (Continuidade): a turma de DESTINO recebe cópia idempotente"* de attendance, grades e content_entries. **Nada é apagado ou movido da origem — tudo é copiado para o destino.**
- A Transferência Institucional de Turmas (`backend/routers/school_transfer.py`, `super_admin only` via `_require_super_admin`, linhas 85-89) é o fluxo mais rigoroso em termos de segurança (dry-run, reautenticação, frase de confirmação, snapshot, rollback de 7 dias) mas move `school_id` **repontando in-place** e mantendo `class_id` estável — ela também assume que o vínculo movido é legítimo; seu rollback restaura o estado anterior exatamente como estava, não anula um erro de origem.
- A Reconstrução de Histórico Pedagógico (`backend/routers/history_reconstruction.py`) é um reparador de gaps do mesmo padrão copy-data — reprocessa cópias faltantes, nunca desfaz nada.

**Por que não podemos reutilizar esse padrão para retificação de erro documental**: o objetivo da retificação é o oposto — a turma de origem **nunca deveria ter tido o vínculo**, então "preservar a origem e copiar para frente" perpetua indevidamente o vínculo errado (a estudante continua aparecendo com frequência/notas "reais" no 6º ANO A) em vez de eliminá-lo administrativamente. É necessário um mecanismo de **anulação com efeito controlado e rastreável**, que hoje não existe em nenhuma forma no código.

### 1.4 Contrato de `academic_events` — lacuna estrutural confirmada

`EVENT_TYPES = ("transfer", "remanejamento", "reclassificacao", "progressao_parcial")` (`backend/routers/academic_events.py:27`). Não há `retificacao`/equivalente. O contrato normativo `docs/ACADEMIC_EVENT_CONTRACT.md` (versão congelada V1) é construído sobre o invariante fundador: *"Movimentações escolares NÃO removem o estudante da turma de origem"* (linha 17) e *"Proibido mover registros históricos entre turmas"* (§6.1, linhas 139-141) — o oposto semântico do que uma retificação de erro documental precisa.

Achado de inconsistência já existente (relevante como precedente, não como bloqueio): `school_transfer.py` grava `event_type: "transferencia_institucional"`/`"reversao_transferencia_institucional"` via `insert_one` direto, **fora** do enum validado por `_validate_event_type` (`academic_events.py:73-78`) — o campo `event_type` do modelo é `str` solto, não `Literal` (`academic_events.py:43`). Isso mostra que adicionar um novo tipo de evento não é tecnicamente barrado pelo schema, mas normativamente exigiria bump de `contract_version` (contrato §2/§14).

O mecanismo de "supersessão" de `academic_events` (`POST /{event_id}/supersede`, `academic_events.py:288-367`) é o precedente mais próximo de "correção" — mas corrige o **registro do evento em si**, nunca desfaz o vínculo físico já materializado em `students`/`enrollments`/`attendance`/`grades`.

### 1.5 MongoDB roda standalone em todos os ambientes — sem transação multi-documento nativa

Confirmado por evidência dupla e não-hipotética:

1. Os três `docker-compose*.yml` (`docker-compose.yml:4-11`, `docker-compose.homolog.yml:8-14`, `docker-compose.coolify.yml:10-16` — este último confirmado como o compose de produção via Coolify em `memory/audit/01_ARQUITETURA_GERAL.md:136-138`) sobem `mongo:7` como container único, sem `--replSet`, sem segundo/terceiro nó.
2. Uma auditoria de topologia **já foi executada contra o banco real de produção** em trabalho anterior (fases P0-F7.9D4-D9) e classificou a topologia como `STANDALONE_OR_TRANSACTION_UNAVAILABLE` (`memory/audit/P0F7_9D6_CAS_DRY_RUN_2026-08-29.md:5`, reafirmado em `memory/audit/P0F7_9D7_AUTHORIZED_PRODUCTION_EXECUTION_2026-08-29.md:15-19`), determinando estratégia obrigatória `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`.
3. Busca em todo o repositório por `start_session`/`with_transaction` retorna **zero ocorrências**.

Ver §10 para a estratégia derivada dessa constatação.

### 1.6 Frequência (Anos Finais) — modelo confirmado, mas o único "quase-mecanismo" de retificação hoje tem bugs reais

O modelo de `attendance` para Anos Finais é turma + data + componente (`course_id`) + `aula_numero`, um documento por aula, com `records[]` por aluno (`backend/routers/attendance.py:320-343`, chave de busca/upsert em `attendance.py:79-87`). **Nota de limpeza recomendada para F1**: existe um modelo Pydantic "morto" em `backend/models.py:1841-1859` (versão antiga, bimestral) shadowed por uma segunda definição de mesmo nome em `models.py:1973-2013` — nenhum router usa a primeira; não é a SSoT e pode confundir quem desenhar a retificação.

O único mecanismo hoje capaz de "mover" frequência entre turmas é `consolidate_student_movement` (`backend/services/pedagogical_consolidation.py:29-51`), com **bugs concretos e comprovados** relevantes para FREQ-01/02/03 (§6):

- A busca por documento "existing" no destino usa apenas `{class_id, date, academic_year}` — **sem `course_id`/`aula_numero`** (`pedagogical_consolidation.py:39-40`). Em Anos Finais, se a turma de origem tiver mais de um componente/aula na mesma data (cenário normal), o segundo componente processado sobrescreve `records[]` do documento criado pelo primeiro, perdendo silenciosamente o registro do primeiro componente.
- O documento novo criado no destino **não recebe `aula_numero`, `attendance_type`, `version`, `mantenedora_id`, `created_by`** (`pedagogical_consolidation.py:46-50`), divergindo do shape produzido pelo motor canônico `save_attendance_canonical` (`attendance.py:258-286`) e criando risco de colisão silenciosa com um lançamento legítimo posterior do professor para a mesma aula.
- Nenhuma integração com a modelagem DVD (`assignment_id`/`attendance_key_scope`) — confirmado por ausência total desses termos no arquivo.
- Nenhuma chamada a `audit_service`/trilha de auditoria central — o único rastro é `migrated_from_class_id`/`migrated_at` dentro do próprio registro.
- Teste existente (`backend/tests/test_student_movement_consolidation.py`) cobre apenas Anos Iniciais com datas distintas — **o cenário Anos Finais multi-componente/multi-aula não tem cobertura**.

**Conclusão**: `consolidate_student_movement` não deve ser reaproveitado como está para mover frequência numa retificação. Ver §6 para a decisão formal proposta.

Também não existe hoje uma única SSoT de cálculo de frequência anual — há pelo menos três padrões de agregação com filtros de escopo inconsistentes: `compute_attendance_buckets`/`attendance_percentage` e `compute_monthly_valid_absences` (ambos em `backend/services/attendance_utils.py:67-105` e `108-203`), e contagens ad-hoc por `set()` de datas em `backend/routers/documents.py:1005-1025` (sem filtro de `class_id`) e `documents.py:1268-1273` (com filtro de `class_id`). Um consumidor (`bolsa_familia.py:146-149`) usa um campo `student_id` de nível raiz que **não existe** no schema real (o campo correto é `records[].student_id`) — é código morto/quebrado, citado aqui como alerta de que nem todo consumidor filtra corretamente hoje.

### 1.7 Notas — "não basta trocar `class_id`" confirmado por múltiplas fontes independentes

- `grades` é um documento por `(student_id, class_id, course_id, academic_year[, dependency_id])` contendo até 4 bimestres + 2 recuperações semestrais no mesmo documento (`backend/models.py:1780-1837`) — **sem índice único composto no Mongo** protegendo essa chave (`backend/startup/indexes.py:103-106` só indexa `id`, `(student_id, academic_year)` e `(class_id, course_id, academic_year)` não-únicos); a unicidade é garantida apenas em nível de aplicação.
- Existem **duas implementações divergentes** de cálculo de média/conceito: `grade_calculator.py:236-314` (ciente de Educação Infantil) vs. a função local duplicada em `backend/routers/grades.py:70-155` (que **não** verifica nível de ensino) — e é a segunda que está de fato em uso no caminho de escrita real (`grades.py` e `grades_dvd.py` chamam a versão local).
- `assessment_policy/` já modela políticas de avaliação diferentes por `class_id`/`series` (`backend/assessment_policy/resolver.py:108-156`) — turma de origem e destino **podem, em tese, ter regimes avaliativos diferentes** (numérico vs. conceitual). O módulo ainda não tem cutover para runtime (`operational_binding.py:1-13`), mas o risco é latente para o desenho.
- DVD amarra proveniência **por campo/bimestre** via `grade_ownership` (snapshot do vínculo docente, incluindo `class_id` da turma de origem daquele lançamento — `backend/services/grade_assignment_scope.py:1-16,81-97`). Trocar apenas o `class_id` de topo do documento desalinha os snapshots internos e quebra a lógica de posse por campo.
- **Não existe mapeamento curricular entre séries** (6º→7º) em nenhum lugar do código. O casamento de nota hoje é só por **igualdade exata de `course_id`** — inclusive no fluxo de progressão real (`pedagogical_consolidation.py:59-61`, `history_reconstruction.py:161`). Se os `course_id` de origem/destino diferirem, a nota não é reconhecida como já existente e vira lançamento novo potencialmente órfão (detectável só a posteriori via diagnóstico administrativo, `backend/routers/admin.py:604-632`).
- A única lógica de colisão hoje existente é "merge não sobrescreve, só completa vazio" (`pedagogical_consolidation.py:62-76`) — adequada para continuidade, não para correção (onde a nota do destino errado tipicamente deveria ser estornada, não mesclada).
- Auditoria por nota individual é fraca: o caminho legado (`routers/grades.py`) não grava `created_by`/`updated_by` no documento nem chama `audit_service` nos endpoints singulares de criação/edição; só o batch grava auditoria truncada a 10 mudanças. O caminho DVD é mais rico (autor + `grade_ownership`), mas sem histórico de versões.
- **Precedente de risco já existente**: cancelamento de matrícula **apaga diretamente** (`delete_many`) as notas do aluno na turma cancelada, sem merge, sem cópia prévia, sem trilha por nota (`backend/routers/students.py:1839-1844`).

### 1.8 RBAC/multi-tenancy — mecanismos canônicos e precedentes de escopo por mantenedora

- `apply_tenant_filter`/`resolve_tenant_id_for_create` (`backend/tenant_scope.py:293-312,360-378`) são os helpers canônicos: fail-closed via `INVALID_TENANT_SENTINEL` quando não há tenant resolvido; `resolve_tenant_id_for_create` ignora explicitamente `school_id`/`class_id`/`student_id` de contexto pai (comentário MT-1, linha 374) — a atribuição de `mantenedora_id` para um novo documento deve vir do `user`/`request`, não de inferência pelo parent.
- `super_admin` opera um tenant selecionado por vez via header `X-Mantenedora-Id`/query param (`tenant_scope.py:137-152`), nunca em modo "Todas" nas rotas de negócio.
- `admin`/`gerente` ficam restritos à própria mantenedora — padrão canônico já usado em `backend/routers/mantenedoras.py:67-79` (`is_super_admin(user) or (role=='gerente' and get_user_mantenedora_id(user)==mid)`) e em `backend/routers/tenant_admin.py:272-282`.
- A Transferência Institucional (`school_transfer.py`) usa enforcement **manual** (`_require_super_admin`, chamado individualmente em 7 handlers) em vez de dependency compartilhada, e deriva `mantenedora_id` do documento `origin`, **não** do helper canônico `tenant_scope.py` — um desvio histórico específico desse módulo super_admin-only que **não deve ser copiado** para a retificação (multi-role).
- `academic_events.py:92,105` já usa corretamente `get_mantenedora_scope(user, request)` de `tenant_scope.py` — é o padrão de referência a seguir.
- Frontend: `/admin/transferencias` hoje é `allowedRoles={['super_admin']}` em `frontend/src/App.js:129,133`. `ProtectedRoute.js:40-43` já normaliza equivalências de papel (inclusive `gerente`), então basta declarar `allowedRoles={['super_admin','admin','gerente']}` numa rota nova — sem necessidade de tratamento especial. O item de menu (`Dashboard.js`, `DASHBOARD_MENU_GROUPS`) é um terceiro ponto de decisão de visibilidade, desacoplado do backend e da rota — os três pontos (router backend, rota frontend, item de menu) não compartilham lógica hoje entre os dois fluxos.

### 1.9 Documentos verificáveis — cobertura desigual hoje

- Só a **declaração escolar** (`backend/services/school_docs_service.py`) usa `enrollments` como fonte primária (com fallback legado logado para `students.class_id`) e tem o ciclo completo: snapshot (`ai_analysis_snapshots`, hash SHA-256 + HMAC), código público `SIGESC-XXXX-XXXX`, endpoint público de verificação (`GET /api/public/verify/{code}`), revogação e supersessão reais (`verifiable_docs_service.py`).
- **Boletim via fila** (`bulletin_renderer.py`) tem hash/QR mas usa `students.class_id` (projeção legada) como fonte, e os campos de revogação em `bulletin_verifications`/`history_verifications` **existem no schema mas não têm endpoint de escrita em produção** — só são setados em testes que manipulam o Mongo diretamente.
- **Boletim síncrono legado** (`routers/documents.py`) e **ficha individual** não têm hash, QR, snapshot nem revogação — geração pura sob demanda a partir de `students.class_id`.
- `history_consolidator.py` (SSoT do Histórico Escolar) **recalcula ao vivo** a partir de `enrollments`/`grades`/`attendance` a cada emissão — corrigir os dados-fonte corrige automaticamente futuras emissões, mas **não retroage** sobre PDFs já hasheados e armazenados, que continuam "válidos" no portal público mesmo refletindo o erro documental anterior.
- `supersede_document` (`verifiable_docs_service.py:324-360`) é o precedente de design mais próximo do desejado: mantém o documento errado publicamente consultável com status `"substituido"`, aponta para o correto, nunca apaga.

### 1.10 Atomicidade — padrões reutilizáveis já maduros no repositório

Três camadas relevantes já existem e devem ser a base da estratégia de saga (§10), em vez de inventar um mecanismo novo:

1. `backend/lib/critical_mutation.py` — abstração genérica de idempotência (índice único `key+target`) + lock distribuído com TTL (`insert_one`/`replace_one` com `DuplicateKeyError`, TTL index nativo) + trilha de auditoria por execução. Já usado em `dedup_enrollments.py`, `grade_legacy_migration.py`, `student_series_backfill.py`.
2. `backend/routers/school_transfer.py` — dry-run com token TTL 24h, idempotência por token, lock simples por flag booleana em `classes` (`transfer_in_progress`, sem TTL — risco documentado de ficar preso se o processo crashar entre set/unset), snapshot pré-mutação, execução sequencial sem transação nativa, rollback como fase separada e auditável com janela de 7 dias ou até emissão de documento oficial.
3. Scripts de produção `P0-F7.9D4→D9` (`backend/scripts/*p0f7_9d4..9d7*`) — **o precedente mais rigoroso do repositório**: checagem de topologia obrigatória antes de decidir estratégia, CAS por documento com verificação de `matched_count`/`modified_count`, pré-flight completo antes da primeira escrita, verificação de pós-condição e colisão após cada escrita, rollback compensatório em ordem reversa, estados terminais explícitos (`PASS`, `FAILED_BEFORE_FIRST_WRITE`, `FAILED_ROLLED_BACK`, `CRITICAL_ROLLBACK_INCOMPLETE`), autorização humana por hash de plano selado.

Optimistic locking parcialmente implementado em `attendance.py:745-757,871-886` (grava `version` mas **não verifica `modified_count`** após o update condicional — colisão de CAS falha silenciosamente) — um gap a não repetir na retificação.

---

## 2. Inventário de coleções/estruturas

Matriz: coleção/estrutura × chave(s) de vínculo × ação futura proposta × risco.

| Coleção/estrutura | Chave(s) de vínculo | Ação futura proposta | Risco |
|---|---|---|---|
| `students` (projeção) | `id`, `class_id` (denormalizado), `student_series`, `school_id` | `rewrite` (via `rebuild_student_home_projection`, nunca edição direta) | Médio — se a reconstrução da projeção não for chamada, `students.class_id` diverge de `enrollments` |
| `students.atendimento_programa_class_id` | turma de programa especial, independente do `class_id` regular | `manual_review` | Baixo/médio — não deve ser tocado automaticamente; se o erro documental também afetou esse campo, é correção separada |
| `enrollments` (matrícula ativa/histórica) | `student_id, school_id, class_id, academic_year, status` | `rewrite` controlado (encerrar origem com novo `status`; criar nova matrícula de destino preservando `enrollment_number`) | Alto — índice único parcial `unique_active_enrollment_per_class` (`backend/startup/indexes.py:177-182`) deve ser respeitado; guard HTTP 409 existente precisa ser contornado só pela rota dedicada |
| `attendance` (Anos Finais: turma+data+componente+`aula_numero`) | `class_id, date, course_id, aula_numero, records[].student_id` | `manual_review` → decisão FREQ (§6): registros válidos tornam-se **retificação administrativa contabilizável** numa estrutura própria; nenhuma cópia bruta para aula/data não comprovada no destino | Alto — motor de cópia atual (`pedagogical_consolidation.py`) tem bugs comprovados nesse cenário (§1.6) |
| `attendance_documentary` (perfil integrador, `pdf_only`) | `class_id, assignment_id, date, ...` | `ignore` (nunca produz efeito acadêmico/estatístico) | Baixo |
| `grades` | `student_id, class_id, course_id, academic_year[, dependency_id]` | `move`/`rewrite` fail-closed (§7): só quando mapeamento curricular 1:1 comprovado; caso contrário `manual_review` bloqueante | Alto — sem índice único de banco; `grade_ownership` por campo amarrado ao `class_id` de origem |
| `student_dependencies` | `student_id, school_id, class_id (independente!), course_id, academic_year, origin_academic_year, origin_class_id` | `manual_review` | Médio — `class_id` de dependência é independente do vínculo regular; retificação da turma regular não deve propagar automaticamente |
| `content_entries` | `class_id, date, course_id, component_id, aula_numero` — **sem `student_id`** | `ignore` | Nenhum — confirmado turma-ancorado, não estudante-ancorado (`backend/routers/content_entries.py`, ausência total de `student_id`) |
| `academic_events` | `student_id, origin_class_id, destination_class_id, mantenedora_id, academic_year` | `rewrite` (novo `event_type` proposto, ou coleção irmã dedicada — decisão em §4/§15) | Médio — contrato normativo V1 está congelado e pressupõe preservação da origem; extensão exige decisão humana explícita |
| `student_history` | `student_id, school_id, class_id, action_type (enum fechado)` | `rewrite` (adicionar valor ao enum `action_type`) | Baixo — `Literal` de string, extensão compatível; mas requer teste de regressão nos consumidores que fazem match literal |
| `audit_logs` | `document_id, old_value, new_value` (genérico) | `preserve` + complementar com coleção de auditoria dedicada | Baixo — usar como camada adicional, não única fonte de auditoria da operação |
| Coleção de auditoria dedicada (nova, proposta) | `protocol, dry_run_token, snapshot[], student_id, origin/destination` | `move`/criar nova (não existe hoje) | — (parte do contrato proposto, §4/§12) |
| Documentos verificáveis (`verifiable_documents`, `ai_analysis_snapshots`, `bulletin_verifications`, `history_verifications`, `school_documents_log`) | `entity_type, entity_id, student_id, school_id, snapshot_id, code` | `revoke` quando aplicável + `manual_review` para reemissão (§8) | Alto — cobertura desigual (§1.9); revogação real só existe para `verifiable_documents` |
| DVD — `attendance` com `assignment_id`/`attendance_key_scope` | `class_id, assignment_id, date, course_id, aula_numero` | `manual_review` (motor de retificação deve ser DVD-aware) | Alto — hoje ignorado pelo motor de cópia existente |
| DVD — `grades.grade_ownership` (proveniência por campo) | `assignment_id, teacher_id, class_id` (snapshot imutável por bimestre) | `preserve` + gravar novo snapshot de proveniência quando aplicável | Alto — desalinhamento entre `class_id` de topo e snapshots internos já identificado como bug potencial |
| `classes` | `id, school_id, mantenedora_id, academic_year, grade_level` | `ignore` (turma de destino deve já existir e ser elegível; nunca criada pela retificação) | Baixo |
| `history_consolidator` (recomputo, não coleção persistida) | deriva de `enrollments`, `grades`, `attendance`, `student_dependencies`, `student_history` | `preserve` (recalcula automaticamente após correção da fonte) | Médio — não retroage sobre PDFs já emitidos (ver `verifiable_documents`) |
| AEE v2 (`backend/aee_v2/`) | `student_id, school_id` — **sem `class_id`/`enrollment_id`** | `preserve` (não tocar) | Nenhum — confirmado student-anchored por ausência total de `class_id`/`enrollment_id` no módulo; área protegida, nenhuma alteração foi feita |
| AEE legado (`planos_aee`) — campo `turma_origem_id`/`turma_origem_nome` | descritivo, não usado como chave de busca | `manual_review` (decisão de produto: aceitar como fotografia histórica ou sanear) | Baixo — cosmético, não funcional |
| Bolsa Família (`bolsa_familia_tracking`) | `student_id, school_id, month` — **sem `class_id` no doc de tracking** | `preserve` (não tocar) | Nenhum — confirmado student-anchored; `class_id` só aparece como filtro de UI via join com `students` |
| `class_students` (legado de leitura) | — | `manual_review` | Desconhecido — comentário no código confirma que é legado e não deve receber novas escritas (`enrollment_service.py:9`), mas não foi auditado se ainda há leitores dependentes da turma antiga |

---

## 3. Riscos e lacunas

1. **Guard-rail existente bloqueia a operação por design** (§1.2) — correto manter bloqueado para edição genérica; a retificação precisa de rota própria com suas próprias validações.
2. **Nenhum mecanismo atual modela "vínculo que nunca deveria ter existido"** — todo o ecossistema (`academic_events`, `student_history`, consolidação pedagógica) pressupõe legitimidade histórica da origem.
3. **Motor de cópia pedagógica tem bugs comprovados** em Anos Finais multi-componente/multi-aula (§1.6) — não reutilizável sem correção, e mesmo corrigido, tem semântica errada (copiar) para o objetivo (anular).
4. **Ausência de mapeamento curricular entre séries** — bloqueador direto para qualquer mapeamento 6º→7º automático de notas (§1.7, §7).
5. **MongoDB standalone, sem transação nativa** — qualquer operação multi-coleção precisa de saga/CAS explícito (§1.5, §10).
6. **Cobertura desigual de documentos verificáveis** — boletim síncrono e ficha individual não têm rastro de emissão, logo não há como detectar de forma confiável "documentos emitidos com a turma incorreta" nesses dois casos (§8).
7. **`grade_ownership` (DVD) amarra proveniência por campo ao `class_id` de origem** — uma retificação ingênua desalinha esse snapshot interno (§1.7).
8. **Optimistic locking incompleto** em `attendance.py` (grava `version` mas não verifica `modified_count`) — padrão a não repetir.
9. **Contrato `academic_events` está congelado (V1, FROZEN)** — qualquer extensão de `event_type` ou de invariante precisa de decisão humana e bump de versão, não pode ser silenciosa.
10. **Falta de rastreabilidade granular de notas no caminho legado** (`routers/grades.py` não grava `created_by`/`updated_by` nem chama `audit_service` nos endpoints singulares) — a retificação não pode assumir que existe histórico prévio confiável para basear decisões de proveniência.
11. **`class_students` legado** — não auditado se ainda tem leitores; risco de exibir turma antiga em algum relatório não mapeado nesta F0.
12. **RBAC hoje é decidido em três lugares desacoplados** (router backend, rota frontend, item de menu) sem compartilhamento entre Transferência Institucional e o que seria a retificação — risco de deriva se não for construída como módulo independente.

---

## 4. Contrato de domínio proposto — `retificacao_enturmacao`

### 4.1 Precondições

- Ator autenticado com papel em `{super_admin, admin, gerente}` e RBAC/tenant válidos conforme §9.
- Turma de origem e turma de destino pertencem à **mesma mantenedora + mesma escola + mesmo ano letivo** (restrição da primeira versão, §9).
- Existe exatamente uma matrícula **ativa** do estudante na turma de origem.
- Turma de destino existe, está ativa, e é elegível (mesma escola/ano letivo; validação de série/nível a definir em F1 conforme decisão humana, §15).
- Nenhuma outra operação administrativa sensível (remanejamento, transferência institucional, retificação) está em andamento para o mesmo `student_id` (lock, §10).
- Dry-run previamente executado com token válido (TTL a definir, seguindo o padrão de `school_transfer.py`, 24h).

### 4.2 Pós-condições

- Matrícula de destino `active`, com `class_id`/`school_id` corretos, preservando `enrollment_number`/data original de matrícula quando tecnicamente possível (§6 de contrato de matrícula/histórico, item do issue).
- Matrícula de origem com novo `status` (proposto: `rectified_out`, não reaproveitar `relocated`/`progressed`/`reclassified` — semântica distinta, ver §12).
- **FREQ-03**: nenhum `attendance.records[]` da turma de origem contém o `student_id` da estudante após a operação.
- Notas: valores/bimestres/conceitos preservados com proveniência, sem vínculo acadêmico ativo remanescente na turma errada (§7).
- Evento de auditoria dedicado, append-only, com snapshot before/after completo, protocolo, justificativa e ator.
- Documentos verificáveis emitidos com a turma incorreta identificados e sinalizados (revogados/superseded conforme política, §8).
- Nenhum resíduo detectável em nenhuma das estruturas do inventário (§2) classificadas como `move`/`rewrite`.

### 4.3 Invariantes (ver também §5, invariantes formais numeradas)

- A turma de origem nunca fica com vínculo acadêmico ativo residual do estudante.
- A operação é auditável integralmente (before/after) e nunca silenciosa.
- A operação nunca inventa data/aula/nota que não existiu.
- A operação é fail-closed diante de qualquer ambiguidade (tenant, mapeamento curricular, colisão de nota, componente sem correspondência).

### 4.4 Idempotência

Chave de idempotência dedicada (padrão `lib/critical_mutation.py`): `(student_id, origin_class_id, destination_class_id, academic_year, requested_by)` ou token explícito gerado no dry-run, com índice único. Reexecução com a mesma chave retorna o resultado já persistido, nunca reaplica a mutação.

### 4.5 Dry-run obrigatório

Sempre executado antes de qualquer escrita. Produz: relatório de impacto por coleção do inventário (§2), lista de bloqueios (ex.: componente sem mapa curricular, colisão de nota), token com TTL, sem qualquer efeito colateral.

### 4.6 Snapshot antes/depois

Snapshot completo por documento afetado (padrão `school_transfer.py:305-323`, usando `_id` como chave universal para coleções sem `id` próprio), persistido antes da primeira escrita.

### 4.7 Protocolo

Protocolo determinístico sequencial por mantenedora/ano, padrão `RETF-{ano}-{seq}` (mesmo estilo de `TRANSF-{ano}-{seq}` e `RECON-{ano}-{seq}` já existentes).

### 4.8 Auditoria

Coleção dedicada (proposta: `class_rectification_audit`), não apenas `audit_logs` genérico — seguindo o precedente de `school_transfer_audit`/`history_reconstruction_audit`.

### 4.9 Reautenticação

Reautenticação por senha imediatamente antes da execução (e do rollback, se elegível) — mesmo padrão de `school_transfer.py` (`verify_password`).

### 4.10 Justificativa obrigatória

Campo de texto livre com tamanho mínimo (proposto: `min_length=55`, alinhado ao valor mais rigoroso já usado no domínio institucional — reavaliar contra `academic_events` que usa 30) mais um campo estruturado opcional de tipo de erro documental (enum a definir em F1).

### 4.11 Frase de confirmação

Frase textual explícita obrigatória antes da execução, distinta da frase de Transferência Institucional (ex.: `"CONFIRMO A RETIFICAÇÃO DE MATRÍCULA/TURMA"`).

### 4.12 Política de rollback

Rollback elegível dentro de janela temporal (a definir — sugerido, por analogia, 7 dias) **e** somente se nenhum documento oficial verificável tiver sido emitido com base no estado pós-retificação. Rollback restaura a partir do snapshot, nunca recalcula.

### 4.13 Política de documentos previamente emitidos

Ver §8.

### 4.14 Detecção de resíduos pós-operação

Verificação de pós-condição obrigatória e automática (não apenas manual) varrendo todas as coleções do inventário classificadas como `move`/`rewrite`, confirmando ausência de `student_id` na turma de origem.

### 4.15 Concorrência / optimistic locking

Lock por `student_id` (não apenas por turma) durante toda a operação, com TTL, seguindo `lib/critical_mutation.py` (não a flag simples e sem TTL de `school_transfer.py`, que tem risco documentado de lock preso em crash).

---

## 5. Invariantes formais

- **INV-01**: A turma de origem nunca retém vínculo acadêmico ativo do estudante após a operação (matrícula, attendance.records[], grades ativos).
- **INV-02**: Nenhuma retificação cria, desloca ou atribui frequência individual a aula/data da turma destino não comprovadamente registrada naquela turma (= FREQ-01, §6).
- **INV-03**: Toda frequência válida do vínculo incorreto é preservada — nunca descartada, nunca inventada (= FREQ-02, §6).
- **INV-04**: Nenhum `attendance.records[]` da turma incorreta contém o `student_id` da estudante após a retificação (= FREQ-03, §6).
- **INV-05**: O mapeamento curricular origem→destino é 1:1 comprovado antes de mover qualquer nota; caso contrário, a operação falha fechada para aquele componente (§7).
- **INV-06**: Nenhuma nota é sobrescrita silenciosamente em caso de colisão no destino; colisão bloqueia a operação (fail-closed), diferente do padrão atual de merge silencioso.
- **INV-07**: A operação nunca altera silenciosamente um documento verificável já emitido (§8) — apenas revoga/supersede com rastro.
- **INV-08**: A operação é idempotente por chave dedicada; reexecução não duplica efeito.
- **INV-09**: A operação é fail-closed sem tenant válido, sem RBAC válido, ou sem mesma mantenedora+escola+ano letivo entre origem e destino (primeira versão).
- **INV-10**: Toda mutação é precedida de dry-run, snapshot, reautenticação, justificativa e frase de confirmação — nenhuma exceção.
- **INV-11**: AEE e Bolsa Família permanecem intactos (não tocados pela operação) — confirmado student-anchored (§1, §2).
- **INV-12**: `content_entries` nunca é tocado pela operação (turma-ancorado, não estudante-ancorado).

---

## 6. Decisão para frequência

### FREQ-01 (formalizada em INV-02)
Nenhuma retificação pode criar, deslocar ou atribuir frequência individual a aula/data da turma destino que não esteja comprovadamente registrada naquela turma. **Consequência de desenho**: a retificação NÃO tenta "casar" aulas da origem com aulas do destino por data — isso seria inventar correspondência não comprovada.

### FREQ-02 (formalizada em INV-03)
Toda frequência válida existente no vínculo incorreto deve ser preservada como (a) correspondência inequívoca com aula real do destino (caso raro, só quando datas/aulas realmente coincidem e isso é verificável automaticamente); ou (b) **retificação administrativa contabilizável**, sem fingir que o professor/turma destino ministrou aquela aula naquela data.

### FREQ-03 (formalizada em INV-04)
Após a retificação, nenhum `attendance.records[]` da turma incorreta pode conter o `student_id` da estudante.

### Decisão proposta: estrutura separada `attendance_rectifications`

**Proposta**: criar coleção dedicada `attendance_rectifications` (não implementar nesta F0) em vez de reaproveitar/estender `attendance.records[]` da turma destino.

**Modelo conceitual** (não implementado):
```
attendance_rectifications {
  id, protocol, student_id, origin_class_id, destination_class_id,
  academic_year, mantenedora_id, school_id,
  origin_records: [ { attendance_id, date, course_id, aula_numero, status } ],
  rectification_type: "administrative_count" | "verified_match",
  computed_summary: { presencas, faltas, justificadas, total_aulas_letivas_no_periodo },
  created_by, created_at, rationale, rectification_operation_id
}
```

**Vantagens**:
- Nunca precisa inventar `aula_numero`/data na turma destino — resolve FREQ-01 por construção.
- Satisfaz FREQ-03 diretamente: basta remover o `student_id` de `attendance.records[]` da origem (sem tocar no destino) e o cálculo de frequência anual passa a somar a estrutura de retificação em vez de records da turma incorreta.
- Auditável e reversível de forma limpa — apagar/desativar o registro de retificação não deixa vestígio em `attendance` real.
- Não colide com o índice único `(class_id, date, course_id, aula_numero)` de `attendance` nem com a extensão DVD (`assignment_id`/`attendance_key_scope`), porque não escreve na coleção `attendance` do destino.

**Riscos**:
- Introduz uma terceira fonte de dados de frequência (além de `attendance` e `attendance_documentary`) que **todo consumidor de frequência anual precisa aprender a somar** — risco de esquecimento em algum relatório (Bolsa Família, boletim, declaração de frequência) se a integração não for completa.
- Exige alteração na função de cálculo canônico de frequência anual (ainda não unificada — hoje há 3 padrões de agregação, §1.6) — esta F0 recomenda que a unificação dessa função seja pré-requisito ou parte do mesmo F1, não um trabalho paralelo desacoplado.

**Alternativa descartada**: gravar diretamente em `attendance.records[]` do destino com uma flag `rectified: true` e `rectified_from_class_id`. Descartada porque exigiria inventar `aula_numero`/data na turma destino (viola FREQ-01) ou deixar o documento sem essas chaves (repete o bug já identificado em `pedagogical_consolidation.py`, §1.6).

### Cálculo canônico combinado (proposto, não implementado)

O cálculo de frequência anual deve, para o ano letivo afetado, somar: (a) registros ordinários da turma destino onde o `student_id` aparece legitimamente (matrícula após a data de retificação) + (b) o `computed_summary` de `attendance_rectifications` referente ao período anterior à retificação — nunca somando (a) e a origem simultaneamente, já que a origem não deve mais conter o `student_id` (FREQ-03). Esta unificação de cálculo é um item de F1, não desta F0.

---

## 7. Decisão para notas/mapeamento curricular

**Não assumir que basta trocar `class_id`** — confirmado como correto por auditoria (§1.7): `grade_ownership` (DVD) amarra proveniência por campo ao `class_id`/`assignment_id` de origem; políticas de avaliação podem divergir por turma/série.

### Algoritmo de mapeamento curricular origem→destino (proposto, não implementado)

1. Para cada `course_id` com nota lançada na turma de origem, buscar candidato(s) de `course_id` na turma de destino.
2. **Comprovação de correspondência 1:1** aceitável apenas quando:
   - Existe metadado explícito de equivalência curricular entre os dois `course_id` (ex.: `Course.grade_levels` cobrindo ambas as séries com o mesmo `course_id` — caso hoje já suportado pelo schema, `backend/models.py:870`, mas não garantido pelos dados reais), OU
   - Existe uma tabela de mapa curricular explícito e auditável cadastrado antes da operação (não inferido automaticamente por nome/similaridade de string — nomes de componente podem colidir sem serem o mesmo componente pedagógico, como já evidenciado por `curriculum_resolver.py` até dentro de uma única turma).
3. Se não houver correspondência 1:1 comprovada → **fail-closed** para aquele componente: a operação bloqueia (não prossegue parcialmente) e reporta no relatório de dry-run como bloqueio a resolver manualmente.

### Condições de fail-closed (formalizadas)

- Não houver correspondência inequívoca de componente (INV-05).
- Houver colisão de nota já existente no destino (INV-06) — diferente do padrão atual de merge silencioso; a retificação deve **bloquear**, não mesclar, pois mesclar dados de um vínculo que nunca deveria existir com dados legítimos do destino corromperia a proveniência.
- Houver política/assignment incompatível entre origem e destino (quando `assessment_policy` estiver em runtime — hoje ainda não está, mas o desenho já deve prever).
- O mapeamento 1:1 não puder ser provado por nenhuma das duas vias do algoritmo acima.

### Preservação de valores, bimestres, conceitos e proveniência

Quando o mapeamento é aprovado: os valores de `b1..b4`/`rec_s1`/`rec_s2` migram para um **novo documento** de `grades` na turma de destino (não editar in-place o documento de origem — permite manter o documento de origem como evidência auditável, marcado como `superseded`/`rectified_out`, em vez de apagado). O novo documento grava um novo snapshot de proveniência em `grade_ownership` refletindo a retificação (novo `assignment_id` sintético ou campo dedicado `rectified_from`, a definir em F1) — nunca reaproveita cegamente o snapshot antigo, que aponta para o vínculo docente da turma errada.

O documento de origem permanece na coleção, mas some do cálculo de médias/boletim ativo do aluno (deixa de ser retornado pelas queries operacionais que filtram por matrícula ativa) — mecanismo exato a definir em F1 (`status` no documento de grades vs. campo `rectified: true` filtrável).

---

## 8. Política documental

### Detecção de documentos emitidos com a turma incorreta

Dado o achado de §1.9 (cobertura desigual), a política precisa ser desenhada em duas camadas:

1. **Documentos com rastro verificável** (`verifiable_documents`, `bulletin_verifications` quando aplicável via `snapshot_id`/`entity_id=student_id`): consulta direta por `student_id` + `entity_type` + intervalo de datas anterior à retificação.
2. **Documentos sem rastro** (boletim síncrono legado, ficha individual): **não podem ser detectados automaticamente** hoje. Proposta: a F0 recomenda que, antes de F1 habilitar a retificação em produção, esses dois geradores sejam migrados para o padrão verificável (fora do escopo desta operação, mas é um pré-requisito de risco a decidir humanamente — §15).

### Política proposta (não implementada)

- **Identificar**: listar todos os `verifiable_documents` com `entity_id=student_id` emitidos com `class_id`/turma igual à origem antes da data da retificação.
- **Revogar quando aplicável**: usar `revoke_document` para documentos cujo conteúdo se torna materialmente incorreto após a retificação (ex.: declaração de matrícula referenciando a turma errada). Não revogar documentos cujo conteúdo continua factualmente correto para o período em que foram emitidos (ex.: uma declaração de frequência do período em que a estudante genuinamente frequentou aulas, mesmo que administrativamente na turma errada) — decisão caso a caso a refinar em F1.
- **Registrar motivo/protocolo**: toda revogação referencia o protocolo `RETF-{ano}-{seq}` da retificação.
- **Permitir reemissão correta**: expor endpoint de reemissão que gera novo documento com `superseded_by_document_id` apontando para o revogado, seguindo o padrão já existente de `supersede_document`.
- **Nunca alterar silenciosamente um documento verificável já emitido** (INV-07) — nenhuma escrita in-place em `verifiable_documents`/`ai_analysis_snapshots` fora dos endpoints de revogação/supersessão já existentes.

---

## 9. RBAC / multi-tenancy

- Papéis autorizados: `super_admin`, `admin`, `gerente`.
- `admin`/`gerente`: restritos à própria mantenedora — validar via `get_user_mantenedora_id(user)`/`get_mantenedora_scope(user, request)` (não apenas `AuthMiddleware.require_roles`, que por si só não diferencia escopo de tenant entre `admin` e `gerente`).
- `super_admin`: opera o tenant selecionado no momento (header `X-Mantenedora-Id`), nunca modo "Todas" nesta operação.
- Origem e destino, na primeira versão: **mesma mantenedora + mesma escola + mesmo ano letivo** — validação bloqueante equivalente a `SAME_MANTENEDORA` de `school_transfer.py`, mais checagem adicional de mesma escola (diferente da Transferência Institucional, que move entre escolas).
- Fail-closed sem tenant válido: usar `apply_tenant_filter`/`resolve_tenant_id_for_create` (canônicos) para toda leitura/escrita — não reproduzir o desvio de `school_transfer.py` que deriva `mantenedora_id` do documento em vez do helper.
- **Nenhuma abertura de permissão da Transferência Institucional existente** — construir como módulo backend independente (novo router dedicado, ex. `enrollment_class_rectification.py`), sem branch condicional dentro de `school_transfer.py`.
- Frontend: nova página separada de `SchoolTransfers.jsx`/`SchoolTransferWizard.jsx`; nova rota com `allowedRoles={['super_admin','admin','gerente']}`; novo item em `DASHBOARD_MENU_GROUPS` com visibilidade correspondente; novo bloco de API client separado de `schoolTransferAPI`.

---

## 10. Atomicidade / rollback

Confirmado (§1.5, §1.10): produção roda MongoDB standalone, sem transação multi-documento nativa. Estratégia obrigatória: **saga com CAS por documento e rollback compensatório**, seguindo o precedente mais maduro do repositório (scripts P0-F7.9D4→D9) e reaproveitando a infraestrutura de `lib/critical_mutation.py`.

### Estado de operação (proposto)

Máquina de estados por execução de retificação: `PENDING_DRY_RUN → DRY_RUN_VALIDATED → LOCKED → EXECUTING → PASS | FAILED_BEFORE_FIRST_WRITE | FAILED_ROLLED_BACK | CRITICAL_ROLLBACK_INCOMPLETE → (opcional) ROLLED_BACK_BY_REQUEST`.

### Componentes obrigatórios

- **Locks**: lock por `student_id` (TTL, via `lib/critical_mutation.py`), impedindo qualquer outra operação administrativa sensível concorrente sobre o mesmo estudante.
- **Idempotência**: chave dedicada com índice único (padrão `critical_mutation.py:141-143`).
- **Snapshot**: completo, por documento, antes da primeira escrita (padrão `school_transfer.py:305-323`).
- **CAS por documento**: cada escrita usa filtro condicional (valor esperado do campo mutável) e verifica `matched_count`/`modified_count` — corrigindo o gap já identificado em `attendance.py` (§1.10) de não verificar isso.
- **Pré-flight completo** antes de qualquer escrita: revalida todas as precondições (§4.1) contra o estado atual do banco.
- **Pós-validação obrigatória** após cada escrita e uma verificação global final (padrão do executor `mongosh` de P0-F7.9D7).
- **Rollback compensatório em ordem reversa** em caso de falha após pelo menos uma escrita, com estados terminais explícitos.
- **Recuperação após falha parcial**: reexecução idempotente a partir do estado persistido (nunca assume que uma reexecução do zero é segura sem checar o estado atual).

---

## 11. Endpoints propostos para F1 (não implementar nesta F0)

Prefixo proposto: `/api/admin/enrollment-rectification` (router novo e dedicado, análogo a `school_transfer.py` mas não estendendo-o).

| Método | Rota | Propósito |
|---|---|---|
| `POST` | `/dry-run` | Valida precondições, mapeamento curricular, gera relatório de impacto e token TTL |
| `POST` | `/execute` | Executa a retificação (exige token de dry-run válido, reautenticação, frase de confirmação, justificativa) |
| `GET` | `/{protocol}` | Consulta detalhe de uma retificação já executada |
| `GET` | `/` | Lista retificações (escopo por tenant/role) |
| `GET` | `/rollback-eligibility/{protocol}` | Verifica elegibilidade de rollback |
| `POST` | `/rollback/{protocol}` | Executa rollback (reautenticação + frase própria) |
| `GET` | `/{protocol}/receipt` | Recibo/protocolo em PDF verificável |
| `GET` | `/eligible-classes` | Lista turmas de destino elegíveis (mesma escola/ano letivo) para o estudante localizado |

---

## 12. Modelo de dados proposto (sem implementar)

### `class_rectification_audit` (nova coleção, análoga a `school_transfer_audit`)

```
{
  id, protocol ("RETF-{ano}-{seq}"), student_id, mantenedora_id, school_id, academic_year,
  origin_class_id, destination_class_id,
  status, dry_run_token, idempotency_key,
  rationale, requested_by, approved_by (se aplicável),
  snapshot: [ { collection, doc_id, before, after } ],
  grade_mapping_result: [ { origin_course_id, destination_course_id, status: "mapped"|"blocked", reason } ],
  attendance_rectification_ids: [...],
  documents_flagged: [ { verifiable_document_id, action: "revoked"|"kept"|"pending_review" } ],
  lock_holder, lock_acquired_at, lock_released_at,
  created_at, executed_at, rolled_back_at
}
```

### `attendance_rectifications` — ver §6.

### Extensão de `enrollments.status` (novo valor de enum, não estrutural)

Novo valor proposto: `rectified_out` (matrícula de origem) — distinto de `relocated`/`progressed`/`reclassified` porque a semântica é "nunca deveria ter existido", não "encerrada legitimamente".

### Extensão de `student_history.action_type` (novo valor de `Literal`)

Novo valor proposto: `retificacao` — adicionado ao enum fechado em `backend/models.py:1203`.

### Extensão de `grades` (campo novo, não estrutural)

Campo proposto `rectified_from_class_id`/`rectified_at` no documento migrado, análogo a `migrated_from_class_id`/`migrated_at` já usado pela consolidação pedagógica, mas semanticamente distinto (retificação, não continuidade).

Nenhum destes campos/coleções foi criado nesta F0 — são propostas de modelo para F1.

---

## 13. Matriz de testes exigidos para F1

| # | Cenário | Objetivo |
|---|---|---|
| 1 | Cenário sintético 6º → 7º completo (dry-run + execução) | Caminho feliz ponta a ponta |
| 2 | Frequência com datas coincidentes entre origem/destino | Confirma que FREQ-01 não é violada mesmo quando datas coincidem por acaso |
| 3 | Frequência com datas NÃO coincidentes | Confirma uso de `attendance_rectifications` em vez de invenção de aula |
| 4 | Componente curricular sem correspondência | Fail-closed (INV-05) |
| 5 | Colisão de nota no destino | Fail-closed (INV-06), sem merge silencioso |
| 6 | Matrícula destino já existente (conflito com índice único) | Tratamento correto do índice `unique_active_enrollment_per_class` |
| 7 | Dados órfãos (nota/attendance sem matrícula correspondente) | Comportamento definido e auditável |
| 8 | Documentos verificáveis emitidos antes da retificação | Detecção, flag e política de revogação (§8) |
| 9 | AEE/Bolsa Família preservados | Confirma INV-11 — nenhuma alteração colateral |
| 10 | Fail-closed de tenant (origem/destino de mantenedoras diferentes) | INV-09 |
| 11 | RBAC — `super_admin`/`admin`/`gerente` permitidos; demais papéis bloqueados | §9 |
| 12 | RBAC — `admin`/`gerente` de mantenedora diferente da do estudante | Fail-closed de escopo |
| 13 | Idempotência — reexecução com mesma chave não duplica efeito | INV-08 |
| 14 | Falha parcial + recuperação (simular crash após 1ª escrita) | §10 |
| 15 | Rollback elegível (dentro da janela, sem documento oficial emitido) | §4.12 |
| 16 | Rollback inelegível (fora da janela ou após emissão de documento) | §4.12 |
| 17 | Pós-condição: origem com zero vínculos acadêmicos ativos da estudante | INV-01/FREQ-03 |
| 18 | Concorrência — duas tentativas simultâneas de retificação do mesmo estudante | Lock (§4.15/§10) |
| 19 | DVD — turma de origem ou destino operando em modo `assignment_session` | Motor deve ser DVD-aware (gap identificado em §1.6) |
| 20 | Cálculo de frequência anual pós-retificação sem dupla contagem | Unificação de cálculo (§6) |

---

## 14. Plano incremental F1/F2/F3

- **F1 (proposto)**: unificação da função de cálculo de frequência anual (pré-requisito, §6); implementação do contrato `retificacao_enturmacao` restrita a **mesma escola** (sem mover entre escolas); dry-run + execução + auditoria + rollback; sem UI ainda (endpoints backend + testes da matriz §13); migração dos dois geradores de documento sem rastro (boletim síncrono, ficha individual) para o padrão verificável **como pré-requisito de habilitar a política documental completa (§8)**.
- **F2 (proposto)**: UX completa (`/admin/transferencias` evoluindo para central de movimentações, conforme fluxo de 13 passos do issue original); relatório de impacto detalhado; reemissão de documentos revogados.
- **F3 (proposto)**: extensão de escopo (se decidido humanamente) para mover entre escolas da mesma mantenedora; integração formal com `assessment_policy` runtime quando este tiver cutover; consolidação de `attendance_rectifications` em relatórios oficiais (Bolsa Família, censo escolar, se aplicável).

Cada fase requer autorização humana explícita antes de iniciar implementação, conforme CLAUDE.md.

---

## 15. Questões que ainda precisam de decisão humana

1. **Nome e estrutura definitiva de `attendance_rectifications`** — a proposta desta F0 é uma coleção separada; alternativas (ex.: subdocumento dentro de `enrollments`) não foram descartadas por engenharia, apenas por design preferencial. Requer validação humana antes de F1.
2. **Extensão ou não do contrato `academic_events` (V1, FROZEN)** — adicionar `event_type: retificacao_enturmacao` ao enum existente, versus manter os dois domínios (movimentação legítima vs. retificação de erro) completamente separados. Envolve bump de `contract_version` e revisão do documento normativo `ACADEMIC_EVENT_CONTRACT.md`.
3. **Janela de rollback e limite de justificativa mínima** — valores propostos (7 dias, 55 caracteres) são análogos ao existente, não uma exigência técnica; confirmar com o responsável do produto.
4. **Política exata de revogação de documentos** — quando revogar vs. quando manter um documento verificável já emitido como "correto para o período em que foi emitido" (§8) precisa de definição de negócio/jurídica, não é puramente técnica.
5. **Pré-requisito de migrar boletim síncrono/ficha individual para o padrão verificável antes de habilitar retificação em produção** — esta F0 recomenda isso como bloqueador; requer confirmação humana, pois amplia o escopo de F1.
6. **Extensão futura para mover entre escolas da mesma mantenedora (F3)** — hoje fora de escopo da primeira versão; precisa decisão explícita se/quando ampliar.
7. **Tratamento do campo cosmético `turma_origem_id`/`turma_origem_nome` em planos AEE legados** — aceitar como fotografia histórica ou saneamento futuro (não funcional, mas visível a usuários).
8. **Se e como o `class_students` legado ainda é lido em algum relatório** — não auditado nesta F0; recomenda-se auditoria dedicada antes de F1 fechar o desenho de propagação.
9. **Modelo de mapeamento curricular explícito** — se será uma tabela administrável por gestores de currículo, ou apenas o campo `Course.grade_levels` já existente (hoje não confiável nos dados reais, §7) — decisão de produto que impacta diretamente a viabilidade de mover notas automaticamente.
10. **Frase de confirmação e nomenclatura final exposta ao usuário** — nomes propostos neste documento (`RETF-{ano}-{seq}`, frase de confirmação) são sugestões técnicas, não texto final de UX/jurídico.

---

## Confirmação de restrições respeitadas nesta F0

- Nenhuma alteração foi feita em `students`, `enrollments`, `attendance`, `grades` ou qualquer dado real.
- Nenhuma retificação foi executada para a estudante motivadora nem para qualquer outro registro real.
- Nenhum endpoint funcional foi criado.
- Nenhum writer/migration/script de mutação foi criado.
- Nenhuma alteração funcional foi feita em AEE (`backend/aee_v2/` e `planos_aee` foram apenas lidos).
- Nenhum schema/índice foi alterado.
- Nenhum merge em `main` foi realizado.
- Auto-merge não foi habilitado.
- Nenhum deploy foi realizado.
- Este documento não expõe dados pessoais reais além do necessário para descrever o caso motivador em termos genéricos (série de origem/destino), sem nome, CPF ou qualquer identificador real da estudante.
