# P0 #250 — F2.4: paridade HTTP/runtime de Objetos de Conhecimento

Data: 2026-08-30  
Base analisada: `main` em `7992f46901f0be91bfc92316170ec898e3cc00f5`  
Caso-canário: E M E I E F Jose Pereira Barbosa — 5º ANO A — 2026 — professora Abadia Alves Martins.

## 1. Objetivo

A F2.3 provou paridade estrutural dos 45 registros legados de junho/2026 quando o fallback do professor é **modelado** como o mesmo reader legado da gestão. A F2.4 verifica o contrato efetivo que decide se esse fallback consegue ou não chegar ao navegador.

Nenhuma correção funcional faz parte desta etapa.

## 2. Achado estático que justifica a F2.4

Há uma fronteira incompatível entre o frontend e o backend:

1. `contentDvdBridge.js` consulta `/professor/diarios`. Se não existir diário da turma com `capabilities.content_enabled=true`, `contentDiariesFor()` devolve zero candidatos e o bridge deixa o `GET /learning-objects` seguir inalterado (`if (candidates.length === 0) return config;`).
2. `GET /learning-objects`, porém, executa `_block_legacy_if_dvd(current_user, class_id, course_id)` antes da leitura.
3. `legacy_content_dvd_guard.py` bloqueia o legado quando existe `teacher_class_assignment` vigente com `diary_settings.enabled=true` para professor/turma. Esse teste não passa pela mesma revalidação de `authorize_assignment_access()` usada por `/professor/diarios`.
4. `list_teacher_diaries()` revalida cada candidato canônico e contabiliza como `blocked_total` os assignments que falham nessa autorização.
5. Em `LearningObjects.js`, uma falha de `loadRecords()` é apenas enviada a `console.error`; o estado `records` não é limpo no `catch`. Assim, se o request atual retornar 409 e houver registros de uma carga anterior, a tela pode continuar exibindo um subconjunto antigo, dando aparência de leitura parcial.

Isso produz uma hipótese falsificável e mais específica que a F2.3:

`/professor/diarios -> 0 content-enabled para a turma`  
`contentDvdBridge -> fallback /learning-objects`  
`legacy_content_dvd_guard -> 409`  
`LearningObjects -> mantém records anteriores se existirem`.

## 3. Relação com a evidência F2.3

O artefato F2.3 no SHA `7992f469...` registrou:

- `management_legacy_record_count = 45`;
- `professor_projection_record_count = 45` no modelo de fallback;
- `dvd_content_diary_count = 0`;
- `dvd_blocked_diary_count = 16`;
- 30/06, 29/06, 27/06 e 26/06 presentes no conjunto legado;
- os registros do conjunto auditado pertencem aos vínculos da própria professora no caso-canário.

O ponto que a F2.3 não avaliou foi o **guard HTTP do endpoint legado**. A F2.4 cobre exatamente essa lacuna.

## 4. Coletor F2.4

`backend/scripts/p0_250_f2_4_content_runtime_contract_audit.py` usa somente leituras e os próprios contratos canônicos do código para medir, na turma-alvo:

- quantidade de diários retornados por `list_teacher_diaries()`;
- quantidade de diários com `content_enabled=true`;
- quantidade de documentos que casam com `build_professor_dvd_query()` do guard legado;
- quantidade de componentes ativos em `teacher_assignments`;
- cardinalidade legada de junho/2026;
- presença estrutural das datas reportadas visualmente;
- metadados não sensíveis de nível/série da turma.

Classificação prioritária:

`CONTENT_RUNTIME_LEGACY_FALLBACK_BLOCKED`

quando o frontend deve cair no legado (`content_enabled_diary_count=0`) mas o backend bloquearia esse mesmo legado (`legacy_guard_match_count>0`).

## 5. Probe de navegador, sem deploy

`memory/audit/tools/p0_250_f2_4_browser_probe.js` é um observador XHR opcional para Chrome DevTools. Ele não dispara requisições e não altera request/response. Observa apenas futuros GETs de:

- `/professor/diarios`;
- `/learning-objects`;
- `/content-entries`.

O relatório contém somente rota, status, presença dos filtros, ano/mês, contagem de registros, quantidade de datas, datas e quantidade de componentes. IDs, conteúdo e PII não são registrados.

Esse probe permite confirmar o HTTP real sob a sessão de Super Administrador e sob a sessão impersonada da professora, sem modificar o bundle e sem novo deploy.

## 6. Gate de produção

A coleta Mongo read-only permanece bloqueada até:

1. PR F2.4 aprovado e mergeado;
2. `main` estabilizada em um SHA exato;
3. autorização humana explícita vinculada a esse SHA;
4. abertura de issue-gatilho com:

```text
P0_250_F2_4_AUDIT=AUTHORIZED
CONFIRMATION=VERIFY_P0_250_F2_4_CONTENT_RUNTIME_READ_ONLY
TARGET_SHA=<sha-exato-da-main>
```

Título exato:

```text
[P0-250-F2.4-RUNTIME-AUDIT] <sha-exato-da-main>
```

## 7. Invariantes

- MongoDB somente leitura.
- Nenhum `insert/update/delete/bulk_write/drop`.
- Nenhum backfill ou remapeamento.
- Nenhuma alteração em conteúdos, notas, frequência, componentes ou vínculos.
- Nenhum HTTP de produção executado pelo coletor backend.
- Nenhum texto de conteúdo, ID de registro, ID docente, ID de estudante, PII de estudante ou credencial emitido.
- Nenhum merge ou deploy automático por esta etapa.
- A issue #250 permanece aberta.

## 8. Critério para a próxima decisão

Se a classificação for `CONTENT_RUNTIME_LEGACY_FALLBACK_BLOCKED`, a correção seguinte deve alinhar a decisão do bridge e do guard à mesma SSoT/capability canônica e tratar explicitamente o estado de erro da UI. Não se deve corrigir banco nem ampliar RBAC para resolver essa divergência.

Se o guard não casar com a turma, o browser probe passa a ser o próximo discriminador obrigatório para localizar a diferença no HTTP real ou em estado/race do frontend.
