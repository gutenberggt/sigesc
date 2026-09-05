# R2.0f — Pareamento Ordinal por Data + Carga — 9º B → 9º A

Data: 2026-09-05

## Escopo

Professor: **Luiz Gomes dos Santos**  
Escola: **E M E I E F Jose Pereira Barbosa**  
Componente: **Matemática**  
Origem: **9º ANO B**  
Destino: **9º ANO A**  
Período: `2026-02-01 <= date < 2026-05-01`

Tracking: #459 → #456 → #453 → #439 → #438 → #418. Investigação raiz: #357.

## Premissa semântica congelada

A R2.0e classificou o 9º B como:

`ONE_CONTENT_PER_DATE_COVERS_SESSION_DOCUMENTS_SUPPORTED`

Calibration hash:

`cbe9f21d5a9d9e76c508c6bea9f924cc10ac086546b9e9cb065aa7a77006af88`

A interpretação aprovada para este preflight é: **um registro de conteúdo por data cobre as sessões daquele dia; `number_of_classes` representa a carga diária coberta e não autoriza multiplicar registros de conteúdo.**

A R2.0f reexecuta a calibração antes do pareamento e bloqueia se o hash ou a classificação tiverem mudado.

## Modelo

Cada conteúdo-fonte é mantido como unidade indivisível com:
- data;
- ordem cronológica;
- carga declarada;
- fingerprint do payload;
- classificação de provenance.

As frequências do 9º A são agregadas por data. Para cada data são medidos:
- quantidade de documentos/sessões;
- soma de `number_of_classes` dos documentos;
- consistência entre quantidade documental e carga declarada;
- fingerprints estruturais das sessões.

A carga diária do destino só é considerada estável quando:

`número de documentos == soma de number_of_classes`

A compatibilidade fonte→destino exige:

`source.number_of_classes == target.document_count == target.declared_load`

## Pareamento monotônico

A fase calcula um LCS por carga, preservando a ordem cronológica das duas sequências. O resultado é exclusivamente diagnóstico.

Não é permitido usar o LCS para:
- descartar conteúdo-fonte;
- descartar data-alvo;
- repetir conteúdo;
- fracionar conteúdo;
- combinar conteúdos;
- inventar conteúdo;
- alterar frequência.

## READY_TO_APPLY

Somente se simultaneamente:
- calibration hash/classificação R2.0e permanecem congelados;
- fonte continua 1 conteúdo por data;
- sessões-alvo são estruturalmente discrimináveis;
- carga diária alvo é consistente;
- destino continua sem conteúdo no período;
- binding do Luiz está único/resolvido;
- número de conteúdos = número de datas-alvo;
- carga total fonte = carga total alvo;
- o pareamento monotônico cobre 100% da fonte e 100% do destino.

Caso contrário: `BLOCKED_REVIEW_REQUIRED`.

## Boundary

- Mongo reads only;
- `attendance.records` não lido;
- estudantes não lidos;
- matrículas não lidas;
- notas não lidas;
- `audit_logs` não lido;
- nenhuma frequência escrita;
- nenhum conteúdo escrito;
- nenhum ID técnico bruto emitido;
- plaintext pedagógico não emitido;
- nenhum deploy;
- R2.1 permanece separada e exige gate explícito de escrita.

## Estado inicial

`main`: `5c6e713cbb29f08e7a191f4f3386d1c8f0469ab9`  
`production`: `ff7c27c75bd5d7dc647a95b879ab1ed3a2c36bf1`

Nenhuma execução R2.0f em produção está autorizada por este documento. A execução depende de merge revisado e gate owner-only/exact-SHA posterior.
