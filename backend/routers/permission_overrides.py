"""
Permission Overrides Router (Apr 2026)

Permite que o super_admin sobrescreva, célula a célula, a visibilidade dos
itens de menu por papel — sem precisar alterar código. Os overrides ficam
em `db.permission_overrides` e são aplicados pelo frontend em cima do
default declarado em `Dashboard.js > DASHBOARD_MENU_GROUPS`.

Schema:
    {
        "item_key": str,    # `testId` único do item (ex.: nav-auditoria-button)
        "role": str,        # papel afetado (ex.: 'admin', 'professor')
        "visible": bool,    # True = força visível, False = força oculto
        "updated_by": str,  # user_id de quem alterou
        "updated_at": str,  # ISO 8601 UTC
    }

Endpoints:
    GET    /api/admin/permissions/overrides      Lista todos (qualquer logado)
    PUT    /api/admin/permissions/override       Upserta um override (super_admin)
    DELETE /api/admin/permissions/override       Remove (reverte ao default) (super_admin)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auth_middleware import AuthMiddleware


class OverridePayload(BaseModel):
    item_key: str
    role: str
    visible: bool


router = APIRouter(tags=["Permissões - Overrides"])


def setup_router(db, audit_service=None, **kwargs):
    """Registra as rotas de overrides de permissão no router compartilhado."""

    def _require_super_admin(user: dict):
        if user.get('role') != 'super_admin':
            raise HTTPException(
                status_code=403,
                detail="Apenas Super Administrador pode editar a Matriz de Permissões"
            )

    @router.get("/admin/permissions/overrides")
    async def list_overrides(request: Request):
        """Lista todos os overrides (qualquer usuário autenticado pode ler;
        o frontend precisa para aplicar a visibilidade real do menu)."""
        await AuthMiddleware.get_current_user(request)
        items = await db.permission_overrides.find(
            {}, {"_id": 0, "item_key": 1, "role": 1, "visible": 1, "updated_at": 1}
        ).to_list(2000)
        return {"items": items, "total": len(items)}

    @router.put("/admin/permissions/override")
    async def upsert_override(payload: OverridePayload, request: Request):
        """Cria ou atualiza um override (item_key, role) → visible."""
        current_user = await AuthMiddleware.get_current_user(request)
        _require_super_admin(current_user)

        item_key = (payload.item_key or '').strip()
        role = (payload.role or '').strip()
        if not item_key or not role:
            raise HTTPException(status_code=400, detail="item_key e role são obrigatórios")

        now = datetime.now(timezone.utc).isoformat()
        update = {
            "item_key": item_key,
            "role": role,
            "visible": bool(payload.visible),
            "updated_by": current_user.get('id'),
            "updated_at": now,
        }
        await db.permission_overrides.update_one(
            {"item_key": item_key, "role": role},
            {"$set": update},
            upsert=True
        )

        if audit_service:
            try:
                await audit_service.log(
                    action='upsert',
                    collection='permission_overrides',
                    user=current_user,
                    request=request,
                    document_id=f"{item_key}:{role}",
                    description=(
                        f"Override de visibilidade: {item_key} × {role} → "
                        f"{'visível' if payload.visible else 'oculto'}"
                    ),
                    new_value=update,
                )
            except Exception:
                pass

        return {"message": "Override aplicado", **update}

    @router.delete("/admin/permissions/override")
    async def delete_override(request: Request, item_key: str, role: str):
        """Remove o override e reverte ao default declarado em Dashboard.js."""
        current_user = await AuthMiddleware.get_current_user(request)
        _require_super_admin(current_user)

        result = await db.permission_overrides.delete_one(
            {"item_key": item_key, "role": role}
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Nenhum override para remover")

        if audit_service:
            try:
                await audit_service.log(
                    action='delete',
                    collection='permission_overrides',
                    user=current_user,
                    request=request,
                    document_id=f"{item_key}:{role}",
                    description=f"Override removido (volta ao default): {item_key} × {role}",
                )
            except Exception:
                pass

        return {"message": "Override removido (revertido ao default)"}
