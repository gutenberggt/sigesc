# AUDITORIA — Impacto da Transferência Institucional em Relatórios/Analytics/Exportações
> **Read-only. Nenhuma correção implementada.** Pré-requisito solicitado antes da Fase 2 (Rollback).
> Base: varredura real do backend SIGESC (FastAPI + Mongo), Jun/2026.

---

## 0. Achado central (governa toda a matriz)

No **re-homing (Opção A)**, a Fase 1 sobrescreve `school_id` para o **destino** em DUAS camadas:
1. `classes.school_id` (fonte) — e registra `classes.school_history[]` (com `start_date`/`end_date`).
2. **Cópias denormalizadas** de `school_id` em `students, enrollments, attendance, grades,
   content_entries, teacher_class_assignments, student_dependencies, planos/atendimentos_aee,
   bolsa_familia_tracking`.

⚠️ **Nenhum desses registros transacionais carrega dimensão temporal de escola.** A ÚNICA fonte
temporal é `classes.school_history[]`. **Nenhum relatório/analytics consulta `school_history[]` hoje.**

Consequência: **todo relatório que escopa por escola atribui o histórico INTEIRO da turma/alunos
movidos à escola de DESTINO** (inclusive períodos anteriores à transferência). A origem perde a
atribuição. O risco é máximo em: (a) transferência no MEIO do ano; (b) relatórios cross-ano; (c)
documentos legais e Censo (ano-base + INEP).

Há **dois padrões de filtro** no código:
- **Padrão A — escola→turmas→`class_id`**: resolve `classes.find({school_id})` → usa `class_id`
  para filtrar attendance/grades. Impactado porque `classes.school_id` mudou.
- **Padrão B — `school_id` denormalizado direto**: filtra `students/enrollments/bolsa/aee` por
  `school_id`. Impactado porque sobrescrevemos `school_id` nesses registros.

✅ **Resolução canônica recomendada (para a sub-fase de correção):** para um registro com `date`/
`academic_year` e `class_id` C, a escola correta = aquela cujo intervalo em `C.school_history[]`
cobre a data do registro. `school_history[]` é **necessário e suficiente** (os registros já têm
`date`/`academic_year`).

---

## MATRIZ DE IMPACTO

Legenda Risco: 🔴 Alto · 🟠 Médio · 🟢 Baixo/Nenhum.

| # | Endpoint | Coleção(ões) | Critério de filtro atual | Impacto pós-transferência | Precisa `school_history`? | Risco |
|---|---|---|---|---|---|---|
| 1 | `GET /api/analytics/overview` | classes, students, enrollments, attendance, grades | Padrão A (att/notas) + Padrão B (alunos/matrículas), filtra por `academic_year` | KPIs da escola (turmas, alunos, frequência, média, aprovação) da turma movida migram p/ destino; origem zera | **Sim** (recortes por período/escola) | 🔴 |
| 2 | `GET /api/analytics/enrollments/trend` | enrollments | Padrão B + série temporal por `date` | Série mensal de matrículas: meses ANTERIORES à transferência aparecem no destino | **Sim** | 🔴 |
| 3 | `GET /api/analytics/attendance/monthly` | classes→attendance | Padrão A, agrupado por mês | Frequência mensal histórica reatribuída ao destino | **Sim** | 🔴 |
| 4 | `GET /api/analytics/grades/by-subject` | classes→grades | Padrão A | Rendimento por disciplina histórico reatribuído | **Sim** | 🟠 |
| 5 | `GET /api/analytics/grades/by-period` | classes→grades | Padrão A, por bimestre | Rendimento por período histórico reatribuído | **Sim** | 🟠 |
| 6 | `GET /api/analytics/schools/ranking` | classes, grades, attendance, enrollments | Padrão A/B por escola | **Ranking de escolas/gestores distorcido** (origem perde, destino infla com passado) | **Sim** | 🔴 |
| 7 | `GET /api/analytics/students/performance` | students, grades, attendance | Padrão B/A | Desempenho do aluno segue o aluno (ok), mas recorte por escola/período distorce | Parcial | 🟠 |
| 8 | `GET /api/analytics/teachers/performance` | classes→grades/attendance | Padrão A | Performance docente por escola distorcida no período anterior | **Sim** | 🟠 |
| 9 | `GET /api/analytics/distribution/grades` | classes→grades | Padrão A | Distribuição de notas por escola distorcida | **Sim** | 🟠 |
| 10 | `GET /api/diary-dashboard/attendance` | classes→attendance | Padrão A, `academic_year` | Preenchimento de frequência: ano corrente da turma some da origem | Parcial (ano corrente) | 🟠 |
| 11 | `GET /api/diary-dashboard/grades` | classes→grades | Padrão A | Idem notas | Parcial | 🟠 |
| 12 | `GET /api/diary-dashboard/content` | classes→content_entries | Padrão A | Idem conteúdos | Parcial | 🟢 |
| 13 | **Histórico Escolar PDF** `POST /api/students/{id}/historico-consolidado/render-pdf` | enrollments, grades, attendance, students | Geração lê dados ATUAIS; `job.school_id = student.school_id` (atual) | **Documento legal**: histórico consolidado por ano pode exibir a ESCOLA atual (destino) para anos anteriores | **Sim** (escola por ano letivo) | 🔴 |
| 14 | **Boletim PDF** `bulletin_pdf` / `bulletins` | grades, classes | Geração lê turma atual | Boletins GERADOS após a transferência atribuem ao destino | **Sim** (no momento da geração) | 🟠 |
| 15 | **PDFs/snapshots JÁ emitidos** `verifiable_documents`, `document_render_jobs`, `diary_snapshots`, `history_pdf` renderizado | (imutável) | school_id congelado na emissão | **NÃO impactado** (registro legal imutável) | Não | 🟢 |
| 16 | `POST /api/monthly-reports/generate` (+ `/pdf`, `/send-email`) | agregados por **mantenedora** | Escopo por `mantenedora_id` (rede), NÃO por escola | Re-homing é **intra-mantenedora** ⇒ soma da rede inalterada; só muda atribuição por escola se o relatório detalhar por escola | Verificar layout interno | 🟢 |
| 17 | `GET /api/mec/elegibilidades` | — (proxy MEC) | Pass-through à API do MEC | **NÃO impactado** (sem escopo local de escola) | Não | 🟢 |
| 18 | `GET /api/mec/students/mapping` | students | `school_id` atual | Mapeamento de estado ATUAL (aceitável); INEP do destino | Não (estado atual) | 🟢 |
| 19 | **Censo Escolar (exportação INEP)** — conceitual / a confirmar onde é gerado | classes, students, enrollments | Ano-base + escola/INEP | 🔴 **CRÍTICO**: escola encerrada deve declarar seu censo do período; dados migrados inflam o destino e somem da origem | **Sim** (obrigatório) | 🔴 |
| 20 | `GET /api/bolsa-familia/stats/network` (+ `/followup`, `/export`) | students, bolsa_familia_tracking, attendance | Rede + `school_id` opcional | Busca Ativa opera no presente (ok); recortes por escola/período da turma movida distorcem | Parcial | 🟠 |
| 21 | `GET /api/bolsa-familia/pdf/{school_id}` | students, bolsa, attendance | Por `school_id` | Relatório por escola: alunos movidos somem da origem | **Sim** (por período) | 🟠 |
| 22 | `GET /api/aee/diario`, `/estudantes`, `/planos`, `/atendimentos` | planos_aee, atendimentos_aee, students | `school_id` denormalizado | AEE segue o aluno (ok operacional); relatórios por escola/período distorcem | Parcial | 🟠 |

---

## RESUMO POR CRITICIDADE

- 🔴 **ALTO (corrigir antes do Rollback):**
  - Censo Escolar (#19) — obrigação legal por ano-base/INEP.
  - Histórico Escolar PDF (#13) — documento legal por ano letivo.
  - Frequência (#3, #2) e Rendimento (#1, #6) — analytics/ranking institucional que alimenta SEMED/gestores.
- 🟠 **MÉDIO (corrigir na sequência):** demais analytics (#4,5,7,8,9), diary-dashboard (#10,11),
  boletim gerado pós-transferência (#14), Bolsa Família por escola (#20,21), AEE por escola (#22).
- 🟢 **BAIXO / NÃO impactado:** documentos imutáveis já emitidos (#15), monthly_reports por
  mantenedora (#16 — confirmar layout), MEC proxy/mapping (#17,18), conteúdos (#12).

---

## RECOMENDAÇÃO (conforme árvore de decisão aprovada)

Há impacto em relatórios históricos críticos ⇒ **NÃO seguir direto para a Fase 2.**
Inserir uma **Fase 1.5 — Resolução Temporal de Escola** antes do Rollback:

1. **Helper canônico** `resolve_school_at(class_id, date|academic_year)` usando `classes.school_history[]`
   (necessário e suficiente — registros já têm data/ano).
2. **Corrigir primeiro os 🔴 críticos**: Censo, Histórico Escolar PDF, Frequência, Rendimento, Ranking/SEMED.
3. **Depois os 🟠 médios.**
4. Só então implementar a **Fase 2 (Rollback)** — que, por usar o snapshot, é independente, mas o
   usuário priorizou a integridade dos relatórios primeiro.

### Pontos abertos a confirmar na implementação (não nesta auditoria)
- Localizar o ponto exato de geração do **Censo/INEP** (não há endpoint explícito em `mec_integration.py`;
  pode estar em serviço/export separado).
- Confirmar se o layout interno de `monthly_reports` detalha por escola (se sim, sobe para 🟠).
- Worker de render de Histórico/Boletim: validar se lê a escola por ano via enrollments (que foram
  re-homed) — provável 🔴 confirmado.
