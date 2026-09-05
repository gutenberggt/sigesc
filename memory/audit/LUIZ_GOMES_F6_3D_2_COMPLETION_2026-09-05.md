# LUIZ-GOMES-F6.3d.2 — conclusão técnica

Data: 2026-09-05
Tracking: #357

## Contexto

A primeira execução da F6.3d.2 (gate #409) foi operacionalmente íntegra, mas terminou `INCONCLUSIVE / SCHOOL_CONTEXT_NOT_UNIQUE`: o dump BSON coerente de 18/08/2026 possui mais de uma identidade histórica para a escola `E M E I E F Jose Pereira Barbosa` quando a seleção é feita apenas por nome.

Isso não demonstrou ausência de conteúdo nem ausência do ator. Demonstrou apenas que a identidade escolar histórica não podia ser escolhida com segurança pelo nome.

## Correção desta etapa

A conclusão técnica da F6.3d.2 passa a resolver o contexto escolar por evidência estrutural, fail-closed:

1. localizar todas as identidades históricas com o mesmo nome normalizado;
2. exigir, dentro de uma única identidade escolar, resolução única em 2026 das seis turmas: 6º A, 6º B, 7º A, 7º B, 8º A e 9º A;
3. exigir evidência de `learning_objects` de Matemática entre 2026-02-01 e 2026-05-01 nas quatro turmas-controle 6º A, 6º B, 7º A e 7º B;
4. aceitar a identidade escolar somente se exatamente um candidato satisfizer simultaneamente os critérios acima;
5. inferir o ator histórico preferencialmente por `teacher_assignments` unânime nas quatro turmas-controle; usar metadados de `learning_objects` apenas como fallback dominante com suporte nas quatro turmas e cobertura mínima de 80%;
6. nunca consultar `users`, nunca emitir IDs técnicos e nunca emitir plaintext pedagógico;
7. aplicar a identidade inferida somente como filtro de leitura em 8º A e 9º A.

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
