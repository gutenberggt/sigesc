# P0 #250 — F2.6: paridade de Conteúdo por componente

Data: 2026-08-30  
Status: **READY_FOR_REVIEW**

## Novo indício funcional

Após a F2.5 em produção e `Ctrl + F5`, a divergência de **Objetos de Conhecimento** permaneceu em vários meses do 5º ANO A da E M E I E F Jose Pereira Barbosa. O teste funcional acrescentou um padrão importante: os dias ausentes na visão da professora estão associados a registros de **Português/Língua Portuguesa e Matemática**.

Isso desloca o foco de “cache visual” para **paridade por componente**.

## Fatos já estabelecidos

- o 5º Ano é tratado como `fundamental_anos_iniciais`;
- `LearningObjects.loadRecords()` consulta Anos Iniciais por `class_id + academic_year + month`, sem `course_id`;
- o calendário usa `records.find(r => r.date === dateStr)` e a lista mensal renderiza `records.map(...)`, sem filtro posterior por `selectedCourses`;
- a F2.4 encontrou 9 componentes ativos no modelo legado, 7 matches raw no guard DVD e zero diários `content_enabled` canonicamente autorizados naquele instante;
- a F2.5 alinhou o guard legado à SSoT de `/professor/diarios`, removendo o 409 indevido quando não há candidato DVD canônico;
- mesmo assim, o padrão visual pós-deploy continuou.

## Hipóteses que a F2.6 separa

1. **Gap HTTP do professor**: o Mongo do tenant contém Português/Matemática, mas `GET /learning-objects` como professora não os devolve.
2. **Gap class-wide**: a consulta por componente devolve o registro, mas a consulta mensal class-wide usada pela tela não o devolve.
3. **Gap de tenant**: o Super Administrador sem escopo enxerga registros sem `mantenedora_id` ou de outro tenant, enquanto a professora (fail-closed no próprio tenant) não pode enxergá-los.
4. **Paridade HTTP/DB**: professor, superadmin scoped e Mongo do tenant são equivalentes; nesse caso o defeito restante está no runtime específico do navegador/impersonação, não no reader backend.
5. **Drift de vínculo**: Português/Matemática aparecem nos 9 `teacher_assignments`, mas possuem representação diferente/ausente em `teacher_class_assignments`. Esse dado é coletado como evidência estrutural, sem qualquer remediação automática.

## Coleta read-only

O coletor compara abril, maio e junho de 2026, por componente:

- `teacher_assignments` ativos do professor;
- `teacher_class_assignments` raw e habilitados/vigentes, sem emitir IDs;
- `learning_objects` direto no Mongo:
  - total sem filtro de tenant;
  - total no tenant da turma;
  - total com tenant ausente/nulo;
  - total pertencente a outro tenant, apenas em contagem;
- HTTP do professor:
  - GET mensal class-wide, exatamente como `LearningObjects.js`;
  - GET mensal filtrado por componente;
- HTTP do Super Administrador:
  - GET sem `X-Mantenedora-Id`;
  - GET explicitamente scoped ao tenant da turma.

O foco de saída destaca **Língua Portuguesa/Português** e **Matemática**, mas todos os componentes ativos são comparados.

## Sessões HTTP sem login

A auditoria não chama `/auth/login`. Ela resolve os usuários por leitura no Mongo e usa `auth_utils.create_access_token()` dentro do backend em execução para criar tokens efêmeros em memória. Nenhum token é persistido ou emitido.

## Classificações

- `PROFESSOR_CONTENT_ENTITLEMENT_DRIFT`
- `CONTENT_COMPONENT_HTTP_PROFESSOR_GAP`
- `CONTENT_COMPONENT_CLASSWIDE_PROJECTION_GAP`
- `CONTENT_COMPONENT_TENANT_SCOPE_GAP`
- `CONTENT_COMPONENT_HTTP_DB_PARITY`

## Limites de segurança

- MongoDB somente leitura;
- HTTP somente `GET`;
- nenhum POST/PUT/PATCH/DELETE no SIGESC;
- nenhuma alteração em `learning_objects`, vínculos, cursos, usuários ou tenant;
- nenhum texto de conteúdo emitido;
- nenhum ID de registro, vínculo, professor, estudante ou usuário emitido;
- nenhum dado de estudante lido;
- nenhum deploy/restart/backfill realizado pelo coletor;
- evidência estrutural privada em GitHub Actions.

## Gate de produção

Após CI, merge automático da instrumentação em `main` e confirmação do SHA exato, a auditoria somente poderá rodar por issue owner-only com:

Título:

`[P0-250-F2.6-COMPONENT-AUDIT] <TARGET_SHA>`

Corpo:

```text
P0_250_F2_6_AUDIT=AUTHORIZED
CONFIRMATION=VERIFY_P0_250_F2_6_COMPONENT_PARITY_READ_ONLY
TARGET_SHA=<40-hex>
```

O workflow falha fechado se `main` tiver avançado.

## O que esta fase não faz

A F2.6 não corrige registros, não altera `mantenedora_id`, não cria/remove vínculos, não muda RBAC, não faz backfill e não encerra a issue #250. Qualquer correção funcional será derivada do resultado live, não de hipótese.
