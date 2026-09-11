import ast
from pathlib import Path

from scripts import ana_lucia_g2_grades_adjudication as g2


def test_classification_contract():
    assert g2._classify([{"b1": 8}], []) == "LEGACY_ONLY"
    assert g2._classify([], [{"b1": 8}]) == "CANONICAL_ONLY"
    assert g2._classify([{"b1": 8}], [{"b1": 8}]) == "BOTH_IDENTICAL"
    assert g2._classify([{"b1": 8, "b2": 9}], [{"b1": 8, "b2": None}]) == "BOTH_COMPLEMENTARY"
    assert g2._classify([{"b1": 8}], [{"b1": 9}]) == "BOTH_CONFLICTING"


def test_read_only_surface_has_no_mongo_mutators():
    source = Path(g2.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"insert_one","insert_many","update_one","update_many","replace_one","delete_one","delete_many","bulk_write","find_one_and_update","find_one_and_delete","find_one_and_replace","drop","drop_database"}
    found = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden]
    assert found == []
