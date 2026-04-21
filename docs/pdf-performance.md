# 🚀 PDF Performance Guidelines — LEIA ANTES DE MEXER EM CÓDIGO DE PDF

> **Atualizado: 2026-02.** Este documento descreve os padrões de performance
> da geração de PDFs no SIGESC. **Toda alteração em geradores de PDF ou
> routers que servem PDF deve seguir estes princípios.**

## 📏 Metas de Latência (via curl, pod local)

| Documento                 | Frio (1ª) | Quente (2ª+) |
|---------------------------|-----------|--------------|
| Boletim individual        | < 1.5s    | < 1.0s       |
| Livro de Promoção         | < 2.5s    | < 1.8s       |
| Objetos de Conhecimento   | < 1.5s    | < 1.0s       |
| Histórico Escolar         | < 2.0s    | < 1.5s       |
| Relatório de Frequência   | < 1.5s    | < 1.0s       |

Se um endpoint ultrapassar consistentemente esses limites, **investigar antes
de aceitar novo código** (profile com `asyncio` tracing ou `py-spy`).

## ❌ Anti-padrões que matam performance

### 1. N+1 queries em loops
```python
# RUIM — 1 query por item
for r in records:
    course = await db.courses.find_one({"id": r["course_id"]})
    r["course_name"] = course["name"]
```

```python
# BOM — 1 query batch
ids = list({r["course_id"] for r in records if r.get("course_id")})
courses = await db.courses.find({"id": {"$in": ids}}, {"_id":0,"id":1,"name":1}).to_list(None)
names = {c["id"]: c["name"] for c in courses}
for r in records:
    r["course_name"] = names.get(r.get("course_id"), "")
```

### 2. Queries sequenciais independentes
```python
# RUIM
turma = await db.classes.find_one(...)
school = await db.schools.find_one(...)
mant  = await db.mantenedora.find_one(...)
```
```python
# BOM
turma, school, mant = await asyncio.gather(
    db.classes.find_one(...),
    db.schools.find_one(...),
    db.mantenedora.find_one(...),
)
```

### 3. Download externo sem cache
Nunca baixe imagens (logo/brasão) sem cache em disco + memória.
Use `pdf.utils.get_logo_image()` — já faz isso. **Não reinvente.**

### 4. Recriar `getSampleStyleSheet()`/estilos por PDF
Use `pdf.utils.get_styles()` — já retorna cached singleton.

### 5. Query sem projeção
```python
# RUIM — baixa todo o documento
await db.students.find({"class_id": cid}).to_list(2000)
```
```python
# BOM
await db.students.find({"class_id": cid}, {"_id":0,"id":1,"full_name":1,"sexo":1}).to_list(2000)
```

### 6. Cache em memória sem TTL
Use `backend/pdf_cache.py` (TTL padrão 5 min). Existem helpers:
- `get_mantenedora_cached(db)`
- `get_calendario_cached(db, academic_year, school_id)`
- `get_school_cached(db, school_id)`

Se precisar invalidar explicitamente após update:
```python
from pdf_cache import pdf_cache
pdf_cache.invalidate("mantenedora:global")
```

## ✅ Checklist obrigatório para novo gerador de PDF

- [ ] Nenhum `find_one()` dentro de loop (use `$in`).
- [ ] Queries independentes rodam com `asyncio.gather`.
- [ ] Todas as queries passam projeção `{"_id": 0, ...}`.
- [ ] Dados globais (mantenedora, escola, calendário) vêm de `pdf_cache`.
- [ ] Logo/brasão via `get_logo_image` (cache embutido).
- [ ] Estilos via `get_styles()` (cache embutido).
- [ ] Se a query usa novo filtro, adicionar índice em `server.py::create_indexes()`.
- [ ] Testar via `curl` medindo cold/warm (comando abaixo).

## 🧪 Como medir

```bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"gutenberg@sigesc.com","password":"@Celta2007"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

for i in 1 2 3; do
  printf "call %d: " $i
  { time curl -s -o /dev/null \
      "$API_URL/api/documents/promotion/<CLASS_ID>?academic_year=2026" \
      -H "Authorization: Bearer $TOKEN"; } 2>&1 | grep real
done
```

Esperado: call 1 (cold) > call 2-3 (warm). Se call 2+ não melhorar, o cache
não está sendo usado — investigar.

## 🗂️ Índices já existentes (não remover)

Ver `/app/backend/server.py::create_indexes()` (bloco marcado
"ÍNDICES ADICIONAIS PARA PERFORMANCE DE PDFs"). Cobrem:
- `learning_objects(class_id, academic_year, date)`
- `learning_objects(class_id, course_id, academic_year)`
- `enrollments(class_id, status, academic_year)`
- `calendar_events(academic_year)`
- `calendario_letivo(ano_letivo, school_id)`

## ⚠️ Se precisar gerar PDF muito pesado (> 100 páginas)

ReportLab é CPU-bound. Para relatórios em massa (ex.: boletim de todos os
alunos de uma escola), preferir:

1. **Async worker + status polling** — retornar `202 Accepted` com job_id;
   frontend faz polling até ficar pronto.
2. **Streaming em chunks** — gerar página a página e fazer `response.write`
   em vez de acumular em `BytesIO` completo.

Evite bloquear o event loop por mais de 2 segundos.

## 🚀 Padrão Async Job (já implementado)

Existe em `backend/pdf_jobs.py` um registry de jobs em memória + endpoints:

- `POST /api/documents/jobs/promotion/{class_id}?academic_year=Y` → inicia, devolve `{job_id}`.
- `GET /api/documents/jobs/{job_id}/status` → `{status, progress, message, filename, error}`.
- `GET /api/documents/jobs/{job_id}/download` → baixa o PDF pronto.

Frontend (ex.: `Promotion.jsx::handleDownloadPDF`) faz polling a cada 500ms
e exibe um modal com barra de progresso + mensagem de estágio:
`Iniciando...` → `Carregando turma e escola...` → `Consolidando matrículas...`
→ `Carregando notas...` → `Calculando médias...` → `Renderizando PDF...` → `Concluído`.

**Para aplicar o mesmo padrão em outros PDFs pesados:**
1. Extrair a lógica do endpoint GET em uma função `async _build_xxx_pdf(..., progress_cb=None) → (bytes, filename)`.
2. Instrumentar `progress_cb(pct, msg)` em milestones (buscar dados / agregar / render).
3. Criar endpoint `POST /documents/jobs/xxx/...` espelhando o shape do Livro de Promoção.
4. O front usa o mesmo fluxo (dispatch → poll → download).

Jobs expiram 10 min após conclusão — limpeza automática.

