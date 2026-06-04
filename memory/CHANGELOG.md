# CHANGELOG — SIGESC

## 2026-06 — Rodapé (gerado por + data/hora + paginação) nos 3 PDFs

- Frontend (`AnalyticsDashboard.jsx`): helper `drawPdfFooter(doc, generatedBy)`
  desenha em TODAS as páginas: "Gerado por {nome do usuário} em {data/hora}" à
  esquerda e "SIGESC · Página i de N" à direita, com faixa branca + linha separadora
  (legível mesmo sobre a imagem do dashboard). Nome vem de `user.full_name` (fallback
  e-mail), via `buildHeaderInfo().generatedBy`.
- Aplicado aos 3 PDFs: Dashboard completo, Ranking de Escolas (substituiu o rodapé
  antigo) e Análise Detalhada do Score.
- Lint JS limpo; `webpack compiled successfully`. ⚠️ Verificação visual pendente
  (preview em inatividade) → requer **redeploy do frontend**.


## 2026-06 — Cabeçalho institucional (brasão + município + escola) nos PDFs exportados

**Solicitação:** todos os PDFs do Dashboard Analítico devem trazer um cabeçalho
institucional com o brasão da mantenedora + nome do município; quando o relatório
for de uma escola específica, citar o nome da escola.

**Backend (`routers/mantenedora.py`):** novo `GET /api/mantenedora/brasao-base64`.
A URL do brasão fica em outro domínio SEM cabeçalho CORS (o `fetch` do browser
falharia), então o backend baixa a imagem (httpx), faz downscale com Pillow
(thumbnail 400px → de ~2,7MB para ~165KB) e devolve um data URL base64 mesma origem.

**Frontend (`AnalyticsDashboard.jsx`):**
- `useMantenedora()` + `useEffect` (na seção de hooks, antes de qualquer early-return)
  carrega o brasão em base64 e guarda em `logoDataUrl`.
- Helper `drawInstitutionalHeader(doc, {...})` desenha faixa com brasão + nome da
  mantenedora + "Município de X - UF" + título do documento; se `schoolName`, cita
  "Escola: ...". Retorna o Y onde o conteúdo começa.
- Aplicado aos 3 PDFs: **Dashboard completo** (cita escola se filtro de escola ativo),
  **Ranking de Escolas** (rede toda, sem escola) e **Análise Detalhada do Score**
  (sempre cita a escola). A planilha Excel do Dashboard também ganhou o contexto
  (mantenedora/município/escola) no topo do "Resumo".

**Validação:** endpoint testado via curl (retorna PNG base64 ~165KB). Lint JS/PY
limpo; `webpack compiled successfully`. Regras de Hooks respeitadas (sem React #310).
⚠️ Verificação visual do PDF NÃO feita: preview em modo inatividade. Requer
**redeploy do backend + frontend** (e acordar o preview p/ testar o download).


## 2026-06 — Fix: "Média por Componente Curricular" repetia componentes + escopo 3º–9º/EJA

**Sintoma:** o gráfico "Média por Componente Curricular" exibia o MESMO componente
várias vezes (ex.: Educação Física/Ensino Religioso repetidos).

**Causa raiz:** `GET /analytics/grades/by-subject` agrupava por `course_id`. Como
existem múltiplos documentos em `courses` com o mesmo nome (um por escola/série),
cada um virava uma barra → duplicação.

**Fix (backend `analytics.py::get_grades_by_subject`):**
- Passa a mesclar por NOME canônico do componente (normaliza acento/caixa) →
  cada componente aparece UMA única vez; a média é recomputada como soma÷contagem
  real entre todos os `course_id` daquele nome (não média de médias).
- Restringe às turmas elegíveis **3º ao 9º Ano e EJA** (exclui Ed. Infantil, 1º e
  2º Ano), mesma regra do `/students/performance`.
- Retorna ordenado por média **decrescente** (maior no topo). Removidos campos
  `course_id`/`abbreviation` do payload (frontend já gera a sigla a partir de
  `course_name`).

**Validação:** `tests/test_grades_by_subject_dedup.py` (3 testes — componente único,
média mesclada 7.0 ignorando 1º Ano, ordem desc com maior no topo) + regressão
`test_by_subject_usa_final_average` verde. Curl 2026: retorna cada componente 1×.
Requer **redeploy do backend**.


## 2026-06 — Dashboard Analítico: exportação PDF/Excel + fix do botão PDF (jspdf-autotable v5)

**1) Exportar Dashboard completo (cards + gráficos):**
- Frontend (`AnalyticsDashboard.jsx`): 2 botões no header — **Exportar PDF** e
  **Exportar Excel** (`data-testid` export-dashboard-pdf-btn / export-dashboard-excel-btn).
- PDF: captura a região de cards + gráficos via `html2canvas` (Tailwind v3, sem
  oklch) → `jsPDF` multipágina A4. Wrapper com `ref={dashboardCaptureRef}`.
- Excel: workbook com abas Resumo (KPIs), Frequência Mensal, Desempenho Bimestre,
  Média por Componente e Distribuição de Notas.
- Dependência declarada: `html2canvas@1.4.1` (`yarn add`).

**2) Ranking de Escolas (Score V2.1) — export em PDF além de Excel:**
- Novo `exportRankingToPDF()` (jsPDF paisagem + `autoTable`, 16 colunas, rodapé
  paginado). Botões "Excel" + "PDF" lado a lado (`export-ranking-pdf-btn`).

**3) Fix (bug) — botão PDF da "Análise Detalhada do Score V2.1" não funcionava:**
- **Causa raiz:** `jspdf-autotable@5` REMOVEU o método de protótipo
  `doc.autoTable(...)`; o código usava a API antiga → `doc.autoTable is not a
  function`. **Fix:** import funcional `import autoTable from 'jspdf-autotable'`
  e todas as chamadas migradas para `autoTable(doc, {...})`. `doc.lastAutoTable.finalY`
  mantido (válido na v5).

**Validação:** `webpack compiled successfully` + lint JS limpo. ⚠️ Verificação
visual de clique/download NÃO pôde ser feita: o proxy de **preview** estava em
modo de inatividade ("Preview Unavailable"). Testar após acordar o preview ou no
ambiente publicado. As mudanças exigem **redeploy do frontend**.


## 2026-06 — Dashboard Analítico: siglas de componentes, cores da distribuição e fix Frequência Mensal por escola

**1) Média por Componente Curricular — siglas oficiais + todos os componentes:**
- Frontend (`AnalyticsDashboard.jsx`): novo mapa `COMPONENT_ABBREVIATIONS` + helper
  `abbreviateComponent(course_name)` (normaliza acento/caixa). Siglas: L. PORT.,
  ARTE, ED. FÍS., L. ING., MAT., CIÊN., HIST., GEOG., ENS. REL., EST. AMAZ.,
  LIT. E RED., ED. AMB. CLI. (fallback p/ não mapeados).
- Removido o `slice(0,10)` → exibe TODOS os componentes; altura do gráfico dinâmica
  (`max(300, n×34)`); tooltip mostra o nome COMPLETO do componente.

**2) Distribuição de Notas — cores distintas por faixa:**
- Novo `DISTRIBUTION_COLORS` por `boundary`: 0-2.9 vermelho escuro, 3-4.9 laranja,
  5-5.9 amarelo, 6-6.9 verde-limão, 7-7.9 verde, 8-8.9 azul-claro, 9-10 índigo
  (antes 6+ eram todas verdes, indistinguíveis).

**3) Fix (bug) — Frequência Mensal "Sem dados" ao selecionar escola:**
- **Causa raiz:** `attendance` NÃO possui campo `school_id`; o endpoint
  `/analytics/attendance/monthly` filtrava `match_filter['school_id']=school_id`
  → resultado SEMPRE vazio quando uma escola era selecionada.
- **Fix (backend `analytics.py`):** resolve as turmas da escola e filtra por
  `class_id` (mesmo padrão do `/overview`). Pipeline migrado para o helper de
  split de `records[]` (combos `P|F`) e rate = P/total (J e F = ausência),
  alinhado ao restante do dashboard.
- **Validado via curl:** ano 2026 + `school_id` da Escola Multisseriada agora
  retorna Fev/Mar/Abr/Dez com taxas (antes vinha `[]`).

**Validação:** regressão `test_analytics_dashboard.py` + `test_teachers_performance_sla.py`
10/10 verde; lint JS/PY limpo.


## 2026-06 — Ajuste: coluna "Diários (60%)" = média ponderada de 3 SLAs (Desempenho dos Professores)

**Solicitação:** Na tabela "Desempenho dos Professores – Top 10" (Dashboard
Analítico), a coluna "Diários (60%)" deixa de ser só a cobertura de objetos de
conhecimento e passa a ser a MÉDIA PONDERADA de 3 SLAs (normalizada 0–100%):
- **SLA Frequência (peso 4):** lançamentos de frequência em até 3 dias / total
  (compara `attendance.created_at` vs `attendance.date`), nas turmas do professor.
- **SLA Conteúdo (peso 3):** objetos de conhecimento registrados / previstos
  (= lógica anterior da coluna).
- **SLA Notas (peso 3):** placeholder = 100% (workflow de prazo de notas ainda não existe).
- Fórmula: `Diários = (SLA_Freq×4 + SLA_Conteúdo×3 + SLA_Notas×3) / 10`.
- `score` final inalterado (60% Diários + 40% índice da média).

**Escopo isolado:** alteração EXCLUSIVA em `GET /api/analytics/teachers/performance`.
O "Ranking de Escolas – Score V2.1" NÃO foi tocado (confirmado pelo usuário).

**Entregue (backend `routers/analytics.py`, `get_teachers_performance`):**
- Pré-agregação de SLA Frequência por turma (pipeline `$dateFromString`/`$subtract`).
- Resposta agora expõe breakdown `sla_freq`, `sla_conteudo`, `sla_notas` além de
  `diario_pct`. Frontend já consome `diario_pct` (nome de campo inalterado → sem mudança de UI).

**Validação:** novo teste `tests/test_teachers_performance_sla.py` (4 testes, semeia
ano isolado 2099 → dias letivos fallback 200; valida SLA Freq 66.7, Conteúdo 10.0,
Notas 100, Diários 59.7). Regressão `test_analytics_dashboard.py` 6/6 verde
(Ranking V2.1 intacto).


## 2026-02 — UX: estado "Sem dados suficientes" no Dashboard Analítico

**Solicitação:** Exibir aviso de "Sem dados suficientes" nos cards/gráficos
quando não houver notas/frequência no período, em vez de mostrar 0 / gráfico em
branco (evita falsa impressão de bug quando um bimestre ainda não foi lançado).

**Entregue (frontend `AnalyticsDashboard.jsx`, somente UI):**
- Novo componente `EmptyChart` (ícone + mensagem + dica).
- Flags `hasGrades`, `hasAttendance`, `hasPeriodData`, `hasSubjectData`,
  `hasDistributionData`, `hasMonthlyData`.
- 5 cards (Frequência, Média Geral, Presença Média, Total de Faltas, Taxa de
  Aprovação) exibem "Sem dados suficientes" quando sem dados (data-testids
  freq-empty, media-geral-empty, presenca-empty, faltas-empty, aprovacao-empty).
- 4 gráficos (Frequência Mensal, Desempenho por Bimestre, Média por Componente,
  Distribuição de Notas) exibem `EmptyChart` no lugar do gráfico em branco.

**Validação:** Testing agent (iteration_92) — cenário 2026 (com dados): SEM
regressão; cenário 2025 (sem dados): estados vazios exibidos. Card "Média Geral"
(única peça faltante apontada) corrigido na sequência (mesmo padrão dos demais).


## 2026-02 — Correção crítica: Dashboard Analítico (10 itens) — schema real

**Problema:** Todos os cards/gráficos/rankings do Dashboard Analítico estavam
zerados/em branco e o ranking mostrava aprovação irreal (100%).

**Causa raiz:** `routers/analytics.py` agregava sobre um schema inexistente
(`grades.grade`, `attendance.status` no topo, `academic_year` como TEXTO). O
banco real usa: notas em **b1..b4 + final_average** (course_id, ano int) e
frequência em **records[]** com status **P/F/J** (combos `P|F`).

**Regras de negócio aplicadas (confirmadas pelo usuário):**
- Frequência = P / total de aulas (J e F = ausência; J exibida à parte).
- Total de Faltas = F + J (Justificadas detalhadas à parte).
- Média Geral / Média(60%) = `final_average` (já é a média dos bimestres lançados).
- Aprovação = por ALUNO: ≥ 5,0 em TODOS os componentes avaliados (base = alunos
  com nota lançada). Substitui a contagem por `status='aprovado'`.
- Desempenho por Bimestre = b1..b4 com notas não-lançadas contando como ZERO.

**Corrigidos 7 endpoints** (`analytics.py`): /overview, /grades/by-period,
/grades/by-subject, /distribution/grades, /schools/ranking, /students/performance,
/teachers/performance. Novo helper `_attendance_split_stages()` (unwind records[]
+ split de `|` + normaliza P/F/J).

**Validação:** Backend pytest 6/6 (`tests/test_analytics_dashboard.py`); frontend
E2E 100% (iteration_91) — cards >0, gráficos renderizando, ranking correto
(escolas sem notas = 0% aprovação, não 100%), Média(60%) preenchida.
OBS: tabela de Professores fica vazia no PREVIEW por não haver `teacher_assignments`
cadastrados (esperado); o cálculo de `media_notas` foi validado via alocação
temporária (retornou 10.0). Sem alterações de frontend.


## 2026-02 — Ajuste: cards de Completude contam apenas alunos ATIVOS

**Solicitação:** Nos cards de Completude (verde/amarelo/vermelho), as somas
devem considerar apenas alunos com status "Ativo".

**Entregue (backend `routers/students.py`, list_students):**
- `completeness_counts` agora é calculado sobre `active_filter`
  (`status='active'`), e não mais sobre todos os status.
- O filtro por faixa (`completeness_band`) na lista também passou a considerar
  apenas ativos, mantendo a consistência entre a contagem do card e a lista.
- Testes atualizados/adicionados em `tests/test_students_completeness.py`
  (soma == active_count; verificação com escola de status misto).

**Validação:** curl numa escola com 1 ativo + 1 transferido → soma das faixas = 1
(= active_count), total = 2. Pytest 6/6 OK. Sem alteração de frontend.


## 2026-02 — Feature: Somas por agrupamento nos "Indicadores da Rede" (Alunos)

**Solicitação:** Acrescentar somatórios na seção "Indicadores da Rede".

**Entregue (frontend `StudentsComplete.js`, somente exibição):**
- Helper `sumSeries(labels)` + consts de total (lê `series_counts`, chaves MAIÚSCULAS).
- Linha "Educação Infantil": 3 badges de soma destacados — `Educação Infantil`
  (Berçário/Maternal/Pré), `Anos Iniciais` (1º-5º Ano), `Anos Finais` (6º-9º Ano)
  (data-testids sum-educacao-infantil / sum-anos-iniciais / sum-anos-finais).
- Linha "Etapas (EJA) e Modalidades": badge `EJA` (soma 1ª-4ª Etapa) inserido
  ENTRE "4ª Etapa" e "Regular" (data-testid sum-eja).

**Validação:** Testing agent frontend 100% (5/5 — iteration_90). Somas conferem
com os badges individuais e backend series_counts.


## 2026-02 — Refactor (frontend): config central das categorias de conexão

**Motivo:** Centralizar rótulos/ícones/cores das categorias (antes fixos no
`OnlineUsers.js`), em par com o módulo central do backend.

**Entregue:**
- Novo `frontend/src/config/connectionCategories.js`: `CONNECTION_CATEGORIES`
  (array com key/label/icon/cores/testId). Editar rótulo, ícone ou cor de uma
  categoria agora é feito SOMENTE aqui. As `key` espelham `by_category` do backend.
- `OnlineUsers.js` consome o config (removida a array inline e os imports de
  ícones movidos para o config).

**Validação:** Lint OK; estrutura de renderização idêntica à validada na
iteration_89 (apenas a fonte da array mudou).


## 2026-02 — Refactor: mapeamento role→categoria de conexão centralizado

**Motivo:** Permitir adicionar novas roles (ex.: novas roles de Saúde) a uma
categoria sem editar a lógica do endpoint.

**Entregue:**
- Novo módulo `backend/utils/connection_categories.py`: `CONNECTION_CATEGORY_ROLES`
  (mapa categoria→roles), `categorize_role()` (case-insensitive, fallback
  "administrativas") e `empty_category_counts()`. Para incluir uma role basta
  editar o conjunto da categoria — único ponto de mudança.
- `routers/admin.py` (login-count) refatorado para usar o módulo. Resposta
  inalterada (`by_category`); soma continua == `successful`.
- Testes: `backend/tests/test_connection_categories.py` (4 testes).

**Validação:** Endpoint confere (soma == successful via curl); 8/8 pytest OK.


## 2026-02 — Feature: Subdivisão das "Conexões Registradas" por categoria (Usuários Online)

**Solicitação:** Manter o campo "Conexões Registradas" e adicionar 5 campos que
subdividem essas conexões por categoria de perfil.

**Categorias:** Professores (role professor), Alunos (aluno), Assistência Social
(ass_social/ass_social_2), Saúde (agente_vacinas + futuras roles de saúde),
Administrativas (todos os demais: admin, semed, secretario, etc.).

**Entregue:**
- Backend (`routers/admin.py`, GET /admin/online-users/login-count): resposta
  agora inclui `by_category` agrupando os logins bem-sucedidos por `user_role`
  via aggregation. A soma das 5 categorias == `successful`.
- Frontend (`OnlineUsers.js`): card "Conexões Registradas" mantido + nova seção
  "Conexões por categoria" (data-testid connections-by-category) com 5 cards
  (conn-cat-professores/alunos/assistencia/saude/administrativas).
- Testes: `backend/tests/test_online_users_login_count.py` (4 testes).

**Validação:** Testing agent E2E 100% (backend 4/4 + frontend — iteration_89).
Card antigo intacto; soma das categorias confere com o total.


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
