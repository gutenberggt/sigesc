# CLAUDE.md — Regras de trabalho no SIGESC

Este arquivo define as instruções persistentes para agentes Claude que trabalhem no repositório `gutenberggt/sigesc`.

## 1. Autoridade e fontes de verdade

Antes de alterar código, leia o contexto aplicável e trate como fontes persistentes de verdade, nesta ordem prática:

1. código, testes, contratos e migrations vigentes;
2. `README.md`;
3. `docs/governance/PROJECT_STATE_BASELINE_2026-08-27.md`;
4. `docs/governance/KNOWLEDGE_AND_CONVERSATION_GOVERNANCE.md`;
5. `memory/PRD.md` e documentação específica do domínio afetado;
6. GitHub Issues/PRs para backlog, decisões e trabalho em andamento.

Não substitua uma fonte canônica por suposições derivadas de conversa, comentário ou contexto transitório.

## 2. Fluxo Git obrigatório

- Nunca desenvolver diretamente em `main`.
- Nunca fazer merge autônomo em `main`.
- Trabalhar em branch dedicada e de escopo coerente.
- Manter mudanças incrementais e compatíveis.
- Abrir ou atualizar Pull Request para toda alteração destinada à `main`.
- Executar e respeitar os checks de CI aplicáveis.
- Resolver findings e threads relevantes antes de considerar o trabalho concluído.
- O merge em `main` exige autorização humana explícita do responsável pelo projeto.
- Deploy é uma etapa separada do merge e não deve ser iniciado implicitamente.

Se uma solicitação pedir bypass dessas regras, não execute o bypass; exponha o conflito no PR.

## 3. Invariantes arquiteturais

### Multi-tenancy e autorização

O SIGESC é SaaS multi-tenant. Toda leitura e escrita sensível deve respeitar tenant/mantenedora e RBAC.

- Use os mecanismos canônicos de `tenant_scope.py`, incluindo `apply_tenant_filter` e `resolve_tenant_id_for_create` quando aplicáveis.
- Não crie atalhos de consulta que ignorem tenant scope.
- Diante de tenant, autorização ou identidade ambígua, adote postura fail-closed.
- Preserve isolamento lógico entre mantenedoras.

### Fonte única de verdade — SSoT

- Não duplique regra de negócio existente em router, client, frontend ou helper paralelo.
- Localize a implementação canônica antes de criar nova lógica.
- Carga horária deve continuar derivada pela fonte canônica em `utils/carga_horaria_calculator.py` quando aplicável.
- Alterações de contrato ou comportamento devem vir acompanhadas de testes e documentação compatíveis.

### Backend e MongoDB

- Rotas backend devem permanecer sob `/api`.
- Não retornar `_id` do MongoDB em respostas; projete-o para fora.
- Use `datetime.now(timezone.utc)` em vez de `utcnow()`.
- Preserve separação entre routers, serviços, providers e clients conforme a arquitetura do domínio.

### Frontend

- Preserve RBAC e tenant scope no comportamento de navegação e carregamento de dados.
- Para ícones, prefira `lucide-react`; evite emojis usados como substitutos de iconografia de interface.

## 4. Áreas protegidas ou de alto risco

### AEE

O AEE é módulo protegido. Não realize alteração funcional no AEE sem autorização humana explícita registrada na solicitação/Issue/PR. Diagnóstico read-only é permitido quando solicitado.

### Diário por Vínculo — DVD

Trate DVD como migração/cutover controlado. Preserve guards, auditorias, compatibilidade necessária com histórico legado e testes de regressão. Não remova bridges/fallbacks de legado sem evidência e autorização compatíveis.

### MIG / MEC / CMDE

- Preserve a arquitetura modular de `backend/mig/`.
- Router MEC deve permanecer fino, sem regra de negócio e sem HTTP direto.
- Comunicação CMDE deve continuar centralizada no cliente/provider canônico.
- Não habilite scheduler ou envio real ao MEC/CMDE implicitamente.
- Não invente códigos, estados, identidade ou mapeamentos externos; falhe de forma fechada e auditável.
- Preserve simulador/dry-run enquanto requisitos de produção, homologação e autorização não estiverem explicitamente satisfeitos.

## 5. Segurança, segredos e dados pessoais

Nunca grave no Git:

- senhas;
- API keys;
- tokens OAuth;
- chaves privadas;
- `.env` de produção;
- credenciais SSH;
- dumps contendo dados pessoais;
- dados identificáveis de estudantes/professores usados apenas para diagnóstico.

Use GitHub Actions Secrets ou mecanismo equivalente para credenciais. Sanitize logs, fixtures, evidências e exemplos persistentes.

## 6. Procedimento antes de editar

Para cada tarefa de desenvolvimento:

1. Leia a Issue/PR e identifique o escopo exato.
2. Inspecione os arquivos e testes relacionados antes de escrever código.
3. Localize a SSoT e os invariantes afetados.
4. Avalie riscos de tenant scope, RBAC, dados pessoais e compatibilidade.
5. Identifique os checks de CI/testes relevantes.
6. Só então implemente a menor mudança coerente que resolva o problema.

Não faça refatoração oportunista fora do escopo sem justificativa explícita.

## 7. Testes e validação

Backend, quando aplicável:

```bash
cd backend
python -m pytest tests/ -q --asyncio-mode=auto
```

Também execute linters, builds e guards específicos já existentes para o domínio alterado. Não neutralize testes para obter CI verde. Se um teste revelar divergência real de contrato, corrija a implementação ou explique o bloqueio no PR.

## 8. Pull Request — conteúdo mínimo

Ao concluir, o PR deve registrar de forma objetiva:

- problema/objetivo;
- abordagem adotada;
- arquivos/domínios afetados;
- testes executados e resultado;
- riscos e compatibilidade;
- migrations/configurações necessárias, se houver;
- impacto em tenant/RBAC/segurança, quando aplicável;
- documentação atualizada, se necessária;
- qualquer decisão que exija validação humana.

Nunca declare validação que não foi realmente executada.

## 9. Definition of Done

Uma tarefa só está pronta para revisão humana quando:

- escopo solicitado foi atendido;
- SSoT e invariantes foram preservados;
- não houve bypass de segurança ou tenant scope;
- testes relevantes foram executados ou a impossibilidade foi documentada;
- CI aplicável está verde ou os bloqueios estão explicitados;
- documentação necessária acompanha a alteração;
- não há segredo ou dado pessoal indevido no diff;
- o PR está pronto para revisão;
- nenhum merge em `main` foi realizado pelo agente.
