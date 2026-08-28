# P0-F6 — Estação privada de adjudicação humana

Data: 2026-08-28

## Objetivo

Transformar o pacote privado P0-F5 em um fluxo operacional seguro para que um responsável humano autorizado registre as decisões necessárias sobre os conflitos de `DUPLICATE_COURSE_IDENTITY`, sem qualquer decisão automática e sem acesso ou escrita no MongoDB.

## Estado de entrada homologado

O P0-F5 de produção terminou com:

- 3 grupos de identidade duplicada;
- 68 conflitos P0-F4 integralmente expandidos;
- 144 unidades de decisão humana;
- 66 unidades de frequência;
- 3 unidades de nota;
- 75 unidades de conteúdo pedagógico;
- 0 conflitos de revisão não resolvidos;
- 144 decisões pendentes;
- nenhuma escrita em banco.

O pacote privado contém dados acadêmicos sensíveis e deve permanecer fora do GitHub.

## Arquitetura P0-F6

Arquivo principal:

`backend/scripts/build_p0f6_private_human_adjudication_station.py`

O utilitário não importa cliente MongoDB e possui somente duas operações locais:

### `build`

Entrada: pacote privado P0-F5.

Valida:

- fase P0-F5 esperada;
- `status=PASS`;
- SHA-256 canônico do pacote;
- cobertura completa;
- ausência de conflitos de revisão não resolvidos;
- contagem exata de unidades;
- IDs únicos;
- todas as unidades ainda `PENDING_HUMAN_DECISION`;
- contrato de decisão contendo `KEEP_SOURCE`, `KEEP_TARGET` e `MANUAL_RECONCILIATION`;
- ausência de recomendação automática.

Saída: HTML privado autocontido, modo `0600`, sem dependências de rede.

O HTML:

- usa CSP restritiva com `connect-src 'none'`;
- não carrega CSS, JavaScript, fontes, imagens ou APIs externas;
- apresenta SOURCE e TARGET lado a lado;
- mostra contexto e autoria disponíveis;
- exige nome e função/cargo do responsável;
- exige declaração explícita de autoridade;
- permite apenas as três decisões humanas previstas;
- exige justificativa para `MANUAL_RECONCILIATION`;
- não usa `localStorage`;
- exporta somente um JSON de decisões, sem alterar o pacote original.

### `seal`

Entradas:

- pacote P0-F5 original;
- JSON de decisões exportado pela estação.

Valida fail-closed:

- SHA do pacote de origem;
- identidade exata de todas as `review_unit_id`;
- nenhuma unidade desconhecida;
- nenhuma decisão duplicada;
- nenhuma unidade ausente;
- decisões limitadas ao conjunto permitido;
- nome e função do responsável;
- declaração de autoridade;
- justificativa obrigatória para reconciliação manual.

Saída: manifesto privado de decisões humanas, modo `0600`, contendo SHA-256 canônico próprio.

## Invariantes

1. P0-F6 não consulta MongoDB.
2. P0-F6 não contém `--apply` ou `--rollback`.
3. P0-F6 não executa remapeamento, merge, exclusão, criação ou desativação.
4. P0-F6 não recomenda SOURCE ou TARGET.
5. Todas as decisões são explicitamente humanas.
6. O HTML e o manifesto de decisões são privados e não devem entrar no GitHub.
7. O manifesto selado não constitui autorização para um executor futuro.
8. Qualquer executor posterior exige fase própria, backup, preflight, dry-run, rollback, CI, autorização de merge e autorização separada para escrita em produção.
9. AEE permanece fora do escopo.

## Privacidade

O HTML gerado incorpora o payload sensível P0-F5 e, portanto:

- deve ser armazenado apenas em ambiente autorizado;
- deve manter permissão `0600` quando em Linux;
- não deve ser publicado por HTTP;
- não deve ser anexado a PR, issue, workflow artifact ou log;
- deve ser transferido apenas por canal seguro para o responsável pela revisão.

O JSON bruto de decisões e o manifesto selado também devem ser tratados como privados, pois podem conter justificativas administrativas.

## Saída esperada da fase

P0-F6 será considerado concluído somente quando existir um manifesto selado contendo exatamente uma decisão humana válida para cada `review_unit_id` do P0-F5, com `pending_human_decisions=0` e sem qualquer escrita no banco.
