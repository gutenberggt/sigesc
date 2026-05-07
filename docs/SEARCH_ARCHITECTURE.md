# Arquitetura de Busca — SIGESC

> **Status**: Diretriz arquitetural **OBRIGATÓRIA** desde Fev/2026.
> Aplicável a toda nova feature ou refatoração que envolva busca de entidades
> (alunos, servidores, escolas, turmas, responsáveis, planos AEE etc.).

---

## 1. Princípio fundamental

> **O frontend NUNCA carrega listas completas para filtrar localmente.**

Toda busca passa por endpoint server-side dedicado, indexado, com payload mínimo.
O frontend apenas dispara queries com debounce/cancelamento e renderiza resultados.

### Por quê?

- Performance: bases de prefeituras grandes podem ter dezenas de milhares de alunos.
- Memória: mantém o navegador leve, mesmo em dispositivos modestos.
- LGPD: frontend só recebe o estritamente necessário (CPF mascarado, sem dados sensíveis extras).
- Multi-tenancy: tenant scope é aplicado **no backend**, fonte de verdade.
- Tráfego: payloads de 10kB em vez de MBs.

---

## 2. Anatomia do endpoint canônico

### Convenção de nome

| ❌ Evite               | ✅ Prefira                          | Motivo                                      |
|------------------------|-------------------------------------|---------------------------------------------|
| `/api/{x}/search`      | `/api/{x}/autocomplete` ou `/lookup`| `/search` cresce descontroladamente (filtros, paginação, ordenação, exportação). Autocomplete é **caso específico** que precisa permanecer **enxuto**. |

### Contrato

```http
GET /api/students/autocomplete?q=joao&limit=10[&school_id=...&class_id=...&status=...]
Authorization: Bearer <token>
```

### Resposta

```json
{
  "items": [
    {
      "id": "uuid",
      "full_name": "João da Silva",
      "cpf_masked": "***.456.***-01",
      "school_id": "uuid",
      "school_name": "EMEF São Francisco",
      "class_id": "uuid",
      "class_name": "5º ano A",
      "status": "active"
    }
  ],
  "used_fallback": false
}
```

---

## 3. Estratégia de matching

### Prefix-first (caminho rápido)

Usa o índice composto `(mantenedora_id, nome_busca)` no MongoDB. **Ordens de magnitude mais rápido** que regex genérico.

```python
{'nome_busca': {'$regex': f'^{q_normalized}'}}
```

### Fallback contains — **com proteção crítica**

Aciona apenas se **AMBAS** as condições forem verdadeiras:

1. Prefix retornou **menos de 3** resultados.
2. Query tem **>= 4** caracteres normalizados.

```python
if len(prefix_hits) < 3 and len(q_norm) >= 4:
    {'nome_busca': {'$regex': q_normalized}}  # contains, sem ^
```

> ❌ **NUNCA** faça contains livre (`/silva/` para qualquer query). Vira full-scan rapidamente em bases grandes.

### Normalização

A query e o campo `nome_busca` precisam usar a **mesma** normalização. Usar:

```python
from text_utils import normalize_for_search
q_norm = normalize_for_search(q)
```

Características: lowercase, sem acentos, sem espaços duplos, trim.

---

## 4. Indexação obrigatória

```python
# /app/backend/scripts/normalize_names_back.py
db.students.create_index(
    [("mantenedora_id", 1), ("nome_busca", 1)],
    name="ix_tenant_nome_busca"
)
```

> ⚠️ Toda coleção que vai receber autocomplete precisa do índice composto **(tenant_id, nome_busca)**.

---

## 5. Segurança e LGPD

| Item | Regra |
|---|---|
| **Autenticação** | obrigatória — `AuthMiddleware.get_current_user` |
| **Tenant scope** | obrigatório — `apply_tenant_filter(filter_query, current_user, request)` |
| **CPF** | sempre **mascarado** (`***.456.***-01`) — nunca retornar CPF cru no autocomplete |
| **Rate limit** | **30 req/min/usuário** (in-memory, sliding window) |
| **Payload** | mínimo necessário para renderizar a linha — sem `created_at`, `updated_at`, dados de matrícula etc. |

---

## 6. Frontend — uso obrigatório do hook

### Hook canônico

`/app/frontend/src/hooks/useStudentSearch.js`

```jsx
import { useStudentSearch } from '@/hooks/useStudentSearch';

const { results, loading, error, usedFallback } = useStudentSearch(query, {
  tenantId: user?.mantenedora_id,
  filters: { status: 'active', school_id: schoolId },
  limit: 10,
  enabled: modalOpen, // pause quando irrelevante
});
```

### O que o hook entrega

| Recurso | Default | Justificativa |
|---|---|---|
| **Debounce** | 300ms | reduz requests em digitação rápida |
| **Mínimo de chars** | 2 | evita poluir o índice com queries inúteis |
| **AbortController** | sempre | cancela requests obsoletos quando usuário continua digitando |
| **Cache tenant-aware** | TTL 30s, key `${tenantId}:${q}:${filters}` | evita repetir mesma query rapidamente; **isolamento por tenant é obrigatório** |
| **Limpa ao desmontar** | sim | sem leak de fetches |

### ❌ Anti-padrões — **proibidos**

- `studentsAPI.getAll()` + `.filter()` no frontend.
- Hooks ad-hoc por página (use o hook canônico).
- Cache de query **sem** `tenantId` na chave (vaza dado entre tenants).
- Chamadas síncronas a cada keystroke sem debounce.

---

## 7. Observabilidade

> **Endpoint canônico**: `GET /api/admin/observability/autocomplete`
> **Acesso**: super_admin **apenas**.
> **Headers**: `Cache-Control: no-store, no-cache, must-revalidate; Pragma: no-cache; Expires: 0`.
> **Rate limit**: 5 req/min/usuário (dedicado, separado do limit geral de autocomplete).
> **Audit log**: cada acesso é gravado em `audit_logs` (action=`export`, collection=`observability_metrics`).

### Princípios

- **Sem PII**: queries são armazenadas como SHA1 truncado da versão **normalizada** (`q_hash` 8 hex). Retenção curta (15min) + sem persistência tornam reverso por brute force impraticável para uso operacional.
- **Janela deslizante 15min em buckets de 1min** (estrutura `{minute_iso: {...}}`). Cleanup automático a cada `record`.
- **p95 incremental via histogram buckets** (`[1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]ms` + overflow). Sem ordenação on-demand.
- **Instance-local**: o snapshot reflete APENAS a réplica respondedora. O payload deixa isso explícito (`mode`, `replica_aware`, `warning`).

### Estrutura do snapshot

```json
{
  "window": "15m",
  "generated_at": "2026-02-12T...",
  "mode": "instance-local",
  "replica_aware": false,
  "warning": "Métricas voláteis (in-memory)...",

  "requests_total": 1284,
  "avg_latency_ms": 18.3,
  "p95_latency_ms": 50.0,

  "empty_results_pct": 12.1,
  "fallback_contains_pct": 7.2,

  "cache_hit_pct": 74.2,
  "cache_entries": 42,
  "cache_memory_estimate_kb": 18.3,

  "rate_limited_requests": 4,

  "query_length_distribution": {"2": 120, "3": 440, "4": 280, "5": 200, "6": 100, "7+": 144},

  "top_queries": [{"q_hash": "a3f2c1b0", "count": 52}, ...],
  "top_tenants": [{"tenant_id": "...", "count": 320}, ...],

  "config": {
    "cache_ttl_seconds": 5,
    "rate_limit_per_minute": 30,
    "latency_buckets_ms": [1, 2, 5, ...],
    "window_minutes": 15
  }
}
```

### Cache server-side

Para alimentar `cache_hit_pct` e reduzir pressão no Mongo:

- **TTL deslizante de 5s** (autocomplete muda a cada keystroke; TTL maior desperdiça RAM).
- **Key**: `${tenant_id}|${q_norm}|${filters_hash}`, onde `filters_hash = SHA1(json.dumps(filters, sort_keys=True))[:8]`.
- **Eviction**: descarta expirados primeiro; se ainda lotado (>1000), drop do mais antigo.
- **Sem invalidação**: cache curto torna desnecessário invalidar em writes.

### Como interpretar as métricas

| Métrica | Bom | Investigar |
|---|---|---|
| `avg_latency_ms` | < 25ms | > 50ms → índice insuficiente |
| `p95_latency_ms` | < 100ms | > 250ms → índice ou Mongo lento |
| `fallback_contains_pct` | < 20% | > 30% → migrar para tokens (Fase 2) |
| `cache_hit_pct` | > 50% | < 30% → debounce muito agressivo? |
| `empty_results_pct` | < 15% | > 30% → frontend permite queries inúteis |
| `query_length_distribution` | maioria 3+ | maioria em "2" → debounce ruim ou min_chars baixo |
| `rate_limited_requests` | 0 | > 0 → usuário fazendo loop ou abuso |

### Roadmap (Fase 2)

Quando precisar consolidar entre réplicas:

- **Opção A**: Redis (HyperLogLog para top queries, sorted sets para latência).
- **Opção B**: Coleção Mongo capped `observability_autocomplete` (escrita assíncrona em background, queries de agregação no endpoint).
- **Disparador**: backend escalar para >1 réplica OU necessidade de alertas históricos (>15min).

---

## 8. Roadmap evolutivo (matching)

| Fase | Estado | Descrição |
|---|---|---|
| **1** | ✅ **Implementada** | Prefix-first indexado + fallback contains restrito |
| **2** | 📋 Backlog | Tokens de nome (`nome_busca_tokens: ["maria", "aparecida", "silva"]`) — busca por qualquer palavra do nome sem regex pesado |
| **3** | 🔮 Apenas se necessário | MongoDB Atlas Search ou ElasticSearch (provável overkill no estágio atual) |

### Fase 2 — Tokens (quando implementar)

```python
# Pipeline de normalização do banco
nome_busca_tokens = normalize_for_search(full_name).split()
# Index: db.students.create_index([("mantenedora_id", 1), ("nome_busca_tokens", 1)])

# Query: $all garante que TODAS as palavras digitadas estão presentes
tokens_query = {"$all": [f"^{t}" for t in q.split()]}  # com regex de prefix
```

> Disparador: quando `fallback_pct > 30%` no monitoramento.

---

## 9. Migração das telas existentes

| Tela | Estado | Prioridade |
|---|---|---|
| `AssocialDashboard` | ✅ Migrado (Fev/2026) | Caso piloto |
| `BolsaFamilia` | 📋 Pendente | Alta — mesma área operacional |
| `VaccineDashboard` | 📋 Pendente | Alta — usuários consultam aluno individual |
| `Grades` | 📋 Pendente | Média — geralmente já tem turma como filtro |
| `Enrollments` | 📋 Pendente | Média |
| `StudentsComplete` | 📋 Pendente | Média |
| `Promotion` | 📋 Pendente | Baixa — fluxo em massa |
| `AnalyticsDashboard` | 📋 Pendente | Baixa — usa agregações, talvez não precise |
| `Students` | 📋 Pendente | Baixa |
| `Guardians` | 📋 Pendente | Baixa — busca por responsáveis (precisaria endpoint próprio) |

> Cada migração deve ser **uma PR isolada**, com smoke test próprio. **Não** generalizar prematuramente — cada tela tem regras de filtro próprias (ex.: Grades sempre filtra por turma; Vacinas pode ter filtro por status de vacinação).

---

## 10. Checklist de revisão de PR

Antes de aprovar PR que adiciona/modifica busca, verifique:

- [ ] Endpoint segue convenção `/api/{entidade}/autocomplete`?
- [ ] Há índice composto `(tenant_id, nome_busca)` na coleção?
- [ ] `apply_tenant_filter` foi chamado?
- [ ] Prefix-first com fallback restrito (`>= 4` chars + `< 3` hits)?
- [ ] CPF mascarado / dados sensíveis omitidos?
- [ ] Rate limit aplicado?
- [ ] Frontend usa o hook canônico (`useStudentSearch`) ou variação aprovada?
- [ ] Cache tenant-aware?
- [ ] Debounce + AbortController?
- [ ] **Cache server-side** com TTL curto e instrumentado?
- [ ] **Telemetria** registrada via `record_autocomplete_call`?
- [ ] **Endpoint de observabilidade** retorna estrutura completa (não snapshot cru)?

---

**Mantido por**: Equipe SIGESC
**Última atualização**: Fev/2026
