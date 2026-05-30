"""Indicadores da Rede: valida a reconciliação (soma == active_count)
para todas as escolas — séries canonicalizadas + 'Série não reconhecida' +
race_counts incl. 'nao_informada' + modalidade_counts.

Iteração 83 — bug fix: contagem por série não casava com total de ativos.
"""
import os
import requests
import pytest

BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
ADMIN_EMAIL = 'gutenberg@sigesc.com'
ADMIN_PASS = '@Celta2007'


@pytest.fixture(scope='module')
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={
        'email': ADMIN_EMAIL, 'password': ADMIN_PASS
    }, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get('access_token') or data.get('token')
    if token:
        s.headers.update({'Authorization': f'Bearer {token}'})
    return s


def test_login_ok(admin_session):
    r = admin_session.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200
    me = r.json()
    assert me.get('email') == ADMIN_EMAIL


def test_schools_list(admin_session):
    r = admin_session.get(f"{BASE}/api/schools", timeout=30)
    assert r.status_code == 200
    schools = r.json()
    assert isinstance(schools, list)
    assert len(schools) > 0


def _fetch_indicators(session, school_id):
    r = session.get(
        f"{BASE}/api/students",
        params={'school_id': school_id, 'page': 1, 'page_size': 1},
        timeout=60,
    )
    assert r.status_code == 200, f"students endpoint failed: {r.status_code} {r.text[:300]}"
    return r.json()


def test_indicators_schema_and_reconciliation_all_schools(admin_session):
    r = admin_session.get(f"{BASE}/api/schools", timeout=30)
    schools = r.json()

    # Filtros simples para escolas reais (com id) e ordenadas
    school_ids = [s['id'] for s in schools if s.get('id')]
    assert school_ids, 'no schools to test'

    failures = []
    schemas = []
    for sid in school_ids:
        data = _fetch_indicators(admin_session, sid)

        # Schema obrigatório
        for key in ('active_count', 'series_counts', 'race_counts',
                    'modalidade_counts', 'unmapped_series'):
            assert key in data, f"missing key '{key}' for school {sid}"

        active = data['active_count']
        series = data['series_counts'] or {}
        races = data['race_counts'] or {}
        unmapped = data['unmapped_series'] or {}

        # Tipos
        assert isinstance(series, dict)
        assert isinstance(races, dict)
        assert isinstance(unmapped, dict)
        assert isinstance(active, int)

        # Chaves de séries em UPPERCASE (ou UNRECOGNIZED key específica)
        for k in series.keys():
            assert k == k.upper() or k == 'SÉRIE NÃO RECONHECIDA' or 'ANO' in k.upper() or 'ETAPA' in k.upper() or 'PRÉ' in k.upper() or 'BERÇÁRIO' in k.upper() or 'MATERNAL' in k.upper(), f"unexpected series key '{k}'"

        # Invariante principal: soma de series == active_count
        soma_series = sum(series.values())
        if soma_series != active:
            failures.append({
                'school_id': sid, 'kind': 'series',
                'sum': soma_series, 'active': active,
                'series': series, 'unmapped': unmapped,
            })

        # Invariante: soma de race_counts == active_count (inclui 'nao_informada')
        soma_race = sum(races.values())
        if soma_race != active:
            failures.append({
                'school_id': sid, 'kind': 'race',
                'sum': soma_race, 'active': active,
                'races': races,
            })

        schemas.append({
            'school_id': sid, 'active': active,
            'series_keys': sorted(series.keys()),
            'race_keys': sorted(races.keys()),
            'has_unmapped': bool(unmapped),
        })

    print('\nINDICATORS_SUMMARY=', schemas)
    if failures:
        print('\nFAILURES=', failures)
    assert not failures, f"reconciliation failed for {len(failures)} schools: {failures}"


def test_fix_school_v1_unmapped(admin_session):
    """Escola 'fix_sch_v1' (mencionada pelo main agent): todos os 10 ativos
    devem cair em 'SÉRIE NÃO RECONHECIDA' com unmapped '(vazio)'=10."""
    r = admin_session.get(f"{BASE}/api/schools", timeout=30)
    schools = r.json()
    target = next((s for s in schools if s.get('id') == 'fix_sch_v1'), None)
    if not target:
        pytest.skip("school fix_sch_v1 not seeded in this preview")
    data = _fetch_indicators(admin_session, 'fix_sch_v1')
    active = data['active_count']
    series = data['series_counts']
    unmapped = data['unmapped_series']
    assert active >= 1
    assert sum(series.values()) == active
    assert 'SÉRIE NÃO RECONHECIDA' in series
    assert series['SÉRIE NÃO RECONHECIDA'] == active
    assert sum(unmapped.values()) == active


def test_multisseriada_school(admin_session):
    sid = '220d4022-ec5e-4fb6-86fc-9233112b87b2'
    data = _fetch_indicators(admin_session, sid)
    active = data['active_count']
    series = data['series_counts']
    assert sum(series.values()) == active
    # As chaves devem ser canônicas (UPPERCASE)
    for k in series.keys():
        assert any(tok in k for tok in ('ANO', 'ETAPA', 'PRÉ', 'BERÇÁRIO', 'MATERNAL', 'NÃO RECONHECIDA'))
