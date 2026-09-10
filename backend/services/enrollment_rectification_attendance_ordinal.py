"""F2.3D — migração ordinal de frequência por componente.

A data da aula da origem NÃO é usada como chave de correspondência.
Para cada componente curricular, preserva-se a sequência histórica de status
(P/F/J/A) e materializa-se essa sequência, em ordem, nas aulas já existentes
da turma destino.

Política institucional:
- nunca criar aula no destino;
- nunca sobrescrever silenciosamente frequência já existente do estudante;
- quando origem > slots do destino, aplicar até a capacidade e ignorar o
  excedente, registrando-o no resumo/auditoria;
- quando destino > origem, os slots restantes permanecem sem lançamento;
- reutilizar o ledger F2.1A como fonte imutável da sequência de origem.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from services.attendance_validation import (
    AttendanceValidationError,
    unvalidate_attendance_institutional,
)
from services.enrollment_rectification_attendance import (
    LEDGER_COLLECTION as SOURCE_LEDGER_COLLECTION,
    _digest,
)

ORDINAL_LEDGER_COLLECTION = "attendance_ordinal_rectifications"
ALLOWED_ACTOR_ROLES = frozenset({"admin", "super_admin", "gerente"})


class OrdinalAttendanceError(Exception):
    def __init__(self, code: str, message: str, *, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_sort_key(item: Mapping[str, Any]) -> tuple[str, int, str]:
    raw_aula = item.get("source_aula_numero")
    try:
        aula = int(raw_aula) if raw_aula is not None else 0
    except (TypeError, ValueError):
        aula = 0
    return (
        str(item.get("source_date") or ""),
        aula,
        str(item.get("source_attendance_id") or ""),
    )


def _target_sort_key(item: Mapping[str, Any]) -> tuple[str, int, str]:
    raw_aula = item.get("aula_numero")
    try:
        aula = int(raw_aula) if raw_aula is not None else 0
    except (TypeError, ValueError):
        aula = 0
    return (str(item.get("date") or ""), aula, str(item.get("id") or ""))


def build_ordinal_pairs(
    source_items: list[Mapping[str, Any]],
    destination_slots: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Pareia por posição; datas servem apenas para ordenar cada lado.

    Não exige igualdade de datas. O excedente da origem é deliberadamente
    ignorado conforme política F2.3D e quantificado no retorno.
    """
    ordered_source = sorted(source_items, key=_source_sort_key)
    ordered_destination = sorted(destination_slots, key=_target_sort_key)
    applied = min(len(ordered_source), len(ordered_destination))
    pairs = [
        {
            "ordinal": index + 1,
            "source": ordered_source[index],
            "destination": ordered_destination[index],
        }
        for index in range(applied)
    ]
    return {
        "pairs": pairs,
        "source_count": len(ordered_source),
        "destination_slot_count": len(ordered_destination),
        "applied_count": applied,
        "ignored_excess_count": max(0, len(ordered_source) - len(ordered_destination)),
        "unused_destination_slot_count": max(0, len(ordered_destination) - len(ordered_source)),
    }


def _has_student(doc: Mapping[str, Any], student_id: str) -> bool:
    return any(str(r.get("student_id")) == str(student_id) for r in (doc.get("records") or []))


async def build_ordinal_attendance_plan(
    db,
    *,
    protocol: str,
    tenant_id: str,
    student_id: str,
    target_class_id: str,
    academic_year: int,
) -> dict[str, Any]:
    """Planeja a materialização ordinal usando somente ledgers F2.1A APPLIED."""
    source_ledgers = await db[SOURCE_LEDGER_COLLECTION].find(
        {
            "mantenedora_id": tenant_id,
            "protocol": protocol,
            "student_id": student_id,
            "state": "APPLIED",
        },
        {"_id": 0},
    ).to_list(10000)

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    unmapped = []
    for item in source_ledgers:
        target_course_id = str(item.get("target_course_id") or "")
        if not target_course_id:
            unmapped.append(item)
            continue
        grouped.setdefault(target_course_id, []).append(item)

    components = []
    blockers = []
    totals = {
        "source_records": len(source_ledgers),
        "mapped_source_records": len(source_ledgers) - len(unmapped),
        "unmapped_source_records": len(unmapped),
        "applied_capacity": 0,
        "ignored_excess": 0,
        "unused_destination_slots": 0,
    }

    for target_course_id, source_items in sorted(grouped.items()):
        destination_slots = await db.attendance.find(
            {
                "mantenedora_id": tenant_id,
                "class_id": target_class_id,
                "academic_year": {"$in": [academic_year, str(academic_year)]},
                "course_id": target_course_id,
            },
            {"_id": 0},
        ).to_list(10000)
        conflicts = [doc for doc in destination_slots if _has_student(doc, student_id)]
        if conflicts:
            blockers.append(
                {
                    "code": "ORDINAL_DESTINATION_ATTENDANCE_ALREADY_PRESENT",
                    "target_course_id": target_course_id,
                    "count": len(conflicts),
                }
            )
            continue

        pairing = build_ordinal_pairs(source_items, destination_slots)
        components.append({"target_course_id": target_course_id, **pairing})
        totals["applied_capacity"] += pairing["applied_count"]
        totals["ignored_excess"] += pairing["ignored_excess_count"]
        totals["unused_destination_slots"] += pairing["unused_destination_slot_count"]

    if unmapped:
        blockers.append(
            {
                "code": "ORDINAL_SOURCE_COMPONENT_UNMAPPED",
                "count": len(unmapped),
            }
        )

    return {
        "contract_version": "F2.3D",
        "policy": "ordinal_by_component_ignore_excess",
        "components": components,
        "blockers": blockers,
        "totals": totals,
    }


async def apply_ordinal_attendance_from_ledger(
    db,
    *,
    protocol: str,
    tenant_id: str,
    student_id: str,
    source_class_id: str,
    target_class_id: str,
    academic_year: int,
    actor: Mapping[str, Any],
    request=None,
    audit_service=None,
) -> dict[str, Any]:
    """Materializa a sequência ordinal nas aulas existentes do destino.

    O chamador deve possuir o lock crítico da retificação/recuperação.
    """
    if actor.get("role") not in ALLOWED_ACTOR_ROLES:
        raise OrdinalAttendanceError("ORDINAL_ACTOR_FORBIDDEN", "Perfil não autorizado para migração ordinal.")

    plan = await build_ordinal_attendance_plan(
        db,
        protocol=protocol,
        tenant_id=tenant_id,
        student_id=student_id,
        target_class_id=target_class_id,
        academic_year=academic_year,
    )
    if plan["blockers"]:
        raise OrdinalAttendanceError(
            "ORDINAL_PLAN_BLOCKED",
            "A migração ordinal possui bloqueios no destino.",
            detail={"blockers": plan["blockers"]},
        )

    applied = 0
    revalidation_pending = 0
    now = _now()
    for component in plan["components"]:
        for pair in component["pairs"]:
            source = pair["source"]
            target = pair["destination"]
            target_id = str(target.get("id") or "")
            if not target_id:
                raise OrdinalAttendanceError("ORDINAL_TARGET_ID_MISSING", "Slot de destino sem id.")

            ledger_key = {
                "mantenedora_id": tenant_id,
                "protocol": protocol,
                "target_attendance_id": target_id,
                "student_id": student_id,
            }
            prior = await db[ORDINAL_LEDGER_COLLECTION].find_one(ledger_key, {"_id": 0})
            if prior and prior.get("state") == "APPLIED":
                continue

            current = await db.attendance.find_one(
                {"id": target_id, "mantenedora_id": tenant_id}, {"_id": 0}
            )
            if not current:
                raise OrdinalAttendanceError("ORDINAL_TARGET_DISAPPEARED", "Aula de destino desapareceu durante a aplicação.")
            if _has_student(current, student_id):
                raise OrdinalAttendanceError(
                    "ORDINAL_DESTINATION_ATTENDANCE_ALREADY_PRESENT",
                    "O destino recebeu frequência concorrente para o estudante.",
                    detail={"target_attendance_id": target_id},
                )

            before = deepcopy(current)
            requires_revalidation = bool(current.get("validated_by") or current.get("validated_at"))
            if requires_revalidation:
                rationale = f"F2.3D migração ordinal de frequência — protocolo {protocol}."
                try:
                    await unvalidate_attendance_institutional(
                        db,
                        target_id,
                        user=dict(actor),
                        request=request,
                        audit_service=audit_service,
                        rationale=rationale,
                        allow_management_override=True,
                    )
                except AttendanceValidationError as exc:
                    raise OrdinalAttendanceError(
                        "ORDINAL_TARGET_UNVALIDATION_FAILED",
                        "Falha ao desvalidar frequência do destino antes da materialização.",
                        detail={"cause": exc.code},
                    ) from exc
                current = await db.attendance.find_one(
                    {"id": target_id, "mantenedora_id": tenant_id}, {"_id": 0}
                )
                revalidation_pending += 1

            source_record = deepcopy(source.get("source_record") or {})
            source_record["student_id"] = student_id
            source_record["status"] = source.get("attendance_status") or source_record.get("status")
            source_record["migrated_from_class_id"] = source_class_id
            source_record["migrated_at"] = now
            source_record["rectification_protocol"] = protocol
            source_record["rectification_ordinal"] = int(pair["ordinal"])

            records_before = list(current.get("records") or [])
            records_after = [*records_before, source_record]
            current_version = current.get("version") or 1
            version_filter: dict[str, Any]
            if "version" in current:
                version_filter = {"version": current.get("version")}
            else:
                version_filter = {"version": {"$exists": False}}

            result = await db.attendance.update_one(
                {
                    "id": target_id,
                    "mantenedora_id": tenant_id,
                    **version_filter,
                    "records.student_id": {"$ne": student_id},
                },
                {
                    "$set": {
                        "records": records_after,
                        "version": current_version + 1,
                        "updated_at": _now(),
                        "updated_by": actor.get("id"),
                    }
                },
            )
            if result.matched_count != 1:
                raise OrdinalAttendanceError(
                    "ORDINAL_TARGET_CAS_CONFLICT",
                    "A aula de destino mudou durante a migração ordinal.",
                    detail={"target_attendance_id": target_id},
                )

            after = await db.attendance.find_one(
                {"id": target_id, "mantenedora_id": tenant_id}, {"_id": 0}
            )
            matches = [r for r in (after.get("records") or []) if str(r.get("student_id")) == student_id]
            if len(matches) != 1 or matches[0].get("status") != source_record.get("status"):
                raise OrdinalAttendanceError(
                    "ORDINAL_TARGET_POSTCONDITION_FAILED",
                    "A frequência ordinal não foi materializada corretamente.",
                    detail={"target_attendance_id": target_id},
                )

            await db[ORDINAL_LEDGER_COLLECTION].update_one(
                ledger_key,
                {
                    "$setOnInsert": {
                        **ledger_key,
                        "state": "APPLIED",
                        "source_attendance_id": source.get("source_attendance_id"),
                        "source_date": source.get("source_date"),
                        "source_course_id": source.get("source_course_id"),
                        "target_course_id": component["target_course_id"],
                        "ordinal": int(pair["ordinal"]),
                        "status": source_record.get("status"),
                        "target_document_before": before,
                        "target_document_hash_before": _digest(before),
                        "target_document_hash_after": _digest(after),
                        "requires_revalidation": requires_revalidation,
                        "applied_at": _now(),
                        "created_by": actor.get("id"),
                    }
                },
                upsert=True,
            )
            applied += 1

    summary = {
        **plan["totals"],
        "applied": applied,
        "revalidation_pending": revalidation_pending,
        "ignored_excess_policy": "IGNORE_EXCESS_SOURCE_RECORDS",
    }
    if audit_service is not None:
        await audit_service.log(
            action="rectify_attendance_ordinal",
            collection="attendance",
            user=dict(actor),
            request=request,
            document_id=student_id,
            description=f"F2.3D migração ordinal de frequência — protocolo {protocol}",
            academic_year=academic_year,
            extra_data={
                "protocol": protocol,
                "source_class_id": source_class_id,
                "target_class_id": target_class_id,
                **summary,
            },
        )
    return {"contract_version": "F2.3D", "state": "APPLIED", "summary": summary, "components": plan["components"]}
