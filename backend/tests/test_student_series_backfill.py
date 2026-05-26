"""
[Sprint 1.2] Testes do backfill `student_series` em `routers/student_series_backfill.py`.

Cobre a categorização A/B/C/D/E com hard invariants:
  - NUNCA sobrescreve `student_series` já preenchido
  - B (multisseriada com series=[única]) só fill quando consistência OK
  - SKIP puro em D (sem matrícula) e E (turma sem grade_level)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routers.student_series_backfill import (  # noqa: E402
    _build_diagnostic,
    _build_class_series_consistency_map,
    _is_empty,
    _execute_backfill_work,
    BackfillRequest,
)


# ---------------------------------------------------------------------------
# Fake Mongo mínimo (find + aggregate + update_one)
# ---------------------------------------------------------------------------
class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()

    async def to_list(self, length=None):
        if length is None:
            return [dict(d) for d in self._docs]
        return [dict(d) for d in self._docs[:length]]


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query, projection=None):
        out = [d for d in self.docs if self._match(d, query)]
        return _Cursor(out)

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if self._match(d, query):
                return dict(d)
        return None

    async def count_documents(self, query):
        return sum(1 for d in self.docs if self._match(d, query))

    def aggregate(self, pipeline):
        # Implementação minimal para os pipelines deste teste:
        # 1. _build_class_series_consistency_map (join enrollments→students)
        if (pipeline and pipeline[0].get("$match", {}).get("status") == "active"
                and any("$lookup" in s and s["$lookup"]["from"] == "students" for s in pipeline)):
            return self._agg_class_consistency(pipeline)
        return _Cursor([])

    def _agg_class_consistency(self, _pipeline):
        # Não temos acesso à collection students aqui — o teste usa _FakeDB
        # que faz o join manualmente em outra função
        return _Cursor([])

    async def update_one(self, query, update):
        for i, d in enumerate(self.docs):
            if self._match(d, query):
                if "$set" in update:
                    self.docs[i] = {**d, **update["$set"]}
                return type("R", (), {"modified_count": 1, "matched_count": 1})()
        return type("R", (), {"modified_count": 0, "matched_count": 0})()

    @staticmethod
    def _match(doc, query):
        for k, v in query.items():
            if k == "$or":
                if not any(_Collection._match(doc, sub) for sub in v):
                    return False
                continue
            if k == "$and":
                if not all(_Collection._match(doc, sub) for sub in v):
                    return False
                continue
            actual = doc.get(k)
            if isinstance(v, dict):
                if "$exists" in v:
                    exists = k in doc
                    if v["$exists"] != exists:
                        return False
                if "$in" in v:
                    if actual not in v["$in"]:
                        return False
                if "$nin" in v:
                    if actual in v["$nin"]:
                        return False
                if "$ne" in v:
                    if actual == v["$ne"]:
                        return False
            else:
                if actual != v:
                    return False
        return True


class _FakeDB:
    """DB com aggregate customizado para o pipeline de consistência."""
    def __init__(self, students=None, enrollments=None, classes=None, schools=None):
        self.students = _Collection(students or [])
        self.enrollments = _Collection(enrollments or [])
        self.classes = _Collection(classes or [])
        self.schools = _Collection(schools or [])

        # Override aggregate de enrollments para implementar o pipeline
        orig_agg = self.enrollments.aggregate

        def custom_agg(pipeline):
            # Detecta o pipeline de consistência (lookup students)
            if any("$lookup" in s and s["$lookup"].get("from") == "students" for s in pipeline):
                out = []
                # Group: class_id → set(student_series) dos students preenchidos
                # com matrícula ativa
                series_by_class: dict = {}
                for e in self.enrollments.docs:
                    if e.get("status") != "active" or not e.get("class_id"):
                        continue
                    stu = next((s for s in self.students.docs if s["id"] == e["student_id"]), None)
                    if stu and stu.get("student_series") not in [None, ""]:
                        series_by_class.setdefault(e["class_id"], set()).add(stu["student_series"])
                for cid, s in series_by_class.items():
                    out.append({"_id": cid, "series_set": list(s)})
                return _Cursor(out)
            return orig_agg(pipeline)

        self.enrollments.aggregate = custom_agg


def _aio(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------
def test_is_empty_handles_none_empty_and_whitespace():
    assert _is_empty(None) is True
    assert _is_empty("") is True
    assert _is_empty("   ") is True
    assert _is_empty("1º Ano") is False


def test_category_A_regular_class_fills_with_grade_level():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "Aluno A", "status": "active",
                   "student_series": None, "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"}],
        classes=[{"id": "c1", "name": "1A", "grade_level": "1º Ano",
                  "is_multi_grade": False, "school_id": "sch1"}],
        schools=[{"id": "sch1", "name": "Escola X"}],
    )
    diag = _aio(_build_diagnostic(db))
    assert diag["total_eligible"] == 1
    assert diag["would_fill"]["scenario_A_regular"] == 1
    assert diag["would_fill"]["scenario_B_single_multi_consistent"] == 0
    assert diag["skipped"]["total"] == 0
    assert diag["_candidates_A"][0]["fill_with"] == "1º Ano"


def test_category_B_multi_with_single_series_and_consistency_passes():
    db = _FakeDB(
        students=[
            {"id": "s1", "full_name": "A", "status": "active", "student_series": None, "school_id": "sch1"},
            {"id": "s2", "full_name": "B", "status": "active", "student_series": "2º Ano", "school_id": "sch1"},
        ],
        enrollments=[
            {"id": "e1", "student_id": "s1", "class_id": "cm", "status": "active"},
            {"id": "e2", "student_id": "s2", "class_id": "cm", "status": "active"},
        ],
        classes=[{"id": "cm", "name": "Multi", "grade_level": "2º Ano",
                  "is_multi_grade": True, "series": ["2º Ano"], "school_id": "sch1"}],
        schools=[{"id": "sch1", "name": "Escola X"}],
    )
    diag = _aio(_build_diagnostic(db))
    # Outro aluno tem series=2º Ano (consistente com series[0])
    assert diag["would_fill"]["scenario_B_single_multi_consistent"] == 1
    assert diag["_candidates_B"][0]["fill_with"] == "2º Ano"


def test_category_C_multi_inconsistent_filled_students_goes_to_skip():
    """Multisseriada com series=[X] mas outros alunos preenchidos com Y → SKIP C."""
    db = _FakeDB(
        students=[
            {"id": "s1", "full_name": "A", "status": "active", "student_series": None, "school_id": "sch1"},
            {"id": "s2", "full_name": "B", "status": "active", "student_series": "3º Ano", "school_id": "sch1"},
        ],
        enrollments=[
            {"id": "e1", "student_id": "s1", "class_id": "cm", "status": "active"},
            {"id": "e2", "student_id": "s2", "class_id": "cm", "status": "active"},
        ],
        classes=[{"id": "cm", "name": "Multi", "grade_level": "2º Ano",
                  "is_multi_grade": True, "series": ["2º Ano"], "school_id": "sch1"}],
    )
    diag = _aio(_build_diagnostic(db))
    assert diag["would_fill"]["total"] == 0
    assert diag["skipped"]["scenario_C_multi_ambiguous"] == 1
    skip = diag["sample_skipped"]["C"][0]
    assert "multi_grade_inconsistent_filled_students" in skip["reason"]


def test_category_C_multi_with_two_or_more_series():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active", "student_series": None, "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "cm", "status": "active"}],
        classes=[{"id": "cm", "name": "Multi", "grade_level": "2º Ano",
                  "is_multi_grade": True, "series": ["2º Ano", "3º Ano"], "school_id": "sch1"}],
    )
    diag = _aio(_build_diagnostic(db))
    assert diag["skipped"]["scenario_C_multi_ambiguous"] == 1


def test_category_D_student_without_active_enrollment_is_skipped():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active", "student_series": None, "school_id": "sch1"}],
        enrollments=[],
        classes=[],
    )
    diag = _aio(_build_diagnostic(db))
    assert diag["skipped"]["scenario_D_no_active_enrollment"] == 1


def test_category_E_class_without_grade_level_is_skipped():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active", "student_series": None, "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"}],
        classes=[{"id": "c1", "name": "Turma X", "grade_level": "",
                  "is_multi_grade": False, "school_id": "sch1"}],
    )
    diag = _aio(_build_diagnostic(db))
    assert diag["skipped"]["scenario_E_incomplete_data"] == 1


def test_hard_invariant_never_overwrites_filled_student_series():
    """Aluno COM student_series preenchido NÃO é elegível."""
    db = _FakeDB(
        students=[
            {"id": "s1", "full_name": "Já preenchido", "status": "active",
             "student_series": "5º Ano", "school_id": "sch1"},
            {"id": "s2", "full_name": "Vazio", "status": "active",
             "student_series": None, "school_id": "sch1"},
        ],
        enrollments=[
            {"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"},
            {"id": "e2", "student_id": "s2", "class_id": "c1", "status": "active"},
        ],
        classes=[{"id": "c1", "name": "1A", "grade_level": "1º Ano",
                  "is_multi_grade": False, "school_id": "sch1"}],
    )
    diag = _aio(_build_diagnostic(db))
    # Apenas s2 é elegível (s1 já preenchido)
    assert diag["total_eligible"] == 1
    assert diag["would_fill"]["scenario_A_regular"] == 1
    candidate_ids = [c["student_id"] for c in diag["_candidates_A"]]
    assert "s1" not in candidate_ids


def test_dry_run_does_not_apply_changes():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active",
                   "student_series": None, "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"}],
        classes=[{"id": "c1", "name": "1A", "grade_level": "1º Ano",
                  "is_multi_grade": False, "school_id": "sch1"}],
    )
    result = _aio(_execute_backfill_work(db, BackfillRequest(dry_run=True), run_id_hint="test-run"))
    assert result["summary"]["would_fill"] == 1
    assert result["summary"]["filled"] == 0
    # student_series ainda vazio
    assert db.students.docs[0].get("student_series") is None


def test_apply_writes_telemetry_fields_on_student():
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active",
                   "student_series": None, "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"}],
        classes=[{"id": "c1", "name": "1A", "grade_level": "1º Ano",
                  "is_multi_grade": False, "school_id": "sch1"}],
    )
    result = _aio(_execute_backfill_work(db, BackfillRequest(dry_run=False), run_id_hint="run-xyz"))
    assert result["summary"]["filled"] == 1
    s1 = db.students.docs[0]
    assert s1["student_series"] == "1º Ano"
    assert s1["series_backfill_run_id"] == "run-xyz"
    assert s1["series_backfill_source"] == "classes.grade_level"
    assert "series_backfill_at" in s1


def test_apply_respects_hard_invariant_with_guard_filter():
    """Guard `$or [exists:False, None, ""]` no update protege contra race
    com outro processo que preencheu student_series entre find e update."""
    db = _FakeDB(
        students=[{"id": "s1", "full_name": "A", "status": "active",
                   "student_series": "JA_PREENCHIDO_POR_OUTRO", "school_id": "sch1"}],
        enrollments=[{"id": "e1", "student_id": "s1", "class_id": "c1", "status": "active"}],
        classes=[{"id": "c1", "name": "1A", "grade_level": "1º Ano",
                  "is_multi_grade": False, "school_id": "sch1"}],
    )
    # s1 já preenchido — _find_eligible_students nem retorna
    # (mas o teste exercita também o caminho do guard)
    result = _aio(_execute_backfill_work(db, BackfillRequest(dry_run=False), run_id_hint="r1"))
    assert result["summary"]["filled"] == 0
    # student_series original preservado
    assert db.students.docs[0]["student_series"] == "JA_PREENCHIDO_POR_OUTRO"
