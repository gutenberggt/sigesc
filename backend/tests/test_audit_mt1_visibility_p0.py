"""P0 — auditoria visível, tenant-scoped e sem falso estado vazio."""

from pathlib import Path

import pytest

from audit_service import AuditService


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
FRONTEND = (REPO / "frontend" / "src" / "pages" / "AuditLogs.jsx").read_text(
    encoding="utf-8"
)
ROUTER = (ROOT / "routers" / "audit_logs.py").read_text(encoding="utf-8")


class _ListCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    async def to_list(self, length=None):
        if length is None:
            return list(self.docs)
        return list(self.docs[:length])


class _EvidenceCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query, _projection=None):
        tenant = query.get("mantenedora_id")
        return _ListCursor(
            doc for doc in self.docs if doc.get("mantenedora_id") == tenant
        )

    async def find_one(self, query, _projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None


class _AuditCollection:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, doc):
        self.inserted.append(dict(doc))
        return object()


class _FakeDB:
    def __init__(self):
        self.schools = _EvidenceCollection([
            {"id": "S-A", "mantenedora_id": "TENANT_A"},
            {"id": "S-B", "mantenedora_id": "TENANT_B"},
        ])
        self.users = _EvidenceCollection([
            {"id": "U-A", "mantenedora_id": "TENANT_A"},
            {"id": "U-B", "mantenedora_id": "TENANT_B"},
        ])
        self.audit_logs = _AuditCollection()


@pytest.mark.asyncio
async def test_scope_query_accepts_legacy_only_with_tenant_evidence():
    service = AuditService()
    service.set_db(_FakeDB())

    query = await service.build_tenant_scope_query("TENANT_A")

    assert {"mantenedora_id": "TENANT_A"} in query["$or"]
    serialized = repr(query)
    assert "S-A" in serialized
    assert "U-A" in serialized
    assert "S-B" not in serialized
    assert "U-B" not in serialized
    assert "$exists" in serialized  # legado sem tenant exige evidência adicional


@pytest.mark.asyncio
async def test_scope_query_sem_tenant_falha_fechado():
    service = AuditService()
    service.set_db(_FakeDB())

    assert await service.build_tenant_scope_query(None) == {
        "_id": {"$exists": False}
    }


@pytest.mark.asyncio
async def test_novo_log_persiste_tenant_operacional():
    db = _FakeDB()
    service = AuditService()
    service.set_db(db)

    await service.log(
        action="update",
        collection="grades",
        document_id="GRADE-1",
        user={
            "id": "SUPER-1",
            "email": "super@example.test",
            "role": "super_admin",
            "active_mantenedora_id": "TENANT_A",
        },
        description="Alterou nota",
    )

    assert len(db.audit_logs.inserted) == 1
    assert db.audit_logs.inserted[0]["mantenedora_id"] == "TENANT_A"


def test_frontend_usa_fetch_canonico_com_contexto_tenant():
    assert "apiFetch(`${API}/api/audit-logs?${params}`)" in FRONTEND
    assert "apiFetch(`${API}/api/audit-logs/stats?days=7`)" in FRONTEND
    assert "buildFetchAuthHeaders('GET')" in FRONTEND
    assert "headers: { 'Authorization': `Bearer ${token}` }" not in FRONTEND


def test_frontend_nao_mascara_erro_como_lista_vazia():
    assert 'data-testid="audit-load-error"' in FRONTEND
    assert "Falha ao carregar a auditoria" in FRONTEND
    assert "response.ok" in FRONTEND


def test_router_propaga_tenant_para_lista_pdf_e_estatisticas():
    assert "tenant_id=tenant_id" in ROUTER
    assert "audit_service.get_stats(days=days, tenant_id=tenant_id)" in ROUTER
    assert "{'id': tenant_id}" in ROUTER
    assert "find_one({}," not in ROUTER
