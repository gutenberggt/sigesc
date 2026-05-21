"""Migração de motivos legacy (texto livre) → subcódigo MEC estruturado.

Owner spec (Fev/2026):
  - Regex/keyword-based, determinístico, auditável.
  - Fallback `24z - Não classificado (legado)` quando nada matchea.
  - Sem IA, sem ML, sem LLM.
  - Preview ANTES de aplicar (gestor revisa).
  - Idempotente (documentos já com reason_id não são re-migrados).

Algoritmo:
  1. Normaliza texto (lowercase, strip accents).
  2. Itera regras em ordem de especificidade decrescente.
  3. Primeiro match wins; confidence = 1.0 quando keyword forte casa,
     0.5 quando é palavra ambígua.
  4. Sem match → `24z` (confidence 0.0).
"""
import re
import unicodedata
from typing import Optional


ENGINE_VERSION = "1.0"


def _normalize(text: str) -> str:
    """lower + remove acentos para matching tolerante."""
    if not text:
        return ""
    txt = text.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFKD", txt)
        if not unicodedata.combining(c)
    )


# Regras (ordem importa — mais específico primeiro). Estrutura:
#   (subcode, [keyword|regex, ...], confidence_when_matched)
#
# Confidence:
#   1.00 — keyword inequívoca (atestado, óbito, gravidez)
#   0.85 — keyword forte (transporte, bullying)
#   0.70 — palavra com possível ambiguidade (longe, doença)
#   0.50 — ambíguo (faltou, problemas)
RULES = [
    # Família — específico ANTES de saúde genérica (Mãe doente > doente)
    ("2b", [r"\bobito\b", r"\bfaleceu\b", r"\bmorreu\b", r"\bluto\b",
            r"\bfalecimento\b", r"\bvelorio\b", r"\benterro\b"], 1.00),
    ("2a", [r"\bmae doente\b", r"\bpai doente\b", r"\bavo doente\b",
            r"\bavoh doente\b", r"\birmao doente\b", r"\birma doente\b",
            r"\bfamiliar doente\b", r"\bdoenca na familia\b"], 1.00),

    # Saúde — específicos primeiro
    ("1c", [r"\bpre[- ]?natal\b", r"\bpos[- ]?parto\b", r"\bpuerper"], 1.00),
    ("8a", [r"\bgravidez de risco\b", r"\bgestacao de risco\b"], 1.00),
    ("8b", [r"\bgravida\b", r"\bgravidez\b", r"\bgestante\b"], 0.85),
    ("1b", [
        r"\bpsicologic\w*", r"\bdepressao\b", r"\bansiedade\b",
        r"\bterapia\b", r"\bsaude mental\b", r"\bpsiqui",
    ], 1.00),
    ("1a", [
        r"\batestado\b", r"\batestado medico\b", r"\bdoente\b", r"\bdoenca\b",
        r"\bgripe\b", r"\bfebre\b", r"\bvirose\b", r"\bcovid\b", r"\bdengue\b",
        r"\bconsulta\b", r"\bhospital\b", r"\binternad", r"\bmedico\b",
        r"\bcirurgia\b", r"\bdor de\b", r"\benjoo\b",
    ], 0.85),

    # Acesso/Transporte
    ("3a", [r"\benchente\b", r"\balagamento\b", r"\binundacao\b"], 1.00),
    ("3b", [r"\btransporte\b", r"\bonibus\b", r"\bconducao\b",
            r"\bvan escolar\b", r"\bsem transporte\b", r"\btransporte quebr",
            r"\bonibus quebr"], 0.85),
    ("3c", [r"\bestrada ruim\b", r"\bestrada fechada\b", r"\bestrada interditad\w*",
            r"\bestrada intransitavel\b", r"\batoleiro\b", r"\blama na estrada\b"], 1.00),
    ("3d", [r"\bviolencia no trajeto\b", r"\bassalto no caminho\b",
            r"\btiroteio no trajeto\b"], 1.00),
    ("3f", [r"\bmora longe\b", r"\blonga distancia\b", r"\bdistancia\b"], 0.70),

    # Suspensão / pedagógico
    ("4a", [r"\bsuspens"], 0.85),
    ("5a", [r"\batividade extraclasse\b", r"\bviagem escolar\b",
            r"\bevento escolar\b", r"\bolimpiada\b", r"\bexcursao\b",
            r"\bjogos estudantis\b"], 1.00),

    # Violência / preconceito
    ("6a", [r"\bbullying\b", r"\bpreconceito\b", r"\bdiscriminacao\b",
            r"\bracismo\b", r"\bhomofobia\b"], 1.00),

    # Situação de rua / trabalho infantil / violência escolar
    ("9a", [r"\bsituacao de rua\b", r"\bmorador de rua\b", r"\bna rua\b"], 1.00),
    ("10b", [r"\btrabalho infantil\b", r"\bcrianca trabalhand"], 1.00),
    ("11a", [r"\bviolencia escolar\b", r"\bviolencia na escola\b",
             r"\bbriga na escola\b", r"\bagressao na escola\b"], 1.00),

    # Trabalho do adolescente
    ("12d", [r"\bmenor aprendiz\b", r"\baprendiz\b"], 1.00),
    ("12b", [r"\bestagio\b", r"\bestagiando\b", r"\bestagiari"], 1.00),
    ("12a", [r"\bemprego formal\b", r"\bcarteira assinada\b"], 1.00),
    ("12c", [r"\btrabalho informal\b", r"\btrabalhando informalmente\b"], 1.00),

    # Abuso sexual
    ("13a", [r"\babuso sexual\b", r"\bexploracao sexual\b", r"\bestupro\b"], 1.00),

    # Desinteresse / abandono
    ("14a", [r"\bdesinteres", r"\bdesmotiv", r"\bnao quer estudar\b",
             r"\bsem motivacao\b"], 0.85),
    ("15a", [r"\babandonou\b", r"\babandono escolar\b", r"\bdesistiu\b",
             r"\bdesistencia\b", r"\bevasao\b"], 1.00),

    # Socioeconômico / familiar
    ("16d", [r"\bnegligencia familiar\b", r"\bnegligencia\b",
             r"\babandono familiar\b"], 1.00),
    ("16a", [r"\bseparacao dos pais\b", r"\bdivorcio\b"], 1.00),
    ("16b", [r"\bcuidar do irmao\b", r"\bcuidar da familia\b",
             r"\bcuidar dos irmaos\b", r"\bcuidar dos pais\b"], 1.00),
    ("16c", [r"\bmudou de casa\b", r"\bmudanca\b", r"\btroca de endereco\b"], 0.70),
    ("16e", [r"\bsem uniforme\b", r"\bfalta de uniforme\b",
             r"\bsem calcado\b", r"\bsem sapato\b", r"\bsem chinelo\b"], 1.00),
    ("16f", [r"\bsem material\b", r"\bfalta de material escolar\b",
             r"\bsem caderno\b", r"\bsem lapis\b", r"\bsem mochila\b"], 1.00),

    # Documentação
    ("17a", [r"\bsem documento\b", r"\bsem certidao\b", r"\bsem rg\b",
             r"\bsem cpf\b", r"\bfalta de documenta"], 1.00),

    # Inclusão
    ("18a", [r"\bsem acessibilidade\b", r"\brampa\b"], 1.00),
    ("18b", [r"\bsem profissional de apoio\b", r"\bsem cuidador\b"], 1.00),
    ("18c", [r"\bsem interprete de libras\b", r"\bsem libras\b"], 1.00),

    # Gestão
    ("19a", [r"\bsem vaga\b"], 1.00),
    ("19b", [r"\bsem modalidade\b"], 1.00),
    ("20a", [r"\bgreve\b"], 1.00),
    ("20b", [r"\bsem professor\b", r"\bescola sem professor\b"], 1.00),
    ("20c", [r"\bescola fechada\b", r"\breforma da escola\b"], 1.00),
    ("20d", [r"\bsem merenda\b", r"\bfalta de merenda\b"], 1.00),

    # Não localizado
    ("21a", [r"\bnao localizad", r"\bnao encontram\w+", r"\bsumiu\b",
             r"\bmudou sem avisar\b"], 1.00),

    # Emergência
    ("22a", [r"\bcalamidade\b", r"\bemergencia\b", r"\bestado de emergencia\b"], 1.00),

    # Privação de liberdade
    ("23a", [r"\bpreso\b", r"\bdetido\b", r"\bfunase\b", r"\bcase\b",
             r"\bcasa de detencao\b", r"\bsemiliberdade\b"], 1.00),

    # Chuva genérica (fallback ACCESS) — só se nada acima casar
    ("3a", [r"\bchuva\b", r"\bchov"], 0.70),
]


# Subcódigo fallback quando nada matchea (Não classificado legado).
LEGACY_UNCLASSIFIED_SUBCODE = "24z"


def classify_legacy_text(text: str) -> dict:
    """Classifica texto legacy → subcode MEC.

    Returns:
      `{matched: bool, suggested_subcode: str, confidence: float,
        matched_rule: str | None, fallback_used: bool}`
    """
    if not text or not text.strip():
        return {
            "matched": False,
            "suggested_subcode": LEGACY_UNCLASSIFIED_SUBCODE,
            "confidence": 0.0,
            "matched_rule": None,
            "fallback_used": True,
        }
    normalized = _normalize(text)
    for subcode, patterns, confidence in RULES:
        for pat in patterns:
            if re.search(pat, normalized):
                return {
                    "matched": True,
                    "suggested_subcode": subcode,
                    "confidence": confidence,
                    "matched_rule": pat,
                    "fallback_used": False,
                }
    return {
        "matched": False,
        "suggested_subcode": LEGACY_UNCLASSIFIED_SUBCODE,
        "confidence": 0.0,
        "matched_rule": None,
        "fallback_used": True,
    }


async def preview_legacy_migration(
    db,
    *,
    academic_year: Optional[int] = None,
    confidence_min: float = 0.0,
    limit: int = 5000,
) -> dict:
    """Análise de TODOS os trackings legacy candidatos a migração.

    Não persiste nada. Owner spec: gestor revisa antes de aplicar.

    Returns:
      ```
      {
        engine_version, total_candidates, classified, unclassified (fallback),
        by_confidence: {"1.00": N, "0.85": N, "0.70": N, "0.0": N},
        by_subcode: {subcode: N},
        samples: [first 50 items com texto + sugestão]
      }
      ```
    """
    query: dict = {
        "reason_id": None,
        "motive_legacy": {"$exists": True, "$ne": ""},
    }
    if academic_year is not None:
        query["academic_year"] = academic_year

    # Resolve subcode→id map UMA vez
    reasons_by_subcode: dict = {}
    cursor = db.attendance_frequency_reasons.find(
        {"active": True, "mec_version": "4.2"},
        {"_id": 0, "id": 1, "mec_subcode": 1, "name": 1},
    )
    async for r in cursor:
        reasons_by_subcode[r["mec_subcode"]] = r

    docs = await db.bolsa_familia_tracking.find(
        query,
        {"_id": 0, "student_id": 1, "school_id": 1, "month": 1,
         "academic_year": 1, "motive_legacy": 1},
    ).limit(limit).to_list(limit)

    classified = 0
    unclassified = 0
    by_confidence: dict = {}
    by_subcode: dict = {}
    samples: list = []
    for doc in docs:
        legacy = doc.get("motive_legacy", "")
        result = classify_legacy_text(legacy)
        if result["confidence"] < confidence_min:
            continue
        if result["fallback_used"]:
            unclassified += 1
        else:
            classified += 1
        conf_key = f"{result['confidence']:.2f}"
        by_confidence[conf_key] = by_confidence.get(conf_key, 0) + 1
        subc = result["suggested_subcode"]
        by_subcode[subc] = by_subcode.get(subc, 0) + 1
        if len(samples) < 50:
            reason_info = reasons_by_subcode.get(subc, {})
            samples.append({
                "student_id": doc.get("student_id"),
                "school_id": doc.get("school_id"),
                "month": doc.get("month"),
                "academic_year": doc.get("academic_year"),
                "legacy_text": legacy,
                "suggested_subcode": subc,
                "suggested_reason_name": reason_info.get("name"),
                "confidence": result["confidence"],
                "matched_rule": result["matched_rule"],
                "fallback_used": result["fallback_used"],
            })

    return {
        "engine_version": ENGINE_VERSION,
        "total_candidates": len(docs),
        "classified": classified,
        "unclassified": unclassified,
        "by_confidence": by_confidence,
        "by_subcode": by_subcode,
        "samples": samples,
    }


async def apply_legacy_migration(
    db,
    *,
    academic_year: Optional[int] = None,
    confidence_min: float = 0.7,
    include_fallback: bool = False,
    user_id: Optional[str] = None,
) -> dict:
    """Aplica migração nos trackings legacy. Atualiza `reason_id`
    apenas para casos com confidence >= `confidence_min`.

    `include_fallback=True` força marcar não classificados como `24z`
    (Não classificado legado) para reduzir o `total_pending` no dashboard.

    Idempotente: NÃO altera documentos que já têm `reason_id != null`.

    Cada documento atualizado ganha:
      - `reason_id` resolvido
      - `legacy_migration` = {migrated_at, engine_version, confidence,
                              matched_rule, original_legacy_text}
    """
    query: dict = {
        "reason_id": None,
        "motive_legacy": {"$exists": True, "$ne": ""},
    }
    if academic_year is not None:
        query["academic_year"] = academic_year

    # Map subcode -> id
    reasons_map: dict = {}
    cursor = db.attendance_frequency_reasons.find(
        {"active": True, "mec_version": "4.2"},
        {"_id": 0, "id": 1, "mec_subcode": 1},
    )
    async for r in cursor:
        reasons_map[r["mec_subcode"]] = r["id"]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    docs = await db.bolsa_familia_tracking.find(
        query,
        {"_id": 0, "student_id": 1, "school_id": 1, "month": 1,
         "academic_year": 1, "motive_legacy": 1},
    ).to_list(50000)

    migrated = 0
    skipped_low_confidence = 0
    skipped_fallback = 0
    errors: list = []
    by_subcode: dict = {}

    for doc in docs:
        try:
            legacy = doc.get("motive_legacy", "")
            result = classify_legacy_text(legacy)
            if result["confidence"] < confidence_min and not result["fallback_used"]:
                skipped_low_confidence += 1
                continue
            if result["fallback_used"] and not include_fallback:
                skipped_fallback += 1
                continue
            subcode = result["suggested_subcode"]
            new_reason_id = reasons_map.get(subcode)
            if not new_reason_id:
                errors.append({
                    "student_id": doc.get("student_id"),
                    "error": f"subcode {subcode} not found",
                })
                continue
            await db.bolsa_familia_tracking.update_one(
                {
                    "student_id": doc.get("student_id"),
                    "school_id": doc.get("school_id"),
                    "month": str(doc.get("month")),
                    "academic_year": doc.get("academic_year"),
                    "reason_id": None,  # garante idempotência
                },
                {
                    "$set": {
                        "reason_id": new_reason_id,
                        "updated_at": now,
                        "legacy_migration": {
                            "migrated_at": now,
                            "engine_version": ENGINE_VERSION,
                            "confidence": result["confidence"],
                            "matched_rule": result["matched_rule"],
                            "fallback_used": result["fallback_used"],
                            "original_legacy_text": legacy,
                            "migrated_by_user_id": user_id,
                        },
                    }
                },
            )
            migrated += 1
            by_subcode[subcode] = by_subcode.get(subcode, 0) + 1
        except Exception as e:  # noqa: BLE001
            errors.append({"student_id": doc.get("student_id"), "error": str(e)})

    return {
        "engine_version": ENGINE_VERSION,
        "total_processed": len(docs),
        "migrated": migrated,
        "skipped_low_confidence": skipped_low_confidence,
        "skipped_fallback": skipped_fallback,
        "errors_count": len(errors),
        "errors": errors[:50],  # limita resposta
        "by_subcode": by_subcode,
    }
