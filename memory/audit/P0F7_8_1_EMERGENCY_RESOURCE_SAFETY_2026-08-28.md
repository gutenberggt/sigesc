# P0-F7.8.1 — Correção emergencial de segurança de recursos

## Incidente

A implementação inicial da P0-F7.8 executava o resolver curricular uma vez para cada matrícula ativa das três turmas auditadas. Cada execução do resolver pode consultar múltiplas coleções. Em produção, isso criava um padrão N+1 de alto custo e podia pressionar CPU, memória e I/O do backend/host.

## Decisão

A P0-F7.8 passa a ser estritamente **bounded read-only**:

- zero loop por estudante;
- zero replay integral do resolver por matrícula;
- zero leitura de `students`, `enrollments`, `grades` e `attendance`;
- exatamente três casos selados;
- por caso, somente leitura de `classes`, `courses` e `teacher_assignments`;
- budget máximo de 9 operações de consulta ao banco para os três casos;
- pool Mongo limitado a 2 conexões;
- timeouts explícitos de conexão e socket;
- a precedência `curricular_rank > evidence_score` é verificada estaticamente na SSoT;
- nenhuma decisão de carga horária;
- nenhuma mutação de banco.

## Resultado preservado

A fase continua apta a:

1. confirmar que o snapshot dos três casos não sofreu drift relevante;
2. recalcular a compatibilidade curricular live de source/target sob `_curricular_fit()`;
3. classificar o par em preferência curricular forte ou necessidade de adjudicação;
4. confirmar que o resolver implantado mantém a precedência curricular introduzida na P0-F7.7.

A observação por estudante foi removida porque não é necessária para autorizar correções e tinha custo operacional desproporcional.

## Regra operacional

A implementação anterior da P0-F7.8 está **superseded** e não deve ser executada novamente. Somente a versão P0-F7.8.1, após merge e deploy, pode ser usada em produção.
