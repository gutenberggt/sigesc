# ANA-LUCIA-F2.5B — adjudicação read-only de tenant e chave agregada legada

Data: 2026-09-01

## Origem

A F2.5 original abortou em produção com `ANA_LUCIA_F2_5_DVD_BINDING_NOT_EXACT:6º ANO A:0`. O diagnóstico read-only do PR #328 isolou a exceção sem qualquer escrita.

A reabertura do artefato F2.3 demonstrou que existem 8 referências `teacher_class_assignments` ao componente atual nas oito turmas, porém `teacher_attributed_2026 = 0`. Portanto, esses vínculos não podem ser usados como slots de Ana Lucia.

O backend de histórico DVD também preserva registros legados existentes com `aula_numero = None` e `number_of_classes`, sem reatribuir autoria nem converter o documento para uma sessão DVD. Logo, `aula_numero` ausente é tratado nesta fase como possível **schema agregado legado**, e não como dado que deva ser inventado.

## Política F2.5B

1. **Tenant**: adjudicar somente pela convergência do `teacher_assignment` legado ativo e único de Ana para a turma/componente, da própria turma, escola e anchors de tenant disponíveis. DVD não participa da inferência.
2. **Chave agregada legada**: para os attendance sem `aula_numero`, usar a chave estrutural `(class_id, date, period)` apenas para decidir se o documento agregado pode ser preservado. Nenhum `aula_numero` é inferido ou escrito.
3. Bloquear quando houver: duplicidade de agregado na origem, agregado correspondente no destino, sessão de origem no mesmo dia/período ou sessão de destino no mesmo dia/período.
4. **Linhagem**: manter a adjudicação `copied_from_id` da F2.5, separando aresta preservada, quebra preexistente e nova quebra de identidade.
5. **Baseline**: comparar exatamente com F2.4: 198 learning candidates, 392 attendance candidates, 74 tenant ausentes, 4 chaves incompletas, 74 copied, 73 pais no conjunto e 1 pai ausente.

## Boundary

- MongoDB somente leitura;
- nenhuma mutação de produção;
- sem HTTP/login;
- sem `attendance.records`;
- sem estudantes/matrículas;
- sem valores de frequência/notas ou texto pedagógico;
- sem IDs técnicos brutos; apenas fingerprints SHA-256 truncados;
- `audit_logs` somente metadados estruturais (`action`, timestamps e role), sem `old_value`, `new_value` ou `description`;
- nenhum tenant backfill, nenhum `aula_numero` backfill, nenhum remapeamento `course_id`, nenhum merge global;
- Transferência Institucional e MT-1 permanecem intocados.

Mesmo se a F2.5B concluir que todos os casos são estruturalmente preserváveis, qualquer write/remap continuará exigindo desenho separado e autorização humana explícita.