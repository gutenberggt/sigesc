# P0-F7.8 — Reavaliação pós-hardening da SSoT

## Objetivo

Reavaliar, em produção e somente leitura, os três vínculos de Geografia documentados na cadeia P0-F7.2→P0-F7.7 após a implantação do hardening do `Curriculum Resolver`.

A etapa responde a duas perguntas separadas:

1. o snapshot curricular/docente continua igual ao que foi selado pela P0-F7.5?
2. como a SSoT endurecida se comporta hoje para as matrículas ativas das três turmas?

A P0-F7.8 **não altera dados** e não transforma a observação do resolver em autorização de correção.

## Fonte selada

Entrada obrigatória:

- relatório privado P0-F7.5 (`READ_ONLY_SERIES_APPLICABILITY`), com SHA canônico válido e exatamente 3 casos de Geografia.

A cadeia do relatório preserva as evidências P0-F7.3/P0-F7.4 que originaram nível, séries, cursos e conflito de carga docente.

## Validação de drift

Antes de executar o resolver, cada caso é novamente conferido contra o MongoDB de produção:

- turma e `academic_year`;
- `mantenedora_id` obrigatório — fail-closed;
- escola;
- nível explícito da turma;
- séries/etapas da turma;
- source e target;
- `nivel_ensino`, `grade_levels`, `carga_horaria_por_serie`, carga anual e estado ativo dos cursos;
- candidatos alternativos já documentados pela P0-F7.5;
- existência de exatamente um vínculo docente ativo source e um target para o professor/turma;
- conflito semanal ainda igual ao snapshot anterior.

Qualquer divergência aborta a fase com erro de `SNAPSHOT_DRIFT`. A P0-F7.8 não tenta corrigir nem reinterpretar snapshot divergente.

## Execução real da SSoT

Para cada matrícula ativa das três turmas, o auditor chama o próprio:

`backend/utils/curriculum_resolver.py::resolve_curriculum()`

O resolver recebe a turma live e a série/etapa da matrícula e pode ler apenas o necessário para sua resolução normal:

- matriz explícita da turma;
- vínculos docentes ativos;
- cursos tenant-scoped;
- evidência acadêmica já usada pelo resolver.

Identificadores de estudantes são usados somente em memória durante a consulta e **não são serializados nem impressos**. O relatório contém apenas contagens agregadas.

## Política observada

A P0-F7.8 separa dois conceitos:

### 1. Estado curricular do par source/target

Calculado pela mesma `_curricular_fit()` da SSoT:

- rank 3: forte;
- rank 2: review/inconclusivo;
- rank 1: incompatível.

### 2. Resultado operacional observado

Agrega, sem expor estudante:

- quantas execuções selecionaram source;
- quantas selecionaram target;
- quantas selecionaram candidato alternativo já conhecido;
- quantas selecionaram outro homônimo inesperado;
- razões de desempate;
- classificações curriculares do vencedor;
- presença de `CURRICULAR_COMPATIBILITY_REVIEW_REQUIRED`.

Um vencedor operacional **não equivale automaticamente a uma decisão institucional**.

## Estados esperados dos três casos

### Caso 1 — MULTI 8º E 9º

- source: rank 3 (`EXPLICIT_SERIES_FULL_MATCH`);
- target: rank 2 (`SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW`);
- estado esperado: `STRONG_CURRICULAR_PREFERENCE_SOURCE`.

A preferência curricular pode ser considerada tecnicamente determinada pela SSoT, mas a P0-F7.8 ainda não executa remapeamento nem alteração de vínculo.

### Caso 2 — MULTI 3º E 4º ETAPA

- source e target `fundamental_anos_finais`: rank 1 (`LEVEL_MISMATCH`);
- candidato EJA exato documentado anteriormente: review por ausência de escopo de séries, salvo se o cadastro live tiver mudado — mudança que seria tratada como drift;
- estado esperado do par: `BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION`.

A existência de um candidato EJA não o injeta automaticamente no conjunto do resolver. O relatório informa apenas se esse candidato já aparece legitimamente em algum conjunto real de candidatos.

### Caso 3 — MULTI 6º E 7º

- source: rank 2 (`PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW`);
- target: rank 2 (`SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW`);
- estado esperado: `BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION`.

A evidência operacional pode desempatar o retorno do resolver, mas não elimina a necessidade de adjudicação curricular.

## Carga horária

A P0-F7.8 apenas confirma que o conflito semanal source/target permanece igual ao snapshot.

Ela:

- não converte carga anual em carga semanal;
- não escolhe 2h ou 3h;
- não altera `teacher_assignments`;
- não autoriza executor de carga.

## Segurança

- leitura MongoDB apenas;
- zero `insert/update/delete/replace/bulk_write`;
- sem `--apply`;
- tenant fail-closed;
- identificadores de estudante não expostos;
- valores de notas não expostos;
- valores de frequência não expostos;
- JSON privado gravado com modo `0600`;
- nenhuma ação automática de banco;
- nenhum executor autorizado.

## Gate de saída

A fase somente pode ser integrada se:

- testes focados cobrirem os três estados esperados;
- CI geral estiver verde;
- guard P0-F7.8 confirmar superfície read-only e privacidade;
- P0-F7.6 e P0-F7.7 permanecerem verdes;
- regressões gerais permanecerem verdes.

Depois do deploy da P0-F7.8, o auditor deve ser executado em produção usando o relatório privado P0-F7.5 mais recente e o resultado completo deve ser preservado em diretório privado. Somente então a próxima etapa poderá transformar os casos tecnicamente resolvidos ou ainda pendentes em um pacote de adjudicação/execução separado.
