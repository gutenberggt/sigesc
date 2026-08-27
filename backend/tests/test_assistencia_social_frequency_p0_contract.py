"""Contrato estático da P0 de frequência da Assistência Social."""
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend" / "routers" / "attendance_ext_dvd.py"
FRONTEND = REPO / "frontend" / "src" / "pages" / "AssocialDashboard.js"


def _social_segment(source: str) -> str:
    start = source.index("async def social_frequency_p0")
    end = source.index("if legacy_pdf is not None:", start)
    return source[start:end]


def test_social_frequency_endpoint_is_role_and_tenant_scoped():
    source = BACKEND.read_text(encoding="utf-8")
    segment = _social_segment(source)

    assert '_SOCIAL_FREQUENCY_ROLES = ["admin", "admin_teste", "ass_social", "ass_social_2"]' in source
    assert "AuthMiddleware.require_roles(_SOCIAL_FREQUENCY_ROLES)" in segment
    assert segment.count("apply_tenant_filter(") >= 3
    assert "AuthMiddleware.verify_school_access" in segment
    assert "compute_monthly_valid_absences(" in segment
    assert '"calculation_version": "social_daily_canonical_v2"' in segment


def test_social_frequency_endpoint_is_read_only():
    source = BACKEND.read_text(encoding="utf-8")
    segment = _social_segment(source)

    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".delete_one(",
        ".delete_many(",
        ".replace_one(",
    )
    assert not any(token in segment for token in forbidden)


def test_frontend_does_not_translate_http_failure_into_missing_attendance():
    source = FRONTEND.read_text(encoding="utf-8")
    start = source.index("const loadStudentDetails")
    end = source.index("const handleLogout", start)
    segment = source[start:end]

    assert "Promise.allSettled([" in segment
    assert "frequencyResult.status === 'rejected'" in segment
    assert "setFrequencyError(" in segment
    assert 'data-testid="student-attendance-error"' in source
    assert "Não foi possível consultar a frequência neste momento" in source
