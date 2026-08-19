# PR #52 — Paridade de Objetos de Conhecimento do Professor

## Objetivo

Completar a operação de **Objetos de Conhecimento** no Diário por Vínculo (DVD) para o professor sem reabrir escrita em `learning_objects`, sem migrar histórico e sem ampliar RBAC.

## Problemas encontrados

1. O atalho rápido do professor abria `/professor/objetos-conhecimento` sem `assignment_id`, enquanto o backend já bloqueia escrita legada em turma DVD.
2. Educação Infantil/Anos Iniciais usam seleção de vários componentes no mesmo dia, mas o bridge utilizava um único `assignment_id` da URL para todos os componentes.
3. A listagem diária sem componente enxergava somente o vínculo raiz, podendo ocultar componentes irmãos do mesmo professor.
4. `Copiar para outra turma` estava explicitamente indisponível no DVD.
5. O PDF de Anos Iniciais, quando aberto por um único vínculo e sem `course_id`, podia representar apenas aquele componente, em vez do conjunto de componentes do próprio professor na turma.
6. Registros históricos têm `assignment_id=null` por design; a cópia precisa preservar qual vínculo autorizado tornou cada item legado visível.

## Solução

### Entrada

O atalho **Objetos de Conhecimento** passa a posicionar o professor em **Meus Diários**. A abertura funcional continua ocorrendo pelo card do vínculo, com `assignment_id` explícito.

### Listagem e multi-componente

`contentDvdBridge.js` consulta somente `/professor/diarios`, já fail-closed, para resolver os vínculos de conteúdo do professor. Em Anos Iniciais/Infantil:

- a listagem sem componente agrega os assignments irmãos da mesma turma;
- cada componente mantém seu próprio `assignment_id`;
- criação/edição usa o assignment correspondente ao componente, e não necessariamente o assignment raiz da URL;
- histórico anterior ao cutover permanece read-only.

### Cópia entre turmas

Foi adicionada rota canônica sobre `content_entries`:

`POST /content-entries/{source_id}/copy-to-class`

Regras:

- exclusiva ao professor no fluxo DVD;
- origem canônica com assignment é reautorizada por `authorize_content_record`;
- origem sem assignment, inclusive `learning_objects`, exige `source_assignment_id` e precisa aparecer em `list_assignment_content_history`;
- destino exige `target_assignment_id` resolvido a partir dos diários autorizados do professor;
- criação do destino usa `save_content_canonical`;
- `learning_objects` é apenas lido como origem histórica e nunca recebe escrita;
- a cópia registra `copied_from_id`, `copied_from_source`, `copied_at` e auditoria.

### PDF

Para Educação Infantil/Anos Iniciais sem `course_id`, o PDF reúne os assignments de conteúdo do **mesmo professor e mesma turma** que estejam autorizados e com `content_enabled=true`.

Para Anos Finais/EJA final, ou quando `course_id` é informado, o PDF permanece estritamente no assignment selecionado.

O PDF não agrega conteúdo de outro professor: conteúdo é autoria por vínculo, diferentemente da frequência `class_daily`.

## Invariantes

1. `learning_objects` permanece histórico/legado e read-only no DVD.
2. Nenhum conteúdo histórico recebe `assignment_id` retroativamente.
3. Toda escrita nova ocorre em `content_entries` pelo motor canônico.
4. Tenant, escola, turma, professor e componente continuam fail-closed.
5. Um vínculo de um componente nunca é reutilizado como propriedade de outro componente.
6. O PDF não cruza autoria entre professores.
7. A cópia não pode usar uma origem histórica que não seja comprovadamente visível no vínculo informado.

## Campos pedagógicos ricos

Este PR **não altera o schema canônico de `content_entries`**. `resources`, `skill_codigos` e `adaptation_ids` continuam fora do contrato atual conforme decisão registrada em `memory/P1_BLUEPRINT_OPCAO_A.md` (P1.0: recursos descartados e BNCC redesenhado/não migrado).

Qualquer reintrodução desses campos exige decisão arquitetural separada para evitar perda silenciosa, dupla fonte curricular ou reativação acidental do schema legado.

## Critérios de aceite

- Acesso rápido não abre rota genérica sem vínculo.
- `Meus Diários → Conteúdos` mantém `assignment_id`.
- Anos Iniciais exibem histórico de todos os componentes autorizados do próprio professor.
- Novo lançamento multicomponente grava cada componente no seu assignment.
- Legado continua consultável e não editável.
- Cópia para turma/componente com vínculo DVD válido funciona e preserva a origem.
- Cópia para destino sem vínculo é bloqueada.
- PDF de Anos Iniciais reúne componentes irmãos do próprio professor.
- PDF de Anos Finais continua isolado por componente/vínculo.
- Nenhuma escrita em `learning_objects`.
