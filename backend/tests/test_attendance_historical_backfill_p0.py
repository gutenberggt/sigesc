"""P0 — regressão do lançamento histórico de Frequência após cutover DVD.

Caso real que motivou o guard:
Ivanilde Freire Batista da Silva → E M E I E F 22 de Abril → 3º/4º/5º ANO
→ Arte → 01/06/2026, com DVD iniciado em 18/08/2026.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from services.attendance_assignment_scope import (
    AttendanceAssignmentContext,
    AttendanceAssignmentScopeError,
)
from services.diary_assignment_contract import (
    AttendanceMode,
    AttendancePurpose,
    DiaryProfile,
    StudentScope,
)


# O guard unitário roda com dependências mínimas e não deve importar o pacote
# routers/__init__.py inteiro. O módulo P0 usa apenas HTTPException como tipo de
# erro em caminhos que estes testes não executam; um stub preserva o isolamento.
if "fastapi" not in sys.modules:
    fastapi_stub = ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_stub.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi_stub

MODULE_PATH = Path(__file__).resolve().parents[1] / "routers" / "attendance_historical_backfill_dvd.py"
SPEC = importlib.util.spec_from_file_location("attendance_historical_backfill_dvd_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
BACKFILL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BACKFILL
SPEC.loader.exec_module(BACKFILL)

HISTORICAL_BACKFILL_FLAG = BACKFILL.HISTORICAL_BACKFILL_FLAG
HISTORICAL_BACKFILL_SOURCE = BACKFILL.HISTORICAL_BACKFILL_SOURCE
_build_historical_resolver = BACKFILL._build_historical_resolver


IVANILDE_ASSIGNMENT_ID = "77fd25ee-5157-54d0-9806-81dae056d7b3"
TARGET_DATE = "2026-06-01"
DVD_VALID_FROM = "2026-08-18"


class FakeCollection:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if not projection:
                    return dict(doc)
                return {
                    key: value
                    for key, value in doc.items()
                    if projection.get(key, 1)
                }
        return None


class FakeDb:
    def __init__(self, assignment):
        self.teacher_class_assignments = FakeCollection([assignment])


def _assignment(**overrides):
    doc = {
        "id": IVANILDE_ASSIGNMENT_ID,
        "teacher_id": "ivanilde-user",
        "teacher_name": "Ivanilde Freire Batista da Silva",
        "class_id": "multisseriada-345",
        "class_name": "3º/4º/5º ANO",
        "component_id": "arte",
        "school_id": "22-de-abril",
        "mantenedora_id": "tenant-1",
        "valid_from": DVD_VALID_FROM,
        "valid_until": None,
        "deleted": False,
        "cutover_provenance": {
            "apply_phase": "38G-B",
            "apply_state": "ACTIVATED",
            "source_legacy_assignment_id": "legacy-ivanilde-arte",
        },
    }
    doc.update(overrides)
    return doc


def _context(assignment):
    return AttendanceAssignmentContext(
        assignment=assignment,
        class_info={
            "id": assignment["class_id"],
            "name": assignment["class_name"],
            "school_id": assignment["school_id"],
            "mantenedora_id": assignment["mantenedora_id"],
            "academic_year": 2026,
        },
        profile=DiaryProfile.REGULAR,
        student_scope=StudentScope.ALL,
        attendance_mode=AttendanceMode.CLASS_DAILY,
        attendance_purpose=AttendancePurpose.OFFICIAL,
        effective_course_id=None,
        session_slots=tuple(),
        storage_collection="attendance",
        snapshot={
            "assignment_id": assignment["id"],
            "teacher_id": assignment["teacher_id"],
            "class_id": assignment["class_id"],
            "school_id": assignment["school_id"],
            "mantenedora_id": assignment["mantenedora_id"],
        },
    )


@pytest.mark.asyncio
async def test_ivanilde_01062026_reusa_cutover_como_prova_sem_retrodatacao():
    assignment = _assignment()
    db = FakeDb(assignment)
    calls = []

    async def base_resolver(_db, _user, _assignment_id, **kwargs):
        calls.append(kwargs.get("on_date"))
        if kwargs.get("on_date") == TARGET_DATE:
            raise AttendanceAssignmentScopeError(
                "ASSIGNMENT_NOT_ACTIVE",
                "O vínculo não está vigente na data solicitada.",
            )
        assert kwargs.get("on_date") == DVD_VALID_FROM
        return _context(assignment)

    async def safe_cutover(_db, context, academic_year):
        assert context.assignment["id"] == IVANILDE_ASSIGNMENT_ID
        assert academic_year == 2026
        return {"id": "legacy-ivanilde-arte"}

    tabs_mod = SimpleNamespace(_safe_cutover_legacy_assignment=safe_cutover)
    resolver = _build_historical_resolver(base_resolver, tabs_mod)

    result = await resolver(
        db,
        {"id": "ivanilde-user", "role": "professor"},
        IVANILDE_ASSIGNMENT_ID,
        on_date=TARGET_DATE,
    )

    assert calls == [TARGET_DATE, DVD_VALID_FROM]
    assert result.assignment["valid_from"] == DVD_VALID_FROM
    assert result.snapshot[HISTORICAL_BACKFILL_FLAG] is True
    assert result.snapshot["historical_backfill_date"] == TARGET_DATE
    assert result.snapshot["historical_backfill_authorized_from"] == DVD_VALID_FROM
    assert result.snapshot["historical_backfill_source"] == HISTORICAL_BACKFILL_SOURCE
    assert result.snapshot["historical_backfill_source_legacy_assignment_id"] == "legacy-ivanilde-arte"


@pytest.mark.asyncio
async def test_sem_proveniencia_38g_b_permanece_bloqueado():
    assignment = _assignment()
    db = FakeDb(assignment)

    async def base_resolver(_db, _user, _assignment_id, **kwargs):
        if kwargs.get("on_date") == TARGET_DATE:
            raise AttendanceAssignmentScopeError("ASSIGNMENT_NOT_ACTIVE", "fora da vigência")
        return _context(assignment)

    async def no_cutover(*_args, **_kwargs):
        return None

    resolver = _build_historical_resolver(
        base_resolver,
        SimpleNamespace(_safe_cutover_legacy_assignment=no_cutover),
    )
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await resolver(
            db,
            {"id": "ivanilde-user", "role": "professor"},
            IVANILDE_ASSIGNMENT_ID,
            on_date=TARGET_DATE,
        )
    assert exc.value.code == "ASSIGNMENT_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_data_apos_valid_from_nao_usa_backfill_para_contornar_expiracao():
    assignment = _assignment(valid_until="2026-08-31")
    db = FakeDb(assignment)
    validator_called = False

    async def base_resolver(*_args, **_kwargs):
        raise AttendanceAssignmentScopeError("ASSIGNMENT_NOT_ACTIVE", "fora da vigência")

    async def validator(*_args, **_kwargs):
        nonlocal validator_called
        validator_called = True
        return {"id": "legacy-ivanilde-arte"}

    resolver = _build_historical_resolver(
        base_resolver,
        SimpleNamespace(_safe_cutover_legacy_assignment=validator),
    )
    with pytest.raises(AttendanceAssignmentScopeError) as exc:
        await resolver(
            db,
            {"id": "ivanilde-user", "role": "professor"},
            IVANILDE_ASSIGNMENT_ID,
            on_date="2026-09-10",
        )
    assert exc.value.code == "ASSIGNMENT_NOT_ACTIVE"
    assert validator_called is False


def test_legado_editado_nao_recebe_assignment_id_retroativo():
    source = Path("routers/attendance_historical_backfill_dvd.py").read_text(encoding="utf-8")
    block = source.split("async def _update_legacy_historical_day", 1)[1].split(
        "def install_attendance_historical_backfill_dvd", 1
    )[0]
    assert '"historical_backfill_last_authorized_assignment_id"' in block
    assert '"assignment_id": payload.assignment_id' in block  # auditoria apenas
    update_block = block.split("update_data = {", 1)[1].split("}", 1)[0]
    assert '"assignment_id"' not in update_block
    assert "Deliberadamente NÃO adiciona assignment_id" in block


def test_instalacao_ocorre_depois_da_paridade_das_abas_e_antes_do_pdf():
    source = Path("routers/__init__.py").read_text(encoding="utf-8")
    phase4 = source.index("install_attendance_dvd_adapter")
    tabs = source.index("install_attendance_tabs_dvd_adapter")
    historical = source.index("install_attendance_historical_backfill_dvd")
    pdf = source.index("install_attendance_pdf_dvd_parity")
    assert phase4 < tabs < historical < pdf
