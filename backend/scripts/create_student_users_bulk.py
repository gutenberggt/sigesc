"""
Gera em massa usuários de acesso (role='aluno') para alunos ativos.

Uso:
    # DRY-RUN — gera CSV em /app/backend/scripts/_out/ sem gravar nada
    python backend/scripts/create_student_users_bulk.py

    # Aplica no banco (idempotente)
    python backend/scripts/create_student_users_bulk.py --apply

    # Restringir a uma mantenedora
    python backend/scripts/create_student_users_bulk.py --mantenedora <id> --apply

    # Restringir a uma escola
    python backend/scripts/create_student_users_bulk.py --school <id> --apply

Regra:
- E-mail: {primeironome}{ultimosobrenome}{MM}@sigesc.com
- Senha:  DDMMYYYY (data de nascimento)
- Duplicatas de e-mail: sufixo -2, -3, ...
- must_change_password=True no 1º login
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from services.student_account_service import build_plan_for_students, apply_plan  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")


def _write_csv(rows: list[dict], path: Path, fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Grava no banco (padrão é dry-run).")
    parser.add_argument("--mantenedora", default=None, help="Filtrar por mantenedora_id.")
    parser.add_argument("--school", default=None, help="Filtrar por school_id.")
    parser.add_argument("--include-inactive", action="store_true",
                        help="Incluir alunos inativos (padrão: somente ativos).")
    parser.add_argument("--out-dir", default=str(BACKEND_DIR / "scripts" / "_out"))
    args = parser.parse_args()

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    plan = await build_plan_for_students(
        db,
        mantenedora_id=args.mantenedora,
        school_ids=[args.school] if args.school else None,
        include_inactive=args.include_inactive,
    )
    totals = plan["totals"]

    print("========================================")
    print("PLANO de criação de usuários de alunos")
    print("========================================")
    print(f"  Alunos avaliados            : {totals['scanned']}")
    print(f"  A criar (novos)             : {totals['to_create']}")
    print(f"  Já possuem user (skip)      : {totals['already_has_user']}")
    print(f"  Ignorados (dados faltando)  : {totals['skipped']}")
    print()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    csv_create = out_dir / f"alunos_to_create_{stamp}.csv"
    csv_skip = out_dir / f"alunos_skipped_{stamp}.csv"
    csv_already = out_dir / f"alunos_already_user_{stamp}.csv"

    if plan["to_create"]:
        _write_csv(
            plan["to_create"], csv_create,
            ["student_id", "full_name", "email", "password",
             "birth_date", "school_id", "mantenedora_id"],
        )
        print(f"  → CSV a criar   : {csv_create}")
    if plan["skipped"]:
        _write_csv(plan["skipped"], csv_skip, ["student_id", "full_name", "reason"])
        print(f"  → CSV ignorados : {csv_skip}")
    if plan["already_has_user"]:
        _write_csv(plan["already_has_user"], csv_already,
                   ["student_id", "full_name", "email", "user_id"])
        print(f"  → CSV já existe : {csv_already}")

    if not args.apply:
        print()
        print("  MODO DRY-RUN. Revise os CSVs acima e re-execute com --apply para gravar.")
        return 0

    print()
    print("  ► Gravando no banco...")
    result = await apply_plan(db, plan)
    print(f"  ✔ Inseridos: {result['inserted']}")
    if result["errors"]:
        print(f"  ✖ Erros:    {len(result['errors'])}")
        for e in result["errors"][:10]:
            print(f"     - {e}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
