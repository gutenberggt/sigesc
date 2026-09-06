# P0 — Auditoria MT-1: visualização tenant-scoped

**Data:** 06/09/2026  
**Incidente:** tela `Logs de Auditoria` exibia `Nenhum log encontrado` ao Super Administrador mesmo com histórico existente.  
**Natureza:** correção funcional + isolamento multi-tenant.  
**Banco:** sem migração, sem backfill e sem alteração retroativa de `audit_logs`.

## Causa

A página `AuditLogs.jsx` usava `fetch()` manual com apenas `Authorization`. Após a MT-1, rotas operacionais exigem contexto de mantenedora (`X-Mantenedora-Id`). A resposta de erro HTTP era silenciosamente tratada como estado vazio, escondendo a falha real.

Além disso, o serviço histórico de auditoria não persistia `mantenedora_id` e as consultas eram globais. Corrigir apenas o header do frontend reabriria risco de leitura cross-tenant.

## Correção

1. Frontend usa `apiFetch` para lista, estatísticas e usuários, e `buildFetchAuthHeaders('GET')` para PDF.
2. Falhas HTTP agora são exibidas como erro explícito; `Nenhum log encontrado` só é mostrado após resposta bem-sucedida com lista realmente vazia.
3. Novos eventos de auditoria persistem `mantenedora_id` derivado do contexto operacional já validado; `school_id` é usado apenas como fallback server-side quando necessário.
4. Toda leitura (`lista`, `estatísticas`, `usuário`, `documento`, `críticos` e `PDF`) recebe tenant explícito e falha fechada sem ele.
5. Logs legados sem `mantenedora_id` não são apropriados nem backfilled. Eles só ficam visíveis quando há evidência inequívoca pelo `school_id` pertencente ao tenant ou pelo `user_id` cujo documento atual declara o tenant.
6. Cabeçalho do PDF deixa de usar a primeira mantenedora como fallback global.

## Invariantes

- Super Administrador continua podendo operar em qualquer mantenedora, mas uma por vez.
- `TENANT_A` nunca recebe log explicitamente pertencente a `TENANT_B`.
- legado sem evidência permanece invisível (`UNRESOLVED` por política, sem mutação).
- nenhuma coleção acadêmica é alterada por esta correção.
- nenhuma migração de banco é necessária.

## Regressão

`backend/tests/test_audit_mt1_visibility_p0.py` cobre:
- escopo legado somente com evidência do tenant;
- fail-closed sem tenant;
- persistência de `mantenedora_id` em novos eventos;
- uso do fetch canônico no frontend;
- erro HTTP não mascarado como lista vazia;
- propagação do tenant para lista, PDF e estatísticas.
