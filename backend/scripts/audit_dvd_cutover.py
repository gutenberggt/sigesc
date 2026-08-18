"""Auditoria READ-ONLY do cutover do Diário por Vínculo Docente (DVD).

Mede o quanto do fluxo de professor ainda depende do legado e quanto já está
coberto pelo DVD. Nenhum dado é migrado, corrigido, inferido ou reatribuído.

Uso no backend de produção:
    cd /app/backend
    python scripts/audit_dvd_cutover.py \
      --academic-year 2026 \
      --reference-date 2026-08-18 \
      --json /tmp/dvd-cutover-audit-2026.json

`--json` grava somente um arquivo local de relatório; não altera o MongoDB.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.dvd_cutover_audit import collect_dvd_cutover_audit  # noqa: E402


def _db_client():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


def print_report(report, details_limit: int = 50) -> None:
    meta = report["meta"]
    bindings = report["bindings"]
    classes_cutover = report["classes_cutover"]
    attendance = report["attendance"]
    content = report["content"]

    print("=" * 88)
    print("AUDITORIA READ-ONLY — CUTOVER DVD: FREQUÊNCIA + CONTEÚDOS")
    print("=" * 88)
    print(
        f"ano={meta['academic_year']} | referência={meta['reference_date']} | "
        f"tenant={meta.get('tenant_id') or 'TODOS'} | db={os.environ.get('DB_NAME', '-')}"
    )
    print()
    print("VÍNCULOS")
    print(json.dumps(bindings, ensure_ascii=False, indent=2, default=str))
    print()
    print("TURMAS — ESTADO DO CUTOVER")
    print(json.dumps(classes_cutover["classification"], ensure_ascii=False, indent=2))
    print()
    print("FREQUÊNCIA")
    print(json.dumps(attendance, ensure_ascii=False, indent=2))
    print()
    print("CONTEÚDOS")
    print(json.dumps(content, ensure_ascii=False, indent=2))

    attention = [
        row
        for row in report["legacy_binding_details"]
        if row.get("classification") != "dvd_active_exact"
    ]
    print()
    print(f"VÍNCULOS QUE EXIGEM AÇÃO — exibindo até {details_limit} de {len(attention)}")
    print("-" * 88)
    for row in attention[: max(0, details_limit)]:
        print(
            f"{row['classification']:<30} | {row['school_name'][:24]:<24} | "
            f"{row['class_name'][:18]:<18} | {row['teacher_name'][:24]:<24} | "
            f"course={str(row.get('course_id') or '-')[:12]}"
        )


async def _main(args) -> int:
    try:
        date.fromisoformat(args.reference_date)
    except ValueError as exc:
        raise SystemExit("--reference-date deve usar YYYY-MM-DD") from exc

    client, db = _db_client()
    try:
        report = await collect_dvd_cutover_audit(
            db,
            academic_year=args.academic_year,
            reference_date=args.reference_date,
            tenant_id=args.tenant_id,
        )
        report["meta"]["database_name"] = os.environ.get("DB_NAME")
        print_report(report, details_limit=args.details_limit)
        if args.json:
            out_path = Path(args.json)
            out_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"\nJSON local salvo em: {out_path}")
        return 0
    finally:
        client.close()


def _parse_args():
    parser = argparse.ArgumentParser(description="Auditoria read-only do cutover DVD")
    parser.add_argument("--academic-year", type=int, default=date.today().year)
    parser.add_argument("--reference-date", default=date.today().isoformat())
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--details-limit", type=int, default=50)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main(_parse_args())))
