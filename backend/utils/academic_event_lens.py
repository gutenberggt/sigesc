"""
Academic Event Lens — autoridade ÚNICA de resolução temporal pedagógica.

[Fev/2026] Implementa o contrato congelado em `/app/docs/ACADEMIC_EVENT_CONTRACT.md`.

PRINCÍPIO ARQUITETURAL CRÍTICO:
========================================================================
Esta é a ÚNICA camada que resolve "quem pode editar o quê e quando" no
domínio pedagógico. Nenhum router, frontend ou query manual deve manter
regra temporal paralela.

Tudo passa por `resolve_student_ownership(...)`.
========================================================================

API canônica:

    state = await resolve_student_ownership(
        db,
        student_id=sid,
        class_id=cid,
        course_id=coid,           # opcional
        target_date="2026-08-15", # YYYY-MM-DD ou None = hoje no tz institucional
        mantenedora_id=tid,       # opcional, para precedência custom
    )

    # state = {
    #   "decision_version": "1",
    #   "editable": True/False,
    #   "visible": True,           # NUNCA False — contrato §16: rastreabilidade preservada
    #   "owner_teacher_id": str | None,
    #   "source": "origin" | "destination" | "neutral",
    #   "sync_mode": "origin_authoritative" | "isolated" | "neutral",
    #   "historical_cutoff_date": "YYYY-MM-DD" | None,
    #   "blocked_reason": str | None,
    #   "governing_event_id": str | None,
    #   "governing_event_type": str | None,
    #   "governing_effective_date": str | None,
    # }

PRECEDÊNCIA (V1, contrato §15):
    reclassificacao > progressao_parcial > remanejamento > transfer
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ===========================================================================
# Constantes congeladas — não mudar sem bumpar `decision_version`.
# ===========================================================================
DECISION_VERSION = "1"

# Precedência V1 (cf. /app/docs/ACADEMIC_EVENT_CONTRACT.md §15)
ACADEMIC_EVENT_PRECEDENCE: tuple[str, ...] = (
    "reclassificacao",      # mais alta — sobrescreve qualquer outro
    "progressao_parcial",
    "remanejamento",
    "transfer",             # mais baixa
)
PRECEDENCE_INDEX: dict[str, int] = {t: i for i, t in enumerate(ACADEMIC_EVENT_PRECEDENCE)}

DEFAULT_INSTITUTIONAL_TZ = "America/Sao_Paulo"


# ===========================================================================
# Helpers
# ===========================================================================
async def _get_institutional_tz(db, mantenedora_id: Optional[str]) -> ZoneInfo:
    """Resolve o timezone institucional da mantenedora.

    Fallback: America/Sao_Paulo (default Brasil).
    """
    if mantenedora_id:
        m = await db.mantenedoras.find_one(
            {"id": mantenedora_id}, {"_id": 0, "timezone": 1}
        )
        if m and m.get("timezone"):
            try:
                return ZoneInfo(m["timezone"])
            except Exception:
                logger.warning("[lens] timezone inválido em mantenedora %s, usando default", mantenedora_id)
    return ZoneInfo(DEFAULT_INSTITUTIONAL_TZ)


def _to_date(value, tz: ZoneInfo) -> date:
    """Converte string/datetime/date para `date` no timezone institucional.

    NUNCA compare datas naïve UTC em bloqueios pedagógicos — exigência do owner.
    """
    if value is None:
        return datetime.now(tz).date()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tz).date()
    if isinstance(value, str):
        # ISO YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SSZ
        s = value[:10]
        return date.fromisoformat(s)
    raise ValueError(f"Não consigo converter para date: {value!r}")


def pick_governing_event(events: Iterable[dict]) -> Optional[dict]:
    """Escolhe o evento de maior precedência entre eventos APROVADOS coexistentes.

    Tiebreaker: `effective_date` mais recente; depois `created_at`.

    Eventos com `approval_status != 'approved'` ou `superseded` são ignorados.
    """
    valid = [
        e for e in events
        if e.get("approval_status") == "approved"
        and not e.get("superseded_by_event_id")
    ]
    if not valid:
        return None

    def _key(e: dict) -> tuple:
        prec = PRECEDENCE_INDEX.get(e.get("event_type", ""), 999)
        eff = e.get("effective_date") or ""
        created = e.get("created_at") or ""
        # menor índice = maior precedência → ordenamos crescente
        return (prec, -_yyyymmdd_to_int(eff), -_iso_to_int(created))

    valid.sort(key=_key)
    return valid[0]


def _yyyymmdd_to_int(s: str) -> int:
    try:
        return int(s.replace("-", "")[:8] or "0")
    except (ValueError, AttributeError):
        return 0


def _iso_to_int(s: str) -> int:
    try:
        return int("".join(c for c in s if c.isdigit())[:14] or "0")
    except (ValueError, AttributeError):
        return 0


# ===========================================================================
# API canônica
# ===========================================================================
async def resolve_student_ownership(
    db,
    *,
    student_id: str,
    class_id: str,
    course_id: Optional[str] = None,
    target_date=None,
    mantenedora_id: Optional[str] = None,
) -> dict:
    """Resolve quem é dono do registro pedagógico em (aluno, turma, data).

    `target_date` aceita None (hoje no tz institucional), str (YYYY-MM-DD ou ISO),
    date ou datetime. Comparação SEMPRE feita em `date` no tz institucional.

    Retorno é determinístico, serializável, auditável.
    """
    tz = await _get_institutional_tz(db, mantenedora_id)
    target = _to_date(target_date, tz)

    # Eventos APROVADOS do aluno em que esta turma é origem OU destino.
    flt: dict = {
        "student_id": student_id,
        "approval_status": "approved",
        "superseded_by_event_id": None,
        "$or": [{"origin_class_id": class_id}, {"destination_class_id": class_id}],
    }
    events = await db.academic_events.find(flt, {"_id": 0}).to_list(50)

    governing = pick_governing_event(events)

    base_decision = {
        "decision_version": DECISION_VERSION,
        "visible": True,                     # contrato §16.1 — sempre visível
        "editable": True,
        "owner_teacher_id": None,
        "source": "neutral",
        "sync_mode": "neutral",
        "historical_cutoff_date": None,
        "blocked_reason": None,
        "governing_event_id": None,
        "governing_event_type": None,
        "governing_effective_date": None,
    }

    if governing is None:
        # Sem evento aplicável — comportamento padrão (turma é dona).
        return base_decision

    effective = _to_date(governing["effective_date"], tz)
    is_origin = governing.get("origin_class_id") == class_id
    is_destination = governing.get("destination_class_id") == class_id

    decision = {
        **base_decision,
        "governing_event_id": governing["id"],
        "governing_event_type": governing.get("event_type"),
        "governing_effective_date": str(effective),
        "historical_cutoff_date": str(effective),
    }

    # --- Regras temporais (cf. §4 e §5) ---
    if is_origin and target < effective:
        # Pré-evento na origem → editável pela origem
        decision.update({
            "editable": True,
            "source": "origin",
            "sync_mode": "origin_authoritative",
            "owner_teacher_id": governing.get("origin_teacher_id"),
        })
    elif is_origin and target >= effective:
        # Pós-evento na origem → BLOQUEADO (aluno foi embora)
        decision.update({
            "editable": False,
            "source": "origin",
            "sync_mode": "isolated",
            "blocked_reason": "AFTER_EFFECTIVE_DATE",
        })
    elif is_destination and target < effective:
        # Pré-evento no destino → herdado, READ-ONLY (origem é dona)
        decision.update({
            "editable": False,
            "source": "destination",
            "sync_mode": "origin_authoritative",
            "owner_teacher_id": governing.get("origin_teacher_id"),
            "blocked_reason": "BEFORE_EFFECTIVE_DATE_DESTINATION",
        })
    elif is_destination and target >= effective:
        # Pós-evento no destino → editável pelo destino
        decision.update({
            "editable": True,
            "source": "destination",
            "sync_mode": "isolated",
            "owner_teacher_id": governing.get("destination_teacher_id"),
        })

    return decision


# ===========================================================================
# Lente para enriquecer listas de items do diário (NÃO filtra; só anota)
# ===========================================================================
async def annotate_items_with_lens(
    db,
    items: list[dict],
    *,
    class_id: str,
    course_id: Optional[str],
    target_date,
    mantenedora_id: Optional[str] = None,
) -> list[dict]:
    """Anexa `_locked`, `_inherited`, `_lock_reason`, `_governing_event_id` a cada item.

    NÃO filtra a lista — contrato §16: rastreabilidade histórica preservada.
    Frontend reflete badges; nunca decide localmente.
    """
    if not items:
        return items
    sids = [it.get("student_id") for it in items if it.get("student_id")]
    if not sids:
        return items

    # 1 query agregada para todos os events do batch.
    events = await db.academic_events.find({
        "student_id": {"$in": sids},
        "approval_status": "approved",
        "superseded_by_event_id": None,
        "$or": [{"origin_class_id": class_id}, {"destination_class_id": class_id}],
    }, {"_id": 0}).to_list(500)

    by_student: dict[str, list[dict]] = {}
    for ev in events:
        by_student.setdefault(ev["student_id"], []).append(ev)

    tz = await _get_institutional_tz(db, mantenedora_id)
    target = _to_date(target_date, tz)

    for it in items:
        sid = it.get("student_id")
        if not sid or sid not in by_student:
            it["_locked"] = False
            it["_inherited"] = False
            it["_lock_reason"] = None
            it["_governing_event_id"] = None
            continue
        governing = pick_governing_event(by_student[sid])
        if governing is None:
            it["_locked"] = False
            it["_inherited"] = False
            it["_lock_reason"] = None
            it["_governing_event_id"] = None
            continue
        effective = _to_date(governing["effective_date"], tz)
        is_origin = governing.get("origin_class_id") == class_id
        is_destination = governing.get("destination_class_id") == class_id

        locked = False
        inherited = False
        reason = None
        if is_origin and target >= effective:
            locked = True
            reason = "AFTER_EFFECTIVE_DATE"
        elif is_destination and target < effective:
            locked = True
            inherited = True
            reason = "BEFORE_EFFECTIVE_DATE_DESTINATION"

        it["_locked"] = locked
        it["_inherited"] = inherited
        it["_lock_reason"] = reason
        it["_governing_event_id"] = governing["id"]
        it["_governing_event_type"] = governing.get("event_type")
        it["_historical_cutoff_date"] = str(effective)
    return items


# ===========================================================================
# Auditoria de tentativas bloqueadas (cf. §8)
# ===========================================================================
async def record_lock_audit(
    db,
    *,
    event_id: Optional[str],
    action: str,
    user_id: str,
    role: Optional[str],
    student_id: str,
    class_id: str,
    target_date,
    target_resource: str,
    reason_code: str,
    payload_hash: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Registra tentativa bloqueada em `db.academic_event_audit`."""
    import uuid
    entry = {
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "action": action,
        "attempted_by_user_id": user_id,
        "attempted_role": role,
        "target_student_id": student_id,
        "target_class_id": class_id,
        "target_date": str(target_date) if target_date else None,
        "target_resource": target_resource,
        "reason_code": reason_code,
        "payload_hash": payload_hash,
        "ip": ip,
        "user_agent": user_agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.academic_event_audit.insert_one(entry)
    except Exception as e:
        logger.exception("[lens-audit] falha ao gravar audit: %s", e)


async def ensure_indexes(db) -> None:
    await db.academic_events.create_index("student_id", background=True)
    await db.academic_events.create_index([("origin_class_id", 1), ("approval_status", 1)], background=True)
    await db.academic_events.create_index([("destination_class_id", 1), ("approval_status", 1)], background=True)
    await db.academic_events.create_index([("mantenedora_id", 1), ("created_at", -1)], background=True)
    await db.academic_events.create_index("supersedes_event_id", background=True)
    await db.academic_event_audit.create_index([("created_at", -1)], background=True)
    await db.academic_event_audit.create_index("attempted_by_user_id", background=True)
    await db.academic_event_audit.create_index("event_id", background=True)
