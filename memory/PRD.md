# SIGESC - Product Requirements Document

## ⛔ MÓDULOS BLOQUEADOS (NÃO ALTERAR SEM PERMISSÃO EXPLÍCITA DO USUÁRIO)

> **AVISO PARA AGENTES E DESENVOLVEDORES**: Os módulos abaixo foram travados pelo
> usuário (proprietário do produto). Qualquer alteração — visual, funcional,
> refatoração, "melhoria" estética, mudança de campos, props, modelos Pydantic,
> rotas, validações, fluxos de salvamento, modais, etc. — **EXIGE autorização
> explícita do usuário ANTES de qualquer edição**. Não pergunte "posso refatorar?"
> de forma genérica; descreva o que pretende mudar e aguarde o "sim" literal.
>
> | Módulo | Caminhos protegidos |
> |---|---|
> | **Diário AEE** | `/app/frontend/src/pages/DiarioAEE.js`, `/app/frontend/src/components/PlanoAEEModal.js`, `/app/frontend/src/pages/tutorials/TutorialDiarioAEE.jsx`, `/app/backend/routers/aee.py`, models `PlanoAEE*` em `/app/backend/models.py` (linhas ~1184-1305), tests em `/app/backend/tests/test_aee*.py` |
>
> Se um bug surgir nesses arquivos, o ÚNICO procedimento permitido é:
> 1. Reproduzir, identificar a causa raiz e descrever o fix proposto (sem aplicar).
> 2. Pedir confirmação ao usuário antes de tocar no código.
> 3. Após o "sim" do usuário, fazer somente o fix mínimo necessário — nada além.

## Original Problem Statement
Sistema Integrado de Gestão Escolar multi-tenant (SaaS) para prefeituras, com isolamento de dados entre mantenedoras, gestão de escolas, turmas, alunos, servidores e folha de pagamento.

## User's preferred language: Portuguese

## Multi-Tenancy Architecture
- Collection `mantenedoras` (plural) é a fonte definitiva de dados de tenants
- Collection legacy `mantenedora` (singular) foi removida
- Row-Level Security via `tenant_scope.py` (`apply_tenant_filter`)
- Super_admin tem acesso cross-tenant e ignora RLS quando sem header `X-Mantenedora-Id`
- Frontend: `TenantSwitcher` + `TenantSyncBoundary` permitem troca fluída sem reload

## Implemented Features (histórico)

### Carga Horária Derivada — Fonte Única de Verdade **[05/Fev/2026]**
- **Refatoração arquitetural**: CH do servidor deixa de ser informada manualmente e passa a
  ser **derivada** de `Σ alocações + Σ substituições vigentes`. Fallback de 40h dividido pelas
  lotações ativas quando não há nenhum registro.
- **Calculator central** (`/app/backend/utils/carga_horaria_calculator.py`):
  - `calcular_carga_horaria_servidor(db, staff_id, *, modo)` — total geral.
  - `calcular_carga_por_lotacao(db, staff_id, school_id, *, modo)` — por escola.
  - `calcular_carga_horaria_servidor_breakdown(...)` — detalhamento para UI.
  - Modo contextual: `'atual'` (substituições vigentes hoje) e `'periodo'` (intervalo/ano letivo).
- **Endpoints atualizados**:
  - `GET /api/staff` enriquece cada item com `carga_horaria_calculada`.
  - `GET /api/staff/{id}` retorna `carga_horaria_calculada` no servidor + `carga_horaria_calculada` em cada lotação ativa.
  - `GET /api/staff/{id}/carga-horaria` (novo) retorna breakdown completo (por escola, fallback, qtd alocações).
- **Folha de pagamento** (`hr.py`): geração de pré-folha agora usa `calcular_carga_por_lotacao(modo='atual')`
  como fonte única (substitui `school_assignments.carga_horaria` manual + fallback legado).
- **Frontend** (3 telas):
  - `StaffModal`: campo "Carga Horária Total Calculada" (readonly, vindo de `carga_horaria_calculada`)
    substitui o texto antigo "definida em Gerenciar Lotações".
  - `LotacaoModal`: campo "CH Semanal" agora é readonly (`auto`) com tooltip explicativo;
    cards de lotações existentes exibem `Xh/sem (calc.)`.
  - `AlocacaoModal`: removido alerta bloqueante "Não é possível salvar"; resumo simplificado
    (Já Alocada + Nova Alocação + Total após salvar) com mensagem informativa "Sem limites manuais".
- **Auditoria + Testes**:
  - Script `/app/backend/scripts/audit_carga_horaria.py` compara manual vs calculado em todos os
    servidores ativos. Gera relatório JSON. Validado em preview: 0 divergências.
  - Suite pytest `/app/backend/tests/test_carga_horaria_calculator.py` com 11 casos cobrindo
    fallback 40h, divisão entre lotações, ignore_workload, substituições vigentes/expiradas.


### Substituição Multi-Turma/Multi-Componente **[05/Fev/2026]**
- Refatorado `SubstituicaoSection.js` para paridade completa com `AlocacaoModal` de "Nova Alocação":
  suporte a **N turmas × M componentes** (cartesian product) em uma única operação.
- UX: botões `+`/`−` com chips 🎓 (amarelo) para turmas e 📖 (roxo) para componentes; opção
  "TODOS (N componentes)" para adicionar em lote; preview da lista de combinações com regente
  detectado e CH por linha.
- Filtros defensivos: Escola usa `professorSchools` (apenas lotações ativas); componentes
  filtrados por nível de ensino comum das turmas; dedupe de componentes já alocados ao substituto
  em qualquer turma selecionada; reset automático ao mudar nível de ensino.
- CH semanal auto-detectada por combinação via regente existente; campo override manual
  (`auto (regente)`) aplica-se a todas as combinações.
- Save loop: `POST /teacher-assignments/substitutions` uma vez por combinação, com contagem
  de sucesso/falha (`4 cadastrada(s), 0 falharam`).
- Todos os `data-testid` adicionados: `subst-add-turma-btn`, `subst-add-comp-btn`,
  `subst-turma-chip-{id}`, `subst-comp-chip-{id}`, `subst-preview-list`.


### Busca Sugestiva + Accent-Insensitive em Toda a UI **[04/Mai/2026]**
- Novo helper `frontend/src/utils/textSearch.js` com `normalizeForSearch()` (NFD + lowercase + remove cedilha) e `highlightSegments()` (realça trecho casado).
- **Declarações Escolares** (`/admin/declaracoes`): substituiu lista pré-carregada com filtro local por **autocomplete sugestivo via backend** a partir do **3º caractere**, debounced 250ms, accent + case insensitive (usa `nome_busca`). Highlight do trecho casado, navegação por teclado (↑ ↓ Enter Esc), botão limpar (X), spinner durante busca, mensagem "Continue digitando" quando < 3 chars.
- **Filtros locais aplicados ao normalizeForSearch** (paralelo): `Events.js`, `Staff.js` (lotacoes/alocacoes), `Announcements.js`, `MessageLogs.js`, `VaccineDashboard.js`, `AssocialDashboard.js`, `PreMatriculaManagement.jsx`. Agora `joao` acha `João`, `concei` acha `Conceição`.
- Validado E2E: `joa` → `JOAO SANTOS` com highlight ✅, `concei` → 1 sugestão ✅, hint < 3 chars visível ✅.


**Sintoma**: PDFs de Matrícula/Frequência/Escolaridade já tinham código + QR, mas Histórico Escolar e Certificado de Conclusão eram emitidos SEM código nem QR — não podiam ser validados pelo portal público.

**Origem**: as rotas `GET /api/documents/historico-escolar/{id}` e `GET /api/documents/certificado/{id}` chamavam diretamente `generate_*_pdf` sem criar `snapshot` antes. Os geradores em `pdf/historico_escolar.py` e `pdf/certificado.py` também não tinham slot para receber `verification_code`.

**Fix**:
- Novo helper `pdf/verification_footer.py` com `build_verification_flowables()` (Platypus) e `draw_verification_footer_on_canvas()` (canvas direto). Usa `segno` (já no requirements) e produz a mesma caixa visual usada nas declarações: código + QR + URL portal + validade.
- `pdf/historico_escolar.py`: aceita kwargs `verification_code` e `valid_until`; injeta o rodapé de verificação no final do story.
- `pdf/certificado.py`: aceita kwargs `verification_code` e `valid_until`; desenha o rodapé via canvas no rodapé inferior (paisagem A4). Também tornou os `.upper()` resilientes a `None` (era falha "'NoneType' object has no attribute 'upper'" em alunos sem todos os campos).
- `routers/documents.py`: ambas as rotas agora chamam `snapshot_service.create_snapshot()` ANTES de gerar o PDF, com `analysis_type="historico"` ou `"certificado"`, validade default 10 anos. O `verification_code` retornado é injetado no PDF e persistido no `verifiable_documents` com `expires_at` correto.

**Validação E2E**:
- `GET /api/documents/historico-escolar/{id}` → PDF 13 KB com `SIGESC-9PWX-6KZ3` extraível via pypdf ✅
- `GET /api/documents/certificado/{id}?academic_year=2025` → PDF 127 KB com `SIGESC-XEPG-3AW3` extraível ✅
- `GET /api/public/verify/SIGESC-XEPG-3AW3` → `status=valido tipo=certificado emitido_em=2026-05-05` ✅
- Catálogo da página `/admin/document-validator` agora reflete corretamente todos os 9 tipos sendo emitidos com código + QR.


- Nova rota autenticada: `/admin/document-validator` (`pages/DocumentValidator.jsx`)
- Botão no Menu de Administração → Gestão Institucional → "Validar Documentos" (visível para super_admin, admin, secretario, diretor, coordenador, auxiliar_secretaria)
- **Catálogo dos 9 tipos de documentos verificáveis** do SIGESC (mantido em sync com `backend/services/verifiable_docs_service.DOC_TYPES`):
  1. Plano de Ação Automático (`plano_acao`) → /admin/plano-acao
  2. Relatório Executivo Mensal (`relatorio_mensal`) → /admin/relatorios-mensais
  3. Declaração de Matrícula (`matricula`) → /admin/students
  4. Declaração de Frequência (`frequencia`) → /admin/students
  5. Declaração de Escolaridade (`escolaridade`) → /admin/students
  6. Histórico Escolar (`historico`) → /admin/promotion
  7. Certificado de Conclusão (`certificado`) → /admin/promotion
  8. Ata / Documento Administrativo (`ata`)
  9. Documento Institucional genérico (`generico`)
- Cada card mostra ícone, descrição, módulo emissor e link "Ir →"
- **Validador embutido**: campo `SIGESC-XXXX-XXXX` que consulta `/api/public/verify/{code}` e exibe status (válido/inválido/revogado) com metadados LGPD-safe (tipo, emitido em, emitido por, escopo, hash truncado)
- **Atalho para o portal público externo** (URL copiável + abrir em nova aba) para compartilhar com vereadores/conselheiros/cidadãos
- Seção "Como funciona" explicando snapshot imutável + SHA-256 + HMAC + QR + revogação


- Helpers em `backend/text_utils.py`: `strip_accents`, `normalize_for_search` (lowercase + sem acentos), `normalize_for_sort` (lowercase preservando acentos), `compute_name_indexes(doc, primary_field)`.
- **Routers atualizados** (`students`, `staff`):
  - **Create/Update** preenchem automaticamente `nome_normalizado` e `nome_busca` a partir de `full_name` (students) / `nome` (staff).
  - **GET com `?search=`** usa `$or`: caminho rápido via `nome_busca` indexado + fallback regex `accent_insensitive_regex` no campo original (cobre registros não migrados).
- **Endpoint `/api/staff` ganhou param `search`** (não existia antes).
- **Validado**: criar `Maria José da Conceição` → `nome_busca = "maria jose da conceicao"` → busca por `maria`, `JOSÉ`, `conceicao` retorna o mesmo registro. Idem para students.

### Bug Fix Crítico — Remoção do CAPS Automático **[04/Mai/2026]**
**Sintoma**: nomes próprios e textos longos foram salvos em CAIXA ALTA + sem acentuação correta no banco, corrompendo dados pedagógicos (planos, observações, conteúdos).

**Origens removidas (3 fontes simultâneas)**:
1. **CSS global** em `frontend/src/index.css` — `text-transform: uppercase` em todo `<input>` e `<textarea>` REMOVIDO. Mantida apenas a classe utilitária opt-in `.input-uppercase` para casos legítimos (códigos BNCC, UF).
2. **`SpellCheckTextarea.jsx`** — `textTransform: uppercase` default REMOVIDO. Agora aceita `data-uppercase` como opt-in (era `data-no-uppercase` como opt-out).
3. **Backend** `format_data_uppercase()` removido de **TODOS** os routers de escrita: `students, staff, schools, classes, courses, learning_objects, users, guardians, auth` E `aee` (autorizado pelo proprietário). Imports remanescentes do `text_utils.py` foram limpos. Função fica disponível em `text_utils.py` mas sem callers — **não usar em código novo**.

**Política nova (arquitetura limpa)**:
- **Banco** armazena dado conforme digitado pelo usuário (capitalização correta, com acentos).
- **PDFs** continuam aplicando `.toUpperCase()` apenas na **renderização** (norma documental institucional brasileira).
- **Comparações case-insensitive** preservadas (legítimas, não persistem).

**Migração reversa de dados existentes**:
- Script `/app/backend/scripts/normalize_names_back.py` com:
  - Backup automático (`backup_<col>_<timestamp>` via `$out`) antes de cada execução com `--apply`
  - Função `title_case_name()` com regras BR: preposições minúsculas (`da, de, do, das, dos, e, em`), siglas conhecidas em UPPER (`AEE, BNCC, EJA, SEMED, ETI, …`), algarismos romanos (`I, II, III…`), hífens, apóstrofos
  - Adiciona `nome_normalizado` (lowercase preservando acentos) + `nome_busca` (lowercase + sem acentos NFD) + `nome_migrado: true` + timestamp
  - Cria índice composto `{mantenedora_id: 1, nome_busca: 1}` para busca eficiente e tenant-safe
  - `bulkWrite` em batches de 1000 (performance)
  - **Default `--dry-run`**, escreve só com `--apply`
  - Coleções: `students, staff, schools, classes, courses, users, mantenedoras` (apenas campos NOMINAIS — não toca em descrições, observações, planos AEE)
  - **AEE NÃO é migrado em massa** — dados antigos do AEE permanecem como estão (acordo arquitetural)

**Comando para o proprietário aplicar em produção**:
```bash
# 1. Sempre: dry-run primeiro
python /app/backend/scripts/normalize_names_back.py --dry-run

# 2. Após revisar o relatório, aplicar:
python /app/backend/scripts/normalize_names_back.py --apply

# 3. Restringir a uma coleção (se preciso):
python /app/backend/scripts/normalize_names_back.py --apply --collection students
```

**Validação**:
- Backend curl: POST `/api/classes` com `"Turma Teste de CapitalizaçÃO"` persiste exatamente como enviado ✅
- Frontend smoke: `getComputedStyle(input).textTransform = 'none'`, input aceita "Teste minúsculo Acentuação" e exibe como digitado ✅
- Dry-run no preview: 58 docs marcados para atualizar (students, schools, classes, courses, users, mantenedoras), 3 sem mudança — siglas (AEE, SEMED), preposições (da/de) e romanos (I, II) preservados corretamente ✅

**Migração aplicada no ambiente preview [05/Mai/2026]** — em 3 fases supervisionadas:
- Fase 1 (`courses` + `users`): 36 docs migrados, backups `backup_*_20260505T105357Z`
- Fase 2 (`students` + `staff`): 10 docs migrados, backups `backup_*_20260505T105647Z`
- Fase 3 (`schools` + `classes` + `mantenedoras`): 14 docs migrados, backups `backup_*_20260505T105804Z`
- **Total**: 60 docs migrados em 7 coleções; dry-run final confirma 0 pendentes
- Validação end-to-end: login + busca `search=maria` retornou `Maria Silva` (busca accent-insensitive funcionando) ✅
- **Próximo passo pendente**: rodar o mesmo script em produção (Coolify) quando o proprietário decidir

**Ferramentas operacionais** [05/Mai/2026]:
- `/app/Makefile` — atalhos: `make migrate-dry-run | migrate-names | migrate-names-yes | migrate-status | migrate-rollback TS=<timestamp>`
- `/app/backend/scripts/run_migration.sh` — runner shell com dual-gate (dry-run obrigatório antes de --apply), prompts Y/n por fase, healthcheck pós-migração, logging em `/var/log/sigesc/migracao_nomes_<TS>.log` e rollback global por timestamp
- Em produção (Coolify): após "Save to Github" + deploy, basta entrar no terminal do container backend e rodar `make migrate-names` (ou `make migrate-names-yes` para CI)

### Normalização de Conteúdo Textual — Fila de Revisão [05/Mai/2026]
**Princípio**: nome ≠ texto. Conteúdo (observações, descrições, pareceres) usa
SENTENCE CASE (não Title Case) e exige revisão humana antes de gravar — o
script gera sugestões e enfileira; admin aprova caso a caso.

**Fluxo**:
1. `make content-dry-run` → relatório read-only
2. `make content-scan` → enfileira sugestões em `content_review_queue` (NÃO grava)
3. Admin revisa em `/admin/content-review` (Aprovar / Rejeitar / Editar / Lote)

**Whitelist atual** (campo a campo):
- `students.observations`
- `student_history.observations`
- `enrollments.observations`
- `staff.observacoes`
- `learning_objects.content` (Conteúdo/Objeto de Conhecimento)
- `learning_objects.pratica_pedagogica` (Práticas Pedagógicas)
- `learning_objects.observations`
- (futuros: `classes.descricao/observacoes` quando schema for ampliado)
- (FASE 2 futuro com filtro restritivo): `learning_objects.methodology`, `learning_objects.evidencia_aprendizagem`
- ❌ NÃO incluído: `learning_objects.resources` (lista de materiais — risco semântico)

**Heurísticas defensivas** (FUNÇÃO `should_skip_text`) — Mai/2026 (refinadas v2):
- 🚫 Algarismos romanos I/II/III/IV/V/VI/.../XX (cobre "MATERNAL I", "PRÉ I", "AULA V")
- 🚫 Lista por vírgula em CAPS — bloqueia APENAS se média de palavras por segmento ≤ 1.5 (lista de materiais como "CADERNO, LÁPIS, BORRACHA")
- ✅ Frases pedagógicas com vírgulas estruturais convertem normalmente ("INTERPRETAÇÃO DE TEXTO, LEITURA E ESCRITA, PRODUÇÃO DE TEXTO" → "Interpretação de texto, leitura e escrita, produção de texto")
- 🚫 Estrutura pedagógica enumerada: ATIVIDADE/AULA/ETAPA/OBJETIVO/UNIDADE/MÓDULO/CAPÍTULO/SEÇÃO + número
- ✅ Casos validados: 11/11 testes passam (CADERNO/LÁPIS bloqueia ✅, INTERPRETAÇÃO DE TEXTO converte ✅)

### Blindagem na entrada (POST/PUT) — Mai/2026
**Princípio**: prevenir ruído contínuo na fila. Antes de gravar, se um campo
whitelistado vier em CAPS narrativo → converter para sentence case usando as
mesmas regras (mesma whitelist + mesmas heurísticas defensivas).

**Util**: `/app/backend/utils/text_normalize.py`
- `normalize_input_text(value)` — single field
- `normalize_input_fields(payload, collection)` — payload completo

**Routers instrumentados** (POST + PUT):
- `students.py` — campo `observations`
- `staff.py` — campo `observacoes`
- `enrollments.py` — campo `observations`
- `student_history.py` — campo `observations`
- `learning_objects.py` — campos `content`, `pratica_pedagogica`, `observations`

**Validação E2E**:
- PUT `/api/students/{id}` enviando `"ALUNO APRESENTA BOM DESEMPENHO EM 14:30. NECESSITA DE ATENDIMENTO AEE."` → gravado como `"Aluno apresenta bom desempenho em 14:30. Necessita de atendimento AEE."` ✅
- Texto com heurística (lista, romano, estrutura) preserva original ✅
- Coleções fora da whitelist intactas ✅

### Botão "Ver contexto" — Mai/2026
- Endpoint: `GET /api/admin/content-review/{id}/context`
- Frontend: modal que mostra todos os campos textuais do registro original, destacando o campo da sugestão pendente em amarelo
- Validação: modal abre, mostra 3 campos textuais (content, pratica_pedagogica, observations), campo destacado tem pin "📍 campo da sugestão" + sugestão embebida ✅

### Higienização Textual — Fase 1 (FORMATAÇÃO determinística) [05/Mai/2026]
**Princípio**: módulo SEPARADO de `content_review` ("nome ≠ caixa ≠ formatação"). Apenas regras
determinísticas, ZERO ortografia, ZERO IA, sempre via fila com revisão humana.

**Regras (Fase 1)**:
1. Espaços múltiplos → 1
2. Espaço antes de pontuação → remove
3. Falta espaço após pontuação (antes de letra) → adiciona (preserva 1.500/14:30)
4. Múltiplas quebras de linha (3+) → 2
5. Capitalização inicial
6. Pontuação final em frases ≥3 palavras
7. Padronização de siglas (aee → AEE etc)
8. Palavras stopword duplicadas (de de → de)

**Pulagem defensiva**: texto vazio/curto, em CAIXA ALTA (vai pro content_review), com romanos
ou estrutura enumerada (preserva).

**Arquivos**:
- Script: `/app/backend/scripts/text_improvement.py` (--dry-run, --scan, --clear-pending)
- Router: `/app/backend/routers/text_improvement.py` (super_admin/admin/admin_teste)
- Página: `/app/frontend/src/pages/TextImprovement.jsx` (rota `/admin/text-improvement`)
- Coleção MongoDB: `text_improvement_queue` (status + applied_rules)
- Make: `make text-dry-run | text-scan | text-clear-pending`
- Dashboard: novo atalho "Higienização Textual" (violeta) no grupo Administração

**Validação E2E [05/Mai/2026]**:
### Higienização Textual — Fase 2 (ORTOGRAFIA via pyspellchecker) [05/Mai/2026]
**Princípio**: ortografia 100% determinística (lib `pyspellchecker` + dict PT-BR de 414k palavras),
ZERO IA, sempre via fila com confidence ≥0.75. Mesma fila/UI da Fase 1, distinguidas pelo campo `tipo`.

**Pipeline ampliado**: cada doc/campo pode gerar 0..2 sugestões (uma de formatação + uma de ortografia).

**Detector** (`scripts/text_improvement.py::detect_spelling_issues`):
- Tokeniza palavras alfabéticas
- Pula: <4 chars, siglas (PRESERVED_ACRONYMS), tokens UPPER, nomes próprios (capitalizada no meio da frase), palavras com dígito, palavras já no dicionário
- Sugestão = `spell.correction(palavra)` com `confidence = 1 - levenshtein(orig, sug)/len(orig)`
- Aplica todas as correções com confidence ≥ 0.75
- Preserva caixa do original

**Vocabulário extra** (termos pedagógicos comuns):
- siglas educacionais (BNCC, AEE, SEMED, EJA, PCD, TEA, TDAH, FUNDEB, PNAE, LGPD…)
- termos comuns: remanejado, rematriculado, multisseriada, alfabetizado, autoavaliação, psicomotor…
- nomes/locais: araguaia, floresta, tocantins…

**UI estendida** (`pages/TextImprovement.jsx`):
- Badge laranja "✏️ Ortografia" + confiança em %
- Diff visual das correções: `palavra ❌ → sugestão ✅ (XX%)`
- Filtro por tipo (Todos / Formatação / Ortografia)
- Texto com correções aplicadas mostrado no painel "Sugestão"

**Validação E2E**: 6 typos genuínos detectados com confidence 78-92% (Necessitra→Necessita, atendimnto→atendimento, profesora→professora, interpretaçao→interpretação, discussao→discussão, Avaliacao→Avaliação). Falsos positivos (Remanejado→Remunerado) eliminados após adicionar termos ao vocabulário extra ✅


**Regras de preservação** (script `normalize_content.py`):
- Siglas (AEE, BNCC, SEMED, TEA, ETI, B1-B4, CNPJ, CPF, RG, NIS, PCD, LGPD, etc.)
- Citações entre aspas simples ou duplas
- Datas (`dd/mm/aaaa`), horas (`hh:mm`), percentuais (`85%`), números
- Sentence case: 1ª letra após `.` `!` `?` ou início → maiúscula; restante minúsculo

**🛑 NUNCA toca em**: BNCC, learning_objects, módulo AEE (bloqueado), planos/objetivos AEE, conteúdos programáticos.

**Arquivos**:
- Script: `/app/backend/scripts/normalize_content.py`
- Router: `/app/backend/routers/content_review.py` (super_admin/admin/admin_teste)
- Página: `/app/frontend/src/pages/ContentReview.jsx` (rota `/admin/content-review`)
- Coleção MongoDB: `content_review_queue` (status: pending/approved/rejected/edited)
- Endpoints: `GET /api/admin/content-review`, `/stats`, `POST /:id/approve`, `/:id/reject`, `/:id/edit-and-approve`, `/bulk-approve`
- Dashboard: novo atalho "Revisão de Conteúdo" no grupo Administração

**Validação end-to-end [05/Mai/2026]**:
- 5 docs de teste enfileirados em `students.observations`
- ✅ APPROVE: doc original atualizado com `content_migrated: true`
- ✅ REJECT: status `rejected`, doc intocado
- ✅ EDIT-AND-APPROVE: admin refinou texto antes; doc gravou texto editado
- ✅ Frontend renderiza cards lado a lado, badges, filtros, bulk-select
- ✅ Siglas preservadas (`AEE`, `B1`, `BNCC`, `TEA`, `SEMED`, `ETI`)
- ✅ Datas/horas/percentuais preservados (`14:30`, `85%`, `15/03/2026`)
- ✅ Citações preservadas intactas

### Bug Fix — "Erro ao salvar plano AEE" (CSRF) **[04/Mai/2026]**
- **Root cause**: `pages/DiarioAEE.js` usa raw `fetch` (não axios) e o objeto `headers` só carregava Authorization+Content-Type. A `CSRFMiddleware` (server.py:788) rejeitava todo POST/PUT/DELETE em /api/aee/* com 403 "CSRF token inválido ou ausente". Resultado: nenhum plano/atendimento/modelo AEE conseguia ser salvo, editado, excluído ou duplicado pelo frontend.
- **Fix**: helper `readCsrfToken()` lê o token de `sessionStorage('sigesc_csrf_token')` (setado pelo response do `/auth/login`) com fallback para cookie `sigesc_csrf`, injetando-o como header `X-CSRF-Token` em todas as escritas do Diário AEE.
- **Tests**: `/app/backend/tests/test_aee_csrf_fix.py` (5 cenários: 403 sem CSRF, 201 com CSRF, e2e create+get+delete).
- **Status**: 100% backend + 100% frontend (validado pelo testing agent — iteration_70).

### Sprint G4.1 — Upload Direto de Logotipo **[04/Mai/2026]**
- Drag & drop + click-to-select de imagens (PNG, JPG, SVG, WebP) no `BrandingPanel.jsx`
- Validação client-side: tipo `image/*`, máx 2MB
- Backend: reutiliza `POST /api/upload?file_type=branding` (FTP externo + fallback local), aceita SVG agora (`.svg` adicionado em `ALLOWED_EXTENSIONS`)
- Após upload, URL pública é injetada em `form.logo_url` automaticamente e refletida tanto no slot do dropzone quanto no preview card em tempo real
- "ou colar URL manualmente" disponível como fallback (collapsible) para quem prefere link externo
- Botão X para remover logo selecionado antes de salvar

### Sprint G4 — Live Preview de Branding Multi-Tenant **[04/Mai/2026]**
**UX para super_admin configurar identidade visual de cada tenant em tempo real.**
- Backend: `routers/tenant_admin.py` — `PUT /api/tenant/branding` aceita {name, slogan, logo_url, primary_color, secondary_color}, valida hex `#RRGGBB`, super_admin pode passar `X-Mantenedora-Id` para editar tenant alvo (admin/gerente/secretario só editam o próprio tenant). Retorna o snapshot atualizado.
- Modelos novos: `BrandingUpdatePayload` + helper `_is_hex_color`.
- Frontend: `components/branding/BrandingPanel.jsx` + tabs em `pages/TenantAdmin.jsx`.
- **Live Preview real**: ao editar cores, aplica `--brand-primary` / `--brand-secondary` em `document.documentElement` em tempo real, refletindo no preview card (header gradient, botão, tags, tiles). Restaura CSS vars originais ao desmontar (proteção contra "saiu sem salvar").
- Após salvar, dispara `tenant-changed` para o `BrandingContext` recarregar e refletir mudança nos Layouts globalmente.
- Validação cliente: hex inválido → toast com erro; tenant não selecionado → toast.
- Tests: `/app/backend/tests/test_branding_g4.py` (8 cenários backend) + Playwright (5 fluxos E2E).
- Status testagem: 100% backend (8/8) + 100% frontend (5/5).

### Sprint G3 — Relatório Executivo Mensal **[03/Mai/2026]**
**Produto dentro do produto**: secretário/gestor recebe TODO MÊS um diagnóstico forensicamente auditável da rede que força DECISÃO (não descreve).
- Backend:
  - `services/monthly_report_service.py`: agregação mensal por mantenedora (escolas, alunos, frequência, cobertura curricular, alertas, aulas lançadas) + Claude Sonnet 4.5 com prompt forçando JSON estruturado (resumo executivo, ranking Top5/Bottom3, diagnóstico causal, 3 ações prioritárias com prazo e responsável, indicador de risco baixo/médio/alto, evidências numéricas)
  - `_stub_report()` fallback determinístico se IA indisponível — relatório SEMPRE pode ser gerado
  - Snapshot imutável (G1.5: hash SHA256 + HMAC) + Verifiable Document (G1.6: código `SIGESC-XXXX-XXXX`) com **validade de 30 dias** do link público
  - Idempotente por `(mantenedora_id, year, month)` via index unique → chamadas repetidas retornam o mesmo snapshot
  - `services/monthly_report_email.py`: gerador HTML/text de email-gatilho (não relatório passivo) com assunto que força ação: `[AÇÃO URGENTE] X escolas em risco alto — janeiro/2026`
  - `services/monthly_report_scheduler.py`: APScheduler dia 1º 06:00 UTC para cada mantenedora ativa, gera relatório do mês ANTERIOR e envia gatilho aos gestores (admin/gerente/secretario com email cadastrado)
  - Router `routers/monthly_reports.py`: POST `/generate`, GET listagem, GET `/{id}`, GET `/{id}/pdf?mode=executive|auditor` (reusa `snapshot_pdf`), POST `/{id}/send-email`
  - Index unique em `monthly_reports` por `(mantenedora_id, year, month)`
- Frontend: `pages/MonthlyReports.jsx` em `/admin/relatorios-mensais` (super_admin/admin/gerente/secretario)
  - Painel de geração (mês/ano com regerar via force=true)
  - Cards por mês com pílula de risco (alto/médio/baixo), KPIs principais, código SIGESC visível
  - Expansão inline mostra Resumo Executivo, Top5/Bottom3 com score 0-100, Diagnóstico Causal, 3 Ações Prioritárias com prazo e impacto
  - Botões: PDF Executivo · PDF Auditor · Enviar Email · Verificar publicamente
  - Modal de envio de email com lista de destinatários
- Email-gatilho: assunto adaptativo (`[AÇÃO URGENTE]` para risco alto, `[Atenção]` para médio, `[OK]` para baixo) + lista de bottom3 + 3 ações com prazo/responsável + código de verificação institucional
- Cron mensal idempotente: dia 1º 06:00 UTC para todos os tenants ativos
- Tests: `/app/backend/tests/test_monthly_reports.py` (18 cenários: validação período, sanitização IA, stub fallback, agregação, idempotência, validade 30 dias)

### Sprint G1.7 — Emissão de Declarações Escolares **[03/Mai/2026]**
- 3 tipos: Matrícula (90d), Frequência (30d), Escolaridade (180d)
- Backend: `services/school_docs_service.py` + `services/school_doc_templates.py`
  - PDF gerado via `reportlab` com cabeçalho oficial + QR Code dinâmico (`segno`)
  - Cada emissão gera código `SIGESC-XXXX-XXXX` (G1.6) e está em `verifiable_documents`
  - Status dinâmicos: válido / expirado (data) / revogado
  - Log de emissão em `school_documents_log` com `student_id`, tipo, finalidade, emitido_por, IP
- Router `routers/school_documents.py`: POST emit, GET list, POST revoke, GET PDF
- Frontend: `pages/SchoolDocuments.jsx` em `/admin/declaracoes`
- Tests: `/app/backend/tests/test_school_documents.py` (13 cenários)


### Fase 1 - Multi-Tenancy base
- `super_admin` desbloqueado em todas as rotas
- `mantenedora_id` injetado em todos os modelos
- CRUD de Mantenedoras com Wizard de Onboarding (CSV)

### Fase 2 - Isolamento e UX
- Row-Level Security em todas as collections (`students`, `classes`, `staff`, etc)
- `TenantSwitcher` + `TenantSyncBoundary` (remount sem reload)
- Remoção completa da coleção legacy `db.mantenedora`

### Permissions & UX polish
- Matriz de permissões: removida coluna ADMIN, SEMED renomeado (Tutor/Analista/Administração)
- Proteção do super_admin primário (sem botão de deleção)
- Admins podem enviar mensagens sem conexão mútua
- Modo Silencioso customizável (bipes de mensagens)
- Secretaria exibida no header
- **[22/Fev/2026]** TenantSwitcher reposicionado para a esquerda do header, agrupado visualmente com o bloco Mantenedora/Secretaria (melhor hierarquia visual)

### Boletim Virtual do Aluno  **[24/Fev/2026]**
- Nova rota `/aluno/boletim` (role=`aluno`) com redirect automático no login
- Backend: `GET /api/student/me/report-card` — identificação escola/aluno, notas b1..b4, recuperação por bimestre, recuperação final, média geral e situação
- Detecção automática de **turmas por CONCEITO** (Educação Infantil / 1º Ano / 2º Ano): exibe b1..b4 como **sigla real do conceito** (OD/DP/ND/NT para EI ou C/ED/ND para 1º-2º ano), com cor + tooltip descritivo + legenda. Sem recuperação, sem média numérica.
- Demais anos: 4 bimestres agrupados em 2 semestres (1º Sem: B1+B2, 2º Sem: B3+B4) com recuperação por bimestre + recuperação final
- Fund II (6º–9º) e EJA 3ª/4ª etapa → faltas por componente curricular
- Alertas: `> 25%` faltas → aviso vermelho; `≥ 95%` presença → parabéns verde
- Seed idempotente de conta de teste: `python backend/scripts/seed_test_student.py` (aluno@sigesc.com / aluno123)
- Testes: `/app/backend/tests/test_student_portal.py` (9 cenários, 100% pass)

### Ajustes finos **[24/Fev/2026]**
- Boletim online: conceitos exibidos como siglas reais (OD/DP/ND/NT e C/ED/ND) com legenda, cor e tooltip — não mais convertidos em nota numérica
- Cadastro/Editar/Visualizar Aluno → Info. Complementares → Deficiências / Transtornos: adicionada opção **"Transtorno do Desenvolvimento da Linguagem (TDL)"**
- PDF Detalhes da Turma: turmas com Tipo de Atendimento = **AEE** agora listam os alunos vinculados via `students.atendimento_programa_class_id`, `planos_aee` e `atendimentos_aee` (mesma lógica do endpoint JSON)

### Ação de Vínculo: Reclassificar **[24/Fev/2026]**
- Nova ação **"🎓 Reclassificar"** em Editar Aluno → Turma/Observações → Vínculo com Turma (entre Progredir e Cancelar)
- Semelhante à Progressão mas com motivo específico (avaliação de conhecimento, Art. 23 da LDB)
- Backend: `action_type='reclassificacao'`, `enrollment.status='reclassified'`, `action_hint='reclassificacao'` roteado em `/api/students/{id}` PUT
- Endpoint `POST /api/students/{id}/copy-data` aceita `copy_type='reclassificacao'` (copia só frequência, não as notas)
- **Bloqueio de diário** (turma origem e destino) funcionando para todas as 4 ações (Remanejado, Transferido, Progredido, Reclassificado):
  - Origem: bimestres cujo início é > `action_date` → `blocked_after_action`
  - Destino: bimestres cujo fim é < `enrollment_date` → `blocked_before_enrollment` (agora com `enrollment_date` sempre populado = data da ação)
  - `action_type_map` atualizado em `grades.py`, `attendance.py` e `class_details.py` (inclui `reclassificacao`)
  - Filtros de enrollment inativa atualizados para incluir `reclassified`

### Ferramenta: Criar Usuários de Alunos em Lote **[24/Fev/2026]**
- Backend: endpoint `POST /api/admin/student-users/bulk-create` (super_admin only) com service em `/app/backend/services/student_account_service.py` — pré-carga em 3 queries + `insert_many` em lotes de 500 (10k alunos em ~10s)
- Script CLI: `python backend/scripts/create_student_users_bulk.py` (dry-run + `--apply`)
- **UI em Ferramentas de Administração** (`/admin/tools`): novo card "Criar Usuários dos Alunos (em lote)" com:
  - Botão "Ver Prévia" (dry-run) → 4 KPIs (avaliados / a criar / já possuem / ignorados) + tabela Aluno/E-mail/Senha
  - Expansor com lista de alunos ignorados e motivo
  - Botão "Criar N usuário(s)" → diálogo de confirmação → "Confirmar Criação"
  - Mensagem de sucesso com contador de inseridos
- Regra: e-mail = `{primeironome}{ultimosobrenome}{MM}@sigesc.com`, senha = `DDMMAAAA`, `must_change_password=true`
- Idempotente: pode rodar quantas vezes quiser — cria apenas quem falta
- Testes: 5/5 pytest em `test_student_bulk_users.py` + 100% frontend (iteration_63)

### Portal do Aluno — Dashboard e Layout **[24/Fev/2026]**
- Nova rota `/aluno` com `AlunoDashboard.jsx` — dashboard do aluno
- Login de aluno agora cai em `/aluno` (Dashboard.js também redireciona `role=aluno` → `/aluno`)
- `/aluno` e `/aluno/boletim` renderizados **dentro do `<Layout>`** (barra superior com logo SIGESC, mantenedora/secretaria, nome do usuário e logout; footer com © 2026 Gutenberg Barroso + link Aprender Digital)
- Boletim exibe turno em português via `SHIFT_LABEL`
- Link "Início" no Boletim aponta para `/aluno`
- PDF **Detalhes da Turma** — turmas AEE agora exibem `Série/Etapa: -` (não o `grade_level`)
- Dashboard do Aluno com **3 cards**:
  - 🎓 **Boletim** (card principal) → `/aluno/boletim`
  - 📅 **Próximos Eventos** — consome `/api/student/me/upcoming-events` (calendário letivo da escola, até 5 eventos futuros, com data relativa Hoje/Amanhã/em X dias/DD-MM-YYYY)
  - 📣 **Avisos** — consome `/api/student/me/announcements` (avisos direcionados, não lidos em negrito + badge vermelho com contador)
- **Bug fix (announcements.py)**: `get_announcement_target_users` agora usa `class_ids` (plural) em vez de `class_id` (singular) — estava quebrado desde sempre pelo modelo `AnnouncementRecipient` só declarar a chave plural. Agora avisos direcionados a turmas realmente chegam aos professores/responsáveis/alunos da turma.
- Testes: 15/15 pytest (`test_student_portal.py` + `test_class_details_pdf_aee.py` + `test_student_dashboard_widgets.py`)

### AEE - Acesso universal do Super Admin (Feb 2026)
- **Backend** (`/app/backend/routers/aee.py`): `ROLES_AEE_WRITE` agora inclui `super_admin`, `admin_teste` e `gerente`; `ROLES_AEE_VIEW` inclui `semed` (além de `semed1/2/3`). Resolve 403 em `GET /api/aee/estudantes`, `/planos`, `/atendimentos` e `/diario`.
- **Frontend** (`/app/frontend/src/pages/DiarioAEE.js`): `fetchData()` refatorado com helper `safeFetchJson()` que valida `response.ok` antes de invocar `.json()` e captura falhas de rede isoladamente. Elimina o crash `TypeError: Failed to execute 'json' on 'Response': body stream already read` quando qualquer endpoint retorna HTTP não-2xx.
- Validação: curl com Super Admin retorna 200 em todos os endpoints AEE; smoke screenshot confirma listagem de estudantes carregando sem erro de console.

### AEE - Salvar Plano AEE corrompendo enums (Feb 2026)
- **Backend** (`/app/backend/text_utils.py`): adicionados `dias_atendimento`, `prazo` e `tipo` à lista `LOWERCASE_FIELDS`. O helper `format_data_uppercase()` estava convertendo valores Literal para MAIÚSCULAS (ex.: `"segunda"` → `"SEGUNDA"`), causando `pydantic.ValidationError` → HTTP 500 → CORS error em produção (proxy Coolify removia headers em respostas 500). Validação: POST `/api/aee/planos` retorna 201 e mantém enums em minúsculas, com texto livre (descrições) em MAIÚSCULAS.
- **Frontend** (`/app/frontend/src/components/PlanoAEEModal.js`): `handleSave()` agora converte `carga_horaria_semanal` de string vazia para `null` via helper `toIntOrNull()`. Resolve HTTP 422 → "Erro ao salvar plano".

### Code Quality - Onda 1 (Feb 2026)
- **MD5 → SHA-256** em `/app/backend/utils/cache.py` (cache TTL) e `/app/backend/pdf/utils.py` (cache de logotipos em disco/memória).
- **Console silencer em produção** — novo `/app/frontend/src/utils/silenceLogsInProduction.js` importado em `index.js`. Anula `console.log/debug/info` quando `NODE_ENV === 'production'`, mantendo `warn/error`.
- **Hardcoded test credentials** — bulk refactor (35 arquivos em `tests/` e `scripts/`) substituindo literais (`@Celta2007`, `aluno123`, etc.) por `os.getenv("SIGESC_TEST_*_PASSWORD", "<default>")`. Permite override via env em CI sem quebrar execução local.
- **React keys estáveis** em StudentsComplete (authorized_persons com `_key` UUID-like, documents_urls com URL como key), SchoolsComplete (5 ocorrências, agora usando IDs/nomes únicos), TutorialDiarioAEE (4 ocorrências, usando títulos de itens estáticos).
  - **Edit flow protegido**: `handleEdit` injeta `_key` em `authorized_persons` carregados do backend (Pydantic ignora extras silenciosamente, então `_key` não persiste — recriado a cada abertura).
  - **Save flow protegido**: `handleSubmit` faz strip do `_key` antes de POST/PUT (limpeza defensiva).
  - **Validação E2E (Playwright)**: abrir aluno → adicionar 2 pessoas → digitar `PESSOA_PRIMEIRA`/`PESSOA_SEGUNDA` → remover a primeira → resultado: `['PESSOA_SEGUNDA']` (correto). 0 React key warnings, 0 console errors. Confirma reconciliação React correta.
  - **Defesa em profundidade no backend** (Feb 2026): `AuthorizedPerson` model tem `ConfigDict(extra="ignore")` explícito; novo `tests/test_authorized_persons_sanitization.py` (2 testes, ambos passando) garante via PUT e POST que `_key` é silenciosamente descartado e nunca chega ao MongoDB. Estratégia: sanitização (não rejeição) — se um cliente legado enviar `_key`, a API ainda funciona.
- **Itens descartados após análise:** `is None`/`is True`/`is False` na codebase são **semanticamente corretos** (distinguem `None` de `False`), e o reviewer flaggeou erroneamente.

### Code Quality - Onda 2 (Hook Dependencies, Feb 2026)
**Estratégia: 1 arquivo por vez, parar para teste manual entre cada um.**

#### useStaff.js ✅ (commitado)
- Função `extractErrorMessage` movida do escopo do hook para escopo de módulo (linha 10). Era recriada a cada render, causando referência stale nos 4 useCallback que a usavam mas não a incluíam nas deps.
- Solução cirúrgica: 1 mudança resolveu os 4 callbacks flagados. Mais correta que adicionar nas deps (que recriaria callbacks a cada render).
- Validação E2E: aba Lotações + edição de servidor + Salvar → toast verde. 0 errors/warnings/loops. `extractErrorMessage` testado com mocks (Pydantic array, string, vazio, sem response) — todos os caminhos OK.

#### VaccineDashboard.js ✅ (commitado)
- Diagnóstico real diferente do reviewer: as deps arrays dos 4 useEffects estavam corretas (setters e module imports são inerentemente estáveis).
- **Bug latente real encontrado:** `localStorage.getItem('accessToken')` lido a cada render → token NÃO se atualizava reativamente em renovações automáticas. As 7 chamadas axios diretas usariam token stale após renovação até algum setState forçar re-render.
- Fix (1 linha): `const { user, logout, accessToken: token } = useAuth();` substituiu o read de localStorage. Token agora reativo.
- Validação: cards KPI populados, 0 errors/warnings/loops.

#### Grades.js ✅ (a aguardando teste manual em produção)
- **Confirmado: useMemo `gradesContextValue` (linha 629) era inútil** — 6 funções (`loadGradesByClass`, `handleSelectStudent`, `handleClearSearch`, `updateLocalGrade`, `saveGrades`, `updateStudentGrade`) eram recriadas a cada render e estavam no deps array → memo invalidava sempre.
- **8 mudanças aplicadas:** 7 funções envolvidas em `useCallback` com deps mínimas + `showAlert` adicionalmente.
- **Bonus de imutabilidade** em `updateLocalGrade` e `updateStudentGrade`: trocados de `[...gradesData]` (captura no closure) e mutação in-place para **functional setState** (`setGradesData(prev => ...)`) com spread imutável. Elimina:
  - Risco de média stale em digitações rápidas (race condition)
  - Mutação acidental do prevState (anti-pattern React)
  - Permite remover `gradesData` e `studentGrades` das deps dos callbacks (eram instabilizadores).
- **Os 3 riscos antecipados pelo usuário:**
  - 🚨 Cálculo errado: blindado (cálculo agora dentro do functional setState)
  - 🚨 Stale data: blindado (functional setState garante estado mais recente)
  - 🚨 useMemo inútil: resolvido (callbacks estáveis fazem o memo realmente cachear)
- Smoke E2E passou (0 errors/warnings/loops). Teste com digitação real pendente — banco preview tem turma sem alunos. **Aguarda validação manual em produção.**

#### Attendance.js ✅ (validar manualmente em produção)
- **2 funções com bonus de imutabilidade** (`updateStudentStatus`, `markAll`) — functional setState (`setAttendanceData(prev => ...)`) elimina stale data quando professor clica rápido em Falta/Presente. Multi-aula path do `markAll` aninha `setAulaStatuses(prevStatuses => ...)` em `setAttendanceData(currentData => ...)` para acessar `students` sem capturar attendanceData no closure.
- **9 funções envolvidas em useCallback** com deps mínimas: `checkDate`, `showAlertMessage`, `loadMedicalCertificates`, `hasActiveCertificate`, `getCertificateInfo`, `loadClassReport`, `generateBimestrePdf`, `loadAlerts`, `navigateDate`.
- **2 funções NÃO foram tocadas** (`loadAttendance`, `saveAttendance`): usam `isMultiAula` que é declarado depois delas no componente — envolver em useCallback geraria TDZ error em runtime. Mantidas como funções normais.
- **Divergência semântica aceita**: removido `if (!attendanceData) return;` global em `updateStudentStatus`/`markAll`. Sem impacto prático (UI bloqueia interação quando attendanceData é null).
- **App.js linha 315**: adicionado `super_admin`, `admin_teste`, `gerente` à `allowedRoles` da rota `/admin/attendance` (mesmo padrão de outras rotas já corrigidas).
- Smoke test passou: página carrega, navegação entre 5 abas funciona, 0 React warnings/loops/runtime errors.

### Token blacklist & revoke-all on logout (Feb 2026, Onda 2 follow-up)
**Descoberta crítica via pytest do contrato de auth (`test_token_refresh_contract.py`):** `auth_utils.token_blacklist` existia mas **nunca funcionou em produção** — bug de datetime aware vs naive engolido silenciosamente por `try/except` em `is_token_revoked`. Logout não revogava nada. Mantinha access_tokens válidos até expirarem (15min).

**Fix multi-arquivo (escopo mínimo, defesa em profundidade):**
- `auth_utils.create_access_token`: adicionado `iat` numérico (segundos epoch) — permite revogação via marker `revoke_all_before`.
- `auth_utils.is_token_revoked`: normaliza timezone do `revoke_all_before` (Motor sem `tz_aware=True` retorna datetime naive) antes de comparar com `token_issued` (aware) — eliminava o TypeError silencioso que causava fail-open.
- `auth_middleware.get_current_user`: consulta `token_blacklist.is_token_revoked()` após decode JWT, com `jti` (futuro) e `user_id+iat` (agora). Tokens emitidos ANTES do fix (sem iat) ignoram check de revoke_all — apenas expiração natural.
- `routers/auth.logout`: chama `revoke_all_user_tokens(user_id, reason='user_logout')` em adição ao revoke do refresh_token. Em ambiente educacional (multi-device, salas compartilhadas), logout invalida TODAS as sessões — comportamento mais seguro.
- `routers/auth.refresh`: consulta blacklist antes de emitir novo token (fecha o buraco onde refresh_token escapava após logout).
- `server.py`: `token_blacklist.set_db(db)` movido para top-level (defesa em profundidade contra falha silenciosa do startup event).

**Pytest suite (11/11 verdes):**
- `test_token_refresh_contract.py`: contrato completo de auth incluindo:
  - Token antigo continua válido após refresh (anti-stale-auth — protege o cenário motivador do VaccineDashboard)
  - 10 chamadas paralelas com tokens antigo+novo: 100% sucesso
  - Logout invalida access_token de TODOS os devices do mesmo usuário
  - Refresh token bloqueado após logout
  - Type confusion (access usado como refresh) → 401

**Trade-off aceito:** logout em device A invalida sessão em device B. Em ambiente educacional, isso é **feature** (evita rastros em PCs compartilhados de escola) — não bug.

#### Split App.js ⏸️ (Onda 2 item g — pendente)

### Forçar Logout Remoto (Feb 2026)
- **Backend** (`/app/backend/routers/admin.py`): novo endpoint `POST /api/admin/sessions/revoke/{user_id}` (somente `super_admin`). Invoca `token_blacklist.revoke_all_user_tokens()`, remove do tracker `active_sessions`, registra audit log e notifica via WebSocket o cliente alvo (`type: force_logout`). Bloqueia auto-revogação (400) — usar `/api/auth/logout` para a própria sessão. Adicionado `import logging` + `logger = logging.getLogger(__name__)` que estavam faltando.
- **Frontend** (`/app/frontend/src/pages/OnlineUsers.js`): nova coluna "Ações" com botão `Forçar Logout` (apenas para super_admin, oculto na própria linha — substituído por "Você"). Modal de confirmação com nome/email do alvo + aviso sobre invalidação de tokens (web/mobile). Toast de feedback (success/error) com auto-dismiss em 5s.
- **Permissão de rota**: `App.js` linha 361 — `super_admin` adicionado a `allowedRoles` de `/admin/online-users`.
- **Validação E2E (8/8 curl + Playwright):**
  - super_admin lista 2 online → POST revoke do aluno (200 + payload com nome/email) → aluno tenta `/api/auth/me` → 401 (token revogado)
  - super_admin tentando revogar a si mesmo → 400 ("Use /api/auth/logout para encerrar sua própria sessão")
  - revoke de UUID inexistente → 404
  - aluno (sem permissão) tentando revogar → 401 (já estava revogado pelo step anterior)
  - UI: modal abre, exibe alvo, botão Cancelar funcional
- **Trade-off educacional**: revogação invalida sessões de TODOS os devices do alvo (mesmo padrão do logout próprio) — feature, não bug, em ambiente de salas compartilhadas.

### Notificação em tempo real de Force Logout (Feb 2026)
- **Frontend** (`/app/frontend/src/components/notifications/NotificationBell.js`): aproveita a conexão WebSocket já montada no Layout. Adicionado handler para `data.type === 'force_logout'` que exibe modal "Sessão encerrada" com a `data.message` enviada pelo backend (`"Sua sessão foi encerrada pelo administrador"`).
- **Modal**: ícone `ShieldAlert`, título, mensagem, aviso de segurança e botão único "Ir para o login" (`data-testid="force-logout-notice-confirm"`).
- **Saída segura**: clique limpa localStorage diretamente (`accessToken`, `refreshToken`, `userData`, `lastActivityTime`) e usa `window.location.replace('/login')` — hard reload para resetar todo estado React, WebSockets e timers (semanticamente correto: sessão foi forçosamente encerrada). Evita travamento do `await logout()` no axios interceptor que tenta refresh com tokens revogados.
- **Validação E2E (Playwright)**: aluno logado → super_admin revoga via API → modal aparece em ~3s → clique → redirect `/login` + localStorage limpo. ✅

### 🚨 Fix Crítico: Vazamento Cross-Tenant em designar_gerente (Feb 2026)
**Bug confirmado em produção:** gerente designado para Mantenedora B continuava vendo dados da Mantenedora A.

**Causa raiz** (`/app/backend/routers/mantenedoras.py`): o endpoint `POST /api/mantenedoras/{mid}/gerente` apenas executava `$set: {role, mantenedora_id}`, sem:
1. Revogar tokens ativos do usuário designado → JWT antigo continuava válido com `mantenedora_id` da mantenedora antiga, e `apply_tenant_filter` retornava dados da mantenedora errada (o filtro confia no payload do JWT, não no DB).
2. Limpar `school_links`/`school_ids` que apontavam para escolas de outras mantenedoras → `verify_school_access` permite gerente em qualquer school da lista, criando bypass adicional.

**Fix multi-camada:**
- **Sanitização de school_links**: filtra para manter apenas escolas cuja `mantenedora_id == mid` (escolas estranhas são removidas em silêncio, contagem retornada no payload).
- **Revogação de tokens**: `token_blacklist.revoke_all_user_tokens(user_id, reason='designar_gerente_to_mantenedora_{mid}')` força relogin → próximo JWT terá `mantenedora_id` correto.
- **Audit log**: `action='designar_gerente'` registra old/new role, mantenedora_id e contagem de school_links antes/depois.
- **Resposta enriquecida**: agora inclui `school_links_kept` e `school_links_removed_cross_tenant` para feedback ao admin.

**Validação (curl + pytest, 100% verde):**
1. User era admin de Floresta (mantenedora_id=A no DB+JWT) → vê 9 alunos da Floresta com seu token
2. Super_admin promove para gerente de Pau Darco (B): resposta `{"school_links_removed_cross_tenant": 1, "school_links_kept": 0}`
3. Token antigo → **HTTP 401 "Token revogado"** ✅
4. Re-login: JWT novo tem `mantenedora_id=B`, `school_ids=[]`
5. `/api/students` → 0 alunos (Pau Darco está vazia) ✅ (antes: 9 alunos da Floresta)
6. `/api/schools` → apenas escolas de Pau Darco ✅
- **Pytest**: `tests/test_designar_gerente_security.py::test_old_token_revoked_after_designar_gerente` PASSED.

### Congelamento de origem + Migração de dados (Feb 2026)
**Regra de negócio (uniformizada para frequência e notas):**
- **Turma de origem**: a partir da data da ação (transferência, remanejamento, progressão, reclassificação), o **bimestre que contém a `action_date` E todos os posteriores ficam bloqueados para edição**. Notas/células com data anterior à ação permanecem visíveis (read-only); notas em bimestres totalmente posteriores são retornadas como `null`; células de frequência com `date >= action_date` aparecem em branco no PDF.
- **Turma de destino**: cópia uniforme — frequência E notas migram em **TODAS as 4 ações** (antes só remanejamento copiava notas). Cada registro copiado recebe `migrated_from_class_id` (id da turma origem) e `migrated_at` (timestamp ISO). Edição dos registros migrados é restrita a **admin / admin_teste / super_admin / gerente / secretario**; professor regular vê os valores em read-only com badge "Migrado".
- **Histórico legado**: ações anteriores ao fix permanecem editáveis livremente (regra vale apenas para ações futuras, sem migração retroativa).

**Backend:**
- `students.py copy_student_data_to_new_class`: removido o branch `if copy_type == 'remanejamento'` que limitava a cópia de notas; agora copia em qualquer `copy_type`. Cada record (`attendance.records[]`) e cada documento `grades` recebe `migrated_from_class_id` + `migrated_at`. Permissão expandida: super_admin/gerente também podem invocar (necessário para o fluxo do bug de tenant que revoga tokens). Idempotente — não sobrescreve registros já existentes no destino.
- `grades.py _ensure_can_edit_migrated_grade()`: helper aplicado em `POST /grades`, `PUT /grades/{id}` e `POST /grades/batch` — bloqueia (403) edição de grade com `migrated_from_class_id` para roles fora da lista autorizada.
- `grades.py load_grades_by_class`: `blocked_after_action` passou de `b_start > action_date` para `b_end >= action_date` (inclui bimestre que contém a data). Bimestres com `b_start > action_date` retornam `b1..b4=null` no payload (mantém B1=8.5 visível, B2..B4=None) + recovery/rec_s1/rec_s2/final_average zerados quando o bimestre referenciado está totalmente após a ação.
- `attendance.py _block_if_changing_migrated_attendance()`: ao salvar uma sessão de frequência, registros com `migrated_from_class_id` são preservados intactos para roles não autorizadas; para roles autorizadas, a flag de migração é mantida ao atualizar o status (auditável).
- `attendance_ext.py get_attendance_bimestre_pdf`: busca `student_history` por turma para alunos inativos; durante a montagem do attendance_by_date pula registros com `att.date >= action_date` → célula em branco no PDF.
- `auth_middleware.verify_school_access`: cross-tenant guard — se `active_tenant` ≠ `school.mantenedora_id`, retorna 403 "Escola pertence a outra mantenedora" (fecha bypass mencionado no fix anterior; gerente não pode mais usar `GET /schools/{id}` para ler escola de outra mantenedora mesmo via school_links residuais).

**Frontend:**
- `Grades.js canEditStudentGrade()`: adicionado parâmetro `gradeRecord` — retorna `false` se `gradeRecord.migrated_from_class_id` e user fora da lista autorizada.
- `GradesTable.jsx`: badge âmbar "Migrado" ao lado do nome do aluno; tooltip nos campos explicando "Nota migrada da turma de origem — apenas secretário, gerente ou super administrador podem editar".

**Pytests** (`tests/test_freeze_origin_and_migration.py` + `tests/test_freeze_migration_extra.py`, 7/7 passing):
1. `copy-data` marca todos os registros com `migrated_from_class_id` (3 attendances + 1 grade copiados).
2. `load_grades_by_class` na origem retorna `blocked_after_action=[1,2,3,4]` para aluno remanejado em 10/03/2026, e `b1=8.5` (visível), `b2=b3=b4=null`.
3. Professor tentando PUT/POST/batch em grade migrated → 403.
4. Super_admin pode editar grade migrated; flag `migrated_from_class_id` é preservada após update.
5. PDF de frequência por bimestre retorna 200 (turma destino e turma origem com action_date).
6. Cross-tenant guard: gerente Mant A com school_link residual → 403 'Escola pertence a outra mantenedora'.

### Fix Race Condition em revoke_all_user_tokens (Feb 2026)
**Bug descoberto pelo testing agent durante a validação:**
- `auth_utils.create_access_token` grava `iat` como inteiro de segundos (`int(now.timestamp())`)
- `revoke_all_user_tokens` gravava `revoke_all_before` como datetime com microssegundos
- Quando re-login ocorria no mesmo segundo da revogação, `token_issued (.000) < revoke_before (.872)` → novo token incorretamente classificado como revogado → 401

**Fix em `auth_utils.revoke_all_user_tokens`**: grava `revoke_all_before` no FINAL do segundo (`microsecond=999999`):
- Tokens com `iat` no mesmo segundo da revogação OU anteriores → revogados ✅
- Tokens emitidos a partir do próximo segundo → válidos ✅
- Trade-off: re-login imediato após revoke precisa aguardar virada do segundo (~1s). Em produção UI o fluxo passa por tela de login + digitação (>1s), tornando isso transparente.

**Validação**: 19/19 testes pytest passando incluindo `test_designar_gerente_security`, `test_token_refresh_contract` (11 cenários de auth) e os 7 de freeze/migration.

### "A" de Atestado no PDF de Frequência (Feb 2026)
**Regra de negócio:** dias amparados por atestado médico (registrados pelo secretário em `medical_certificates`) devem renderizar a letra **'A'** nas colunas correspondentes do PDF de frequência, **substituindo qualquer status (P/F/J)** que o professor tenha lançado. Atestado conta como **presença** nos totais (não-falta).

**Backend:**
- `/app/backend/routers/attendance_ext.py get_attendance_bimestre_pdf`: após buscar attendances, varre `medical_certificates` no intervalo do bimestre e monta `medical_days_by_student[student_id] = set(['YYYY-MM-DD'])`. Cada `students_attendance[i]` recebe a chave `medical_days` com a lista ordenada de datas amparadas por atestado.
- `/app/backend/pdf/frequencia.py`: ao iterar `attendance_days`, antes de aplicar `status_map → P/F/J`, verifica `day_only in medical_days` → renderiza **'A'** e incrementa `presencas` (atestado é presença justificada).
- Regra é completamente data-driven: o atestado pode ter sido inserido **antes ou depois** do registro de frequência pelo professor; no momento da geração do PDF, o atestado vence.

**Pytest** (`tests/test_attendance_pdf_atestado.py`): cria turma + aluno + 2 sessões (P em 09/03 e F em 10/03) + atestado cobrindo 09/03 a 12/03 → gera PDF e valida que o texto extraído contém 'A' (independente do status original lançado pelo professor). PASSED.

### Propagação da regra "A" nos relatórios sintéticos (Feb 2026)
**Uniformização**: a regra "atestado vence sobre P/F/J" agora é aplicada também:
- **Relatório de turma** (`GET /api/attendance/report/class/{class_id}`): `student_stats` reclassifica células como `medical` quando data ∈ `medical_days[sid]`; `attendance_percentage = (present + justified + medical) / total * 100`.
- **Cálculo individual** (`GET /api/attendance/student-attendance/{student_id}`): adicionado bucket `medical` e desconto de faltas cobertas por atestado antes do cálculo da porcentagem.
- **Boletim e Ficha Individual** (`pdf/boletim.py` via `routers/documents.py`): no loop que calcula `faltas_regular` e `faltas_por_componente`, datas com 'F' que estão em `medical_days_set` deixam de contar como falta (atestado vence). Resultado: a coluna "Faltas" do boletim e o `total_geral_faltas` ficam alinhados com o PDF de frequência da turma.
- **Declaração de Frequência** (`pdf/declaracoes.py` via `routers/documents.py`): `total_faltas -= faltas_cobertas_por_atestado` antes de calcular `frequency_percentage`.

**Helper centralizado**: `/app/backend/services/attendance_utils.py` expõe:
- `fetch_medical_days_for_student(certs, candidate_dates)` → set de YYYY-MM-DD cobertos por atestado, opcionalmente filtrado pelo calendário letivo.
- `classify_with_atestado(date, raw_status, medical_days)` → status efetivo ('A'/'P'/'F'/'J'/'L').
- `compute_attendance_buckets(records, medical_days)` → P/F/J/L/A/total.
- `attendance_percentage(buckets)` → (P+J+A)/total × 100.

**Pytest adicional**: `test_class_summary_excludes_certificate_days_from_absences` valida que `/api/attendance/report/class/{class_id}` retorna `absent=0`, `medical=2`, `attendance_percentage=100.0` para um aluno com 2 sessões (P+F) ambas cobertas por atestado. 10/10 pytest verde.

### Cabeçalho institucional no PDF de Frequência (Feb 2026)
**Antes**: brasão minúsculo (1.05×0.7cm, quase invisível) e cabeçalho mostrava apenas o nome da escola + período.

**Depois** (`pdf/frequencia.py`):
- Brasão **aumentado para 2.2cm** (proporção quadrada).
- Bloco institucional ao lado do brasão: **Nome da mantenedora** (10pt bold) → **Secretaria** (8pt itálico) → **Slogan** (7pt cinza, opcional) — usa o mesmo padrão do boletim/declaração para consistência visual.
- Coluna direita centralizada: **nome da escola** (linha 1) + **título "FREQUÊNCIA - Xº BIMESTRE DE YYYY"** + **período** (linha 2).
- Linha vertical sutil entre brasão e bloco institucional.
- Fallback gracioso: se a mantenedora não tem brasão, layout colapsa para 2 colunas (institucional + escola/título).

**Validação**: `test_attendance_pdf_renders_A_for_certificate_days` estendido para verificar a presença de "PREFEITURA"/"FLORESTA" e "EDUCAÇÃO" no texto extraído do PDF. Validação manual com curl em escola real (`ESCOLA TESTE MULTISSERIADA`) gerou PDF de 5MB com cabeçalho correto. 7/7 pytest verde.

### Diário AEE: persistência completa do Plano e Atendimento (Feb 2026)
**Bug**: vários campos preenchidos no formulário do Plano AEE não eram salvos. Reabrir o plano para edição mostrava os campos vazios.

**Causa raiz**: o frontend (`PlanoAEEModal.js`) coletava 13 campos que **não existiam** em `PlanoAEEBase`. Por causa de `extra="ignore"`, o Pydantic descartava silenciosamente todos esses campos no save, sem erro visível.

**Campos adicionados ao `PlanoAEEBase` + `PlanoAEEUpdate`**: `escola_origem_nome`, `data_elaboracao`, `periodo_vigencia`, `linha_base_situacao_atual/potencialidades/dificuldades/comunicacao`, `indicadores_progresso`, `frequencia_revisao` (Literal mensal/bimestral/trimestral/semestral), `criterios_ajuste`, `combinados_professor_regente`, `adaptacoes_por_componente`.

**Outros fixes:**
- `carga_horaria_semanal` mudou de `int` (minutos) para `Optional[str]` — frontend envia "4 horas", "240 min".
- `text_utils.LOWERCASE_FIELDS` recebeu `frequencia_revisao` (mesmo bug que `dias_atendimento`).
- Frontend (`PlanoAEEModal.js handleSave`): não converte mais `carga_horaria_semanal` em int.

**Pytests** (`tests/test_aee_full_save.py`, 2/2 passing):
1. `test_plano_aee_saves_and_returns_all_fields`: cria plano com 13 novos campos → GET retorna todos preservados → PUT atualiza 3 campos → GET valida atualização e preservação dos outros.
2. `test_atendimento_aee_full_save_and_edit`: atendimento completo com todos os campos → `duracao_minutos` calculado (60 min) → PUT recalcula (90 min) → demais campos preservados.

**Validação total**: 12/12 pytest verde.

### Validação E2E: Professor → Plano AEE via Modelo (Apr 2026)
**Pergunta do usuário**: "Os Planos AEE a partir de um modelo podem ser criados, salvos e visualizados pelo professor?"

**Resultado**: SIM ✅. Fluxo validado ponta-a-ponta com conta `professor.teste@sigesc.com` (role efetivo `professor`):
1. `GET /api/aee/templates` — 8 modelos institucionais visíveis.
2. `POST /api/aee/planos/from-template` — cria plano em rascunho (HTTP 201) com `professor_aee_id` correto.
3. `GET /api/aee/planos/{id}` — leitura permitida (`check_aee_access`).
4. `PUT /api/aee/planos/{id}` — atualização permitida (`check_aee_write_access`).
5. `GET /api/aee/planos/{id}/pdf` — PDF gerado (HTTP 200, ~5MB).
6. `GET /api/aee/planos` — lista filtrada automaticamente por `professor_aee_id == current_user.id`.
7. UI: Tab "Modelos" + botão "Novo a partir de Modelo" visíveis (`canEdit = role !== 'semed3'`).

### Permissões finais da Biblioteca de Modelos AEE para Professor (Apr 2026)
**Regra institucional SEMED**: Professor recebe TODAS as ações da Biblioteca **EXCETO exclusão** de modelos ou planos.

**Backend (`/app/backend/routers/aee.py`)**:
- `delete_template` agora retorna 403 quando `current_user.role == 'professor'` (mesmo para templates próprios).
- `delete_plano_aee` já não permitia professor (lista de roles autorizadas inclui apenas admins/secretário/coordenador/auxiliar/apoio_pedagogico/super_admin/gerente).

**Frontend (`/app/frontend/src/pages/DiarioAEE.js`)**:
- Nova flag `canDelete = canEdit && !isProfessor`.
- Botão "Excluir Modelo" e "Excluir Plano" agora renderizam apenas quando `canDelete === true`.

**Validação curl** (8 cenários, todos verde):
- Professor cria template: 200 ✅
- Professor exclui próprio template: 403 ✅
- Professor exclui template institucional: 403 ✅
- Professor exclui plano: 403 ✅
- Professor duplica template institucional: 200 ✅
- Professor edita template duplicado: 200 ✅
- Admin exclui templates (cleanup): 200 ✅

**Validação UI screenshot**:
- Aba Modelos: 8 templates listados, ações apenas {duplicar, editar} — sem ícone de lixeira.
- Aba Planos: ações {visualizar, editar, duplicar, novo atendimento} — sem ícone de lixeira.

## Current Backlog

### Importador de Currículo — Extração V2 estruturada por tabela (May 2026) ✅
**Problema reportado**: descrições extraídas vinham com "ruído de colunas" (texto de "Propostas de Atividades" vazando em "Habilidades"), porque pdfplumber `extract_text()` lê em ordem de layout físico, misturando colunas.

**Solução V2** (`services/curriculum_extractor.py` reescrito):
- Passou a usar `page.extract_tables()` em vez de `extract_text()`.
- Detecta automaticamente a estrutura de cabeçalho do DCM:
  - Linha 0: `[EIXOS ESTRUTURANTES, COMPONENTE, ETAPA, ANO, BIMESTRE]`
  - Linha 1: valores (ex.: LÍNGUA PORTUGUESA, 3º, 1º)
  - Linha 2: sub-headers `[OBJETOS, HABILIDADES, PROPOSTAS, Nº DE]`
- Identifica a coluna "HABILIDADES" e extrai SOMENTE ela, eliminando vazamento.
- Agora preenche **automaticamente**: `ano`, `bimestre`, `componente_codigo`, `etapa`, `eixo_estruturante` diretamente dos cabeçalhos da tabela.
- Trade-off: ~10 códigos perdidos em páginas com estrutura atípica (138 vs 148 antes), mas **qualidade massivamente superior**.

**Fix complementar**: `routers/curriculum_import.py` agora propaga `bimestre` e `eixo_estruturante` do extractor → `CurriculumImportItem` → `CurriculumSkill` no commit.

**Re-importação concluída**: 138 habilidades de LP extraídas do DCM Floresta do Araguaia, todas com `ano` E `bimestre` preenchidos. Exemplo validado:
```
EF03LP01 | Ano: 3 | Bimestre: 1
Descrição: "Ler e escrever palavras com correspondências regulares contextuais entre grafemas e fonemas – c/qu; g/gu; r/rr; s/ss; o (e não u) e e (e não i) em sílaba átona em final de palavra – e com marcas de nasalidade (til, m, n)."
```
Distribuição balanceada: 4 anos × 4 bimestres com 1-9 habilidades cada.

### Importador de Currículo PDF → Extração → Revisão → Importação (May 2026) ✅
**Pipeline completo** para escalar ingestão de BNCC/DCM com qualidade.

**Backend**:
- `services/curriculum_extractor.py`: regex `E[FIM]\d{2}[A-Z]{2}\d{2}[A-Z]?` + pdfplumber. Deduplica por código (mantém descrição mais longa), classifica etapa por ano (1-5 iniciais, 6-9 finais), suporta códigos de faixa (EF15, EF89, etc.) marcando `ano=None` e `ano_range="15"`.
- `routers/curriculum_import.py`: 7 endpoints (upload, list, get, update item, bulk-status, commit, cancel). Todos super_admin via Matriz `nav-curriculum-button`.
- Models `CurriculumImportBatch` + `CurriculumImportItem` com status workflow: `pending → edited/approved/rejected → imported/duplicate`.
- Commit cria componente novo se necessário, verifica duplicidade em tempo real (caso outro batch tenha importado), preserva itens já imported entre re-uploads do mesmo PDF.

**Frontend** (`pages/CurriculumImport.jsx` em `/admin/curriculo/importar`):
- Card de upload (file + select componente + select fonte).
- Lista dos lotes recentes (cards clicáveis).
- Tabela revisional com: filtros por status (pending/approved/rejected/imported/duplicate/edited), busca por código/descrição, seleção múltipla, edição inline (código/descrição/ano), ações em lote (aprovar/rejeitar/reset), botão "Importar N aprovadas" (commit).
- Menu do Dashboard ganhou entrada "Importar Currículo (PDF)" com testId `nav-curriculum-import-button` (super_admin).

**Pytest** (`tests/test_curriculum_import.py`, 3/3 verde em 106s):
1. `test_full_pipeline` — upload do DCM real (148 LP) → edit item → bulk-approve 3 → commit (3 inserted, 1 component created) → re-upload marca 3 como duplicate.
2. `test_upload_rejects_non_pdf` — .txt rejeitado 400.
3. `test_commit_without_approved_returns_400` — commit sem aprovar → 400 com mensagem.

**Teste real com PDF do usuário**: `DOCUMENTO-CURRICULAR-DO-MUNICIPIO-DE-FLORESTA DO ARAGUAIA.pdf` → 148 habilidades de Língua Portuguesa extraídas. Qualidade: códigos BNCC 100% corretos, descrições capturadas (algumas com ruído de layout de colunas — revisão inline resolve).

### Sprint B parcial — Campo Habilidade BNCC/DCM em LearningObjects (May 2026)
**Componente novo** (`/app/frontend/src/components/SkillPicker.jsx`):
- Combobox multi-select com busca remota (`/api/curriculum/skills?q=...`), debounce 300ms.
- Filtro automático por `ano` da turma (extrai dígito de `grade_level`) e por `componenteCodigo` opcional.
- Chips removíveis (X) com badge da fonte (BNCC/Computação/DCM/Municipal), código + descrição, e botão `+` para inserir descrição no campo Conteúdo.
- Cache local das habilidades selecionadas para não refazer queries.
- Cobre retrocompatibilidade: registros antigos sem `skill_codigos` continuam funcionando.

**Backend**:
- `LearningObjectBase/Create/Update/Model` agora têm `skill_codigos: List[str] = []`.
- Mongo persiste array de códigos BNCC; pytest `tests/test_learning_objects_skills.py` (2/2 verde) valida CRUD + retrocompatibilidade.

**Frontend**:
- `services/api.js` ganhou `curriculumAPI` (components, skills, methods, stats, CRUD).
- `pages/LearningObjects.js` integra o `SkillPicker` ANTES do textarea Conteúdo, propaga `skill_codigos` em `formData` e nas operações de load/save/reset.

**Validação E2E (testing agent, iteration_68)**: render, busca remota debounced, dropdown, chips, contador "X selecionada", botão `+` para inserir descrição — todos OK.

### Módulo de Currículo BNCC/DCM — Sprint A (May 2026) ✅
**Catálogo curricular vivo**: SIGESC agora indexa Componentes, Habilidades (com código BNCC tipo `EF03MA02`) e Metodologias.

**Models** (`models.py`):
- `CurriculumComponent` — Língua Portuguesa, Matemática, Computação, Estudos Amazônicos (DCM Floresta do Araguaia), etc. Campo `eixo_estruturante` para os 4 eixos do DCM ("Linguagem e suas Formas Comunicativas", etc.). `etapa` ∈ infantil/anos_iniciais/anos_finais/eja/medio. `fonte` ∈ BNCC/BNCC_COMPUTACAO/DCM_FA/MUNICIPAL.
- `CurriculumSkill` — `codigo` único (ex.: EF03MA02), `descricao`, `ano` (1-9), `bimestre` (1-4 — DCM organiza por bimestre), `objeto_conhecimento`, `unidade_tematica`, `metodos_recomendados[]`.
- `CurriculumMethod` — biblioteca de metodologias reutilizáveis (Sequência didática, Resolução de problemas, etc.).

**Router** (`/api/curriculum/`):
- `GET /components`, `GET /skills?componente_id&ano&bimestre&fonte&etapa&q&limit&offset`, `GET /skills/{codigo}`, `GET /methods`, `GET /stats`.
- `POST/PUT/DELETE` em components/skills/methods restritos a super_admin via `nav-curriculum-button` (Matriz de Permissões).
- Soft-delete de componente com skills vinculadas (não destrói dados); hard-delete se vazio.
- Atualização de código de componente repropaga `componente_codigo` em skills.

**Seed** (`seeds/seed_computacao_bncc.py`):
- BNCC complementar de Computação (Resolução CNE/CP nº 1/2022) — 41 habilidades cobrindo os 3 eixos (Pensamento Computacional, Mundo Digital, Cultura Digital) × Educação Infantil + Anos Iniciais (1º-5º) + Anos Finais (6º-9º).
- 8 metodologias-base (Programação em blocos, Robótica, etc.).
- Idempotência forte via IDs determinísticos (`hashlib.sha1`) — rodar 2x não duplica.
- Executa automaticamente no startup do FastAPI (`@app.on_event("startup")`).

**Pytest** (`tests/test_curriculum_sprint_a.py`, 8/8 verde):
1. `test_stats_after_seed` — totais corretos (41 skills BNCC_COMPUTACAO).
2. `test_get_skill_by_codigo` — EF03CO01 retorna skill + componente aninhado.
3. `test_filter_skills_by_ano` — `?ano=4` retorna 4 habilidades.
4. `test_text_search` — `?q=algoritmo` encontra resultados.
5. `test_get_skill_404_unknown` — código inexistente → 404.
6. `test_component_crud_super_admin` — POST/PUT/DELETE completo.
7. `test_seed_idempotency` — segunda execução não duplica.
8. `test_skills_pagination` — limit/offset funcionam.

**Próximo (Sprint B)**: página `/admin/curriculo` (UI editável) + combobox "Habilidade BNCC" no `LearningObjects.js` que pré-preenche o conteúdo a partir do código.

### Migração Total para Inline + Atalho Alt+Enter (May 2026)
- **17 campos restantes** migrados de `SpellCheckButton` (modal) para `SpellCheckTextarea` (sublinhado inline): ActionPlans (descrição), PreMatricula (observações), StudentsComplete (8 campos), DiarioAEE atendimento (3) + templates (4).
- **Atalho Alt+Enter** dentro de palavra sublinhada aplica automaticamente a 1ª sugestão (estilo Google Docs). Implementado via `handleKeyDown` em `SpellCheckTextarea.jsx`.
- Popover de sugestões agora mostra dica visual "Alt+Enter aplica a 1ª sugestão" no rodapé.
- **Validação E2E (testing agent, iteration_67)**: Alt+Enter testado com sucesso em /avisos (typed "otimo" → Alt+Enter → "ótimo" no valor final). 4 cenários verdes, demais confirmados via código-fonte. Zero regressões.

### Corretor Ortográfico PT-BR — Sublinhado Inline (May 2026)
**Feedback do usuário**: "O erro não é destacado direto no texto, tipo sublinhada a palavra com erro."

**Solução**: novo componente `SpellCheckTextarea` (`/app/frontend/src/components/SpellCheckTextarea.jsx`) substitui o `<textarea>` nativo com técnica de **overlay espelhado**:
- Uma `<div>` absoluta atrás do textarea, com o mesmo `className` (padding, font, line-height), renderiza o texto quebrado em `<span>`s. Spans de erro recebem `underline decoration-wavy` com cores por tipo (rosa=ortografia, âmbar=gramática, azul=estilo, violeta=pontuação).
- Textarea fica visível por cima com `spellCheck={false}` (para não duplicar com o corretor nativo do browser).
- Overlay recebe `textTransform: uppercase` inline para alinhar com a regra global do SIGESC (`index.css` L107-122).
- Scroll do textarea é espelhado no overlay.
- Debounce de 800ms após cada edição; chamada a `/api/spellcheck` é abortada se o usuário continuar digitando (AbortController).
- **Popover de sugestões**: ao posicionar cursor dentro de uma palavra sublinhada (`onClick`/`onKeyUp`), abre popover com a mensagem + 4 melhores sugestões. Clique em "Aplicar" substitui o trecho e reexecuta o check.
- Badge vermelho no canto superior direito mostra contagem total de erros `[data-testid=spellcheck-indicator]`.

**Migração** (textareas nativos → SpellCheckTextarea):
- `pages/Announcements.js` — Conteúdo
- `pages/LearningObjects.js` — Conteúdo e Observações
- `components/PlanoAEEModal.js` — helper local `SpellTextField` encapsula label + SpellCheckTextarea em 11 campos livres

**Validação E2E (testing agent, iteration_66)**: 100% dos 2 cenários testados verdes. Confirmado: indicador aparece, sublinhados ondulados renderizam sob as palavras erradas com alinhamento pixel-perfect mesmo com `text-transform: uppercase`, popover abre ao clicar/posicionar cursor na palavra, sugestão é aplicada e valor final correto. `pointer-events-none` no overlay preserva 100% das interações do textarea (digitação, cursor, scroll).

**Trade-offs**:
- O componente `SpellCheckButton` (modal com lista completa) continua disponível para uso secundário onde inline não faz sentido (ex.: forms compactos, quando user quer "revisar tudo de uma vez"). Os 17 campos migrados na rodada anterior ainda usam o botão — se você quiser trocar todos para o overlay inline, é 1 rodada de search_replace.

### Corretor Ortográfico PT-BR (LanguageTool, May 2026)
**Feature**: corretor ortográfico + gramatical em português (Brasil), 100% gratuito, integrado a 3 telas de alta escrita.

**Backend** (`/app/backend/routers/spellcheck.py`):
- `POST /api/spellcheck` — proxy autenticado para `https://api.languagetool.org/v2/check`.
- Env opcional `LANGUAGETOOL_URL` permite apontar para self-host futuro sem mudar código.
- Body: `{text: str, language: "pt-BR"}`. Limites: texto ≤ 20k chars, 20 req/min por IP (limite da API pública).
- Normaliza payload: `matches: [{message, offset, length, replacements: [str], rule_id, category, issue_type, context}]`.
- Tratamento de 429/504/502 com mensagens amigáveis em PT-BR.
- Desabilita regras pedantes (`WHITESPACE_RULE`, `UPPERCASE_SENTENCE_START`) para reduzir ruído em textos escolares.

**Frontend** (`/app/frontend/src/components/SpellCheckButton.jsx`):
- Componente reutilizável com dois modos: `compact` (ícone) ou botão com label "Revisar".
- Modal lista cada sugestão com: badge do tipo (Ortografia/Gramática/Estilo), contexto com trecho em destaque, mensagem explicativa, botões "Aplicar" por sugestão, botão "Ignorar", e "Aplicar todas as principais" (1ª sugestão de cada erro).
- Após cada aplicação, re-executa o check — offsets sempre consistentes.
- Integração pronta: basta passar `text` + `onApply(newText)`.

**Integrações**:
- `pages/Announcements.js` — campo Conteúdo.
- `pages/LearningObjects.js` — Conteúdo/Objeto e Observações.
- `components/PlanoAEEModal.js` — 11 textareas (Situação Atual, Potencialidades, Dificuldades, Comunicação, Barreiras, Objetivos, Recursos, Indicadores, Orientações Sala Comum, Combinados, Adequações, Adaptações) via helper local `LabelWithSpell`.

**Pytest** (`tests/test_spellcheck.py`, 4/4 verde): detecta erros conhecidos ("vai na" → "à", "otimo" → "ótimo"), retorna vazio para texto correto, exige autenticação, rejeita texto vazio (422).

**Custo operacional**: R$ 0 até 20 req/min por IP. Se a prefeitura crescer, basta subir container LanguageTool no Coolify e apontar `LANGUAGETOOL_URL`.

### Matriz de Permissões — Camada Dinâmica no Backend (Apr 2026)
**Problema**: a Matriz (`/admin/permission-matrix`) controlava apenas a visibilidade do menu no frontend. Usuários podiam burlar a UI e chamar as APIs via curl.

**Solução**: helper `AuthMiddleware.require_permission(db, item_key, default_roles)` em `auth_middleware.py` consulta `permission_overrides` a cada requisição:
- Override `visible=True`  → libera (mesmo se papel fora dos defaults).
- Override `visible=False` → bloqueia com 403 "Acesso negado pela Matriz de Permissões".
- Sem override → fallback para `require_roles(default_roles)`.
- **`super_admin` sempre passa** (evita lock-out acidental).

**Routers migrados** (testId do Dashboard → endpoint):
- `nav-analytics-button` → `routers/analytics.py` (detail endpoints via `_require_admin_tier`)
- `nav-semed-panel-button` → `routers/pmpi.py` (Painel do Secretário)
- `nav-pmpi-engine-button` → `routers/pmpi_engine.py`
- `nav-action-plans-button` → `routers/action_plans.py`
- `nav-mec-button` → `routers/mec_integration.py` (5 rotas)
- `nav-audit-logs-button` → `routers/audit_logs.py` (5 rotas)
- `nav-online-users-button` → `routers/admin.py` (online-users, sessions/revoke)
- `nav-admin-tools-button` → `routers/admin.py` (migrate-*, cleanup-*)
- `nav-logs-button` → `routers/admin_messages.py` (4 rotas, log de conversas)
- `nav-hr-payroll-button` → `routers/hr.py` (24 rotas via replace_all)
- `nav-bolsa-familia-button` → `routers/bolsa_familia.py` (3 rotas)
- `nav-diary-dashboard-button` → `routers/diary_dashboard.py` (via `check_access`)
- `nav-mantenedora-button` → `routers/mantenedoras.py` (create/delete/designar_gerente)

**UI** (`PermissionMatrix.js`): coluna `super_admin` agora é read-only (badge verde "sempre visível") para refletir a lógica do backend e evitar confusão. Rodapé atualizado com aviso.

**Pytest suite** (`tests/test_permission_matrix_backend.py`, 4/4 passing):
1. `test_super_admin_bypasses_matrix_deny` — super_admin ignora override deny.
2. `test_default_deny_without_override_returns_403` — papel fora do default → 403.
3. `test_override_grants_access_to_non_default_role` — override True libera.
4. `test_override_denies_default_role` — override False bloqueia default-allow.

### Bug fix Apr 2026: Plano AEE criado via Modelo invisível para Professor
**Sintoma**: Professor clicava em "Novo a partir de Modelo", recebia mensagem de sucesso, mas o plano não aparecia na lista. Para super_admin aparecia normalmente.

**Causa raiz**: Em `create_plano_from_template`, quando a turma AEE do aluno (`atendimento_programa_class_id`) tinha `teacher_assignment` ativo, o código sobrescrevia `professor_aee_id` com `staff.id`. Mas o filtro `list_planos_aee` para professor compara com `current_user.id` (user.id ≠ staff.id) → plano sumia.

**Fix**:
1. `create_plano_from_template` agora resolve o **user.id** vinculado ao staff (via email match em `db.users`). Só substitui `professor_aee_id` se houver usuário linkado; caso contrário mantém `current_user.id`.
2. Filtro de professor em `list_planos_aee`, `get_diario_aee`, `get_diario_aee_pdf`, `list_estudantes_aee` agora usa `$or: [{professor_aee_id: uid}, {created_by: uid}]`. Garante visibilidade de planos antigos (criados antes do fix com staff.id) E continuará vendo planos onde foi explicitamente designado.

**Validação curl** (6 cenários):
- Cria plano via modelo: `professor_aee_id = user.id` ✅
- Lista planos: aparece (1/1) ✅
- PUT plano: 200 ✅
- Diário Consolidado: aparece ✅
- Plano histórico (`prof_aee_id=staff_id_fake`, `created_by=user.id`): visível via $or ✅

### Hot fix Apr 2026: Plano criado via Modelo continuava sumindo no UI mesmo após backend OK
**Sintoma**: backend agora retornava o plano corretamente para professor (filter $or), mas no UI a lista ainda mostrava 0 linhas após criar via Modelo.

**Causa raiz**: filtro **frontend** (`filteredPlanos` em `DiarioAEE.js`) restringe planos por `selectedTurma` (turma AEE auto-selecionada do professor). Quando o aluno escolhido no modal "Aplicar Modelo" pertencia a outra turma AEE, o plano era criado mas o `filteredPlanos` o escondia.

**Fix frontend** (`handleApplyTemplate` em `pages/DiarioAEE.js`): após sucesso da chamada `/from-template`, antes de chamar `fetchData()`, realinha `selectedTurma` para a `atendimento_programa_class_id` do aluno escolhido (ou limpa se o aluno não tem turma AEE). Garante que o novo plano apareça na lista filtrada do professor instantaneamente.

**Validação UI**: rows_before=0 → criar via UI → rows_after=1, plano "ANA OLIVEIRA - Deficiência Intelectual - Rascunho" visível imediatamente.

### P1
- Regras de cálculo de carga horária prevista na folha de pagamento (aguarda regras de negócio do usuário)
- **Módulo de Currículo (BNCC/DCM)** — Sprint A: models `CurriculumSkill`/`CurriculumMethod`/`CurriculumComponent` + router CRUD `/api/curriculum/` + seed idempotente "Computação". Sprint B: página `/admin/curriculo` + combobox "Habilidade BNCC" em `LearningObjects.js`. Sprint C: endpoint de cobertura curricular + widget dashboard coordenador.

### P2
- Carga horária fracionada em componentes curriculares
- Botão "Baixar em segundo plano" (minimizar modal) para PDFs demorados

### P3
- E-mail de confirmação na pré-matrícula
- Avaliar planilhas do Educacenso como modelo de importação oficial

## Key Files
- `/app/frontend/src/components/Layout.js` - header com TenantSwitcher à esquerda
- `/app/frontend/src/components/TenantSwitcher.jsx`
- `/app/frontend/src/components/TenantSyncBoundary.jsx`
- `/app/backend/tenant_scope.py` - RLS
- `/app/backend/routers/mantenedora.py` - endpoint da mantenedora ativa
- `/app/backend/routers/mantenedoras.py` - CRUD multi-tenant

## Credentials
Ver `/app/memory/test_credentials.md` — super_admin primário: `gutenberg@sigesc.com`


---

## 2026-02 — Currículo: Extrator Híbrido validado + Filtro por Bimestre no SkillPicker

### Validação Issue #1 (Extrator Híbrido V3)
- Rodados `pytest backend/tests/test_curriculum_import.py` (3 testes) + `test_curriculum_sprint_a.py` (8) + `test_learning_objects_skills.py` (2): **13/13 PASS**.
- PDF DCM Floresta (4.6MB, 148 habilidades LP): extração agora cobre **148/148 códigos** (138 high-confidence via tabela + 10 fallback regex), **138 com bimestre** capturado dos metadados da tabela.
- **Otimização single-pass**: `_extract_via_tables` agora coleta `extract_text()` por página dentro da mesma passagem que faz `extract_tables()`, e as Fases B (todos códigos) e C (fallback regex) reutilizam esse cache. Resultado: 101s → 36s (≈3× mais rápido).

### Issue #2 — Filtro `bimestre` no SkillPicker (P1)
**Backend** (`/app/backend/routers/curriculum.py`):
- `GET /api/curriculum/skills?bimestre=N` agora aplica filtro inclusivo: retorna habilidades do bimestre `N` **ou** sem bimestre definido (transversais/anuais como BNCC_COMPUTACAO).
- Combinação `q + bimestre` usa `$and` para evitar conflito de `$or`.
- Cobertura: `tests/test_curriculum_skills_bimestre.py` (3 testes) PASS.

**Frontend**:
- `SkillPicker.jsx` aceita prop `bimestre`. Aplica filtro automático quando o usuário **não** está pesquisando texto, com botão inline "Mostrar todos / Filtrar pelo Nº bim.".
- Cada resultado exibe badge `Nº bim.` (destacado em roxo quando casa com o bimestre da turma).
- `LearningObjects.js`: `getBimestreFromDate(selectedDate)` agora consulta primeiro `bimestrePeriods` (calendário letivo configurado pelo secretário), com fallback para janela trimestral por mês. Bimestre detectado é injetado no `<SkillPicker bimestre={...} />`.

### Backlog atualizado
- (P0) Sprint C — Cobertura Curricular: endpoint analytics + widget dashboard Coordenação.
- (P1) Sugestão "habilidades mais usadas na turma" no topo do dropdown (cache).
- (P2) Carga horária zerada folha de pagamento, botão "Baixar em segundo plano" PDFs pesados, CSV estudantes via Resend, tooltips KPI Secretário, refactor `grade_calculator.py`, `App.js` lazy-load, HttpOnly cookies.



---

## 2026-02 — Currículo v2: Arquitetura Multi-Camadas (BNCC + DCM + Municipal)

### Decisões de produto (Sprint A ajustada)
- Máx 3 habilidades por registro de aula (UX + indicadores de cobertura limpos).
- Retrocompat: `skill_codigos` coexiste com `adaptation_ids` por 30 dias + script de migração automático converte por match de código.
- Obrigatoriedade **condicional**: `adaptation_id` obrigatório apenas quando existe ≥1 adaptation para (componente + ano + bimestre). Fluxos sem base DCM permanecem em texto livre.
- Seed BNCC inicial: Computação (41) + núcleo LP/MA vindo do commit dos batches DCM (criado automaticamente na importação).

### Novos modelos normalizados (3NF)
- `bncc_skills`: núcleo nacional canônico, único por `codigo_bncc`. Sem bimestre.
- `curriculum_components`: agora com `escopo` (NACIONAL|MUNICIPAL), `mantenedora_id`, `area_conhecimento`.
- `curriculum_adaptations`: FK → bncc_skills + FK → component + `ano/bimestre/ordem` + `codigo_local` + `descricao_local`. Unique composto `(mantenedora_id, component_id, bncc_skill_id, codigo_local, ano, bimestre)`.
- `curriculum_adaptation_methods`: 1:N com adaptation.
- `learning_objects.adaptation_ids[]` (máx 3) + campos novos `evidencia_aprendizagem` + `pratica_pedagogica`.

### Backend entregue
- `/app/backend/services/curriculum_v2_migration.py` — migração idempotente (índices, backfill escopo em components, BNCC_COMPUTACAO → bncc_skills + adaptations, skill_codigos → adaptation_ids em learning_objects).
- `/app/backend/routers/curriculum_v2.py` — endpoints: `/bncc`, `/adaptations` (catálogo flattened), `/adaptations/{id}` (joined BNCC+methods), `/adaptations/availability` (obrigatoriedade condicional), `POST /v2/migrate`, `/coverage`.
- `/app/backend/routers/curriculum_import.py` — commit reescrito: cria `bncc_skills` (quando código BNCC), cria `curriculum_adaptations` (upsert por slot único), mantém `curriculum_skills` legado 30d.
- `LearningObjectCreate` com validator: máximo de 3 `adaptation_ids`.

### Frontend entregue
- `SkillPicker.jsx` (v2): consome `/api/curriculum/adaptations`, emite `adaptation_ids`, limite de 3 com aviso, badge de bimestre destacado quando bate com o bimestre corrente da turma.
- `LearningObjects.js`: `adaptation_ids` no formData, inferência de `componente_codigo` a partir do nome do curso selecionado, bimestre via `bimestrePeriods` do calendário letivo.
- `api.js`: `curriculumAPI.{bncc, adaptations, adaptationById, adaptationAvailability, createAdaptation, updateAdaptation, deleteAdaptation, runMigration, coverage}`.

### Cobertura de testes (25 PASS)
- `tests/test_curriculum_v2.py` (6): migração idempotente, listar BNCC, listar adaptations flattened, detalhe com join, availability condicional.
- `tests/test_learning_objects_v2.py` (3): criação com adaptation_ids, rejeição 422 para >3, coverage reportando adaptations usadas.
- `tests/test_curriculum_import.py` (3): pipeline PDF→extract→review→commit agora grava em bncc+adaptations+legacy.
- Outros já existentes seguem PASS (19): sprint_a (8), skills_bimestre (3), learning_objects_skills (2), curriculum_import cleanup.

### Próximos passos
- (P0) Script one-shot de migração manual para `adaptation_ids` em massa (rodar em produção com relatório CSV de conversões/faltas).
- (P0) UI `/admin/curriculo` refatorada para CRUD direto de `adaptations` (componentes + filtros mantenedora + ano + bimestre).
- (P0) Widget dashboard Coordenação com `/api/curriculum/coverage` — barras % concluído por componente/ano/bimestre + drill-down em pendências.
- (P1) Cards de "habilidades mais usadas na turma" no topo do SkillPicker (cache em `learning_objects`).
- (P1) Conditional required no handleSave: chamar `/availability` antes de salvar para exibir aviso.




---

## 2026-02 — Sprint B v2: CRUD Adaptações + Validação + Widget Cobertura

### Ordem entregue (conforme diretriz final)
1. 🔴 **UI `/admin/curriculo/adaptacoes`** — CRUD completo
2. 🔴 **Validação obrigatória condicional** — bloqueia salvar sem `adaptation_id` quando há base
3. 🔴 **Widget Cobertura** — thresholds 90/70 + forecasting por ritmo semanal

### UI Adaptações (CurriculumAdaptations.jsx)
- Filtros sticky (Componente/Ano/Bimestre/Busca), tabela paginada 30/pg, modal edição com auto-fill BNCC informativo + campos editáveis, ação Sincronizar BNCC (`/v2/migrate`), integração com importador PDF.
- Delete inteligente: soft-delete se adaptation em uso por `learning_objects`; hard delete caso contrário.

### Validação Obrigatória (LearningObjects.js)
- `handleSave` chama `/api/curriculum/adaptations/availability` antes de submeter quando `adaptation_ids=[]`. Se `required=true` → bloqueia com alerta informativo direcionando à seleção.
- Inferência automática do `componente_codigo` por nome do curso.

### Widget Cobertura (`/admin/curriculo/cobertura`)
**Thresholds ajustados**: ≥90% verde · 70-89% âmbar · <70% vermelho · futuro cinza sem %.
**Forecasting por ritmo semanal (backend)**: projeção linear `pct × total_days/elapsed_days` → No ritmo / Em risco / Não cumpre. Bimestre fechado <90% → Fechado crítico.
**Banner de alerta**: "⚠️ Cobertura crítica detectada: intervenção necessária" quando `closed_critical>0` ou `critical_rows>0`.
**Drill-down**: cada bimestre expande lista de pendências.
**Backend**: `GET /api/curriculum/coverage?academic_year&class_id&component_id` retorna `{totals, rows, bimestre_windows}`.

### Cobertura de testes (26 PASS)
- `tests/test_curriculum_coverage.py` — seed sintético com b1 fechado 10%, b2 em andamento 70%, b3 futuro; valida status e forecast.
- 25 testes anteriores permanecem PASS (import pipeline, v2 CRUD, availability, learning_objects v2, sprint_a, skills bimestre).

### Navegação (Dashboard.js)
Em "Gestão Institucional":
- "Adaptações Curriculares" (super_admin + coordenador)
- "Cobertura Curricular" (super_admin + admin + coordenador + diretor + secretário)

### Próximos passos
- (P1) Cards "habilidades mais usadas na turma" no topo do SkillPicker (cache em aggregation pipeline).
- (P2) Relatório CSV de migração skill_codigos → adaptation_ids para ops.
- (P2) Deprecação oficial de `skill_codigos` após 30 dias.
- (P3) Extração BNCC nacional completa via CSV oficial MEC.


---

## 2026-02 — Sprint C: Feed de Intervenções Necessárias (gestão ativa)

### Diretriz do usuário
"O sistema deixa de ser painel e vira mecanismo de gestão ativa. Controle > estética."

### Arquitetura (híbrido in-app + e-mail, fallback automático)
- **Collection `intervention_alerts`**: um alerta por (school_id, class_id, component_id, ano, bimestre). Campos: `status` (em_risco|nao_cumpre|fechado_critico), `escalation_level` (1|2|3), `first_detected_at`, `last_notified_at`, `last_coverage_pct`, `resolved_at`.
- **Collection `intervention_notifications`**: inbox in-app por usuário, com `link` profundo para o slot em `/admin/curriculo/cobertura?class_id&component&ano&bim`.
- **Detecção semanal**: APScheduler `CronTrigger(day_of_week='mon', hour=7, minute=0, timezone='UTC')` roda `services/intervention_detector.py`.
- **Gatilho**: `status == em_risco || nao_cumpre || (bim fechado && <90%)`.
- **Escalonamento por tempo sem resolver**: 0–1 sem → Nível 1 (coord) · 2–3 sem → Nível 2 (diretor + coord) · ≥4 sem → Nível 3 (secretaria + diretor + coord).
- **Anti-spam**: novo e-mail/in-app só dispara se `last_notified_at > 7 dias`.
- **Fallback automático**: sem `RESEND_API_KEY` → in-app sozinho + warning log. Sistema NÃO trava por dependência externa.
- **Auto-resolução**: se cobertura ≥ 90% na próxima rodada, alerta é marcado como `resolved_at` automaticamente (e sai do feed).

### Backend entregue
- `/app/backend/services/intervention_detector.py` — detecção por turma, upsert idempotente, cálculo de escalonamento, envio híbrido.
- `/app/backend/routers/interventions.py` — endpoints:
  - `GET  /api/intervencoes` — feed ordenado por severidade+antiguidade (escopo por escola se não super_admin)
  - `GET  /api/intervencoes/notifications` — inbox do usuário + contador `unread`
  - `POST /api/intervencoes/notifications/{id}/read` + `/read-all`
  - `POST /api/intervencoes/{id}/resolve` — resolve manual
  - `POST /api/intervencoes/run-detection` — trigger manual (admin/debug)
- Scheduler inicializado no setup_router (singleton).

### Frontend entregue
- **Página `/admin/intervencoes`**: resumo (ativas/críticas/nível 3), lista com badge de status, nível de escalonamento (Coord→Direção→Secretaria), semanas sem resolver, botões "Resolver agora" (link direto com query params) + "✓" (marcar resolvido).
- **Dashboard**: novo item "Intervenções Necessárias" (ícone Siren vermelho) visível para super_admin/admin/coord/diretor/secretário.

### E-mail (Resend)
- Template HTML com assunto "⚠️ Intervenção necessária — Cobertura curricular em risco", corpo curto (Turma + Componente + Bimestre + Status + % cobertura + Previsão), CTA "Resolver agora" com link direto.
- Disparo somente se `RESEND_API_KEY` E `RESEND_SENDER_EMAIL` configurados.

### Testes (3 PASS em `test_interventions.py`)
1. `run-detection` cria alertas `nao_cumpre` com pct=0 e nível 1 — PASS.
2. Idempotência: 2ª rodada não duplica — PASS.
3. Resolve manual: alerta sai do feed ativo, aparece em `include_resolved=true` — PASS.

### E2E manual
- POST `/run-detection` criou 60 alertas para dados reais do sistema.
- Página `/admin/intervencoes` renderiza com resumo 66/66, cards de escalonamento, botão "Resolver agora" linkando ao slot em Cobertura.

### Próximos passos (Sprint D se solicitado)
- 🟠 (P1) Bell icon no header exibindo `/notifications` com badge de unread.
- 🟠 (P1) Plano de ação automático por escola (gerado a partir dos alertas) — fecha ciclo detectar → alertar → orientar → cobrar → medir.
- 🟠 (P1) Ranking de gestores por taxa de resolução (accountability real).
- ⚪ (P2) Cards "habilidades mais usadas na turma" no topo do SkillPicker (UX).
- ⚪ (P3) Deprecação oficial de `skill_codigos` após 30 dias.



---

## 2026-02 — Sprint D: Ranking de Gestão Curricular (accountability real)

### Diretriz do usuário
"Você está criando transparência de desempenho dentro da rede. Se fizer certo, vira ferramenta de gestão oficial."

### Mitigação política aplicada
- **Escopo por papel**: `super_admin/admin/secretario` veem ranking completo. `diretor/coordenador` veem apenas a própria escola (`self`), nunca comparação com pares.
- **Contexto obrigatório exibido**: nº de turmas da escola, nº de alertas recebidos, taxa de resolução ponderada, nível crítico 3 destacado. Evita leitura sem contexto.
- **Transparência do score**: tooltip/legenda oficial explica fórmula e que o ranking considera apenas alertas reais gerados pelo sistema (não subjetividade).

### Score (0–100)
```
score = max(0, min(100,
    max(0, min(100, 100 - avg_resolution_days * 5)) * 0.5
    + resolution_rate * 100 * 0.4
    - active_alerts * 2
))
```

### Peso por nível de escalonamento
`LEVEL_WEIGHT = {1: 1, 2: 2, 3: 3}` — um alerta Nível 3 (secretaria) pesa 3× mais que um Nível 1 (coord) no cálculo de taxa. Evita gestores "esconderem" problemas graves.

### Métricas por escola
- `received` / `resolved` / `active` (recebidos, resolvidos, pendentes)
- `resolution_rate` (% ponderada por nível)
- `avg_resolution_days` (tempo médio entre first_detected_at e resolved_at)
- `critical_level_3` (backlog Nível 3)
- `weighted_score` + `rank`

### Backend (`/app/backend/routers/interventions.py`)
- `GET /api/intervencoes/ranking?period=(7d|30d|60d|90d|all)&only_mine=bool`
- Agrega intervention_alerts por `school_id`, resolve `school.name` + coordenador ativo vinculado.
- Auto-escopo: roles não-admin recebem apenas `self`, `rows=[]`, `full_access=false`.

### Frontend (`/admin/ranking-gestores`)
- Filtro de período (7/30/60/90/todo).
- Cartão "Seu desempenho" para gestor (role limitado).
- Tabela com medalha 🥇🥈🥉 para top 3, fundo vermelho suave para últimos 3 (quando >5 escolas).
- Colunas: #, Escola, Gestor, Turmas, Alertas, Taxa, Tempo médio, Pendentes (com N3 destacado), Score.
- Legenda oficial explicando fórmula.

### Testes (2 PASS em `test_ranking_gestores.py`, 28 total no suite v2+C+D)
1. Ordenação descendente por score: Escola A (5/5 resolvidos, 2d médio) ranqueia acima de Escola B (1/6 resolvidos + 5 ativos + 2 N3) — PASS.
2. Período `all` engloba alertas antigos — PASS.

### Impacto estratégico desbloqueado
- Base para bônus por desempenho (KPI oficial defensável).
- Identificação automática de escolas críticas (últimos 3 vermelhos).
- Relatórios oficiais de gestão pedagógica.
- Intervenção automática mais agressiva (nos baixos scores).

### Próximos passos (Sprint E opcional)
- 🟠 (P1) Plano de ação automático por escola: usando ranking + pendências, gerar checklist priorizado para a escola com menor score.
- 🟠 (P1) Bell icon no header com badge de unread (`/intervencoes/notifications`).
- ⚪ (P2) Exportar ranking em CSV/PDF para reuniões da SEMED.
- ⚪ (P2) Gráfico de evolução mensal do score (linha temporal por escola).



---

## 2026-02 — Sprint E: Plano de Ação Automático (orientação operacional)

### Objetivo (diretriz do usuário)
"Hoje você detecta e cobra, agora precisa **orientar com precisão operacional**. Sem isso, o gestor sabe que está mal, mas não sabe o que fazer primeiro."

### Fecha o ciclo: detectar → alertar → **orientar** → cobrar → medir

### Motor determinístico (regras fixas, não-IA)
5 regras em ordem de prioridade:

| # | Trigger | Ação | Prio | Prazo | Responsável |
|---|---------|------|------|-------|-------------|
| 1 | `coverage_pct < 70%` | Regularizar habilidades pendentes (top 5 da componente pior) | 1 | 7d | coordenador |
| 2 | `level_3_active >= 3` | Intervenção imediata nas turmas críticas | 1 | 3d | diretor |
| 3 | `lancamento_rate < 0.7` | Cobrar regularização de lançamentos no diário | 2 | 5d | coordenador |
| 4 | `resolution_rate < 0.6` (com ≥3 recebidos) | Revisar fluxo de resposta a alertas | 3 | 14d | coordenador |
| 5 | `avg_resolution_days > 5` | Implantar rotina semanal de acompanhamento | 3 | 14d | diretor |

**Limite**: máx. 5 ações. **Ordem**: (prioridade, impacto alto→medio→baixo).

### Estrutura de cada ação
- `ordem`, `prioridade`, `categoria`, `titulo`, `descricao` (com números concretos), `impacto`, `prazo_dias`, `responsavel`, `metrica_sucesso`, `link` (1 clique → ação no sistema).

### Backend (`/app/backend/routers/interventions.py`)
- `GET /api/intervencoes/plano-acao?school_id=&period=(7d|30d|60d|90d|all)`
- Reaproveita dados de: `intervention_alerts`, `curriculum_adaptations`, `learning_objects`.
- Contexto completo retornado: score, classificação (Adequado/Atenção/Crítico), métricas crus.
- Escopo: super_admin/admin/secretario → qualquer escola. Diretor/coord → apenas sua(s) escola(s).

### Frontend (`/admin/plano-acao`)
- Dropdown de escola + filtro de período.
- Header colorido com nome da escola + contexto (cobertura / alertas / N3 / tempo médio / lançamentos) + score grande.
- Cards de ação com prioridade numerada (#1, #2...), badge de impacto, ícone de prazo, responsável, título, descrição operacional com **números reais**, métrica de sucesso destacada, botão "Agir agora" (link direto).
- Estado vazio: badge verde "Nenhuma ação recomendada".
- Legenda com as 5 regras determinísticas.

### Testes (4 PASS em `test_plano_acao.py`, 32 PASS no eixo v2+C+D+E)
1. Plano gera múltiplas categorias (cobertura + N3 + lançamentos).
2. Ação de cobertura tem link para `/admin/curriculo/cobertura` e métrica.
3. Ação de N3 é urgente (prazo ≤3 dias, impacto alto, responsável=diretor).
4. Contexto retornado tem level_3_active=4, received=5, coverage_pct=0, score<60.

### Navegação (Dashboard → Gestão Institucional)
Novo item "Plano de Ação" (ícone Zap amber) para super_admin/admin/secretario/diretor/coordenador.

### Ciclo completo entregue
```
1. /admin/curriculo/cobertura   — diagnóstico
2. /admin/intervencoes          — alertas com escalonamento
3. /admin/plano-acao            — orientação operacional (NOVO)
4. /admin/ranking-gestores      — accountability mensurável
```

### Próximos passos (quando quiser continuar)
- 🟠 (P1) Bell icon no header com badge de unread (`/intervencoes/notifications`).
- 🟠 (P2) Evolução mensal do score por escola (gráfico linha).
- 🟠 (P2) Exportar plano de ação em PDF para reuniões pedagógicas.
- ⚪ (P3) IA gerando descrição adaptativa por histórico (evolução do motor de regras).



---

## 2026-02 — Sprint F: Multi-Tenant Toolkit (auditoria + branding + onboarding)

### Diretriz do usuário
"Vamos blindar as lacunas. SIGESC é multi-tenant — uma só plataforma para N municípios."

### Confirmação de arquitetura
- A infraestrutura `tenant_scope.py` (filtros automáticos `apply_tenant_filter`) **já existia** e é usada nas rotas de currículo, intervenções, action_plans, students, users, etc.
- Sprint F entrega **transparência operacional sobre as lacunas** + **onboarding rápido** + **branding por mantenedora**.

### Backend novo (`/app/backend/routers/tenant_admin.py`)

**Auditoria** — `GET /api/tenant/audit?sample_size=N`
- Mapeia cada coleção crítica (17): `total`, `with_tenant`, `without_tenant`, `coverage_pct`, `sample`, `parent_for_backfill`.
- Resultado real do sistema: schools/classes/courses/students/staff/enrollments/grades/learning_objects/calendar_events/etc → **100% cobertos**.
- Lacunas legítimas: `intervention_alerts` (cross-tenant para BNCC nacional), `curriculum_adaptations` (BNCC_COMPUTACAO), `curriculum_components` (NACIONAL).

**Backfill** — `POST /api/tenant/audit/backfill?dry_run=bool`
- Deriva `mantenedora_id` automaticamente a partir do parent (`school_id` ou `class_id`).
- Modo seguro com `dry_run=true` (padrão): apenas conta o que seria atualizado.
- Modo escrita explícito (`dry_run=false`): aplica e retorna contagem.

**Branding público** — `GET /api/tenant/branding/public?mantenedora_id=&host=`
- Endpoint **sem autenticação** (consumido pelo login screen).
- Resolução: por `mantenedora_id` → por `host`/subdomain (codigo_inep/slug) → primeira mantenedora → fallback default.
- Retorna: `name`, `logo_url`, `brasao_url`, `primary_color`, `secondary_color`, `secretaria`, `slogan`, `exibir_pre_matricula`, `destaque_mensagem`.

**Onboarding wizard** — `POST /api/tenant/onboard`
- Cria nova mantenedora completa em 1 chamada: mantenedora + admin local (role=gerente) + escola inicial opcional.
- Senha temporária `Mudar@2026` com `must_change_password=true`.
- Validação de e-mail único.

### Frontend (`/admin/tenant`)

Página dedicada para super_admin:
- **Banner de status**: amarelo se há órfãos, verde se 100% íntegro.
- **Tabela de auditoria**: coleção por coleção, com barra de progresso colorida (verde/amarelo/vermelho), órfãos destacados, parent disponível para backfill.
- **Botão "Rodar backfill"**: aplica derivação automática de mantenedora_id (com confirmação).
- **Botão "Nova Mantenedora"**: modal wizard com nome + CNPJ + município/estado + cor primária (color picker) + URL logotipo + admin (nome+email) + escola inicial opcional. Mostra senha temporária no toast de sucesso.

### Testes (6 PASS em `test_tenant_admin.py`, 38 PASS no eixo total)
1. Branding público responde sem auth.
2. Audit lista coleções esperadas.
3. Audit protegido (401 sem token).
4. Backfill dry_run não escreve.
5. Onboard cria mantenedora + admin + escola completos.
6. Onboard rejeita e-mail duplicado (409).

### Navegação
Dashboard → Gestão Institucional → "Multi-Tenant" (ícone ShieldCheck verde, super_admin only).

### Status pós-Sprint F
- Schools/classes/courses/students/staff/enrollments/grades/learning_objects: **100% blindados** ✅
- BNCC nacional permanece intencionalmente cross-tenant (compartilhada por todas as redes) ✅
- Onboarding de nova mantenedora: **5 cliques / <2 minutos** ✅
- Branding por mantenedora: dados disponíveis via endpoint público ✅

### Próximos passos (quando quiser)
- 🟠 (P1) Aplicar `branding/public` no LoginScreen (logo + cor + nome dinâmicos).
- 🟠 (P2) Whitelabel completo no header da aplicação (logo no topo, tema CSS vars).
- 🟠 (P2) Bell icon com `/intervencoes/notifications` no header.
- ⚪ (P3) Convite Resend automático para o admin local recém-criado.
- ⚪ (P3) Export LGPD por mantenedora (direito ao esquecimento + portabilidade).



---

## Sprint F final — Branding por domínio (Multi-Tenant) [03/Fev/2026]

- Endpoint `GET /api/tenant/branding/public` resolve o tenant via `Request.headers.host` (sem query param — evita domain spoofing e garante cache HTTP correto).
- CRUD de `tenant_domains` (super_admin only) em `/api/tenant/domains`.
- Hook `useTenantBranding.js` consome o endpoint automaticamente a partir do host atual.
- `Login.js` refatorado para aplicar logo + cores via CSS variables dinamicamente.
- Quando o domínio não está mapeado, fallback para branding padrão SIGESC.
- Status: ✅ Concluído, validado (screenshot), 40/40 testes legados + 7 novos passando.

## Fase 2 — Planos de Ação enriquecidos por IA (Claude Sonnet 4.5) [03/Fev/2026]

### Objetivo
Complementar o motor determinístico de 5 regras fixas com uma camada de IA que:
- Gera **análise executiva** contextual em linguagem natural.
- Produz **insight histórico do gestor** baseado nos últimos 90 dias de alertas (taxa de resolução, tempo médio, categoria mais negligenciada).
- Sugere até 2 **recomendações extras** não cobertas pelas regras.
- Enriquece cada ação determinística com uma **descrição mais humana**.

### Implementação
- **Backend**: `services/plano_acao_ai.py` usando `emergentintegrations` + `EMERGENT_LLM_KEY` + `anthropic/claude-sonnet-4-5-20250929`.
- **System prompt** pedagógico (contexto BNCC/DCM, escopo operacional, 1-clique para ação).
- **Output JSON puro** validado e sanitizado (limits de string, cap de extras em 2).
- **Cache 24h** em coleção `ai_plans` por `(mantenedora_id, school_id, period)`.
- **Graceful fallback**: sem chave / timeout / parse fail → endpoint retorna plano determinístico normalmente, `ai_enriched=false`.
- **Endpoint**: `GET /api/intervencoes/plano-acao?ai=true&force_refresh=true`.
- **Frontend** (`PlanoAcao.jsx`): toggle "IA ligada/desligada", card de análise executiva (gradient indigo), bloco de histórico do gestor, cards de recomendações extras com badge "IA", descrição enriquecida (+ details/summary para a descrição técnica original), botão "Regenerar IA".

### Testes
- `backend/tests/test_plano_acao_ai.py` com 8 cenários, 100% pass:
  1. Fallback sem EMERGENT_LLM_KEY.
  2. Enriquecimento OK com mock.
  3. Cache de 24h (segunda chamada não chama Claude).
  4. `force_refresh=true` bypassa cache.
  5. Validação / cap de extras em 2.
  6. Parse de JSON embrulhado em markdown.
  7. Endpoint default mantém retrocompat.
  8. Endpoint com `ai=true` real usando EMERGENT_LLM_KEY (smoke test E2E).
- Validação visual: screenshot exibe análise executiva, histórico de 90d, 5 ações com badges "IA".

### Status
✅ Concluído, 25/25 testes passando (17 legados + 8 novos), sem regressão.

### Próximos passos (backlog atualizado)
- 🟡 (P2) Selo de Conclusão Curricular em PDF — adiado pelo usuário até gestão ativa virar rotina.
- 🟡 (P2) Refatoração `grade_calculator.py` (dívida técnica).
- ⚪ (P3) CSV de importação com convites automáticos via Resend.
- ⚪ (P3) Isolamento de auth (HttpOnly cookies).
- ⚪ (P3) Tooltips explicativos nos KPIs do Secretário.
- ⚪ (P3) Botão "Baixar em segundo plano" para PDFs pesados.

---

## Sprint G2 — HttpOnly Cookies + CSRF + Session Rotation [03/Fev/2026]

### Objetivo
Migrar autenticação de `localStorage + Authorization: Bearer` (vulnerável a XSS) para **HttpOnly cookies** com CSRF protection via double-submit pattern + rotação de refresh token a cada uso.

### Implementação

**Backend**
- `auth_utils.py` — helpers:
  - `set_auth_cookies(response, access, refresh, csrf)` — seta os 3 cookies
  - `clear_auth_cookies(response)` — clear em logout
  - `generate_csrf_token()` — `secrets.token_urlsafe(32)`
  - Cookies: `sigesc_access` (HttpOnly, 15min, path=/), `sigesc_refresh` (HttpOnly, 7d, path=/api/auth), `sigesc_csrf` (não-HttpOnly, 15min, path=/)
  - Flags: `Secure=True` + `SameSite=Lax` por padrão
- `auth_middleware.py` — `get_current_user`: ordem de leitura `cookie → Bearer → query ?token=`
- `routers/auth.py`:
  - `/login` seta cookies + retorna tokens no body (retrocompat)
  - `/refresh` lê de cookie OU body + **rotaciona jti** (revoga antigo ao emitir novo)
  - `/logout` lê refresh do cookie + clear cookies + blacklist
  - `GET /auth/csrf-token` (novo) emite novo CSRF sem invalidar sessão
- `server.py` — `CSRFMiddleware`:
  - Só valida POST/PUT/PATCH/DELETE em `/api/*`
  - **Só exige CSRF quando auth vem por cookie** (Bearer não é vulnerável a CSRF)
  - Pula endpoints públicos: `/login`, `/register`, `/refresh`, `/forgot-password`, `/reset-password`, `/confirm-email-change`, `/resend-email-change`, `/tenant/branding/public`, `/pre-matricula`
  - Double-submit: `X-CSRF-Token` header == `sigesc_csrf` cookie

**Frontend** (`services/api.js`)
- `axios.defaults.withCredentials = true` (cookies em todas requests)
- Interceptor lê `sigesc_csrf` cookie e injeta `X-CSRF-Token` em POST/PUT/PATCH/DELETE
- Bearer continua sendo enviado (retrocompat — backend dá prioridade ao cookie)

### Testes (`tests/test_auth_cookies.py`) — 9/9 pass
1. Login seta 3 cookies com flags corretas (HttpOnly, Secure, SameSite=Lax)
2. `GET /me` funciona só com cookie (sem Bearer)
3. Retrocompat: `GET /me` continua OK com Bearer header
4. Refresh rotaciona: refresh token antigo vira 401 após 1º uso
5. CSRF bloqueia POST de escrita sem header quando auth via cookie
6. CSRF libera com header correto
7. CSRF não é exigido se auth vem via Bearer
8. Logout limpa cookies e invalida tokens
9. `GET /auth/csrf-token` rotaciona o cookie CSRF

### Validação E2E
- Screenshot do browser: cookies visíveis com flags corretas (`sigesc_access: httpOnly=True, secure=True, sameSite=Lax`)
- Dashboard e PlanoAcao funcionando normalmente após migração
- **Regressão: 34/34 testes passando** (17 legados + 8 IA + 9 cookies)

### Segurança — ganhos concretos
- ✅ Access token imune a XSS (não acessível via JS)
- ✅ Refresh token escopado a `/api/auth/*` (mínima superfície)
- ✅ CSRF double-submit em rotas mutadoras
- ✅ Refresh token rotation (detecção de reuso = compromisso)
- ✅ Secure=True garante cookie só via HTTPS
- ✅ SameSite=Lax mitiga CSRF cross-site

### Próximas evoluções (backlog)
- (P2) Remover suporte a Bearer header após período de transição (2-3 semanas)
- (P3) Idle timeout: auto-refresh do access token antes de expirar via interceptor 401 → `/refresh` → retry
- (P3) Alerta visual quando CSRF falhar (mostrar que sessão precisa ser renovada)


---

## Sprint G1 — Explainability IA + Cache Invalidation Reativa [03/Fev/2026]

### Problema resolvido
Fase 2 entregava análises fortes ("abandono operacional — não há gestor ativo") sem transparência sobre quais dados embasaram a inferência. Risco de "caixa preta opinativa" com consequências políticas em secretarias.

### Implementação

**Backend — `services/plano_acao_ai.py`**
- System prompt reescrito: Claude agora é **obrigado** a produzir campos paralelos de evidências para cada afirmação forte.
- Schema enriquecido:
  - `analise_evidencias: [{metrica, valor, fonte}]` (2-4 itens)
  - `insight_evidencias: [{metrica, valor, fonte}]` (1-3 itens)
  - `recomendacoes_extra[].baseado_em: [{metrica, valor, fonte}]` (1+ item)
- `_sanitize_evidencias()` — valida, trunca strings, remove entradas sem `metrica` ou `valor`.
- `invalidate_ai_plans_for_school(db, school_id)` — nova função para invalidação reativa do cache.

**Cache Invalidation Reativa**
- `POST /api/intervencoes/{alert_id}/resolve` → invalida cache IA da escola após resolver
- `services/intervention_detector.run_intervention_detection()` → coleta `touched_schools` (novo alert OU mudança de nível de escalonamento) e invalida o cache dessas escolas no final.
- Evita o pior cenário: IA gerar análise defasada de 24h enquanto o operacional já mudou.

**Frontend (`PlanoAcao.jsx`)**
- Novo componente `<EvidenceList>` — pills com formato `metrica: valor` em fundo branco com borda indigo.
- Renderiza `analise_evidencias` abaixo da análise executiva.
- Renderiza `insight_evidencias` abaixo do insight histórico.
- Renderiza `baseado_em` em cada recomendação extra da IA.
- Tooltip com `fonte` (caminho literal do payload) no hover de cada pill.

### Testes (`tests/test_plano_acao_evidencias.py`) — 6/6 pass
1. Sanitização filtra entradas inválidas (vazias, tipo errado, sem valor).
2. `max_items` é respeitado no corte do array.
3. Resposta IA enriquecida contém `analise_evidencias`, `insight_evidencias`, `baseado_em`.
4. `invalidate_ai_plans_for_school` remove docs apenas da escola alvo.
5. Endpoint `/resolve` dispara invalidação de cache da escola.
6. Endpoint `/plano-acao?ai=true` retorna schema com arrays de evidências.

### Regressão completa — 40/40 testes passando
- 17 legados + 8 IA + 9 cookies + 6 evidências.

### Validação E2E (screenshot)
Na tela real, a Claude gerou:
- Análise: "A escola registra paralisia operacional total: 66 alertas recebidos nos últimos 30 dias, zero resolvidos, 0% de cobertura curricular e 0% de lançamentos no diário..."
- Pills: "Alertas ativos: 66 · Taxa de resolução: 0.0 · Cobertura curricular: 0.0% · Taxa de lançamentos: 0.0"
- Insight: "...Componente mais negligenciado: CO"

**Cada afirmação agora é auditável.** Se o gestor duvidar de um número, basta bater o olho no pill que referencia a fonte exata no payload.

### Status: ✅ PRODUÇÃO-READY
Base consolidada para Sprint G3 (Relatório Executivo Mensal) — o prompt agora gera output rastreável que pode ser enviado por e-mail para Secretários sem risco reputacional.


---

## Sprint G1.5 — Snapshot + Integridade + Modo Auditor [03/Fev/2026]

### Problema resolvido
G1 entregou **evidência auditável** (rastreabilidade do payload). Faltava **prova defensável**: congelamento imutável dos dados no momento da análise + integridade criptográfica. Sem isso, um relatório de abril poderia "mudar" em maio conforme o estado do sistema evoluísse. Inaceitável para uso institucional (Tribunal de Contas, Conselho Municipal, secretaria).

### Implementação

**Backend — `services/snapshot_service.py`**
- Schema `ai_analysis_snapshots`: `{id, version, mantenedora_id, entity_type, entity_id, analysis_type, payload_snapshot, ai_output, model, public_hash, server_signature, created_at, expires_at, created_by, retention_policy}`
- **Hash público SHA256**: JSON canônico determinístico (sort_keys=True, ensure_ascii=False) sobre payload + output + timestamp + model + version → qualquer alteração invalida.
- **Assinatura HMAC-SHA256**: com `SNAPSHOT_HMAC_SECRET` (gerado automaticamente no .env) → prova de origem, impede forjar snapshots externamente.
- **Retenção configurável por mantenedora**: default 5 anos, mínimo 2 anos (LGPD), opção "forever" opt-in. Index TTL no Mongo (`expires_at_dt`).
- **Access control por scope**:
  - `super_admin` → global
  - `admin/gerente/secretario` → sua mantenedora
  - `diretor` → apenas snapshots de suas escolas
  - `professor/aluno/coordenador` → 403

**Backend — `services/snapshot_pdf.py`**
- Gera PDFs institucionais via `reportlab`:
  - **Executivo**: resumo + análise + evidências (inline) + ações + selo de integridade (hash + HMAC + URL de verificação + timestamp + modelo + versão + criado por)
  - **Auditor**: tudo acima + tabelas completas de evidências em cada recomendação + **Anexo A** com payload_snapshot em JSON canônico para reprodutibilidade externa do hash
- Header institucional SIGESC, paleta indigo (aligned com app theme)

**Backend — `routers/snapshots.py`**
- `GET /api/snapshots` — lista com escopo aplicado por role
- `GET /api/snapshots/{id}` — detalhes completos
- `GET /api/snapshots/{id}/verify` — retorna `{valid, hash_valid, signature_valid, public_hash, recomputed_hash, server_signature, recomputed_signature, model, version, created_at, snapshot_id, entity_id}` — endpoint forense
- `GET /api/snapshots/{id}/pdf?mode=executive|auditor` — binário PDF
- `GET /api/snapshots/retention-policy` — política vigente
- `PUT /api/snapshots/retention-policy` — super_admin/admin altera

**Integração automática**
- `enrich_plan_with_ai` agora aceita `user` e **sempre cria snapshot** após validação da resposta IA, antes de persistir o cache. Resposta do endpoint `/plano-acao?ai=true` inclui `snapshot_id`, `public_hash`, `server_signature`.

**Frontend — `PlanoAcao.jsx`**
- Botão **"🔒 Modo Auditor"** (só visível para roles autorizados: super_admin/admin/admin_teste/gerente/secretario/diretor)
- Modal auditor com:
  - Snapshot atual (ID + hash público + HMAC) em monospace
  - Verificação automática ao abrir → banner verde (Documento íntegro) ou vermelho (comprometido) com hash_valid/signature_valid explícitos
  - Botões **"PDF Executivo"** e **"PDF Auditor (completo)"** com download direto
  - **Histórico de snapshots** (até 10 últimos) com badge "ATUAL" no atual
  - Explicação de como validar externamente + referência ao endpoint `/verify`

### Testes (`tests/test_snapshots.py`) — 17/17 pass
1. Hash determinístico (mesmo input → mesmo hash)
2. Hash muda com qualquer alteração (payload, output, timestamp)
3. HMAC computa corretamente com secret dado
4. HMAC retorna None quando secret ausente
5. `verify_snapshot_integrity` detecta tampering (payload alterado ou secret diferente)
6. `create_snapshot` persiste doc com TTL default (5 anos)
7. `get_scope_for_user` bloqueia professor/aluno
8. `get_scope_for_user` escopa diretor em suas escolas
9. `get_scope_for_user` escopa secretario em sua mantenedora
10. `get_scope_for_user` retorna {} (global) para super_admin
11. `set_retention_policy` rejeita custom < 2 anos
12. `set_retention_policy` aceita "forever"
13. Endpoint `/snapshots` lista para super_admin sem escopo
14. Endpoint `/verify` retorna schema rico com todos os campos
15. Endpoint `/pdf` gera PDF válido (executive < auditor em tamanho)
16. Endpoint `/snapshots` bloqueia professor (403)
17. `enrich_plan_with_ai` cria snapshot automaticamente e retorna metadados

### Regressão completa — 57/57 testes passando
- 17 legados + 8 IA + 9 cookies + 6 evidências + 17 snapshots.

### Validação E2E (screenshot)
Modal auditor renderizado com:
- Snapshot ID `c052267c-162a-47c0-bd02-02a225cde17e`
- Hash público `sha256:3061ea2b7ea4fd1ccd81505e532731429d0cb0...`
- HMAC `hmac-sha256:48d69662901943785...`
- Banner verde: "Documento íntegro e autêntico" · Hash válido: sim · Assinatura válida: sim
- Histórico de 3 snapshots anteriores com timestamps
- Instrução completa de como validar externamente

### Impacto estratégico
Saída de *"sistema com IA"* para *"sistema com evidência verificável + trilha de decisão institucional"*. Cada análise agora pode ser:
- Defendida em reunião pública
- Impressa como PDF com selo de integridade
- Validada por um terceiro sem acesso ao banco
- Usada como justificativa em tribunal de contas

### Status: ✅ PRODUÇÃO-READY
Base consolidada para Sprint G3 (Relatório Mensal) que herdará snapshots desde o dia 1.


---

## Sprint G1.6 — Portal Público de Verificação + Verifiable Documents [03/Fev/2026]

### Problema resolvido
G1.5 entregou **prova auditável** restrita a usuários autenticados. Para transformar isso em argumento de venda institucional (prestação de contas pública, reuniões com conselho, tribunal de contas), era necessário um **portal público sem auth** onde qualquer cidadão pudesse validar um documento impresso sem login — **mas sem expor dados sensíveis (LGPD)**.

### Arquitetura desacoplada (decisão crítica)
Em vez de acoplar a validação ao snapshot de IA, criamos a coleção genérica `verifiable_documents` — qualquer documento institucional pode ser emitido com código público: plano_acao, relatorio_mensal, certificado, declaracao, historico, ata, generico.

### Implementação

**Backend — `services/verifiable_docs_service.py`**
- **Código amigável** `SIGESC-XXXX-XXXX` (8 chars de alfabeto seguro — sem 0/O/1/I/L para evitar erro humano)
- **Entropia**: 28^8 ≈ 3.8×10^11 combinações por 8 chars, unicidade garantida por índice único + retry em até 5 colisões
- **Normalização de input** (LGPD-UX real): aceita `"sigescabcd2345"`, `"ABCD-2345"`, `"  abcd2345  "`, `"sigesc-abcd-2345"` — tudo resolve para o mesmo documento canônico
- **Revogação** com motivo + usuário + timestamp — definitivo, sem reversão (mantém simples)
- **Metadata pública mínima**: `{tipo, tipo_label, emitido_em, emitido_por, escopo}` — ZERO payload, ZERO ai_output
- **Integração automática com snapshots**: `create_snapshot()` agora emite código público automaticamente via `create_verifiable_document()` — rastreabilidade unificada

**Backend — `routers/verifiable_docs.py`**
- **Público (SEM AUTH)**: `GET /api/public/verify/{code}` com rate limit **20/min por IP** via slowapi
  - Response LGPD-safe em **3 estados claros**: `"valido" | "invalido" | "revogado"`
  - Valida hash + HMAC do snapshot vinculado quando existe (integridade real, não só "existe")
  - Schema: `{status, codigo, tipo, tipo_label, emitido_em, emitido_por, escopo, integridade, assinatura_valida, mensagem}`
- **Autenticado**:
  - `GET /api/documents` — lista com escopo (super_admin global / admin+secretario mantenedora / diretor suas escolas)
  - `GET /api/documents/{code}` — detalhes
  - `POST /api/documents/{code}/revoke` — revogação com motivo
  - `POST /api/documents/ensure-for-snapshot/{snapshot_id}` — geração **retroativa sob demanda** para snapshots pré-G1.6 (opção C escolhida: evita migração pesada)

**PDF com QR Code + código legível** (`services/snapshot_pdf.py` + `segno`)
- QR Code (correção ISO alta, ~3cm) gerado via `segno` (biblioteca leve, zero deps externas) apontando para `{FRONTEND}/verificar/{code}`
- Bloco destacado em indigo com:
  - Código `SIGESC-XXXX-XXXX` em Courier-Bold 14pt
  - URL do portal: `{FRONTEND}/verificar`
  - QR Code ao lado
  - Instrução: "Digite o código acima ou escaneie o QR Code ao lado para confirmar a autenticidade e integridade deste documento"

**Frontend — `pages/VerifyPublic.jsx` + rotas `/verificar` e `/verificar/:code`**
- Rota **PÚBLICA** (sem autenticação) — nova seção no App.js ao lado de /pre-matricula e /login
- UX moderno: gradient indigo-950 → slate-900, glass-morphism no card, tipografia grande e legível
- **Normalização client-side** espelhando backend — evita chamadas inválidas
- Input com autoFocus, placeholder `SIGESC-ABCD-1234`, monospace
- 3 estados visuais distintos:
  - **Válido**: badge verde `ShieldCheck` + "Documento autêntico e íntegro"
  - **Revogado**: badge âmbar `ShieldAlert` + "Documento revogado" + data da revogação
  - **Inválido**: badge vermelho `ShieldX` + "Documento inválido"
- URL compartilhável após verificação (`navigate` replace)
- Tratamento de 429 (rate limit) com mensagem clara
- Rodapé institucional: "Infraestrutura de Confiança SIGESC · Verificação pública baseada em SHA256 + HMAC-SHA256"

### Testes (`tests/test_verifiable_docs.py`) — 27/27 pass
- **Formato código**: 50 rodadas de regex match, 200 códigos únicos em lote
- **Normalização**: parametrizado com 7 variações aceitas + 7 inválidas
- **Persistência**: create + resolve com input não-canônico + revoke + idempotência
- **LGPD crítico**: `build_portal_response` recebe doc com `"DADO_PESSOAL_SENSIVEL"` embutido e retorna resposta sem vazar nenhum campo sensível (assert negativo explícito)
- **3 estados do portal**: validação individual
- **E2E público**: endpoint SEM auth retorna 200, schema mínimo, bloqueia `ai_output/payload_snapshot/public_hash/server_signature` no response
- **Normalização no endpoint**: código lowercase sem prefix/hífen resolve corretamente
- **Revogação via endpoint**: super_admin revoga → portal público retorna `"revogado"`
- **Integração**: `create_snapshot` emite automaticamente `verification_code`
- **Retroativo**: `ensure-for-snapshot` gera código para snapshot antigo + idempotência

### Regressão completa — 84/84 testes passando
- 17 legados + 8 IA + 6 evidências + 9 cookies + 17 snapshots + 27 verifiable docs.

### Validação E2E (screenshots)
Portal renderizado com `SIGESC-5NJP-XG93` (snapshot real com HMAC) → banner verde "Documento autêntico e íntegro" · Integridade: **confirmada** · Assinatura: **válida**.
Portal renderizado com `SIGESC-MK5B-6UH6` (doc de teste sem HMAC) → banner vermelho "Documento inválido" · Integridade: confirmada · Assinatura: **inválida / ausente** — comportamento correto.
Input normaliza: `sigescabcd2345` → resolve para `SIGESC-ABCD-2345`.

### Impacto estratégico
**Saída de** *"sistema com IA"* **para** *"infraestrutura de autenticação documental da rede municipal"*.
Qualquer documento institucional emitido pelo SIGESC agora pode ser:
- Validado publicamente em 2 segundos via QR Code (sem login)
- Defendido em reunião pública com evidência técnica reproduzível
- Revogado centralmente se for emitido por erro
- Estendido para qualquer outro tipo documental futuro (certificados, declarações) sem reformar infraestrutura

Isso **não é mais feature**. É **base para vender transparência como padrão** em redes que precisam cumprir Lei de Acesso à Informação.

### Status: ✅ PRODUÇÃO-READY
Ciclo completo: G1 (explicação) → G1.5 (prova privada) → G1.6 (verificação pública). Base consolidada para Sprint G3.

