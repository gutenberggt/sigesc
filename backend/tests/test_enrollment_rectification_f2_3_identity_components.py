from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.enrollment_rectification_f2_3_identity_components import (
    _cpf_digits,
    _normalize_birth_date,
    _norm,
    component_hash,
    resolve_by_components,
)


def _h(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode()).hexdigest()


def test_normalizers_are_stable():
    assert _norm("  Aluna   Vitória ") == "aluna vitoria"
    assert _normalize_birth_date("01/03/2013") == "2013-03-01"
    assert _cpf_digits("123.456.789-00") == "12345678900"


def test_component_hash_is_domain_separated():
    salt = "0123456789abcdef0123456789abcdef"
    value = "same"
    assert component_hash(salt, "name", value) != component_hash(salt, "cpf", value)


def test_unique_cpf_resolves_even_when_name_differs():
    salt = "0123456789abcdef0123456789abcdef"
    students = [
        {"id": "a", "full_name": "Outra Pessoa", "birth_date": "2012-01-01", "cpf": "00000000000"},
        {"id": "b", "full_name": "Nome Cadastrado", "birth_date": "2013-03-01", "cpf": "12345678900"},
    ]
    resolved, method, counts = resolve_by_components(
        students,
        salt=salt,
        expected_name_hash=_h(salt, "name", "nome da ficha"),
        expected_dob_hash=_h(salt, "dob", "2013-03-01"),
        expected_cpf_hash=_h(salt, "cpf", "12345678900"),
    )
    assert resolved is not None and resolved["id"] == "b"
    assert "cpf_exact" in str(method)
    assert counts["cpf_exact_count"] == 1


def test_conflicting_unique_signals_fail_closed():
    salt = "0123456789abcdef0123456789abcdef"
    students = [
        {"id": "a", "full_name": "Pessoa Um", "birth_date": "2013-03-01", "cpf": "11111111111"},
        {"id": "b", "full_name": "Pessoa Dois", "birth_date": "2014-04-02", "cpf": "22222222222"},
    ]
    resolved, method, counts = resolve_by_components(
        students,
        salt=salt,
        expected_name_hash=_h(salt, "name", "pessoa um"),
        expected_dob_hash=_h(salt, "dob", "2013-03-01"),
        expected_cpf_hash=_h(salt, "cpf", "22222222222"),
    )
    assert resolved is None
    assert method == "COMPONENT_SIGNAL_CONFLICT"
    assert counts["unique_method_agreement"] is False


def test_no_unique_signal_stays_blocked():
    salt = "0123456789abcdef0123456789abcdef"
    students = [
        {"id": "a", "full_name": "Pessoa Um", "birth_date": "2012-01-01", "cpf": "11111111111"},
        {"id": "b", "full_name": "Pessoa Dois", "birth_date": "2014-04-02", "cpf": "22222222222"},
    ]
    resolved, method, counts = resolve_by_components(
        students,
        salt=salt,
        expected_name_hash=_h(salt, "name", "ninguem"),
        expected_dob_hash=_h(salt, "dob", "2015-05-03"),
        expected_cpf_hash=_h(salt, "cpf", "33333333333"),
    )
    assert resolved is None and method is None
    assert counts["cpf_exact_count"] == 0
