"""Guards puros da Ficha Individual de Urgências.

Não importa FastAPI/ReportLab/Mongo. O objetivo é impedir regressões arquiteturais:
- a contingência não pode escrever nas coleções acadêmicas;
- a única escrita admitida é a trilha independente manual_document_issuances;
- o gerador oficial deve ser reutilizado por overrides explícitos;
- FunctionType, __globals__ e monkeypatch do gerador oficial são proibidos;
- todas as leituras acadêmicas sensíveis devem respeitar o escopo multi-tenant;
- o router deve ser registrado explicitamente em server.py;
- frontend, Dashboard e aviso de não-mutação devem permanecer presentes.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROUTER = ROOT / "backend" / "routers" / "manual_ficha_individual.py"
PDF_GENERATOR = ROOT / "backend" / "pdf" / "ficha_individual.py"
SERVER = ROOT / "backend" / "server.py"
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
    "insert_one",
    "insert_many",
    "update_one",
    "update_many",
    "replace_one",
    "delete_one",
    "delete_many",
    "find_one_and_update",
    "find_one_and_replace",
    "find_one_and_delete",
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


def test_manual_router_uses_explicit_official_pdf_overrides_only():
    source = _source(BACKEND_ROUTER)

    assert "from pdf.ficha_individual import generate_ficha_individual_pdf" in source
    assert "pdf_buffer = generate_ficha_individual_pdf(" in source
    assert "resultado_override=payload.resultado" in source
    assert "data_emissao_override=payload.data_emissao" in source

    # A reconstrução v2 aposenta definitivamente a clonagem do code object/globals.
    forbidden_fragments = (
        "types.FunctionType",
        "__globals__",
        "isolated_globals",
        "ficha_individual_module.determinar_resultado_documento =",
        "ficha_individual_module.date =",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source, f"Técnica de override proibida reapareceu: {fragment}"


def test_official_pdf_exposes_backward_compatible_contingency_seam():
    source = _source(PDF_GENERATOR)
    tree = ast.parse(source)

    funcs = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "generate_ficha_individual_pdf"
    ]
    assert len(funcs) == 1
    fn = funcs[0]
    args = [arg.arg for arg in fn.args.args]
    assert args[-2:] == ["resultado_override", "data_emissao_override"]

    defaults = fn.args.defaults
    # Os dois novos argumentos precisam permanecer opcionais para não alterar emissões normais.
    assert isinstance(defaults[-2], ast.Constant) and defaults[-2].value is None
    assert isinstance(defaults[-1], ast.Constant) and defaults[-1].value is None

    assert "if resultado_override is None:" in source
    assert "resultado = resultado_calc['resultado']" in source
    assert "today = format_date_pt(data_emissao_override or local_today())" in source


def test_manual_router_enforces_tenant_scope_on_primary_entities():
    source = _source(BACKEND_ROUTER)
    assert (
        "from tenant_scope import apply_tenant_filter, assert_same_tenant, "
        "resolve_active_mantenedora"
    ) in source

    for literal in (
        'apply_tenant_filter({"id": school_id}, user, request)',
        'apply_tenant_filter({"id": class_id}, user, request)',
        'apply_tenant_filter({"id": student_id}, user, request)',
        'apply_tenant_filter({"id": {"$in": ids}}, user, request)',
        'resolve_active_mantenedora(',
    ):
        assert literal in source, f"Escopo multi-tenant ausente: {literal}"

    # A leitura de frequência também deve passar por apply_tenant_filter.
    assert '"class_id": class_id,' in source
    assert '"academic_year": {"$in": [academic_year, str(academic_year)]},' in source
    assert "apply_tenant_filter(" in source


def test_manual_routes_are_registered_explicitly_in_server():
    router_source = _source(BACKEND_ROUTER)
    server_source = _source(SERVER)

    assert '@router.get("/documents/ficha-individual-manual/preview")' in router_source
    assert '@router.post("/documents/ficha-individual-manual")' in router_source
    assert "manual_ficha_individual as manual_ficha_individual_mod" in server_source
    assert "manual_ficha_individual_mod.setup_router(" in server_source
    assert "app.include_router(manual_ficha_individual_mod.router, prefix=\"/api\")" in server_source

    # Não voltar ao acoplamento indireto em routers/__init__.py da implementação antiga.
    assert "_documents_module.router.include_router(manual_router)" not in server_source


def test_role_contract_is_identical_backend_and_frontend():
    router = _source(BACKEND_ROUTER)
    app = _source(APP)

    for role in (
        "super_admin",
        "admin",
        "admin_teste",
        "secretario",
        "diretor",
        "auxiliar_secretaria",
    ):
        assert f'"{role}"' in router
        assert f"'{role}'" in app

    # Escopo inicialmente aprovado: gerente/coordenação/SEMED/professor não entram.
    allowed_block = router.split("_ALLOWED_ROLES =", 1)[1].split("}", 1)[0]
    for forbidden in ("gerente", "coordenador", "semed", "professor"):
        assert f'"{forbidden}"' not in allowed_block


def test_frontend_routes_dashboard_entry_and_non_mutation_warning_exist():
    app = _source(APP)
    dashboard = _source(DASHBOARD)
    form = _source(FORM)

    assert "const Urgencias = lazy(() => import('@/pages/Urgencias'))" in app
    assert "const UrgenciaFichaIndividual = lazy(() => import('@/pages/UrgenciaFichaIndividual'))" in app
    assert 'path="/admin/urgencias"' in app
    assert 'path="/admin/urgencias/ficha-individual"' in app

    assert "label: 'Urgências'" in dashboard
    assert "route: '/admin/urgencias'" in dashboard
    assert "testId: 'nav-urgencias-button'" in dashboard

    assert (
        "não substituem nem alteram Notas, Frequência, Matrícula ou Histórico acadêmico"
        in form
    )
    assert "responseType: 'blob'" in form
