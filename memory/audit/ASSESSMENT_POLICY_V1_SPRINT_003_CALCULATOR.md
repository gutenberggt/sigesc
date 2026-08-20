# Assessment Policy Multi-Mantenedora v1 — Sprint 003 Calculator + Recovery

**Status:** EM EXECUÇÃO  
**Branch:** `feat/assessment-policy-calculator-v1`  
**Base:** `4b21f9994d1aff2f6921df835575303f6443ef73` (merge PR #56)  
**Natureza:** cálculo puro/determinístico; **sem ativação no runtime de Notas**.

---

## 1. Objetivo

Implementar o Calculator/Recovery Engine que recebe uma `AssessmentPolicy` já resolvida e resultados de períodos/recuperações e produz cálculo reproduzível, explicado e sem efeitos colaterais.

Esta sprint NÃO decide aprovação/reprovação, NÃO consulta frequência, NÃO escreve `grades` e NÃO substitui `grade_calculator.py`/rotas legadas.

---

## 2. Invariantes

1. Mesma política + mesmas entradas = mesmo resultado.
2. Nenhum acesso a Mongo, HTTP, autenticação ou LLM dentro do cálculo.
3. Valores ausentes nunca viram zero implicitamente.
4. Média parcial e média final são conceitos diferentes.
5. Conceitos são convertidos exclusivamente pela escala da política.
6. Nota numérica respeita a escala configurada.
7. Recuperação usa somente grupos explicitamente configurados.
8. Empates são resolvidos somente pela estratégia da política; empate ainda não resolvido falha fechado.
9. `only_if_improves` deve estar definido para executar recuperação.
10. Grupos de recuperação sobrepostos no mesmo período são rejeitados na v1.
11. Arredondamento usa `ROUND_HALF_UP`, não `round()` binário do Python.
12. Resultado inclui explicação determinística e provenance da política.
13. Nenhuma regra de Floresta do Araguaia será hardcoded.

---

## 3. Modos executáveis nesta sprint

### NUMERIC

Entradas de período/recuperação são números. O valor precisa estar dentro de `numeric_scale.minimum..maximum`.

### CONCEPTUAL

Entradas são códigos definidos em `conceptual_scale`. Exemplo de uma mantenedora:

```text
C  -> 10,0
ED -> 7,5
ND -> 5,0
```

O exemplo acima é configuração, não regra do motor.

`DESCRIPTIVE` e `SKILL_BASED` permanecem no contrato, mas Calculator v1 falha explicitamente se forem enviados para cálculo numérico.

---

## 4. Períodos ausentes

O legado atual converte `None` para zero. O novo motor não herdará essa semântica.

Se existem B1 e B2, mas B3/B4 ainda não foram lançados:

```text
current_average = cálculo parcial segundo partial_divisor
final_average   = None
is_final        = false
```

Somente quando todos os períodos `required_for_final=true` estiverem presentes o motor produz `final_average`.

---

## 5. Média ponderada

Para `weighted_average`:

```text
numerador = Σ(valor_efetivo × peso)
```

Parcial:

- `sum_available_weights`: divisor = soma dos pesos dos períodos presentes;
- `sum_all_weights`: divisor = soma dos pesos participantes configurados.

Final:

- `sum_all_weights`: divisor = soma dos pesos dos períodos obrigatórios + opcionais presentes.

Período opcional ausente não deve reduzir média final.

---

## 6. Média simples

Para `simple_average`, cada período participante vale uma unidade no cálculo; `PeriodRule.weight` não multiplica o valor da média simples.

- parcial `sum_available_weights` -> quantidade de períodos presentes;
- parcial `sum_all_weights` -> quantidade de períodos participantes;
- final -> quantidade de períodos obrigatórios + opcionais presentes.

O peso continua disponível para estratégias explícitas de desempate de recuperação.

---

## 7. Recuperação v1

Estratégia executável:

`replace_lowest`

Para cada grupo com entrada de recuperação:

1. considerar somente períodos do grupo que possuem resultado;
2. encontrar o menor valor efetivo;
3. em empate, aplicar `tie_break`:
   - `highest_weight`;
   - `earliest_period`;
   - `latest_period`;
4. se o desempate ainda resultar em mais de um candidato, falhar fechado;
5. se `only_if_improves=true`, substituir somente quando recuperação > resultado atual;
6. se `only_if_improves=false`, substituir sempre.

A v1 rejeita grupos configurados que disputam o mesmo período. Isso evita recuperação sequencial implícita e não documentada.

---

## 8. Erros de domínio planejados

- `ASSESSMENT_CALCULATION_MODE_UNSUPPORTED`
- `ASSESSMENT_CALCULATION_UNKNOWN_PERIOD`
- `ASSESSMENT_CALCULATION_VALUE_INVALID`
- `ASSESSMENT_CALCULATION_VALUE_OUT_OF_SCALE`
- `ASSESSMENT_CALCULATION_UNKNOWN_CONCEPT`
- `ASSESSMENT_RECOVERY_UNKNOWN_INPUT`
- `ASSESSMENT_RECOVERY_RULE_INCOMPLETE`
- `ASSESSMENT_RECOVERY_NO_ELIGIBLE_PERIOD`
- `ASSESSMENT_RECOVERY_TIE_UNRESOLVED`

---

## 9. Resultado canônico do cálculo

O resultado deve expor, no mínimo:

```text
current_average
final_average
is_final
original_values
final_values
period_weights
recoveries_applied
numerator
divisor
policy_id
policy_version
rule_hash
```

Esses dados serão a base futura do shadow mode e da explicação “Como esta média foi calculada?”.

---

## 10. Fora de escopo

- `AcademicOutcomeEngine` (aprovação/reprovação);
- Attendance SSoT;
- gravação em `grades`;
- alteração de `final_average` legado;
- rotas de Notas;
- Boletim/PDF/Ficha/Histórico;
- UI;
- backfill;
- shadow mode contra dados reais;
- publicação de política municipal real.

---

## 11. Gate para próxima fase

A próxima fase só pode iniciar quando:

- numeric e conceptual estiverem cobertos;
- média parcial/final estiver coberta;
- `ROUND_HALF_UP` estiver comprovado;
- recovery `replace_lowest` e todos os tie-breaks estiverem cobertos;
- regras incompletas falharem fechado;
- nenhum `None` virar zero;
- provenance estiver presente;
- Scope Creep Guard estiver verde;
- CI/regressões gerais estiverem verdes.
