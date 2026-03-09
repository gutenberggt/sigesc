"""
Router para endpoints de Sandbox (modo teste).
Extraído de server.py durante a refatoração modular.
"""

from fastapi import APIRouter, HTTPException, status, Request

from auth_middleware import AuthMiddleware

router = APIRouter(tags=["Sandbox"])


def setup_router(sandbox_service=None, **kwargs):
    """Configura o router com dependências."""

    @router.get("/sandbox/status")
    async def get_sandbox_status(request: Request):
        """Retorna o status do banco sandbox (apenas admin)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)
        return sandbox_service.get_status()

    @router.post("/sandbox/reset")
    async def reset_sandbox_manual(request: Request):
        """Reseta o banco sandbox manualmente (apenas admin)"""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)
        result = await sandbox_service.reset_sandbox()
        if not result.get('success'):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get('error', 'Erro ao resetar sandbox')
            )
        return result

    return router
