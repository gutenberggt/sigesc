"""Guards de isolamento multi-tenant da Ficha Individual de Urgências."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "backend" / "routers" / "manual_ficha_individual.py"
RESOLVER = ROOT / "backend" / "utils" / "curriculum_resolver.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_curriculum_resolver_scopes_all_internal_evidence_by_class_tenant():
    source = _source(RESOLVER)

    assert 'tenant_id = class_info.get("mantenedora_id")' in source
    assert '"mantenedora_id": 1,' in source
    assert 'def _tenant_query(query: dict, tenant_id: Optional[str]) -> dict:' in source

    for fragment in (
        '_tenant_query(\n            {\n                "student_id": student_id,',
        '_tenant_query({"class_id": class_id}, tenant_id)',
        'db, class_id, tenant_id=tenant_id',
        'db, nivel_ensino=nivel, tenant_id=tenant_id',
        'db, list(candidates.keys()), tenant_id=tenant_id',
    ):
        assert fragment in source, f"Tenant scope ausente no resolver: {fragment}"


def test_manual_ficha_medical_certificates_are_fail_closed_by_tenant():
    source = _source(ROUTER)
    segment = source.split('certs = await db.medical_certificates.find(', 1)[1].split(
        'medical_days =', 1
    )[0]

    # Não depender de formatação: exige o helper de tenant dentro da própria
    # chamada de medical_certificates e os campos/guards necessários.
    assert 'apply_tenant_filter(' in segment
    assert '"student_id": student_id,' in segment
    assert '"mantenedora_id": 1' in segment
    assert 'user,' in segment
    assert 'request,' in segment
    assert 'for cert in certs:' in source
    assert 'assert_same_tenant(cert, user, request)' in source


def test_urgencias_tenant_guard_remains_fail_closed_not_legacy_unscoped_fallback():
    source = _source(ROUTER)
    attendance_segment = source.split('async def _build_attendance_data(', 1)[1].split(
        'def _preview_courses(', 1
    )[0]

    assert 'medical_certificates.find(\n        apply_tenant_filter(' in attendance_segment
    assert 'mantenedora_id": {"$exists": False}' not in attendance_segment
    assert 'legacy_certs' not in attendance_segment
