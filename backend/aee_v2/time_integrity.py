"""P0 — integridade temporal dos horários do AEE.

Impede novos horários impossíveis/invertidos sem reescrever o histórico.
O router legado permanece intacto: esta camada envolve apenas criação/edição de
Planos e Atendimentos AEE e valida os pares horario_inicio/horario_fim antes da
persistência.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import inspect
import re
from typing import Any, Mapping, Optional, get_type_hints

from fastapi import HTTPException


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
MIN_OPERATIONAL_MINUTES = 6 * 60
MAX_OPERATIONAL_MINUTES = 22 * 60
SUSPICIOUS_DURATION_MINUTES = 4 * 60


@dataclass(frozen=True)
class AEETimeValidationError(ValueError):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def parse_hhmm(value: Any, *, field: str) -> int:
    text = str(value or "").strip()
    if not _TIME_RE.fullmatch(text):
        raise AEETimeValidationError(
            "AEE_TIME_FORMAT_INVALID",
            f"{field} deve estar no formato HH:MM (00:00 a 23:59).",
        )
    hour, minute = map(int, text.split(":"))
    return hour * 60 + minute


def validate_time_interval(
    start: Any,
    end: Any,
    *,
    require_pair: bool = False,
    enforce_operational_window: bool = True,
) -> Optional[int]:
    """Valida um intervalo AEE de mesmo dia e devolve duração em minutos."""

    start_text = str(start or "").strip()
    end_text = str(end or "").strip()

    if not start_text and not end_text:
        if require_pair:
            raise AEETimeValidationError(
                "AEE_TIME_PAIR_REQUIRED",
                "Informe horário inicial e horário final do atendimento.",
            )
        return None

    if not start_text or not end_text:
        raise AEETimeValidationError(
            "AEE_TIME_PAIR_INCOMPLETE",
            "Horário inicial e horário final devem ser informados juntos.",
        )

    start_min = parse_hhmm(start_text, field="horario_inicio")
    end_min = parse_hhmm(end_text, field="horario_fim")

    if enforce_operational_window:
        if start_min < MIN_OPERATIONAL_MINUTES or start_min > MAX_OPERATIONAL_MINUTES:
            raise AEETimeValidationError(
                "AEE_TIME_START_OUTSIDE_WINDOW",
                "Horário inicial do AEE deve estar entre 06:00 e 22:00.",
            )
        if end_min < MIN_OPERATIONAL_MINUTES or end_min > MAX_OPERATIONAL_MINUTES:
            raise AEETimeValidationError(
                "AEE_TIME_END_OUTSIDE_WINDOW",
                "Horário final do AEE deve estar entre 06:00 e 22:00.",
            )

    if end_min <= start_min:
        raise AEETimeValidationError(
            "AEE_TIME_END_NOT_AFTER_START",
            "Horário final deve ser posterior ao horário inicial no mesmo dia.",
        )

    return end_min - start_min


def classify_time_interval(start: Any, end: Any, *, stored_duration: Any = None) -> dict:
    """Classificação read-only usada pelo auditor de dados existentes."""

    issues: list[dict] = []
    start_text = str(start or "").strip()
    end_text = str(end or "").strip()

    if not start_text and not end_text:
        return {"duration_minutes": None, "issues": []}

    if not start_text or not end_text:
        issues.append({"code": "AEE_TIME_PAIR_INCOMPLETE"})
        return {"duration_minutes": None, "issues": issues}

    try:
        start_min = parse_hhmm(start_text, field="horario_inicio")
    except AEETimeValidationError as exc:
        issues.append({"code": exc.code, "field": "horario_inicio", "value": start_text})
        start_min = None

    try:
        end_min = parse_hhmm(end_text, field="horario_fim")
    except AEETimeValidationError as exc:
        issues.append({"code": exc.code, "field": "horario_fim", "value": end_text})
        end_min = None

    if start_min is None or end_min is None:
        return {"duration_minutes": None, "issues": issues}

    if start_min < MIN_OPERATIONAL_MINUTES or start_min > MAX_OPERATIONAL_MINUTES:
        issues.append({"code": "AEE_TIME_START_OUTSIDE_WINDOW", "value": start_text})
    if end_min < MIN_OPERATIONAL_MINUTES or end_min > MAX_OPERATIONAL_MINUTES:
        issues.append({"code": "AEE_TIME_END_OUTSIDE_WINDOW", "value": end_text})

    duration = end_min - start_min
    if duration <= 0:
        issues.append({"code": "AEE_TIME_END_NOT_AFTER_START"})
        duration_value = None
    else:
        duration_value = duration
        if duration > SUSPICIOUS_DURATION_MINUTES:
            issues.append({"code": "AEE_TIME_DURATION_SUSPICIOUS", "minutes": duration})

    if stored_duration is not None and duration_value is not None:
        try:
            stored = int(stored_duration)
        except (TypeError, ValueError):
            issues.append({"code": "AEE_TIME_STORED_DURATION_INVALID", "value": stored_duration})
        else:
            if stored != duration_value:
                issues.append(
                    {
                        "code": "AEE_TIME_STORED_DURATION_MISMATCH",
                        "stored_minutes": stored,
                        "expected_minutes": duration_value,
                    }
                )

    return {"duration_minutes": duration_value, "issues": issues}


def _route_for(base_router, path: str, method: str):
    matches = [
        route
        for route in base_router.routes
        if getattr(route, "path", None) == path
        and method.upper() in (getattr(route, "methods", set()) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"AEE Time Integrity esperava uma rota {method.upper()} {path}; encontrou {len(matches)}."
        )
    return matches[0]


def _resolved_endpoint_signature(endpoint) -> inspect.Signature:
    """Materializa annotations adiadas antes do clone feito por include_router().

    FastAPI 0.110.1 recria a APIRoute ao executar ``include_router``. Wrappers
    criados em outro módulo mantêm, via ``@wraps``, annotations como strings,
    mas o namespace do wrapper não contém necessariamente os modelos/Request do
    endpoint original. Sem uma ``__signature__`` concreta, body e Request podem
    ser reclassificados como query params na rota final.
    """

    signature = inspect.signature(endpoint)
    source = inspect.unwrap(endpoint)
    source_globals = getattr(source, "__globals__", {}) or {}

    try:
        hints = get_type_hints(source, globalns=source_globals, localns=source_globals)
    except Exception as exc:
        unresolved = [
            name
            for name, parameter in signature.parameters.items()
            if isinstance(parameter.annotation, str)
        ]
        if unresolved:
            raise RuntimeError(
                "AEE Time Integrity não conseguiu resolver annotations da rota: "
                + ", ".join(unresolved)
            ) from exc
        return signature

    parameters = [
        parameter.replace(annotation=hints.get(name, parameter.annotation))
        for name, parameter in signature.parameters.items()
    ]
    resolved = signature.replace(
        parameters=parameters,
        return_annotation=hints.get("return", signature.return_annotation),
    )
    unresolved = [
        name
        for name, parameter in resolved.parameters.items()
        if isinstance(parameter.annotation, str)
    ]
    if unresolved:
        raise RuntimeError(
            "AEE Time Integrity preservou annotations não resolvidas na rota: "
            + ", ".join(unresolved)
        )
    return resolved


def _payload_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_unset=True)
    return {}


def _find_body(bound_arguments: Mapping[str, Any], preferred_names: tuple[str, ...]) -> dict:
    for name in preferred_names:
        if name in bound_arguments:
            payload = _payload_dict(bound_arguments[name])
            if payload:
                return payload
    for value in bound_arguments.values():
        payload = _payload_dict(value)
        if "horario_inicio" in payload or "horario_fim" in payload:
            return payload
    return {}


def _raise_http(exc: AEETimeValidationError) -> None:
    raise HTTPException(status_code=422, detail=f"{exc.message} [{exc.code}]") from exc


def _wrap_time_route(
    base_router,
    db,
    *,
    path: str,
    method: str,
    body_names: tuple[str, ...],
    collection_name: str,
    id_argument: Optional[str] = None,
):
    route = _route_for(base_router, path, method)
    current = route.endpoint
    signature = _resolved_endpoint_signature(current)

    @wraps(current)
    async def guarded(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        payload = _find_body(bound.arguments, body_names)
        touches_time = "horario_inicio" in payload or "horario_fim" in payload

        if method.upper() == "POST" or touches_time:
            merged = dict(payload)
            if method.upper() != "POST" and id_argument:
                document_id = bound.arguments.get(id_argument)
                existing = await db[collection_name].find_one(
                    {"id": document_id},
                    {"_id": 0, "horario_inicio": 1, "horario_fim": 1},
                ) or {}
                merged = {
                    "horario_inicio": payload.get("horario_inicio", existing.get("horario_inicio")),
                    "horario_fim": payload.get("horario_fim", existing.get("horario_fim")),
                }

            try:
                validate_time_interval(
                    merged.get("horario_inicio"),
                    merged.get("horario_fim"),
                    require_pair=False,
                )
            except AEETimeValidationError as exc:
                _raise_http(exc)

        return await current(*args, **kwargs)

    setattr(guarded, "__signature__", signature)
    route.endpoint = guarded
    route.dependant.call = guarded


def install_aee_time_integrity(base_router, db):
    """Protege criação/edição de Plano e Atendimento contra horários inválidos."""

    if getattr(base_router, "_aee_time_integrity_installed", False):
        return base_router

    targets = (
        ("/aee/planos", "POST", ("plano_data",), "planos_aee", None),
        ("/aee/planos/{plano_id}", "PUT", ("plano_update",), "planos_aee", "plano_id"),
        ("/aee/atendimentos", "POST", ("atendimento_data",), "atendimentos_aee", None),
        (
            "/aee/atendimentos/{atendimento_id}",
            "PUT",
            ("atendimento_update",),
            "atendimentos_aee",
            "atendimento_id",
        ),
    )

    for path, method, body_names, collection, id_argument in targets:
        _wrap_time_route(
            base_router,
            db,
            path=path,
            method=method,
            body_names=body_names,
            collection_name=collection,
            id_argument=id_argument,
        )

    setattr(base_router, "_aee_time_integrity_installed", True)
    return base_router


def install_aee_time_integrity_setup(aee_module):
    if getattr(aee_module, "_aee_time_integrity_setup_installed", False):
        return

    original_setup = aee_module.setup_aee_router

    def wrapped_setup(db, audit_service):
        configured = original_setup(db, audit_service)
        return install_aee_time_integrity(configured, db)

    aee_module.setup_aee_router = wrapped_setup
    aee_module._aee_time_integrity_setup_installed = True
