# LUIZ-GOMES — R1.0B — Schema Bridge Forense do dump de 18/08/2026

**Data:** 2026-09-05  
**Tracking:** #422 → #418 → #357  
**Escopo:** Luiz Gomes dos Santos — Matemática — 8º ANO A / 9º ANO A — fevereiro a abril/2026  
**Natureza:** investigação forense read-only; nenhum backfill, remapeamento ou escrita acadêmica

## Contexto

A R1.0A confirmou no banco vivo **67 datas-âncora de frequência de Matemática** (33 no 8º A e 34 no 9º A), porém encontrou zero `learning_objects`, zero `content_entries`, zero eventos auditáveis de identidade e zero datas top-level em snapshots para os alvos. Todas as 67 datas ficaram como `ATTENDANCE_ANCHOR_ONLY`.

A trilha F6.3d preservou outra fonte: um dump BSON ad hoc de **18/08/2026**, estruturalmente selecionado e restaurável em Mongo temporário isolado. A última tentativa F6.3d.2 terminou corretamente como:

- `INCONCLUSIVE / HISTORICAL_SCHEMA_INSUFFICIENT`
- motivo: `CLASS_NAME_SCHEMA_NOT_RESOLVED`

Isso não prova que o dump não contém conteúdo de Matemática. Prova apenas que o probe anterior dependia de aliases de schema que não conseguiram identificar de forma determinística as seis turmas do caso.

## Objetivo da R1.0B

Construir uma ponte de schema entre o dump histórico e os conceitos necessários à investigação, sem depender exclusivamente do nome das chaves:

1. escola Jose Pereira Barbosa;
2. turmas 6º A, 6º B, 7º A, 7º B, 8º A e 9º A;
3. identidade/referência de turma em `learning_objects`;
4. Matemática em `courses` e sua referência em `learning_objects`;
5. data da aula no intervalo `2026-02-01 <= date < 2026-05-01`.

## Estratégia

### 1. Descoberta estrutural por valor

O probe percorre somente valores escalares não pedagógicos das coleções permitidas. Para nomes de turma, tenta duas estratégias:

- `FULL_VALUE`: algum caminho escalar contém exatamente o rótulo canônico da turma;
- `GRADE_SECTION_COMPOSITE`: dois caminhos escalares, combinados deterministicamente, representam série/ano e seção (por exemplo, `8º ANO` + `A`).

A segunda estratégia existe especificamente para superar schemas históricos em que o nome completo da turma não era materializado em um único campo.

### 2. Contexto escolar

A escola é localizada pelo valor exato do nome. O bridge só aceita uma relação `schools ↔ classes` quando um identificador estrutural exclusivo da escola é compartilhado pelas seis turmas e resolve cada uma delas de forma única.

### 3. Relação turma ↔ learning_objects

O probe procura pares de caminhos escalares cujo conjunto de valores demonstre a referência entre `classes` e `learning_objects`. Os quatro controles — 6º A, 6º B, 7º A e 7º B — precisam ter ao menos uma linha relacionada antes que o par seja considerado viável.

### 4. Relação Matemática ↔ learning_objects

Matemática é descoberta por valor em `courses`. A identidade do componente é aceita somente quando há sobreposição relacional com `learning_objects`.

### 5. Data

A chave histórica de data é descoberta por valores que formem datas ISO válidas dentro de fevereiro–abril/2026. A solução final precisa produzir evidência de Matemática no período em todos os quatro controles.

### 6. Unicidade

Aliases equivalentes que produzem exatamente a mesma solução estrutural são deduplicados. Depois disso:

- exatamente 1 solução → bridge resolvido;
- 0 soluções → `INCONCLUSIVE`;
- mais de 1 solução → `INCONCLUSIVE`.

A ambiguidade nunca é escolhida por heurística de preferência.

## Payload pedagógico

A R1.0B não publica `content`, `methodology`, `observations` ou `resources`. Ela calcula apenas `rows_with_payload`, um booleano/contador de presença de valor não vazio.

Encontrar payload **não prova autoria**. A R1.0B deliberadamente não tenta atribuir linhas ao Luiz. Se o schema for resolvido e houver linhas de Matemática nos alvos, uma etapa posterior **R1.0C — atribuição histórica/payload** poderá ser aberta.

## Taxonomia

- `SCHEMA_BRIDGE_RESOLVED_TARGET_PAYLOAD_PRESENT` — schema único; há Matemática nos alvos e ao menos uma linha com payload;
- `SCHEMA_BRIDGE_RESOLVED_TARGET_ROWS_WITHOUT_PAYLOAD` — schema único; há linhas de Matemática nos alvos, mas sem payload detectável;
- `SCHEMA_BRIDGE_RESOLVED_NO_TARGET_MATH_ROWS` — schema único; controles positivos, porém zero linhas de Matemática nos alvos;
- `HISTORICAL_SCHEMA_BRIDGE_INCONCLUSIVE` — schema não pôde ser resolvido unicamente;
- `SCHEMA_BRIDGE_RUNTIME_OR_BOUNDARY_ERROR` — falha operacional ou quebra de boundary.

## Boundary

O runner existente F6.3d.1 continua responsável pelo isolamento:

- seleção do grupo BSON de 18/08 fora da árvore canônica;
- Mongo temporário com `--network none`;
- nenhuma porta publicada;
- source mount read-only;
- restauração somente das coleções allowlisted;
- estudantes, matrículas, frequência e notas fora do restore;
- plaintext pedagógico não emitido;
- stdout/stderr bruto do probe não sai do host;
- cleanup do container temporário e do probe staged;
- Mongo de produção não recebe qualquer escrita.

## Governança

A implementação deve entrar por PR próprio. A execução no host exige issue-gate criada pelo owner, SHA exato de `main`, SHA esperado de `production` e os trackings #422/#418/#357 abertos.

Esta subfase não exige deploy da aplicação: o workflow faz checkout do SHA revisado e envia somente o probe temporário ao host para execução no dump isolado.

R1.1 continua bloqueada enquanto não existir pelo menos um `RECOVERABLE_EXACT` comprovado. R1.0B, isoladamente, nunca autoriza reconstrução em produção.
