"""P0 — proveniência histórica fail-closed para cutovers DVD ativados."""

from copy import deepcopy
from pathlib import Path
import re

import pytest

from services.dvd_cutover_legacy_provenance import (
    APPROVED_HISTORICAL_CUTOVER_PHASES,
    is_approved_historical_cutover,
    resolve_validated_cutover_legacy_assignment,
)


APPROVED_PHASES = {
    "38G-B",
    "SECOND_WAVE_2A-B",
    "SECOND_WAVE_2B",
    "SECOND_WAVE_2C",
    "SECOND_WAVE_2D_J",
}


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                if not projection:
                    return dict(doc)
                return {
                    key: value
                    for key, value in doc.items()
                    if projection.get(key, 1)
                }
        return None

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected:
                    if actual not in expected["$in"]:
                        return False
                    continue
                if "$regex" in expected:
                    flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
                    if re.search(expected["$regex"], str(actual or ""), flags) is None:
                        return False
                    continue
                raise AssertionError(f"Operador fake não suportado: {expected}")
            if actual != expected:
                return False
        return True


class FakeDb:
    def __init__(self, *, legacy=None, staff=None, users=None):
        self.teacher_assignments = FakeCollection(legacy or [])
        self.staff = FakeCollection(staff or [])
        self.users = FakeCollection(users or [])


def assignment(phase="38G-B", **overrides):
    doc = {
        "id": "dvd-1",
        "teacher_id": "user-1",
        "class_id": "class-1",
        "component_id": "course-1",
        "valid_from": "2026-08-18",
        "valid_until": None,
        "cutover_provenance": {
            "apply_phase": phase,
            "apply_state": "ACTIVATED",
            "source_legacy_assignment_id": "legacy-1",
        },
    }
    doc.update(overrides)
    return doc


def legacy(**overrides):
    doc = {
        "id": "legacy-1",
        "staff_id": "staff-1",
        "class_id": "class-1",
        "course_id": "course-1",
        "status": "ativo",
        "academic_year": 2026,
    }
    doc.update(overrides)
    return doc


def db_for(*, legacy_doc=None, staff_doc=None, user_doc=None):
    return FakeDb(
        legacy=[legacy_doc or legacy()],
        staff=[staff_doc or {"id": "staff-1", "user_id": "user-1", "email": "prof@example.org"}],
        users=[user_doc or {"id": "user-1", "email": "prof@example.org"}],
    )


def test_lista_de_fases_e_explicita_e_exata():
    assert APPROVED_HISTORICAL_CUTOVER_PHASES == APPROVED_PHASES


@pytest.mark.parametrize("phase", sorted(APPROVED_PHASES))
@pytest.mark.asyncio
async def test_todas_as_fases_aprovadas_revalidam_a_mesma_origem_sem_retrodatacao(phase):
    dvd = assignment(phase)
    before = deepcopy(dvd)

    result = await resolve_validated_cutover_legacy_assignment(
        db_for(),
        dvd,
        2026,
        expected_class_id="class-1",
        expected_component_id="course-1",
    )

    assert result["id"] == "legacy-1"
    assert dvd == before
    assert dvd["valid_from"] == "2026-08-18"


@pytest.mark.asyncio
async def test_second_wave_2b_com_staff_sem_user_id_usa_fallback_unico_por_email():
    dvd = assignment("SECOND_WAVE_2B")
    dvd["teacher_id"] = "teacher-email-fallback"
    database = db_for(
        staff_doc={
            "id": "staff-1",
            "user_id": None,
            "email": "teacher.fixture@example.org",
        },
        user_doc={
            "id": "teacher-email-fallback",
            "email": "teacher.fixture@example.org",
        },
    )

    result = await resolve_validated_cutover_legacy_assignment(
        database,
        dvd,
        2026,
        expected_class_id="class-1",
        expected_component_id="course-1",
    )

    assert result and result["id"] == "legacy-1"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d["cutover_provenance"].update({"apply_state": "PLANNED"}),
        lambda d: d["cutover_provenance"].update({"apply_phase": "FUTURE_UNKNOWN_WAVE"}),
        lambda d: d["cutover_provenance"].update({"source_legacy_assignment_id": None}),
    ],
)
def test_gate_inicial_falha_fechado(mutator):
    dvd = assignment()
    mutator(dvd)
    assert is_approved_historical_cutover(dvd) is False


@pytest.mark.asyncio
async def test_not_activated_permanece_bloqueado_sem_consultar_origem():
    dvd = assignment()
    dvd["cutover_provenance"]["apply_state"] = "PLANNED"
    database = FakeDb()

    result = await resolve_validated_cutover_legacy_assignment(database, dvd, 2026)

    assert result is None


@pytest.mark.parametrize(
    "legacy_doc",
    [
        legacy(status="inativo"),
        legacy(class_id="other-class"),
        legacy(course_id="other-course"),
        legacy(academic_year=2025),
    ],
)
@pytest.mark.asyncio
async def test_origem_legada_inconsistente_permanece_bloqueada(legacy_doc):
    result = await resolve_validated_cutover_legacy_assignment(
        db_for(legacy_doc=legacy_doc),
        assignment("SECOND_WAVE_2C"),
        2026,
        expected_class_id="class-1",
        expected_component_id="course-1",
    )
    assert result is None


@pytest.mark.asyncio
async def test_origem_legada_ausente_permanece_bloqueada():
    database = FakeDb(
        legacy=[],
        staff=[{"id": "staff-1", "user_id": "user-1"}],
        users=[{"id": "user-1"}],
    )
    result = await resolve_validated_cutover_legacy_assignment(
        database,
        assignment("SECOND_WAVE_2D_J"),
        2026,
    )
    assert result is None


@pytest.mark.asyncio
async def test_identidade_docente_divergente_permanece_bloqueada():
    database = db_for(
        staff_doc={"id": "staff-1", "user_id": "outro-user", "email": "prof@example.org"},
    )
    result = await resolve_validated_cutover_legacy_assignment(
        database,
        assignment("SECOND_WAVE_2A-B"),
        2026,
    )
    assert result is None


def test_servico_e_estritamente_read_only_e_nao_muta_valid_from():
    source = Path("services/dvd_cutover_legacy_provenance.py").read_text(encoding="utf-8")
    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".find_one_and_update(",
        "assignment[\"valid_from\"] =",
    )
    for token in forbidden:
        assert token not in source
