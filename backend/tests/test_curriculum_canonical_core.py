from pathlib import Path

from routers.curriculum_core import (
    CurriculumSourceCreate,
    NamedCurricularElement,
    TeachingPlanCreate,
    TeachingPlanItem,
    build_curriculum_core_router,
)


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "backend" / "routers" / "curriculum_core.py"
ROUTERS_INIT = ROOT / "backend" / "routers" / "__init__.py"


def test_source_contract_distinguishes_national_and_municipal_sources():
    tenant = CurriculumSourceCreate(title="DCM 2026", source_type="DCM")
    national = CurriculumSourceCreate(
        title="BNCC Computação", source_type="BNCC_COMPUTACAO", scope="national"
    )
    assert tenant.scope == "tenant"
    assert national.scope == "national"


def test_teaching_plan_supports_multiple_objects_and_practices():
    item = TeachingPlanItem(
        adaptation_id="adapt-1",
        knowledge_objects=[
            NamedCurricularElement(label="Tipos de dados"),
            NamedCurricularElement(label="Organização de dados"),
        ],
        pedagogical_practices=[
            NamedCurricularElement(label="Aula dialogada"),
            NamedCurricularElement(label="Trabalho colaborativo"),
        ],
    )
    plan = TeachingPlanCreate(
        curriculum_version_id="version-1",
        academic_year=2026,
        component_id="course-1",
        bimestre=1,
        grade_scope=["6", "7"],
        title="Plano de Ensino Bimestral",
        items=[item],
    )
    assert plan.grade_scope == ["6", "7"]
    assert len(plan.items[0].knowledge_objects) == 2
    assert len(plan.items[0].pedagogical_practices) == 2


def test_core_router_exposes_sources_versions_plan_and_context_without_legacy_writes():
    router = build_curriculum_core_router(object())
    signatures = {
        (route.path, method)
        for route in router.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert ("/sources", "GET") in signatures
    assert ("/sources", "POST") in signatures
    assert ("/versions", "POST") in signatures
    assert ("/versions/{version_id}/publish", "POST") in signatures
    assert ("/teaching-plans", "POST") in signatures
    assert ("/teaching-plans/{plan_id}/publish", "POST") in signatures
    assert ("/teaching-plans/context", "GET") in signatures

    source = CORE.read_text(encoding="utf-8")
    assert "db.learning_objects" not in source
    assert "learning_objects.insert" not in source
    assert "learning_objects.update" not in source


def test_tenant_and_publishing_guards_are_explicit():
    source = CORE.read_text(encoding="utf-8")
    assert "CURRICULUM_TENANT_REQUIRED" in source
    assert "assert_same_tenant" in source
    assert "TEACHING_PLAN_SKILL_INVALID" in source
    assert "CURRICULUM_VERSION_NOT_PUBLISHED" in source
    assert '"status": "published"' in source
    assert '"status": "superseded"' in source


def test_bootstrap_installs_core_before_server_materializes_curriculum_router():
    source = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "from .curriculum_core import install_curriculum_core_setup" in source
    assert "install_curriculum_core_setup(_curriculum_v2_mod)" in source
