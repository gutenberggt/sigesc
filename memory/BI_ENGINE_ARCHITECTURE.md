# BI_ENGINE_ARCHITECTURE.md — Motor de Indicadores do SIGESC IA
### Especificação Arquitetural Oficial · Sprint BI-0 · Jun/2026

> **READ-ONLY.** Documento de arquitetura. Não altera código, coleções, endpoints,
> dashboards, banco ou comportamento. Encerra a fase de diagnóstico e inaugura a
> fase de construção da **Plataforma de Inteligência Educacional**. A implementação
> só inicia após aprovação formal desta especificação.
>
> Complementa: `ARCHITECTURE_BASELINE.md` (§3 princípio SSoT), `EXECUTIVE_ARCHITECT_REVIEW.md`,
> `audit/04_INDICADORES.md`, `audit/21_BUSINESS_INTELLIGENCE.md`.

## Índice
1. [Diretrizes obrigatórias](#0-diretrizes-arquiteturais-obrigatórias)
2. [Modelo conceitual](#2-modelo-conceitual)
3. [Arquitetura geral](#3-arquitetura-geral)
4. [Catálogo oficial de indicadores](#4-catálogo-oficial-de-indicadores)
5. [Modelo de definição (`bi_indicator_defs`)](#5-modelo-de-definição-de-indicadores)
6. [Engine de cálculo](#6-engine-de-cálculo)
7. [Granularidade](#7-granularidade)
8. [Estratégia de performance](#8-estratégia-de-performance)
9. [Contrato da API BI](#9-contrato-da-api-bi)
10. [Integração com IA (Indicator Context Pack)](#10-integração-com-a-ia)
11. [Roadmap de implementação](#11-roadmap-de-implementação)

---

## 0. Diretrizes Arquiteturais Obrigatórias
| # | Diretriz | Implicação de projeto |
|---|---|---|
| 1 | **SSoT** | indicador só é calculado no Motor; dashboards/IA/relatórios apenas consomem |
| 2 | **Reutilização antes de criação** | Motor reusa `attendance_utils`, `grade_calculator`, `serie_canonical` como calculadoras base |
| 3 | **Escalabilidade** | centenas de indicadores sem mudança estrutural → definição **declarativa** |
| 4 | **Configurabilidade** | novo indicador = novo registro em `bi_indicator_defs` (mínimo código) |
| 5 | **Rastreabilidade** | toda resposta (dashboard/IA) referencia `indicator_id` + `def_version` + `computed_at` |
| 6 | **Independência da origem** | adapters de fonte: SIGESC (OLTP), API externa, import CSV/Excel, cadastro manual |
| 7 | **Compatibilidade retroativa** | defs versionadas + resultados publicados imutáveis (não reescrever histórico) |

---

## 2. Modelo Conceitual
Conceitos, contextualizados à gestão educacional:

- **Fato (Fact):** evento mensurável registrado no OLTP. Ex.: uma frequência (aluno faltou
  em uma aula), uma nota lançada, uma matrícula efetivada. É a matéria-prima.
- **Dimensão (Dimension):** eixo pelo qual um fato é analisado. Ex.: escola, turma, aluno,
  tempo (ano/bimestre/mês), componente curricular, série, zona (urbana/rural), cor/raça.
- **Métrica (Metric):** valor numérico bruto agregável. Ex.: nº de faltas, nº de matrículas,
  soma de notas. Métrica **não** tem interpretação por si só.
- **Indicador (Indicator):** métrica(s) transformada(s) por uma **fórmula** e associada(s) a
  dimensões/granularidade, com significado de gestão. Ex.: *Taxa de Frequência* = função de
  presenças/dias letivos. **Só o Motor produz indicadores.**
- **Agregação (Aggregation):** operação de consolidação de fatos numa granularidade
  (sum, avg, count, ratio, weighted_avg). Ex.: média da rede = agregação das escolas.
- **Granularidade (Grain):** nível de detalhe do resultado — **rede · escola · etapa/nível ·
  turma · professor · aluno**. Um mesmo indicador é calculável em vários grãos.
- **KPI:** indicador **elevado a meta de gestão**, com alvo/limiar e semântica de status
  (🟢🟡🔴). Ex.: *Taxa de Aprovação* com meta ≥ 95%. Todo KPI é um indicador; nem todo
  indicador é KPI.
- **Dashboard:** superfície de **consumo** que agrupa indicadores/KPIs por público. Nunca calcula.
- **Mart (Data Mart):** coleção **pré-agregada** com resultados de indicadores por
  dimensão/grão/período, otimizada para leitura (ex.: `mart_frequencia`).
- **Materialização:** processo de pré-calcular e persistir um indicador num mart (ETL
  incremental). Oposto de cálculo on-the-fly.
- **Cache:** armazenamento temporário do resultado de um cálculo (TTL), sem persistência
  dimensional completa. Camada intermediária entre tempo real e materialização.
- **Tendência (Trend):** variação de um indicador ao longo do tempo (delta, %, direção ▲▼).
- **Série Histórica (Time Series):** sequência de valores de um indicador por período,
  base para tendências, projeções e comparações inter-anuais.

**Relação:** `Fatos + Dimensões → (Agregação + Fórmula no Motor) → Indicador → [KPI] →
[Mart/Cache] → API BI → Dashboards/IA/Relatórios`.

---

## 3. Arquitetura Geral
```
   ┌──────────────────────────── FONTES (independência de origem) ────────────────────────────┐
   │  SIGESC OLTP (MongoDB)  ·  APIs externas (MEC/INEP/FNDE/IBGE)  ·  Import CSV/Excel  ·      │
   │  Cadastro manual (metas, PME externo)                                                      │
   └───────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                ▼   (Source Adapters — normalizam para Fatos/Dimensões)
   ┌────────────────────────────────── MOTOR DE INDICADORES (SSoT) ─────────────────────────────┐
   │  ① Registry (bi_indicator_defs) — definição declarativa dos indicadores                    │
   │  ② Resolver — resolve indicador+escopo+grão, ordena dependências (DAG)                      │
   │  ③ Calculators — biblioteca canônica (reusa attendance_utils, grade_calculator, ...)        │
   │  ④ Aggregator — aplica grão/dimensões; deriva (nunca reimplementa)                          │
   │  ⑤ Materializer/Cache — decide tempo real | cache | mart; grava mart_* + bi_refresh_log     │
   │  ⑥ Traceability — carimba indicator_id + def_version + inputs + computed_at                 │
   └───────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                ▼
   ┌────────────────────────────────── BUSINESS INTELLIGENCE API (/api/bi/*) ───────────────────┐
   │  contrato estável · RLS por tenant/escola · filtros · paginação · versionado                │
   └───────┬───────────────┬──────────────┬───────────────┬───────────────┬──────────────────────┘
           ▼               ▼              ▼               ▼               ▼
   Dashboard          Dashboard        Relatórios       Alertas         SIGESC IA
   Operacional        Executivo        (PDF/e-mail)     (alert_engine)  (Indicator Context Pack)
```

### Camadas (o que cada uma faz)
- **Fontes:** sistemas de origem. O Motor não se acopla a nenhuma; **Source Adapters** convertem
  cada origem em fatos/dimensões canônicos.
- **Motor de Indicadores:** cérebro (SSoT). Registry declarativo + resolver (DAG de dependências)
  + calculators canônicos + aggregator por grão + camada de materialização/cache + rastreabilidade.
- **API BI:** única porta de saída dos indicadores. Aplica segurança (RLS), filtros, paginação.
- **Consumidores:** dashboards (Operacional/Executivo/Especializados), relatórios, alertas e IA —
  todos consomem os **mesmos** valores oficiais.

---

## 4. Catálogo Oficial de Indicadores
> Consolida `audit/04_INDICADORES.md`. Códigos oficiais estáveis (usados em `bi_indicator_defs`,
> API e IA). Campos por indicador: código · nome · categoria · objetivo · fórmula · fonte ·
> dependências · grãos · periodicidade · dashboards · APIs · cache · materialização · parametrização.

### Sumário (código → nome → categoria → estratégia de performance)
| Código | Nome | Categoria | Perf. |
|---|---|---|---|
| `IND-APROV` (A1) | Taxa de Aprovação/Reprovação | Rendimento | materializado |
| `IND-MEDIA` (A2) | Média ponderada | Rendimento | cache/materializado |
| `IND-CONCEITO` (A3) | Resultado conceitual (Infantil/1º-2º) | Rendimento | cache |
| `IND-DISTNOTA` (A4) | Distribuição de notas | Rendimento | materializado |
| `IND-FREQ` (B1) | Taxa de Frequência | Frequência | materializado |
| `IND-INFREQ` (B2) | Infrequência / Busca Ativa | Frequência | derivado(B1) |
| `IND-PBF` (B3) | Condicionalidade Bolsa Família | Frequência | materializado |
| `IND-MATRIC` (C1) | Matrículas / Ativos | Fluxo | materializado |
| `IND-MATTREND` (C2) | Tendência de matrícula | Fluxo | materializado(série) |
| `IND-DISTORCAO` (C3) | Distorção idade-série | Fluxo | materializado |
| `IND-RESULT` (C4) | Rendimento por status | Fluxo | materializado (≡ A1) |
| `IND-RACA` (D1) | Distribuição cor/raça | Demografia | materializado |
| `IND-PERFIL` (D2) | PcD / NIS / Zona | Demografia | materializado |
| `IND-COBERT` (E1) | Cobertura curricular | Currículo | materializado |
| `IND-DIARIO` (E2) | Cumprimento de diário | Currículo | cache/materializado |
| `IND-RANKESC` (F1) | Ranking de escolas | Comparativo | derivado |
| `IND-RANKGEST` (F2) | Ranking de gestão | Comparativo | derivado(≈F1) |
| `IND-PERFALU` (F3) | Performance de alunos | Comparativo | materializado |
| `IND-PERFPROF` (F4) | Performance de professores | Comparativo | materializado |
| `IND-RISCOACAD` (G1) | Risco acadêmico | Risco | cache |
| `IND-RISCOFREQ` (G2) | Risco de frequência | Risco | cache |
| `IND-RISCOGER` (G3) | Risco geral | Risco | cache |
| `IND-PMEEXT` (H1) | Indicadores externos PME | Externo/Manual | sem cálculo (input) |

### Fichas de referência (exemplos completos — demais seguem o mesmo padrão em `audit/04`)
**`IND-FREQ` — Taxa de Frequência**
- Categoria: Frequência · Objetivo: medir presença efetiva.
- Fórmula: `dias_presentes / dias_letivos`, com **consolidação diária ≥50%** (dia com ≥50%
  das aulas presentes = presente). Parâmetro: `limiar_dia=0.5`.
- Fonte: `attendance` + `calendario_letivo`. Dependências: calculadora `frequencia()`
  (reusa `attendance_utils`), `school_calendar_helper` (dias/sábado letivo).
- Grãos: aluno→turma→escola→rede, por mês/bimestre/ano.
- Periodicidade: diária. Dashboards: Operacional, BuscaAtiva, BF, Executivo. API: `/api/bi/indicators?code=IND-FREQ`.
- Cache: sim · Materialização: sim (`mart_frequencia`) · Parametrização: limiar diário, período.

**`IND-MEDIA` — Média ponderada**
- Fórmula: `(B1×2+B2×3+B3×2+B4×3)/10`; recuperação semestral substitui a menor nota do semestre.
- Fonte: `grades`. Dependência: calculadora `media_ponderada()` (reusa `grade_calculator`).
- Grãos: aluno→turma→escola→rede. Materialização: sim. Parametrização: pesos, média de aprovação (mantenedora).

**`IND-DISTORCAO` — Distorção idade-série**
- Fórmula: `(idade_no_ano − idade_esperada(série)) ≥ limiar` (padrão 2 anos).
- Fonte: `students.birth_date` + série (via `student_series`/`grade_level`). Grãos: aluno→série→escola→rede.
- Materialização: sim. Parametrização: limiar de anos.

### Equivalentes / derivados / unificação (resumo)
- **Unificar:** `IND-APROV (A1) ≡ IND-RESULT (C4)`; `IND-RANKESC (F1) ≈ IND-RANKGEST (F2)`.
- **Derivados (compor, não recalcular):** `IND-INFREQ = 1 − IND-FREQ`; `IND-PBF = IND-FREQ vs. limiar`;
  `IND-MATTREND = série de IND-MATRIC`; `F1/F3/F4/G* = agregações/ponderações de A/B/E`.
- **Calculado em múltiplos locais hoje (dívida a eliminar):** frequência (4×), média (5×),
  ranking (2×), resultado/status (2×) → uma única implementação no Motor.

---

## 5. Modelo de Definição de Indicadores (`bi_indicator_defs`)
> **Especificação lógica** (não criar coleção). Cada indicador = 1 documento declarativo versionado.

```jsonc
{
  "code": "IND-FREQ",                 // identificador oficial estável (imutável)
  "version": 3,                        // versão da definição (compatibilidade retroativa)
  "status": "active",                  // active | draft | deprecated | disabled
  "name": "Taxa de Frequência",
  "description": "Percentual de presença efetiva com consolidação diária.",
  "category": "frequencia",            // rendimento|frequencia|fluxo|demografia|curriculo|comparativo|risco|externo
  "objective": "Monitorar presença para prevenção de evasão.",
  "unit": "percent",                   // percent | count | ratio | score | currency
  "formula": {                         // declarativa e interpretável pelo resolver
    "type": "ratio",                   // ratio|weighted_avg|count|sum|avg|composite|derived|manual|external
    "numerator": "dias_presentes",
    "denominator": "dias_letivos",
    "pre": ["consolidacao_diaria(limiar_dia)"]
  },
  "source": {                          // independência de origem
    "kind": "oltp",                    // oltp | external_api | import | manual
    "collections": ["attendance", "calendario_letivo"],
    "adapter": "sigesc.attendance"
  },
  "dependencies": ["calendario.dias_letivos", "calc.frequencia"], // DAG
  "supported_grains": ["aluno","turma","escola","rede"],
  "supported_dimensions": ["tempo","serie","zona","componente"],
  "default_grain": "escola",
  "refresh": { "periodicity": "daily", "strategy": "materialized" }, // realtime|cached|materialized
  "cache": { "enabled": true, "ttl_seconds": 3600 },
  "materialization": { "enabled": true, "mart": "mart_frequencia", "incremental_key": "date" },
  "parameters": [                      // parametrização sem código
    { "key": "limiar_dia", "type": "float", "default": 0.5, "range": [0,1] },
    { "key": "periodo", "type": "enum", "values": ["mes","bimestre","ano"], "default": "mes" }
  ],
  "kpi": { "is_kpi": true, "target": 0.9, "warn": 0.85, "critical": 0.75, "direction": "higher_is_better" },
  "consumers": { "dashboards": ["operacional","busca_ativa","bolsa_familia","executivo"],
                 "apis": ["/api/bi/indicators"] },
  "rbac": { "min_roles": ["semed","admin","gerente","secretario","diretor"] },
  "documentation": { "owner": "SEMED", "notes": "Regra 50%/dia é local, não norma MEC." },
  "audit": { "created_at": "...", "created_by": "...", "supersedes_version": 2 }
}
```

### Regras de uso
- **Versionamento:** `code` é imutável; mudança de fórmula → nova `version` (a anterior vira
  `deprecated`, mas resultados já materializados permanecem — compatibilidade retroativa §0.7).
- **Ativação/desativação:** `status` controla exposição na API sem apagar histórico.
- **Dependências:** lista de nós (outros indicadores ou calculadoras) → resolver monta **DAG**
  e detecta ciclos; um cálculo base é reutilizado por todos os dependentes.
- **Fórmulas:** declarativas (`type` + operandos); `derived`/`composite` referenciam outros `code`
  (nunca reimplementam). `manual`/`external` não têm cálculo (entram por adapter).
- **Parâmetros:** tipados, com default e faixa → habilitam parametrização por requisição.
- **Documentação:** dono (responsável), notas de negócio, regras regulatórias.

---

## 6. Engine de Cálculo
Fluxo de uma solicitação de indicador:
1. **Solicitação:** consumidor chama `/api/bi/indicators?code=IND-FREQ&grain=escola&scope={escola_id}&periodo=mes&ano=2026` (ou via Context Pack para IA).
2. **Resolução (Resolver):** carrega a `def` (code+version ativa), valida grão/dimensões/params
   contra `supported_*`, resolve **DAG de dependências** (ex.: `IND-INFREQ`→`IND-FREQ`→`calc.frequencia`+`calendario.dias_letivos`).
3. **Decisão de origem (Materializer):** se `strategy=materialized` e mart fresco → **lê mart**;
   se `cached` e cache válido → **lê cache**; senão **calcula** (realtime).
4. **Cálculo (Calculators):** biblioteca canônica única — `frequencia()`, `media_ponderada()`,
   `resultado_final()`, `distorcao_idade_serie()`, `indice_composto()`, `risco()`. **Reusa**
   `attendance_utils`/`grade_calculator`/`serie_canonical` internamente (não reescreve regra).
5. **Agregação (Aggregator):** aplica grão e dimensões solicitadas sobre fatos/base já calculada.
6. **Reuso de cálculo:** resultados intermediários (ex.: base de frequência por aluno×dia) são
   **memoizados na requisição** e/ou persistidos em mart → dependentes reaproveitam.
7. **Rastreabilidade:** resposta carimba `{code, version, computed_at, source: mart|cache|realtime, inputs_hash}`.

**Como evitar duplicação:** um único ponto de cálculo por métrica-base; derivados **compõem**
bases via `code`; a proibição SSoT impede recomputo fora do Motor. **Registro de dependências:**
explícito na `def` (`dependencies`) → DAG audível e testável.

---

## 7. Granularidade
Suporte nativo, **sem duplicar lógica**: o cálculo base ocorre no **grão mais fino declarado**
(ex.: aluno×dia para frequência; aluno×componente para média) e a **agregação sobe** pelos grãos
por composição.

```
aluno ──▶ turma ──▶ escola ──▶ rede
              └────▶ etapa/nível (Ed. Infantil, Anos Iniciais/Finais, EJA)
professor ─▶ (via teacher_assignments) turma ─▶ escola ─▶ rede
```
- **Regra:** `agregado(grão_N) = função_de_agregação(agregado(grão_N-1))` — a fórmula base é
  escrita uma vez; a subida é genérica (sum/avg ponderado/count) definida em `formula.type`.
- **Dimensões ortogonais** (tempo, série, zona, cor/raça, componente) recortam qualquer grão.
- **Professor** é grão especial resolvido via `teacher_assignments` (alocação) — reusa o mesmo cálculo.
- **Pré-condição de integridade:** grãos aluno/turma dependem do **vínculo unificado (D2)** —
  fonte única `enrollments` (senão os agregados divergem).

---

## 8. Estratégia de Performance
Três classes, com critérios técnicos de enquadramento:

| Classe | Quando usar | Critério | Exemplos |
|---|---|---|---|
| **Tempo real** | dados voláteis, escopo pequeno, baixa reutilização | grão fino + poucos registros; latência aceitável < ~300ms | frequência de 1 aluno hoje; média de 1 turma |
| **Cache (TTL)** | consulta repetida, tolera leve defasagem | mesmo escopo consultado por muitos usuários; custo médio | ranking do dia; risco por aluno (TTL curto) |
| **Materializado (mart)** | rede inteira, séries históricas, dashboards executivos | alto custo de agregação + alta reutilização + defasagem tolerável (refresh diário/incremental) | IND-FREQ/IND-APROV/IND-MATRIC por rede/escola/mês |

- **Refresh incremental:** ETL processa apenas o delta (por `incremental_key`, ex.: `date`) e
  usa `with_critical_mutation` (idempotência + lock + `bi_refresh_log`).
- **Invalidação:** materialização é a **fonte de verdade** para grãos altos; tempo real é
  fallback quando mart está defasado. Cache invalida por TTL ou evento.
- **Fallback graceful:** se mart indisponível → cair para realtime (com marcação na rastreabilidade).

---

## 9. Contrato da API BI (`/api/bi/*`)
> **Especificação de contrato (não implementar).** Auth: JWT (padrão do sistema) + **RLS por
> tenant/escola** herdada de `tenant_scope`. Erros seguem o padrão HTTP atual.

### `GET /api/bi/indicators`
- **Finalidade:** obter valor(es) de um ou mais indicadores num escopo/grão.
- **Parâmetros:** `code` (1..n), `grain` (rede|escola|etapa|turma|professor|aluno),
  `scope_id` (id do grão; opcional p/ rede), `ano`, `periodo` (mes|bimestre|ano),
  `dimensions` (ex.: `serie,zona`), `params` (ex.: `limiar_dia=0.5`), `page`, `page_size`.
- **Resposta:** `{ code, name, unit, version, grain, scope, value, breakdown[by dimension],
  kpi_status, source: mart|cache|realtime, computed_at }`.
- **Paginação:** para breakdowns grandes (por escola/turma). **Filtros:** dimensões + escopo.

### `GET /api/bi/dashboard/{dashboard_id}`
- **Finalidade:** payload consolidado de um dashboard (Operacional/Executivo/Especializado):
  lista de indicadores + KPIs já resolvidos para o escopo/RBAC do usuário.
- **Parâmetros:** `scope`, `ano`, `periodo`, `filters`. **Resposta:** `{ dashboard, generated_at,
  indicators: [ {code, value, kpi_status, ...} ], filters_applied }`.

### `GET /api/bi/trends`
- **Finalidade:** série histórica/tendência de um indicador.
- **Parâmetros:** `code`, `grain`, `scope_id`, `from`, `to`, `bucket` (mes|bimestre|ano).
- **Resposta:** `{ code, series: [{period, value}], delta, direction ▲▼, projection? }`.

### `GET /api/bi/rankings`
- **Finalidade:** ordenar entidades (escolas/turmas/professores) por indicador/índice.
- **Parâmetros:** `code|index`, `grain`, `ano`, `periodo`, `order`, `limit`, `filters`.
- **Resposta:** `{ ranking: [{scope_id, name, value, position}], criteria }`.

### `GET /api/bi/alerts`
- **Finalidade:** indicadores que cruzaram limiar (KPI 🔴/🟡) — consumido por `alert_engine`.
- **Parâmetros:** `severity`, `scope`, `category`. **Resposta:** `{ alerts: [{code, scope,
  value, target, severity, since}] }`.

### `GET /api/bi/catalog`
- **Finalidade:** listar definições ativas (para UI de administração/documentação). Read-only da `def`.

---

## 10. Integração com a IA
**Princípio obrigatório:** a IA **nunca** consulta OLTP diretamente quando existe indicador
equivalente. A IA consome **conhecimento estruturado** via **Indicator Context Pack**.

### Indicator Context Pack (contrato lógico)
```jsonc
{
  "scope": { "grain": "escola", "scope_id": "...", "name": "EMEF X", "ano": 2026, "periodo": "bimestre-2" },
  "generated_at": "2026-06-30T...Z",
  "indicators": [
    { "code": "IND-FREQ", "name": "Taxa de Frequência", "value": 0.87, "unit": "percent",
      "version": 3, "kpi_status": "warn", "target": 0.9, "source": "mart_frequencia",
      "trend": { "delta": -0.06, "direction": "down" } },
    { "code": "IND-DISTORCAO", "value": 0.14, "breakdown": { "6_ano": 0.22 }, "version": 2 }
  ],
  "benchmarks": { "rede_media_IND-FREQ": 0.93 },
  "provenance": { "def_versions": {"IND-FREQ":3,"IND-DISTORCAO":2} }
}
```
### Garantias
- **Mesmos valores** que os dashboards (ambos leem do Motor) → zero divergência número-narrativa.
- **Rastreabilidade:** cada afirmação da IA referencia `code` + `version` + `computed_at`;
  a análise é persistida em `ai_analysis_snapshots` com o Pack de entrada (auditável).
- **Consistência** entre análise, relatório e visualização (fonte única).
- **Fallback determinístico** opera sobre o mesmo Pack (sem chave/limite de IA).

### Refatoração implicada (futuro)
`pmpi_ai`, `plano_acao_ai`, `monthly_report_service` deixam de montar dados ad-hoc e passam a
receber o Context Pack do Motor.

---

## 11. Roadmap de Implementação
> Fases sequenciais; cada uma com objetivos, dependências, riscos e critérios de conclusão.

### BI-1 — Fundação (dados consistentes)
- **Objetivos:** unificar vínculo aluno↔turma (D2, fonte única `enrollments`); sanear status
  legado (D6); unificar estratégia de snapshots (D8); definir dimensões/fatos canônicos.
- **Dependências:** decisões da Sprint 000.1.
- **Riscos:** alto raio de regressão no núcleo → mitigar com feature-flag + rollback + suíte ampliada.
- **Conclusão:** vínculo único em produção; dimensões `dim_*` e fatos `fato_*` especificados e validados.

### BI-2 — Motor de Indicadores (SSoT)
- **Objetivos:** `bi_indicator_defs` (registry) + Resolver (DAG) + biblioteca `services/indicators/`
  (absorve `attendance_utils`/`grade_calculator`); migrar cálculos duplicados (frequência, média,
  ranking, resultado) para o Motor; unificar motores de risco (D5).
- **Dependências:** BI-1.
- **Riscos:** divergência de números durante migração → validar Motor vs. legado (paridade) antes de cortar.
- **Conclusão:** ≥ catálogo essencial (A1,A2,B1,C1,C3,D1,E1) servido exclusivamente pelo Motor,
  com paridade comprovada; zero cálculo duplicado nos indicadores migrados.

### BI-3 — Data Marts e otimizações
- **Objetivos:** modelo dimensional físico + ETL incremental (`with_critical_mutation`) +
  `mart_*` + camada de cache; classificação realtime/cache/materializado por indicador.
- **Dependências:** BI-2; MongoDB **replica set** + backup; worker dedicado (APScheduler fora do web).
- **Riscos:** consistência OLTP→mart → reconciliação + `bi_refresh_log` auditável.
- **Conclusão:** indicadores de rede materializados com refresh incremental e RLS; SLA de leitura definido.

### BI-4 — Integração dos Dashboards
- **Objetivos:** `/api/bi/*` estável; Dashboard **Operacional** (ex-Analytics) e **Executivo**
  (PME+SemedPanel+Ranking) consumindo o Motor; biblioteca `components/analytics/` compartilhada;
  remover todo cálculo de indicador do frontend (SSoT).
- **Dependências:** BI-3.
- **Riscos:** regressão de UI → snapshots visuais + paridade de números.
- **Conclusão:** 100% dos gráficos de rede vêm de `/api/bi/*`; nenhum cálculo em página/componente.

### BI-5 — Integração com IA
- **Objetivos:** Indicator Context Pack; refatorar `pmpi_ai`/`plano_acao_ai`/`monthly_report_service`;
  rastreabilidade em `ai_analysis_snapshots`.
- **Dependências:** BI-3/BI-4.
- **Riscos:** custo/latência → enviar agregados, não brutos.
- **Conclusão:** IA cita apenas números do Motor, com proveniência; paridade IA↔dashboard.

### BI-6 — Integrações externas (MEC/INEP/FNDE/IBGE, ...)
- **Objetivos:** Source Adapters externos + indicadores `external`/`import`/`manual`;
  benchmarks (IDEB/SAEB), taxas líquidas (censo IBGE), condicionalidades (FNDE/CadÚnico).
- **Dependências:** BI-2 (registry) + BI-3 (marts).
- **Riscos:** disponibilidade/qualidade de dados externos → cache + fallback + carimbo de origem.
- **Conclusão:** ≥1 fonte externa integrada via adapter, sem alterar o núcleo do Motor.

---

## Resultado esperado
Especificação completa e suficiente para implementar o Motor de Indicadores e toda a camada
de BI do SIGESC IA, respeitando SSoT, reutilização, escalabilidade, configurabilidade,
rastreabilidade, independência de origem e compatibilidade retroativa. **A implementação
inicia somente após aprovação formal desta arquitetura.**

*Sprint BI-0 concluída em Jun/2026 — READ-ONLY. Nenhum código, coleção, endpoint, dashboard,
banco ou comportamento foi alterado.*
