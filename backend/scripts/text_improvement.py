"""Higienização Textual Assistida — Fase 1 (FORMATAÇÃO)
========================================================

EVOLUÇÃO de `normalize_content.py` (CAPS → sentence case):
- Aqui detectamos anomalias de FORMATAÇÃO em texto JÁ em sentence case.
- 100% determinístico, ZERO IA, ZERO ortografia.
- Sempre via fila de revisão humana (`text_improvement_queue`).

Regras (Fase 1):
    1. Espaços múltiplos → 1 espaço
    2. Espaço antes de pontuação → remove
    3. Falta de espaço após pontuação (antes de letra) → adiciona
    4. Múltiplas quebras de linha (3+) → 2
    5. Capitalização inicial (1ª letra minúscula → maiúscula)
    6. Pontuação final ausente em frases (≥3 palavras) → adiciona "."
    7. Siglas minúsculas → maiúsculas (aee → AEE)
    8. Palavras duplicadas consecutivas (de de, a a) → 1

REGRAS DE OURO:
    - Não toca BNCC/AEE/learning_objects.{evidencia, resources}
    - Não toca texto inteiro em CAPS (use `normalize_content.py` antes)
    - Não toca texto com algarismos romanos (preserva estrutura)
    - Não toca listas estruturadas curtas
    - Sempre via fila — ZERO write automático

Uso:
    python scripts/text_improvement.py --dry-run
    python scripts/text_improvement.py --scan
    python scripts/text_improvement.py --clear-pending
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import InsertOne

# Permite rodar tanto `python scripts/text_improvement.py` quanto `python -m scripts.text_improvement`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from scripts.normalize_content import (  # type: ignore
        PRESERVED_ACRONYMS,
        is_likely_caps,
        should_skip_text,
        strip_accents,
    )
except ModuleNotFoundError:
    from normalize_content import (  # type: ignore  # noqa: F401
        PRESERVED_ACRONYMS,
        is_likely_caps,
        should_skip_text,
        strip_accents,
    )

load_dotenv()
logger = logging.getLogger("text_improvement")

QUEUE_COLLECTION = "text_improvement_queue"
BATCH_SIZE = 500

# ============================================================
# DICIONÁRIO ORTOGRÁFICO (Fase 2)
# ============================================================
# Lazy init: carrega só na 1ª chamada.
_SPELL = None
_EXTRA_VOCAB = {
    # Termos pedagógicos comuns que podem não estar no dict
    "bncc", "aee", "semed", "seduc", "etí", "eti", "emeief", "emeif",
    "emef", "emei", "fundeb", "funarte", "pnae", "lgpd", "pcd", "tea",
    "tdah", "alfabetização", "letramento", "interdisciplinar",
    "psicopedagógico", "psicopedagogo", "neurodivergente",
    # Verbos/substantivos do dia-a-dia escolar (frequentes em pareceres)
    "remanejado", "remanejada", "remanejamento", "remanejar",
    "rematriculado", "rematriculada", "rematrícula", "rematricular",
    "transferido", "transferida", "matriculado", "matriculada",
    "evadido", "evadida", "evasão", "reclassificação", "reclassificado",
    "reagrupamento", "reagrupamentos", "agrupamento", "agrupamentos",
    "aprovado", "reprovado", "promovido", "retido",
    "alfabetizado", "alfabetizada", "alfabetizando",
    "diversificada", "complementar", "diversificadas",
    "psicomotor", "psicomotora", "psicomotricidade",
    "sociolinguístico", "sociocultural", "psicossocial",
    "autoavaliação", "autoavaliações", "autonomia",
    "multisseriada", "multisseriado", "multisseriadas",
    "atendimento", "atendimentos",
    # Nomes próprios/locais comuns nas escolas (extensível pelo admin via DB)
    "araguaia", "floresta", "palmas", "tocantins",
}


def _get_spell():
    global _SPELL
    if _SPELL is None:
        from spellchecker import SpellChecker
        _SPELL = SpellChecker(language="pt")
        _SPELL.word_frequency.load_words(_EXTRA_VOCAB)
        logger.info("Dicionário PT carregado: %d palavras",
                    len(_SPELL.word_frequency.dictionary))
    return _SPELL

# Whitelist (mesma do content_review) — campos onde podemos enfileirar.
#
# 🛑 [Fev/2026] AEE LOCKED: coleções `aee_plans`, `aee_attendances`,
# `aee_attendance_records`, `aee_templates` NÃO entram aqui. Conteúdo
# pedagógico individualizado é fiel à digitação. Se houver necessidade
# futura de revisão para AEE, o caminho é a fila MANUAL "Apoio à Escrita"
# acionada explicitamente (jamais automática).
CONTENT_FIELDS_BY_COLLECTION: Dict[str, List[str]] = {
    "students": ["observations"],
    "student_history": ["observations"],
    "enrollments": ["observations"],
    "staff": ["observacoes"],
    "learning_objects": ["content", "methodology", "pratica_pedagogica", "observations"],
}


# ============================================================
# REGRAS DETERMINÍSTICAS DE FORMATAÇÃO
# ============================================================
_DOUBLE_SPACE_RE = re.compile(r" {2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([.,;:!?])")
# Apenas quando próximo char é LETRA (preserva números 1.500, datas, horas).
_MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"([.,;:!?])([A-Za-zÀ-ÿ])")
_TRIPLE_NEWLINE_RE = re.compile(r"\n{3,}")
_DUPLICATE_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def _has_roman_or_struct(text: str) -> bool:
    """Reusa heurística defensiva do content_review (romanos, estrutura enumerada)."""
    skip = should_skip_text(text)
    return skip is not None


def detect_format_issues(text: str) -> Tuple[str, List[str]]:
    """Aplica todas as regras determinísticas de formatação em sequência.

    Retorna (texto_corrigido, [regras_aplicadas]). Se nada mudou, retorna
    (text, []).
    """
    if not isinstance(text, str) or not text.strip():
        return text, []

    new_text = text
    rules: List[str] = []

    # 1) Espaços múltiplos (apenas espaços horizontais, preserva \n)
    candidate = _DOUBLE_SPACE_RE.sub(" ", new_text)
    if candidate != new_text:
        rules.append("espacos_duplos")
        new_text = candidate

    # 2) Espaço antes de pontuação
    candidate = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", new_text)
    if candidate != new_text:
        rules.append("espaco_antes_pontuacao")
        new_text = candidate

    # 3) Falta de espaço após pontuação (apenas antes de LETRA, preserva 1.500/14:30)
    candidate = _MISSING_SPACE_AFTER_PUNCT_RE.sub(r"\1 \2", new_text)
    if candidate != new_text:
        rules.append("espaco_apos_pontuacao")
        new_text = candidate

    # 4) Múltiplas quebras de linha
    candidate = _TRIPLE_NEWLINE_RE.sub("\n\n", new_text)
    if candidate != new_text:
        rules.append("quebras_de_linha")
        new_text = candidate

    # 5) Capitalização inicial (1ª letra alfabética minúscula → maiúscula)
    stripped = new_text.lstrip()
    if stripped and stripped[0].islower():
        prefix = new_text[: len(new_text) - len(stripped)]
        new_text = prefix + stripped[0].upper() + stripped[1:]
        rules.append("capitalizacao_inicial")

    # 6) Pontuação final em frases ≥3 palavras (evita rótulos curtos)
    stripped = new_text.rstrip()
    if stripped and len(stripped.split()) >= 3 and stripped[-1] not in ".!?:;\"'»)":
        suffix = new_text[len(stripped):]
        new_text = stripped + "." + suffix
        rules.append("pontuacao_final")

    # 7) Padronização de siglas (minúsculas → UPPER)
    for sigla in PRESERVED_ACRONYMS:
        # só faz sentido para siglas alfabéticas; pula B1-B4 e romanos curtos
        if not sigla.isalpha() or len(sigla) < 2:
            continue
        if sigla in {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}:
            continue  # romanos não são siglas
        pattern = re.compile(r"\b" + sigla.lower() + r"\b")
        candidate = pattern.sub(sigla, new_text)
        if candidate != new_text:
            rules.append(f"sigla_{sigla}")
            new_text = candidate

    # 8) Palavras duplicadas consecutivas
    # Cuidado: "Maria Maria" pode ser nome composto. Aplicamos só para palavras
    # de stop words frequentes (de, da, do, a, o, e, em, que, com, sem, para).
    _STOPWORD_DUP_RE = re.compile(
        r"\b(de|da|do|das|dos|a|o|e|em|que|com|sem|para|por|na|no|nas|nos|à|às|ao|aos)\s+\1\b",
        re.IGNORECASE,
    )
    candidate = _STOPWORD_DUP_RE.sub(r"\1", new_text)
    if candidate != new_text:
        rules.append("palavras_duplicadas")
        new_text = candidate

    return new_text, rules


def should_skip_format(text: str) -> Optional[str]:
    """Decide se o texto deve ser PULADO pela higienização de formatação."""
    if not text or not isinstance(text, str):
        return "vazio"
    if len(text.strip()) < 5:
        return "muito curto"
    if is_likely_caps(text):
        return "está em CAIXA ALTA — use Revisão de Conteúdo primeiro"
    if _has_roman_or_struct(text):
        return "contém romano/estrutura enumerada"
    return None


# ============================================================
# DETECTOR DE ORTOGRAFIA — Fase 2
# ============================================================
# Levenshtein simples (sem dependência adicional)
def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1))
        prev = curr
    return prev[-1]


_WORD_RE = re.compile(r"\b[A-Za-zÀ-ÿ]+\b")


def _is_proper_noun(text: str, match: re.Match) -> bool:
    """Heurística: palavra começa com maiúscula no MEIO da frase
    (precedida por algo que não é início de sentença) → provável nome próprio."""
    word = match.group(0)
    if not word[0].isupper():
        return False
    start = match.start()
    if start == 0:
        return False
    # Olha caracteres não-espaço anteriores
    i = start - 1
    while i >= 0 and text[i] == " ":
        i -= 1
    if i < 0:
        return False
    prev_char = text[i]
    # Se o anterior é fim-de-sentença, é início de frase (não nome próprio)
    return prev_char not in ".!?\n"


def detect_spelling_issues(
    text: str, min_confidence: float = 0.75,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Detecta palavras potencialmente erradas e sugere correção.

    Pulagem (não corrige):
      - palavras < 4 chars
      - siglas conhecidas (PRESERVED_ACRONYMS)
      - tokens UPPER (provável sigla nova)
      - nomes próprios (Capitalizada no meio da frase)
      - palavras com dígitos
      - palavras já no dicionário

    Retorna (texto_corrigido, [{original, sugestao, confidence, position}, ...]).
    Aplica todas correções com confidence ≥ min_confidence.
    """
    if not text or not isinstance(text, str):
        return text, []

    spell = _get_spell()
    candidates: List[Dict[str, Any]] = []

    for m in _WORD_RE.finditer(text):
        word = m.group(0)
        if len(word) < 4:
            continue
        if word.upper() in PRESERVED_ACRONYMS:
            continue
        if word.isupper():
            continue  # provável sigla nova (deixa pro humano)
        if _is_proper_noun(text, m):
            continue
        wlow = word.lower()
        if wlow in spell:
            continue
        suggestion = spell.correction(wlow)
        if not suggestion or suggestion == wlow:
            continue
        d = _levenshtein(wlow, suggestion)
        confidence = max(0.0, 1 - d / max(len(wlow), 1))
        if confidence < min_confidence:
            continue
        # Preserva caixa do original
        if word[0].isupper():
            suggestion = suggestion.capitalize()
        candidates.append({
            "original": word,
            "sugestao": suggestion,
            "confidence": round(confidence, 2),
            "position": m.start(),
        })

    # Aplica de trás pra frente para preservar índices
    new_text = text
    for c in sorted(candidates, key=lambda x: -x["position"]):
        s, e = c["position"], c["position"] + len(c["original"])
        new_text = new_text[:s] + c["sugestao"] + new_text[e:]

    return new_text, candidates


def should_skip_spelling(text: str) -> Optional[str]:
    """Pulagem específica para ortografia."""
    if not text or not isinstance(text, str):
        return "vazio"
    if len(text.strip()) < 8:  # textos muito curtos não justificam scan
        return "muito curto"
    if is_likely_caps(text):
        return "está em CAIXA ALTA — use Revisão de Conteúdo primeiro"
    if _has_roman_or_struct(text):
        return "contém romano/estrutura enumerada"
    return None


# ============================================================
# QUEUE
# ============================================================
async def ensure_queue_indexes(db) -> None:
    col = db[QUEUE_COLLECTION]
    await col.create_index("status")
    await col.create_index([("source_collection", 1), ("source_id", 1), ("source_field", 1)])
    await col.create_index("mantenedora_id")
    await col.create_index("created_at")
    logger.info("Índices de %s garantidos.", QUEUE_COLLECTION)


async def _already_queued(db, col_name: str, doc_id: Any, field: str, tipo: str) -> bool:
    existing = await db[QUEUE_COLLECTION].find_one({
        "source_collection": col_name,
        "source_id": str(doc_id),
        "source_field": field,
        "tipo": tipo,
        "status": "pending",
    }, {"_id": 1})
    return existing is not None


def _build_queue_item(
    col_name: str, doc: Dict[str, Any], field: str,
    original: str, sugestao: str, applied_rules: List[str],
    tipo: str = "formatacao", confidence: Optional[float] = None,
    spelling_corrections: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tipo": tipo,
        "source_collection": col_name,
        "source_id": str(doc.get("id") or doc.get("_id")),
        "source_field": field,
        # [Fev/2026] Campos para escopo do professor + UI de "Original – Turma – Componente".
        # Para coleções não-pedagógicas (students, staff, etc.) ficam None.
        "class_id": doc.get("class_id"),
        "course_id": doc.get("course_id"),
        "recorded_by_user_id": doc.get("recorded_by") or doc.get("created_by_user_id") or doc.get("created_by"),
        "original": original,
        "sugestao": sugestao,
        "applied_rules": applied_rules,
        "confidence": confidence,
        "spelling_corrections": spelling_corrections or [],
        "status": "pending",
        "mantenedora_id": doc.get("mantenedora_id"),
        "context": {
            "full_name": doc.get("full_name") or doc.get("nome"),
            "name": doc.get("name"),
        },
        "created_at": datetime.now(timezone.utc),
        "reviewed_at": None,
        "reviewed_by": None,
        "edited_text": None,
    }


# ============================================================
# DRY-RUN / SCAN
# ============================================================
async def _process_collection(db, col_name: str, fields: List[str], scan: bool):
    col = db[col_name]
    total = await col.count_documents({})
    if total == 0:
        return {"colecao": col_name, "total": 0, "candidatos_format": 0, "candidatos_spell": 0,
                "pulados": 0, "exemplos": [], "enfileirados": 0, "duplicados": 0}

    projection = {"_id": 1, "id": 1, "mantenedora_id": 1, "full_name": 1,
                  "nome": 1, "name": 1, "class_id": 1, "course_id": 1,
                  "recorded_by": 1, "created_by_user_id": 1, "created_by": 1,
                  **{f: 1 for f in fields}}
    cursor = col.find({}, projection)

    candidatos_format = 0; candidatos_spell = 0
    pulados = 0; enfileirados = 0; duplicados = 0
    exemplos: List[Dict[str, Any]] = []
    ops: List[InsertOne] = []

    async for doc in cursor:
        for f in fields:
            v = doc.get(f)
            if not isinstance(v, str) or not v.strip():
                continue
            doc_id = doc.get("id") or doc.get("_id")

            # ----- FASE 1: FORMATAÇÃO -----
            if not should_skip_format(v):
                new_v, rules = detect_format_issues(v)
                if rules:
                    candidatos_format += 1
                    if len(exemplos) < 5:
                        exemplos.append({"campo": f, "tipo": "formatacao",
                                         "original": v[:120], "sugestao": new_v[:120],
                                         "rules": rules})
                    if scan:
                        if await _already_queued(db, col_name, doc_id, f, "formatacao"):
                            duplicados += 1
                        else:
                            ops.append(InsertOne(_build_queue_item(
                                col_name, doc, f, v, new_v, rules, tipo="formatacao")))
                            enfileirados += 1

            # ----- FASE 2: ORTOGRAFIA -----
            if not should_skip_spelling(v):
                new_v_sp, corrections = detect_spelling_issues(v)
                if corrections:
                    candidatos_spell += 1
                    if len(exemplos) < 5:
                        exemplos.append({"campo": f, "tipo": "ortografia",
                                         "original": v[:120], "sugestao": new_v_sp[:120],
                                         "rules": [f"{c['original']}→{c['sugestao']}" for c in corrections[:3]]})
                    if scan:
                        if await _already_queued(db, col_name, doc_id, f, "ortografia"):
                            duplicados += 1
                        else:
                            avg_conf = sum(c["confidence"] for c in corrections) / len(corrections)
                            rules_list = [f"sp_{c['original']}_{c['sugestao']}" for c in corrections]
                            ops.append(InsertOne(_build_queue_item(
                                col_name, doc, f, v, new_v_sp, rules_list,
                                tipo="ortografia", confidence=round(avg_conf, 2),
                                spelling_corrections=corrections)))
                            enfileirados += 1

            else:
                pulados += 1

            if scan and len(ops) >= BATCH_SIZE:
                await db[QUEUE_COLLECTION].bulk_write(ops, ordered=False); ops.clear()
    if scan and ops:
        await db[QUEUE_COLLECTION].bulk_write(ops, ordered=False)

    return {"colecao": col_name, "total": total,
            "candidatos_format": candidatos_format, "candidatos_spell": candidatos_spell,
            "pulados": pulados, "exemplos": exemplos,
            "enfileirados": enfileirados, "duplicados": duplicados}


async def cmd_dry_run(db, cols: List[str]) -> int:
    print()
    print("=" * 102)
    print(f"{'COLEÇÃO':<22} {'TOTAL':>8} {'FORMAT':>8} {'ORTOG':>8} {'PULADOS':>10}   {'EXEMPLO'}")
    print("-" * 102)
    grand_total = grand_fmt = grand_sp = grand_skip = 0
    rows = []
    for col in cols:
        if col not in CONTENT_FIELDS_BY_COLLECTION:
            logger.warning("Fora da whitelist: %s", col); continue
        r = await _process_collection(db, col, CONTENT_FIELDS_BY_COLLECTION[col], scan=False)
        rows.append(r)
        ex = r["exemplos"][0]["original"][:24] + "…" if r["exemplos"] else ""
        print(f"{r['colecao']:<22} {r['total']:>8} {r['candidatos_format']:>8} "
              f"{r['candidatos_spell']:>8} {r['pulados']:>10}   {ex}")
        grand_total += r["total"]; grand_fmt += r["candidatos_format"]
        grand_sp += r["candidatos_spell"]; grand_skip += r["pulados"]
    print("-" * 102)
    print(f"{'TOTAL':<22} {grand_total:>8} {grand_fmt:>8} {grand_sp:>8} {grand_skip:>10}")
    print("=" * 102)
    print()
    for r in rows:
        if not r["exemplos"]:
            continue
        print(f"\n  ● {r['colecao']} — amostras:")
        for e in r["exemplos"]:
            tipo_emoji = "🔧" if e["tipo"] == "formatacao" else "✏️"
            print(f"    {tipo_emoji} [{e['campo']}/{e['tipo']}] regras: {e['rules']}")
            print(f"       ❌ {e['original']}")
            print(f"       ✅ {e['sugestao']}")
    print()
    print("ℹ️  Nenhum dado foi alterado. Para enfileirar:")
    print(f"   python scripts/text_improvement.py --scan --collections {','.join(cols)}")
    print()
    return 0


async def cmd_scan(db, cols: List[str]) -> int:
    await ensure_queue_indexes(db)
    total_q = total_d = 0
    for col in cols:
        if col not in CONTENT_FIELDS_BY_COLLECTION:
            logger.warning("Fora da whitelist: %s", col); continue
        r = await _process_collection(db, col, CONTENT_FIELDS_BY_COLLECTION[col], scan=True)
        logger.info("scan: %s", {k: r[k] for k in [
            "colecao", "total", "enfileirados", "duplicados",
            "candidatos_format", "candidatos_spell"]})
        total_q += r["enfileirados"]; total_d += r["duplicados"]
    print()
    print("=" * 82)
    print("✅ SCAN CONCLUÍDO")
    print("=" * 82)
    print(f"  Sugestões enfileiradas: {total_q}  (formatação + ortografia)")
    print(f"  Já pendentes (ignorados): {total_d}")
    print()
    print("  👉 Revisar em: /admin/text-improvement")
    print()
    return 0


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
        description="Higienização textual (Fase 1: FORMATAÇÃO determinística) via fila de revisão.",
    )
    grp = p.add_mutually_exclusive_group(required=False)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--scan", action="store_true")
    grp.add_argument("--clear-pending", action="store_true")
    p.add_argument("--collections", default=",".join(CONTENT_FIELDS_BY_COLLECTION.keys()))
    p.add_argument("--log-file")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def setup_logging(log_file: Optional[str], verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=handlers, force=True)


async def run(args: argparse.Namespace) -> int:
    setup_logging(args.log_file, args.verbose)
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        logger.error("MONGO_URL/DB_NAME ausentes."); return 2

    cols = [c.strip() for c in args.collections.split(",") if c.strip()]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    logger.info("DB=%s · coleções=%s", db_name, cols)
    try:
        if args.scan:
            return await cmd_scan(db, cols)
        if args.clear_pending:
            return await cmd_clear_pending(db, cols)
        return await cmd_dry_run(db, cols)
    finally:
        client.close()


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
