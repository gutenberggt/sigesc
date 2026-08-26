"""P0 Auth — impede server.py de ignorar o bootstrap do Modo de Teste."""

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SERVER = (BACKEND / "server.py").read_text(encoding="utf-8")
ROUTERS_INIT = (BACKEND / "routers" / "__init__.py").read_text(encoding="utf-8")


def test_server_importa_setup_auth_wrapped_do_pacote_routers():
    assert "setup_auth_router," in SERVER.split("from routers import (", 1)[1].split(")", 1)[0]
    assert "from routers.auth import setup_router as setup_auth_router" not in SERVER


def test_wrapper_auth_instala_modo_de_teste_e_busca_global():
    block = ROUTERS_INIT.split("def setup_auth_router", 1)[1].split("def setup_students_router", 1)[0]
    assert "install_auth_impersonation(configured, db, audit_service)" in block
    assert "install_auth_impersonation_search(configured, db)" in block
    assert "install_impersonation_request_audit_policy(audit_service)" in block


def test_server_registra_router_auth_resultante_do_wrapper():
    assert "auth_router = setup_auth_router(db, audit_service)" in SERVER
    assert "app.include_router(auth_router, prefix=\"/api\")" in SERVER
