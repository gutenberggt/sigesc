"""Contrato estático da Fase 3 da interface AEE v2.

O teste não executa React. Ele protege as invariantes de integração entre a UI
legada do Diário e o sidecar versionado criado nas Fases 1/2.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIARIO = ROOT / "frontend" / "src" / "pages" / "DiarioAEE.js"
PLANO_MODAL = ROOT / "frontend" / "src" / "components" / "PlanoAEEModal.js"
DOSSIE = ROOT / "frontend" / "src" / "components" / "DossieAEEV2Modal.jsx"
PDF = ROOT / "backend" / "pdf" / "plano_aee.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_diario_exposes_v2_title_and_dossier_entrypoint():
    source = _read(DIARIO)

    assert "Diário AEE V2.0" in source
    assert "import DossieAEEV2Modal" in source
    assert "btn-dossie-v2-" in source
    assert "<span>Dossiê V2</span>" in source
    assert "inline-flex items-center" in source
    assert "<DossieAEEV2Modal" in source


def test_dossier_bootstrap_is_explicit_not_automatic():
    source = _read(DOSSIE)

    assert "Inicializar Dossiê V2" in source
    assert "const bootstrap = async ()" in source
    assert "onClick={bootstrap}" in source
    assert "useEffect(() =>" in source
    # O carregamento inicial consulta estado; não deve chamar bootstrap.
    effect_block = source[source.index("useEffect(() =>"):source.index("if (!show || !plano) return null;")]
    assert "bootstrap()" not in effect_block


def test_dossier_uses_versioned_sidecar_concurrency_contract():
    source = _read(DOSSIE)

    assert "expected_head_revision" in source
    assert "expected_working_snapshot_id" in source
    assert "/activation-validation" in source
    assert "/activate" in source
    assert "/revisions" in source
    assert "/sections/study-case" not in source  # rota é composta por SECTION_PATHS
    assert "study_case: 'study-case'" in source


def test_curricular_experience_label_changes_only_presentation():
    modal = _read(PLANO_MODAL)
    dossier = _read(DOSSIE)
    pdf = _read(PDF)

    expected = "Adaptações por Componente Curricular/Campos de Experiência"
    assert expected in modal
    assert expected in dossier
    assert expected in pdf

    # Campo técnico legado/canônico continua estável para compatibilidade.
    assert "adaptacoes_por_componente" in modal
    assert "adaptacoes_por_componente" in dossier
    assert "plano.get('adaptacoes_por_componente')" in pdf


def test_dossier_keeps_legacy_records_read_only_in_fase3():
    source = _read(DOSSIE)

    for endpoint in ("/api/aee/atendimentos?", "/api/aee/articulacoes?", "/api/aee/evolucoes?"):
        assert endpoint in source

    # Escritas da Fase 3 são exclusivamente no sidecar dossie-v2.
    write_calls = [line.strip() for line in source.splitlines() if "method:" in line]
    assert write_calls
    assert all("'POST'" in line or "'PATCH'" in line for line in write_calls)
