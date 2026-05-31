# CHANGELOG — SIGESC

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
