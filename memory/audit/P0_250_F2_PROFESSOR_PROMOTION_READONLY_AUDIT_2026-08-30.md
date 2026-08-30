# P0 #250 — Fase 2: auditoria read-only do caso Professor ⇄ Livro de Promoção

Data: 2026-08-30
Status: **READY_FOR_REVIEW**

## Motivo

O PR #251 corrigiu assimetrias estáticas do Livro de Promoção para o perfil professor e foi publicado no SHA `d91471a8b33a6f7fc53040d211cc3a86623dc8b6`. O release protegido confirmou o SHA público, health da API e continuidade do volume MongoDB. Mesmo assim, o caso-canário continuou apresentando notas existentes na tela de Notas como `-` no Livro de Promoção.

Portanto, a Fase 1 é considerada **insuficiente para explicar o incidente real**. A issue #250 foi reaberta e a Fase 2 passa a observar apenas a estrutura necessária no estado vivo.

## Caso delimitado

- docente: Abadia Alves Martins;
- escola: E M E I E F Jose Pereira Barbosa;
- turma: 5º ANO A;
- ano letivo: 2026;
- expectativa observada de alocação: 9 componentes ativos.

Os nomes acima servem apenas para localizar inequivocamente o caso. O snapshot não publica nomes de estudantes nem valores de notas.

## Perguntas que o snapshot responde

Para cada `course_id` efetivamente alocado à docente na turma/ano:

1. quantos `teacher_assignments` ativos existem;
2. se o `course_id` resolve para um documento de `courses`;
3. quantos documentos de `grades` existem no par exato `class_id + course_id + academic_year`;
4. quantos desses documentos possuem ao menos um campo bimestral/recuperação preenchido, sem ler o valor para fora do MongoDB;
5. quantos documentos pertencem ao universo de estudantes usado pelo Livro de Promoção;
6. quantos pertencem ao universo que o endpoint `/grades/by-class` monta;
7. se há mais de um documento de nota para o mesmo `student_id + course_id` no recorte;
8. se há divergência de tipo entre IDs;
9. quantos IDs de curso compartilham o mesmo nome, como sinal auxiliar de colisão semântica.

## Classificações possíveis

- `IDENTITY_AMBIGUOUS_OR_MISSING`: escola/docente/staff/turma não resolvem de forma única;
- `ASSIGNMENT_TOPOLOGY_DRIFT`: quantidade de assignments/IDs de componente divergiu dos 9 observados;
- `COURSE_REFERENCE_GAP`: assignment aponta para course inexistente;
- `DUPLICATE_GRADE_DOCUMENTS`: mais de um documento de grade por estudante/componente no recorte;
- `PROMOTION_BYCLASS_STUDENT_SET_DIVERGENCE`: os dois caminhos enxergam conjuntos diferentes de documentos por identidade de estudante;
- `ID_TYPE_DIVERGENCE`: tipos de ID divergem entre course e grade;
- `DATA_PATHS_STRUCTURALLY_EQUIVALENT`: nenhuma dessas divergências estruturais foi encontrada; nesse caso o foco seguinte deve migrar para runtime/frontend, e não para remediação de banco.

## Limites de segurança

O coletor é deliberadamente bounded e somente leitura:

- não contém `insert`, `update`, `replace`, `delete`, `bulkWrite`, `findOneAndUpdate`, `drop` ou `dropDatabase`;
- não executa backfill, merge, consolidação ou remapeamento;
- não reinicia containers;
- não altera `teacher_assignments`, `grades`, `students`, `enrollments` ou `courses`;
- valores de `b1`, `b2`, `b3`, `b4`, `rec_s1` e `rec_s2` são reduzidos dentro do MongoDB a flags booleanas de presença e **não são emitidos no snapshot**;
- nomes, CPF, responsáveis ou quaisquer outros dados de estudantes não são projetados;
- o artefato técnico permanece privado no GitHub Actions por 90 dias.

## Execução em produção

Depois de o código ser revisado, testado, integrado em `main` e explicitamente autorizado, a auditoria é disparada por um issue owner-scoped com título:

`[P0-250-F2-AUDIT] <TARGET_SHA>`

Corpo canônico:

```text
P0_250_F2_AUDIT=AUTHORIZED
CONFIRMATION=VERIFY_P0_250_F2_READ_ONLY
TARGET_SHA=<40-hex da main revisada>
```

O workflow falha fechado se o `main` tiver mudado desde a autorização.

## O que esta fase NÃO autoriza

Mesmo que a auditoria encontre divergência, nenhuma correção de banco fica automaticamente autorizada. O resultado deve primeiro ser adjudicado e transformado, se necessário, em um PR de correção de lógica ou em um plano de remediação separado.
