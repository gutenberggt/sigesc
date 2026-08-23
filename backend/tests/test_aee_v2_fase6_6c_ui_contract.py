from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIARIO = ROOT / "frontend" / "src" / "pages" / "DiarioAEE.js"
VIEWER = ROOT / "frontend" / "src" / "components" / "PlanoAEEEffectiveViewer.jsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_diario_6_6c_imports_read_only_effective_viewer():
    source = _read(DIARIO)
    assert "PlanoAEEEffectiveViewer" in source
    assert "@/components/PlanoAEEEffectiveViewer" in source
    assert "AEE v2 Fase 6.6C: cutover controlado da leitura/UX autorizado" in source


def test_status_visual_uses_effective_summary_and_integrity_has_no_legacy_fallback():
    source = _read(DIARIO)
    assert "const getPlanEffectiveStatus = (plano) =>" in source
    assert "if (plano?.effective_error) return null;" in source
    assert "legacy_compatible_status" in source
    assert "Integridade pendente" in source
    assert "plano-status-efetivo-" in source
    assert "'cancelado': 'Cancelado'" in source


def test_days_visual_use_effective_schedule_and_heterogeneous_is_explicit():
    source = _read(DIARIO)
    assert "const getPlanEffectiveDays = (plano) =>" in source
    assert "effective_summary?.schedule_summary" in source
    assert "getPlanEffectiveDays(plano)" in source
    assert "Agenda variável" in source
    assert "Indisponível" in source


def test_v2_governance_badge_distinguishes_working_active_and_integrity():
    source = _read(DIARIO)
    assert "const getPlanV2Badge = (plano) =>" in source
    assert "Dossiê V2 · Verificar integridade" in source
    assert "Dossiê V2 · Em trabalho" in source
    assert "document_version" in source
    assert "plano-v2-badge-" in source


def test_visualizar_fetches_individual_get_instead_of_using_raw_list_object():
    source = _read(DIARIO)
    assert "const handleVisualizarPlano = async (plano) =>" in source
    assert "`${API_URL}/api/aee/planos/${plano.id}`" in source
    assert "const effectivePlan = await response.json();" in source
    assert "setViewingPlano(effectivePlan);" in source
    assert "setViewingPlano(plano);" not in source


def test_legacy_inline_viewer_was_replaced_by_effective_viewer():
    source = _read(DIARIO)
    assert "<PlanoAEEEffectiveViewer" in source
    assert "payload={viewingPlano}" in source
    assert "onGeneratePdf={handleGerarPDFPlano}" in source
    assert "viewingPlano.linha_base_situacao_atual" not in source
    assert "Modal de Visualização do Plano AEE (Feb 2026)" not in source


def test_6_6c_does_not_enforce_write_governance_early():
    source = _read(DIARIO)
    assert "handleEditPlano(plano)" in source
    assert "handleDuplicarPlano(plano)" in source
    assert "handleDeletePlano(plano)" in source
    assert "AEE_V2_LEGACY_PLAN_WRITE_BLOCKED" not in source


def test_effective_viewer_is_read_only_and_renders_dossier_sections():
    source = _read(VIEWER)
    assert "effective_dossier" in source
    assert "effective_source" in source
    assert "effective_version" in source
    assert "Estudo de Caso" in source
    assert "PAEE" in source
    assert "PEI" in source
    assert "Agenda / Cronograma" in source
    assert "Snapshot V2 vigente" in source
    assert "Projeção efetiva do Plano legado" in source
    assert "Referência histórica" in source
    assert "não representam uma Fonte Efetiva confirmada" in source
    for write_verb in ("method: 'POST'", "method: 'PUT'", "method: 'PATCH'", "method: 'DELETE'"):
        assert write_verb not in source


def test_effective_viewer_keeps_pdf_action_by_plan_id_payload():
    source = _read(VIEWER)
    assert "onGeneratePdf?.(payload)" in source
    assert 'data-testid="btn-gerar-pdf-plano"' in source
