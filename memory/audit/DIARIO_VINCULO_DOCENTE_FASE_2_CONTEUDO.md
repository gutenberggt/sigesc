# Diário por Vínculo Docente v1.0 — Fase 2 — Registro de Conteúdos

**Status:** implementação em branch isolada / PR Draft #31  
**Branch:** `agent/diario-vinculo-fase2-conteudo`  
**Base:** `main` em `e3d6141538c5ac918dfa40090d19b2a4e4f46a59`

## 1. Objetivo

Conectar `content_entries` ao modelo de Diário por Vínculo Docente (DVD) sem alterar Frequência, Notas/Conceitos, PDFs ou AEE e sem executar backfill histórico.

Conteúdo é o primeiro consumidor real do `assignment_id` porque já é independente de frequência e possui autoria, versionamento, publicação/correção e auditoria próprios.

## 2. Regra dual-mode

A Fase 2 mantém coexistência explícita:

- registro sem `assignment_id`: **legado**, comportamento anterior preservado;
- registro com `assignment_id`: **DVD**, propriedade pedagógica por vínculo.

Nenhum documento histórico existente recebe `assignment_id` automaticamente nesta fase.

## 3. Separação essencial: criação x histórico

A autorização possui duas semânticas deliberadamente distintas.

### 3.1 Nova escrita / upsert

Criação usa o vínculo **vivo** por `authorize_assignment_access(...)` e exige:

- `diary_settings.enabled=true`;
- assignment não excluído;
- vigência na data do lançamento;
- turma/etapa dentro do escopo DVD;
- componente compatível;
- escola e tenant válidos;
- propriedade pedagógica ou override gerencial expresso;
- capability `content_enabled=true`.

### 3.2 Registro já constituído

Depois que o conteúdo foi criado, sua proveniência torna-se histórica. Leitura, update, publish, correct e delete usam `authorize_assignment_snapshot_access(...)`.

O assignment vivo é consultado apenas para conferir identidade estável:

```text
assignment_id
teacher_id
class_id
```

Campos administrativos mutáveis do assignment **não reclassificam retroativamente** o conteúdo já registrado. Portanto, um registro não desaparece se depois ocorrer:

- mudança de `component_id` do assignment;
- encurtamento de `valid_until`;
- `diary_settings.enabled=false`;
- mudança do perfil atual;
- soft-delete do assignment.

A autorização continua aplicando papel atual do usuário, acesso atual à escola, tenant atual e capabilities do **perfil histórico snapshotado**.

Hard-delete/orfandade do assignment ou divergência de `teacher_id/class_id` falham fechado.

## 4. Escrita DVD e anti-spoof

`ContentEntryCreate` aceita `assignment_id` opcional.

Quando existe DVD ativo para turma/componente/data:

1. `assignment_id` explícito é validado pelo serviço central;
2. se omitido e existir exatamente um vínculo DVD válido do próprio professor, o backend auto-resolve o vínculo para compatibilidade com a tela atual;
3. múltiplos vínculos próprios compatíveis geram ambiguidade e exigem `assignment_id` explícito;
4. DVD ativo de outro professor nunca cai silenciosamente no legado;
5. `teacher_id` do cliente não redefine autoria e divergência é rejeitada;
6. omitir `component_id` não permite escapar do DVD;
7. um registro existente com o mesmo assignment mas `teacher_id` incompatível bloqueia o upsert para não normalizar corrupção silenciosamente.

## 5. Snapshot/provenance do conteúdo

Novos registros DVD persistem no mínimo:

```text
assignment_id
assignment_profile_at_record
assignment_schema_version_at_record
teacher_id
teacher_name
class_id
component_id
school_id
mantenedora_id
```

`assignment_id` é a propriedade pedagógica canônica. `teacher_id`, componente, escola/tenant e perfil são snapshots do contexto autorizado no momento do registro. `created_by` e `updated_by` continuam representando autoria operacional.

Registro DVD sem snapshot mínimo (`assignment_id`, `teacher_id`, `class_id`, `assignment_profile_at_record`, `assignment_schema_version_at_record`) falha fechado.

A auditoria de conteúdo passa a incluir `assignment_id` em `extra_data`.

## 6. Chave natural e índices

O índice UNIQUE anterior era:

```text
(class_id, component_id, teacher_id, date, aula_numero)
```

Isso impediria dois assignments distintos do mesmo professor no mesmo contexto.

A Fase 2 separa as regras.

### Legado

```text
UNIQUE (class_id, component_id, teacher_id, date, aula_numero)
WHERE deleted=false AND assignment_id=null/missing
```

### DVD

```text
UNIQUE (class_id, component_id, assignment_id, date, aula_numero)
WHERE deleted=false AND assignment_id é string não vazia
```

Também é criado:

```text
INDEX (assignment_id, date desc)
```

A evolução é idempotente: o startup inspeciona `ux_content_entry_logical`; se ainda estiver com o filtro antigo `{deleted:false}`, ele é recriado uma única vez com o filtro legado. Nenhum documento é reescrito.

## 7. Leitura e isolamento

`GET /content-entries` recebe filtro opcional `assignment_id`.

Para registros DVD:

- professor proprietário vê seu conteúdo;
- professor não vê conteúdo DVD de outro vínculo;
- gestão autorizada obtém visão consolidada segundo escola/tenant;
- registro com snapshot inconsistente é omitido da listagem em vez de vazar dados;
- registros legados continuam com o comportamento anterior até a fase de migração.

`GET /content-entries/{id}` aplica a mesma autorização histórica para registros DVD.

## 8. Update, publish, correct e delete

Para registros DVD, passam por autorização de snapshot antes de qualquer mutação:

- `PUT /content-entries/{id}`;
- `POST /content-entries/{id}/publish`;
- `POST /content-entries/{id}/correct`;
- `DELETE /content-entries/{id}`.

Escrita gerencial requer `allow_management_override=true` no consumidor confiável e continua limitada pelas roles e capabilities definidas no contrato DVD.

Optimistic locking, `draft/published/corrected`, snapshot hash existente, correção institucional e soft-delete permanecem preservados.

## 9. Integrador

`integrator` possui `content_enabled=true`; portanto registra conteúdo normalmente pelo próprio assignment.

Esta fase não toca em frequência `pdf_only`, Notas/Conceitos ou PDFs.

## 10. Escopo educacional

Permanece o contrato das Fases 0/1:

- Educação Infantil;
- 1º ao 5º Ano;
- EJA 1ª e 2ª Etapa.

Ficam fora do DVD v1 nesta fase:

- 6º ao 9º;
- EJA 3ª/4ª;
- demais etapas;
- AEE.

Etapas fora do DVD continuam no caminho legado.

## 11. Arquivos da Fase 2

- `backend/routers/content_entries.py` — integração do domínio de conteúdo;
- `backend/services/content_assignment_scope.py` — resolução de nova escrita e filtro do conteúdo;
- `backend/services/diary_assignment_snapshot_access.py` — autorização histórica por snapshot;
- `backend/services/content_audit.py` — `assignment_id` na auditoria;
- `backend/startup/indexes.py` — unicidade separada legado/DVD;
- `backend/tests/test_content_assignment_scope_phase2.py` — isolamento/autorização;
- `backend/tests/test_content_assignment_scope_phase2_edges.py` — anti-bypass e imutabilidade histórica;
- `backend/tests/test_content_entry_indexes_phase2.py` — evolução idempotente dos índices;
- `.github/workflows/ci.yml` — guards da Fase 2.

## 12. Testes de proteção

Execução canônica atual:

```text
Fase 0: 54
Fase 1: 24
Fase 2: 29
TOTAL : 107
```

Os casos da Fase 2 cobrem, entre outros:

- legado preservado;
- auto-resolução inequívoca;
- assignment obrigatório/ambíguo;
- anti-spoof de professor e componente;
- omissão de componente sem fallback legado;
- integrador com conteúdo;
- isolamento entre professores;
- gestão e override;
- tenant fail-closed;
- proveniência corrompida bloqueada no upsert;
- componente histórico preservado;
- assignment expirado/desabilitado/soft-deleted sem apagar histórico;
- snapshot incompleto fail-closed;
- evolução idempotente dos índices.

## 13. O que NÃO muda

- nenhuma frequência é alterada;
- nenhuma nota/conceito é alterado;
- nenhum PDF é alterado;
- nenhum arquivo AEE é alterado;
- nenhum conteúdo histórico recebe assignment automaticamente;
- nenhuma tela `V2` é criada;
- nenhuma regra de avaliação é alterada.

## 14. Gate de aprovação

A Fase 2 somente pode sair de Draft após:

- **107/107** guards verdes no head final;
- `ruff` e `compileall` verdes;
- frontend build verde;
- startup real com MongoDB verde, incluindo criação dos novos índices;
- Gate de Transferência/Regressão verde;
- PR mergeável sobre a mesma `main`;
- diff revisado sem Frequência, Notas, PDFs ou AEE;
- validação final explícita antes do merge.
