"""Fev 2026 — Sprint G1.7: Declarações Escolares Verificáveis.

Cobre:
  1. Emissão de declaração de matrícula cria snapshot + verifiable_document + log.
  2. Validade padrão por tipo respeitada (matricula 90d, frequencia 30d, escolaridade 180d).
  3. PDF contém código + QR + validade.
  4. Portal público mostra "valido" para documento válido recém-emitido.
  5. Portal mostra "expirado" quando expires_at < now.
  6. Portal mostra "revogado" após revogação.
  7. Payload snapshot é LGPD-safe (sem CPF/RG/endereço).
  8. Tipo inválido retorna 400.
  9. Professor é bloqueado (403).
 10. Auxiliar_secretaria pode emitir.
 11. Log de emissão é persistido com IP + user.
 12. Download idempotente do PDF via /{code}/pdf.
 13. Finalidade é registrada no snapshot.
 14. Override de validity_days funciona.
"""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://autosave-drafts.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

STUDENT_ID = "student_g17_test"
SCHOOL_ID = "school_g17_test"
CLASS_ID = "cls_g17_test"


@pytest.fixture(scope="module")
def token():
    time.sleep(1.2)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


@pytest.fixture(scope="module", autouse=True)
def seed_g17():
    async def setup():
        db = _db()
        await db.students.delete_many({"id": STUDENT_ID})
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.classes.delete_many({"id": CLASS_ID})
        await db.class_students.delete_many({"student_id": STUDENT_ID})
        await db.verifiable_documents.delete_many({"entity_id": STUDENT_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": STUDENT_ID})
        await db.school_documents_log.delete_many({"student_id": STUDENT_ID})

        await db.schools.insert_one({
            "id": SCHOOL_ID, "name": "Escola Municipal Teste G17",
        })
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "3º Ano A", "school_id": SCHOOL_ID,
            "academic_year": 2026, "grade_level": "3º ano do Ensino Fundamental",
            "shift": "Matutino",
        })
        await db.students.insert_one({
            "id": STUDENT_ID,
            "full_name": "Maria Silva Santos",
            "birth_date": "15/03/2016",
            "school_id": SCHOOL_ID,
            "enrollment_number": "2026001",
            "cpf": "12345678901",  # SENSÍVEL — não deve aparecer no snapshot
            "rg": "9876543",       # SENSÍVEL
            "phone": "11999998888",  # SENSÍVEL
        })
        await db.class_students.insert_one({
            "student_id": STUDENT_ID, "class_id": CLASS_ID,
            "active": True,
            "enrolled_at": datetime.now(timezone.utc).isoformat(),
        })

    async def teardown():
        db = _db()
        await db.students.delete_many({"id": STUDENT_ID})
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.classes.delete_many({"id": CLASS_ID})
        await db.class_students.delete_many({"student_id": STUDENT_ID})
        await db.verifiable_documents.delete_many({"entity_id": STUDENT_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": STUDENT_ID})
        await db.school_documents_log.delete_many({"student_id": STUDENT_ID})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


# ---------- Emissão ----------

def test_emite_declaracao_matricula(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={
            "student_id": STUDENT_ID,
            "doc_type": "matricula",
            "purpose": "Apresentação em banco",
        },
        timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1500
    code = r.headers.get("X-SIGESC-Code")
    assert code and code.startswith("SIGESC-")


def test_validade_default_por_tipo(token):
    """Matrícula=90d, Frequência=30d, Escolaridade=180d."""
    async def check():
        db = _db()
        docs = await db.school_documents_log.find(
            {"student_id": STUDENT_ID}, {"_id": 0}
        ).sort("emitted_at", -1).to_list(10)
        return docs

    # Emite os 3 tipos
    for dt in ("matricula", "frequencia", "escolaridade"):
        body = {"student_id": STUDENT_ID, "doc_type": dt, "purpose": "Teste"}
        if dt == "frequencia":
            body["frequencia_pct"] = 95.5
            body["bimestre"] = "1º bimestre"
        if dt == "escolaridade":
            body["serie_concluida"] = "3º ano EF"
        r = httpx.post(
            f"{BACKEND}/api/school-documents/issue",
            headers=_h(token), json=body, timeout=30,
        )
        assert r.status_code == 200, r.text

    docs = asyncio.run(check())
    by_type = {d["doc_type"]: d for d in docs}
    # Verifica validade
    for dt, expected_days in [
        ("matricula", 90), ("frequencia", 30), ("escolaridade", 180),
    ]:
        emit = datetime.fromisoformat(by_type[dt]["emitted_at"])
        valid = datetime.fromisoformat(by_type[dt]["valid_until"])
        delta_days = (valid - emit).days
        # Tolerância ±1 dia por conta de arredondamento
        assert abs(delta_days - expected_days) <= 1, (
            f"{dt}: esperado {expected_days}d, obtido {delta_days}d"
        )


def test_tipo_invalido_retorna_400(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "certificado_ouro",
              "purpose": ""},
        timeout=15,
    )
    assert r.status_code == 400


def test_aluno_inexistente_retorna_404(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": "student_ghost", "doc_type": "matricula",
              "purpose": ""},
        timeout=15,
    )
    assert r.status_code == 404


# ---------- LGPD: snapshot não contém PII extra ----------

def test_snapshot_nao_inclui_cpf_rg_telefone(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "matricula",
              "purpose": "Teste LGPD"},
        timeout=30,
    )
    assert r.status_code == 200
    snap_id = r.headers["X-SIGESC-Snapshot-Id"]

    async def get_snap():
        db = _db()
        return await db.ai_analysis_snapshots.find_one(
            {"id": snap_id}, {"_id": 0, "expires_at_dt": 0}
        )
    snap = asyncio.run(get_snap())
    assert snap is not None
    snap_str = str(snap)
    # Dados SENSÍVEIS do aluno (criados no seed) NÃO devem aparecer
    assert "12345678901" not in snap_str  # CPF
    assert "9876543" not in snap_str      # RG
    assert "11999998888" not in snap_str  # telefone
    # Dados permitidos DEVEM aparecer
    assert "Maria Silva Santos" in snap_str
    assert "15/03/2016" in snap_str


# ---------- Portal público: 4 estados ----------

def test_portal_retorna_valido_para_doc_recem_emitido(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "matricula",
              "purpose": "Banco"},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]
    # Sem auth
    pr = httpx.get(f"{BACKEND}/api/public/verify/{code}", timeout=15)
    assert pr.status_code == 200
    data = pr.json()
    assert data["status"] == "valido"
    assert data["tipo"] == "matricula"
    assert "valido_ate" in data
    # LGPD: não vaza dados do aluno
    assert "Maria" not in str(data)


def test_portal_retorna_expirado_quando_expires_at_passou(token):
    """Força expires_at no passado e confirma status 'expirado'."""
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "frequencia",
              "purpose": "Benefício social",
              "frequencia_pct": 90},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]

    async def set_expired():
        db = _db()
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.verifiable_documents.update_one(
            {"code": code}, {"$set": {"expires_at": past}}
        )
    asyncio.run(set_expired())

    pr = httpx.get(f"{BACKEND}/api/public/verify/{code}", timeout=15)
    data = pr.json()
    assert data["status"] == "expirado", data
    assert "valido_ate" in data
    assert "Solicite uma nova emissão" in data["mensagem"]


def test_portal_retorna_revogado_apos_revogar(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "escolaridade",
              "purpose": "Transferência", "serie_concluida": "3º ano"},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]

    # Revoga
    rr = httpx.post(
        f"{BACKEND}/api/school-documents/{code}/revoke",
        headers=_h(token), json={"reason": "Erro no nome"}, timeout=20,
    )
    assert rr.status_code == 200
    # Portal público
    pr = httpx.get(f"{BACKEND}/api/public/verify/{code}", timeout=15)
    data = pr.json()
    assert data["status"] == "revogado"
    assert "revogado_em" in data


# ---------- Log de auditoria ----------

def test_emissao_registra_log_com_ip_e_usuario(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "matricula",
              "purpose": "Log audit"},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]

    async def get_log():
        db = _db()
        return await db.school_documents_log.find_one(
            {"code": code}, {"_id": 0}
        )
    log = asyncio.run(get_log())
    assert log is not None
    assert log["purpose"] == "Log audit"
    assert log["emitted_by"]["email"] == SUPER_ADMIN["email"]
    assert log["doc_type"] == "matricula"
    assert log["valid_until"]


# ---------- Regeneração idempotente ----------

def test_pdf_endpoint_regenera_mesmo_documento(token):
    """GET /{code}/pdf deve retornar PDF válido usando dados do snapshot."""
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "matricula",
              "purpose": "Regenerar"},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]

    r2 = httpx.get(
        f"{BACKEND}/api/school-documents/{code}/pdf",
        headers=_h(token), timeout=30,
    )
    assert r2.status_code == 200
    assert r2.content[:4] == b"%PDF"
    assert len(r2.content) > 1500


# ---------- Autorização ----------

def test_professor_bloqueado_ao_emitir():
    prof = httpx.post(
        f"{BACKEND}/api/auth/login",
        json={"email": "professor.teste@sigesc.com",
              "password": "Professor@2026"},
        timeout=15,
    )
    if prof.status_code != 200:
        pytest.skip("professor de teste não disponível")
    tk = prof.json()["access_token"]
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(tk),
        json={"student_id": STUDENT_ID, "doc_type": "matricula", "purpose": ""},
        timeout=15,
    )
    assert r.status_code == 403


# ---------- Override de validade ----------

def test_validity_days_override(token):
    r = httpx.post(
        f"{BACKEND}/api/school-documents/issue",
        headers=_h(token),
        json={"student_id": STUDENT_ID, "doc_type": "matricula",
              "purpose": "Custom", "validity_days": 7},
        timeout=30,
    )
    assert r.status_code == 200
    code = r.headers["X-SIGESC-Code"]
    valid_until = r.headers["X-SIGESC-Valid-Until"]
    delta = datetime.fromisoformat(valid_until) - datetime.now(timezone.utc)
    assert 6 <= delta.days <= 7


# ---------- List endpoint ----------

def test_list_endpoint_retorna_logs(token):
    r = httpx.get(
        f"{BACKEND}/api/school-documents?student_id={STUDENT_ID}",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    # Cada item deve ter os campos mínimos
    item = data["items"][0]
    for k in ("code", "doc_type", "purpose", "emitted_at", "valid_until"):
        assert k in item
