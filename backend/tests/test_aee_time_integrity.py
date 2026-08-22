import asyncio
from copy import deepcopy

import pytest
from fastapi import APIRouter, FastAPI, HTTPException

from aee_v2.time_integrity import (
    classify_time_interval,
    install_aee_time_integrity,
    validate_time_interval,
)


class Payload:
    def __init__(self, **data):
        self.data = data

    def model_dump(self, exclude_unset=False):
        assert exclude_unset is True
        return deepcopy(self.data)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = deepcopy(docs or [])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return deepcopy(doc)
        return None


class FakeDB:
    def __init__(self):
        self.collections = {
            "planos_aee": FakeCollection([
                {"id": "p1", "horario_inicio": "13:30", "horario_fim": "15:00"}
            ]),
            "atendimentos_aee": FakeCollection([
                {"id": "a1", "horario_inicio": "15:30", "horario_fim": "17:00"}
            ]),
        }

    def __getitem__(self, name):
        return self.collections[name]


def _router():
    router = APIRouter(prefix="/aee")

    @router.post("/planos")
    async def create_plano_aee(plano_data=None):
        return {"ok": True}

    @router.put("/planos/{plano_id}")
    async def update_plano_aee(plano_id: str, plano_update=None):
        return {"ok": True}

    @router.post("/atendimentos")
    async def create_atendimento_aee(atendimento_data=None):
        return {"ok": True}

    @router.put("/atendimentos/{atendimento_id}")
    async def update_atendimento_aee(atendimento_id: str, atendimento_update=None):
        return {"ok": True}

    return router


def _route(routes, path, method):
    return next(
        route for route in routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    )


def test_valid_afternoon_intervals_are_accepted():
    assert validate_time_interval("13:30", "15:00") == 90
    assert validate_time_interval("15:30", "17:00") == 90


def test_early_morning_typo_is_rejected():
    with pytest.raises(Exception, match="06:00 e 22:00"):
        validate_time_interval("03:30", "05:00")


def test_inverted_interval_is_rejected():
    with pytest.raises(Exception):
        validate_time_interval("13:30", "03:00")


def test_audit_classifier_explains_known_bad_cases():
    first = classify_time_interval("03:30", "05:00")
    codes = {issue["code"] for issue in first["issues"]}
    assert "AEE_TIME_START_OUTSIDE_WINDOW" in codes
    assert "AEE_TIME_END_OUTSIDE_WINDOW" in codes

    second = classify_time_interval("13:30", "03:00", stored_duration=810)
    codes = {issue["code"] for issue in second["issues"]}
    assert "AEE_TIME_END_OUTSIDE_WINDOW" in codes
    assert "AEE_TIME_END_NOT_AFTER_START" in codes


def test_stored_duration_mismatch_is_detected():
    result = classify_time_interval("09:30", "11:00", stored_duration=120)
    assert result["duration_minutes"] == 90
    assert any(i["code"] == "AEE_TIME_STORED_DURATION_MISMATCH" for i in result["issues"])


def test_route_guard_blocks_invalid_create_and_preserves_valid_create():
    async def scenario():
        router = _router()
        install_aee_time_integrity(router, FakeDB())

        create_plan = _route(router.routes, "/aee/planos", "POST")
        with pytest.raises(HTTPException) as exc:
            await create_plan.endpoint(
                plano_data=Payload(horario_inicio="03:30", horario_fim="05:00")
            )
        assert exc.value.status_code == 422
        assert "AEE_TIME_START_OUTSIDE_WINDOW" in str(exc.value.detail)

        result = await create_plan.endpoint(
            plano_data=Payload(horario_inicio="15:30", horario_fim="17:00")
        )
        assert result == {"ok": True}

    asyncio.run(scenario())


def test_partial_update_merges_existing_pair_before_validation():
    async def scenario():
        router = _router()
        install_aee_time_integrity(router, FakeDB())
        update_plan = _route(router.routes, "/aee/planos/{plano_id}", "PUT")

        result = await update_plan.endpoint(
            plano_id="p1",
            plano_update=Payload(horario_fim="16:00"),
        )
        assert result == {"ok": True}

        with pytest.raises(HTTPException):
            await update_plan.endpoint(
                plano_id="p1",
                plano_update=Payload(horario_fim="03:00"),
            )

    asyncio.run(scenario())


def test_attendance_guard_blocks_inverted_interval():
    async def scenario():
        router = _router()
        install_aee_time_integrity(router, FakeDB())
        create_attendance = _route(router.routes, "/aee/atendimentos", "POST")

        with pytest.raises(HTTPException) as exc:
            await create_attendance.endpoint(
                atendimento_data=Payload(horario_inicio="13:30", horario_fim="03:00")
            )
        assert exc.value.status_code == 422

    asyncio.run(scenario())


def test_guard_is_idempotent_and_survives_fastapi_include_router():
    router = _router()
    db = FakeDB()
    install_aee_time_integrity(router, db)
    wrapped = _route(router.routes, "/aee/planos", "POST").endpoint
    install_aee_time_integrity(router, db)
    assert _route(router.routes, "/aee/planos", "POST").endpoint is wrapped

    app = FastAPI()
    app.include_router(router, prefix="/api")
    final_route = _route(app.routes, "/api/aee/planos", "POST")
    assert final_route.endpoint.__code__.co_filename.endswith("/aee_v2/time_integrity.py")
    assert hasattr(final_route.endpoint, "__wrapped__")
