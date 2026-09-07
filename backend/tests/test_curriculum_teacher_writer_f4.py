from pathlib import Path
from types import SimpleNamespace

import pytest

from services import content_form_canonical_cutover as cutover


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend/services/content_form_canonical_cutover.py"
ADAPTER = ROOT / "backend/routers/content_partial_cutover.py"
LEGACY = ROOT / "backend/routers/learning_objects.py"


class _FindOneCollection:
    def __init__(self, value):
        self.value = value

    async def find_one(self, *args, **kwargs):
        return dict(self.value) if self.value is not None else None


class _FakeDb:
    def __init__(self):
        self.classes = _FindOneCollection(
            {
                "id": "c1",
                "mantenedora_id": "t1",
                "academic_year": 2026,
                "grade_level": "6",
            }
        )
        self.calendario_letivo = _FindOneCollection(
            {
                "ano_letivo": 2026,
                "bimestre_1_inicio": "2026-02-01",
                "bimestre_1_fim": "2026-04-30",
                "bimestre_2_inicio": "2026-05-01",
                "bimestre_2_fim": "2026-07-15",
                "bimestre_3_inicio": "2026-07-16",
                "bimestre_3_fim": "2026-09-30",
                "bimestre_4_inicio": "2026-10-01",
                "bimestre_4_fim": "2026-12-20",
            }
        )
        self.teaching_plans = _FindOneCollection(
            {
                "id": "plan-1",
                "revision": 3,
                "curriculum_version_id": "cv-1",
                "academic_year": 2026,
                "component_id": "eng",
                "bimestre": 3,
                "grade_scope": ["6"],
                "status": "published",
                "items": [
                    {
                        "id": "item-1",
                        "adaptation_id": "ad-1",
                        "knowledge_objects": [
                            {"id": "ko-1", "label": "Reading strategies"}
                        ],
                        "pedagogical_practices": [
                            {"id": "pp-1", "label": "Guided reading"}
                        ],
                        "source_refs": ["BNCC-p.10"],
                    }
                ],
            }
        )


def test_f4_teacher_form_has_no_direct_legacy_write_path():
    service = SERVICE.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")

    assert "save_content_canonical" in service
    assert "db.learning_objects.insert_one" not in service
    assert "db.learning_objects.update_one" not in service
    assert "db.learning_objects.delete_one" not in service
    assert 'current_user.get("role") != "professor"' in adapter
    assert "create_from_learning_object_form" in adapter
    assert "update_from_learning_object_form" in adapter
    assert "delete_from_learning_object_form" in adapter


def test_f4_persists_structured_curriculum_relations():
    service = SERVICE.read_text(encoding="utf-8")

    for token in (
        '"curriculum_binding"',
        '"curriculum_links"',
        '"teaching_plan_id"',
        '"curriculum_version_id"',
        '"teaching_plan_item_ids"',
        '"knowledge_objects"',
        '"pedagogical_practices"',
        '"adaptation_ids"',
        'FORM_WRITER_ORIGIN = "learning_objects_form_f4"',
    ):
        assert token in service


@pytest.mark.asyncio
async def test_published_plan_binding_snapshots_skill_object_and_practice(monkeypatch):
    monkeypatch.setattr(cutover, "get_mantenedora_scope", lambda user, request: "t1")
    monkeypatch.setattr(cutover, "assert_same_tenant", lambda doc, user, request: None)

    binding = await cutover._curriculum_binding(
        _FakeDb(),
        {"id": "teacher-1", "role": "professor", "mantenedora_id": "t1"},
        SimpleNamespace(),
        class_id="c1",
        component_id="eng",
        date="2026-09-07",
        academic_year=2026,
        adaptation_ids=["ad-1"],
    )

    assert binding["status"] == "bound"
    assert binding["bimestre"] == 3
    assert binding["teaching_plan_id"] == "plan-1"
    assert binding["curriculum_version_id"] == "cv-1"
    assert binding["teaching_plan_item_ids"] == ["item-1"]
    assert binding["knowledge_objects"] == [
        {"id": "ko-1", "label": "Reading strategies"}
    ]
    assert binding["pedagogical_practices"] == [
        {"id": "pp-1", "label": "Guided reading"}
    ]
    assert binding["source_refs"] == ["BNCC-p.10"]


def test_f4_keeps_legacy_router_as_fallback_not_ssot():
    legacy = LEGACY.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")

    # O legado ainda existe para histórico/gestão; a F4 não o apaga nem migra.
    assert 'router = APIRouter(tags=["Objetos de Aprendizagem"])' in legacy
    assert "legacy_create" in adapter
    assert "legacy_update" in adapter
    assert "legacy_delete" in adapter
    # O professor é explicitamente desviado antes do create legado.
    professor_guard = adapter.index('current_user.get("role") != "professor"')
    canonical_create = adapter.index("create_from_learning_object_form", professor_guard)
    assert professor_guard < canonical_create
