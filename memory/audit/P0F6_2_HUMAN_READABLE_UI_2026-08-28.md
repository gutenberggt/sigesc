# P0-F6.2 — Interface humana da estação privada de adjudicação

## Objetivo

Reduzir risco operacional na adjudicação humana dos conflitos P0-F6, substituindo códigos técnicos visíveis por linguagem institucional compreensível, sem alterar o contrato técnico exportado.

## Escopo

- somente apresentação HTML offline;
- nenhuma alteração no pacote P0-F5;
- nenhum acesso a MongoDB;
- nenhuma decisão automática;
- nenhuma alteração em `review_unit_id`;
- decisões internas continuam `KEEP_SOURCE`, `KEEP_TARGET` e `MANUAL_RECONCILIATION`;
- `seal` continua delegado ao contrato P0-F6 já validado.

## Traduções principais

- `learning_objects` → Conteúdo pedagógico;
- `grades` → Notas;
- `attendance` → Frequência;
- `PEDAGOGICAL_CONTENT_FIELD_DECISION` → Divergência em conteúdo pedagógico;
- `GRADE_FIELD_DECISION` → Divergência em nota;
- `ATTENDANCE_STUDENT_DECISION` → Divergência de frequência;
- `SOURCE` → Registro 1;
- `TARGET` → Registro 2.

`Registro 1` e `Registro 2` são deliberadamente neutros. A interface informa que nenhum deles significa automaticamente correto, errado, mais novo ou mais antigo.

## Contexto legível

A área principal deixa de mostrar UUIDs e chaves como `school_id`, `class_id` e `academic_year`. A apresentação prioriza Escola, Turma, Ano letivo, Data, Aula, Período e Estudante. Os identificadores técnicos permanecem no pacote e o `review_unit_id` fica recolhido em “Detalhes técnicos”.

## Segurança e rastreabilidade

- contrato técnico preservado integralmente;
- CSP offline preservada;
- dependências de rede = 0;
- arquivo privado `0600` preservado;
- nenhuma superfície de banco;
- teste executa `node --check` sobre o JavaScript realmente gerado;
- transformação fail-closed se a estrutura esperada do P0-F6.1 mudar.

## Não autoriza

Esta fase não autoriza consolidação de cursos, remapeamento, exclusão, criação, escrita em produção ou execução das decisões humanas.
