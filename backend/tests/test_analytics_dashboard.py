"""Regressão do Dashboard Analítico após correção do modelo de dados real.

Valida que as agregações usam o schema REAL:
  - grades: final_average / b1..b4 (não o campo inexistente 'grade')
  - attendance: records[] com status P/F/J (não 'status' no topo)
  - academic_year como número (não string)

Regras de negócio (Fev/2026):
  - Frequência = P / total de aulas (J e F = ausência; J exibida à parte)
  - Total de Faltas = F + J
  - Média Geral / Média(60%) = final_average
  - Aprovação = por aluno, todos os componentes >= 5,0
  - Desempenho por Bimestre = b1..b4 com não-lançadas = 0
"""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
YEAR = 2026
SCHOOL_WITH_DATA = "220d4022-ec5e-4fb6-86fc-9233112b87b2"  # Escola Teste Multisseriada


def _token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _h():
    return {"Authorization": f"Bearer {_token()}"}


def test_overview_calcula_frequencia_e_media():
    r = requests.get(f"{BASE_URL}/api/analytics/overview",
                     params={"academic_year": YEAR}, headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    att = d["attendance"]
    gr = d["grades"]
    # Frequência calculada (P/total) > 0 e coerente
    assert att["total_records"] > 0, "Sem registros de frequência"
    assert att["rate"] > 0, f"Frequência não calculada: {att}"
    # Total de Faltas = F + J e Justificadas <= Total de Faltas
    assert att["absent"] >= att["justified"], att
    assert att["present"] + att["absent"] == att["total_records"], att
    # Média Geral calculada (final_average) > 0
    assert gr["average"] > 0, f"Média Geral não calculada: {gr}"
    assert 0 <= gr["approval_rate"] <= 100


def test_by_period_usa_bimestres():
    r = requests.get(f"{BASE_URL}/api/analytics/grades/by-period",
                     params={"academic_year": YEAR}, headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert len(data) == 4, f"Esperado 4 bimestres, got {len(data)}"
    names = [x["period_name"] for x in data]
    assert names == ["1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"]
    # 1º bimestre (encerrado) deve ter média > 0
    assert data[0]["avg_grade"] > 0, f"1º Bimestre sem média: {data[0]}"


def test_by_subject_usa_final_average():
    r = requests.get(f"{BASE_URL}/api/analytics/grades/by-subject",
                     params={"academic_year": YEAR}, headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert len(data) > 0, "Nenhum componente curricular com média"
    for item in data:
        assert item["avg_grade"] > 0, f"Componente sem média: {item}"


def test_distribution_nao_vazia():
    r = requests.get(f"{BASE_URL}/api/analytics/distribution/grades",
                     params={"academic_year": YEAR}, headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert isinstance(data, list) and len(data) > 0, "Distribuição vazia"
    assert sum(b["count"] for b in data) > 0


def test_ranking_indicadores_preenchidos():
    r = requests.get(f"{BASE_URL}/api/analytics/schools/ranking",
                     params={"academic_year": YEAR}, headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    items = r.json()
    with_data = [s for s in items if "Multisseriada" in (s.get("school_name") or "")]
    assert with_data, "Escola com dados não encontrada no ranking"
    ind = with_data[0]["indicators"]
    assert ind["nota_media"] > 0, ind
    assert ind["frequencia_pct"] > 0, ind
    # Aprovação por aluno (>=5 em todos os componentes), entre 0 e 100
    assert 0 <= ind["aprovacao_pct"] <= 100


def test_students_performance_media_preenchida():
    r = requests.get(f"{BASE_URL}/api/analytics/students/performance",
                     params={"academic_year": YEAR, "school_id": SCHOOL_WITH_DATA},
                     headers=_h(), timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json().get("data", [])
    assert len(data) > 0, "Nenhum aluno no desempenho"
    # Pelo menos um aluno com média (60%) > 0
    assert any((s.get("avg_grade") or 0) > 0 for s in data), \
        f"Coluna Média(60%) zerada para todos: {[s.get('avg_grade') for s in data]}"
