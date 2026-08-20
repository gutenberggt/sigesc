# Assessment Policy Multi-Mantenedora v1 — Sprint 002 Resolver

**Status:** EM EXECUÇÃO  
**Branch:** `feat/assessment-policy-resolver-v1`  
**Base:** `437d142ab04ff5a4de4f8f22e86cc6f74e6055e9` (merge PR #55)  
**Natureza:** resolução read-only de política; **sem substituir cálculo de Notas**.

---

## 1. Objetivo

Implementar o `PolicyResolver` determinístico que responde:

> Qual versão publicada da política avaliativa pertence a esta mantenedora e está vigente para este estudante, escola, turma, série efetiva, componente, etapa/modalidade, ano letivo e data de referência?

A Sprint 002 não calcula média, não aplica recuperação, não grava `grades` e não altera `final_average`/`status`.

---

## 2. Invariantes

1. Tenant fail-closed: política de outra mantenedora nunca é candidata.
2. Somente `published` pode ser resolvida para uso oficial.
3. `academic_year` e vigência devem conter o contexto solicitado.
4. `rule_hash` publicado deve ser íntegro/reproduzível.
5. A série efetiva vem prioritariamente da matrícula anual.
6. Em turma multisseriada, ausência de série individual confiável bloqueia a resolução.
7. `class.grade_level` só é fallback seguro para turma não multisseriada.
8. Política mais específica prevalece sobre política geral.
9. Empate real de especificidade entre políticas aplicáveis falha fechado.
10. Ausência de política aplicável falha fechado.
11. Nenhum fallback global do SIGESC para média, conceitos, pesos ou aprovação.
12. Nenhum write no Mongo nesta sprint.

---

## 3. Série efetiva do estudante

Ordem de evidência planejada:

1. `enrollments.student_series` em matrícula da mesma turma e ano letivo;
2. `students.student_series` somente para contexto corrente e coerente com a turma;
3. `classes.grade_level` somente quando a turma não for multisseriada.

Turma é considerada multisseriada quando houver evidência explícita, por exemplo:

- `is_multi_grade=true`; ou
- `series` com mais de uma série distinta.

Se for multisseriada e a matrícula/estudante não fornecer série individual:

`ASSESSMENT_STUDENT_SERIES_REQUIRED`

O comportamento legado que usa `class.grade_level` em multisseriada permanece intacto nas rotas atuais durante a transição; o novo Resolver não herdará esse risco.

---

## 4. Contexto canônico

O Resolver trabalhará com um contexto explícito:

```text
mantenedora_id
school_id
class_id
student_id
component_id (opcional)
academic_year
reference_date
student_series
effective education_stage (opcional)
effective modality (opcional)
```

A construção do contexto será separada do algoritmo puro de seleção de política.

---

## 5. Matching de escopo

Uma dimensão `None` na política significa sem restrição. Lista configurada exige presença do valor contextual correspondente.

Dimensões:

- `school_ids`
- `class_ids`
- `series`
- `component_ids`
- `education_stages`
- `modalities`

Se uma política restringir uma dimensão que o contexto não consegue resolver, ela não poderá ser escolhida silenciosamente.

---

## 6. Precedência

A precedência seguirá dois níveis:

### Tier administrativo

1. turma + componente;
2. turma;
3. escola + componente;
4. escola;
5. mantenedora/contexto + componente;
6. mantenedora/contexto;
7. mantenedora geral.

### Especificidade contextual

Dentro do mesmo tier, ganha a política que restringe mais dimensões contextuais aplicáveis (`series`, `education_stages`, `modalities`).

O tamanho da lista não desempata. Duas políticas igualmente específicas que se sobrepõem no mesmo contexto representam ambiguidade de configuração.

Erro:

`ASSESSMENT_POLICY_AMBIGUOUS`

---

## 7. Integridade da política publicada

Antes de retornar uma política:

```text
stored rule_hash == calculate_rule_hash(policy)
```

Caso contrário:

`ASSESSMENT_POLICY_INTEGRITY_ERROR`

Nunca executar cálculo oficial com regra publicada adulterada/inconsistente.

---

## 8. Conflict Checker de publicação

A Sprint 001 deixou a publicação fail-closed até existir verificador real de conflito.

A Sprint 002 implementará o `PolicyConflictChecker` utilizando as mesmas regras de interseção/especificidade do Resolver:

- políticas de escopos disjuntos podem coexistir;
- política mais específica pode coexistir como override;
- duas políticas publicadas de igual especificidade que possam resolver o mesmo contexto são conflito de publicação.

Isso permitirá publicar versões sem abrir brecha para resolução ambígua.

---

## 9. Fora de escopo

- Calculator;
- Recovery Engine;
- Academic Outcome Engine;
- UI de cadastro;
- endpoints administrativos públicos;
- startup/index installation;
- feature flag de cutover;
- shadow mode;
- backfill;
- alteração de notas/boletins/PDFs.

---

## 10. Gate para Sprint 003

A Sprint 003 (Calculator/Recovery determinísticos) só poderá iniciar quando:

- resolução tenant-scoped estiver testada;
- multisseriação fail-closed estiver testada;
- vigência/ano estiverem testados;
- overrides de escola/turma/componente estiverem testados;
- ambiguidade estiver fail-closed;
- hash publicado for verificado;
- conflict checker estiver alinhado ao Resolver;
- nenhum runtime legado de Notas tiver sido alterado;
- CI/regressão estiver verde.
