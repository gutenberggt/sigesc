"""Fase 6.6A — read model batch da Fonte Efetiva para listagem de Planos AEE.

Este módulo é deliberadamente puro em relação ao runtime HTTP: não instala rotas,
não altera respostas e não persiste dados. Ele recebe Planos legado já autorizados
pelo endpoint existente e resolve heads/snapshots V2 em lote.

Hard gate arquitetural:
- no máximo uma consulta de heads por lote;
- no máximo uma consulta de snapshots por lote;
- nenhum ``find_one`` por Plano;
- nenhum ``create_index``;
- nenhum write.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any, Optional

from .repository import AEEV2Repository
from .versioning import AEEV2Snapshot, verify_snapshot_hash


V2_TO_LEGACY_STATUS = {
    "draft": "rascunho",
    "active": "ativo",
    "review": "revisao",
    "closed": "encerrado",
    "cancelled": "cancelado",
}
LEGACY_TO_V2_STATUS = {value: key for key, value in V2_TO_LEGACY_STATUS.items()}

_DAY_ORDER = {
    "segunda": 0,
    "segunda-feira": 0,
    "terca": 1,
    "terça": 1,
    "terca-feira": 1,
    "terça-feira": 1,
    "quarta": 2,
    "quarta-feira": 2,
    "quinta": 3,
    "quinta-feira": 3,
    "sexta": 4,
    "sexta-feira": 4,
}


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = " ".join(str(value).strip().split())
    return value or None


def normalize_days(values: Any) -> list[str]:
    """Normaliza apenas whitespace/duplicação e ordena dias conhecidos."""

    if not isinstance(values, (list, tuple, set)):
        return []
    unique: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return sorted(
        unique,
        key=lambda value: (
            _DAY_ORDER.get(value.lower(), 99),
            value.lower(),
            value,
        ),
    )


def _schedule_from_snapshot(snapshot: AEEV2Snapshot) -> tuple[list[str], str]:
    sessions = list(snapshot.dossier.schedule.sessions or [])
    days = normalize_days([session.weekday for session in sessions])
    if not sessions:
        return days, "empty"

    shapes = {
        (
            _text(session.start),
            _text(session.end),
            _text(session.local),
            _text(session.modalidade),
        )
        for session in sessions
    }
    return days, "heterogeneous" if len(shapes) > 1 else "homogeneous"


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _base_item(plano: Mapping[str, Any]) -> dict[str, Any]:
    legacy_status = _text(plano.get("status"))
    legacy_days = normalize_days(plano.get("dias_atendimento"))
    return {
        "legacy_plano_id": _text(plano.get("id")),
        "v2_managed": False,
        "management_state": "legacy_only",
        "effective_source": "legacy",
        "effective_version": {
            "active_snapshot_id": None,
            "document_version": None,
            "revision": None,
            "working_snapshot_id": None,
        },
        "legacy_status": legacy_status,
        "effective_lifecycle_status": LEGACY_TO_V2_STATUS.get(legacy_status),
        "effective_legacy_status": legacy_status,
        "legacy_days": legacy_days,
        "effective_days": list(legacy_days),
        "schedule_shape": "legacy_projection",
        "status_parity": True,
        "days_parity": True,
        "integrity_error": None,
        "working_integrity_error": None,
    }


def _identity_error(
    source: Mapping[str, Any],
    plano: Mapping[str, Any],
    *,
    prefix: str,
) -> Optional[dict[str, str]]:
    for field in ("student_id", "school_id", "academic_year"):
        expected = plano.get(field)
        actual = source.get(field)
        if expected is None or actual is None:
            continue
        if str(actual) != str(expected):
            return _error(
                f"AEE_V2_PLAN_LIST_{prefix}_IDENTITY_MISMATCH",
                f"Identidade {field} do AEE v2 diverge da âncora legado.",
            )
    return None


def _validate_snapshot(
    raw: Optional[Mapping[str, Any]],
    *,
    expected_id: Optional[str],
    legacy_plano_id: str,
    plano: Mapping[str, Any],
    kind: str,
) -> tuple[Optional[AEEV2Snapshot], Optional[dict[str, str]]]:
    prefix = kind.upper()
    if not expected_id:
        return None, None
    if raw is None:
        return None, _error(
            f"AEE_V2_PLAN_LIST_{prefix}_SNAPSHOT_MISSING",
            f"Ponteiro {kind} aponta para snapshot AEE v2 inexistente.",
        )
    raw_dict = dict(raw)
    if not verify_snapshot_hash(raw_dict):
        return None, _error(
            f"AEE_V2_PLAN_LIST_{prefix}_SNAPSHOT_HASH_INVALID",
            f"Snapshot {kind} AEE v2 falhou na verificação de integridade.",
        )
    try:
        snapshot = AEEV2Snapshot.model_validate(raw_dict)
    except Exception:
        return None, _error(
            f"AEE_V2_PLAN_LIST_{prefix}_SNAPSHOT_CONTRACT_INVALID",
            f"Snapshot {kind} AEE v2 não atende ao contrato persistido.",
        )
    if snapshot.id != expected_id:
        return None, _error(
            f"AEE_V2_PLAN_LIST_{prefix}_SNAPSHOT_ID_MISMATCH",
            f"Snapshot {kind} resolvido não corresponde ao ponteiro do head.",
        )
    if snapshot.legacy_plano_id != legacy_plano_id:
        return None, _error(
            f"AEE_V2_PLAN_LIST_{prefix}_PLAN_ID_MISMATCH",
            f"Snapshot {kind} pertence a outro Plano AEE legado.",
        )
    dossier = snapshot.dossier
    dossier_identity = {
        "student_id": dossier.student_id,
        "school_id": dossier.school_id,
        "academic_year": dossier.academic_year,
    }
    identity_error = _identity_error(dossier_identity, plano, prefix=f"{prefix}_DOSSIER")
    if identity_error:
        return None, identity_error
    return snapshot, None


async def resolve_plan_list_effective_batch(
    db,
    planos: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve summaries técnicos com <=2 round-trips Mongo V2 por lote."""

    started = perf_counter()
    plans = [plano for plano in planos if isinstance(plano, Mapping)]
    base_items = [_base_item(plano) for plano in plans]

    valid_ids: list[str] = []
    seen_ids: set[str] = set()
    for item in base_items:
        plano_id = item.get("legacy_plano_id")
        if plano_id and plano_id not in seen_ids:
            seen_ids.add(plano_id)
            valid_ids.append(plano_id)

    head_queries = 0
    snapshot_queries = 0
    heads_by_plan: dict[str, dict[str, Any]] = {}
    snapshots_by_id: dict[str, dict[str, Any]] = {}

    if valid_ids:
        head_queries = 1
        head_cursor = db[AEEV2Repository.HEADS].find(
            {"legacy_plano_id": {"$in": valid_ids}},
            {
                "_id": 0,
                "legacy_plano_id": 1,
                "student_id": 1,
                "school_id": 1,
                "academic_year": 1,
                "active_snapshot_id": 1,
                "working_snapshot_id": 1,
                "head_revision": 1,
            },
        )
        heads = await head_cursor.to_list(length=len(valid_ids))
        heads_by_plan = {
            str(head.get("legacy_plano_id")): dict(head)
            for head in heads
            if head.get("legacy_plano_id")
        }

        snapshot_ids: list[str] = []
        seen_snapshot_ids: set[str] = set()
        for head in heads_by_plan.values():
            for field in ("active_snapshot_id", "working_snapshot_id"):
                snapshot_id = _text(head.get(field))
                if snapshot_id and snapshot_id not in seen_snapshot_ids:
                    seen_snapshot_ids.add(snapshot_id)
                    snapshot_ids.append(snapshot_id)

        if snapshot_ids:
            snapshot_queries = 1
            snapshot_cursor = db[AEEV2Repository.SNAPSHOTS].find(
                {"id": {"$in": snapshot_ids}},
                {"_id": 0},
            )
            snapshots = await snapshot_cursor.to_list(length=len(snapshot_ids))
            snapshots_by_id = {
                str(snapshot.get("id")): dict(snapshot)
                for snapshot in snapshots
                if snapshot.get("id")
            }

    result_items: list[dict[str, Any]] = []
    for plano, item in zip(plans, base_items):
        plano_id = item.get("legacy_plano_id")
        if not plano_id:
            item.update(
                {
                    "management_state": "integrity_error",
                    "effective_source": None,
                    "effective_lifecycle_status": None,
                    "effective_legacy_status": None,
                    "effective_days": None,
                    "schedule_shape": None,
                    "status_parity": None,
                    "days_parity": None,
                    "integrity_error": _error(
                        "AEE_V2_PLAN_LIST_LEGACY_ID_MISSING",
                        "Plano AEE retornado sem identificador legado.",
                    ),
                }
            )
            result_items.append(item)
            continue

        head = heads_by_plan.get(plano_id)
        if not head:
            result_items.append(item)
            continue

        item["v2_managed"] = True
        item["effective_version"]["active_snapshot_id"] = _text(
            head.get("active_snapshot_id")
        )
        item["effective_version"]["working_snapshot_id"] = _text(
            head.get("working_snapshot_id")
        )

        head_identity_error = _identity_error(head, plano, prefix="HEAD")
        if head_identity_error:
            item.update(
                {
                    "management_state": "integrity_error",
                    "effective_source": None,
                    "effective_lifecycle_status": None,
                    "effective_legacy_status": None,
                    "effective_days": None,
                    "schedule_shape": None,
                    "status_parity": None,
                    "days_parity": None,
                    "integrity_error": head_identity_error,
                }
            )
            result_items.append(item)
            continue

        active_id = item["effective_version"]["active_snapshot_id"]
        working_id = item["effective_version"]["working_snapshot_id"]

        working_snapshot, working_error = _validate_snapshot(
            snapshots_by_id.get(working_id) if working_id else None,
            expected_id=working_id,
            legacy_plano_id=plano_id,
            plano=plano,
            kind="working",
        )
        if working_id:
            item["working_integrity_error"] = working_error

        if not active_id:
            if not working_id or working_error:
                item["management_state"] = "integrity_error"
                item["working_integrity_error"] = working_error or _error(
                    "AEE_V2_PLAN_LIST_WORKING_POINTER_MISSING",
                    "Head AEE v2 sem snapshot ativo e sem snapshot de trabalho.",
                )
            else:
                item["management_state"] = "working_only"
            # A semântica 6.1A continua sendo legado quando não há active.
            item["effective_source"] = "legacy"
            result_items.append(item)
            continue

        active_snapshot, active_error = _validate_snapshot(
            snapshots_by_id.get(active_id),
            expected_id=active_id,
            legacy_plano_id=plano_id,
            plano=plano,
            kind="active",
        )
        if active_error or active_snapshot is None:
            item.update(
                {
                    "management_state": "integrity_error",
                    "effective_source": None,
                    "effective_lifecycle_status": None,
                    "effective_legacy_status": None,
                    "effective_days": None,
                    "schedule_shape": None,
                    "status_parity": None,
                    "days_parity": None,
                    "integrity_error": active_error
                    or _error(
                        "AEE_V2_PLAN_LIST_ACTIVE_RESOLUTION_ERROR",
                        "Não foi possível resolver o snapshot ativo.",
                    ),
                }
            )
            result_items.append(item)
            continue

        effective_days, schedule_shape = _schedule_from_snapshot(active_snapshot)
        lifecycle_status = _text(active_snapshot.dossier.lifecycle.status)
        effective_legacy_status = V2_TO_LEGACY_STATUS.get(lifecycle_status)
        if lifecycle_status and effective_legacy_status is None:
            item.update(
                {
                    "management_state": "integrity_error",
                    "effective_source": None,
                    "effective_lifecycle_status": lifecycle_status,
                    "effective_legacy_status": None,
                    "effective_days": effective_days,
                    "schedule_shape": schedule_shape,
                    "status_parity": None,
                    "days_parity": item["legacy_days"] == effective_days,
                    "integrity_error": _error(
                        "AEE_V2_PLAN_LIST_LIFECYCLE_STATUS_UNMAPPED",
                        "Status de ciclo de vida V2 sem projeção para o vocabulário legado.",
                    ),
                }
            )
            result_items.append(item)
            continue

        item.update(
            {
                "management_state": "active",
                "effective_source": "sidecar_active",
                "effective_lifecycle_status": lifecycle_status,
                "effective_legacy_status": effective_legacy_status,
                "effective_days": effective_days,
                "schedule_shape": schedule_shape,
                "status_parity": item["legacy_status"] == effective_legacy_status,
                "days_parity": item["legacy_days"] == effective_days,
            }
        )
        item["effective_version"].update(
            {
                "document_version": active_snapshot.document_version,
                "revision": active_snapshot.revision,
            }
        )
        # Um working inválido é governança degradada, mas não muda a fonte ativa íntegra.
        if working_snapshot is None and working_id and not working_error:
            item["working_integrity_error"] = _error(
                "AEE_V2_PLAN_LIST_WORKING_RESOLUTION_ERROR",
                "Não foi possível resolver o snapshot de trabalho.",
            )
        result_items.append(item)

    return {
        "items": result_items,
        "performance": {
            "head_queries": head_queries,
            "snapshot_queries": snapshot_queries,
            "batch_ms": round((perf_counter() - started) * 1000.0, 3),
        },
    }
