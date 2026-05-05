"""
Normalização de Conteúdo Textual — SIGESC (Mai/2026)
=====================================================

Detecta campos de TEXTO (observações, descrições, pareceres) em CAIXA ALTA
e gera sugestões em SENTENCE CASE (primeira letra de cada frase maiúscula).

POLÍTICAS NÃO-NEGOCIÁVEIS:
  - NÃO grava nada no doc original — enfileira em `content_review_queue`.
  - Só campos de TEXTO LIVRE whitelistados. Nunca toca em:
      * BNCC / conteúdos programáticos / learning_objects
      * Módulo AEE (BLOQUEADO — política do proprietário)
      * Campos nominais (trate-se disso pelo script `normalize_names_back.py`)
  - Preserva: siglas (AEE, BNCC, SEMED…), aspas, números, datas, percentuais.

Fluxo:
    1) `--dry-run` (default): analisa e mostra contagem/amostras, sem tocar em nada.
    2) `--scan`: insere sugestões pendentes em `content_review_queue`.
    3) `--clear-pending`: remove itens ainda não revisados (útil após schema change).

A aprovação/rejeição das sugestões acontece via painel `/admin/content-review`
(rotas em `routers/content_review.py`), NÃO por este script.

Exemplos:
    python scripts/normalize_content.py --dry-run
    python scripts/normalize_content.py --scan --collections students,student_history
    python scripts/normalize_content.py --clear-pending
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import InsertOne

load_dotenv()
logger = logging.getLogger("normalize_content")

QUEUE_COLLECTION = "content_review_queue"
BATCH_SIZE = 500

# ============================================================
# WHITELIST RESTRITIVA — campo a campo, coleção a coleção
# ------------------------------------------------------------
# Adicionar aqui exige revisão. BNCC/AEE/learning_objects NÃO entram.
# ============================================================
CONTENT_FIELDS_BY_COLLECTION: Dict[str, List[str]] = {
    "students": ["observations"],
    "student_history": ["observations"],
    "enrollments": ["observations"],
    "staff": ["observacoes"],
    # Estes campos precisam ser adicionados ao schema Class antes de entrarem:
    # "classes": ["descricao", "observacoes"],
    # Pareceres descritivos (quando houver coleção dedicada):
    # "parecer_descritivo": ["texto"],
}

# ============================================================
# REGRAS DE PRESERVAÇÃO
# ============================================================
# Siglas que devem permanecer em UPPER mesmo após sentence case
PRESERVED_ACRONYMS = {
    "AEE", "BNCC", "EJA", "ENEM", "INEP", "MEC", "PNE", "PNAE", "PCD",
    "TGD", "TEA", "TDAH", "EMEIEF", "EMEF", "EMEI", "EJEM", "ETI",
    "FUNDEB", "FUNDEF", "ABNT", "OAB", "SEMED", "SEDUC", "PMPI", "PME",
    "CNPJ", "CPF", "RG", "NIS", "PIS", "SUS", "CEP", "LGPD", "BF",
    "UBS", "CRAS", "CREAS", "UTI", "TI", "USB", "LED", "PDF", "CSV",
    "IPTU", "ICMS", "ISS", "CNH", "IP", "DNS", "API", "SQL",
    "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
    "QI",
    "B1", "B2", "B3", "B4",  # bimestres
}

# Palavras que, mesmo em meio de frase, continuam MINÚSCULAS (preposições/conjunções)
LOWER_PARTICLES = {
    "a", "o", "e", "é", "ou", "da", "de", "di", "do", "du",
    "das", "dos", "em", "no", "na", "nos", "nas", "por", "pelo", "pela",
    "com", "sem", "para", "pra", "à", "ao", "aos", "às", "se",
}

# Caracteres terminadores de sentença (usado pelos regex dentro de to_sentence_case)

# Detecta padrões que devem ser PRESERVADOS (números, datas, horas, percentuais, citações)
# Ordem importa: mais específico primeiro.
PRESERVE_PATTERNS = [
    (re.compile(r'"[^"]*"'), "QT"),                                    # "citação"
    (re.compile(r"'[^']*'"), "QS"),                                    # 'citação'
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"), "DT"),                # 01/01/2026
    (re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"), "TM"),               # 14:30
    (re.compile(r"\b\d+[.,]?\d*\s*%"), "PC"),                          # 85%
    (re.compile(r"\b\d+[.,]?\d*\b"), "NM"),                            # 42, 3.14, 1.500,00
]

_PLACEHOLDER_RE = re.compile(r"\uE000[a-z]+\uE001")


def _to_letters(n: int) -> str:
    """Converte int para sequência de letras (a, b, ..., z, aa, ab, ...). Imune a \\d."""
    if n == 0:
        return "a"
    out = []
    while n:
        out.append(chr(ord("a") + n % 26))
        n //= 26
    return "".join(reversed(out))


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def is_likely_caps(text: str) -> bool:
    """Detecta se o texto é predominantemente CAIXA ALTA (>70% das letras)."""
    if not text or not isinstance(text, str):
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return (upper / len(letters)) >= 0.70


def _protect(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Substitui padrões preserváveis por placeholders Unicode PUA + letras
    (imunes a \\d, e \\b não corta dentro porque letras são word chars)."""
    slots: List[Tuple[str, str]] = []

    def _sub(match: re.Match) -> str:
        idx = len(slots)
        token = f"\uE000{_to_letters(idx)}\uE001"
        slots.append((token, match.group(0)))
        return token

    protected = text
    for pattern, _tag in PRESERVE_PATTERNS:
        protected = pattern.sub(lambda m: _sub(m), protected)
    return protected, slots


def _restore(text: str, slots: List[Tuple[str, str]]) -> str:
    for token, original in slots:
        text = text.replace(token, original)
    return text


def to_sentence_case(text: str) -> str:
    """Converte texto em CAPS para sentence case preservando:
       - siglas conhecidas (PRESERVED_ACRONYMS)
       - citações (entre aspas simples ou duplas)
       - datas (dd/mm/aaaa), horas (hh:mm), números, percentuais
       - primeira letra de cada sentença (após . ! ? ou início do texto)
    """
    if not text or not isinstance(text, str):
        return text

    # 1) Protege padrões imunes
    protected, slots = _protect(text)

    # 2) Baixa TUDO para minúsculas (placeholders permanecem intactos — \x00 e dígitos)
    lowered = protected.lower()

    # 3) Capitaliza primeira letra após início do texto ou após . ! ?
    def _capitalize_after(match: re.Match) -> str:
        prefix = match.group(1)  # pontuação ou '' (início)
        letter = match.group(2)
        return prefix + letter.upper()

    # Caso 1: primeira letra real do texto (ignorando placeholders e espaços iniciais)
    result = re.sub(
        r"^([\s]*(?:\uE000[a-z]+\uE001)?[\s]*)([a-zà-ÿ])",
        lambda m: m.group(1) + m.group(2).upper(),
        lowered,
    )
    # Caso 2: após pontuação terminal
    result = re.sub(
        r"([.!?]+\s+)([a-zà-ÿ])",
        _capitalize_after,
        result,
    )

    # 4) Restaura siglas conhecidas (case-insensitive)
    def _restore_acronym(match: re.Match) -> str:
        w = match.group(0)
        if w.upper() in PRESERVED_ACRONYMS:
            return w.upper()
        return w

    # Evita tocar em tokens que fazem parte de placeholders (\x00XX99\x00)
    def _preserve_placeholders_regex(pattern: re.Pattern, repl, s: str) -> str:
        # Substitui cada match EXCETO se estiver dentro de um placeholder
        out: List[str] = []
        last = 0
        for ph in _PLACEHOLDER_RE.finditer(s):
            # processa região anterior
            out.append(pattern.sub(repl, s[last:ph.start()]))
            # placeholder intacto
            out.append(ph.group(0))
            last = ph.end()
        out.append(pattern.sub(repl, s[last:]))
        return "".join(out)

    result = _preserve_placeholders_regex(
        re.compile(r"\b[a-zà-ÿ][a-zà-ÿ0-9]+\b"), _restore_acronym, result,
    )

    # 5) Restaura placeholders dos padrões protegidos
    return _restore(result, slots)


# ============================================================
# QUEUE OPERATIONS
# ============================================================
async def ensure_queue_indexes(db) -> None:
    col = db[QUEUE_COLLECTION]
    await col.create_index("status")
    await col.create_index([("source_collection", 1), ("source_id", 1), ("source_field", 1)])
    await col.create_index("mantenedora_id")
    await col.create_index("created_at")
    logger.info("Índices de %s garantidos.", QUEUE_COLLECTION)


async def _already_queued(db, col_name: str, doc_id: Any, field: str) -> bool:
    existing = await db[QUEUE_COLLECTION].find_one({
        "source_collection": col_name,
        "source_id": str(doc_id),
        "source_field": field,
        "status": "pending",
    }, {"_id": 1})
    return existing is not None


def _build_queue_item(
    col_name: str, doc: Dict[str, Any], field: str,
    original: str, sugestao: str,
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source_collection": col_name,
        "source_id": str(doc.get("id") or doc.get("_id")),
        "source_field": field,
        "original": original,
        "sugestao": sugestao,
        "status": "pending",
        "mantenedora_id": doc.get("mantenedora_id"),
        "context": {
            # mini-contexto para a UI sem vazar dados sensíveis
            "full_name": doc.get("full_name") or doc.get("nome"),
            "name": doc.get("name"),
        },
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "reviewed_by": None,
        "edited_text": None,
    }


# ============================================================
# DRY-RUN
# ============================================================
async def dry_run_collection(
    db, col_name: str, fields: List[str], examples: int,
) -> Dict[str, Any]:
    col = db[col_name]
    total = await col.count_documents({})
    if total == 0:
        return {"colecao": col_name, "total": 0, "candidatos": 0, "exemplos": []}

    projection = {"_id": 1, "id": 1, "mantenedora_id": 1, **{f: 1 for f in fields}}
    cursor = col.find({}, projection)

    candidatos = 0
    exemplos: List[Dict[str, str]] = []
    async for doc in cursor:
        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            if not is_likely_caps(v):
                continue
            new_v = to_sentence_case(v)
            if new_v == v:
                continue
            candidatos += 1
            if len(exemplos) < examples:
                exemplos.append({
                    "campo": f,
                    "original": v[:120],
                    "sugestao": new_v[:120],
                })
    return {"colecao": col_name, "total": total, "candidatos": candidatos, "exemplos": exemplos}


async def cmd_dry_run(db, cols: List[str], examples: int) -> int:
    print()
    print("=" * 82)
    print(f"{'COLEÇÃO':<22} {'TOTAL':>8} {'CANDIDATOS':>12}   {'EXEMPLO':<30}")
    print("-" * 82)
    grand_total = grand_cand = 0
    all_rows: List[Dict[str, Any]] = []
    for col in cols:
        if col not in CONTENT_FIELDS_BY_COLLECTION:
            logger.warning("Fora da whitelist: %s", col); continue
        r = await dry_run_collection(db, col, CONTENT_FIELDS_BY_COLLECTION[col], examples)
        all_rows.append(r)
        ex = ""
        if r["exemplos"]:
            e = r["exemplos"][0]
            ex = f"{e['original'][:24]}…"
        print(f"{r['colecao']:<22} {r['total']:>8} {r['candidatos']:>12}   {ex:<30}")
        grand_total += r["total"]; grand_cand += r["candidatos"]
    print("-" * 82)
    print(f"{'TOTAL':<22} {grand_total:>8} {grand_cand:>12}")
    print("=" * 82)
    print()
    for r in all_rows:
        if not r["exemplos"]:
            continue
        print(f"\n  ● {r['colecao']} — amostras ({len(r['exemplos'])}):")
        for e in r["exemplos"]:
            print(f"    [{e['campo']}]")
            print(f"       ❌ {e['original']}")
            print(f"       ✅ {e['sugestao']}")
    print()
    print("ℹ️  Nenhum dado foi alterado. Para enfileirar sugestões para revisão:")
    print(f"   python scripts/normalize_content.py --scan --collections {','.join(cols)}")
    print()
    return 0


# ============================================================
# SCAN → QUEUE
# ============================================================
async def scan_collection(db, col_name: str, fields: List[str]) -> Dict[str, Any]:
    col = db[col_name]
    total = await col.count_documents({})
    if total == 0:
        return {"colecao": col_name, "total": 0, "enfileirados": 0, "pulados_duplicados": 0}

    projection = {"_id": 1, "id": 1, "mantenedora_id": 1, "full_name": 1, "nome": 1, "name": 1,
                  **{f: 1 for f in fields}}
    cursor = col.find({}, projection)
    ops: List[InsertOne] = []
    enfileirados = 0
    duplicados = 0

    async for doc in cursor:
        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            if not is_likely_caps(v):
                continue
            new_v = to_sentence_case(v)
            if new_v == v:
                continue
            if await _already_queued(db, col_name, doc.get("id") or doc.get("_id"), f):
                duplicados += 1
                continue
            ops.append(InsertOne(_build_queue_item(col_name, doc, f, v, new_v)))
            enfileirados += 1
            if len(ops) >= BATCH_SIZE:
                await db[QUEUE_COLLECTION].bulk_write(ops, ordered=False)
                ops.clear()

    if ops:
        await db[QUEUE_COLLECTION].bulk_write(ops, ordered=False)

    return {
        "colecao": col_name, "total": total,
        "enfileirados": enfileirados, "pulados_duplicados": duplicados,
    }


async def cmd_scan(db, cols: List[str]) -> int:
    await ensure_queue_indexes(db)
    results = []
    for col in cols:
        if col not in CONTENT_FIELDS_BY_COLLECTION:
            logger.warning("Fora da whitelist: %s", col); continue
        r = await scan_collection(db, col, CONTENT_FIELDS_BY_COLLECTION[col])
        results.append(r)
        logger.info("scan: %s", r)

    total_queued = sum(r["enfileirados"] for r in results)
    total_dup = sum(r["pulados_duplicados"] for r in results)

    print()
    print("=" * 82)
    print("✅ SCAN CONCLUÍDO")
    print("=" * 82)
    print(f"  Sugestões enfileiradas: {total_queued}")
    print(f"  Já pendentes (ignorados): {total_dup}")
    print()
    print("  👉 Revisar em: /admin/content-review")
    print()
    return 0


# ============================================================
# CLEAR PENDING
# ============================================================
async def cmd_clear_pending(db, cols: List[str]) -> int:
    filt = {"status": "pending"}
    if cols:
        filt["source_collection"] = {"$in": cols}
    res = await db[QUEUE_COLLECTION].delete_many(filt)
    logger.info("Removidos %d itens pendentes.", res.deleted_count)
    return 0


# ============================================================
# CLI
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Normalização reversa de CONTEÚDOS textuais (CAPS → sentence case) via fila de revisão.",
    )
    grp = p.add_mutually_exclusive_group(required=False)
    grp.add_argument("--dry-run", action="store_true",
                     help="(default) Análise sem alterar nada.")
    grp.add_argument("--scan", action="store_true",
                     help="Enfileira sugestões em content_review_queue.")
    grp.add_argument("--clear-pending", action="store_true",
                     help="Remove itens pending da fila (não afeta doc original).")
    p.add_argument("--collections", default=",".join(CONTENT_FIELDS_BY_COLLECTION.keys()))
    p.add_argument("--examples", type=int, default=5)
    p.add_argument("--log-file", help="Caminho de arquivo de log.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def setup_logging(log_file: Optional[str], verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=handlers, force=True)


async def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_file, args.verbose)

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        logger.error("MONGO_URL/DB_NAME ausentes.")
        return 2

    cols = [c.strip() for c in args.collections.split(",") if c.strip()]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    logger.info("DB=%s · coleções=%s", db_name, cols)

    try:
        if args.scan:
            return await cmd_scan(db, cols)
        if args.clear_pending:
            return await cmd_clear_pending(db, cols)
        return await cmd_dry_run(db, cols, args.examples)
    finally:
        client.close()


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
