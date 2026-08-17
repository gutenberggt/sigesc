# Diário por Vínculo Docente v1.0 — Fase 2 — Registro de Conteúdos

**Status:** implementação em branch isolada  
**Branch:** `agent/diario-vinculo-fase2-conteudo`  
**Base:** `main` em `e3d6141538c5ac918dfa40090d19b2a4e4f46a59`

## 1. Objetivo

Conectar `content_entries` ao modelo de Diário por Vínculo Docente (DVD) sem alterar Frequência, Notas/Conceitos, PDFs ou AEE e sem executar backfill histórico.

Conteúdo foi escolhido como primeiro consumidor porque já é um domínio independente de frequência, possui autoria docente própria e optimistic locking/auditoria consolidados.

## 2. Regra de compatibilidade

A Fase 2 é dual-mode:

- registro sem `assignment_id`: **legado**, com comportamento anterior preservado;
- registro com `assignment_id`: **DVD**, sujeito à autorização central da Fase 1.

Nenhum documento histórico recebe `assignment_id` automaticamente nesta fase.

## 3. Escrita DVD

`ContentEntryCreate` passa a aceitar `assignment_id` opcional.

Quando há DVD ativo para turma/componente/data:

1. `assignment_id` explícito é validado por `authorize_assignment_access(...)`;
2. se omitido e houver exatamente um vínculo DVD válido do próprio professor, o backend auto-resolve o vínculo para preservar compatibilidade com a tela atual;
3. se houver múltiplos vínculos próprios compatíveis, a escrita é bloqueada como ambígua;
4. se houver DVD ativo mas nenhum vínculo válido do usuário, não há fallback para o legado;
5. `teacher_id` informado pelo cliente não redefine autoria; se divergir do vínculo, a requisição é rejeitada;
6. `teacher_id` e `teacher_name` persistidos são derivados/snapshotados do assignment autorizado.

Omitir componente também não pode ser usado para escapar do DVD: a presença de vínculos ativos na turma continua sendo detectada e o resolvedor falha em vez de cair silenciosamente no legado.

## 4. Propriedade e provenance

Novos registros DVD persistem:

```text
assignment_id
assignment_profile_at_record
assignment_schema_version_at_record
teacher_id
teacher_name
class_id
component_id
```

`assignment_id` é a propriedade pedagógica canônica. `teacher_id` permanece como snapshot denormalizado de autoria pedagógica. `created_by`/`updated_by` continuam representando autoria operacional.

A auditoria (`content_audit`) passa a incluir `assignment_id` em `extra_data`.

## 5. Chave natural e índices

O índice UNIQUE anterior era:

```text
(class_id, component_id, teacher_id, date, aula_numero)
```

Isso impediria dois assignments distintos do mesmo professor no mesmo contexto.

A Fase 2 separa as regras:

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

Também é criado índice de consulta:

```text
(assignment_id, date desc)
```

A evolução é idempotente: o startup inspeciona `ux_content_entry_logical`; se ainda possuir o filtro antigo `{deleted:false}`, ele é recriado uma única vez com o filtro legado. Nenhum documento é alterado.

## 6. Leitura

`GET /content-entries` recebe filtro opcional `assignment_id`.

Registros DVD retornados por listagens são filtrados pela autorização central:

- professor proprietário vê seu conteúdo;
- professor não vê registros DVD de outro vínculo;
- gestão autorizada mantém visão consolidada conforme escola/tenant;
- registros legados são preservados nesta fase, pois sua migração ocorrerá posteriormente.

`GET /content-entries/{id}` também autoriza registros DVD pelo assignment real.

## 7. Update, publish, correct e delete

Para registros com `assignment_id`, todas as operações abaixo passam pelo serviço central antes da mutação:

- `PUT /content-entries/{id}`;
- `POST /content-entries/{id}/publish`;
- `POST /content-entries/{id}/correct`;
- `DELETE /content-entries/{id}`.

Escrita gerencial utiliza `allow_management_override=true` no consumidor confiável (router), mas continua limitada pelas roles e capabilities definidas na Fase 1.

Registros legados mantêm o fluxo anterior.

## 8. Integrador

O perfil `integrator` possui `content_enabled=true`; portanto pode registrar conteúdo normalmente pelo seu assignment.

A Fase 2 não toca em sua frequência opcional `pdf_only` nem em Notas/Conceitos.

## 9. Escopo educacional

O escopo continua herdado das Fases 0/1:

- Educação Infantil;
- 1º ao 5º Ano;
- EJA 1ª e 2ª Etapa.

AEE permanece excluído. 6º-9º, EJA 3ª/4ª e demais etapas continuam no comportamento legado.

## 10. Arquivos da Fase 2

- `backend/routers/content_entries.py` — integração real do domínio;
- `backend/services/content_assignment_scope.py` — resolução/isolamento por vínculo;
- `backend/services/content_audit.py` — `assignment_id` na auditoria;
- `backend/startup/indexes.py` — coexistência de unicidade legado/DVD;
- `backend/tests/test_content_assignment_scope_phase2.py` — autorização e isolamento;
- `backend/tests/test_content_entry_indexes_phase2.py` — migração idempotente dos índices;
- `.github/workflows/ci.yml` — inclusão dos guards da Fase 2.

## 11. O que NÃO muda

- nenhuma frequência é alterada;
- nenhuma nota/conceito é alterado;
- nenhum PDF é alterado;
- nenhum arquivo AEE é alterado;
- nenhum conteúdo histórico recebe assignment automaticamente;
- nenhuma tela nova `V2` é criada;
- a página atual continua podendo operar no modo legado e, em DVD inequívoco, o backend auto-resolve o único vínculo do professor.

## 12. Critérios para aprovação

A Fase 2 só pode ser mesclada após:

- todos os guards Fase 0 + Fase 1 + Fase 2 verdes;
- `ruff` e `compileall` verdes;
- startup real com MongoDB confirmando a evolução dos índices;
- frontend build verde;
- Gate de Transferência/Regressão verde;
- diff restrito ao domínio de conteúdo/infra de teste;
- validação de que AEE, Frequência, Notas e PDFs não foram tocados.
