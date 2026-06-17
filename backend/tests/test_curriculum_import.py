"""
May 2026 — Pipeline de importação curricular: extract → review → commit.

Cenários testados:
  1. Upload do PDF DCM Floresta do Araguaia retornando ≥ 100 candidatos LP.
  2. Listagem de batches devolve o recém-criado.
  3. Edit de item (descricao, ano).
  4. Bulk-status approve em N indices.
  5. Commit cria componente novo + skills, marca itens como 'imported'.
  6. Re-upload do mesmo PDF marca códigos já importados como 'duplicate'.
  7. Cleanup automático (deleta batch/skills/components) ao final.
"""
import os
import pytest
import httpx


BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://multi-tenant-fixed.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
DCM_PDF_URL = "https://customer-assets.emergentagent.com/job_38293ece-e844-49f2-b474-2b7e394f2ff0/artifacts/sylkc9p3_DOCUMENTO-CURRICULAR-DO-MUNICIPIO-DE-FLORESTA%20DO%20ARAGUAIA.pdf"


@pytest.fixture(scope="module")
def token():
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def pdf_bytes():
    r = httpx.get(DCM_PDF_URL, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.content


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _cleanup(token):
    """Deleta todos os batches DCM_FA + skills + components criados nos testes."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def run():
        c = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = c[os.environ.get("DB_NAME", "sigesc_db")]
        await db.curriculum_skills.delete_many({"fonte": "DCM_FA"})
        await db.curriculum_components.delete_many({"fonte": "DCM_FA"})
        await db.curriculum_adaptations.delete_many({"fonte": "DCM_FA"})
        # BNCC LP gerados pelo DCM_FA devem ser limpos para reisolamento
        await db.bncc_skills.delete_many({"componente_codigo": "LP"})
        await db.curriculum_import_batches.delete_many({})

    asyncio.run(run())


def test_full_pipeline(token, pdf_bytes):
    _cleanup(token)

    # 1. Upload (LP only)
    files = {"file": ("dcm_fa.pdf", pdf_bytes, "application/pdf")}
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/upload?only=LP&fonte=DCM_FA",
        headers=_h(token), files=files, timeout=60,
    )
    assert r.status_code == 201, r.text
    upload_data = r.json()
    assert upload_data["total_items"] >= 100  # PDF tem 148 LP
    assert upload_data["by_componente"].get("LP", 0) >= 100
    batch_id = upload_data["batch_id"]

    # 2. List batches
    r = httpx.get(f"{BACKEND}/api/curriculum/import/batches", headers=_h(token), timeout=20)
    assert r.status_code == 200, r.text
    batches = r.json()
    assert any(b["id"] == batch_id for b in batches)

    # 3. Get batch detail
    r = httpx.get(f"{BACKEND}/api/curriculum/import/batches/{batch_id}", headers=_h(token), timeout=30)
    assert r.status_code == 200, r.text
    detail = r.json()
    assert len(detail["items"]) == upload_data["total_items"]

    # 4. Edit item idx 0 (corrigir descrição)
    r = httpx.put(
        f"{BACKEND}/api/curriculum/import/batches/{batch_id}/items/0",
        headers=_h(token),
        json={"descricao": "Descrição corrigida pelo pytest.", "status": "edited"},
        timeout=20,
    )
    assert r.status_code == 200, r.text

    # 5. Bulk approve indices 0,1,2
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/batches/{batch_id}/bulk-status",
        headers=_h(token),
        json={"indices": [0, 1, 2], "status": "approved"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 3

    # 6. Commit
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/batches/{batch_id}/commit",
        headers=_h(token), timeout=30,
    )
    assert r.status_code == 200, r.text
    commit_data = r.json()
    assert commit_data["skills_inserted"] == 3
    assert commit_data["components_created"] == 1
    assert commit_data["status"] == "partially_committed"

    # 7. Re-upload deveria marcar os 3 já importados como duplicate
    files2 = {"file": ("dcm_fa.pdf", pdf_bytes, "application/pdf")}
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/upload?only=LP&fonte=DCM_FA",
        headers=_h(token), files=files2, timeout=60,
    )
    assert r.status_code == 201, r.text
    re_upload = r.json()
    assert re_upload["duplicates"] >= 3, re_upload

    _cleanup(token)


def test_upload_rejects_non_pdf(token):
    files = {"file": ("foo.txt", b"not a pdf", "text/plain")}
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/upload",
        headers=_h(token), files=files, timeout=20,
    )
    assert r.status_code == 400


def test_commit_without_approved_returns_400(token, pdf_bytes):
    _cleanup(token)
    files = {"file": ("dcm_fa.pdf", pdf_bytes, "application/pdf")}
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/upload?only=LP",
        headers=_h(token), files=files, timeout=60,
    )
    assert r.status_code == 201, r.text
    bid = r.json()["batch_id"]
    # Sem aprovar nenhum, commit deve falhar
    r = httpx.post(
        f"{BACKEND}/api/curriculum/import/batches/{bid}/commit",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 400
    assert "aprovado" in r.json().get("detail", "").lower()
    _cleanup(token)
