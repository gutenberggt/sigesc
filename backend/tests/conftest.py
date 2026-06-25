"""
conftest — provisionamento de ESTADO ISOLADO para a 2ª camada do gate de regressão
(suíte da Transferência Institucional) em ambientes de banco limpo (CI).

Só age quando `CI_SEED_TRANSFER=1`. Em dev/preview (sem essa env) NÃO faz nada,
preservando o comportamento original das suítes contra dados reais.

Garante:
  - 1 mantenedora dedicada + 3 escolas ativas (mesma mantenedora) com calendário 2025
    → atende `_pick_two_schools_same_mantenedora` (Fase 1) e `_dest_with_calendar` (rollback).
  - Reset de estado ANTES de cada teste: reativa as escolas do sandbox e remove
    turmas/dados residuais → impede cascata entre testes (ex.: escola encerrada por
    uma transferência anterior). Tudo marcado `ci_fixture: true` e removido ao final.
"""
import os
from pathlib import Path
from datetime import datetime, timezone

import pytest
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_ENABLED = os.environ.get("CI_SEED_TRANSFER") == "1"
_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

MANT = "CITX-MANT"
SCHOOLS = ["CITX-SCH-0", "CITX-SCH-1", "CITX-SCH-2"]
YEAR = 2025
_MARKED_COLLS = ["mantenedoras", "schools", "calendario_letivo", "classes", "students",
                 "enrollments", "attendance", "grades", "content_entries",
                 "planos_aee", "bolsa_familia_tracking"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _purge():
    for coll in _MARKED_COLLS:
        _db[coll].delete_many({"ci_fixture": True})


def _seed():
    _purge()
    _db.mantenedoras.insert_one({"ci_fixture": True, "id": MANT, "nome": "CI TRANSFER MANT",
                                 "name": "CI TRANSFER MANT", "created_at": _now()})
    for sid in SCHOOLS:
        _db.schools.insert_one({"ci_fixture": True, "id": sid, "name": f"CI {sid}",
                                "mantenedora_id": MANT, "status": "active",
                                "niveis_ensino_oferecidos": ["educacao_infantil"],
                                "educacao_infantil": True, "anos_letivos_ativos": [YEAR],
                                "created_at": _now()})
        _db.calendario_letivo.insert_one({"ci_fixture": True, "id": f"CITX-CAL-{sid}",
                                          "ano_letivo": YEAR, "school_id": sid,
                                          "mantenedora_id": MANT, "dias_letivos_previstos": 200})


def _reactivate():
    """Antes de cada teste: reativa escolas do sandbox e limpa turmas residuais."""
    _db.schools.update_many({"id": {"$in": SCHOOLS}}, {"$set": {"status": "active"}})
    cids = [c["id"] for c in _db.classes.find({"school_id": {"$in": SCHOOLS}}, {"_id": 0, "id": 1})]
    if cids:
        for coll in ["students", "enrollments", "attendance", "grades", "content_entries",
                     "student_dependencies", "teacher_class_assignments"]:
            _db[coll].delete_many({"class_id": {"$in": cids}})
        _db.classes.delete_many({"id": {"$in": cids}})


@pytest.fixture(scope="session", autouse=True)
def _ci_transfer_world():
    if not _ENABLED:
        yield
        return
    _seed()
    yield
    _purge()


@pytest.fixture(autouse=True)
def _ci_transfer_reset():
    if _ENABLED:
        _reactivate()
    yield
