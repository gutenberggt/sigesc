# P0 — Frequência DVD `class_daily` por chave canônica da turma

Data: 2026-08-21

## Incidente

No PDF de frequência do 1º bimestre/2026 da E M E I E F Paroquial Curupira, turma 2º Ano D, o cabeçalho identificava corretamente a professora Dolores Lopes Lima e mostrava 41 dias previstos, porém o documento era gerado com `DIAS REGISTRADOS: 0` e todos os estudantes com zero presença/falta.

## Causa raiz

A semântica canônica de `class_daily` já define a frequência diária pela turma + data (+ período), com `course_id=None`. `assignment_id` e `teacher_id` são dados de autorização/proveniência, não componentes da chave natural.

Entretanto, `_assignment_docs()` ainda fazia leitura estrita por `assignment_id`. A ponte de compatibilidade corrigia isso apenas quando o vínculo possuía proveniência 38G-B validada. Fora desse caso, ou quando a frequência da turma estava materializada sob outro vínculo/professor autorizado, a leitura podia retornar lista vazia mesmo existindo frequência oficial para a turma.

O PDF DVD usa essa lista para formar `attendance_days` e calcula `DIAS REGISTRADOS` por `len(attendance_days)`. Assim, a falha de leitura resultava diretamente em zero dias e zero P/F/J no documento.

## Correção

Para contextos autorizados `CLASS_DAILY + OFFICIAL`, a fonte consolidada passa a consultar `attendance` pela chave canônica:

- `class_id` do vínculo autorizado;
- intervalo de datas permitido;
- `course_id=None`;
- `attendance_mode=class_daily`;
- `attendance_purpose=official`.

Não há filtro de `teacher_id` nem de `assignment_id` na recuperação da frequência diária oficial.

Documentos legados sem `assignment_id` continuam sendo combinados em memória e permanecem somente leitura. Quando há documento legado e DVD para a mesma turma/data/período, o documento DVD prevalece apenas na leitura consolidada para impedir dupla contagem.

## Limites de segurança

1. `resolve_attendance_assignment()` continua sendo a porta de autorização do professor/vínculo/tenant/turma.
2. Vínculos normais respeitam `valid_from` e `valid_until`.
3. Somente cutovers 38G-B revalidados podem atravessar o `valid_from` técnico de ativação para recuperar o histórico anual legado.
4. `ASSIGNMENT_SESSION` continua usando a leitura original por vínculo/componente/sessão.
5. `pdf_only` documental não passa a ler frequência oficial.
6. Nenhum documento de frequência é escrito, migrado, removido ou reatribuído por esta correção.
7. A autoria/proveniência armazenada no documento continua intacta.

## Regressão adicionada

Os testes permanentes passam a garantir que o bloco canônico `class_daily`:

- filtra por turma, `course_id=None`, modo e natureza oficiais;
- não filtra por `teacher_id`;
- não filtra pelo `assignment_id` atual;
- mantém os limites de vigência para vínculos que não são cutover 38G-B.

## Critério de aceitação operacional

Ao gerar novamente o PDF da E M E I E F Paroquial Curupira — 2º Ano D — vespertino — 1º bimestre/2026 pelo Diário por Vínculo, os registros oficiais existentes para a turma no período devem compor as colunas de frequência, `DIAS REGISTRADOS`, faltas e presenças. O cabeçalho continua usando o vínculo docente apenas para identificação/autorização, não para fragmentar a frequência diária oficial.
