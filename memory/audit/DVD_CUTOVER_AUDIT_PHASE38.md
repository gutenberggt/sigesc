# PR #38 — Auditoria READ-ONLY do Cutover DVD

## Objetivo

Medir o estado real antes de qualquer migração de **Frequência** e **Conteúdos** para o Diário por Vínculo Docente (DVD).

Esta etapa **não altera dados**. Ela não habilita `diary_settings`, não cria `teacher_class_assignments`, não migra `attendance`, não copia `learning_objects` para `content_entries` e não atribui autoria histórica.

## Fontes de verdade auditadas

### Vínculo legado

`teacher_assignments` — fluxo usado atualmente por `/professor/turmas` e pelos cards `Fluxo atual`.

Chave operacional analisada: `staff_id + class_id + course_id + academic_year`, com `status=ativo`.

### Vínculo DVD

`teacher_class_assignments` — responsabilidade pedagógica temporal.

O vínculo só é considerado efetivamente no DVD quando:

1. pertence ao mesmo professor/turma/componente compatível;
2. está vigente na `reference_date`;
3. `deleted != true`;
4. `diary_settings.enabled == true`;
5. o profile é `regular`, `integrator` ou `shared`;
6. não é `shared/group` enquanto não existir lista canônica/auditável de estudantes.

O escopo de etapa reutiliza `services.diary_assignment_contract.is_class_in_scope`: Educação Infantil, 1º–5º Ano e EJA 1ª/2ª Etapa; AEE permanece excluído.

## Classificação de cada vínculo legado elegível

| Código | Interpretação |
|---|---|
| `dvd_active_exact` | exatamente um DVD compatível, vigente e habilitado; vínculo pronto para operar pelo DVD |
| `dvd_missing` | não existe `teacher_class_assignment` compatível |
| `dvd_present_disabled` | vínculo temporal existe, mas DVD não foi habilitado |
| `dvd_present_not_current` | vínculo existe, porém não está vigente na data de referência |
| `dvd_active_ambiguous` | mais de um DVD vigente/habilitado é compatível; bloqueia cutover automático |
| `dvd_active_group_unresolved` | `shared/group` ainda sem lista canônica de estudantes |
| `dvd_enabled_invalid_profile` | configuração habilitada com profile não reconhecido |
| `teacher_identity_unresolved` | não foi possível resolver `staff_id` para um usuário proprietário; não inferir |
| `class_unresolved` | turma referenciada não foi encontrada |

`remaining_legacy_or_unsafe_bindings` = vínculos legados elegíveis que **não** estão em `dvd_active_exact`.

Isso é uma métrica de trabalho pendente, não uma ordem de migração.

## Estado por turma

- `fully_cutover`: todos os vínculos legados elegíveis da turma possuem cobertura DVD exata;
- `partially_cutover`: existe DVD ativo, mas pelo menos um vínculo legado da turma ainda não tem cobertura exata;
- `legacy_only`: há vínculo legado elegível e nenhum cutover seguro;
- `dvd_only`: há DVD vigente/habilitado e não há vínculo legado ativo correspondente no ano;
- `no_teacher_binding`: turma elegível sem vínculo legado nem DVD vigente/habilitado.

`partially_cutover` merece atenção especial porque o dashboard atual elimina o fallback legado por `class_id`. Uma turma parcialmente convertida pode esconder componentes legados quando qualquer DVD da turma já aparece em `Meus Diários`.

## Frequência

A auditoria separa:

- documentos oficiais com `assignment_id`;
- documentos oficiais legados sem `assignment_id`;
- pares distintos `class_id + date` legados;
- total de linhas de estudante dentro dos documentos legados;
- documentos legados em turmas que já possuem DVD vigente/habilitado;
- `attendance_documentary` (`pdf_only`).

Nenhum registro sem autoria é reatribuído.

## Conteúdos

A auditoria separa:

- `learning_objects` — legado ainda usado por `LearningObjects.js`;
- `content_entries` sem `assignment_id` — conteúdo canônico ainda legado;
- `content_entries` com `assignment_id` — DVD;
- registros `learning_objects` em turmas que já possuem DVD ativo;
- sobreposição por `class_id + componente + date` entre legado e DVD.

A sobreposição serve apenas como alerta de reconciliação. Não significa que os textos sejam equivalentes nem que um registro possa ser descartado.

## Segurança da auditoria

Arquivos:

- `backend/services/dvd_cutover_audit.py`
- `backend/scripts/audit_dvd_cutover.py`
- `backend/tests/test_dvd_cutover_audit_phase38.py`

O teste de guard rejeita a presença, nesses arquivos, de chamadas Mongo como `insert_one`, `update_one`, `update_many`, `delete_one`, `delete_many`, `bulk_write`, `create_index` e equivalentes.

O único efeito opcional é `--json CAMINHO`, que grava uma cópia **local** do relatório no filesystem do container.

## Execução prevista em produção

A execução deve usar o backend de produção e o mesmo `.env` que contém `MONGO_URL` e `DB_NAME`:

```bash
cd /app/backend
python scripts/audit_dvd_cutover.py \
  --academic-year 2026 \
  --reference-date 2026-08-18 \
  --json /tmp/dvd-cutover-audit-2026.json
```

Como o PR ainda não deve ser deployado apenas para auditar, o script também pode ser executado por stdin a partir da branch do PR, com `docker exec -i -w /app/backend ... python -`, sem alterar a imagem/container. Essa execução será orientada somente depois que os guards do PR estiverem verdes.

## Gate antes de qualquer migração

Nenhuma migração/cutover será implementada até termos:

1. saída real da auditoria de produção;
2. contagem exata de `remaining_legacy_or_unsafe_bindings`;
3. lista de turmas `partially_cutover` e `legacy_only`;
4. volume de frequência legada e conteúdo legado em turmas já DVD;
5. decisão explícita de tratamento para cada categoria ambígua/não resolvida.
