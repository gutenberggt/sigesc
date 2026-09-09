from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.enrollment_rectification_f2_3_strong_identity import (
    _cpf_digits,
    _one_edit_name_variants,
    composite_fingerprint,
)


def test_cpf_digits_strips_formatting():
    assert _cpf_digits("123.456.789-00") == "12345678900"


def test_composite_fingerprint_normalizes_name_date_and_cpf_format():
    salt = "0123456789abcdef0123456789abcdef"
    a = composite_fingerprint(
        salt, "  Aluna   Vitória ", "01/03/2013", "123.456.789-00"
    )
    b = composite_fingerprint(
        salt, "aluna vitoria", "2013-03-01", "12345678900"
    )
    assert a == b
    assert len(a) == 64


def test_one_edit_variants_include_single_missing_character_case():
    variants = _one_edit_name_variants("emanuelle vitoria ribeiro da silva")
    assert "emmanuelle vitoria ribeiro da silva" in variants


def test_one_edit_variants_do_not_include_original():
    original = "emmanuelle vitoria ribeiro da silva"
    assert original not in _one_edit_name_variants(original)


def test_executor_is_standalone_from_other_audit_scripts():
    path = ROOT / "scripts" / "enrollment_rectification_f2_3_strong_identity.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "scripts.enrollment_rectification_f2_3_case_preflight" not in imported_modules
    assert not any(module.startswith("scripts.") for module in imported_modules)
    assert "services.enrollment_rectification" in imported_modules
