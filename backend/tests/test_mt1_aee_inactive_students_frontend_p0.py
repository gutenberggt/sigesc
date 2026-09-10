from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AEE = ROOT / "frontend/src/pages/DiarioAEE.js"
STUDENTS = ROOT / "frontend/src/pages/StudentsComplete.js"


def test_diario_aee_uses_canonical_tenant_aware_fetch():
    source = AEE.read_text(encoding="utf-8")
    assert "import { apiFetch } from '@/services/api';" in source
    assert "apiFetch(`${API_URL}/api/schools`" in source
    assert "const res = await apiFetch(url, options);" in source
    assert "fetch(" not in source


def test_inactive_status_can_query_without_school_or_search():
    source = STUDENTS.read_text(encoding="utf-8")
    assert "if (!filterSchoolId && !debouncedSearch && !filterStatus)" in source
    assert "if (filterStatus) params.status = filterStatus;" in source
