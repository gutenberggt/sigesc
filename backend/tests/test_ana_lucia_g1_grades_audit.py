import ast
from pathlib import Path

from scripts import ana_lucia_g1_grades_audit as g1


def test_pair_identical():
    a = {"b1": 8.0, "b2": None}
    b = {"b1": 8.0, "b2": None}
    assert g1._classify_pair(a, b) == "BOTH_IDENTICAL"


def test_pair_complementary():
    a = {"b1": 8.0, "b2": None}
    b = {"b1": None, "b2": 9.0}
    assert g1._classify_pair(a, b) == "BOTH_COMPLEMENTARY"


def test_pair_conflicting():
    a = {"b1": 8.0}
    b = {"b1": 9.0}
    assert g1._classify_pair(a, b) == "BOTH_CONFLICTING"


def test_no_mongo_mutators_in_read_only_audit():
    source = Path(g1.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "insert_one", "insert_many", "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write", "find_one_and_update",
        "find_one_and_delete", "find_one_and_replace", "drop", "drop_database",
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden:
            found.append(node.func.attr)
    assert found == []
