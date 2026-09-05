# R2.0g.1 — Fundação super_admin-only do Assistente de Cópia Manual Mapeada

Data: 2026-09-05  
Tracking: #463 → #462 → #459 → #438 → #418

## Decisão de produto

O Assistente de Cópia Manual Mapeada é um serviço **exclusivo do `super_admin`**.
Nenhum outro papel do SIGESC pode consultar opções, ler a origem por este serviço,
listar destinos, executar preflight ou aplicar um lote. Ocultação de UI não é
considerada mecanismo de segurança: todos os endpoints fazem autorização backend
explícita e fail-closed.

## Motivação

A R2.0f confirmou que o calendário do 9º B e do 9º A não admite pareamento
automático seguro por data/carga. O caminho administrativo passa a ser seleção
humana explícita da data de destino, enquanto o sistema fica responsável por
validar escopo, autoria/vínculo, ocupação, fingerprints, idempotência e escrita
canônica.

## Arquitetura R2.0g.1

O adapter `backend/routers/manual_content_copy_admin.py` é instalado sobre o
setup do router canônico de `content_entries`, antes de `server.py` registrar o
router. Não reutiliza o endpoint de cópia do professor.

Endpoints do serviço (sob `/api/content-entries`):

- `GET /admin/manual-copy/options`;
- `GET /admin/manual-copy/source`;
- `GET /admin/manual-copy/destinations`;
- `POST /admin/manual-copy/preflight`;
- `POST /admin/manual-copy/apply`.

Todos exigem `AuthMiddleware.require_roles(["super_admin"])` e uma verificação
adicional de `user.role == "super_admin"`.

## Multi-tenancy

Mesmo para `super_admin`, o serviço é operacional, não control-plane. Portanto
exige uma mantenedora ativa selecionada e chama
`resolve_operational_tenant_context`. Escolas e turmas de origem/destino são
validadas contra a mantenedora operacional. O serviço não opera no modo "Todas".

## Autoria pedagógica

O `super_admin` é operador da reconstrução, não professor autor do conteúdo.
Por isso nenhuma data de destino é elegível sem um único vínculo/professor
resolvido.

Ordem de resolução:

1. vínculo DVD vigente e único;
2. vínculo DVD histórico/backfill único;
3. `teacher_assignments` legado com identidade de usuário canônica única;
4. snapshot de professor na frequência, igualmente resolvido para usuário canônico.

Ambiguidade ou identidade não resolvida tornam a data indisponível. O adapter
nunca usa `super_admin.id` como fallback de autoria pedagógica.

## Mapeamento e preflight

- o operador informa explicitamente `source_id → target_date`;
- `target_date` vazia significa `NÃO COPIAR`;
- duas origens não podem apontar para a mesma data;
- a data deve pertencer ao universo de frequência do destino no mês;
- data já ocupada por conteúdo canônico ou legado fica indisponível;
- origem é fingerprintada e revalidada;
- preflight produz manifesto determinístico SHA-256;
- apply recompõe o preflight e exige o mesmo hash.

Nenhuma heurística ordinal, mensal, por carga ou por sessão escolhe datas pelo
operador.

## Escrita e proteção contra corrida

O apply usa exclusivamente `save_content_canonical` e cria `content_entries` em
`draft`. Nunca cria ou atualiza `learning_objects`.

`expected_version=0` é enviado ao writer. Se surgir um rascunho concorrente entre
o preflight e o apply, o writer gera conflito em vez de atualizá-lo silenciosamente.

## Idempotência e rollback

Cada request de apply recebe uma chave Mongo `_id` determinística baseada em
`tenant + request_id`, aproveitando a unicidade nativa de `_id`. Duplo submit não
pode iniciar dois lotes equivalentes.

O serviço mantém em memória somente os IDs retornados pelo writer canônico nesta
execução. Em falha, o rollback compensatório faz soft-delete exclusivamente desses
IDs, mesmo se a atualização de provenance tiver falhado antes de gravar o batch ID.
O lote fica `FAILED_ROLLED_BACK`.

## Provenance

Cada registro criado recebe, entre outros:

- `manual_copy_batch_id`;
- `manual_copy_request_id`;
- `manual_copy_manifest_hash`;
- `manual_copy_type = MANUAL_MAPPED_CONTENT_COPY`;
- marcador de reconstrução administrativa;
- origem: ID/kind/turma/componente/data/fingerprint;
- destino: turma/componente/data/binding mode;
- `manual_copy_authorized_by` e timestamp.

Isso não converte a turma-espelho em prova histórica exata. O caso Luiz continua
sendo reconstrução administrativa institucional.

## Fora do escopo desta subfase

A R2.0g.1 não adiciona ainda a tela React. A R2.0g.2 implementará as duas colunas
Origem/Destino, filtros, seleção visual, botão Copiar e modal bloqueante fechável
somente por OK, mantendo visibilidade exclusiva do `super_admin`.

Nenhum deploy e nenhuma cópia de dados de produção fazem parte desta subfase.
O apply real do caso Luiz exigirá autorização humana explícita específica.
