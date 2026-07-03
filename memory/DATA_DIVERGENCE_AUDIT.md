# DATA_DIVERGENCE_AUDIT.md — Auditoria de Divergência de Dados (Sprint BI-1A.5)

> **100% READ-ONLY.** Nenhum dado, código, coleção, API ou comportamento alterado.
> Evidências extraídas por script de leitura reproduzível:
> `audit/scripts/data_divergence_audit.py` (usa `MONGO_URL`/`DB_NAME`, apenas `find`/`count`).
>
> ⚠️ **ESCOPO DOS NÚMEROS:** os valores abaixo foram medidos no **ambiente de PREVIEW**
> (base `sigesc` disponível ao agente), que contém **dados de teste/homologação**.
> Eles **comprovam a metodologia e a existência dos problemas D2/D6**, mas **NÃO
> representam a produção**. Antes da BI-1B, o **mesmo script deve ser executado na
> base de PRODUÇÃO** (read-only) para obter os números oficiais. As conclusões
> qualitativas (existência de órfãos, status não-canônicos, divergência de vínculo)
> são válidas; a magnitude precisa ser reconfirmada em produção.

Data-base da medição (preview): Jun/2026.

---

## Entrega 1 — Auditoria D2 (Vínculo Aluno ↔ Turma)
### Contagens base (preview)
| Métrica | Valor |
|---|---|
| Alunos (`students`) | 23 |
| Matrículas (`enrollments`) | 165 |
| Vínculos em `class_students` | **0** (coleção vazia no preview) |
| Alunos com `students.class_id` preenchido | 18 |
| Alunos com `class_id` vazio | 5 |
| Turmas (`classes`) | 81 |
| Escolas (`schools`) | 6 |

### Representações do vínculo (quantas fontes)
São **3 representações** possíveis do vínculo aluno↔turma no schema:
1. `enrollments` (student_id + class_id + academic_year + status) — **fonte candidata a canônica**.
2. `students.class_id` — atalho denormalizado (turma "atual").
3. `class_students` — lista turma→alunos (**vazia no preview**; pode existir em produção).

> **Fonte principal hoje:** o sistema usa um **fallback combinado** (matrícula ativa
> OU `student.class_id` OU `class.grade_level`), o que é justamente a causa de bugs.
> Não há **uma** fonte única declarada — confirmando o achado D2.

### Consistência e divergência
Entre os 18 alunos com `class_id` preenchido:
| Situação | Qtde | % |
|---|---|---|
| Consistente (`class_id` bate com matrícula ativa) | 16 | 88,89% |
| **Divergente** (`class_id` ≠ turma da matrícula ativa) | **2** | **11,11%** |
| Sem matrícula | 0 | 0% |

Exemplos de divergência (anonimizados por id):
- Aluno `62b4…112e`: `class_id=e370…d5d2`, mas matrícula ativa aponta `c09b…8ecd`.
- Aluno `159a…65c3`: `class_id=c09b…8ecd`, porém **sem** matrícula ativa (aponta para vínculo não-ativo).

### Órfãos e referências quebradas (preview)
| Problema | Qtde | Interpretação |
|---|---|---|
| Matrículas cujo `student_id` **não existe** em `students` | **137** | matrículas órfãs (aluno removido/dado de teste) |
| Matrículas cujo `class_id` **não existe** em `classes` | **89** | turma inexistente/renomeada |
| Matrículas cujo `school_id` **não existe** em `schools` | 9 | escola inexistente |
| `students.class_id` apontando p/ turma inexistente | 2 | referência quebrada |
| Matrículas **totalmente válidas** (aluno+turma+escola existem) | **19 / 165 (11,5%)** | restante é ruído de teste |

### Inconsistências temporais/estruturais
| Problema | Qtde |
|---|---|
| Matrícula com `school_id` ≠ `school_id` da sua turma | 8 |
| Alunos com **>1 matrícula ativa** no mesmo ano letivo | 1 |

> **Leitura crítica:** no preview, a maioria das matrículas são **órfãs de teste**
> (137/165). Ainda assim, o padrão comprova D2: convivência de múltiplas fontes,
> divergência mensurável e referências quebradas. **Em produção, a proporção de
> órfãos deve ser muito menor** — reexecutar o script para o número real.

---

## Entrega 2 — Mapa Completo das Dependências D2
Consumidores do vínculo aluno↔turma (evidência de código — auditorias anteriores):

| Camada | Consumidor | Criticidade | Freq. uso | Risco de regressão |
|---|---|---|---|---|
| API | `enrollments.py`, `students.py`, `classes.py` | Alta | Alta | **Alto** |
| API | `grades.py` (grid por turma, multisseriada) | Alta | Alta | **Alto** |
| API | `attendance.py` (lista de alunos da turma) | Alta | Alta | **Alto** |
| API | `documents.py`/`promotion` (livro/boletim) | Alta | Média | Alto |
| API | `professor.py` (turmas/alunos do professor) | Média | Alta | Médio |
| Página | `Students*`, `Classes`, `Grades`, `Attendance`, `Promotion` | Alta | Alta | Alto |
| Dashboard | Analytics, PME (matrícula/rendimento por turma) | Média | Média | Médio |
| Relatório | Boletim, Ficha, Livro de Promoção, Ata | Alta | Média | Alto |
| Serviço | `grade_calculator`, `attendance_utils`, `pedagogical_consolidation` | Alta | Alta | Alto |
| IA/BI (futuro) | fatos de matrícula do Motor de Indicadores | Alta | — | Alto (pré-requisito) |

**Conclusão:** o vínculo é dependência **crítica e de alta frequência** — a migração
exige feature-flag, dual-write e regressão ampla (ver plano final).

---

## Entrega 3 — Auditoria D6 (Status Legados)
### Distribuição de status em `enrollments` (preview)
| Status | Qtde | Canônico? |
|---|---|---|
| active | 116 | ✅ |
| transferred | 18 | ✅ |
| relocated | 18 | ✅ |
| dropout | 7 | ✅ |
| **inactive** | **3** | ❌ legado |
| **reclassified** | **1** | ❌ legado |
| progressed | 1 | ✅ |
| cancelled | 1 | ✅ |

### Distribuição de status em `students` (preview)
| Status | Qtde | Observação |
|---|---|---|
| active | 19 | ✅ |
| **inactive** | 3 | legado (equivalente a cancelado/desligado) |
| transferred | 1 | ✅ |

### Análise
- **Valores diferentes (enrollments):** 8 (dos quais **2 não-canônicos**: `inactive`, `reclassified`).
- **Equivalências propostas:** `inactive → cancelled`; `reclassified → progressed`
  (consistente com o `field_validator` já existente em `models.py::EnrollmentBase`).
- **Obsoletos:** `inactive`, `reclassified` (não pertencem ao conjunto oficial).
- **Necessários por compatibilidade (na leitura):** manter tolerância via `field_validator`
  mesmo após migração, para dados históricos externos.
- **Conjunto OFICIAL após padronização (`enrollments`):**
  `active · completed · cancelled · transferred · relocated · progressed · dropout`.

---

## Entrega 4 — Matriz de Migração (resumo; detalhe em BI-1B_FINAL_MIGRATION_PLAN.md)
| Objeto | Alteração | Qtde estimada (preview→prod a confirmar) | Dependências | Impacto funcional | Risco | Rollback |
|---|---|---|---|---|---|---|
| `enrollments.status` | coerção `inactive→cancelled`, `reclassified→progressed` | 4 no preview | leitura de matrículas | Nenhum (valores equivalentes) | Baixo | snapshot + reversão por lote |
| `students.status` | coerção `inactive→` valor oficial | 3 no preview | listagens/filtros | Baixo | Baixo | snapshot + reversão |
| Vínculo (D2) | eleger `enrollments` como fonte; derivar `class_id`/`class_students` | vínculos divergentes (2/18 no preview) | núcleo (notas/freq./promoção) | Médio/Alto | **Alto** | feature-flag + dual-write + backup |
| Órfãos | quarentena/arquivamento de matrículas órfãs | 137 no preview (ruído de teste) | relatórios/contagens | Médio | Médio | mover p/ coleção `*_quarantine` (reversível) |

---

## Entrega 5 — Dry-Run (simulação lógica, SEM alterar dados)
Projeção com base nos números do preview (reconfirmar em produção):
| Métrica da simulação | Valor (preview) |
|---|---|
| Registros que **seriam modificados** (D6 status) | 7 (4 enroll + 3 student) |
| Registros que **permaneceriam inalterados** (D6) | 181 |
| Vínculos que **seriam reconciliados** (D2) | 2 divergentes |
| Matrículas órfãs que **exigiriam intervenção/quarentena** | 137 (revisão humana — provável ruído de teste) |
| Conflitos que exigiriam **decisão manual** | 1 (aluno com >1 matrícula ativa/ano) |
| Estimativa de duração (preview, ~200 docs) | < 1s |
| Estimativa de duração (produção) | **a medir** — proporcional ao volume; esperado poucos minutos com índices |

> Dry-run **não** escreveu nada. Em produção, o script pode ser estendido para modo
> `--report-only` produzindo estes mesmos números sem qualquer escrita.

---

## Entrega 6 — Relatório de Qualidade dos Dados
| Domínio | Consistência estimada (preview) | Principais problemas | Recomendação |
|---|---|---|---|
| **Alunos** | ~78% | 5/23 sem escola válida (ruído) | validar `school_id` na migração |
| **Matrículas** | **~11,5%** (preview poluído) | 137 órfãs de aluno, 89 de turma | **quarentena de órfãos** + reexecutar em produção |
| **Turmas** | Alta (81 íntegras) | — | ok |
| **Escolas** | Alta (6) | — | ok |
| **Componentes** | Não medido nesta rodada | — | incluir em auditoria específica |
| **Professores** | Base mínima no preview (2) | amostra insuficiente | medir em produção |
| **Frequência** | Não medido (fora do escopo D2/D6) | — | auditar antes de BI-2 (fatos) |
| **Avaliações/Notas** | Não medido | — | auditar antes de BI-2 |
| **Indicadores** | Inexistentes (Motor não implementado) | — | nascem no Motor (BI-2) |

**Justificativa:** a baixíssima consistência de matrículas no preview decorre de
**dados de teste órfãos**, não necessariamente de defeito de produção — por isso a
**reexecução em produção é obrigatória** antes de qualquer decisão de migração.

---

## Síntese
- **D2 confirmado:** múltiplas fontes de vínculo, divergência mensurável (11,11% no
  preview entre alunos com `class_id`) e referências quebradas.
- **D6 confirmado:** valores não-canônicos reais (`inactive`, `reclassified`) em
  matrículas e alunos.
- **Bloqueio metodológico:** os números de magnitude são do **preview** — a liberação
  da BI-1B depende de **reexecutar `data_divergence_audit.py` em produção**.

➡️ Plano de execução, segurança, rollback, validação e critérios objetivos:
[`BI-1B_FINAL_MIGRATION_PLAN.md`](BI-1B_FINAL_MIGRATION_PLAN.md).
