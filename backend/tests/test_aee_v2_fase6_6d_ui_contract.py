from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIARIO = ROOT / "frontend" / "src" / "pages" / "DiarioAEE.js"


def _source() -> str:
    return DIARIO.read_text(encoding="utf-8")


def test_diario_records_explicit_6_6d_authorization():
    source = _source()
    assert "AEE v2 Fase 6.6D: governança de escrita autorizada" in source
    assert "23/08/2026" in source


def test_mutation_policy_helper_is_fail_safe_for_integrity_and_v2_management():
    source = _source()
    assert "const getPlanMutationPolicy = (plano) =>" in source
    assert "plano?.mutation_policy" in source
    assert "blocked_integrity" in source
    assert "dossier_v2_required" in source
    assert "legacy_allowed" in source


def test_edit_routes_v2_managed_to_dossier_and_legacy_to_existing_modal():
    source = _source()
    assert "const handleEditPlano = (plano) =>" in source
    assert "if (policy === 'dossier_v2_required')" in source
    assert "setDossiePlano(plano);" in source
    assert "if (policy === 'blocked_integrity')" in source
    assert "setEditingPlano(plano);" in source
    assert "setShowPlanoModal(true);" in source


def test_duplicate_and_delete_are_blocked_in_ui_for_non_legacy_policy():
    source = _source()
    assert "const handleDuplicarPlano = (plano) =>" in source
    assert "const handleDeletePlano = (plano) =>" in source
    assert source.count("getPlanMutationPolicy(plano) !== 'legacy_allowed'") >= 2
    assert "Este Plano é gerenciado pelo Dossiê AEE V2 e não pode ser duplicado pelo fluxo legado." in source
    assert "A âncora histórica deste Plano é protegida pelo Dossiê AEE V2 e não pode ser excluída pelo fluxo legado." in source


def test_integrity_policy_never_opens_destructive_legacy_flow():
    source = _source()
    assert "Verifique a integridade do Dossiê AEE V2 antes de alterar este Plano." in source
    assert "Verifique a integridade do Dossiê AEE V2 antes de duplicar este Plano." in source
    assert "Verifique a integridade do Dossiê AEE V2 antes de excluir este Plano." in source


def test_backend_remains_authority_and_existing_error_parser_handles_409():
    source = _source()
    assert "parseResponseError(response, 'Erro ao salvar plano')" in source
    assert "parseResponseError(response, 'Erro ao duplicar plano')" in source
    assert "parseResponseError(response, 'Erro ao excluir plano')" in source
    assert "mutation_policy" in source


def test_6_6c_read_paths_and_pdf_are_preserved():
    source = _source()
    assert "<PlanoAEEEffectiveViewer" in source
    assert "setViewingPlano(effectivePlan);" in source
    assert "onGeneratePdf={handleGerarPDFPlano}" in source
    assert "<DossieAEEV2Modal" in source
    assert "Novo Atendimento" in source
