# P0-F7.9D7.1 — Intra-batch collision preflight

Data: 2026-08-29

## Motivo

A primeira execução autorizada da P0-F7.9D7 interrompeu o avanço no ordinal 22 com `P0F79D7_IMMEDIATE_COLLISION` após 21 writes. O rollback compensatório reverso restaurou os 21 documentos alterados, resultando em `SAFE_ROLLBACK`, sem remediação persistente e sem necessidade de recuperação manual.

A análise local comprovou que as propostas 21 e 22 convergiam para o mesmo tuple futuro ativo `(staff_id, school_id, class_id, target_course_id, academic_year)`. D3/D5 validavam colisões contra o estado existente e D6 simulava cada caso com rollback imediato; por isso, a colisão criada cumulativamente pelo próprio lote não era representada antes da execução.

## Correção

A D7.1 introduz um preflight estritamente local/offline que combina o plano D4 com o snapshot D5, usa `staff_id` apenas em memória para formar a chave do tuple futuro e nunca o grava no relatório. O relatório particiona as propostas em:

- `safe_entries`: propostas sem colisão intralote;
- `blocked_entries`: propostas pertencentes a grupos que convergem para o mesmo tuple futuro;
- `collision_groups`: agrupamentos que exigem adjudicação humana antes de qualquer plano revisado.

O wrapper oficial da D7 passa a exigir um relatório D7.1 com `execution_gate_open=true`, `safe_noncolliding=23`, `blocked_intra_batch=0` e `collision_groups=0`. Caso contrário, a armação é bloqueada antes da geração do executor.

## Segurança

- nenhuma conexão com MongoDB;
- nenhuma chamada de rede;
- nenhuma escrita em produção;
- nenhum `staff_id` exposto no relatório;
- nenhum dado de estudante;
- nenhuma reexecução automática da D7 anterior;
- qualquer lote revisado exigirá novo plano e nova autorização explícita de escrita em produção.

## Resultado esperado para o caso atual

A partir do snapshot fresco já coletado antes da execução que sofreu rollback:

- `entries=23`;
- `safe_noncolliding=21`;
- `blocked_intra_batch=2`;
- `collision_groups=1`;
- `execution_gate_open=false`.

As duas propostas bloqueadas permanecem fora de qualquer nova execução até adjudicação específica.
