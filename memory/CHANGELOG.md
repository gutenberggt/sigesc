# CHANGELOG — SIGESC

## 2026-02 — Feature: Filtros por faixa de Completude na lista de Alunos

**Solicitação:** Na página Alunos(as), na linha do "Total: N registros / Gerar
PDF / Ações em Lote", adicionar 4 botões (Verde, Amarelo, Vermelho, Branco/Todos)
espelhando a coluna "Completude". Cada botão mostra a quantidade de alunos na
faixa e, ao clicar, filtra a lista; o branco ("Todos") limpa o filtro.

**Faixas:** Verde ≥80%, Amarelo 50-79%, Vermelho <50% (espelham completenessColor).

**Entregue:**
- Backend (`routers/students.py`, list_students): novo param `completeness_band`
  (green|yellow|red) que filtra a lista server-side; resposta agora inclui
  `completeness_counts` {green,yellow,red} calculado por aggregation sobre TODO
  o conjunto filtrado (não só a página). Helpers `_completeness_pct_stage()` e
  `_BAND_EXPR` espelham os 14 critérios de `_compute_student_completeness`.
- Frontend (`StudentsComplete.js`): estados `completenessCounts`/`completenessBand`,
  4 botões na linha do Total (data-testid completeness-filter-green/yellow/red/all),
  toggle ao reclicar a faixa ativa, reset de página ao trocar filtro.
- Testes: `backend/tests/test_students_completeness.py` (5 testes).

**Validação:** Testing agent E2E 100% (backend 5/5 + frontend — iteration_88).
Contagens batem com o total; filtros e toggle funcionam.


## 2026-02 — Feature: Painel in-app de Auditoria de Matrículas (read-only)

**Solicitação:** Transformar a fase de auditoria do script de saneamento num
painel in-app na secretaria, para acompanhar matrículas ausentes/duplicadas em
tempo real sem usar o shell.

**Entregue:**
- Backend: `GET /api/students/enrollment-audit` (em `routers/students.py`) —
  read-only, tenant/escola-aware. Retorna, por coleção (`students` e
  `enrollments`): total, vazios, grupos duplicados (+ owners) e amostra de
  alunos sem matrícula (limite 200); além de `owner_names` e o status do índice
  único `uq_enrollment_number`. Restrito a super_admin/admin/gerente/semed/secretario.
- Frontend: `pages/EnrollmentAudit.jsx` — rota `/admin/auditoria-matriculas`,
  card "Auditoria de Matrículas" no Dashboard (grupo "Gestão Escolar"). Mostra
  4 cards de estatística, banner do índice único (ATIVO/inativo) e tabelas de
  duplicatas + alunos sem matrícula. Botão "Atualizar" para refresh.
- Testes: `backend/tests/test_enrollment_audit.py` (10 testes, autossuficiente).

**Validação:** Testing agent E2E 100% (backend + frontend, iteration_87). Pytest
local 10/10 OK.


## 2026-02 — P1: Backfill + Deduplicação de Matrículas + Índice Único

**Solicitação:** Sanar passivo de matrículas AUSENTES (vazias) e DUPLICADAS.
Regra do usuário p/ duplicatas: manter a matrícula do aluno/registro MAIS ANTIGO
e gerar nova matrícula para os demais.

**Entregue:**
- `backend/scripts/backfill_dedup_enrollment.py` (novo): script standalone com
  3 fases (Dedup → Backfill → Índice único parcial). DRY-RUN por padrão; exige
  `--apply` para alterar e `--apply --create-index` para criar o índice.
  - Dedup mantém o doc mais antigo (menor `created_at`/`enrollment_date`) e
    regenera os demais via gerador atômico (`utils/enrollment.py`).
  - Backfill preenche vazios em `students` e `enrollments`.
  - Índice ÚNICO PARCIAL `uq_enrollment_number` (`partialFilterExpression:
    {enrollment_number: {$gt: ""}}`) — barra duplicatas mas permite vazios.
  - Contador atômico é "sememeado" via `$max` acima do maior sufixo do ano,
    evitando colisão com legado.
- `backend/tests/test_backfill_dedup_enrollment.py` (novo): regressão da lógica
  de ordenação (mais antigo) e geração única (3 testes, OK).

**Validação (banco de preview):** aplicado com sucesso → 0 vazios, 0 duplicatas
em ambas as coleções; índice bloqueia inserção duplicada e permite múltiplos
vazios. Backend saudável (200).

**Como rodar em PRODUÇÃO (após deploy):**
```
cd /app/backend
python3 scripts/backfill_dedup_enrollment.py                 # 1) dry-run (revisar plano)
python3 scripts/backfill_dedup_enrollment.py --apply --create-index   # 2) aplicar
```


## 2026-05-31 — Feature: Indicador de Completude do Cadastro

**Solicitação:** Indicador de "completude do cadastro" do aluno. Escolhas do usuário:
exibir em AMBOS (badge na lista + barra no formulário); conjunto AMPLIADO de campos;
estilo percentual com cor.

**Critérios (14, espelhados frontend/backend):** os 10 obrigatórios + Documento
(CPF/NIS/Certidão) + Telefone do Responsável + Turma + Matrícula. (Não há campos de
endereço no formulário, então não entraram no cálculo.)

**Implementação:**
- `frontend/src/utils/registrationCompleteness.js` (novo): `computeCompleteness(data)`
  → {percent, filled, total, missing}, `completenessColor(percent)` (verde ≥80,
  amarelo 50–79, vermelho <50), e `COMPLETENESS_CRITERIA`.
- `backend/routers/students.py`: `_compute_student_completeness(student)` (espelha o
  frontend); a listagem `GET /api/students` adiciona `completeness` (0–100) em cada
  item, projetando os campos extras só para o cálculo e removendo-os depois (payload leve).
- `frontend/src/pages/StudentsComplete.js`:
  - Coluna "Completude" na tabela inline (badge com mini-barra + % colorido,
    data-testid `completeness-badge-<id>`). Atualizados thead, tbody, skeleton e colSpan.
  - Barra de progresso no topo do formulário (data-testid `form-completeness-bar` /
    `form-completeness-percent`), com `useMemo`, contagem n/14, lista "Faltando: ..." e cor.
  - `components/Tabs.js` já controlável (da feature anterior).

**Testado:** testing_agent iteration_86 (barra do form 100% OK). Coluna da lista
corrigida (era código morto no array `columns`; migrada para o markup inline da tabela)
e validada visualmente: 20 badges, cores corretas (43% vermelho, 50% amarelo), %
batendo com o backend.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy de **frontend E backend** (esta feature mexe
nos dois) no Coolify.

---

## 2026-05-31 — Feature: campos obrigatórios no cadastro de aluno + pop-up de alerta

**Solicitação:** Tornar campos obrigatórios no cadastro do aluno; se algum estiver
ausente ao salvar, abrir um pop-up de alerta (caixa centralizada com mensagem e
botão OK) e navegar até a aba do primeiro campo faltante.

**Campos obrigatórios:**
- Aba Identificação: Nome Completo, Data de Nascimento, Sexo, Nacionalidade,
  Cor/Raça, Comunidade Tradicional, Naturalidade (Cidade), Estado.
- Aba Responsáveis: Mãe (mother_name) e Responsável Legal (legal_guardian_type;
  se "Outro", o nome do responsável também é exigido).

**Implementação (frontend):**
- `getMissingRequiredFields()` + validação no `handleSubmit` que abre o pop-up
  (`setRequiredAlert`) e troca para a aba do 1º campo faltante (`setFormTabIndex`).
- Pop-up centralizado novo (data-testid `required-fields-modal`, itens
  `required-field-item-N`, botão `required-fields-modal-ok-btn`).
- `components/Tabs.js` tornado CONTROLÁVEL (props opcionais `activeIndex` +
  `onTabChange`, retrocompatível) para permitir a navegação programática de aba.
- Labels obrigatórios marcados com `*`. Adicionados data-testid `create-student-btn`
  e `save-student-btn`.
- **Fix importante:** o `<form>` recebeu `noValidate` — o input `full_name` tinha
  `required` HTML5 que disparava o tooltip nativo do browser e bloqueava o
  `handleSubmit`, impedindo o pop-up. Com `noValidate`, a validação customizada é a
  única fonte.

**Testado:** testing_agent iteration_85 — 100% (5/5 cenários). Pop-up dispara,
OK fecha, navegação de aba funciona, asteriscos presentes.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy do **frontend** (Save to GitHub → Coolify
Redeploy do serviço frontend) para publicar esta feature.

---

## 2026-05-31 — Fix definitivo: "Série não reconhecida" nos Indicadores da Rede (P0)

**Sintoma (produção):** Escola Nivalda mostrava 314 alunos ativos, mas as séries
somavam só 47 (Berçário II 12, Maternal I 7, Maternal II 28) — 267 alunos "sumiam".
O backend os jogava em "SÉRIE NÃO RECONHECIDA: 267".

**Root cause:** No pipeline de agregação `series_pipeline` (routers/students.py),
o cálculo de `_grade_effective` usava:
`$cond[$and[$ne(ss, null), $ne(ss, "")] ? ss : class.grade_level]`.
Quando o campo `student_series` estava **AUSENTE** (não apenas null/""), a variável
`$$ss` virava "missing" e `$ne(missing, null)` resolve para **TRUE** no MongoDB →
o `$cond` mantinha o valor missing em vez de cair no fallback `classes.grade_level`
→ canonicalizava para None → "Série não reconhecida". (Os scripts de diagnóstico em
Python usavam `.get()/.strip()`, por isso reconheciam corretamente os 314.)

Dados de Nivalda confirmados: 267 com `student_series` ausente/null, cujas turmas
TÊM `grade_level` válido (Maternal II 129, Maternal I 98, Berçário II 40).

**Fix:** `vars.ss = $trim($ifNull($student_series, ""))`. O `$ifNull` coage
null E campo ausente para "", e `$trim` normaliza só-espaços. Assim cai no fallback
do `grade_level` corretamente. Mantém a prioridade do `student_series` quando
preenchido (multisseriadas).

Validado nos dados reais de produção (via pipeline standalone): Nivalda passa a
somar 314 (Berçário II 52, Maternal I 105, Maternal II 157), 0 não reconhecidas.

**Arquivos:**
- `routers/students.py` (~linha 609-628): pipeline `_grade_effective` corrigido.
- `tests/test_series_pipeline_fallback.py`: 4 testes de regressão (missing/null/
  vazio/espaços caem no fallback; student_series válido tem prioridade;
  reconciliação soma 100%). Todos passando.

**Scripts de diagnóstico criados em** `backend/scripts/` (standalone, sem deps do
projeto, rodam em qualquer container via base64):
- `diagnose_snr_standalone.py` — classifica causa-raiz por aluno (A/B/C/D/E).
- `series_breakdown_standalone.py` — detalhamento de séries (código novo) p/ comparar com a tela.
- `fix_grade_level_standalone.py` — preenche `classes.grade_level` vazio a partir do nome da turma (DRY-RUN por padrão).

**Diagnóstico de ambiente (produção = Coolify):** backend `uvicorn server:app`,
frontend nginx (PWA com service worker network-first), traefik. Código implantado
(students.py + serie_canonical.py) estava CORRETO/idêntico (md5 batendo) — o bug era
de LÓGICA no pipeline, não de deploy desatualizado.

**AÇÃO PENDENTE DO USUÁRIO:** redeploy do **backend** em produção (Save to GitHub →
Coolify Redeploy do serviço backend) para subir o fix. Frontend NÃO precisa redeploy.
Após o deploy, validar Nivalda = 314 no painel "Indicadores da Rede".
