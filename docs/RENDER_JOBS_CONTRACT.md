# Contrato Normativo: Document Render Jobs

> **Status: CONGELADO V1 (Fev/2026).**
> Documento normativo. Implementação reservada para o passo 4 da sequência
> proposta pelo owner: `academic_events → observability → fechamento → render_jobs → boletim → PDF → histórico`.

```yaml
contract_version: 1
schema_version: 1
status: FROZEN
issued_at: 2026-02-08
```

## 1. Princípio fundador

> **PDF é consequência do snapshot, nunca fonte de verdade.**

Render síncrono inline na requisição do usuário destrói:
- performance (gera latência inaceitável em horários de pico);
- rastreabilidade (sem registro de qual template/engine foi usado);
- reemissão (não há como reproduzir o mesmo PDF);
- versionamento (não há histórico de quais layouts existiram).

Toda geração de PDF passa por uma fila assíncrona com job persistido.

---

## 2. Modelo canônico (`db.document_render_jobs`)

```json
{
  "id": "<uuid>",
  "document_type": "dependency_completion | bulletin | history | enrollment_certificate",
  "source_snapshot_id": "<id em dependency_completions / bulletin_snapshots / etc>",
  "source_collection": "dependency_completions",

  "template_version": "boletim_v3.1.0",
  "render_engine_version": "weasyprint-60.x",
  "render_options": {
    "page_size": "A4",
    "include_qr": true,
    "watermark": null
  },

  "status": "pending | processing | completed | failed | superseded",

  "generated_file_id": null,            // id em files collection / object storage
  "generated_file_size_bytes": null,
  "generated_at": null,
  "error_message": null,
  "retry_count": 0,
  "max_retries": 3,
  "next_retry_at": null,

  "requested_by_user_id": "...",
  "requested_at": "ISO timestamp",
  "request_ip": "...",
  "request_user_agent": "...",

  "mantenedora_id": "...",
  "school_id": "...",

  "audit_trail": [
    {"action": "queued", "at": "...", "by_user_id": "..."},
    {"action": "processing", "at": "...", "worker_id": "..."},
    {"action": "completed", "at": "...", "file_id": "...", "duration_ms": 1234}
  ]
}
```

---

## 3. Ciclo de vida

```
pending → processing → completed
                  ↓
                failed → (retry com backoff exponencial)
                  ↓
            (após max_retries) failed permanente
```

Estados terminais: `completed`, `failed` (após retries), `superseded`.

`superseded` é usado quando um novo job para o mesmo `source_snapshot_id` é
solicitado antes do anterior completar — preserva auditoria sem confundir
o usuário.

### 3.1 Retry policy

- Backoff exponencial: 30s, 2min, 10min.
- `max_retries` default = 3.
- Erros não-recuperáveis (ex.: snapshot não existe) → `failed` imediato sem retry.

---

## 4. Princípios de imutabilidade

- `template_version` e `render_engine_version` são SNAPSHOTS — capturados
  na criação do job e preservados mesmo se a versão default mudar depois.
- `source_snapshot_id` aponta para snapshot imutável (já hash-validado).
- Reemissão de job antigo deve gerar PDF idêntico ao original (mesmo template,
  mesmo engine, mesmo dado canônico).

---

## 5. Política de retenção

- Jobs `completed` / `failed`: retidos para sempre (auditoria documental).
- Arquivos PDF gerados: retidos 7 anos por padrão (ajustável por mantenedora).
- Após retenção, arquivo é movido para storage frio (cold storage); job
  permanece em coleção viva com `file_archived: true`.

---

## 6. Idempotência

Job é idempotente por `(source_snapshot_id, document_type, template_version, render_engine_version)`:
- Solicitação duplicada antes do anterior completar → retorna o job pending existente.
- Solicitação duplicada após completar → retorna o job completed existente.
- **Reemissão explícita** exige flag `force_reissue: true` no payload + audit log.

---

## 7. Endpoints planejados (Fase 4)

```
POST   /api/render-jobs                    Cria job (status pending)
GET    /api/render-jobs/{id}               Consulta status do job
GET    /api/render-jobs?source_id=...      Lista jobs de um snapshot
POST   /api/render-jobs/{id}/retry         Força retry manual (admin only)
GET    /api/render-jobs/{id}/file          Download do PDF (auth-protected)
GET    /api/public/render-jobs/{token}/file  Download via verification_token (público, leitura única ou TTL)
```

---

## 8. Integração com snapshots

```
dependency_completion (snapshot)
    └─ render_job 1 (boletim_v3.0.0, weasyprint-60.x)  → PDF v3.0.0
    └─ render_job 2 (boletim_v3.1.0, weasyprint-60.x)  → PDF v3.1.0
    └─ render_job 3 (historico_v1.0.0, ...)            → PDF histórico
```

Um snapshot pode gerar múltiplos PDFs (boletim + histórico) — cada PDF é um
job independente com versionamento próprio.

---

## 9. Observabilidade

Canal `render_jobs` em `utils/observability.py` (a implementar):
- `job_duration_ms` (avg, p95, p99)
- `queue_depth_pending`
- `failure_rate_pct`
- `retry_count_distribution`
- `template_version_usage` (qual layout está sendo mais usado)

---

## 10. Implementação obrigatória ANTES do PDF

Esta fila DEVE ser implementada antes de qualquer endpoint que gere PDF
síncrono. Caso contrário:
- Latência inaceitável em horários de pico.
- Sem rastreabilidade.
- Sem reemissão fiel.
- Sem versionamento.

---

## 11. Não tocar nesta V1 (escopo futuro)

- Geração inline (síncrona) — proibida.
- PDFs gerados client-side (browser print) — proibidos para documentos oficiais.
- Edição de PDF gerado — impossível por design (PDF é cópia do snapshot).

---

## 12. Cenários de teste obrigatórios (quando implementar)

1. Job criado com sucesso — status `pending` retornado imediatamente.
2. Worker processa job → status `processing` → `completed` com `file_id` populado.
3. Job idempotente: 2ª solicitação retorna o job existente.
4. `force_reissue: true` cria novo job mesmo havendo `completed`.
5. Job falha → retry após 30s → retry após 2min → retry após 10min → `failed` permanente.
6. Job superseded: novo job no mesmo snapshot pendente → antigo vira `superseded`.
7. Reemissão: chamar render_job com `template_version` antiga gera PDF idêntico ao original.
8. Endpoint `/file` retorna 404 se job não está `completed`.
9. Endpoint público `/render-jobs/{token}/file` valida `verification_token` antes de servir.
10. Hash do PDF gerado bate com `pdf_hash_sha256` armazenado no job.
