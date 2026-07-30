"""
Sprint 000 — Testes da Fundação do MIG (CMDE).

E4 (paridade): CmdeService reproduz exatamente as respostas dos endpoints atuais.
Unitários: mapper/validators e mapeamento de erros do BaseGovClient para exceções tipadas.
"""
import sys, os, asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    # Carrega backend/.env se as vars não estiverem no ambiente
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

from motor.motor_asyncio import AsyncIOMotorClient
from mig.cmde.service import CmdeService
from mig.cmde.mapper import CmdeMapper
from mig.cmde import validators
from mig.core.http_client import BaseGovClient
from mig.core.exceptions import MigAuthError, MigForbiddenError, MigTimeoutError, MigUnavailableError, MigConfigError


# ---------- Unitários: mapper/validators ----------
def test_mapper_validators():
    row = CmdeMapper.build_mapping_row(
        {"id": "1", "full_name": "Aluno X", "cpf": "", "nis": "123", "inep_code": ""},
        {"name": "Escola Y", "inep_code": "15175600"})
    assert row["ready"] is False and row["missing_fields"] == ["CPF"], row
    row2 = CmdeMapper.build_mapping_row(
        {"id": "2", "full_name": "Aluno Z", "cpf": "111", "nis": "222", "inep_code": ""},
        {"name": "Escola W", "inep_code": "999"})
    assert row2["ready"] is True and row2["missing_fields"] == [], row2
    # sem INEP da escola → não pronto, INEP Escola faltante
    row3 = CmdeMapper.build_mapping_row(
        {"id": "3", "full_name": "A", "cpf": "1", "nis": "", "inep_code": ""}, {})
    assert row3["ready"] is False and row3["missing_fields"] == ["NIS", "INEP Escola"], row3
    print("OK unit: mapper/validators")


# ---------- Unitários: mapeamento de erros do BaseGovClient ----------
def _fake_client_returning(status_code, text="erro", json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json = MagicMock(return_value=(json_data if json_data is not None else {"ok": True}))

    class _Ctx:
        def __init__(self_, *a, **k):
            pass
        async def __aenter__(self_):
            m = MagicMock()
            async def _req(*a, **k):
                return resp
            m.request = _req
            return m
        async def __aexit__(self_, *a):
            return False
    return _Ctx


async def _run_client_error_cases():
    import mig.core.http_client as hc
    for code, exc in [(401, MigAuthError), (403, MigForbiddenError)]:
        with patch.object(hc.httpx, "AsyncClient", _fake_client_returning(code)):
            c = BaseGovClient("http://x", provider="cmde")
            try:
                await c.get("/y"); assert False, "deveria levantar"
            except exc:
                pass
    # 200 retorna json
    with patch.object(hc.httpx, "AsyncClient", _fake_client_returning(200, json_data={"a": 1})):
        c = BaseGovClient("http://x", provider="cmde")
        assert await c.get("/y") == {"a": 1}
    print("OK unit: BaseGovClient status mapping")


# ---------- Paridade contra baseline (DB real) ----------
BASELINE_STATUS = {"students_total": 19, "students_with_cpf": 18, "students_with_nis": 19,
                   "schools_total": 6, "schools_with_inep": 6}
BASELINE_MAPPING = {"total": 19, "ready_count": 0, "not_ready_count": 19}


async def _run_parity():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    svc = CmdeService(db)

    status = await svc.sync_status()
    assert status["details"] == BASELINE_STATUS, status["details"]
    assert status["status"] == "not_configured" and status["environment"] == "homologacao"

    mapping = await svc.students_mapping()
    assert mapping["total"] == BASELINE_MAPPING["total"], mapping["total"]
    assert mapping["ready_count"] == BASELINE_MAPPING["ready_count"], mapping["ready_count"]
    assert mapping["not_ready_count"] == BASELINE_MAPPING["not_ready_count"]
    # shape das linhas idêntico ao endpoint atual
    sample = mapping["students"][0]
    assert set(sample.keys()) == {"id", "full_name", "cpf", "nis", "inep_code",
                                  "school_name", "school_inep", "ready", "missing_fields"}, sample.keys()

    cfg = await svc.get_config()
    assert cfg["status"] == "not_configured" and cfg["environment"] == "homologacao"
    # PGP removido (decisão Sprint 000)
    assert "pgp_public_key" not in cfg and "pgp_private_key_configured" not in cfg, cfg

    # elegibilidades sem config → MigConfigError (mesma msg do baseline)
    try:
        await svc.query(search="123"); assert False
    except MigConfigError as e:
        assert "não configurada" in e.message.lower()
    print("OK paridade: sync_status, students_mapping, get_config, query(400)")


if __name__ == "__main__":
    test_mapper_validators()
    asyncio.run(_run_client_error_cases())
    asyncio.run(_run_parity())
    print("\nSPRINT 000 — TODOS OS TESTES PASSARAM ✅")
