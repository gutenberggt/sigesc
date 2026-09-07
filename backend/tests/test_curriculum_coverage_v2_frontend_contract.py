from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COVERAGE_PAGE = ROOT / "frontend" / "src" / "pages" / "CurriculumCoverage.jsx"
COVERAGE_CLIENT = ROOT / "frontend" / "src" / "services" / "curriculumCoverageV2.js"


def test_frontend_reads_canonical_coverage_v2_only():
    client = COVERAGE_CLIENT.read_text(encoding="utf-8")
    page = COVERAGE_PAGE.read_text(encoding="utf-8")

    assert "/curriculum/coverage-v2" in client
    assert "curriculumCoverageV2API.get(params)" in page
    assert "import { curriculumAPI" not in page
    assert "curriculumAPI.coverage(params)" not in page


def test_frontend_never_fabricates_zero_without_published_plan():
    page = COVERAGE_PAGE.read_text(encoding="utf-8")

    assert "percentage_available" in page
    assert "coverage_state === 'plano_inexistente'" in page
    assert "Percentual indisponível" in page
    assert "Aguardando plano publicado" in page
    assert "data?.totals?.pct ?? 0" not in page
    assert "O SIGESC não calcula 0% quando o denominador curricular não existe." in page


def test_frontend_keeps_history_and_outside_plan_explicitly_separate():
    page = COVERAGE_PAGE.read_text(encoding="utf-8")

    assert "worked_outside_plan_count" in page
    assert "historical_unstructured_count" in page
    assert "fora do plano vigente" in page
    assert "fora do numerador" in page
