# Assessment Policy Multi-Mantenedora v1 — Sprint 001 Foundation

**Status:** EM EXECUÇÃO  
**Branch:** `feat/assessment-policy-foundation-v1`  
**Base:** `6024474873ffed4ada9d0b0d5bd0bd4601d56ff8` (merge PR #54)  
**Natureza desta etapa:** arquitetura + inventário + contratos; **sem alteração de regra de negócio em produção**.

---

## 1. Objetivo

Criar a fundação para substituir regras de avaliação/aprovação dispersas e hardcoded por um motor determinístico, versionado, auditável e multi-mantenedora.

Invariante central:

> O SIGESC não possui regra avaliativa global. Toda regra de avaliação, recuperação, cálculo e resultado escolar pertence a uma política versionada de uma mantenedora e é resolvida pelo contexto acadêmico efetivo do estudante.

Nenhum dado de `grades` será migrado, recalculado ou reescrito nesta sprint.

---

## 2. Escopo da Sprint 001

1. Commit Archaeologist — reconstruir os motores/regras existentes.
2. Dependency Doctor — mapear produtores e consumidores de resultados avaliativos.
3. Definir contrato de `AssessmentPolicy` v1.
4. Criar Registry/Schema isolado, sem integrar ainda com as rotas de notas.
5. Criar validações puras e testes de contrato.
6. Não substituir `calculate_and_update_grade()` nesta sprint.
7. Não alterar Boletim, PDFs, BI, Histórico ou Promoção nesta sprint.
8. Não executar backfill.

---

## 3. Baseline encontrado — Commit Archaeologist

### 3.1 `backend/routers/grades.py`

Existe um motor legado que calcula `final_average` e `status` após gravações em `grades`.

A auditoria de produção de 2026 comprovou que os `final_average` persistidos do 1º/2º Ano auditados coincidem com este motor legado.

**Classificação:** motor ativo/legado; deverá ser encapsulado e posteriormente retirado do papel de SSoT, nunca removido antes do shadow mode.

### 3.2 `backend/grade_calculator.py`

Contém outro conjunto independente de regras:

- `WEIGHTS = {b1: 2, b2: 3, b3: 2, b4: 3}`;
- `MIN_AVERAGE = 5.0`;
- `MIN_ATTENDANCE = 75.0`;
- recuperação de B1/B2 e B3/B4;
- regra especial de Educação Infantil;
- `calculate_maior_conceito()`;
- status/documentos com regras por série/nível;
- função de resultado final que já recebe `regras_aprovacao` da mantenedora.

Há, portanto, uma combinação de parâmetros configuráveis com regras ainda codificadas no módulo.

**Classificação:** fonte parcial/reutilizável para descoberta, mas não pode permanecer como SSoT multi-mantenedora no formato atual.

### 3.3 `backend/models.py` — Mantenedora

O cadastro atual da mantenedora já possui parâmetros administrativos de aprovação, entre eles:

- `media_aprovacao`;
- `frequencia_minima`;
- `aprovacao_com_dependencia`;
- `max_componentes_dependencia`;
- `cursar_apenas_dependencia`;
- `qtd_componentes_apenas_dependencia`.

Esses campos não possuem versionamento temporal e não expressam toda a política avaliativa. Alterá-los sobrescreve a configuração corrente e não cria, por si só, uma política reproduzível por ano/vigência.

**Decisão:** preservar compatibilidade durante a transição; não ampliar esse bloco. O novo domínio será uma coleção versionada própria (`assessment_policies`).

### 3.4 Frontend conceitual

`frontend/src/components/grades/gradeHelpers.jsx`, `Grades.js` e `AlunoTab.jsx` possuem lógica própria para conceitos, incluindo `calcularMaiorConceito()`.

**Classificação:** cálculo duplicado no cliente. No estado-alvo, frontend apresenta/simula; o resultado canônico deve vir do motor backend.

### 3.5 Status conceitual

`backend/tests/test_status_conceitual.py` documenta como regra atual:

- Educação Infantil + 1º/2º Ano tratados como conceituais;
- 1º/2º Ano promovidos quando os bimestres estão completos;
- 3º+ tratados como avaliados numericamente.

A política multi-mantenedora não poderá codificar esses anos como regra universal.

**Decisão:** preservar os testes atuais enquanto o motor legado continuar oficial; novos testes da política v1 serão isolados e não alterarão esses contratos na Sprint 001.

---

## 4. Baseline encontrado — Dependency Doctor

### 4.1 Produtores / mutadores principais

- `backend/routers/grades.py`
- `backend/routers/grades_dvd.py`
- `backend/grade_calculator.py`

### 4.2 Consumidores identificados de `final_average` / regras de aprovação

A busca de dependências identificou, entre outros:

- `backend/pdf/boletim.py`
- `backend/pdf/ficha_individual.py`
- `backend/pdf/notas.py`
- `backend/pdf/historico_escolar.py`
- `backend/utils/bulletin_builder.py`
- `backend/routers/analytics.py`
- `backend/services/academic_risk_engine.py`
- `backend/routers/student_history.py`
- `backend/services/history_consolidator.py`
- `backend/routers/student_portal.py`
- `backend/routers/documents.py`
- `backend/routers/dependency_completions.py`
- `frontend/src/pages/Grades.js`
- `frontend/src/components/grades/GradesTable.jsx`
- `frontend/src/components/grades/AlunoTab.jsx`
- `frontend/src/pages/BulletinViewer.jsx`
- `frontend/src/pages/BoletimAluno.jsx`
- `frontend/src/pages/Promotion.jsx`

Esta lista é baseline inicial; a Sprint 001 deverá transformá-la em matriz classificada por tipo de uso: **calcula / grava / exibe / decide / agrega / testa**.

---

## 5. Riscos já confirmados

### R1 — múltiplas SSoT

Há mais de um algoritmo para média e situação.

### R2 — regra municipal hardcoded

Pesos, média mínima, frequência e tratamento conceitual aparecem em código. Uma política de uma mantenedora não pode ser regra global do produto.

### R3 — política histórica não reproduzível

Campos diretamente em `mantenedoras` não carregam versão, vigência ou hash da regra.

### R4 — multisseriação

A política não pode ser resolvida apenas por `class.grade_level`. Deve priorizar a série individual da matrícula/vínculo histórico.

### R5 — consumidores recalculando

Boletim, PDF, frontend, BI e documentos não podem manter fórmulas paralelas depois do cutover.

### R6 — migração prematura

Os dados bimestrais existentes devem ser preservados. Campos derivados só poderão ser remediados após Registry + Resolver + Calculator + shadow/dry-run.

---

## 6. Arquitetura-alvo

```text
Mantenedora
    |
    +-- AssessmentPolicy Registry (versionado / imutável quando publicado)
            |
            +-- Policy Resolver
                    |
                    +-- série efetiva do estudante
                    +-- escola
                    +-- turma
                    +-- componente
                    +-- modalidade/etapa
                    +-- ano letivo
                    +-- data de referência
                            |
                            v
                    ResolvedAssessmentPolicy
                            |
                    +-------+-------+
                    |               |
              Calculator       Recovery Engine
                    |               |
                    +-------+-------+
                            |
                  Canonical Assessment
                            |
                  Academic Outcome Engine
                            |
             Boletim / PDF / Histórico / BI
```

IA/RAG poderá explicar ou auditar a política, nunca participar do cálculo oficial.

---

## 7. Precedência de resolução

A política candidata deve sempre pertencer à mantenedora ativa e estar vigente no contexto solicitado.

Precedência de especificidade planejada:

1. turma + componente;
2. turma;
3. escola + componente;
4. escola;
5. mantenedora + série/modalidade/etapa/componente;
6. mantenedora + série/modalidade/etapa;
7. mantenedora geral compatível com o contexto.

Duas políticas publicadas igualmente específicas e simultaneamente aplicáveis devem falhar fechado:

`ASSESSMENT_POLICY_AMBIGUOUS`

Ausência de política aplicável:

`ASSESSMENT_POLICY_REQUIRED`

---

## 8. Série efetiva

Ordem planejada:

1. série persistida na matrícula do ano (`enrollment.student_series`);
2. série preservada no vínculo/histórico anual;
3. `student.student_series` quando coerente com o ano corrente;
4. `class.grade_level` somente como fallback seguro.

Se a turma for multisseriada e não houver série individual confiável:

`ASSESSMENT_STUDENT_SERIES_REQUIRED`

Nunca inferir silenciosamente uma série coletiva em turma multisseriada.

---

## 9. Contrato de política v1

A política deverá conter, no mínimo:

- identidade (`id`, `policy_key`, `version`);
- `mantenedora_id`;
- `name`;
- `status` (`draft`, `validated`, `published`, `superseded`, `retired`);
- `academic_year`;
- `effective_from` / `effective_until`;
- `scope`;
- modo de avaliação;
- escala conceitual ou numérica;
- períodos e pesos;
- estratégia de cálculo;
- estratégia/grupos de recuperação;
- regras de resultado acadêmico;
- fontes normativas;
- `rule_hash` após publicação;
- autoria e timestamps.

Política `published` será imutável. Alteração cria nova versão.

---

## 10. Política de Floresta do Araguaia — exemplo de configuração, não regra global

Configuração informada para a mantenedora:

- 1º/2º Ano: C/ED/ND;
- C=10,0; ED=7,5; ND=5,0;
- 3º Ano: numérico;
- pesos B1=2, B2=3, B3=2, B4=3;
- recuperação substitui a menor nota; em empate, período de maior peso;
- média por componente >= 5,0;
- frequência mínima = 75%.

Pendências operacionais antes de publicar a política municipal como definitiva:

1. associação exata entre cada recuperação existente e os períodos alcançados;
2. confirmar se recuperação inferior nunca reduz o resultado original (`only_if_improves`);
3. confirmar base dos 75% (`global`, `component` ou outra).

Essas pendências não impedem a fundação do motor genérico.

---

## 11. Entregáveis da Sprint 001

- [x] branch isolada criada a partir do PR #54;
- [x] baseline dos motores identificado;
- [x] baseline de dependências identificado;
- [x] decisão de não ampliar `mantenedoras.media_aprovacao` como SSoT;
- [ ] schema puro da política v1;
- [ ] canonicalização/hash determinístico;
- [ ] validator puro;
- [ ] testes unitários do contrato;
- [ ] matriz completa de consumidores;
- [ ] Scope Creep guard inicial;
- [ ] CI verde;

---

## 12. Proibições nesta Sprint

- Não alterar cálculo atual de `grades`.
- Não atualizar `final_average`.
- Não alterar `status` de alunos/notas.
- Não fazer backfill.
- Não alterar frequência.
- Não alterar AEE.
- Não alterar matrícula/transferência.
- Não alterar PDFs para usar o novo motor ainda.
- Não cadastrar automaticamente política em produção.
- Não habilitar feature flag de cutover.

---

## 13. Gate para Sprint 002

A Sprint 002 (Resolver) somente pode iniciar quando:

1. schema e validator v1 estiverem estabilizados;
2. o hash canônico for reproduzível;
3. tenant isolation estiver coberto por testes;
4. a matriz de dependências estiver revisada;
5. nenhum comportamento de notas tiver mudado;
6. CI/regressão estiver verde.
