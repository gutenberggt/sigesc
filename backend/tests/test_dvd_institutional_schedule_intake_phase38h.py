import copy
import json
import runpy
import sys
from pathlib import Path

import pymongo


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = (
    BACKEND_DIR
    / "scripts"
    / "validate_dvd_institutional_schedule_intake.py"
)


class _FakeAdmin:
    def command(self, name):
        assert name == "ping"
        return {"ok": 1}


class _FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *args, **kwargs):
        return copy.deepcopy(self.rows)


class _FakeDB:
    def __init__(self, *, classes, schedules):
        self.classes = _FakeCollection(classes)
        self.class_schedules = _FakeCollection(schedules)


class _FakeClient:
    def __init__(
        self,
        *args,
        classes=None,
        schedules=None,
        **kwargs,
    ):
        self.admin = _FakeAdmin()
        self._db = _FakeDB(
            classes=classes or [],
            schedules=schedules or [],
        )

    def __getitem__(self, name):
        assert name == "sigesc"
        return self._db

    def close(self):
        pass


def _base_entry():
    return {
        "school_id": "school-1",
        "school_name": "Escola Teste",
        "class_id": "class-1",
        "class_name": "Turma Teste",
        "academic_year": 2026,
        "shift": "morning",
        "operation": "CREATE",
        "existing_schedule_id": None,
        "components": [
            {
                "course_id": "course-1",
                "course_name": "Componente 1",
            },
            {
                "course_id": "course-2",
                "course_name": "Componente 2",
            },
        ],
        "institutional_input": {
            "slots_per_day_confirmed": None,
            "slot_times_confirmed": {},
            "schedule_slots_confirmed": [],
            "institutional_source": None,
            "confirmed_by": None,
            "confirmation_date": None,
            "notes": None,
        },
    }


def _complete_input():
    return {
        "slots_per_day_confirmed": 2,
        "slot_times_confirmed": {
            "1": {
                "start": "07:00",
                "end": "07:45",
            },
            "2": {
                "start": "07:45",
                "end": "08:30",
            },
        },
        "schedule_slots_confirmed": [
            {
                "day": "segunda",
                "slot_number": 1,
                "course_id": "course-1",
            },
            {
                "day": "terca",
                "slot_number": 2,
                "course_id": "course-2",
            },
        ],
        "institutional_source": "Documento institucional",
        "confirmed_by": "Responsável Teste",
        "confirmation_date": "2026-08-18",
        "notes": None,
    }


def _run_validator(
    monkeypatch,
    tmp_path,
    *,
    institutional_input=None,
):
    entry = _base_entry()

    if institutional_input is not None:
        entry["institutional_input"] = copy.deepcopy(
            institutional_input
        )

    input_path = tmp_path / "input.json"
    report_path = tmp_path / "report.json"

    input_path.write_text(
        json.dumps(
            {
                "classes": [entry],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    classes = [
        {
            "id": "class-1",
            "school_id": "school-1",
            "academic_year": 2026,
            "shift": "morning",
        }
    ]

    def fake_client_factory(*args, **kwargs):
        return _FakeClient(
            *args,
            classes=classes,
            schedules=[],
            **kwargs,
        )

    monkeypatch.setattr(
        pymongo,
        "MongoClient",
        fake_client_factory,
    )

    monkeypatch.setenv(
        "MONGO_URL",
        "mongodb://fake/sigesc",
    )

    monkeypatch.setenv(
        "DB_NAME",
        "sigesc",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--input",
            str(input_path),
            "--report",
            str(report_path),
        ],
    )

    runpy.run_path(
        str(SCRIPT),
        run_name="__main__",
    )

    return json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )


def _single_result(report):
    rows = report["classes"]
    assert len(rows) == 1
    return rows[0]


def test_baseline_without_confirmation_is_pending(
    monkeypatch,
    tmp_path,
):
    report = _run_validator(
        monkeypatch,
        tmp_path,
    )

    result = _single_result(report)

    assert result["state"] == "PENDING"
    assert result["errors"] == []

    assert set(
        result["pending_fields"]
    ) == {
        "confirmation_date",
        "confirmed_by",
        "institutional_source",
        "schedule_slots_confirmed",
        "slot_times_confirmed",
        "slots_per_day_confirmed",
    }


def test_complete_confirmation_is_ready_for_dry_run(
    monkeypatch,
    tmp_path,
):
    report = _run_validator(
        monkeypatch,
        tmp_path,
        institutional_input=_complete_input(),
    )

    result = _single_result(report)

    assert result["state"] == "READY_FOR_DRY_RUN"
    assert result["errors"] == []
    assert result["pending_fields"] == []


def test_missing_slot_times_remains_pending_not_invalid(
    monkeypatch,
    tmp_path,
):
    data = _complete_input()
    data["slot_times_confirmed"] = {}

    report = _run_validator(
        monkeypatch,
        tmp_path,
        institutional_input=data,
    )

    result = _single_result(report)

    assert result["state"] == "PENDING"
    assert result["errors"] == []
    assert result["pending_fields"] == [
        "slot_times_confirmed"
    ]


def test_invalid_supplied_time_is_invalid(
    monkeypatch,
    tmp_path,
):
    data = _complete_input()

    data["slot_times_confirmed"]["1"] = {
        "start": "09:00",
        "end": "08:00",
    }

    report = _run_validator(
        monkeypatch,
        tmp_path,
        institutional_input=data,
    )

    result = _single_result(report)

    assert result["state"] == "INVALID"
    assert "INVALID_SLOT_TIME_PAIR" in result["errors"]


def test_unknown_component_is_invalid(
    monkeypatch,
    tmp_path,
):
    data = _complete_input()

    data["schedule_slots_confirmed"][0][
        "course_id"
    ] = "course-invalid"

    report = _run_validator(
        monkeypatch,
        tmp_path,
        institutional_input=data,
    )

    result = _single_result(report)

    assert result["state"] == "INVALID"
    assert "UNKNOWN_COURSE_ID" in result["errors"]


def test_duplicate_day_slot_is_invalid(
    monkeypatch,
    tmp_path,
):
    data = _complete_input()

    data[
        "schedule_slots_confirmed"
    ].append(
        {
            "day": "segunda",
            "slot_number": 1,
            "course_id": "course-2",
        }
    )

    report = _run_validator(
        monkeypatch,
        tmp_path,
        institutional_input=data,
    )

    result = _single_result(report)

    assert result["state"] == "INVALID"
    assert "DUPLICATE_DAY_SLOT" in result["errors"]


def test_source_contains_no_mongodb_mutators():
    text = SCRIPT.read_text(
        encoding="utf-8"
    )

    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        ".create_index(",
        ".drop_index(",
        ".find_one_and_update(",
        ".find_one_and_delete(",
        ".find_one_and_replace(",
    )

    for token in forbidden:
        assert token not in text, (
            "Validador institucional read-only contém "
            f"mutador MongoDB: {token}"
        )
