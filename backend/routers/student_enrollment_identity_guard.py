"""P0 — protege a identidade numérica da matrícula na edição genérica de estudante.

Contrato:
- ``enrollments`` é a fonte canônica da matrícula regular ativa;
- ``students.enrollment_number`` é apenas uma projeção derivada;
- ``PUT /students/{student_id}`` não pode aceitar um número de matrícula vindo
  do cliente como dado editável;
- a lógica de domínio legada continua podendo definir ``enrollment_number``
  internamente durante remanejamento/rematrícula, depois da sanitização.

A opção por IGNORAR o campo recebido, em vez de responder 4xx, é deliberada:
o frontend atual envia o formulário completo na edição e inclui o número apenas
para exibição (read-only). Rejeitar o payload quebraria edições legítimas dos
cadastros legados que ainda aguardam reconciliação. Ignorar impede nova
mutação indevida sem aplicar qualquer saneamento implícito ao passivo atual.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import Request

from models import Student, StudentUpdate


ROUTE_PATH = "/students/{student_id}"
ROUTE_METHOD = "PUT"


def _remove_route(base_router, path: str, method: str):
    """Remove uma rota existente e devolve seu endpoint original."""
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


def sanitize_student_update(student_update: StudentUpdate) -> StudentUpdate:
    """Retira a projeção derivada enviada pelo cliente, preservando os demais campos.

    A reconstrução do modelo é intencional: o endpoint legado usa
    ``model_dump(exclude_unset=True)``. Apenas atribuir ``None`` manteria o campo
    no ``fields_set`` e poderia apagá-lo; ao reconstruir sem a chave, o campo
    deixa de participar do update genérico.
    """
    if hasattr(student_update, "model_dump"):
        payload = student_update.model_dump(exclude_unset=True)
    else:  # pragma: no cover - compatibilidade defensiva com Pydantic v1
        payload = student_update.dict(exclude_unset=True)

    payload.pop("enrollment_number", None)
    return StudentUpdate(**payload)


def install_student_enrollment_identity_guard(base_router: Any):
    """Envolve somente o PUT genérico de estudantes com a guarda P0."""
    if getattr(base_router, "_student_enrollment_identity_guard_installed", False):
        return base_router

    current_update = _remove_route(base_router, ROUTE_PATH, ROUTE_METHOD)
    if current_update is None:
        raise RuntimeError(
            "Enrollment Identity Guard não pôde ser instalado: "
            f"rota esperada ausente ({ROUTE_METHOD} {ROUTE_PATH})."
        )

    @base_router.put("/{student_id}", response_model=Student)
    @wraps(current_update)
    async def guarded_update_student(
        student_id: str,
        student_update: StudentUpdate,
        request: Request,
    ):
        safe_update = sanitize_student_update(student_update)
        return await current_update(student_id, safe_update, request)

    setattr(base_router, "_student_enrollment_identity_guard_installed", True)
    return base_router