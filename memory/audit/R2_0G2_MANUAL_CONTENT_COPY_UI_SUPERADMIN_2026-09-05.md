# R2.0g.2 — Interface operacional Origem → Destino — super_admin-only

Data: 2026-09-05  
Tracking: #467  
Parent: #462  
Fundação backend: #463 / PR #466 / `main@713a93abccde99247a04cc94a39d692cc08dfb5e`

## Objetivo

Implementar a superfície operacional do Assistente de Cópia Manual Mapeada de Conteúdo sem ampliar a autorização já definida na R2.0g.1.

A interface serve a operações administrativas excepcionais em que o calendário/turma não permite inferência automática segura. O operador humano escolhe explicitamente a data destino de cada registro-fonte; o sistema valida, congela o manifesto e grava pela SSoT canônica.

## Decisão de hardening da superfície

A R2.0g.2 **não cria uma nova rota React**.

O acesso é realizado por um launcher global `Cópia de Conteúdo`, renderizado no `Layout` somente quando o papel efetivo é exatamente:

`super_admin`

O próprio componente repete a checagem e retorna `null` para qualquer outro papel. Essa escolha evita:

- descoberta/acesso por URL de uma página dedicada;
- exposição por `permission_overrides` / Matriz de Permissões;
- dependência de regra de menu mutável;
- permanência do launcher durante impersonação para outro papel.

A autorização real continua no backend R2.0g.1, que exige `super_admin` exato nos cinco endpoints.

## UX implementada

Interface de tela cheia em duas colunas **Origem** e **Destino**.

Filtros:

- mês/ano;
- escola de origem;
- turma de origem;
- escola de destino;
- turma de destino;
- componente curricular único para ambos os lados.

### Origem

Exibe cronologicamente:

- data do conteúdo;
- carga/número de aulas;
- origem `content_entries` (canônico) ou `learning_objects` (legado);
- conteúdo em leitura;
- metodologia e observações quando existentes.

### Destino

Cada linha da origem possui seleção explícita de uma data destino.

Regras de UI:

- padrão `NÃO COPIAR`;
- nenhuma data é escolhida automaticamente;
- datas que o backend marca indisponíveis permanecem visíveis, porém desabilitadas;
- uma data já escolhida por outra linha fica desabilitada;
- quando selecionada, a UI mostra sessões, carga declarada, professor e modo de vínculo resolvido.

## Fluxo de escrita protegido

1. carregar opções tenant-scoped;
2. carregar origem e destinos somente com filtros completos;
3. operador cria o mapa manual;
4. cliente impede duplicidade óbvia de destino;
5. botão `Copiar` chama `/preflight`;
6. se o preflight for inválido, **não há chamada a `/apply`**;
7. se válido, exibe confirmação explícita com contagem e hash;
8. confirmação chama `/apply` com o MESMO `request_id`, o MESMO mapa congelado e `manifest_hash` retornado pelo preflight;
9. durante execução, botões ficam bloqueados contra clique duplicado;
10. resultado aparece em modal bloqueante.

## Modal final

O resultado de sucesso/erro é exibido em modal sobreposto com `role=alertdialog`.

Contrato:

- não fecha clicando no backdrop;
- não fecha com `Escape` — o evento é interceptado;
- somente o botão `OK` encerra o aviso;
- sucesso informa `copied_count`, `skipped_without_target` e `batch_id`;
- erro nunca é convertido em mensagem de sucesso.

## Transporte e segurança

A UI não monta Authorization, tenant ou CSRF por conta própria.

O cliente `manualContentCopyApi.js` utiliza `apiFetch` da SSoT `frontend/src/services/api.js`, preservando:

- cookie HttpOnly;
- Bearer de retrocompatibilidade;
- `X-Mantenedora-Id`;
- `X-CSRF-Token` para POST.

Endpoints consumidos:

- `GET /api/content-entries/admin/manual-copy/options`
- `GET /api/content-entries/admin/manual-copy/source`
- `GET /api/content-entries/admin/manual-copy/destinations`
- `POST /api/content-entries/admin/manual-copy/preflight`
- `POST /api/content-entries/admin/manual-copy/apply`

## Boundary desta PR

Esta fase prepara **código de UI**.

Não está autorizado por esta PR:

- deploy em produção;
- execução de preflight do caso Luiz em produção;
- execução de apply do caso Luiz;
- qualquer cópia de conteúdo;
- alteração de frequência;
- alteração de `learning_objects`.

Após CI verde, o merge exige autorização humana explícita. Mesmo depois do merge, qualquer uso em produção para reconstrução acadêmica exige gate específico de escrita.