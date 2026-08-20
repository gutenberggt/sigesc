# Assessment Policy v1 — Dependency Matrix

**Sprint:** 001 Foundation  
**Base auditada:** `6024474873ffed4ada9d0b0d5bd0bd4601d56ff8`  
**Objetivo:** registrar produtores, calculadores, consumidores e decisões que precisarão migrar para a futura SSoT.

> Esta matriz é documental. Nenhum arquivo legado listado abaixo é alterado nesta sprint.

---

## 1. Motores/regras concorrentes confirmados

| Origem | Papel atual | Achado | Destino planejado |
|---|---|---|---|
| `backend/routers/grades.py` | cálculo derivado após escrita | motor aritmético legado ativo em rotas de notas | encapsular no shadow; retirar do papel de SSoT após cutover |
| `backend/grade_calculator.py` | cálculo ponderado + situação/documentos | pesos/mínimos hardcoded + regras por série | decompor em políticas/configuração; não promover diretamente |
| `frontend/src/components/grades/gradeHelpers.jsx` | conceitos/cálculo visual | lógica conceitual própria, incluindo maior conceito | frontend deixa de calcular resultado canônico |
| `frontend/src/pages/Grades.js` | orquestração/UI | consome helpers e derivados | consumir resposta canônica futura |
| `frontend/src/components/grades/AlunoTab.jsx` | visão por estudante | síntese conceitual local | consumir resposta canônica futura |

---

## 2. Achados do Commit Archaeologist

### A-001 — média e frequência hardcoded

`backend/grade_calculator.py` contém constantes globais de pesos, média mínima e frequência mínima. Isso não pode representar múltiplas mantenedoras.

### A-002 — parametrização parcial já existe na mantenedora

`backend/models.py` já expõe:

- `media_aprovacao`;
- `frequencia_minima`;
- regras de dependência.

Esses campos ajudam na compatibilidade, mas não têm versão/vigência/hash e não descrevem política avaliativa completa.

### A-003 — recuperação ponderada tem inconsistência de empate

No motor ponderado atual:

- comentário/intenção declara priorização do bimestre de maior peso em empate;
- implementação de `rec_s1` usa `b1 <= b2`, portanto escolhe B1 quando B1 == B2;
- implementação equivalente no segundo grupo escolhe B3 quando B3 == B4.

Isso é incompatível com a regra de desempate por maior peso (B2/B4 no conjunto 2/3/2/3).

**Decisão:** não corrigir nesta Sprint 001, porque isso mudaria cálculo de produção. Registrar e cobrir no futuro motor canônico.

### A-004 — média parcial do motor ponderado trata ausentes como zero

O motor ponderado atual converte `None` em 0 e divide sempre pela soma total dos pesos. Isso mistura "período ainda não realizado" com nota zero.

O contrato v1 separa média parcial e final e permite `partial_divisor=sum_available_weights`.

### A-005 — política conceitual está codificada por série/nível

Os testes e helpers atuais assumem determinadas séries como conceituais/promovidas. No estado-alvo, isso deverá ser decisão da política resolvida da mantenedora.

---

## 3. Matriz de dependências

Legenda de papel:

- **WRITE**: grava dados avaliativos/derivados;
- **CALC**: contém fórmula/regra;
- **DECIDE**: determina situação/resultado;
- **DOC**: gera documento oficial;
- **READ**: exibe/consulta;
- **BI**: agrega indicador/risco;
- **SCHEMA**: contrato/configuração;
- **AUDIT**: teste/script/documentação.

| Arquivo | Papel | Dependência observada | Risco de cutover | Ordem futura |
|---|---|---|---|---|
| `backend/routers/grades.py` | WRITE/CALC | `final_average`, recuperação, status | CRÍTICO | shadow/cutover do write engine |
| `backend/routers/grades_dvd.py` | WRITE | chama fluxo de cálculo após escrita DVD | CRÍTICO | junto do write engine |
| `backend/grade_calculator.py` | CALC/DECIDE | pesos, recuperação, mínimos, conceitos, resultado | CRÍTICO | substituir por adapters para policy engine |
| `backend/models.py` | SCHEMA | campos B1-B4, recuperação e regras na mantenedora | ALTO | compatibilidade/migração de schema |
| `backend/utils/bulletin_builder.py` | DOC/CALC | `final_average` e recuperação | ALTO | consumir resultado canônico |
| `backend/pdf/boletim.py` | DOC/CALC/DECIDE | regras da mantenedora + recuperação + resultado | CRÍTICO | migrar após engine estabilizado |
| `backend/pdf/ficha_individual.py` | DOC/CALC/DECIDE | regras da mantenedora + resultado | CRÍTICO | migrar após boletim |
| `backend/pdf/notas.py` | DOC/READ | B1-B4, recuperação, `final_average` | ALTO | consumir projeção canônica |
| `backend/pdf/historico_escolar.py` | DOC/READ | média de aprovação/resultados históricos | CRÍTICO | somente após política histórica resolvível |
| `backend/routers/student_history.py` | READ/DECIDE | média de aprovação/histórico | CRÍTICO | política histórica/snapshot |
| `backend/services/history_consolidator.py` | DECIDE | regras de aprovação/consolidação | CRÍTICO | usar AcademicOutcome canônico |
| `backend/routers/history_reconstruction.py` | READ/WRITE | campos avaliativos/reconstrução | ALTO | preservar ledger e proveniência |
| `backend/routers/student_portal.py` | READ/CALC | média/recuperação | ALTO | somente leitura canônica |
| `backend/routers/documents.py` | DOC/READ | campos de recuperação | ALTO | depois dos geradores canônicos |
| `backend/routers/dependency_completions.py` | DECIDE | `final_average`/dependência | ALTO | AcademicOutcome/Dependency policy |
| `backend/services/pedagogical_consolidation.py` | BI/DECIDE | recuperação/resultados | ALTO | consumir read model canônico |
| `backend/routers/analytics.py` | BI | agrega `final_average` e aprovação | CRÍTICO | migrar para BI SSoT após cutover |
| `backend/services/academic_risk_engine.py` | BI | usa `final_average`/recuperação | ALTO | read model canônico |
| `backend/scripts/top100_desempenho_alunos.py` | BI/AUDIT | usa `final_average` | MÉDIO | atualizar após BI |
| `frontend/src/components/grades/gradeHelpers.jsx` | CALC/READ | conceitos, recuperação, síntese | CRÍTICO | remover fórmula paralela |
| `frontend/src/components/grades/GradesTable.jsx` | READ/WRITE | B1-B4/recuperação/resultado | ALTO | policy-aware UI |
| `frontend/src/components/grades/AlunoTab.jsx` | READ/WRITE/CALC | síntese conceitual local | CRÍTICO | resultado vindo do backend |
| `frontend/src/pages/Grades.js` | READ/WRITE/CALC | orquestra regras visuais | ALTO | policy resolver context |
| `frontend/src/pages/BulletinViewer.jsx` | READ | `final_average`/recuperação | MÉDIO | consumir boletim canônico |
| `frontend/src/pages/BoletimAluno.jsx` | READ | média/regras | MÉDIO | consumir boletim canônico |
| `frontend/src/pages/Promotion.jsx` | DECIDE/READ | série conceitual e aprovação | CRÍTICO | AcademicOutcome canônico |
| `frontend/src/pages/Mantenedora.js` | SCHEMA/WRITE | `media_aprovacao` e regras atuais | ALTO | nova seção de Policy Registry |
| `backend/routers/mantenedora.py` | SCHEMA/WRITE | CRUD atual da mantenedora | MÉDIO | não embutir nova política no doc da mantenedora |
| `backend/routers/tenant_admin.py` | SCHEMA | administração multi-tenant | MÉDIO | RBAC/tenant boundary do Registry |

---

## 4. Testes/auditorias que representam comportamento legado

Estes testes NÃO deverão ser apagados para fazer a nova arquitetura passar. Durante shadow/cutover, devem ser classificados como contrato legado ou reescritos somente quando o comportamento oficial mudar deliberadamente:

- `backend/tests/test_status_conceitual.py`;
- `backend/tests/test_professor_grades_full_parity_p0.py`;
- `tests/test_zero_grade_bug.py`;
- `tests/test_mandatory_no_grade_bug.py`;
- testes de boletim/histórico/analytics relacionados.

---

## 5. Plano de migração dos consumidores

Ordem deliberada:

1. Registry + schema + validator (sem runtime de notas).
2. Resolver multi-mantenedora.
3. Calculator/Recovery puros.
4. Shadow adapter no write path, sem alterar valor oficial.
5. Dry-run por mantenedora/ano.
6. Cutover controlado do cálculo derivado.
7. `Grades` UI e leituras.
8. Boletim e Ficha Individual.
9. Histórico/Reconstrução.
10. Academic Outcome/Promoção/Dependência.
11. BI/Risco/Consolidação.
12. Remoção final das fórmulas paralelas, após comprovação de zero consumidores.

---

## 6. Gates para remover um legado

Nenhuma função/fórmula antiga pode ser removida até que:

- seu conjunto de consumidores esteja zerado ou adaptado;
- shadow mode comprove equivalência quando aplicável;
- divergências intencionais estejam documentadas por política;
- documentos oficiais tenham sido validados;
- histórico permaneça reproduzível;
- rollback esteja definido.

---

## 7. Resultado da Foundation até este ponto

A arquitetura não deve "corrigir `grade_calculator.py`" e reutilizá-lo diretamente. A solução correta é:

```text
legados (vários)
      |
      +--> Commit Archaeologist / Dependency Doctor
                    |
                    v
             regras explicitadas
                    |
                    v
        AssessmentPolicy versionada
                    |
                    v
          motor puro determinístico
```

Os legados permanecem intactos até o shadow/cutover por mantenedora.
