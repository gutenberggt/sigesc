# P0-F7.9B — Contenção de Integridade Curricular das Alocações

Data: 2026-08-29

## Objetivo

Impedir que novas gravações em `teacher_assignments` recriem o passivo histórico identificado pela P0-F7.9A, sem alterar ou excluir registros históricos existentes.

## Invariantes

- Nenhuma migração ou correção de dados históricos nesta etapa.
- Nenhuma escrita automática em produção.
- Regra curricular centralizada em `utils.curriculum_resolver`; a fronteira de escrita apenas aplica política fail-closed sobre o classificador canônico.
- Turma sem nível explícito não pode receber nova alocação.
- Componente sem nível explícito não pode receber nova alocação.
- Divergência de nível é bloqueada.
- Componente do mesmo nível e sem escopo de série continua permitido para o nível inteiro.
- Quando existe escopo de série/matriz no componente, a turma precisa possuir série/etapa suficiente e obter compatibilidade forte.
- Encerramento/inativação de vínculo histórico permanece permitido para possibilitar remediação.
- Hard delete continua bloqueado pelo P0 Global.
- Create, update, substitution e tentativa de hard delete deixam trilha de auditoria.
- Toda escrita é tenant-scoped e o contexto staff/escola/turma/componente deve pertencer à mesma mantenedora.

## Superfícies protegidas

- `POST /teacher-assignments`
- `POST /teacher-assignments/substitutions`
- `PUT /teacher-assignments/{assignment_id}` quando o estado resultante permanece `ativo`
- `DELETE /teacher-assignments/{assignment_id}` permanece bloqueado e passa a auditar a tentativa

## Não escopo

- Não corrige os 21 vínculos da turma investigada.
- Não decide os casos de adjudicação da P0-F7.9.
- Não decide divergência de carga horária.
- Não executa auditoria geral da rede; isso pertence à P0-F7.9C.

## Critério de saída

A etapa pode ser considerada concluída quando os testes focados comprovarem:

1. `educacao_infantil -> eja_final` é rejeitado;
2. `eja_final -> eja_final` sem `grade_levels` é aceito;
3. turma sem nível explícito é rejeitada mesmo quando o nome da série permitiria inferência;
4. escopo parcial/conflitante de séries é bloqueado;
5. contexto escola/ano divergente é bloqueado;
6. os três caminhos ativos de escrita usam a mesma validação;
7. create/update/delete-blocked possuem contrato de auditoria;
8. hard delete permanece desabilitado.
