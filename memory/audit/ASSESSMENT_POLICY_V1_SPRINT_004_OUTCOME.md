# Assessment Policy Multi-Mantenedora v1 — Sprint 004 Academic Outcome

**Status:** EM EXECUÇÃO  
**Branch:** `feat/assessment-policy-outcome-v1`  
**Base:** `21adaf9b70f2d27114e3105d102520c14d1a4359` (merge PR #57)  
**Natureza:** decisão pedagógica pura; **sem ativação no runtime de Notas/Promoção**.

---

## 1. Objetivo

Implementar um `AcademicOutcomeEngine` determinístico que consome resultados finais de componentes já produzidos pelo Calculator e evidência de frequência já produzida pela SSoT de Frequência.

O engine responde ao domínio pedagógico:

> O estudante concluiu a avaliação? Atendeu ao rendimento? Atendeu à frequência? A política prevê algum regime de dependência para a quantidade de componentes não atingidos?

Não é responsabilidade deste engine interpretar status administrativo de matrícula, calcular notas, recalcular frequência, criar dependências no banco, promover matrícula ou aplicar decisão de Conselho de Classe.

---

## 2. Achados do legado

`grade_calculator.calcular_resultado_final_aluno()` e `determinar_resultado_documento()` hoje misturam:

- status administrativos (`transferido`, `desistente`, `falecido`, `remanejado`);
- promoção/conclusão por série;
- completude do 4º bimestre;
- média mínima por componente;
- frequência mínima;
- classificação de componente formativo/regular;
- `APROVADO COM DEPENDÊNCIA`;
- `EM DEPENDÊNCIA`;
- exceções hardcoded por nível/série.

O legado também possui duas implementações semelhantes de resultado, aumentando o risco de divergência.

### Regras hardcoded que NÃO serão transportadas ao novo engine

- Educação Infantil = aprovação/conclusão automática;
- 1º/2º Ano = promoção automática;
- Anos Iniciais = dependência sempre desabilitada;
- 9º Ano/4ª Etapa = `APROVADO COM DEPENDÊNCIA` sempre proibido;
- inferência de série por texto como fonte de regra de resultado.

No novo domínio, diferenças por etapa/série pertencem ao **scope da AssessmentPolicy**.

---

## 3. Dependência é domínio acadêmico próprio

`docs/STUDENT_DEPENDENCY.md` já estabelece dois modos mutuamente exclusivos:

- `with_dependency`: estudante segue em matrícula regular e carrega componentes pendentes;
- `dependency_only`: estudante cursa exclusivamente dependências.

A coleção `student_dependencies` é o vínculo pedagógico concreto. O Outcome Engine NÃO a cria nem altera.

A saída do engine poderá recomendar o modo previsto pela política; um workflow posterior, auditável e autorizado, materializará essa decisão administrativa/pedagógica.

---

## 4. Problema do contrato atual

O campo:

```text
require_all_components: bool
```

é insuficiente.

`false` poderia significar, de forma ambígua:

- média geral;
- tolerar N componentes abaixo da média;
- dependência;
- ignorar componentes opcionais;
- decisão por conselho.

**Decisão:** na v1, o único `ComponentOutcomeStrategy` executável será:

```text
all_required_components
```

`require_all_components` será preservado temporariamente por compatibilidade de schema, mas `false` será rejeitado pelo novo engine/validator até existir estratégia explícita que lhe dê significado.

---

## 5. Regimes de dependência configuráveis

A política passa a declarar faixas explícitas de quantidade de componentes não atingidos.

Exemplo genérico:

```text
dependency.enabled = true

outcomes:
  with_dependency:
    min_failed_components = 1
    max_failed_components = 2

  dependency_only:
    min_failed_components = 3
    max_failed_components = null
```

Isto reproduz uma regra quando uma mantenedora assim decidir, sem codificar séries no produto.

### Invariantes

- faixas devem começar em >= 1;
- `max >= min` quando informado;
- o mesmo modo não pode aparecer duas vezes na v1;
- faixas de modos diferentes não podem se sobrepor;
- sem faixa aplicável, estudante com componente abaixo do mínimo fica `NOT_APPROVED_COMPONENT`;
- escopo da política decide onde a regra vale.

---

## 6. Componentes

Entrada canônica por componente:

```text
component_id
final_average
is_final
required
counts_for_outcome
```

Regras:

- `counts_for_outcome=false` → não participa de aprovação/reprovação;
- componente obrigatório (`required=true`) sem resultado final → outcome `IN_PROGRESS`;
- componente opcional sem resultado → não bloqueia fechamento;
- componente opcional com resultado final e `counts_for_outcome=true` participa do critério;
- média abaixo de `minimum_component_average` gera componente não atingido.

O engine não conhece `atendimento_programa`, AEE ou integral. O adapter futuro é responsável por dizer se o componente participa do resultado.

---

## 7. Frequência

Frequência nunca será recalculada aqui.

O engine recebe evidência canônica conforme `attendance_basis`:

- `global`: um percentual global;
- `stage`: um percentual da etapa/contexto;
- `component`: mapa `component_id -> percentual`.

Sem `minimum_attendance_percentage`, frequência não participa da decisão.

Quando a política exige frequência e a evidência requerida está ausente, o resultado permanece `IN_PROGRESS` — nunca aprova por ausência de dado.

Para `component`, todos os componentes que contam para outcome e possuem avaliação final devem satisfazer o percentual mínimo; componente obrigatório sem frequência suficiente é falha de frequência.

---

## 8. Estados canônicos v1

```text
IN_PROGRESS
APPROVED
WITH_DEPENDENCY
DEPENDENCY_ONLY
NOT_APPROVED_COMPONENT
NOT_APPROVED_ATTENDANCE
NOT_APPROVED_COMPONENT_AND_ATTENDANCE
```

Os rótulos de UI/documento (“Aprovado”, “Reprovado”, “Promovido”, etc.) serão camada de apresentação/institucionalização posterior. O engine trabalha com enum estável.

---

## 9. Precedência da decisão

1. Validar contrato/policy hash.
2. Determinar completude dos componentes obrigatórios.
3. Determinar completude da evidência de frequência exigida.
4. Se faltar dado obrigatório → `IN_PROGRESS`.
5. Identificar componentes abaixo do mínimo.
6. Avaliar frequência.
7. Se frequência falhou, ela não é neutralizada por dependência.
8. Se frequência passou e existem componentes não atingidos, consultar faixas explícitas de dependência.
9. Sem faixa aplicável → `NOT_APPROVED_COMPONENT`.
10. Sem falhas → `APPROVED`.

---

## 10. Conselho de Classe

`CouncilRule` permanece na política, mas o Outcome Engine NÃO altera automaticamente o resultado.

Uma futura operação de override deverá:

- receber resultado canônico original;
- exigir permissão específica;
- exigir justificativa quando configurado;
- gerar evento de auditoria;
- preservar resultado original e decisão substitutiva.

Não haverá `if council.enabled: approved` no engine.

---

## 11. Política de Floresta do Araguaia

A regra informada pela mantenedora pode ser representada, por exemplo, com:

```text
minimum_component_average = 5.0
minimum_attendance_percentage = 75.0
component_strategy = all_required_components
```

A base de frequência (`global`/`component`/`stage`) permanece pendente de confirmação institucional antes de publicar a política municipal real.

Nenhuma regra de dependência de Floresta será inventada nesta sprint.

---

## 12. Fora de escopo

- status administrativos da matrícula;
- promoção/transferência de enrollment;
- criação/alteração de `student_dependencies`;
- Conselho de Classe operacional;
- leitura da frequência no Mongo;
- cálculo da frequência;
- alteração de `grades`/`final_average`;
- Boletim/PDF/Ficha/Histórico;
- UI;
- backfill;
- shadow mode;
- cutover.

---

## 13. Gate

A Sprint 004 só poderá ser integrada quando:

- outcome puro estiver coberto;
- `require_all_components=false` falhar explicitamente;
- componentes incompletos mantiverem `IN_PROGRESS`;
- frequência ausente obrigatória mantiver `IN_PROGRESS`;
- global/stage/component estiverem cobertos;
- faixas de dependência estiverem validadas e sem sobreposição;
- dependência nunca neutralizar falha de frequência;
- Council não alterar resultado automaticamente;
- policy hash/provenance estiver preservado;
- Scope Creep Guard estiver verde;
- regressões anteriores e CI geral estiverem verdes.
