"""Fase 1 — continuidade do número institucional nas movimentações do estudante.

Objetivo:
- preservar o MESMO número institucional em remanejamento com fallback legado,
  rematrícula/retorno e transferência entre escolas;
- manter ``enrollments`` como fonte canônica quando há um único número histórico;
- não confiar cegamente em ``students.enrollment_number`` quando ele diverge;
- bloquear históricos ambíguos ou quando o log original confirma outro número;
- reutilizar o endpoint legado, preservando permissões, validações, histórico e
  consolidação pedagógica já existentes.

A integração usa ``utils.enrollment.enrollment_number_override_once``. O resolvedor
só é executado quando o endpoint, já autorizado e validado, chega ao ponto real de
geração de número. Nesse instante, se houver identidade institucional reutilizável,
o número é liberado do vínculo histórico (para respeitar o índice único) e devolvido
ao fluxo legado. Se não existir identidade anterior, o gerador atômico normal segue.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import logging
import re
from typing import Any, Optional

from fastapi import HTTPException, Request, status

from auth_middleware import AuthMiddleware
from models import Student, StudentUpdate
from utils.enrollment import enrollment_number_override_once


logger = logging.getLogger(__name__)

UPDATE_ROUTE_PATH = "/students/{student_id}"
TRANSFER_ROUTE_PATH = "/students/{student_id}/transfer"

SPECIAL_PROGRAMS = frozenset({
    "aee",
    "recomposicao_aprendizagem",
    "reforco_escolar",
})

_MATRICULA_RX = re.compile(r"matr[ií]cula:\s*(\d+)", re.IGNORECASE)


class EnrollmentIdentityContinuityConflict(Exception):
    """A identidade institucional não pode ser escolhida com segurança."""


@dataclass
class IdentityDecision:
    student_id: str
    number: str
    basis: str
    student_number_before: str
    target_class_id: str
    academic_year: int
    source_enrollment_id: Optional[str] = None
    source_status: Optional[str] = None
    source_previous_number: Optional[str] = None
    source_previous_present: bool = False
    released: bool = False


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _payload(model: StudentUpdate) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)  # pragma: no cover - Pydantic v1


def choose_identity_number(
    *,
    student_number: str,
    enrollment_numbers: set[str],
    logged_number: str,
) -> tuple[Optional[str], str]:
    """Escolhe a identidade com regras explícitas e fail-closed.

    Política:
    - múltiplos números distintos em enrollments => ambiguidade, bloqueia;
    - um único número em enrollments é canônico;
    - se o log original existe e confirma outro número, bloqueia em vez de
      perpetuar uma identidade possivelmente errada;
    - sem número em enrollments, usa students somente se o log não o contradiz;
    - sem qualquer identidade anterior, retorna ``None`` para gerar número novo.
    """

    student_number = _norm(student_number)
    logged_number = _norm(logged_number)
    enrollment_numbers = {_norm(n) for n in enrollment_numbers if _norm(n)}

    if len(enrollment_numbers) > 1:
        raise EnrollmentIdentityContinuityConflict(
            "Histórico possui múltiplos números de matrícula distintos. "
            "A movimentação foi bloqueada para revisão individual."
        )

    if enrollment_numbers:
        canonical = next(iter(enrollment_numbers))
        if logged_number:
            if logged_number == canonical:
                return canonical, "LOG_ORIGINAL_CONFIRMA_ENROLLMENT"
            if student_number and logged_number == student_number:
                raise EnrollmentIdentityContinuityConflict(
                    "O log original confirma students.enrollment_number, mas a "
                    "matrícula canônica contém outro número. Revise a identidade "
                    "antes da movimentação."
                )
            raise EnrollmentIdentityContinuityConflict(
                "O log original registra um terceiro número de matrícula. "
                "A identidade histórica precisa de reconciliação antes da movimentação."
            )
        return canonical, "ENROLLMENT_CANONICO_SEM_LOG"

    if student_number:
        if logged_number and logged_number != student_number:
            raise EnrollmentIdentityContinuityConflict(
                "O número existente em students é contradito pelo log original. "
                "Revise a identidade antes da movimentação."
            )
        return student_number, (
            "LOG_ORIGINAL_CONFIRMA_STUDENT_ONLY" if logged_number else "STUDENT_ONLY"
        )

    if logged_number:
        # Não reintroduz automaticamente número que só existe em texto histórico.
        raise EnrollmentIdentityContinuityConflict(
            "Existe número apenas no log histórico, sem correspondente atual em "
            "students/enrollments. Revise o caso antes da movimentação."
        )

    return None, "SEM_IDENTIDADE_ANTERIOR"


async def _first_logged_enrollment_number(db, student_id: str) -> str:
    cursor = db.audit_logs.find(
        {
            "collection": "students",
            "document_id": student_id,
            "extra_data.action_type": "matricula",
        },
        {"_id": 0, "timestamp": 1, "extra_data": 1},
    ).sort("timestamp", 1)

    async for log in cursor:
        observations = _norm((log.get("extra_data") or {}).get("observations"))
        match = _MATRICULA_RX.search(observations)
        if match:
            return match.group(1)
    return ""


async def _regular_enrollments(db, student_id: str) -> list[dict]:
    docs = await db.enrollments.find(
        {"student_id": student_id}, {"_id": 0}
    ).to_list(length=1000)

    class_ids = sorted({_norm(e.get("class_id")) for e in docs if _norm(e.get("class_id"))})
    classes = {}
    if class_ids:
        async for class_doc in db.classes.find(
            {"id": {"$in": class_ids}},
            {"_id": 0, "id": 1, "atendimento_programa": 1},
        ):
            classes[class_doc["id"]] = class_doc

    regular = []
    for enrollment in docs:
        class_id = _norm(enrollment.get("class_id"))
        class_doc = classes.get(class_id)
        if not class_doc:
            if _norm(enrollment.get("enrollment_number")) or _norm(
                enrollment.get("previous_enrollment_number")
            ):
                raise EnrollmentIdentityContinuityConflict(
                    "Há matrícula numerada apontando para turma inexistente. "
                    "Saneie o vínculo antes da movimentação."
                )
            continue
        program = _norm(class_doc.get("atendimento_programa")).lower()
        if program not in SPECIAL_PROGRAMS:
            regular.append(enrollment)
    return regular


async def _assert_number_owned_only_by_student(db, student_id: str, number: str) -> None:
    other_student = await db.students.find_one(
        {"id": {"$ne": student_id}, "enrollment_number": number},
        {"_id": 0, "id": 1, "full_name": 1},
    )
    if other_student:
        raise EnrollmentIdentityContinuityConflict(
            f"O número institucional {number} está em uso por outro estudante "
            f"({other_student.get('full_name') or other_student.get('id')})."
        )

    other_enrollment = await db.enrollments.find_one(
        {
            "student_id": {"$ne": student_id},
            "$or": [
                {"enrollment_number": number},
                {"previous_enrollment_number": number},
            ],
        },
        {"_id": 0, "id": 1, "student_id": 1},
    )
    if other_enrollment:
        raise EnrollmentIdentityContinuityConflict(
            f"O número institucional {number} aparece no histórico de outro estudante. "
            "A movimentação foi bloqueada por segurança."
        )


async def resolve_and_prepare_identity_handoff(
    db,
    *,
    student_id: str,
    target_class_id: Optional[str],
    academic_year: int,
) -> Optional[IdentityDecision]:
    """Resolve a identidade e libera, se necessário, o vínculo histórico atual.

    Esta função é chamada de dentro do gerador contextual, portanto somente após
    o endpoint legado alcançar seu ponto autorizado/validado de criação do vínculo.
    """

    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise EnrollmentIdentityContinuityConflict("Estudante não encontrado.")

    effective_class_id = _norm(target_class_id) or _norm(student.get("class_id"))
    if not effective_class_id:
        raise EnrollmentIdentityContinuityConflict(
            "Não foi possível determinar a turma de destino da movimentação."
        )

    target_class = await db.classes.find_one(
        {"id": effective_class_id},
        {"_id": 0, "id": 1, "atendimento_programa": 1},
    )
    if not target_class:
        raise EnrollmentIdentityContinuityConflict("Turma de destino inexistente.")

    target_program = _norm(target_class.get("atendimento_programa")).lower()
    if target_program in SPECIAL_PROGRAMS:
        raise EnrollmentIdentityContinuityConflict(
            "Rematrícula/transferência da turma regular não pode usar turma de "
            "programa especial como destino. Efetive primeiro a matrícula regular."
        )

    regular = await _regular_enrollments(db, student_id)
    enrollment_numbers: set[str] = set()
    for enrollment in regular:
        current = _norm(enrollment.get("enrollment_number"))
        previous = _norm(enrollment.get("previous_enrollment_number"))
        if current:
            enrollment_numbers.add(current)
        if previous:
            enrollment_numbers.add(previous)

    student_number = _norm(student.get("enrollment_number"))
    logged_number = await _first_logged_enrollment_number(db, student_id)
    number, basis = choose_identity_number(
        student_number=student_number,
        enrollment_numbers=enrollment_numbers,
        logged_number=logged_number,
    )

    if not number:
        return None

    await _assert_number_owned_only_by_student(db, student_id, number)

    holders = [e for e in regular if _norm(e.get("enrollment_number")) == number]
    if len(holders) > 1:
        raise EnrollmentIdentityContinuityConflict(
            "Mais de um vínculo do mesmo estudante mantém o número no campo ativo. "
            "Saneie a duplicidade antes da movimentação."
        )

    source = holders[0] if holders else None
    if source and _norm(source.get("status")).lower() == "active":
        raise EnrollmentIdentityContinuityConflict(
            "Existe matrícula regular ativa ainda retendo o número institucional. "
            "Encerre/corrija o vínculo antes de criar outro."
        )

    decision = IdentityDecision(
        student_id=student_id,
        number=number,
        basis=basis,
        student_number_before=student_number,
        target_class_id=effective_class_id,
        academic_year=int(academic_year),
        source_enrollment_id=source.get("id") if source else None,
        source_status=source.get("status") if source else None,
        source_previous_number=(source.get("previous_enrollment_number") if source else None),
        source_previous_present=("previous_enrollment_number" in source if source else False),
    )

    if source:
        result = await db.enrollments.update_one(
            {
                "id": source.get("id"),
                "student_id": student_id,
                "status": source.get("status"),
                "enrollment_number": number,
            },
            {
                "$set": {
                    "enrollment_number": "",
                    "previous_enrollment_number": number,
                }
            },
        )
        if getattr(result, "matched_count", 0) != 1:
            raise EnrollmentIdentityContinuityConflict(
                "O vínculo histórico mudou durante a movimentação. Recarregue e tente novamente."
            )
        decision.released = True

    return decision


async def _rollback_release_if_safe(db, decision: Optional[IdentityDecision]) -> None:
    if not decision or not decision.released or not decision.source_enrollment_id:
        return

    # Se o número já foi consumido por um novo vínculo, restaurar a origem
    # violaria o índice único. Nesse caso, preserva o handoff realizado.
    holder = await db.enrollments.find_one(
        {"enrollment_number": decision.number}, {"_id": 0, "id": 1}
    )
    if holder and holder.get("id") != decision.source_enrollment_id:
        return
    if holder and holder.get("id") == decision.source_enrollment_id:
        return

    update = {"$set": {"enrollment_number": decision.number}}
    if decision.source_previous_present:
        update["$set"]["previous_enrollment_number"] = decision.source_previous_number
    else:
        update["$unset"] = {"previous_enrollment_number": ""}

    await db.enrollments.update_one(
        {
            "id": decision.source_enrollment_id,
            "enrollment_number": "",
            "previous_enrollment_number": decision.number,
        },
        update,
    )


async def _finalize_projection_and_audit(
    db,
    audit_service,
    request: Request,
    decision: Optional[IdentityDecision],
) -> None:
    if not decision:
        return

    current = await db.students.find_one(
        {"id": decision.student_id},
        {"_id": 0, "enrollment_number": 1, "school_id": 1, "full_name": 1},
    )
    if not current:
        return

    current_number = _norm(current.get("enrollment_number"))
    projection_changed = False
    if current_number != decision.number:
        result = await db.students.update_one(
            {"id": decision.student_id, "enrollment_number": current.get("enrollment_number")},
            {"$set": {"enrollment_number": decision.number}},
        )
        projection_changed = bool(getattr(result, "modified_count", 0))

    try:
        current_user = await AuthMiddleware.get_current_user(request)
        if decision.released:
            await audit_service.log(
                action="update",
                collection="enrollments",
                user=current_user,
                request=request,
                document_id=decision.source_enrollment_id,
                description=(
                    f"Preservou número institucional {decision.number} durante movimentação; "
                    "o vínculo histórico passou a guardar previous_enrollment_number."
                ),
                school_id=current.get("school_id"),
                academic_year=decision.academic_year,
                old_value={"enrollment_number": decision.number},
                new_value={
                    "enrollment_number": "",
                    "previous_enrollment_number": decision.number,
                },
                extra_data={
                    "identity_continuity_basis": decision.basis,
                    "source_status": decision.source_status,
                },
            )
        if projection_changed:
            await audit_service.log(
                action="update",
                collection="students",
                user=current_user,
                request=request,
                document_id=decision.student_id,
                description=(
                    f"Sincronizou projeção do número institucional de "
                    f"{current.get('full_name') or decision.student_id}."
                ),
                school_id=current.get("school_id"),
                old_value={"enrollment_number": current_number or None},
                new_value={"enrollment_number": decision.number},
                extra_data={"identity_continuity_basis": decision.basis},
            )
    except Exception:
        # A movimentação principal já foi concluída e o histórico legado também
        # registra a ação. Falha do log complementar não deve transformar sucesso
        # em HTTP 500 nem induzir repetição da movimentação pelo usuário.
        logger.exception("[enrollment-identity] falha no audit log complementar")


def _remove_route(base_router: Any, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def install_student_enrollment_identity_continuity(base_router: Any, db, audit_service):
    """Envolve PUT de estudantes e POST de transferência com continuidade P1."""
    if getattr(base_router, "_student_enrollment_identity_continuity_installed", False):
        return base_router

    current_update = _remove_route(base_router, UPDATE_ROUTE_PATH, "PUT")
    current_transfer = _remove_route(base_router, TRANSFER_ROUTE_PATH, "POST")
    if current_update is None or current_transfer is None:
        raise RuntimeError(
            "Enrollment Identity Continuity não pôde ser instalada: rotas esperadas ausentes."
        )

    @base_router.put("/{student_id}", response_model=Student)
    @wraps(current_update)
    async def continuity_update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        payload = _payload(student_update)
        target_class_id = payload.get("class_id")
        decision_box: dict[str, Optional[IdentityDecision]] = {"decision": None}

        async def resolver(current_db, academic_year: int) -> Optional[str]:
            decision = await resolve_and_prepare_identity_handoff(
                current_db,
                student_id=student_id,
                target_class_id=target_class_id,
                academic_year=academic_year,
            )
            decision_box["decision"] = decision
            return decision.number if decision else None

        try:
            with enrollment_number_override_once(resolver):
                result = await current_update(student_id, student_update, request)
        except EnrollmentIdentityContinuityConflict as exc:
            await _rollback_release_if_safe(db, decision_box.get("decision"))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception:
            await _rollback_release_if_safe(db, decision_box.get("decision"))
            raise

        await _finalize_projection_and_audit(
            db, audit_service, request, decision_box.get("decision")
        )
        decision = decision_box.get("decision")
        if decision and hasattr(result, "enrollment_number"):
            result.enrollment_number = decision.number
        return result

    @base_router.post("/{student_id}/transfer")
    @wraps(current_transfer)
    async def continuity_transfer_student(student_id: str, request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        target_class_id = body.get("class_id") if isinstance(body, dict) else None
        decision_box: dict[str, Optional[IdentityDecision]] = {"decision": None}

        async def resolver(current_db, academic_year: int) -> Optional[str]:
            decision = await resolve_and_prepare_identity_handoff(
                current_db,
                student_id=student_id,
                target_class_id=target_class_id,
                academic_year=academic_year,
            )
            decision_box["decision"] = decision
            return decision.number if decision else None

        try:
            with enrollment_number_override_once(resolver):
                result = await current_transfer(student_id, request)
        except EnrollmentIdentityContinuityConflict as exc:
            await _rollback_release_if_safe(db, decision_box.get("decision"))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except Exception:
            await _rollback_release_if_safe(db, decision_box.get("decision"))
            raise

        await _finalize_projection_and_audit(
            db, audit_service, request, decision_box.get("decision")
        )
        decision = decision_box.get("decision")
        if decision and isinstance(result, dict):
            student_payload = result.get("student")
            if isinstance(student_payload, dict):
                student_payload["enrollment_number"] = decision.number
            enrollment_payload = result.get("enrollment")
            if isinstance(enrollment_payload, dict):
                enrollment_payload["enrollment_number"] = decision.number
        return result

    setattr(base_router, "_student_enrollment_identity_continuity_installed", True)
    return base_router
