"""Regressão #350.1 — filtros avançados da listagem de Estudantes.

Cobre correção semântica, multisseriação, legado, AEE efetivo, combinação com
Turma Especial e isolamento tenant. Sem Mongo real e sem writes de produção.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid

import pytest
from starlette.requests import Request

import auth_middleware as auth_module
from auth_middleware import AuthMiddleware


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDENTS_PATH = os.path.join(BACKEND_DIR, "routers", "students.py")
FILTERS_PATH = os.path.join(BACKEND_DIR, "routers", "student_list_filters.py")


def _load_module(path: str, prefix: str):
    name = f"{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_filters_module = _load_module(FILTERS_PATH, "student_list_filters_under_test")
install_student_list_filters = _filters_module.install_student_list_filters


# mongomock 4.3 não implementa integralmente operadores usados pela rota
# canônica de Estudantes. Estes shims existem só no processo de teste.
def _patch_mongomock_trim() -> None:
    from mongomock.aggregate import _Parser

    if getattr(_Parser, "_sigesc_trim_patched", False):
        return
    original = _Parser._handle_string_operator

    def _patched(self, operator, values):
        if operator == "$trim":
            if isinstance(values, dict):
                input_val = self.parse(values.get("input"))
                chars = values.get("chars")
                chars = self.parse(chars) if chars is not None else None
            else:
                input_val = self.parse(values)
                chars = None
            if input_val is None:
                return None
            return str(input_val).strip(chars)
        if operator == "$strLenCP":
            input_val = self.parse(values)
            return len(str(input_val)) if input_val is not None else 0
        return original(self, operator, values)

    _Parser._handle_string_operator = _patched
    _Parser._sigesc_trim_patched = True


def _patch_mongomock_round() -> None:
    from mongomock.aggregate import _Parser

    if getattr(_Parser, "_sigesc_round_patched", False):
        return
    original_parse = _Parser.parse

    def _patched_parse(self, expression):
        if isinstance(expression, dict) and set(expression.keys()) == {"$round"}:
            values = expression["$round"]
            if isinstance(values, (list, tuple)):
                number = self.parse(values[0])
                place = self.parse(values[1]) if len(values) > 1 else 0
            else:
                number = self.parse(values)
                place = 0
            if number is None:
                return None
            return round(number, place) if place else round(number)
        return original_parse(self, expression)

    _Parser.parse = _patched_parse
    _Parser._sigesc_round_patched = True


def _patch_motor_collation_noop() -> None:
    import mongomock_motor

    if getattr(mongomock_motor.AsyncCursor, "_sigesc_collation_patched", False):
        return

    def _noop_collation(self, *_args, **_kwargs):
        return self

    mongomock_motor.AsyncCursor.collation = _noop_collation
    mongomock_motor.AsyncCursor._sigesc_collation_patched = True


_patch_mongomock_trim()
_patch_mongomock_round()
_patch_motor_collation_noop()

from mongomock_motor import AsyncMongoMockClient  # noqa: E402


TENANT_A = "TENANT_A"
TENANT_B = "TENANT_B"
CURRENT_TDAH = "Transtorno do Déficit de Atenção e Hiperatividade (TDAH)"
LEGACY_TDAH = "Transtorno de Déficit de Atenção e Hiperatividade (TDAH)"


def make_request(path: str = "/api/students") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [(b"authorization", b"Bearer test-token")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    })


def _install_admin(monkeypatch, tenant_id: str = TENANT_A) -> None:
    payload = {
        "type": "access",
        "sub": "USER_ADMIN",
        "id": "USER_ADMIN",
        "role": "admin",
        "school_ids": [],
        "email": "admin@example.test",
        "mantenedora_id": tenant_id,
    }
    monkeypatch.setattr(auth_module, "decode_token", lambda _token: dict(payload))

    async def _fake_get_current_user(_request):
        return dict(payload)

    monkeypatch.setattr(
        AuthMiddleware,
        "get_current_user",
        staticmethod(_fake_get_current_user),
    )


def _student(
    sid: str,
    class_id: str,
    *,
    tenant: str = TENANT_A,
    school: str = "SCHOOL_A",
    series: str,
    color: str = "branca",
    community: str = "nao_pertence",
    disabilities=None,
    program_type: str = "",
    program_class_id: str = "",
):
    return {
        "id": sid,
        "full_name": sid.replace("_", " ").title(),
        "school_id": school,
        "class_id": class_id,
        "student_series": series,
        "status": "active",
        "mantenedora_id": tenant,
        "color_race": color,
        "comunidade_tradicional": community,
        "disabilities": list(disabilities or []),
        "atendimento_programa_tipo": program_type,
        "atendimento_programa_class_id": program_class_id,
    }


async def _seed():
    client = AsyncMongoMockClient()
    db = client["sigesc_students_filters"]

    await db.schools.insert_many([
        {"id": "SCHOOL_A", "name": "Escola A", "status": "active", "mantenedora_id": TENANT_A},
        {"id": "SCHOOL_B", "name": "Escola B", "status": "active", "mantenedora_id": TENANT_B},
    ])

    await db.classes.insert_many([
        {
            "id": "CLASS_MIX", "school_id": "SCHOOL_A", "mantenedora_id": TENANT_A,
            "education_level": "fundamental_anos_iniciais", "grade_level": "1º ANO",
            "atendimento_programa": "", "is_multi_grade": True, "series": ["1º ANO", "6º ANO"],
        },
        {
            "id": "CLASS_INT", "school_id": "SCHOOL_A", "mantenedora_id": TENANT_A,
            "education_level": "fundamental_anos_iniciais", "grade_level": "4º ANO",
            "atendimento_programa": "atendimento_integral",
        },
        {
            "id": "CLASS_FINAL", "school_id": "SCHOOL_A", "mantenedora_id": TENANT_A,
            "education_level": "fundamental_anos_finais", "grade_level": "7º ANO",
            "atendimento_programa": "",
        },
        {
            "id": "CLASS_RECOMP", "school_id": "SCHOOL_A", "mantenedora_id": TENANT_A,
            "education_level": "fundamental_anos_finais", "grade_level": "7º ANO",
            "atendimento_programa": "recomposicao_aprendizagem",
        },
        {
            "id": "CLASS_B", "school_id": "SCHOOL_B", "mantenedora_id": TENANT_B,
            "education_level": "fundamental_anos_finais", "grade_level": "7º ANO",
            "atendimento_programa": "",
        },
    ])

    students = [
        _student(
            "STUDENT_1", "CLASS_MIX", series="1º ANO", color="parda",
            community="quilombola", disabilities=["Dislexia"],
        ),
        _student(
            "STUDENT_6", "CLASS_MIX", series="6º ANO", color="preta",
            disabilities=[LEGACY_TDAH],
        ),
        _student("STUDENT_INT", "CLASS_INT", series="4º ANO"),
        _student(
            "STUDENT_RECOMP", "CLASS_FINAL", series="7º ANO",
            program_type="recomposicao_aprendizagem", program_class_id="CLASS_RECOMP",
        ),
        _student("STUDENT_AEE_ACTIVE", "CLASS_FINAL", series="7º ANO", color="parda"),
        _student("STUDENT_AEE_DRAFT", "CLASS_FINAL", series="7º ANO"),
        _student("STUDENT_AEE_CLOSED", "CLASS_FINAL", series="7º ANO"),
        _student(
            "STUDENT_VISUAL_LEGACY", "CLASS_FINAL", series="7º ANO",
            disabilities=["Deficiência Visual"],
        ),
        _student(
            "STUDENT_B", "CLASS_B", tenant=TENANT_B, school="SCHOOL_B",
            series="7º ANO", color="parda", disabilities=[CURRENT_TDAH],
        ),
    ]
    await db.students.insert_many(students)

    await db.enrollments.insert_many([
        {
            "id": f"ENR_{s['id']}", "student_id": s["id"], "school_id": s["school_id"],
            "class_id": s["class_id"], "academic_year": 2026, "status": "active",
            "student_series": s["student_series"], "mantenedora_id": s["mantenedora_id"],
        }
        for s in students
    ])

    await db.planos_aee.insert_many([
        {
            "id": "PLAN_ACTIVE", "student_id": "STUDENT_AEE_ACTIVE", "school_id": "SCHOOL_A",
            "academic_year": 2026, "status": "ativo", "dias_atendimento": [],
        },
        {
            "id": "PLAN_DRAFT", "student_id": "STUDENT_AEE_DRAFT", "school_id": "SCHOOL_A",
            "academic_year": 2026, "status": "rascunho", "dias_atendimento": [],
        },
        {
            "id": "PLAN_CLOSED", "student_id": "STUDENT_AEE_CLOSED", "school_id": "SCHOOL_A",
            "academic_year": 2026, "status": "encerrado", "dias_atendimento": [],
        },
        {
            "id": "PLAN_B", "student_id": "STUDENT_B", "school_id": "SCHOOL_B",
            "academic_year": 2026, "status": "ativo", "dias_atendimento": [],
        },
    ])
    return db


def _get_list_endpoint(router):
    matches = [
        route.endpoint for route in router.routes
        if route.path == "/students" and "GET" in (route.methods or set())
    ]
    assert len(matches) == 1
    return matches[0]


def _make_endpoints(db):
    students_module = _load_module(STUDENTS_PATH, "students_under_test")
    router = students_module.setup_students_router(db, audit_service=None)
    canonical = _get_list_endpoint(router)
    install_student_list_filters(router, db)
    filtered = _get_list_endpoint(router)
    return canonical, filtered


async def _call(endpoint, **overrides):
    params = dict(
        school_id=None,
        class_id=None,
        status=None,
        search=None,
        completeness_band=None,
        color_race=None,
        comunidade_tradicional=None,
        education_level=None,
        modalidade=None,
        disability=None,
        page=1,
        page_size=50,
        skip=0,
        limit=5000,
    )
    params.update(overrides)
    # O endpoint canônico anterior não conhece os cinco parâmetros novos.
    if "student_list_filters" not in getattr(endpoint, "__module__", ""):
        for key in (
            "color_race", "comunidade_tradicional", "education_level", "modalidade", "disability"
        ):
            params.pop(key, None)
    return await endpoint(request=make_request(), **params)


def _ids(result) -> set[str]:
    return {str(student["id"]) for student in result["items"]}


def test_no_new_filter_preserves_canonical_contract(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    canonical, filtered = _make_endpoints(db)

    before = asyncio.run(_call(canonical))
    after = asyncio.run(_call(filtered))
    assert _ids(after) == _ids(before)
    assert after["total"] == before["total"]
    assert after["active_count"] == before["active_count"]


def test_color_and_traditional_community_filters(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    race = asyncio.run(_call(endpoint, color_race="parda"))
    assert _ids(race) == {"STUDENT_1", "STUDENT_AEE_ACTIVE"}

    community = asyncio.run(_call(endpoint, comunidade_tradicional="quilombola"))
    assert _ids(community) == {"STUDENT_1"}


def test_disability_current_tda_h_matches_known_legacy_spelling(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(_call(endpoint, disability=CURRENT_TDAH))
    assert _ids(result) == {"STUDENT_6"}


def test_ambiguous_legacy_condition_is_only_exact_match(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(_call(endpoint, disability="Deficiência Visual"))
    assert _ids(result) == {"STUDENT_VISUAL_LEGACY"}

    # Não reinterpretar automaticamente como Baixa Visão/Cegueira/Visão Monocular.
    current = asyncio.run(_call(endpoint, disability="Baixa Visão"))
    assert _ids(current) == set()


def test_education_level_respects_individual_series_in_multigrade_class(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    initials = asyncio.run(_call(endpoint, education_level="fundamental_anos_iniciais"))
    assert "STUDENT_1" in _ids(initials)
    assert "STUDENT_6" not in _ids(initials)

    finals = asyncio.run(_call(endpoint, education_level="fundamental_anos_finais"))
    assert "STUDENT_6" in _ids(finals)
    assert "STUDENT_1" not in _ids(finals)


def test_regular_and_integral_modalities_use_main_class(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    regular = asyncio.run(_call(endpoint, modalidade="regular"))
    assert "STUDENT_INT" not in _ids(regular)
    assert "STUDENT_AEE_ACTIVE" in _ids(regular)  # AEE é add-on, não substitui turma regular.
    assert "STUDENT_RECOMP" in _ids(regular)  # Recomposição também pode ser atendimento adicional.

    integral = asyncio.run(_call(endpoint, modalidade="atendimento_integral"))
    assert _ids(integral) == {"STUDENT_INT"}


def test_recomposicao_detects_add_on_link(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(_call(endpoint, modalidade="recomposicao_aprendizagem"))
    assert _ids(result) == {"STUDENT_RECOMP"}


def test_aee_uses_effective_lifecycle_not_raw_plan_existence(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(_call(endpoint, modalidade="aee"))
    assert _ids(result) == {"STUDENT_AEE_ACTIVE"}
    assert result["modalidade_counts"]["aee"] == 1


def test_special_class_or_composes_with_education_level(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(
        _call(
            endpoint,
            class_id="CLASS_RECOMP",
            education_level="fundamental_anos_finais",
        )
    )
    assert _ids(result) == {"STUDENT_RECOMP"}


def test_filters_compose_with_and(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch)
    _, endpoint = _make_endpoints(db)

    result = asyncio.run(
        _call(
            endpoint,
            color_race="parda",
            education_level="fundamental_anos_finais",
            modalidade="aee",
        )
    )
    assert _ids(result) == {"STUDENT_AEE_ACTIVE"}


def test_tenant_b_never_leaks_into_tenant_a(monkeypatch):
    db = asyncio.run(_seed())
    _install_admin(monkeypatch, TENANT_A)
    _, endpoint = _make_endpoints(db)

    broad = asyncio.run(_call(endpoint, color_race="parda"))
    assert "STUDENT_B" not in _ids(broad)

    aee = asyncio.run(_call(endpoint, modalidade="aee"))
    assert "STUDENT_B" not in _ids(aee)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
