# Assessment Policy Multi-Mantenedora v1 — Sprint 005 Shadow/Dry-run Foundation

**Status:** EM EXECUÇÃO  
**Branch:** `feat/assessment-policy-shadow-v1`  
**Base:** `ff9389297a4c459335b5d44edfbb973ed84e4897` (merge PR #58)  
**Natureza:** comparação read-only; **zero escrita e zero cutover**.

---

## 1. Objetivo

Criar a fundação de shadow/dry-run que compare:

```text
valor legado efetivamente persistido
             vs
resultado do Assessment Policy Engine v1
```

sem recalcular o legado, sem atualizar `grades`, sem mudar `final_average`, sem alterar `status` e sem publicar automaticamente qualquer política.

---

## 2. Princípio de comparação

O lado legado é evidência histórica observada:

```text
grades.final_average
```

O shadow NÃO chamará `calculate_and_update_grade()` nem qualquer função legada que possa escrever no Mongo.

O lado novo é obtido exclusivamente por:

```text
AssessmentPolicy + snapshot de inputs
        -> Calculator/Recovery v1
```

Outcome poderá ser comparado em fase posterior quando houver evidência canônica de frequência e uma política institucional completa.

---

## 3. Snapshot legado

O modelo atual de `GradeBase` possui, entre outros:

```text
student_id
class_id
course_id
academic_year
b1
b2
b3
b4
rec_s1
rec_s2
recovery
final_average
status
```

A fundação shadow tratará esse documento como snapshot read-only.

---

## 4. Mapeamento explícito obrigatório

O shadow não pressupõe que nomes de campos legados são nomes canônicos da política.

Entrada obrigatória:

```text
period_field_map:
  b1 -> <policy period code>
  b2 -> <policy period code>
  ...

recovery_field_map:
  rec_s1 -> <policy recovery input code>
  rec_s2 -> <policy recovery input code>
  recovery -> <policy recovery input code>
```

Somente campos explicitamente mapeados são enviados ao Calculator.

Isso é necessário porque a associação operacional das recuperações de Floresta do Araguaia ainda depende de confirmação institucional. Nenhum vínculo `rec_s1=B1/B2` será transformado em regra oficial por inferência do código legado.

---

## 5. Classificações do shadow

Para média por componente:

```text
MATCH
DIFFERENT
BOTH_INCOMPLETE
NEW_INCOMPLETE
LEGACY_MISSING
ERROR
```

### MATCH

Novo `final_average` existe e é igual ao legado segundo uma tolerância decimal declarada.

### DIFFERENT

Ambos existem, mas diferem além da tolerância.

### BOTH_INCOMPLETE

Nem o legado possui `final_average` persistido nem a política nova considera o conjunto de períodos suficiente para produzir `final_average`. Não entra no denominador de `match_rate`.

### NEW_INCOMPLETE

Legado possui `final_average`, mas a política nova ainda não considera o conjunto de períodos suficiente para fechamento.

### LEGACY_MISSING

Novo motor produz resultado final, mas o legado não possui `final_average` persistido.

### ERROR

O snapshot não pode ser avaliado de forma segura — política inválida, contexto anual incompatível, conceito incompatível, recuperação ambígua etc.

---

## 6. Tolerância

Comparações usarão `Decimal`, nunca float binário.

A tolerância será argumento explícito, por padrão:

```text
0.01
```

Ela não altera cálculos; serve apenas para classificar equivalência do relatório.

---

## 7. Provenance do relatório

Cada comparação deve carregar:

```text
grade_id
student_id
class_id
course_id
academic_year
legacy_final_average
new_current_average
new_final_average
new_is_final
delta
absolute_delta
classification
policy_id
policy_version
rule_hash
mapping_hash
error_code (quando houver)
```

O `mapping_hash` prova qual mapeamento legado→política foi utilizado. O `rule_hash` deve continuar disponível inclusive nos registros classificados como `ERROR`, para que o relatório preserve qual regra foi tentada.

---

## 8. Batch report

O agregador puro deverá produzir:

```text
total
matches
differences
both_incomplete
new_incomplete
legacy_missing
errors
comparable
match_rate
max_absolute_delta
policy_ids/rule_hashes usados
mapping_hash
```

`match_rate` é calculado somente sobre registros comparáveis:

```text
matches / (matches + differences)
```

Casos incompletos ou com erro não são convertidos artificialmente em divergência nem em equivalência.

Sem gravar o relatório no Mongo.

---

## 9. Regras de segurança

- nenhuma função shadow pode executar `insert`, `update`, `replace`, `delete` ou `bulk_write`;
- nenhum código legado mutador será chamado;
- nenhum `final_average` será atualizado;
- nenhum `status` será atualizado;
- snapshot de ano diferente de `policy.academic_year` deve resultar em `ERROR`, nunca comparação cruzada silenciosa;
- erro por snapshot é registrado como `ERROR`, não corrigido automaticamente;
- erro de configuração do mapeamento/tolerância invalida o lote inteiro, porque um relatório produzido com configuração errada seria enganoso;
- política deve ser fornecida explicitamente ou resolvida por adapter read-only futuro;
- política real de Floresta não será criada enquanto parâmetros institucionais pendentes não forem confirmados.

---

## 10. Fora de escopo desta Foundation

- acesso ao Mongo de produção;
- policy admin API/UI;
- criação de política municipal real;
- frequência real;
- Outcome shadow;
- remediação de divergências;
- backfill;
- feature flag de cutover;
- alteração dos consumidores de `final_average`.

---

## 11. Gate para dry-run de produção

Somente avançar para adapter read-only de produção quando:

- comparador puro estiver testado;
- mapping explícito estiver testado;
- mapping hash for reproduzível;
- incompatibilidade de ano política/snapshot falhar fechado;
- agregação não perder erros/divergências;
- Scope Creep Guard estiver verde;
- CI/regressões anteriores estiverem verdes;
- parâmetros reais da política a testar forem fornecidos explicitamente;
- execução de produção continuar `MONGO_WRITES=0`.
