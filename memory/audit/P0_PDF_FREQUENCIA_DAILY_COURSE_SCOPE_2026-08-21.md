# P0 — PDF de frequência diária não pode herdar filtro de componente

Data: 2026-08-21

## Evidência do incidente

Após o deploy do PR #72, a E M E I E F Paroquial Curupira — 2º Ano D — 1º bimestre/2026 apresentou a seguinte divergência:

- relatório **Ver na Tela**: 41 dias com registro, com presenças, faltas e justificadas por estudante;
- PDF: `DIAS PREVISTOS: 41`, `DIAS REGISTRADOS: 0` e totais zerados.

Testes adicionais mostraram que a falha se concentra em **Educação Infantil e 1º ao 5º ano**. Os níveis cuja frequência é por componente/aula não reproduzem o defeito.

## Causa raiz

A tela e o PDF estavam construindo o escopo de consulta de maneiras diferentes.

Na aba Relatórios, `Ver na Tela` usa `reportCourseId`. Em Educação Infantil e Anos Iniciais não existe seletor de componente para o relatório, portanto a chamada é feita sem `course_id` e recupera corretamente a frequência diária da turma.

Já `Gerar PDF` usa `reportCourseId || selectedCourse`. O `selectedCourse` pode permanecer preenchido pela navegação de **Meus Diários**, mesmo quando a frequência do nível é diária e pertence à turma, não ao componente.

O endpoint legado do PDF recebia esse `course_id` residual e acrescentava o filtro diretamente à consulta Mongo:

`class_id + academic_year + período + course_id`

Nos documentos de frequência diária, a chave canônica é `class_id + date (+ period)` e `course_id` é `None`. Consequentemente, o filtro residual eliminava todos os documentos do bimestre e o PDF recebia uma coleção vazia.

Isso explica simultaneamente:

1. professor e turma corretos no cabeçalho;
2. 41 dias corretos na tela;
3. zero dias no PDF;
4. incidência em Infantil e 1º–5º ano;
5. funcionamento dos níveis por componente.

## Correção

A camada `attendance_ext_dvd.py`, que já protege a superfície legada de PDF, agora normaliza o escopo antes de delegar ao gerador:

- Educação Infantil → `course_id=None`;
- 1º ao 5º ano / Anos Iniciais → `course_id=None`;
- EJA inicial → `course_id=None`;
- Anos Finais, EJA final e Ensino Médio → preserva `course_id`.

Assim, mesmo que o navegador envie um componente residual, o backend aplica a semântica canônica da modalidade antes de consultar `attendance`.

## Segurança e invariantes

- nenhuma frequência é criada, migrada, editada ou removida;
- nenhuma autoria é alterada;
- não há mudança no renderer do PDF;
- não há mudança na frequência por componente dos Anos Finais/EJA final/Ensino Médio;
- o ajuste ocorre apenas no escopo de leitura do PDF;
- o backend permanece protegido mesmo diante de URL antiga, cache do frontend ou contexto residual de navegação.

## Regressão permanente

O gate `test_professor_attendance_pdf_document_parity_p0.py`, já executado pelo CI de Diário por Vínculo, passa a exigir que:

- exista normalização explícita do `course_id` para frequência diária;
- Educação Infantil seja classificada como diária;
- séries 1–5 sejam classificadas como diárias;
- séries 6+ e níveis explicitamente por componente preservem o filtro.

Também foi adicionado o teste dedicado `test_attendance_pdf_daily_course_scope_p0.py` para documentar a regressão de forma isolada.

## Critério de aceitação

Após deploy, ao gerar novamente o PDF da Paroquial Curupira — 2º Ano D — 1º bimestre/2026, o documento deve apresentar:

- `DIAS REGISTRADOS: 41`;
- colunas correspondentes aos dias lançados;
- P/F/J/A compatíveis com a fonte de frequência;
- totais de faltas e presenças coerentes com o relatório em tela.
