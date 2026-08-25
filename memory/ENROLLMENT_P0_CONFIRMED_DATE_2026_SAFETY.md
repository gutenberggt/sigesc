# Invariantes de segurança — data confirmada P0

1. `2026-01-15` é data administrativa confirmada, não inferida.
2. `students.created_at` não é usado como data de matrícula.
3. A primeira frequência apenas corrobora que a data confirmada não é posterior à vida acadêmica observada.
4. Qualquer mudança de estudante, turma, escola, tenant, número de matrícula ou documento preexistente bloqueia o caso.
5. O lote é fail-closed: um bloqueio impede escrita inicial do lote.
6. Reexecução reconhece reparo exato como idempotente.
7. Notas e frequências não são modificadas.
