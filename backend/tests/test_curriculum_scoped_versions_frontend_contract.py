"""Contrato estático do workspace curricular e preservação do importador legado."""
from pathlib import Path


FRONTEND = Path("../frontend/src")


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_workspace_abre_em_versoes_e_preserva_aba_legada():
    source = _read("pages/CurriculumImport.jsx")
    assert "useState('versions')" in source
    assert "Versões Curriculares" in source
    assert "Importar habilidades" in source
    assert "CurriculumSkillImportLegacy" in source
    assert "ScopedCurriculumVersions" in source
    assert "Fontes oficiais → Versão Curricular por componente/série/bimestre → Plano de Ensino Bimestral." in source


def test_fluxo_novo_usa_endpoints_proprios_e_plano_canonico():
    source = _read("components/curriculum/ScopedCurriculumVersions.jsx")
    assert "/api/curriculum/import/scoped-versions/upload" in source
    assert "/refresh-skill-resolution" in source
    assert "/publish`" in source
    assert "/create-teaching-plan" in source
    assert "/api/curriculum/teaching-plans/${plan.id}/publish" in source
    assert "/api/curriculum/sources" in source
    assert "coursesAPI.list()" in source


def test_ui_expoe_separacao_normativa_e_objetos_de_conhecimento():
    source = _read("components/curriculum/ScopedCurriculumVersions.jsx")
    assert "Habilidades DCM obrigatórias" in source
    assert "Habilidades BNCC complementares" in source
    assert "Integração transversal" in source
    assert "Objetos de Conhecimento" in source
    assert "Resolva as habilidades DCM obrigatórias antes de publicar." in source


def test_importador_legado_permanece_disponivel_e_separado():
    legacy = _read("pages/CurriculumSkillImportLegacy.jsx")
    scoped = _read("components/curriculum/ScopedCurriculumVersions.jsx")
    assert "data-testid=\"curriculum-import-page\"" in legacy
    assert "/api/curriculum/import/upload" in legacy
    assert "/api/curriculum/import/scoped-versions/upload" not in legacy
    assert "/api/curriculum/import/upload" not in scoped
