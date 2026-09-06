from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "backend" / "routers" / "student_history_responsible_name.py"
ROUTERS_INIT = ROOT / "backend" / "routers" / "__init__.py"
CSS = ROOT / "frontend" / "src" / "index.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_student_history_resolves_responsible_full_name_read_only():
    source = _read(ADAPTER)

    assert 'ROUTE_PATH = "/students/{student_id}/history"' in source
    assert "history = await current_history(student_id=student_id, request=request)" in source
    assert '"full_name": 1' in source
    assert "names_by_id" in source
    assert "names_by_email" in source
    assert 'item["user_name"] = resolved_name' in source
    assert ".to_list(None)" in source

    # A camada é exclusivamente de projeção de leitura: nenhuma mutação do
    # histórico ou de usuários pode ser introduzida aqui.
    assert "insert_one" not in source
    assert "update_one" not in source
    assert "update_many" not in source
    assert "delete_one" not in source
    assert "delete_many" not in source


def test_student_router_installs_responsible_name_projection_in_safe_order():
    source = _read(ROUTERS_INIT)

    assert (
        "from .student_history_responsible_name import "
        "install_student_history_responsible_name"
    ) in source
    install = "install_student_history_responsible_name(configured, db, sandbox_db)"
    transfer = "install_student_transfer_destination_access(configured, db, sandbox_db)"
    filters = "return install_student_list_filters(configured, db, sandbox_db)"

    assert install in source
    assert source.index(transfer) < source.index(install) < source.index(filters)


def test_history_table_allows_wrapping_in_every_column():
    css = _read(CSS)

    assert "Histórico do Estudante — Turma/Observações" in css
    assert "+ .overflow-x-auto > table.min-w-full.text-sm th" in css
    assert "+ .overflow-x-auto > table.min-w-full.text-sm td" in css
    assert "white-space: normal !important;" in css
    assert "overflow-wrap: anywhere;" in css
