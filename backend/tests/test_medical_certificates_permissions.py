"""
Teste de permissões para exclusão de atestados médicos.

Valida que os papéis: super_admin, admin, admin_teste, gerente, secretario
podem chamar `delete_certificate`. E que outros papéis (ex: ass_social)
recebem 403.

Não usa DB real — mocka via AsyncMock.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import HTTPException


@pytest.mark.asyncio
async def test_delete_permissions():
    from routers.medical_certificates import setup_medical_certificates_router

    fake_cert = {
        "id": "cert-123",
        "student_id": "stu-1",
    }

    db = MagicMock()
    db.medical_certificates = MagicMock()
    db.medical_certificates.find_one = AsyncMock(return_value=fake_cert)
    db.medical_certificates.delete_one = AsyncMock(return_value=None)
    # Para o caso secretario (busca enrollment + school_assignment)
    db.enrollments = MagicMock()
    db.enrollments.find_one = AsyncMock(return_value={"school_id": "sch-1"})
    db.school_assignments = MagicMock()
    db.school_assignments.find_one = AsyncMock(return_value={"id": "sa-1"})

    # Auth middleware mockado: troca-se o role conforme cada teste
    auth_middleware = MagicMock()

    router = setup_medical_certificates_router(db, auth_middleware)

    # Encontra o handler delete
    delete_route = next(
        r for r in router.routes
        if getattr(r, "path", "") == "/medical-certificates/{certificate_id}"
        and "DELETE" in getattr(r, "methods", set())
    )
    handler = delete_route.endpoint

    request_mock = MagicMock()

    # ------ Roles que DEVEM passar ------
    for role in ("super_admin", "admin", "admin_teste", "gerente"):
        auth_middleware.get_current_user = AsyncMock(
            return_value={"id": "u-1", "email": f"{role}@x.com", "role": role}
        )
        result = await handler(request=request_mock, certificate_id="cert-123")
        assert result.get("message"), f"Role {role} deveria conseguir deletar"

    # ------ Secretario com vínculo de escola: deve passar ------
    auth_middleware.get_current_user = AsyncMock(
        return_value={"id": "u-2", "email": "sec@x.com", "role": "secretario"}
    )
    result = await handler(request=request_mock, certificate_id="cert-123")
    assert result.get("message"), "Secretario com vínculo deveria conseguir deletar"

    # ------ Secretario SEM vínculo de escola: deve dar 403 ------
    db.school_assignments.find_one = AsyncMock(return_value=None)
    auth_middleware.get_current_user = AsyncMock(
        return_value={"id": "u-3", "email": "sec2@x.com", "role": "secretario"}
    )
    with pytest.raises(HTTPException) as exc:
        await handler(request=request_mock, certificate_id="cert-123")
    assert exc.value.status_code == 403

    # ------ Roles que NÃO devem passar ------
    db.school_assignments.find_one = AsyncMock(return_value={"id": "sa-1"})  # restaura
    for role in ("ass_social", "ass_social_2", "professor", "aluno", "agente_vacinas", "diretor"):
        auth_middleware.get_current_user = AsyncMock(
            return_value={"id": "u-x", "email": f"{role}@x.com", "role": role}
        )
        with pytest.raises(HTTPException) as exc:
            await handler(request=request_mock, certificate_id="cert-123")
        assert exc.value.status_code == 403, f"Role {role} deveria dar 403, deu {exc.value.status_code}"
