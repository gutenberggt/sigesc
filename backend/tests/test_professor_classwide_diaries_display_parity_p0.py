"""P0 — paridade visual de regência class-wide em Meus Diários.

Um vínculo DVD com ``component_id=None`` representa regência/autorização da turma
inteira. Ele não é um componente curricular e, quando a lotação possui componentes
reais, deve autorizar esses componentes sem criar a linha visual fantasma
"Regência / vínculo da turma".
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
MY_DIARIES = (
    REPO / "frontend" / "src" / "components" / "professor" / "MyDiariesSection.jsx"
).read_text(encoding="utf-8")


def test_regencia_classwide_e_guardada_fora_do_mapa_de_componentes():
    assert "classWideDiaries: []" in MY_DIARIES
    assert "if (!diary.component_id)" in MY_DIARIES
    assert "module.classWideDiaries.push(diary);" in MY_DIARIES
    assert "const classWideDiary = classWideDiaries.length === 1 && components.length > 0" in MY_DIARIES


def test_regencia_unica_e_herdada_pelos_componentes_reais():
    assert "const getEffectiveComponent = (component, module) =>" in MY_DIARIES
    assert "!module?.classWideDiary" in MY_DIARIES
    assert "return { ...component, diary: module.classWideDiary };" in MY_DIARIES
    assert "const effectiveComponent = getEffectiveComponent(component, module);" in MY_DIARIES
    assert "buildComponentContext(effectiveComponent, module, academicYear)" in MY_DIARIES


def test_vinculo_especifico_tem_precedencia_sobre_regencia():
    # getEffectiveComponent devolve o componente intacto quando já existe diary
    # específico; somente componentes sem diary herdam o class-wide.
    assert "component.diary || !module?.classWideDiary" in MY_DIARIES


def test_regencia_nao_produz_chave_react_duplicada_quando_herdada():
    assert "key={component.id || diary?.assignment_id || component.name}" in MY_DIARIES
    assert "inheritedClassWide" in MY_DIARIES


def test_ambiguidade_classwide_nao_escolhe_assignment_arbitrariamente():
    assert "classWideDiaries.length === 1" in MY_DIARIES
    assert "components.length === 0 || classWideDiaries.length > 1" in MY_DIARIES
    # O fallback explícito continua disponível para turma sem componentes ou
    # para tornar uma inconsistência ambígua visível, em vez de mascará-la.
    assert "Regência / vínculo da turma" in MY_DIARIES
