"""Guards puros da Ficha Individual de Urgências.

Não importa FastAPI/ReportLab/Mongo. O objetivo é impedir regressões arquiteturais:
- a contingência não pode escrever nas coleções acadêmicas;
- a única escrita admitida é a trilha independente manual_document_issuances;
- o gerador oficial deve ser reutilizado de forma isolada, sem monkeypatch global;
- frontend e Dashboard devem manter as rotas/avisos essenciais.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROUTER = ROOT / "backend" / "routers" / "manual_ficha_individual.py"
ROUTERS_INIT = ROOT / "backend" / "routers" / "__init__.py"
DASHBOARD = ROOT / "frontend" / "src" / "pages" / "Dashboard.js"
APP = ROOT / "frontend" / "src" / "App.js"
FORM = ROOT / "frontend" / "src" / "pages" / "UrgenciaFichaIndividual.jsx"

PROTECTED_COLLECTIONS = {
    "grades",
    "attendance",
    "students",
    "enrollments",
    "student_history",
}
WRITE_METHODS = {
    "insert_one", "insert_many",
    "update_one", "update_many",
    "replace_one",
    "delete_one", "delete_many",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collection_for_call(node: ast.Call) -> tuple[str | None, str | None]:
    """Retorna (coleção, método) para db.collection.write_method(...)."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in WRITE_METHODS:
        return None, None
    owner = func.value
    if isinstance(owner, ast.Attribute):
        return owner.attr, func.attr
    if isinstance(owner, ast.Subscript):
        slice_node = owner.slice
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            return slice_node.value, func.attr
    return None, func.attr


def test_manual_router_never_writes_academic_collections():
    tree = ast.parse(_source(BACKEND_ROUTER))
    writes: list[tuple[str | None, str | None, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            collection, method = _collection_for_call(node)
            if method:
                writes.append((collection, method, node.lineno))

    forbidden = [w for w in writes if w[0] in PROTECTED_COLLECTIONS]
    assert forbidden == [], f"Escrita acadêmica proibida detectada: {forbidden}"

    allowed = [(c, m) for c, m, _ in writes]
    assert allowed == [("manual_document_issuances", "insert_one")], (
        "A Ficha de Urgências deve escrever somente a trilha documental independente; "
        f"encontrado: {allowed}"
    )


def test_manual_router_reuses_official_pdf_without_global_monkeypatch():
    source = _source(BACKEND_ROUTER)
    assert "ficha_individual_module.generate_ficha_individual_pdf" in source
    assert "types.FunctionType" in source
    assert "isolated_globals = dict(original.__globals__)" in source
    assert "isolated_globals[\"determinar_resultado_documento\"]" in source
    assert "isolated_globals[\"date\"]" in source

    # Não permitir atribuição direta aos globals do módulo oficial.
    assert "ficha_individual_module.determinar_resultado_documento =" not in source
    assert "ficha_individual_module.date =" not in source


def test_manual_routes_are_attached_to_existing_documents_router():
    router_source = _source(BACKEND_ROUTER)
    init_source = _source(ROUTERS_INIT)
    assert '@router.get("/documents/ficha-individual-manual/preview")' in router_source
    assert '@router.post("/documents/ficha-individual-manual")' in router_source
    assert "_documents_module.router.include_router(manual_router)" in init_source


def test_frontend_routes_and_dashboard_entry_exist():
    app = _source(APP)
    dashboard = _source(DASHBOARD)
    form = _source(FORM)

    assert "const Urgencias = lazy(() => import('@/pages/Urgencias'))" in app
    assert "const UrgenciaFichaIndividual = lazy(() => import('@/pages/UrgenciaFichaIndividual'))" in app
    assert 'path="/admin/urgencias"' in app
    assert 'path="/admin/urgencias/ficha-individual"' in app
    assert "label: 'Urgências'" in dashboard
    assert "testId: 'nav-urgencias-button'" in dashboard

    # Aviso visível de que a ferramenta não altera registros acadêmicos.
    assert "não substituem nem alteram Notas, Frequência, Matrícula ou Histórico acadêmico" in form
    assert "responseType: 'blob'" in form
