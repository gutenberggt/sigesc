# Auditoria de Movimentação de Alunos — Preservação e Rastreabilidade Pedagógica

> Status: **AUDITORIA (sem implementação)**. Conclusões baseadas em **evidência real**:
> leitura de código + execução controlada em banco isolado (`scripts/_audit_student_movement.py`)
> + inspeção das coleções antes/depois. Reproduzível a qualquer momento.

## 1. Mapeamento dos fluxos (endpoints / serviços / coleções)

| Fluxo | Onde vive (código) | O que faz nas coleções |
|---|---|---|
| **Remanejamento** (mesma escola, troca de turma) | `PUT /api/students/{id}` (`routers/students.py`, bloco ~1606–1661, `action_hint='remanejamento'`) + chamada **separada** `POST /api/students/{id}/copy-data` (~2210–2340) | Matrícula antiga → status `relocated`; cria nova matrícula `active` (turma destino); atualiza `students.class_id`. `copy-data` **copia** `attendance` e `grades` da origem→destino (marca `migrated_from_class_id`). |
| **Progressão** (avanço de série/ano) | mesmo `PUT` (`action_hint='progressao'` → status `progressed`) + `copy-data` (`copy_type='progressao'`) | Igual ao remanejamento. Variante "progredir e emitir histórico" → status `transferred`, **sem** nova turma e **sem** copy (fluxo de saída). |
| **Reclassificação** | mesmo `PUT` (`action_hint='reclassificacao'` → status `reclassified`) + `copy-data` (`copy_type='reclassificacao'`) | Igual ao remanejamento. |
| **Transferência entre escolas (mesma mantenedora)** | **Motor próprio**: `routers/school_transfer.py` (`/dry-run`, `/execute`, `/rollback`) — âncora `class_id` | Move a **turma inteira** alterando `school_id` em `classes` (+`school_history[]`), `students`, `enrollments`, `attendance`, `grades`, `content_entries`, `student_dependencies`, `teacher_class_assignments`, AEE (`planos_aee`, `atendimentos_aee`, ...), `bolsa_familia_tracking`. **NÃO** usa `copy-data`. |
| **Histórico Escolar (consolidação)** | `services/history_consolidator.py` → `build_consolidated_history()` | Lê `enrollments` agrupando por (ano, turma); agrega `grades` por **student_id+ano+course_ids da turma** (independe da turma atual) e `attendance` por **class_id+ano**; resolve a escola da época via `school_history[]`. |

**Acionamento do `copy-data`:** é **disparado pelo FRONTEND** (`StudentsComplete.js` ~1130–1175) em remanejar/reclassificar/progredir, dentro de `try/catch` que **NÃO interrompe o fluxo** em erro. O backend **não** chama `copy-data` automaticamente no `PUT`.

---

## 2. Matriz coleção × comportamento (evidência de banco)

Cenário executado: aluno na Turma A com 1 nota (b1=8, b2=7), 2 frequências (1 P, 1 F), 1 conteúdo, 1 AEE, 1 Bolsa Família. Remanejado A→B e depois retornado B→A (mesmo ano letivo).

| Coleção | Origem após mover | Destino após mover | Comportamento | Evidência |
|---|---|---|---|---|
| `grades` (notas) | **Preservada** (grades_A=1) | **Cópia** (grades_B=1, `migrated_from_class_id` setado) | **Duplicação** controlada (idempotente: retorno não re-duplica) | snapshots A→B: grades_A=1, grades_B=1, grades_B_migrated=1 |
| `attendance` (frequência) | **Preservada** (att_A=2) | **Cópia** (att_B=2) | **Duplicação** (cópia por data) | att_A_recs=2, att_B_recs=2 |
| `content_entries` (conteúdo) | **Preservada** (content_A=1) | **NÃO copiado** (content_B=0) | ⚠️ **Lacuna**: conteúdo NÃO migra no remanejamento/progressão/reclassificação | content_A=1, content_B=0 |
| `enrollments` | antiga → `relocated/progressed/reclassified` | nova → `active` | Histórico de matrículas preservado | enroll_all = [(A,relocated),(B,active)] |
| `students.class_id` | — | atualizado p/ destino | OK | class_id: A→B→A |
| `planos_aee` (AEE) | **Intacto** (student-anchored) | — | **Preservado**, sem quebra | aee=1 antes e depois |
| `bolsa_familia_tracking` | **Intacto** (student-anchored) | — | **Preservado**, sem duplicação/perda | bolsa=1 antes e depois |

---

## 3. Respostas às questões obrigatórias

**Frequência**
- Origem permanece intacta? **SIM** (att_A=2 preservadas).
- Copiada para histórico? **SIM, para a turma destino** (cópia em `attendance`, não para coleção de histórico separada).
- Visível no Histórico Escolar? **SIM** — `_aggregate_attendance` por (class_id, ano).
- Cálculo anual correto? **PARCIAL/RISCO** — o Histórico consolidado mostra **2 registros para o MESMO ano** (turma A e turma B), cada um com frequência (50% e 50%) → ver item 7. Não há perda, mas há **duplicação de linha por turma**.

**Notas e conceitos**
- Origem preservada? **SIM** (grades_A=1).
- Consolidação por período? **SIM** — `build_consolidated_history` agrega notas por **student+ano+curso**, independente da turma atual (valor 7.5 aparece corretamente).
- Migração parcial? **SIM** — `copy-data` copia notas (e frequência), **mas não conteúdo**.
- Perda de vínculo após troca de turma? **NÃO** para notas (agregação por student+ano+curso). Mas há **duplicação** (nota existe em A e em B).

**AEE**
- Atendimentos permanecem vinculados? **SIM** — `planos_aee`/atendimentos são por `student_id`; movimentação por turma não os altera.
- Quebra de histórico? **NÃO** no remanejamento/progressão/reclassificação. Na transferência entre escolas, o motor reescreve `school_id` (preserva vínculo) — OK.

**Bolsa Família**
- Acompanhamento íntegro? **SIM** (por `student_id`).
- Duplicação/perda? **NÃO** (1 registro antes e depois).

**Histórico Escolar (Turma A → Turma B)**
- Frequência do período A: aparece (50%). Notas do período A: aparecem (7.5). Resultados independem da turma atual para **notas** (agregação por student+ano+curso). ✅ para preservação.
- ⚠️ **PORÉM**: o consolidado gera **2 linhas para o mesmo ano/série** (uma por turma cursada no ano), ambas com nota 7.5 e freq 50% → **duplicação de registro de ano letivo** no histórico. Legalmente, um ano/série deve aparecer **uma única vez consolidada**.

---

## 4. Cenário de auditoria obrigatória — resultado

Executado A→B (remanejamento) e retorno B→A (evidência na seção 2):
- **Origem preservada:** ✅ (notas, frequência, conteúdo permanecem em A).
- **Destino ativo:** ✅ (matrícula B active; notas/frequência copiadas; **conteúdo NÃO**).
- **Histórico completo:** ⚠️ presente, porém **duplicado por turma** no ano.
- **Retorno:** ✅ idempotente para notas (sem re-duplicar); matrículas acumulam (A relocated, B relocated, A active).

Progressão e reclassificação: **mesmo caminho de código** do remanejamento (apenas muda `action_hint`/status e `copy_type`) → **mesmo comportamento e mesmas lacunas**.
Transferência entre escolas: caminho **distinto e mais íntegro** (move a turma inteira por `class_id`, **inclui `content_entries`**, sem duplicação, com `school_history[]` e rollback auditado).

---

## 5. O que funciona / não funciona / riscos

**Funciona**
- Preservação da origem (notas, frequência, conteúdo) em todos os fluxos.
- Consolidação de **notas** independente da turma atual (`build_consolidated_history`).
- AEE e Bolsa Família intactos (ancorados em `student_id`).
- Transferência entre escolas: completa, sem duplicação, com `school_history[]` e rollback.

**Não funciona / lacunas**
1. **Conteúdo (`content_entries`) NÃO é copiado** em remanejamento/progressão/reclassificação (só notas e frequência). Diário do destino fica sem o conteúdo do período cursado na origem.
2. **Histórico Escolar duplica o ano/série** quando há troca de turma no mesmo ano (1 linha por turma) — risco legal.
3. **`copy-data` é frontend-triggered e fail-silent** (try/catch que não interrompe). Se falhar (rede/offline/erro), a movimentação conclui mas notas/frequência **não migram** ao destino — **perda silenciosa na visão da turma atual**.
4. **`academic_year` da nova matrícula = `datetime.now().year`** (students.py ~1617), desacoplado do `academic_year` da turma. Movimentação feita em ano diferente do da turma gera matrícula com ano divergente → histórico fragmentado.
5. **Duplicação de notas/frequência** (origem + destino): seguro para o consolidado por notas, mas qualquer relatório que **some por aluno×ano através de turmas** pode **contar em dobro** a frequência (a verificar caso a caso).

**Riscos**
- **Pedagógico:** boletim/diário do destino sem conteúdo; histórico com ano duplicado confunde resultado final.
- **Legal:** Histórico Escolar oficial com a mesma série repetida; risco em transferências/comprovações.
- **Relatórios:** possível dupla contagem de frequência em agregações por aluno×ano; Censo pode divergir.
- **Operacional:** consolidação depende de uma chamada de frontend que pode falhar silenciosamente.

---

## 6. Decisão recomendada (após auditoria)

**O mecanismo canônico de preservação/consolidação JÁ EXISTE** (`copy-data` + `build_consolidated_history`). Portanto, conforme a regra definida, a recomendação é **corrigir os fluxos/lacunas que não o acionam corretamente**, e **complementar** com a ferramenta de reprocessamento (porque há dados legados já movidos com as lacunas acima):

**P0 — Correções dirigidas**
- Acionar a consolidação **no backend** (dentro do `PUT`), de forma transacional, em vez de depender do frontend fail-silent. (Ou, no mínimo, falhar visivelmente e registrar pendência.)
- Incluir **`content_entries`** na cópia (`copy-data`) de remanejamento/progressão/reclassificação.
- **Deduplicar o Histórico Escolar** por (ano, série): consolidar múltiplas turmas do mesmo ano em **um único registro** (mantendo rastreabilidade da(s) turma(s) de origem).
- Corrigir o `academic_year` da nova matrícula para herdar o **ano da turma destino**, não `now().year`.

**P1 — Ferramenta de Administração: "Reconstrução de Histórico Pedagógico"**
Necessária para **dados legados** já movidos sem consolidação completa. Capaz de reprocessar, para **alunos / turmas / escola inteira** selecionados:
- frequência, notas, conceitos e histórico (re-rodar a consolidação canônica de forma idempotente),
- com **dry-run** + relatório do que será alterado + auditoria, no padrão já usado na Transferência Institucional.

---

## 7. Reprodutibilidade
- Script de evidência: `backend/scripts/_audit_student_movement.py` (sandbox isolado `AUDMOV-*`, self-teardown).
- Saída-chave (mesmo ano): grades A=1/B=1(migrated), attendance A=2/B=2, **content A=1/B=0**, AEE/Bolsa intactos; Histórico consolidado = **2 registros para o mesmo ano** (turma A e B), ambos 7.5 / 50%.
