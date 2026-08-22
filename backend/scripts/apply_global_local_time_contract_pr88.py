#!/usr/bin/env python3
"""Materializa o contrato temporal global do SIGESC para o PR #88.

Este script altera SOMENTE código-fonte do checkout atual. Não acessa banco.
É idempotente: pode ser executado novamente; quando o contrato já estiver
materializado, não deve produzir alterações adicionais.

Contrato:
- backend é autoridade do instante UTC;
- navegador/computador informa timezone/offset civil da requisição;
- UI, auditoria e documentos exibem/registram a representação civil nesse fuso;
- timestamps técnicos continuam UTC;
- jobs assíncronos preservam o contexto temporal da requisição.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHANGED: list[str] = []


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(f"Arquivo esperado não encontrado: {rel}")
    return path.read_text(encoding="utf-8")


def write(rel: str, source: str) -> None:
    path = ROOT / rel
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == source:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    CHANGED.append(rel)


def add_import_after(source: str, anchor: str, addition: str) -> str:
    if addition in source:
        return source
    if anchor not in source:
        raise SystemExit(f"Âncora de import não encontrada: {anchor}")
    return source.replace(anchor, anchor + "\n" + addition, 1)


def add_import_after_initial_imports(source: str, addition: str) -> str:
    if addition in source:
        return source
    lines = source.splitlines()
    indices = [i for i, line in enumerate(lines[:180]) if line.startswith(("import ", "from "))]
    if not indices:
        raise SystemExit(f"Bloco de imports não encontrado para: {addition}")
    lines.insert(max(indices) + 1, addition)
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Frontend bootstrap: transporta timezone/offset em Axios e fetch.
# ---------------------------------------------------------------------------
rel = "frontend/src/index.js"
s = read(rel)
s = add_import_after(
    s,
    'import "@/utils/contentCopyErrorNormalizer";',
    'import { installClientTimeContext } from "@/utils/clientTimeContext";',
)
if "installClientTimeContext();" not in s:
    anchor = "const root = ReactDOM.createRoot"
    if anchor not in s:
        raise SystemExit("index.js: âncora React root ausente")
    s = s.replace(anchor, "installClientTimeContext();\n\n" + anchor, 1)
write(rel, s)

# ---------------------------------------------------------------------------
# Backend middleware e CORS.
# ---------------------------------------------------------------------------
rel = "backend/server.py"
s = read(rel)
s = add_import_after(
    s,
    "from utils.connection_manager import ConnectionManager, ActiveSessionsTracker",
    "from utils.client_time import ClientTimeContextMiddleware",
)
if "app.add_middleware(ClientTimeContextMiddleware)" not in s:
    anchor = 'app = FastAPI(title="SIGESC API", version="1.0.0")'
    if anchor not in s:
        raise SystemExit("server.py: criação do FastAPI não encontrada")
    s = s.replace(anchor, anchor + "\napp.add_middleware(ClientTimeContextMiddleware)", 1)
old_headers = 'allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With", "X-Mantenedora-Id"]'
new_headers = 'allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With", "X-Mantenedora-Id", "X-SIGESC-Timezone", "X-SIGESC-UTC-Offset-Minutes", "X-SIGESC-Local-Date"]'
if old_headers in s:
    s = s.replace(old_headers, new_headers)
elif '"X-SIGESC-Timezone"' not in s:
    raise SystemExit("server.py: allow_headers CORS não reconhecido")
write(rel, s)

# ---------------------------------------------------------------------------
# Frontend: datas civis automáticas nunca podem ser extraídas de ISO UTC.
# ---------------------------------------------------------------------------
known_civil_files = [
    "frontend/src/pages/Attendance.js",
    "frontend/src/pages/Enrollments.js",
    "frontend/src/hooks/useStaff.js",
    "frontend/src/pages/DiarioAEE.js",
    "frontend/src/pages/StudentsComplete.js",
]
for rel in known_civil_files:
    s = read(rel)
    patterns = (
        "new Date().toISOString().split('T')[0]",
        'new Date().toISOString().split("T")[0]',
        "new Date().toISOString().slice(0, 10)",
        'new Date().toISOString().slice(0, 10)',
    )
    if not any(p in s for p in patterns):
        continue
    if "browserLocalTodayISO" not in s:
        s = add_import_after_initial_imports(
            s, "import { browserLocalTodayISO } from '@/utils/browserLocalDate';"
        )
    for p in patterns:
        s = s.replace(p, "browserLocalTodayISO()")
    write(rel, s)

# Objetos de Conhecimento: hoje e datas iteradas de calendário.
rel = "frontend/src/pages/LearningObjects.js"
s = read(rel)
if "browserLocalTodayISO" not in s or "browserLocalDateISO" not in s:
    s = add_import_after_initial_imports(
        s,
        "import { browserLocalDateISO, browserLocalTodayISO } from '@/utils/browserLocalDate';",
    )
s = s.replace("sabLetivos.add(d.toISOString().split('T')[0]);", "sabLetivos.add(browserLocalDateISO(d));")
s = s.replace('sabLetivos.add(d.toISOString().split("T")[0]);', "sabLetivos.add(browserLocalDateISO(d));")
s = s.replace("blocked.add(d.toISOString().split('T')[0]);", "blocked.add(browserLocalDateISO(d));")
s = s.replace('blocked.add(d.toISOString().split("T")[0]);', "blocked.add(browserLocalDateISO(d));")
s = s.replace("const isToday = dateStr === new Date().toISOString().split('T')[0];", "const isToday = dateStr === browserLocalTodayISO();")
s = s.replace('const isToday = dateStr === new Date().toISOString().split("T")[0];', "const isToday = dateStr === browserLocalTodayISO();")
write(rel, s)

# Diário operacional.
rel = "frontend/src/pages/DiaryCalendar.jsx"
s = read(rel)
if "browserLocalTodayISO" not in s:
    s = add_import_after_initial_imports(
        s, "import { browserLocalTodayISO } from '@/utils/browserLocalDate';"
    )
s = s.replace(
    "function todayISO() {\n  const d = new Date();\n  return d.toISOString().slice(0, 10);\n}",
    "function todayISO() {\n  return browserLocalTodayISO();\n}",
)
write(rel, s)

# Substituições de servidor.
rel = "frontend/src/components/staff/SubstituicaoSection.js"
s = read(rel)
if "new Date().toISOString().slice(0, 10)" in s:
    if "browserLocalTodayISO" not in s:
        s = add_import_after_initial_imports(
            s, "import { browserLocalTodayISO } from '@/utils/browserLocalDate';"
        )
    s = s.replace("new Date().toISOString().slice(0, 10)", "browserLocalTodayISO()")
write(rel, s)

# Auditoria UI: dia do filename é local; visualização prefere snapshot local.
rel = "frontend/src/pages/AuditLogs.jsx"
s = read(rel)
if "browserLocalTodayISO" not in s:
    s = add_import_after_initial_imports(
        s, "import { browserLocalTodayISO } from '@/utils/browserLocalDate';"
    )
s = s.replace("new Date().toISOString().slice(0, 10)", "browserLocalTodayISO()")
s = s.replace("formatDate(log.timestamp)", "formatDate(log.timestamp_local || log.timestamp)")
write(rel, s)

# Varredura global: converte SOMENTE padrões inequívocos de data civil YYYY-MM-DD.
DATE_ONLY_PATTERNS = [
    re.compile(r"new Date\(\)\.toISOString\(\)\.split\(['\"]T['\"]\)\[0\]"),
    re.compile(r"new Date\(\)\.toISOString\(\)\.slice\(0,\s*10\)"),
    re.compile(r"new Date\(\)\.toISOString\(\)\.substring\(0,\s*10\)"),
]
for path in (ROOT / "frontend/src").rglob("*"):
    if path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
        continue
    rel = str(path.relative_to(ROOT))
    s = path.read_text(encoding="utf-8")
    if not any(p.search(s) for p in DATE_ONLY_PATTERNS):
        continue
    if "browserLocalTodayISO" not in s:
        s = add_import_after_initial_imports(
            s, "import { browserLocalTodayISO } from '@/utils/browserLocalDate';"
        )
    for p in DATE_ONLY_PATTERNS:
        s = p.sub("browserLocalTodayISO()", s)
    write(rel, s)

# ---------------------------------------------------------------------------
# Auditoria backend: UTC canônico + snapshot civil imutável.
# ---------------------------------------------------------------------------
rel = "backend/audit_service.py"
s = read(rel)
if "from utils.client_time import current_time_context, local_day_bounds_utc, local_now" not in s:
    s = s.replace(
        "import logging\n",
        "import logging\n\nfrom utils.client_time import current_time_context, local_day_bounds_utc, local_now\n",
        1,
    )
if "time_ctx = current_time_context(now_utc)" not in s:
    anchor = "            # Monta o registro de auditoria\n            audit_record = {"
    if anchor not in s:
        raise SystemExit("audit_service.py: âncora audit_record não encontrada")
    s = s.replace(
        anchor,
        "            # UTC é o instante canônico; o snapshot local preserva a hora civil.\n"
        "            now_utc = datetime.now(timezone.utc)\n"
        "            time_ctx = current_time_context(now_utc)\n"
        "            audit_record = {",
        1,
    )
s = s.replace(
    "'academic_year': academic_year or datetime.now().year,",
    "'academic_year': academic_year or local_now(now_utc).year,",
)
s = s.replace(
    "'timestamp': datetime.now(timezone.utc).isoformat(),",
    "'timestamp': now_utc.isoformat(),\n"
    "                'timestamp_utc': time_ctx['timestamp_utc'],\n"
    "                'timestamp_local': time_ctx['timestamp_local'],\n"
    "                'timezone': time_ctx['timezone'],\n"
    "                'utc_offset_minutes': time_ctx['utc_offset_minutes'],\n"
    "                'timezone_source': time_ctx['timezone_source'],",
)
old_filter = """            # Filtro de data
            if filters.get('start_date') or filters.get('end_date'):
                query['timestamp'] = {}
                if filters.get('start_date'):
                    query['timestamp']['$gte'] = filters['start_date']
                if filters.get('end_date'):
                    query['timestamp']['$lte'] = filters['end_date'] + 'T23:59:59'
"""
new_filter = """            # Filtro por dia civil do dispositivo; converte limites para UTC.
            if filters.get('start_date') or filters.get('end_date'):
                start_utc, end_utc = local_day_bounds_utc(
                    filters.get('start_date'), filters.get('end_date')
                )
                query['timestamp'] = {}
                if start_utc:
                    query['timestamp']['$gte'] = start_utc
                if end_utc:
                    query['timestamp']['$lte'] = end_utc
"""
if old_filter in s:
    s = s.replace(old_filter, new_filter, 1)
write(rel, s)

# PDF da auditoria.
rel = "backend/routers/audit_logs.py"
s = read(rel)
if "from utils.client_time import local_now" not in s:
    s = s.replace(
        "from auth_middleware import AuthMiddleware\n",
        "from auth_middleware import AuthMiddleware\nfrom utils.client_time import local_now\n",
        1,
    )
old_fmt = """        def _fmt_dt(ts):
            try:
                d = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                return d.strftime('%d/%m/%Y %H:%M')
            except Exception:
                return str(ts or '-')
"""
new_fmt = """        def _fmt_dt(ts, *, event_local=False):
            try:
                d = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                if not event_local:
                    d = local_now(d.astimezone(timezone.utc))
                return d.strftime('%d/%m/%Y %H:%M')
            except Exception:
                return str(ts or '-')
"""
if old_fmt in s:
    s = s.replace(old_fmt, new_fmt, 1)
s = s.replace(
    "Paragraph(_fmt_dt(lg.get('timestamp')), cell),",
    "Paragraph(_fmt_dt(lg.get('timestamp_local') or lg.get('timestamp'), event_local=bool(lg.get('timestamp_local'))), cell),",
)
s = s.replace(
    "gen_at = datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M')",
    "gen_at = local_now().strftime('%d/%m/%Y %H:%M')",
)
s = s.replace(
    "filename = f\"logs_auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf\"",
    "filename = f\"logs_auditoria_{local_now().strftime('%Y%m%d_%H%M')}.pdf\"",
)
write(rel, s)

# ---------------------------------------------------------------------------
# Documentos/PDFs: emissão civil usa contexto da requisição.
# Timestamp técnico UTC explícito permanece intocado.
# ---------------------------------------------------------------------------
pdf_candidates = list((ROOT / "backend/pdf").glob("*.py"))
for extra in (ROOT / "backend/pdf_generator.py", ROOT / "backend/hr_pdf_generator.py"):
    if extra.exists():
        pdf_candidates.append(extra)

for path in pdf_candidates:
    rel = str(path.relative_to(ROOT))
    s = path.read_text(encoding="utf-8")
    before = s
    # Não substitui datetime.now(timezone.utc), que é técnico e deliberado.
    s = re.sub(r"(?<![\w.])datetime\.now\(\)", "local_now()", s)
    s = re.sub(r"(?<![\w.])date\.today\(\)", "local_today()", s)
    # Alguns geradores faziam UTC -> timezone do container via astimezone() sem tz.
    s = s.replace("datetime.now(timezone.utc).astimezone()", "local_now()")
    if s != before and "from utils.client_time import local_now, local_today" not in s:
        s = add_import_after_initial_imports(
            s, "from utils.client_time import local_now, local_today"
        )
    write(rel, s)

# ---------------------------------------------------------------------------
# Jobs assíncronos: snapshot do contexto temporal no enqueue.
# ---------------------------------------------------------------------------
job_routers = [
    "backend/routers/bulletin_pdf.py",
    "backend/routers/history_pdf.py",
    "backend/routers/diary_snapshots.py",
    "backend/routers/render_jobs.py",
]
for rel in job_routers:
    s = read(rel)
    if "document_render_jobs.insert_one" not in s:
        continue
    if "from utils.client_time import current_time_context" not in s:
        s = add_import_after_initial_imports(s, "from utils.client_time import current_time_context")
    if '"time_context": current_time_context()' not in s:
        anchor = '"audit_trail": ['
        if anchor not in s:
            raise SystemExit(f"{rel}: audit_trail do job não encontrado")
        s = s.replace(anchor, '"time_context": current_time_context(),\n            "audit_trail": [', 1)
    write(rel, s)

# Worker restaura contexto ao executar o renderer, sem alterar relógio UTC da fila.
rel = "backend/services/render_worker.py"
s = read(rel)
if "from utils.client_time import use_time_context" not in s:
    s = s.replace(
        "from utils.render_jobs import (",
        "from utils.client_time import use_time_context\nfrom utils.render_jobs import (",
        1,
    )
if "with use_time_context(" not in s:
    old = "        result = await handler(job) or {}"
    if old not in s:
        raise SystemExit("render_worker.py: chamada do handler não encontrada")
    s = s.replace(
        old,
        "        time_ctx = job.get(\"time_context\") or {}\n"
        "        with use_time_context(\n"
        "            timezone_name=time_ctx.get(\"timezone\"),\n"
        "            utc_offset_minutes=time_ctx.get(\"utc_offset_minutes\"),\n"
        "            source=\"render_job\",\n"
        "        ):\n"
        "            result = await handler(job) or {}",
        1,
    )
write(rel, s)

# ---------------------------------------------------------------------------
# Registros verificáveis: UTC permanece e a representação civil é preservada.
# ---------------------------------------------------------------------------
for rel in ("backend/services/bulletin_renderer.py", "backend/services/history_renderer.py"):
    s = read(rel)
    if "from utils.client_time import current_time_context" not in s:
        s = add_import_after_initial_imports(s, "from utils.client_time import current_time_context")
    if "time_ctx = current_time_context()" not in s:
        candidates = [
            "    now = datetime.now(timezone.utc).isoformat()",
            "    now = datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%SZ\")",
        ]
        for anchor in candidates:
            if anchor in s:
                s = s.replace(anchor, anchor + "\n    time_ctx = current_time_context()", 1)
                break
        else:
            raise SystemExit(f"{rel}: âncora de now UTC não encontrada")
    if '"created_at_local": time_ctx["timestamp_local"]' not in s:
        anchor = '"created_at": now,'
        if anchor not in s:
            raise SystemExit(f"{rel}: created_at não encontrado")
        s = s.replace(
            anchor,
            anchor
            + '\n        "created_at_local": time_ctx["timestamp_local"],'
            + '\n        "timezone": time_ctx["timezone"],'
            + '\n        "utc_offset_minutes": time_ctx["utc_offset_minutes"],',
            1,
        )
    write(rel, s)

for rel in ("backend/routers/bulletin_pdf.py", "backend/routers/history_pdf.py"):
    s = read(rel)
    if '"issued_at_local": v.get("created_at_local")' not in s:
        anchor = '"issued_at": v.get("created_at"),'
        if anchor not in s:
            raise SystemExit(f"{rel}: issued_at público não encontrado")
        s = s.replace(
            anchor,
            anchor
            + '\n            "issued_at_local": v.get("created_at_local"),'
            + '\n            "timezone": v.get("timezone"),'
            + '\n            "utc_offset_minutes": v.get("utc_offset_minutes"),',
            1,
        )
    write(rel, s)

print("Contrato temporal global aplicado.")
if CHANGED:
    print("Arquivos alterados:")
    for rel in CHANGED:
        print(f" - {rel}")
else:
    print("Nenhuma alteração necessária; checkout já estava materializado.")
