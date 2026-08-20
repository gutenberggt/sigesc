# Assessment Policy Multi-Mantenedora v1 — Sprint 001 Foundation

**Status:** CONCLUÍDA TECNICAMENTE — PR #55 em validação final  
**Branch:** `feat/assessment-policy-foundation-v1`  
**Base:** `6024474873ffed4ada9d0b0d5bd0bd4601d56ff8` (merge PR #54)  
**Natureza:** arquitetura + inventário + contratos + Registry isolado; **sem alteração do comportamento de Notas em produção**.

---

## 1. Objetivo

Criar a fundação para substituir regras de avaliação/aprovação dispersas e hardcoded por um motor determinístico, versionado, auditável e multi-mantenedora.

Invariante central:

> O SIGESC não possui regra avaliativa global. Toda regra de avaliação, recuperação, cálculo e resultado escolar pertence a uma política versionada de uma mantenedora e será resolvida pelo contexto acadêmico efetivo do estudante.

Nenhum dado de `grades` foi migrado, recalculado ou reescrito nesta sprint.

---

## 2. Escopo executado

1. Commit Archaeologist dos motores/regras existentes.
2. Dependency Doctor dos produtores e consumidores de resultado avaliativo.
3. Contrato `AssessmentPolicy` v1.
4. Canonicalização e SHA-256 determinístico das regras.
5. Validator puro.
6. Registry tenant-scoped e lifecycle isolado.
7. Optimistic locking por `revision`.
8. Especificação de índices Mongo — sem startup hook.
9. Scope Creep Guard específico da Foundation.
10. Testes puros de contrato, tenant isolation e lifecycle.

Não foram alterados:

- `calculate_and_update_grade()`;
- cálculo vigente de `grades`;
- `final_average`;
- `status`;
- frequência;
- AEE;
- matrícula/transferência;
- Boletim/PDF/Histórico/BI/Promoção.

---

## 3. Baseline — Commit Archaeologist

### 3.1 `backend/routers/grades.py`

Existe um motor legado que calcula `final_average` e `status` após gravações em `grades`.

A auditoria de produção de 2026 comprovou que os `final_average` persistidos do 1º/2º Ano auditados coincidem com este motor legado.

**Decisão:** permanecer intacto até shadow mode/cutover por mantenedora.

### 3.2 `backend/grade_calculator.py`

Contém outro conjunto independente de regras, incluindo:

- pesos B1/B2/B3/B4 codificados;
- média mínima/frequência mínima codificadas;
- recuperação;
- regras conceituais por etapa/série;
- `calculate_maior_conceito()`;
- regras de resultado documental.

Achados adicionais:

- o motor ponderado trata períodos ausentes como zero e divide pela soma total dos pesos;
- o desempate de recuperação tem divergência entre intenção/comentário e implementação: `<=` seleciona B1/B3 em empate, embora a regra esperada de maior peso aponte B2/B4 no conjunto 2/3/2/3.

**Decisão:** não corrigir esse legado na Foundation. Alterá-lo mudaria comportamento de produção antes do shadow mode.

### 3.3 Parametrização existente na mantenedora

`backend/models.py` já possui campos como:

- `media_aprovacao`;
- `frequencia_minima`;
- regras de dependência.

Eles não possuem versionamento temporal, vigência ou hash e não expressam uma política avaliativa completa.

**Decisão:** preservar por compatibilidade; não ampliar esse bloco como nova SSoT. O novo domínio utilizará coleção própria `assessment_policies`.

### 3.4 Frontend

`gradeHelpers.jsx`, `Grades.js` e `AlunoTab.jsx` possuem cálculo/síntese próprios.

**Estado-alvo:** frontend apresenta e coleta dados; resultado canônico virá do backend.

### 3.5 Status conceitual legado

`backend/tests/test_status_conceitual.py` registra comportamento atual por série/etapa, inclusive promoção do 1º/2º Ano quando completo.

**Decisão:** preservar enquanto o legado for oficial. A nova arquitetura não transforma isso em regra global.

---

## 4. Dependency Doctor

A matriz detalhada está em:

`memory/audit/ASSESSMENT_POLICY_V1_DEPENDENCY_MATRIX.md`

Produtores/calculadores críticos incluem:

- `backend/routers/grades.py`;
- `backend/routers/grades_dvd.py`;
- `backend/grade_calculator.py`.

Consumidores relevantes incluem:

- Boletim;
- Ficha Individual;
- Relatório de Notas;
- Histórico Escolar;
- portal do estudante;
- reconstrução/consolidação histórica;
- Promoção/Dependência;
- Analytics;
- risco acadêmico;
- consolidação pedagógica;
- telas de Notas no frontend.

Nenhum consumidor será migrado antes de Registry + Resolver + Calculator + shadow/dry-run.

---

## 5. Arquitetura-alvo

```text
Mantenedora
    |
    +-- AssessmentPolicy Registry
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

IA/RAG poderá explicar ou auditar políticas, nunca participar do cálculo oficial.

---

## 6. Contrato `AssessmentPolicy` v1

A Foundation implementa:

- `PolicyStatus`: `draft`, `validated`, `published`, `superseded`, `retired`;
- `AssessmentMode`: `numeric`, `conceptual`, `descriptive`, `skill_based`;
- escopo por escola/turma/série/componente/etapa/modalidade;
- escala conceitual configurável;
- escala numérica configurável;
- períodos e pesos configuráveis;
- estratégia de cálculo;
- grupos/estratégia de recuperação;
- regra de resultado acadêmico;
- base de frequência;
- conselho/override auditável;
- fontes normativas;
- parent policy reference;
- `rule_hash`;
- metadados de criação/validação/publicação;
- `revision` para concorrência otimista.

`DESCRIPTIVE` e `SKILL_BASED` não são obrigados a carregar fórmula numérica artificial.

---

## 7. Canonicalização e hash

`canonical.py` calcula:

`sha256:<hex>`

sobre os campos que alteram resolução/cálculo, incluindo tenant, ano, vigência, escopo e regras.

Metadados administrativos como nome, autoria e timestamps não alteram o hash.

Assim, mesmas regras efetivas produzem o mesmo hash.

---

## 8. Validator puro

Valida, entre outros:

- períodos duplicados;
- escala conceitual incompleta/ambígua;
- recuperação sem grupos;
- períodos inexistentes em recuperação;
- necessidade de explicitar `only_if_improves` antes de publicar;
- média mínima fora da escala;
- frequência mínima sem `attendance_basis` e vice-versa;
- override por conselho sem auditoria;
- ausência de fonte normativa na publicação;
- divergência de `rule_hash`.

Não acessa Mongo, HTTP, autenticação ou motores legados.

---

## 9. Registry/lifecycle

O Registry implementado na Foundation permanece **desconectado das rotas atuais**.

Lifecycle:

```text
DRAFT
  |
  +-- validar --> VALIDATED
  |                 |
  |                 +-- reabrir --> DRAFT
  |                 |
  |                 +-- publicar --> PUBLISHED
  |
  +-- editar somente como DRAFT
```

`PUBLISHED`, `SUPERSEDED` e `RETIRED` são imutáveis para edição normal.

Mudança normativa futura deverá criar nova versão.

### Publicação fail-closed

A publicação exige um `PolicyConflictChecker` explícito.

Sem checker:

`ASSESSMENT_POLICY_CONFLICT_CHECK_REQUIRED`

Com conflito:

`ASSESSMENT_POLICY_CONFLICT`

O checker real será fornecido pelo Resolver na Sprint 002. Logo, a Foundation não permite publicação real por suposição de ausência de conflito.

---

## 10. Multi-tenancy

Toda leitura/mutação do repository exige `mantenedora_id` explicitamente.

Exemplo de chave lógica:

```text
(mantenedora_id, policy_key, version)
```

A mesma `policy_key/version` pode existir em duas mantenedoras sem colisão.

Cross-tenant deve falhar fechado.

---

## 11. Optimistic locking

Cada política possui:

`revision >= 1`

Toda transição/edição substitui o documento somente se a revisão persistida ainda for a esperada.

Exemplo:

```text
Admin A carrega revision=1
Admin B carrega revision=1
Admin A salva -> revision=2
Admin B tenta salvar revision=1
        -> ASSESSMENT_POLICY_CONCURRENT_MODIFICATION
```

Isso evita perda silenciosa de configuração administrativa.

`revision` não participa do hash da regra.

---

## 12. Índices planejados

Foram especificados, mas **não instalados** nesta sprint:

- unique `(mantenedora_id, id)`;
- unique `(mantenedora_id, policy_key, version)`;
- janela de resolução por tenant/status/ano/vigência;
- índices separados por dimensões array de escopo.

Os arrays não são combinados no mesmo índice composto, evitando desenho multikey inválido/limitante no MongoDB.

Nenhum startup hook foi criado.

---

## 13. Scope Creep Guard

A PR possui guard dedicado que autoriza apenas:

- `backend/assessment_policy/**`;
- testes próprios da Foundation;
- documentação de auditoria;
- workflow/guard da própria Foundation.

Mudanças em Notas, Frequência, AEE, Matrícula, Transferência, PDFs etc. fazem o gate falhar.

---

## 14. Política de Floresta do Araguaia

As regras informadas para a mantenedora servem como **fixture/exemplo de validação**, não como regra global do produto:

- 1º/2º Ano: C/ED/ND;
- C=10,0; ED=7,5; ND=5,0;
- 3º Ano: numérico;
- pesos B1=2, B2=3, B3=2, B4=3;
- recuperação substitui menor resultado; empate -> maior peso;
- média mínima por componente = 5,0;
- frequência mínima = 75%.

Pendências antes de publicar a configuração municipal real:

1. associação exata entre cada recuperação e os períodos alcançados;
2. confirmar `only_if_improves`;
3. confirmar `attendance_basis` dos 75%.

Essas pendências não bloqueiam o motor genérico.

---

## 15. Entregáveis da Sprint 001

- [x] branch isolada criada a partir do PR #54;
- [x] Commit Archaeologist;
- [x] Dependency Doctor / matriz de consumidores;
- [x] decisão de não ampliar `mantenedoras.media_aprovacao` como SSoT;
- [x] schema puro da política v1;
- [x] canonicalização/hash determinístico;
- [x] validator puro;
- [x] Registry tenant-scoped;
- [x] lifecycle DRAFT -> VALIDATED -> PUBLISHED;
- [x] publicação fail-closed sem conflict checker;
- [x] imutabilidade após publicação;
- [x] optimistic locking por `revision`;
- [x] índices planejados sem startup hook;
- [x] testes unitários do contrato;
- [x] testes de tenant isolation/lifecycle/concurrency;
- [x] Scope Creep Guard;
- [x] Foundation Gate dedicado.

---

## 16. Proibições preservadas

Nesta sprint:

- não foi alterado o cálculo de `grades`;
- não foi atualizado `final_average`;
- não foi alterado `status`;
- não houve backfill;
- não houve escrita em produção;
- não foi alterada frequência;
- não foi alterado AEE;
- não foi alterada matrícula/transferência;
- PDFs/Boletim/BI continuam no legado;
- nenhuma política foi cadastrada automaticamente;
- nenhuma feature flag de cutover foi ativada.

---

## 17. Gate para Sprint 002 — Resolver

A Sprint 002 só pode iniciar após o PR #55 concluir seus gates e ser integrado ao `main`.

Condições arquiteturais da Foundation:

1. schema/validator estabilizados — **PASS**;
2. hash reproduzível — **PASS**;
3. tenant isolation coberto por testes — **PASS**;
4. lifecycle e imutabilidade cobertos — **PASS**;
5. concorrência otimista coberta — **PASS**;
6. matriz de dependências revisada — **PASS**;
7. runtime atual de Notas não modificado — **PASS por diff**;
8. Scope Creep Guard — **PASS**;
9. CI/regressão — **aguardando o último ciclo da head final do PR**.

Próxima sprint:

> **Sprint 002 — Policy Resolver Multi-Mantenedora:** resolução por tenant, vigência, ano, escola, turma, componente, modalidade/etapa e série efetiva do estudante, com detecção determinística de ambiguidade e sem conectar ainda o novo Calculator ao write-path oficial.
