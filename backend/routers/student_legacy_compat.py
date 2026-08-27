"""Compatibilidade P0 para documentos legados de estudantes.

O cadastro histórico do SIGESC possui estudantes anteriores ao endereço
estruturado. Nesses documentos, ``address`` é uma string (logradouro/localidade)
e os demais componentes permanecem em campos planos como ``address_number``,
``neighborhood``, ``city`` e ``state``. O modelo atual ``Student`` exige um
``StudentAddress`` e, sem compatibilidade, GET/PUT podem terminar em
``ValidationError`` depois de a autorização (e até a escrita) já ter ocorrido.

Esta camada é deliberadamente NÃO persistente:
- nunca escreve no MongoDB;
- reconstrói o endereço apenas na resposta em memória;
- preserva todos os componentes legados conhecidos;
- normaliza somente Literals semanticamente inequívocos encontrados no censo;
- não converte comunidade tradicional vazia em ``nao_pertence``;
- não mascara erros Pydantic fora do conjunto legado auditado.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import Request
from pydantic import ValidationError

from auth_middleware import AuthMiddleware
from models import Student, StudentUpdate


_GET_PATH = "/students/{student_id}"
_PUT_PATH = "/students/{student_id}"
_CANCEL_TRANSFER_PATH = "/students/{student_id}/cancel-transfer"

_COMPAT_ERROR_ROOTS = frozenset({
    "address",
    "civil_certificate_type",
    "comunidade_tradicional",
})

_CERTIFICATE_TYPES = frozenset({"nascimento", "casamento"})


def normalize_legacy_student_doc(doc: dict | None) -> dict | None:
    """Projeta um documento legado para o contrato atual sem persistir nada.

    ``address`` histórico corresponde ao antigo campo de logradouro/localidade,
    pois coexistia no mesmo documento com número, complemento, bairro, cidade e
    UF. Esses componentes são apenas reagrupados em ``StudentAddress``.
    """
    if doc is None:
        return None
    if not isinstance(doc, dict):
        raise TypeError("Documento de estudante deve ser dict ou None")

    normalized = dict(doc)
    raw_address = normalized.get("address")

    if isinstance(raw_address, str):
        normalized["address"] = {
            "zip_code": normalized.get("zip_code"),
            "state": normalized.get("state"),
            "state_ibge_code": normalized.get("state_ibge_code"),
            "city": normalized.get("city"),
            "city_ibge_code": normalized.get("city_ibge_code"),
            "neighborhood": normalized.get("neighborhood"),
            "street": raw_address.strip() or None,
            "number": normalized.get("address_number"),
            "complement": normalized.get("address_complement"),
            "geographic_location": normalized.get("geographic_location"),
            "differentiated_location": normalized.get("differentiated_location"),
        }

    certificate_type = normalized.get("civil_certificate_type")
    if isinstance(certificate_type, str):
        stripped = certificate_type.strip()
        lowered = stripped.lower()
        if not stripped:
            normalized["civil_certificate_type"] = None
        elif lowered in _CERTIFICATE_TYPES:
            normalized["civil_certificate_type"] = lowered

    traditional_community = normalized.get("comunidade_tradicional")
    if isinstance(traditional_community, str) and not traditional_community.strip():
        # Vazio significa "não informado". Não reinterpretar como nao_pertence.
        normalized["comunidade_tradicional"] = None

    return normalized


def is_legacy_compat_validation_error(exc: ValidationError) -> bool:
    """Aceita fallback somente quando TODOS os erros são do legado auditado."""
    errors = exc.errors()
    if not errors:
        return False

    for error in errors:
        loc = error.get("loc") or ()
        root = str(loc[0]) if loc else ""
        if root not in _COMPAT_ERROR_ROOTS:
            return False
    return True


def build_compatible_student(doc: dict) -> Student:
    """Constrói o Student atual a partir da projeção compatível em memória."""
    return Student.model_validate(normalize_legacy_student_doc(doc))


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


def _db_for_user(db, sandbox_db, current_user: dict):
    if current_user.get("is_sandbox"):
        return sandbox_db if sandbox_db is not None else db
    return db


async def _reload_compatible_student(db, sandbox_db, request: Request, student_id: str):
    current_user = await AuthMiddleware.get_current_user(request)
    current_db = _db_for_user(db, sandbox_db, current_user)
    doc = await current_db.students.find_one({"id": student_id}, {"_id": 0})
    if doc is None:
        return None
    return build_compatible_student(doc)


def install_student_legacy_compat(base_router: Any, db, sandbox_db=None):
    """Instala fallback de serialização nas rotas que materializam ``Student``.

    O endpoint original sempre roda primeiro. Logo, autenticação, autorização,
    multi-tenancy e regras de negócio permanecem exatamente as mesmas. Só quando
    ele termina em ``ValidationError`` exclusivamente dos campos legados
    auditados recarregamos o documento e projetamos a resposta compatível.
    """
    if getattr(base_router, "_student_legacy_compat_installed", False):
        return base_router

    current_get = _remove_route(base_router, _GET_PATH, "GET")
    current_put = _remove_route(base_router, _PUT_PATH, "PUT")
    current_cancel = _remove_route(base_router, _CANCEL_TRANSFER_PATH, "POST")

    if current_get is None or current_put is None or current_cancel is None:
        raise RuntimeError(
            "Student Legacy Compat não pôde ser instalado: rotas esperadas ausentes."
        )

    @base_router.get("/{student_id}", response_model=Student)
    @wraps(current_get)
    async def compatible_get_student(student_id: str, request: Request):
        try:
            return await current_get(student_id, request)
        except ValidationError as exc:
            if not is_legacy_compat_validation_error(exc):
                raise
            student = await _reload_compatible_student(
                db, sandbox_db, request, student_id
            )
            if student is None:
                raise
            return student

    @base_router.put("/{student_id}", response_model=Student)
    @wraps(current_put)
    async def compatible_update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        try:
            return await current_put(student_id, student_update, request)
        except ValidationError as exc:
            if not is_legacy_compat_validation_error(exc):
                raise
            student = await _reload_compatible_student(
                db, sandbox_db, request, student_id
            )
            if student is None:
                raise
            return student

    @base_router.post("/{student_id}/cancel-transfer")
    @wraps(current_cancel)
    async def compatible_cancel_transfer(student_id: str, request: Request):
        try:
            return await current_cancel(student_id, request)
        except ValidationError as exc:
            if not is_legacy_compat_validation_error(exc):
                raise
            student = await _reload_compatible_student(
                db, sandbox_db, request, student_id
            )
            if student is None:
                raise
            return {
                "message": (
                    "Transferência cancelada com sucesso. "
                    "Estudante restaurado na turma de origem."
                ),
                "student": student.model_dump(),
                "class_id": student.class_id,
                "school_id": student.school_id,
            }

    setattr(base_router, "_student_legacy_compat_installed", True)
    return base_router
