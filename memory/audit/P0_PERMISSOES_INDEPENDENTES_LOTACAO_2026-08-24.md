# P0 — Permissões independentes da função da lotação

Data: 24/08/2026

## Regra institucional

- `users.role` e `users.roles` definem quais papéis/permissões o usuário pode exercer.
- `school_assignments` ativas definem em quais escolas o usuário atua.
- `school_assignments.funcao` é atributo funcional/RH e não pode conceder, reduzir ou bloquear permissões da aplicação.
- Para papéis com escopo escolar, todas as escolas de lotações ativas do ano corrente compõem o escopo da sessão, independentemente da função registrada na lotação.
- Quando não existem lotações ativas, `user.school_links` permanece como fallback legado.

## Evidência do problema

Na auditoria de secretários de 2026, usuários com papel `secretario` e lotação funcional `apoio` ficavam sem `school_ids`, embora devessem manter permissões de secretário na escola onde estão lotados.

## Alteração

`backend/role_context.py` deixa de filtrar `school_assignments` por `funcao == active_role`. As lotações ativas passam a fornecer somente o escopo escolar; o papel ativo continua vindo exclusivamente do cadastro do usuário/sessão.

## Regressão

`backend/tests/test_multi_role_active_session_p0.py` protege explicitamente:

- o mesmo conjunto de escolas para diferentes papéis autorizados do usuário;
- manutenção do escopo quando `lotacao.funcao` difere do papel ativo;
- caso real de contrato: usuário `secretario` lotado funcionalmente como `apoio` mantém a escola no escopo e permissões de secretário.

## Fora de escopo

- Nenhuma alteração em dados de produção.
- Nenhuma alteração em cargos, funções de RH ou lotações existentes.
- Nenhuma alteração em permissões atribuídas em `users.role`/`users.roles`.
- Nenhuma alteração no escopo pedagógico por turma/componente de `teacher_assignments`.
