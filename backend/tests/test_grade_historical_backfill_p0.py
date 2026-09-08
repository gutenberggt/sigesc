"""P0 — regressão da escrita histórica de Notas após o cutover DVD.

Contrato: professor pedagogicamente legítimo pode lançar campo vazio de período
pré-cutover quando o DVD 38G-B deriva de vínculo legado revalidado. Nenhuma
ponte pode apropriar legado não-nulo, sobrescrever outro owner ou transformar um
vínculo realmente posterior em vínculo histórico.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys

import pytest

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessContext,
    effective_diary_settings,
)
from services.grade_assignment_scope import (
    GradeAssignmentContext,
    GradeAssignmentScopeError,
    apply_grade_field_ownership,
)
from services.grade_cutover_history import (
    HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG,
    HISTORICAL_WRITE_FLAG,
    HISTORICAL_WRITE_PERIOD_END_FLAG,
    HISTORICAL_WRITE_PERIOD_FLAG,
    HISTORICAL_WRITE_PERIOD_START_FLAG,
    HISTORICAL_WRITE_SOURCE_FLAG,
    LEGACY_HISTORY_FLAG,
    LEGACY_SOURCE_FLAG,
    LEGACY_YEAR_FLAG,
    decorate_context_with_legacy_history,
    historical_grade_write_evidence,
    safe_cutover_legacy_assignment,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "routers" / "grades_historical_backfill_dvd.py"
SPEC = importlib.util.spec_from_file_location(
    "grades_historical_backfill_dvd_under_test",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
BACKFILL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BACKFILL
SPEC.loader.exec_module(BACKFILL)

_build_historical_ownership_adapter = BACKFILL._build_historical_ownership_adapter
_historical_change_metadata = BACKFILL._historical_change_metadata


PERIODS = {
    1: ("2026-02-01", "2026-04-30"),
    2: ("2026-05-01", "2026-07-15"),
    3: ("2026-07-16", "2026-09-30"),
    4: ("2026-10-01", "2026-12-20"),
}
DVD_VALID_FROM = "2026-08-18"


def _match(doc, query):
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$regex" in expected:
                flags = re.I if "i" in str(expected.get("$options") or "") else 0
                if not re.search(expected["$regex"], str(actual or ""), flags):
                    return False
            continue
        if actual != expected:
            return False
    return True


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return dict(doc)
        return None


class FakeDb:
    def __init__(self, *, legacy=None, staff=None, users=None):
        self.teacher_assignments = FakeCollection(
            [legacy or _legacy_assignment()]
            if legacy is not False
            else []
        )
        self.staff = FakeCollection(
            [staff or _staff()]
            if staff is not False
            else []
        )
        self.users = FakeCollection(users or [])


def _assignment(**overrides):
    doc = {
        "id": "dvd-1",
        "teacher_id": "teacher-1",
        "teacher_name": "Professora Um",
        "class_id": "class-1",
        "class_name": "6º ANO A",
        "component_id": "math",
        "school_id": "school-1",
        "mantenedora_id": "tenant-1",
        "valid_from": DVD_VALID_FROM,
        "valid_until": None,
        "deleted": False,
        "diary_settings": {
            "enabled": True,
            "schema_version": 1,
            "profile": "regular",
            "student_scope": "all",
        },
        "cutover_provenance": {
            "apply_phase": "38G-B",
            "apply_state": "ACTIVATED",
            "source_legacy_assignment_id": "legacy-1",
        },
    }
    doc.update(overrides)
    return doc


def _legacy_assignment(**overrides):
    doc = {
        "id": "legacy-1",
        "staff_id": "staff-1",
        "class_id": "class-1",
        "course_id": "math",
        "status": "ativo",
        "academic_year": 2026,
    }
    doc.update(overrides)
    return doc


def _staff(**overrides):
    doc = {
        "id": "staff-1",
        "user_id": "teacher-1",
        "email": "prof@example.com",
    }
    doc.update(overrides)
    return doc


def _context(*, owner=True, assignment=None):
    assignment = assignment or _assignment()
    settings = effective_diary_settings(assignment)
    access = DiaryAssignmentAccessContext(
        assignment=assignment,
        class_info={
            "id": "class-1",
            "school_id": "school-1",
            "mantenedora_id": "tenant-1",
        },
        settings=settings,
        action=DiaryAction.GRADES,
        is_owner=owner,
        management_override=False,
    )
    return GradeAssignmentContext(
        access=access,
        assignment_id=assignment["id"],
        class_id="class-1",
        course_id="math",
        profile=settings.profile,
        student_scope=settings.student_scope,
        snapshot={
            "assignment_id": assignment["id"],
            "teacher_id": assignment["teacher_id"],
            "teacher_name": assignment["teacher_name"],
            "class_id": assignment["class_id"],
            "component_id": "math",
            "assignment_component_id": assignment.get("component_id"),
            "school_id": "school-1",
            "mantenedora_id": "tenant-1",
            "assignment_profile_at_record": settings.profile.value,
            "assignment_schema_version_at_record": settings.schema_version,
        },
    )


def _user():
    return {
        "id": "teacher-1",
        "role": "professor",
        "mantenedora_id": "tenant-1",
        "school_ids": ["school-1"],
    }


@pytest.mark.asyncio
async def test_01_prova_38g_b_valida_resolve_origem_legada():
    legacy = await safe_cutover_legacy_assignment(FakeDb(), _context(), 2026)
    assert legacy and legacy["id"] == "legacy-1"


@pytest.mark.asyncio
async def test_02_fase_diferente_de_38g_b_nao_autoriza():
    assignment = _assignment(cutover_provenance={
        "apply_phase": "38G-A",
        "apply_state": "ACTIVATED",
        "source_legacy_assignment_id": "legacy-1",
    })
    assert await safe_cutover_legacy_assignment(FakeDb(), _context(assignment=assignment), 2026) is None


@pytest.mark.asyncio
async def test_03_cutover_nao_activated_nao_autoriza():
    assignment = _assignment(cutover_provenance={
        "apply_phase": "38G-B",
        "apply_state": "PLANNED",
        "source_legacy_assignment_id": "legacy-1",
    })
    assert await safe_cutover_legacy_assignment(FakeDb(), _context(assignment=assignment), 2026) is None


@pytest.mark.asyncio
async def test_04_sem_source_legacy_assignment_id_nao_autoriza():
    assignment = _assignment(cutover_provenance={
        "apply_phase": "38G-B",
        "apply_state": "ACTIVATED",
    })
    assert await safe_cutover_legacy_assignment(FakeDb(), _context(assignment=assignment), 2026) is None


@pytest.mark.asyncio
async def test_05_origem_legada_de_outra_turma_nao_autoriza():
    db = FakeDb(legacy=_legacy_assignment(class_id="class-2"))
    assert await safe_cutover_legacy_assignment(db, _context(), 2026) is None


@pytest.mark.asyncio
async def test_06_origem_legada_de_outro_componente_nao_autoriza():
    db = FakeDb(legacy=_legacy_assignment(course_id="port"))
    assert await safe_cutover_legacy_assignment(db, _context(), 2026) is None


@pytest.mark.asyncio
async def test_07_origem_legada_de_outro_ano_nao_autoriza():
    db = FakeDb(legacy=_legacy_assignment(academic_year=2025))
    assert await safe_cutover_legacy_assignment(db, _context(), 2026) is None


@pytest.mark.asyncio
async def test_08_staff_de_outro_professor_nao_autoriza():
    db = FakeDb(staff=_staff(user_id="teacher-2"))
    assert await safe_cutover_legacy_assignment(db, _context(), 2026) is None


@pytest.mark.asyncio
async def test_09_fallback_por_email_revalida_o_mesmo_usuario():
    db = FakeDb(
        staff=_staff(user_id=None, email="Prof@Example.com"),
        users=[{"id": "teacher-1", "email": "prof@example.com"}],
    )
    legacy = await safe_cutover_legacy_assignment(db, _context(), 2026)
    assert legacy and legacy["id"] == "legacy-1"


@pytest.mark.asyncio
async def test_10_contexto_de_leitura_recebe_prova_e_ano_sem_mutar_assignment():
    context = _context()
    decorated = await decorate_context_with_legacy_history(FakeDb(), context, 2026)
    assert decorated.snapshot[LEGACY_HISTORY_FLAG] is True
    assert decorated.snapshot[LEGACY_SOURCE_FLAG] == "legacy-1"
    assert decorated.snapshot[LEGACY_YEAR_FLAG] == 2026
    assert context.assignment["valid_from"] == DVD_VALID_FROM
    assert decorated.assignment["valid_from"] == DVD_VALID_FROM


@pytest.mark.asyncio
async def test_11_b2_inteiro_antes_do_cutover_gera_evidencia_historica():
    evidence = await historical_grade_write_evidence(
        FakeDb(), _context(), field="b2", period_number=2, period=PERIODS[2]
    )
    assert evidence[HISTORICAL_WRITE_FLAG] is True
    assert evidence[HISTORICAL_WRITE_SOURCE_FLAG] == "legacy-1"
    assert evidence[HISTORICAL_WRITE_AUTHORIZED_FROM_FLAG] == DVD_VALID_FROM
    assert evidence[HISTORICAL_WRITE_PERIOD_FLAG] == 2
    assert evidence[HISTORICAL_WRITE_PERIOD_START_FLAG] == "2026-05-01"
    assert evidence[HISTORICAL_WRITE_PERIOD_END_FLAG] == "2026-07-15"


@pytest.mark.asyncio
async def test_12_contexto_nao_owner_nao_recebe_ponte_historica():
    evidence = await historical_grade_write_evidence(
        FakeDb(), _context(owner=False), field="b2", period_number=2, period=PERIODS[2]
    )
    assert evidence is None


@pytest.mark.asyncio
async def test_13_periodo_que_encosta_no_valid_from_nao_e_historico():
    evidence = await historical_grade_write_evidence(
        FakeDb(),
        _context(),
        field="b2",
        period_number=2,
        period=("2026-05-01", DVD_VALID_FROM),
    )
    assert evidence is None


@pytest.mark.asyncio
async def test_14_periodo_posterior_ao_cutover_nao_recebe_ponte():
    evidence = await historical_grade_write_evidence(
        FakeDb(), _context(), field="b4", period_number=4, period=PERIODS[4]
    )
    assert evidence is None


@pytest.mark.asyncio
async def test_15_assignment_com_intervalo_invalido_nao_recebe_ponte():
    context = _context(assignment=_assignment(valid_until="2026-08-01"))
    evidence = await historical_grade_write_evidence(
        FakeDb(), context, field="b2", period_number=2, period=PERIODS[2]
    )
    assert evidence is None


@pytest.mark.asyncio
async def test_16_campo_b2_vazio_pode_ser_lancado_com_ownership_auditavel():
    wrapped = _build_historical_ownership_adapter(apply_grade_field_ownership)
    context = _context()
    ownership = await wrapped(
        FakeDb(),
        _user(),
        {"b2": None},
        {"b2": 8.5},
        context,
        periods=PERIODS,
        active_mantenedora_id="tenant-1",
    )
    snapshot = ownership["b2"]
    assert snapshot["assignment_id"] == "dvd-1"
    assert snapshot[HISTORICAL_WRITE_FLAG] is True
    assert snapshot[HISTORICAL_WRITE_SOURCE_FLAG] == "legacy-1"
    assert context.assignment["valid_from"] == DVD_VALID_FROM


@pytest.mark.asyncio
async def test_17_b3_com_intersecao_normal_nao_recebe_marcador_historico():
    wrapped = _build_historical_ownership_adapter(apply_grade_field_ownership)
    ownership = await wrapped(
        FakeDb(),
        _user(),
        {"b3": None},
        {"b3": 9.0},
        _context(),
        periods=PERIODS,
        active_mantenedora_id="tenant-1",
    )
    assert ownership["b3"]["assignment_id"] == "dvd-1"
    assert HISTORICAL_WRITE_FLAG not in ownership["b3"]


@pytest.mark.asyncio
async def test_18_sem_prova_38g_b_preserva_grade_period_outside_assignment():
    wrapped = _build_historical_ownership_adapter(apply_grade_field_ownership)
    db = FakeDb(legacy=False)
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await wrapped(
            db,
            _user(),
            {"b2": None},
            {"b2": 7.0},
            _context(),
            periods=PERIODS,
            active_mantenedora_id="tenant-1",
        )
    assert exc.value.code == "GRADE_PERIOD_OUTSIDE_ASSIGNMENT"


@pytest.mark.asyncio
async def test_19_legado_nao_nulo_sem_ownership_continua_exigindo_revisao():
    wrapped = _build_historical_ownership_adapter(apply_grade_field_ownership)
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await wrapped(
            FakeDb(),
            _user(),
            {"b2": 6.0},
            {"b2": 7.0},
            _context(),
            periods=PERIODS,
            active_mantenedora_id="tenant-1",
        )
    assert exc.value.code == "GRADE_LEGACY_FIELD_REQUIRES_REVIEW"


@pytest.mark.asyncio
async def test_20_owner_de_outro_assignment_continua_bloqueado():
    wrapped = _build_historical_ownership_adapter(apply_grade_field_ownership)
    foreign = dict(_context().snapshot)
    foreign["assignment_id"] = "dvd-other"
    existing = {"b2": 6.0, "grade_ownership": {"b2": foreign}}
    with pytest.raises(GradeAssignmentScopeError) as exc:
        await wrapped(
            FakeDb(),
            _user(),
            existing,
            {"b2": 7.0},
            _context(),
            periods=PERIODS,
            active_mantenedora_id="tenant-1",
        )
    assert exc.value.code == "GRADE_FIELD_OWNED_BY_OTHER_ASSIGNMENT"


def test_21_change_de_campo_historico_fica_explicito_na_auditoria():
    updated = {
        "grade_ownership": {
            "b2": {
                "assignment_id": "dvd-1",
                HISTORICAL_WRITE_FLAG: True,
                HISTORICAL_WRITE_SOURCE_FLAG: "legacy-1",
            }
        }
    }
    change = {"new": {"b2": 8.0}, "assignment_id": "dvd-1"}
    enriched = _historical_change_metadata(updated, change)
    assert enriched["historical_grade_write"] is True
    assert enriched["historical_fields"] == ["b2"]
    assert enriched["historical_source_legacy_assignment_ids"] == ["legacy-1"]


def test_22_change_normal_nao_recebe_falso_marcador_historico():
    updated = {"grade_ownership": {"b3": {"assignment_id": "dvd-1"}}}
    change = {"new": {"b3": 9.0}, "assignment_id": "dvd-1"}
    assert _historical_change_metadata(updated, change) == change
