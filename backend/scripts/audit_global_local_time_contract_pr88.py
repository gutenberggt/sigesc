#!/usr/bin/env python3
"""Auditoria READ-ONLY do contrato temporal global do SIGESC (PR #88).

Contrato protegido:
- UTC permanece o instante canônico técnico do backend;
- data/hora civil segue o fuso do computador/navegador que originou a ação;
- o navegador informa apenas timezone/offset, nunca o instante autoritativo;
- auditoria preserva simultaneamente UTC + snapshot civil local;
- documentos síncronos e assíncronos usam o contexto temporal da requisição;
- datas civis de UI nunca são derivadas por conversão para UTC.

Não altera arquivos nem banco. Exit code 1 significa contrato incompleto.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAILURES: list[str] = []
NOTES: list[str] = []


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        FAILURES.append(f"arquivo obrigatório ausente: {rel}")
        return ""
    return path.read_text(encoding="utf-8")


def require(rel: str, needle: str, label: str | None = None) -> None:
    source = text(rel)
    if needle not in source:
        FAILURES.append(f"{rel}: ausente {label or needle!r}")


def forbid(rel: str, pattern: str, label: str | None = None) -> None:
    source = text(rel)
    if re.search(pattern, source):
        FAILURES.append(f"{rel}: padrão proibido {label or pattern!r}")


# ---------------------------------------------------------------------------
# 1. Bootstrap do navegador e transporte do contexto temporal
# ---------------------------------------------------------------------------
require(
    "frontend/src/index.js",
    'import { installClientTimeContext } from "@/utils/clientTimeContext";',
    "import do contexto temporal global",
)
require("frontend/src/index.js", "installClientTimeContext();", "instalação global do contexto temporal")

client_helper = "frontend/src/utils/clientTimeContext.js"
for needle in (
    "Intl.DateTimeFormat().resolvedOptions().timeZone",
    "getTimezoneOffset()",
    "axios.interceptors.request.use",
    "window.fetch =",
    "X-SIGESC-Timezone",
    "X-SIGESC-UTC-Offset-Minutes",
):
    require(client_helper, needle)

# ---------------------------------------------------------------------------
# 2. Middleware/CORS backend
# ---------------------------------------------------------------------------
server = "backend/server.py"
for needle in (
    "from utils.client_time import ClientTimeContextMiddleware",
    "app.add_middleware(ClientTimeContextMiddleware)",
    '"X-SIGESC-Timezone"',
    '"X-SIGESC-UTC-Offset-Minutes"',
    '"X-SIGESC-Local-Date"',
):
    require(server, needle)

# ---------------------------------------------------------------------------
# 3. Auditoria: UTC canônico + snapshot civil + filtro de dia civil
# ---------------------------------------------------------------------------
audit = "backend/audit_service.py"
for needle in (
    "current_time_context",
    "local_day_bounds_utc",
    "'timestamp': now_utc.isoformat()",
    "'timestamp_utc': time_ctx['timestamp_utc']",
    "'timestamp_local': time_ctx['timestamp_local']",
    "'timezone': time_ctx['timezone']",
    "'utc_offset_minutes': time_ctx['utc_offset_minutes']",
):
    require(audit, needle)
forbid(
    audit,
    r"query\['timestamp'\]\['\$lte'\]\s*=\s*filters\['end_date'\]\s*\+\s*['\"]T23:59:59",
    "filtro de auditoria ingênuo por dia UTC",
)

# ---------------------------------------------------------------------------
# 4. Data civil no frontend: proíbe extrair YYYY-MM-DD de um ISO UTC
# ---------------------------------------------------------------------------
DATE_FROM_UTC = re.compile(
    r"toISOString\(\)\s*\.\s*(?:split\(\s*['\"]T['\"]\s*\)\s*\[\s*0\s*\]|slice\(\s*0\s*,\s*10\s*\)|substring\(\s*0\s*,\s*10\s*\))"
)

frontend_hits: list[str] = []
for path in (ROOT / "frontend/src").rglob("*"):
    if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
        continue
    source = path.read_text(encoding="utf-8")
    for match in DATE_FROM_UTC.finditer(source):
        line = source.count("\n", 0, match.start()) + 1
        frontend_hits.append(f"{path.relative_to(ROOT)}:{line}")
if frontend_hits:
    FAILURES.append(
        "datas civis ainda derivadas de toISOString UTC: " + ", ".join(frontend_hits[:30])
    )

# Pontos críticos que já causaram incidente e devem usar helper local explicitamente.
for rel in (
    "frontend/src/pages/Attendance.js",
    "frontend/src/pages/LearningObjects.js",
    "frontend/src/pages/Enrollments.js",
    "frontend/src/pages/DiarioAEE.js",
    "frontend/src/pages/StudentsComplete.js",
    "frontend/src/pages/DiaryCalendar.jsx",
    "frontend/src/components/staff/SubstituicaoSection.js",
):
    source = text(rel)
    if "browserLocalTodayISO" not in source and "browserLocalDateISO" not in source:
        FAILURES.append(f"{rel}: sem helper explícito de data civil local")

# ---------------------------------------------------------------------------
# 5. Camada documental: sem relógio ingênuo do container para emissão civil
# ---------------------------------------------------------------------------
document_files = list((ROOT / "backend/pdf").glob("*.py"))
for extra in (ROOT / "backend/pdf_generator.py", ROOT / "backend/hr_pdf_generator.py"):
    if extra.exists():
        document_files.append(extra)

naive_doc_hits: list[str] = []
for path in document_files:
    source = path.read_text(encoding="utf-8")
    for pattern, label in (
        (re.compile(r"(?<![\w.])datetime\.now\(\)"), "datetime.now()"),
        (re.compile(r"(?<![\w.])date\.today\(\)"), "date.today()"),
    ):
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            naive_doc_hits.append(f"{path.relative_to(ROOT)}:{line} [{label}]")
if naive_doc_hits:
    FAILURES.append(
        "geradores documentais ainda dependem do fuso do container: "
        + ", ".join(naive_doc_hits[:40])
    )

# PDF de auditoria deve respeitar snapshot local do evento e contexto local da geração.
audit_pdf = "backend/routers/audit_logs.py"
for needle in (
    "timestamp_local",
    "local_now()",
):
    require(audit_pdf, needle)

# ---------------------------------------------------------------------------
# 6. Jobs assíncronos: snapshot no enqueue e restauração no worker
# ---------------------------------------------------------------------------
worker = "backend/services/render_worker.py"
for needle in (
    "from utils.client_time import use_time_context",
    "with use_time_context(",
    "job.get(\"time_context\")",
):
    require(worker, needle)

for rel in (
    "backend/routers/bulletin_pdf.py",
    "backend/routers/history_pdf.py",
    "backend/routers/diary_snapshots.py",
    "backend/routers/render_jobs.py",
):
    source = text(rel)
    if "document_render_jobs.insert_one" in source:
        if "current_time_context" not in source or '"time_context": current_time_context()' not in source:
            FAILURES.append(f"{rel}: job assíncrono sem snapshot de timezone da requisição")

# Verificações públicas preservam UTC e também carimbo civil emitido.
for rel in ("backend/services/bulletin_renderer.py", "backend/services/history_renderer.py"):
    for needle in ("created_at_local", "timezone"):
        require(rel, needle)
for rel in ("backend/routers/bulletin_pdf.py", "backend/routers/history_pdf.py"):
    for needle in ("issued_at_local", "timezone"):
        require(rel, needle)

# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
print("=== AUDITORIA DO CONTRATO TEMPORAL GLOBAL — PR #88 ===")
if NOTES:
    for note in NOTES:
        print(f"NOTE: {note}")
if FAILURES:
    for failure in FAILURES:
        print(f"FAIL: {failure}")
    print(f"\nRESULTADO: INCOMPLETO ({len(FAILURES)} falha(s))")
    sys.exit(1)

print("RESULTADO: PASS — contrato temporal global materializado nos pontos auditados.")
