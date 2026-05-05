"""
Normalização Reversa de Nomes — SIGESC (Mai/2026)
==================================================

Reverte o efeito do antigo migrate_uppercase.py com **segurança operacional
de produção**: dual-gate (apply + confirm), backup automático timestampado,
rollback nativo, log de auditoria, progress bar, escopo por coleção e
batch-size controlável.

POLÍTICAS NÃO-NEGOCIÁVEIS (acordadas com o proprietário):
  - Apenas CAMPOS NOMINAIS (whitelist por coleção). NUNCA toca em descrições,
    observações, conteúdos, planos.
  - AEE NÃO é migrado em massa (módulo bloqueado).
  - Registros que JÁ estão em capitalização razoável passam BATIDO
    (`is_likely_uppercase`).
  - Siglas conhecidas (AEE, BNCC, EJA, SEMED, …) permanecem UPPER quando
    estavam UPPER no original.
  - Cada coleção usa o campo primário próprio: students→full_name,
    staff→nome, schools→name, classes→name, courses→name, mantenedoras→nome.

Exemplos de uso:

    # 1) Análise sem alterar nada
    python scripts/normalize_names_back.py --dry-run

    # 2) Análise restrita a coleções específicas
    python scripts/normalize_names_back.py --dry-run --collections students,staff

    # 3) Aplicar em produção (DUAL-GATE: --apply + --confirm)
    python scripts/normalize_names_back.py --apply --confirm \\
        --collections students --log-file /var/log/sigesc/migracao.log

    # 4) Rollback completo a partir de um backup
    python scripts/normalize_names_back.py --rollback \\
        backup_students_20260505T030000Z --collections students
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

load_dotenv()

logger = logging.getLogger("normalize_names")

# ============================================================
# CONFIG: campos nominais por coleção (POLÍTICA RESTRITIVA)
# ============================================================
NAME_FIELDS_BY_COLLECTION: Dict[str, List[str]] = {
    "students": ["full_name", "father_name", "mother_name", "guardian_name"],
    "staff": ["nome", "marital_status_spouse_name"],
    "schools": ["name", "principal_name", "secretary_name", "coordinator_name"],
    "classes": ["name"],
    "courses": ["name"],
    "users": ["full_name"],
    "mantenedoras": ["nome"],
}

# Campo primário por coleção — base de `nome_normalizado` e `nome_busca`.
PRIMARY_NAME_FIELD: Dict[str, Optional[str]] = {
    "students": "full_name",
    "staff": "nome",
    "schools": "name",
    "classes": "name",
    "courses": "name",
    "users": "full_name",
    "mantenedoras": "nome",
}

LOWER_PARTICLES = {"da", "de", "di", "do", "du", "das", "dos", "e", "em", "y"}

KNOWN_ACRONYMS = {
    "AEE", "EJA", "BNCC", "ENEM", "INEP", "MEC", "PNE", "PNAE", "PCD",
    "TGD", "TEA", "TDAH", "EMEIEF", "EMEF", "EMEI", "EJEM",
    "FUNDEB", "FUNDEF", "ABNT", "OAB", "USP", "UFPA", "ETI",
    "PMPI", "PME", "SEMED", "SEDUC",
    "QA", "II", "III", "IV", "VI", "VII", "VIII", "IX",
    "CNPJ", "CPF", "RG", "NIS", "PIS", "SUS", "CEP",
}

DEFAULT_BATCH_SIZE = 1000
DEFAULT_DRY_RUN_EXAMPLES = 10


# ============================================================
# HELPERS DE NORMALIZAÇÃO
# ============================================================
def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def title_case_name(raw: str) -> str:
    """Capitaliza um nome próprio com regras BR (preposições, siglas, hífen, apóstrofo)."""
    if not raw or not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s:
        return s

    def cap_token(token_orig: str, is_first: bool) -> str:
        if not token_orig:
            return token_orig
        if "-" in token_orig:
            return "-".join(
                cap_token(p, is_first and i == 0)
                for i, p in enumerate(token_orig.split("-"))
            )
        if "'" in token_orig:
            return "'".join(
                cap_token(p, is_first and i == 0)
                for i, p in enumerate(token_orig.split("'"))
            )
        token_upper = token_orig.upper()
        if token_upper in KNOWN_ACRONYMS and token_orig.isupper():
            return token_upper
        word_lower = token_orig.lower()
        if not is_first and word_lower in LOWER_PARTICLES:
            return word_lower
        return word_lower[:1].upper() + word_lower[1:]

    tokens = [w for w in re.split(r"\s+", s) if w]
    return " ".join(cap_token(w, i == 0) for i, w in enumerate(tokens))


def normalize_search(text: str) -> str:
    if not text:
        return text
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


def normalize_lower(text: str) -> str:
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip().lower()


def is_likely_uppercase(value: str) -> bool:
    """Retorna True se a string parece estar em CAIXA ALTA forçada."""
    if not value or not isinstance(value, str):
        return False
    letters = [c for c in strip_accents(value) if c.isalpha()]
    if len(letters) < 2:
        return False
    return all(c.isupper() for c in letters)


# ============================================================
# BACKUP & ROLLBACK
# ============================================================
async def backup_collection(db, col_name: str, timestamp: str) -> str:
    backup_name = f"backup_{col_name}_{timestamp}"
    pipeline = [{"$match": {}}, {"$out": backup_name}]
    await db[col_name].aggregate(pipeline, allowDiskUse=True).to_list(length=None)
    count = await db[backup_name].count_documents({})
    logger.info("Backup criado: %s (%d docs)", backup_name, count)
    return backup_name


async def rollback_collection(db, backup_name: str, target_name: str) -> int:
    """Restaura `target_name` a partir de `backup_name`. Retorna nº docs restaurados."""
    if not await _collection_exists(db, backup_name):
        raise ValueError(f"Backup '{backup_name}' não existe.")
    pipeline = [{"$match": {}}, {"$out": target_name}]
    await db[backup_name].aggregate(pipeline, allowDiskUse=True).to_list(length=None)
    count = await db[target_name].count_documents({})
    logger.warning("Rollback aplicado: %s ← %s (%d docs)", target_name, backup_name, count)
    return count


async def _collection_exists(db, name: str) -> bool:
    cols = await db.list_collection_names(filter={"name": name})
    return name in cols


# ============================================================
# DRY-RUN
# ============================================================
async def dry_run_collection(
    db, col_name: str, fields: List[str], primary_field: Optional[str], limit_examples: int
) -> Dict[str, Any]:
    col = db[col_name]
    total = await col.count_documents({})
    if total == 0:
        return {"colecao": col_name, "total": 0, "alterados": 0, "pct": 0.0, "exemplos": []}

    projection = {"_id": 1, **{f: 1 for f in fields}}
    if primary_field and primary_field not in projection:
        projection[primary_field] = 1

    cursor = col.find({}, projection)
    scanned = 0
    alterados = 0
    exemplos: List[Dict[str, str]] = []

    async for doc in cursor:
        scanned += 1
        changed = False
        sample_old = sample_new = None
        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            if not is_likely_uppercase(v):
                continue
            new_v = title_case_name(v)
            if new_v != v:
                changed = True
                if sample_old is None:
                    sample_old = v
                    sample_new = new_v
        if changed:
            alterados += 1
            if len(exemplos) < limit_examples and sample_old:
                exemplos.append({
                    "campo": fields[0] if primary_field is None else primary_field,
                    "original": sample_old,
                    "novo": sample_new,
                })

    pct = round((alterados / scanned * 100), 2) if scanned else 0.0
    return {
        "colecao": col_name,
        "total": scanned,
        "alterados": alterados,
        "pct": pct,
        "exemplos": exemplos,
    }


# ============================================================
# APPLY
# ============================================================
async def apply_collection(
    db, col_name: str, fields: List[str], primary_field: Optional[str],
    batch_size: int, show_progress: bool,
) -> Dict[str, Any]:
    col = db[col_name]
    total = await col.count_documents({})
    if total == 0:
        return {"colecao": col_name, "total": 0, "alterados": 0, "pct": 0.0}

    projection = {"_id": 1, **{f: 1 for f in fields}}
    if primary_field and primary_field not in projection:
        projection[primary_field] = 1
    projection["nome_normalizado"] = 1
    projection["nome_busca"] = 1

    cursor = col.find({}, projection)
    bulk_ops: List[UpdateOne] = []
    alterados = 0
    scanned = 0

    pbar = None
    if show_progress and HAS_TQDM:
        pbar = tqdm(total=total, desc=f"  {col_name:<14}", unit="doc", ncols=80)

    async for doc in cursor:
        scanned += 1
        new_set: Dict[str, Any] = {}
        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            if not is_likely_uppercase(v):
                continue
            new_v = title_case_name(v)
            if new_v != v:
                new_set[f] = new_v

        if primary_field:
            current_primary = new_set.get(primary_field, doc.get(primary_field))
            if isinstance(current_primary, str) and current_primary.strip():
                new_norm = normalize_lower(current_primary)
                new_busca = normalize_search(current_primary)
                if doc.get("nome_normalizado") != new_norm:
                    new_set["nome_normalizado"] = new_norm
                if doc.get("nome_busca") != new_busca:
                    new_set["nome_busca"] = new_busca

        if new_set:
            new_set["nome_migrado"] = True
            new_set["nome_migrado_em"] = datetime.now(timezone.utc).isoformat()
            alterados += 1
            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": new_set}))
            if len(bulk_ops) >= batch_size:
                await col.bulk_write(bulk_ops, ordered=False)
                bulk_ops.clear()

        if pbar:
            pbar.update(1)

    if bulk_ops:
        await col.bulk_write(bulk_ops, ordered=False)
        bulk_ops.clear()

    if pbar:
        pbar.close()

    pct = round((alterados / scanned * 100), 2) if scanned else 0.0
    return {"colecao": col_name, "total": scanned, "alterados": alterados, "pct": pct}


async def ensure_index(db, col_name: str) -> None:
    col = db[col_name]
    try:
        await col.create_index(
            [("mantenedora_id", 1), ("nome_busca", 1)],
            name="ix_tenant_nome_busca", background=True,
        )
        logger.info("Índice ix_tenant_nome_busca em %s", col_name)
    except Exception:
        try:
            await col.create_index(
                [("nome_busca", 1)], name="ix_nome_busca", background=True,
            )
            logger.info("Índice ix_nome_busca em %s (sem tenant)", col_name)
        except Exception as e:
            logger.warning("Falha ao criar índice em %s: %s", col_name, e)


# ============================================================
# CLI
# ============================================================
def setup_logging(log_file: Optional[str], verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)


def print_dry_run_report(rows: List[Dict[str, Any]]) -> None:
    print()
    print("=" * 78)
    print(f"{'COLEÇÃO':<16} {'TOTAL':>10} {'ALTERAR':>10} {'%':>8}   {'EXEMPLO':<30}")
    print("-" * 78)
    grand_total = grand_alter = 0
    for r in rows:
        ex = ""
        if r["exemplos"]:
            e = r["exemplos"][0]
            old = (e["original"] or "")[:18]
            new = (e["novo"] or "")[:18]
            ex = f"{old} → {new}"
        print(f"{r['colecao']:<16} {r['total']:>10} {r['alterados']:>10} {r['pct']:>7}%   {ex:<30}")
        grand_total += r["total"]
        grand_alter += r["alterados"]
    print("-" * 78)
    pct_g = round((grand_alter / grand_total * 100), 2) if grand_total else 0.0
    print(f"{'TOTAL':<16} {grand_total:>10} {grand_alter:>10} {pct_g:>7}%")
    print("=" * 78)


async def cmd_dry_run(db, cols: List[str], examples: int) -> int:
    rows = []
    for col in cols:
        if col not in NAME_FIELDS_BY_COLLECTION:
            logger.warning("Coleção fora da whitelist (ignorada): %s", col)
            continue
        r = await dry_run_collection(
            db, col, NAME_FIELDS_BY_COLLECTION[col], PRIMARY_NAME_FIELD.get(col), examples,
        )
        rows.append(r)
        logger.info("dry-run: %s", json.dumps(r, ensure_ascii=False))
    print_dry_run_report(rows)
    print()
    print("ℹ️  Nenhum dado foi alterado. Para aplicar:")
    print("   python scripts/normalize_names_back.py --apply --confirm \\")
    print(f"        --collections {','.join(cols)}")
    return 0


async def cmd_apply(
    db, cols: List[str], batch_size: int, skip_backup: bool, show_progress: bool,
) -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backups: Dict[str, str] = {}

    if not skip_backup:
        logger.info("=== BACKUP (timestamp %s) ===", timestamp)
        for col in cols:
            if col not in NAME_FIELDS_BY_COLLECTION:
                continue
            try:
                backups[col] = await backup_collection(db, col, timestamp)
            except Exception as e:
                logger.error("Backup de %s falhou: %s — abortando.", col, e)
                return 3
    else:
        logger.warning("--skip-backup ativo: NENHUM backup será criado.")

    logger.info("=== ÍNDICES ===")
    for col in cols:
        if col in PRIMARY_NAME_FIELD and PRIMARY_NAME_FIELD[col]:
            await ensure_index(db, col)

    logger.info("=== MIGRAÇÃO (batch_size=%d) ===", batch_size)
    summary = []
    for col in cols:
        if col not in NAME_FIELDS_BY_COLLECTION:
            continue
        s = await apply_collection(
            db, col, NAME_FIELDS_BY_COLLECTION[col], PRIMARY_NAME_FIELD.get(col),
            batch_size, show_progress,
        )
        summary.append(s)
        logger.info("apply: %s", json.dumps(s, ensure_ascii=False))

    print()
    print("=" * 78)
    print("✅ MIGRAÇÃO CONCLUÍDA")
    print("=" * 78)
    grand = sum(r["alterados"] for r in summary)
    print(f"  Total de docs atualizados: {grand}")
    if backups:
        print()
        print("  📦 Backups disponíveis (use --rollback para reverter):")
        for col, name in backups.items():
            print(f"     {col:<14} → {name}")
    print()
    return 0


async def cmd_rollback(db, cols: List[str], backup_arg: str) -> int:
    """Aceita formato curto (apenas timestamp 20260505T030000Z) ou nome
    completo (backup_students_20260505T030000Z)."""
    is_full_name = backup_arg.startswith("backup_")
    for col in cols:
        if col not in NAME_FIELDS_BY_COLLECTION:
            logger.warning("Coleção fora da whitelist (ignorada): %s", col)
            continue
        backup_name = backup_arg if is_full_name else f"backup_{col}_{backup_arg}"
        if not await _collection_exists(db, backup_name):
            logger.error("Backup '%s' não encontrado.", backup_name)
            return 4
        await rollback_collection(db, backup_name, col)
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Normalização reversa de nomes (CAPS → capitalização correta) com segurança operacional.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grp = p.add_mutually_exclusive_group(required=False)
    grp.add_argument("--dry-run", action="store_true",
                     help="(default) Análise sem alterar dados.")
    grp.add_argument("--apply", action="store_true",
                     help="Aplica a migração (exige --confirm).")
    grp.add_argument("--rollback", metavar="BACKUP",
                     help="Restaura coleções a partir de um backup. "
                          "Aceita timestamp (20260505T030000Z) ou nome completo.")

    p.add_argument("--confirm", action="store_true",
                   help="Confirmação explícita (obrigatório com --apply).")
    p.add_argument("--collections", default=",".join(NAME_FIELDS_BY_COLLECTION.keys()),
                   help="Lista CSV de coleções (whitelist). Default: todas.")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                   help=f"Tamanho do bulkWrite (default: {DEFAULT_BATCH_SIZE}).")
    p.add_argument("--examples", type=int, default=DEFAULT_DRY_RUN_EXAMPLES,
                   help=f"Quantos exemplos mostrar no dry-run (default: {DEFAULT_DRY_RUN_EXAMPLES}).")
    p.add_argument("--log-file", help="Caminho de arquivo de log para auditoria.")
    p.add_argument("--skip-backup", action="store_true",
                   help="(NÃO recomendado) Pula o backup automático.")
    p.add_argument("--no-progress", action="store_true",
                   help="Desativa progress bar (útil para CI/cron).")
    p.add_argument("--verbose", action="store_true", help="Log nível DEBUG.")
    return p.parse_args()


async def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_file, args.verbose)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        logger.error("MONGO_URL/DB_NAME não definidos no ambiente.")
        return 2

    cols = [c.strip() for c in args.collections.split(",") if c.strip()]

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    show_progress = not args.no_progress and HAS_TQDM and sys.stdout.isatty()

    logger.info("DB=%s · coleções=%s", db_name, cols)

    try:
        if args.rollback:
            print()
            print("⚠️  ROLLBACK — vai SOBRESCREVER coleções com o conteúdo do backup.")
            if not args.confirm:
                logger.error("ABORTADO: rollback requer --confirm.")
                return 1
            return await cmd_rollback(db, cols, args.rollback)

        if args.apply:
            if not args.confirm:
                logger.error("ABORTADO: --apply exige --confirm explícito.")
                print()
                print("Para confirmar, repita o comando incluindo --confirm:")
                print(f"   python {sys.argv[0]} --apply --confirm "
                      f"--collections {','.join(cols)}")
                return 1
            return await cmd_apply(
                db, cols, args.batch_size, args.skip_backup, show_progress,
            )

        # default: dry-run
        return await cmd_dry_run(db, cols, args.examples)
    finally:
        client.close()


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
