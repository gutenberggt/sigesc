"""Tests for GET /api/admin/online-users/login-count by_category breakdown."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')
ADMIN_EMAIL = 'gutenberg@sigesc.com'
ADMIN_PASSWORD = '@Celta2007'


@pytest.fixture(scope='module')
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()['access_token']


@pytest.fixture(scope='module')
def admin_session(admin_token):
    s = requests.Session()
    s.headers.update({'Authorization': f'Bearer {admin_token}',
                      'Content-Type': 'application/json'})
    return s


def test_login_count_returns_total_successful_by_category(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/online-users/login-count", timeout=30)
    assert r.status_code == 200, f"status {r.status_code} body {r.text}"
    data = r.json()
    # Top-level keys
    assert 'total' in data
    assert 'successful' in data
    assert 'by_category' in data
    # by_category keys
    cats = data['by_category']
    for k in ('professores', 'alunos', 'assistencia_social', 'saude', 'administrativas'):
        assert k in cats, f"missing category {k}"
        assert isinstance(cats[k], int)
    # Types
    assert isinstance(data['total'], int)
    assert isinstance(data['successful'], int)
    # Successful <= total
    assert data['successful'] <= data['total']


def test_login_count_sum_equals_successful(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/online-users/login-count", timeout=30)
    assert r.status_code == 200
    data = r.json()
    s = sum(data['by_category'].values())
    print(f"successful={data['successful']} total={data['total']} by_category={data['by_category']} sum={s}")
    assert s == data['successful'], (
        f"Sum of by_category ({s}) must equal successful ({data['successful']}). "
        f"by_category={data['by_category']}"
    )


def test_online_users_endpoint_still_works(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/online-users", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_login_count_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/online-users/login-count", timeout=30)
    assert r.status_code in (401, 403)
