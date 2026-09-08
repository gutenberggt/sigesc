import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_ROUTER_PATH = REPO_ROOT / "backend" / "routers" / "users.py"


def _users_source() -> str:
    return USERS_ROUTER_PATH.read_text(encoding="utf-8")


def _load_scope_helper():
    """Carrega só a função pura, sem importar dependências do router."""
    source = _users_source()
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_apply_secretary_school_scope"
    )
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), str(USERS_ROUTER_PATH), "exec"), namespace)
    return namespace["_apply_secretary_school_scope"]


def test_non_secretary_keeps_existing_tenant_filter_unchanged():
    scope = _load_scope_helper()
    original = {"mantenedora_id": "tenant-a"}

    result = scope(original, {"role": "admin", "school_ids": ["school-a"]})

    assert result == original


def test_secretary_requires_user_link_to_one_of_authorized_schools():
    scope = _load_scope_helper()

    result = scope(
        {"mantenedora_id": "tenant-a"},
        {
            "role": "secretario",
            "school_ids": ["school-a", "", "school-a", "school-b"],
        },
    )

    assert result == {
        "$and": [
            {"mantenedora_id": "tenant-a"},
            {
                "$or": [
                    {"school_links.school_id": {"$in": ["school-a", "school-b"]}},
                    {"school_ids": {"$in": ["school-a", "school-b"]}},
                ]
            },
        ]
    }


def test_secretary_without_authorized_school_fails_closed():
    scope = _load_scope_helper()

    result = scope(
        {"mantenedora_id": "tenant-a"},
        {"role": "secretario", "school_ids": []},
    )

    school_scope = result["$and"][1]
    assert school_scope == {
        "$or": [
            {"school_links.school_id": {"$in": []}},
            {"school_ids": {"$in": []}},
        ]
    }


def test_list_count_get_and_update_apply_the_school_scope():
    source = _users_source()

    assert source.count(
        "filter_query = _apply_secretary_school_scope(filter_query, current_user)"
    ) == 2
    assert source.count(
        'user_filter = _apply_secretary_school_scope({"id": user_id}, current_user)'
    ) == 2


def test_secretary_cannot_assign_user_to_school_outside_own_scope():
    source = _users_source()

    assert "requested_school_ids.issubset(allowed_school_ids)" in source
    assert (
        'detail="Secretário só pode vincular usuários às suas escolas autorizadas"'
        in source
    )
