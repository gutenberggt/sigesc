from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.enrollment_rectification_f2_3_schoolwide_identity import (
    _cpf_digits,
    _normalize_birth_date,
    _norm,
    component_hash,
    resolve_by_components,
)


def _h(salt: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{salt}|{kind}|{value}".encode()).hexdigest()


def test_normalization_contract():
    assert _norm("  Aluna Vitória ") == "aluna vitoria"
    assert _normalize_birth_date("01/03/2013") == "2013-03-01"
    assert _cpf_digits("123.456.789-00") == "12345678900"


def test_unique_cpf_resolves_schoolwide():
    salt = "0123456789abcdef0123456789abcdef"
    students = [
        {"id": "a", "full_name": "Pessoa A", "birth_date": "2010-01-01", "cpf": "11111111111"},
        {"id": "b", "full_name": "Nome Divergente", "birth_date": "2011-02-02", "cpf": "22222222222"},
    ]
    resolved, method, counts = resolve_by_components(
        students, salt=salt,
        name_hash=_h(salt, "name", "nome da ficha"),
        dob_hash=_h(salt, "dob", "2013-03-01"),
        cpf_hash=_h(salt, "cpf", "22222222222"),
    )
    assert resolved is not None and resolved["id"] == "b"
    assert "cpf_exact" in str(method)
    assert counts["cpf_exact_count"] == 1


def test_conflicting_unique_signals_block():
    salt = "0123456789abcdef0123456789abcdef"
    students = [
        {"id": "a", "full_name": "Pessoa Um", "birth_date": "2013-03-01", "cpf": "11111111111"},
        {"id": "b", "full_name": "Pessoa Dois", "birth_date": "2014-04-04", "cpf": "22222222222"},
    ]
    resolved, method, counts = resolve_by_components(
        students, salt=salt,
        name_hash=_h(salt, "name", "pessoa um"),
        dob_hash=_h(salt, "dob", "2013-03-01"),
        cpf_hash=_h(salt, "cpf", "22222222222"),
    )
    assert resolved is None
    assert method == "COMPONENT_SIGNAL_CONFLICT"
    assert counts["unique_method_agreement"] is False
