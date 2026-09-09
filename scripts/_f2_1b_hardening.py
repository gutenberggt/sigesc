from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

service = ROOT / "backend/services/enrollment_rectification_grades.py"
text = service.read_text(encoding="utf-8")
old = '''def _cas_filter(doc: Mapping[str, Any]) -> dict[str, Any]:\n    """CAS pelo subconjunto acadêmico que compõe o fingerprint F2.1B."""\n    query: dict[str, Any] = {\n        "id": doc.get("id"),\n        "mantenedora_id": doc.get("mantenedora_id"),\n        "student_id": doc.get("student_id"),\n        "class_id": doc.get("class_id"),\n        "course_id": doc.get("course_id"),\n        "academic_year": doc.get("academic_year"),\n        "dependency_id": doc.get("dependency_id"),\n        "grade_ownership": doc.get("grade_ownership") or {},\n        "rectified_fields": doc.get("rectified_fields") or {},\n    }\n    for field in GRADE_VALUE_FIELDS:\n        query[field] = doc.get(field)\n    return query\n'''
new = '''def _cas_filter(doc: Mapping[str, Any]) -> dict[str, Any]:\n    """CAS pelo subconjunto acadêmico que compõe o fingerprint F2.1B.\n\n    Documentos legados podem não possuir fisicamente `grade_ownership` ou\n    `rectified_fields`. O fingerprint normaliza ausência para mapa vazio; o CAS\n    preserva essa semântica sem exigir que o campo legado exista.\n    """\n    query: dict[str, Any] = {\n        "id": doc.get("id"),\n        "mantenedora_id": doc.get("mantenedora_id"),\n        "student_id": doc.get("student_id"),\n        "class_id": doc.get("class_id"),\n        "course_id": doc.get("course_id"),\n        "academic_year": doc.get("academic_year"),\n        "dependency_id": doc.get("dependency_id"),\n    }\n    if "grade_ownership" in doc:\n        query["grade_ownership"] = doc.get("grade_ownership") or {}\n    else:\n        query["grade_ownership"] = {"$exists": False}\n    if "rectified_fields" in doc:\n        query["rectified_fields"] = doc.get("rectified_fields") or {}\n    else:\n        query["rectified_fields"] = {"$exists": False}\n    for field in GRADE_VALUE_FIELDS:\n        query[field] = doc.get(field)\n    return query\n'''
if old not in text:
    raise SystemExit("F2.1B hardening: CAS anchor not found")
service.write_text(text.replace(old, new, 1), encoding="utf-8")

tests = ROOT / "backend/tests/test_enrollment_rectification_f2_1b_grades.py"
t = tests.read_text(encoding="utf-8")
anchor = '''@pytest.mark.asyncio\nasync def test_replay_after_applied_is_idempotent(db):\n'''
extra = '''@pytest.mark.asyncio\nasync def test_legacy_documents_without_metadata_maps_are_supported_by_cas(db):\n    src = source_grade()\n    src.pop("grade_ownership", None)\n    src.pop("rectified_fields", None)\n    dst = destination_grade()\n    dst.pop("rectified_fields", None)\n    await db.grades.insert_many([deepcopy(src), deepcopy(dst)])\n    out = await apply(db, manifest(src, dst))\n    assert out["state"] == "APPLIED"\n    updated = await db.grades.find_one({"id": dst["id"]}, {"_id": 0})\n    assert updated["b1"] == 8.0 and updated["b2"] == 6.0\n    assert "b1" not in (updated.get("grade_ownership") or {})\n    assert await db.grades.find_one({"id": src["id"]}) is None\n\n\n'''
if anchor not in t:
    raise SystemExit("F2.1B hardening: test anchor not found")
tests.write_text(t.replace(anchor, extra + anchor, 1), encoding="utf-8")
print("F2.1B legacy CAS hardening applied")
