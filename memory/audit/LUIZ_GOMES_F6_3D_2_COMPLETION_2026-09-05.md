# LUIZ-GOMES-F6.3d.2 — conclusão técnica

Data: 2026-09-05
Tracking: #357

## Contexto

A primeira execução da F6.3d.2 (gate #409) foi operacionalmente íntegra, mas terminou `INCONCLUSIVE / SCHOOL_CONTEXT_NOT_UNIQUE`. Essa classificação histórica era genérica e não distinguia zero de múltiplas correspondências nominais.

Após o PR #410, o gate #411 tornou a medição explícita e concluiu `INCONCLUSIVE / SCHOOL_CONTEXT_NOT_FOUND`, com `name_matches=0`. Portanto, o dump BSON coerente de 18/08/2026 não oferece a identidade histórica da escola de forma utilizável pelo campo nominal consultado. Isso não demonstrou ausência de conteúdo nem ausência do ator; demonstrou apenas que `schools.name` não é uma SSoT histórica suficiente para este dump.

## Resolução estrutural definitiva da escola

A F6.3d.2 passa a derivar a identidade escolar diretamente da relação `classes.school_id`, sem usar o nome como chave de seleção:

1. selecionar as classes de 2026 cujos nomes correspondem às seis turmas esperadas: 6º A, 6º B, 7º A, 7º B, 8º A e 9º A;
2. agrupar essas classes pelo `school_id` histórico, mantendo o ID somente em memória e nunca o emitindo;
3. exigir, dentro de um mesmo grupo, exatamente uma ocorrência de cada uma das seis turmas;
4. exigir `learning_objects` de Matemática entre 2026-02-01 e 2026-05-01 em cada uma das quatro turmas-controle 6º A, 6º B, 7º A e 7º B;
5. aceitar a identidade escolar somente se exatamente um grupo `classes.school_id` satisfizer simultaneamente os critérios acima;
6. zero grupos => `SCHOOL_CONTEXT_NOT_STRUCTURALLY_RESOLVED`; mais de um => `SCHOOL_CONTEXT_STRUCTURAL_AMBIGUITY`; ambos fail-closed.

O nome `E M E I E F Jose Pereira Barbosa` permanece apenas como contexto humano no relatório e não participa da decisão estrutural.

## Inferência do ator

Após resolver uma única identidade escolar:

1. preferir `teacher_assignments` unânime nas quatro turmas-controle + Matemática (`TEACHER_ASSIGNMENTS_EXACT_CONTROL_UNANIMOUS`);
2. usar, apenas como fallback, metadados de `learning_objects` com suporte em 4/4 turmas, cobertura mínima de 80% e sem empate (`LEARNING_OBJECT_METADATA_FOUR_CLASS_DOMINANT`);
3. nunca consultar `users`;
4. nunca emitir IDs técnicos;
5. aplicar a identidade inferida apenas como filtro read-only em 8º A e 9º A.

## Boundary

- dump de 18/08/2026 restaurado exclusivamente em Mongo temporário;
- `--network none` e zero portas publicadas;
- fonte BSON montada read-only;
- nenhuma escrita em produção;
- nenhuma leitura de estudantes, matrículas, notas ou `attendance.records`;
- payload pedagógico reduzido a presença/ausência booleana;
- nenhum ID técnico publicado em logs, comentário ou artifact.

## Critério de completude

A F6.3d.2 é tecnicamente completa quando o gate pós-merge:

- conclui `COMPLETED` com uma única identidade escolar estrutural e `EXACT_CONTROL_DERIVED`, produzindo a classificação dos dois alvos; **ou**
- conclui `INCONCLUSIVE` por uma condição fail-closed genuína ainda não resolvível com o dump disponível, sem erro operacional/probe/boundary.

Nenhuma classificação desta fase autoriza correção de dados. Qualquer recuperação ou remapeamento exige etapa própria, preflight, CAS/idempotência, rollback e autorização específica.
