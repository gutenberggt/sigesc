"""Contrato do P0 AEE — reparo histórico controlado de 14 documentos."""

import asyncio
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys


# O Contract Guard é isolado e não instala motor. O script usa Motor somente no
# entrypoint; para testar a lógica pura/fake DB, basta um stub de importação.
motor_pkg = ModuleType("motor")
motor_asyncio = ModuleType("motor.motor_asyncio")
motor_asyncio.AsyncIOMotorClient = object
motor_pkg.motor_asyncio = motor_asyncio
sys.modules.setdefault("motor", motor_pkg)
sys.modules.setdefault("motor.motor_asyncio", motor_asyncio)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_aee_time_integrity_2026_p0.py"
spec = importlib.util.spec_from_file_location("repair_aee_time_integrity_2026_p0", SCRIPT)
repair = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(repair)


class FakeCursor:
    def __init__(self, docs):
        self.docs = deepcopy(docs)

    async def to_list(self, _length):
        return deepcopy(self.docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.update_filters = []
        self.inserted = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                result = deepcopy(doc)
                if projection and projection.get("_id") == 0:
                    result.pop("_id", None)
                return result
        return None

    def find(self, query, projection=None):
        docs = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    ok = doc.get(key) in value["$in"]
                else:
                    ok = doc.get(key) == value
                if not ok:
                    break
            if ok:
                docs.append(doc)
        return FakeCursor(docs)

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))
        self.inserted.append(deepcopy(doc))
        return SimpleNamespace(acknowledged=True)

    async def update_one(self, query, update):
        self.update_filters.append(deepcopy(query))
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                before = deepcopy(doc)
                doc.update(deepcopy(update.get("$set", {})))
                return SimpleNamespace(
                    matched_count=1,
                    modified_count=1 if doc != before else 0,
                )
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def replace_one(self, query, replacement):
        for index, doc in enumerate(self.docs):
            if all(doc.get(key) == value for key, value in query.items()):
                self.docs[index] = deepcopy(replacement)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class FakeDB:
    def __init__(self, *, heads=None):
        plans = []
        for target in repair.PLAN_TARGETS:
            plans.append({"id": target["id"], **deepcopy(target["expected"])})

        attendances = []
        for target in repair.ATTENDANCE_TARGETS:
            attendances.append({"id": target["id"], **deepcopy(target["expected"])})

        self.planos_aee = FakeCollection(plans)
        self.atendimentos_aee = FakeCollection(attendances)
        self.aee_dossier_v2_heads = FakeCollection(heads or [])
        self.backup = FakeCollection()

    def __getitem__(self, name):
        if name == repair.BACKUP_COLLECTION:
            return self.backup
        if name == "planos_aee":
            return self.planos_aee
        if name == "atendimentos_aee":
            return self.atendimentos_aee
        raise KeyError(name)


def test_repair_targets_are_exactly_the_14_audited_documents():
    ids = [t["id"] for t in repair.PLAN_TARGETS + repair.ATTENDANCE_TARGETS]

    assert len(repair.PLAN_TARGETS) == 2
    assert len(repair.ATTENDANCE_TARGETS) == 12
    assert len(ids) == 14
    assert len(set(ids)) == 14

    samuel = repair.PLAN_TARGETS[0]
    nicollas = repair.PLAN_TARGETS[1]
    assert samuel["expected"]["horario_inicio"] == "03:30"
    assert samuel["expected"]["horario_fim"] == "05:00"
    assert samuel["update"] == {"horario_inicio": "15:30", "horario_fim": "17:00"}
    assert nicollas["expected"]["horario_fim"] == "03:00"
    assert nicollas["update"] == {"horario_inicio": "13:30", "horario_fim": "15:00"}
    assert all(t["update"]["duracao_minutos"] == 90 for t in repair.ATTENDANCE_TARGETS)


def test_exact_filter_contains_id_and_expected_old_values():
    target = repair.ATTENDANCE_TARGETS[0]
    query = repair._exact_filter(target)

    assert query == {
        "id": target["id"],
        "plano_aee_id": repair.NICOLLAS_PLAN_ID,
        "horario_inicio": "13:30",
        "horario_fim": "03:00",
        "duracao_minutos": 810,
    }


def test_precheck_passes_only_when_all_targets_match_and_no_v2_head_exists():
    db = FakeDB()
    result = asyncio.run(repair._precheck(db))

    assert result["ok"] is True
    assert result["errors"] == []
    assert len(result["plan_docs"]) == 2
    assert len(result["attendance_docs"]) == 12
    assert result["heads"] == []


def test_precheck_blocks_legacy_repair_if_target_plan_has_v2_head():
    db = FakeDB(
        heads=[
            {
                "id": "head-1",
                "legacy_plano_id": repair.NICOLLAS_PLAN_ID,
                "active_snapshot_id": "snapshot-1",
                "working_snapshot_id": None,
            }
        ]
    )
    result = asyncio.run(repair._precheck(db))

    assert result["ok"] is False
    assert any(error["code"] == "AEE_V2_HEAD_PRESENT" for error in result["errors"])


def test_apply_writes_backup_then_updates_only_exact_targets_and_postcheck_passes():
    async def scenario():
        db = FakeDB()
        precheck = await repair._precheck(db)
        assert precheck["ok"] is True

        result = await repair._apply(db, precheck)
        assert result["changed"] == 14

        assert len(db.backup.inserted) == 1
        backup = db.backup.inserted[0]
        assert backup["operation_id"] == repair.OPERATION_ID
        assert backup["targets_count"] == 14
        assert len(backup["plans_before"]) == 2
        assert len(backup["attendances_before"]) == 12

        assert len(db.planos_aee.update_filters) == 2
        assert len(db.atendimentos_aee.update_filters) == 12
        assert all("id" in query for query in db.planos_aee.update_filters)
        assert all("id" in query for query in db.atendimentos_aee.update_filters)
        assert all(query.get("horario_fim") == "03:00" for query in db.atendimentos_aee.update_filters)
        assert all(query.get("duracao_minutos") == 810 for query in db.atendimentos_aee.update_filters)

        postcheck = await repair._postcheck(db)
        assert postcheck == {"ok": True, "errors": []}

    asyncio.run(scenario())


def test_script_has_no_broad_update_many_or_delete_operations():
    source = SCRIPT.read_text(encoding="utf-8")

    assert ".update_many(" not in source
    assert ".delete_many(" not in source
    assert ".delete_one(" not in source
    assert "--apply" in source
    assert "DRY-RUN" in source
