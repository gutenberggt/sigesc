#!/usr/bin/env python3
"""Build the bounded MongoDB read-only collector for P0 #250 F2.

The collector is intentionally case-specific and emits structural metadata only.
It never emits grade values and contains no MongoDB mutation primitive.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DB_DEFAULT = "sigesc"
ACADEMIC_YEAR = 2026
TEACHER_NAME = "Abadia Alves Martins"
SCHOOL_NAME = "E M E I E F Jose Pereira Barbosa"
CLASS_NAME = "5º ANO A"
EXPECTED_COMPONENT_COUNT = 9

MUTATOR_TOKENS = (
    ".insertOne(",
    ".insertMany(",
    ".updateOne(",
    ".updateMany(",
    ".replaceOne(",
    ".deleteOne(",
    ".deleteMany(",
    ".bulkWrite(",
    ".findOneAndUpdate(",
    ".findOneAndDelete(",
    ".findOneAndReplace(",
    ".drop(",
    ".dropDatabase(",
)


def build_js(db_name: str = DB_DEFAULT) -> str:
    cfg = {
        "db": db_name,
        "academic_year": ACADEMIC_YEAR,
        "teacher_name": TEACHER_NAME,
        "school_name": SCHOOL_NAME,
        "class_name": CLASS_NAME,
        "expected_component_count": EXPECTED_COMPONENT_COUNT,
    }
    cfg_json = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))

    js = r'''const cfg = __CFG__;
const targetDb = db.getSiblingDB(cfg.db);

function uniq(values) {
  return [...new Set((values || []).filter(v => v !== null && v !== undefined).map(v => String(v)))];
}
function typeName(value) {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  return typeof value;
}
function inYear(value) {
  return value === null || value === undefined || Number(value) === Number(cfg.academic_year);
}
function normalizedStatus(value) {
  return String(value || 'active').toLowerCase();
}
function emit(payload) {
  print('P0_250_F2_AUDIT_JSON=' + JSON.stringify(payload));
}

const schools = targetDb.schools.find(
  {name: cfg.school_name},
  {_id: 0, id: 1, name: 1}
).limit(3).toArray();

const users = targetDb.users.find(
  {full_name: cfg.teacher_name},
  {_id: 0, id: 1, full_name: 1, email: 1, role: 1, roles: 1}
).limit(3).toArray();

const userIds = uniq(users.map(u => u.id));
const emails = uniq(users.map(u => u.email));
const staffQuery = {$or: []};
if (userIds.length) staffQuery.$or.push({user_id: {$in: userIds}});
if (emails.length) staffQuery.$or.push({email: {$in: emails}});
const staff = staffQuery.$or.length ? targetDb.staff.find(
  staffQuery,
  {_id: 0, id: 1, user_id: 1, email: 1, status: 1}
).limit(3).toArray() : [];

const schoolIds = uniq(schools.map(s => s.id));
const classCandidates = schoolIds.length ? targetDb.classes.find(
  {school_id: {$in: schoolIds}, name: cfg.class_name},
  {_id: 0, id: 1, name: 1, school_id: 1, academic_year: 1, grade_level: 1, status: 1}
).limit(10).toArray() : [];
const classes = classCandidates.filter(c => inYear(c.academic_year));

const identity = {
  school_matches: schools.length,
  user_matches: users.length,
  staff_matches: staff.length,
  class_matches: classes.length,
};

if (schools.length !== 1 || users.length !== 1 || staff.length !== 1 || classes.length !== 1) {
  emit({
    schema: 'P0_250_F2_PROMOTION_CASE_AUDIT_V1',
    status: 'PASS',
    classification: 'IDENTITY_AMBIGUOUS_OR_MISSING',
    database_mutation: false,
    grade_values_emitted: false,
    identity,
  });
  quit(0);
}

const school = schools[0];
const teacherUser = users[0];
const teacherStaff = staff[0];
const classDoc = classes[0];

const assignments = targetDb.teacher_assignments.find(
  {
    staff_id: teacherStaff.id,
    class_id: classDoc.id,
    academic_year: cfg.academic_year,
    status: 'ativo',
  },
  {
    _id: 0,
    id: 1,
    staff_id: 1,
    school_id: 1,
    class_id: 1,
    course_id: 1,
    academic_year: 1,
    status: 1,
    carga_horaria_semanal: 1,
  }
).limit(100).toArray();

const assignedCourseIds = uniq(assignments.map(a => a.course_id));
const courses = assignedCourseIds.length ? targetDb.courses.find(
  {id: {$in: assignedCourseIds}},
  {_id: 0, id: 1, name: 1, status: 1, nivel_ensino: 1, workload: 1, carga_horaria: 1}
).limit(100).toArray() : [];
const assignedNames = uniq(courses.map(c => c.name));
const sameNameCourses = assignedNames.length ? targetDb.courses.find(
  {name: {$in: assignedNames}},
  {_id: 0, id: 1, name: 1, status: 1}
).limit(500).toArray() : [];

// Reproduce the two student universes without exposing names or other PII.
const directStudents = targetDb.students.find(
  {class_id: classDoc.id},
  {_id: 0, id: 1, status: 1}
).limit(5000).toArray();
const enrollments = targetDb.enrollments.find(
  {class_id: classDoc.id},
  {_id: 0, student_id: 1, status: 1, academic_year: 1}
).limit(5000).toArray();

const promotionEnrollmentStatuses = new Set([
  'active', 'ativo',
  'transferred', 'transferencia', 'transferido',
  'dropout', 'desistencia', 'desistente',
]);
const promotionEnrollmentIds = enrollments
  .filter(e => promotionEnrollmentStatuses.has(normalizedStatus(e.status)) && inYear(e.academic_year))
  .map(e => e.student_id);
const promotionStudentIds = new Set(uniq(directStudents.map(s => s.id).concat(promotionEnrollmentIds)));

const byClassActiveEnrollmentIds = enrollments
  .filter(e => normalizedStatus(e.status) === 'active')
  .map(e => e.student_id);
const byClassInactiveStatuses = new Set(['transferred', 'dropout', 'relocated', 'progressed', 'reclassified']);
const byClassInactiveIds = enrollments
  .filter(e => byClassInactiveStatuses.has(normalizedStatus(e.status)))
  .map(e => e.student_id);
const byClassDirectIds = directStudents
  .filter(s => ['active', 'ativo'].includes(normalizedStatus(s.status)))
  .map(s => s.id);
const byClassStudentIds = new Set(uniq(byClassActiveEnrollmentIds.concat(byClassInactiveIds, byClassDirectIds)));

// Grade values never leave MongoDB. The projection reduces them to presence booleans.
const gradeFacts = assignedCourseIds.length ? targetDb.grades.aggregate([
  {$match: {
    class_id: classDoc.id,
    course_id: {$in: assignedCourseIds},
    academic_year: cfg.academic_year,
  }},
  {$project: {
    _id: 0,
    id: 1,
    student_id: 1,
    class_id: 1,
    course_id: 1,
    academic_year: 1,
    has_b1: {$ne: [{$ifNull: ['$b1', null]}, null]},
    has_b2: {$ne: [{$ifNull: ['$b2', null]}, null]},
    has_b3: {$ne: [{$ifNull: ['$b3', null]}, null]},
    has_b4: {$ne: [{$ifNull: ['$b4', null]}, null]},
    has_rec_s1: {$ne: [{$ifNull: ['$rec_s1', null]}, null]},
    has_rec_s2: {$ne: [{$ifNull: ['$rec_s2', null]}, null]},
  }},
]).toArray() : [];

const courseSummaries = courses.map(course => {
  const cid = String(course.id);
  const facts = gradeFacts.filter(g => String(g.course_id) === cid);
  const perStudent = new Map();
  facts.forEach(g => {
    const sid = String(g.student_id);
    perStudent.set(sid, (perStudent.get(sid) || 0) + 1);
  });
  const duplicateStudentDocuments = [...perStudent.values()].filter(n => n > 1).length;
  const nonempty = facts.filter(g => g.has_b1 || g.has_b2 || g.has_b3 || g.has_b4 || g.has_rec_s1 || g.has_rec_s2);
  const promotionMatched = facts.filter(g => promotionStudentIds.has(String(g.student_id)));
  const byClassMatched = facts.filter(g => byClassStudentIds.has(String(g.student_id)));
  const sameNameIds = uniq(sameNameCourses.filter(c => c.name === course.name).map(c => c.id));
  return {
    course_id: cid,
    course_name: course.name || null,
    course_id_type: typeName(course.id),
    assignment_count: assignments.filter(a => String(a.course_id) === cid).length,
    same_name_course_ids: sameNameIds,
    same_name_course_count: sameNameIds.length,
    grade_documents: facts.length,
    grade_documents_with_any_recorded_field: nonempty.length,
    distinct_grade_students: perStudent.size,
    duplicate_grade_student_groups: duplicateStudentDocuments,
    promotion_student_matches: promotionMatched.length,
    by_class_student_matches: byClassMatched.length,
    grade_course_id_types: uniq(facts.map(g => typeName(g.course_id))),
    grade_student_id_types: uniq(facts.map(g => typeName(g.student_id))),
  };
});

const mismatchCourses = courseSummaries.filter(c => c.promotion_student_matches !== c.by_class_student_matches);
const duplicateGradeCourses = courseSummaries.filter(c => c.duplicate_grade_student_groups > 0);
const typeMismatchCourses = courseSummaries.filter(c =>
  c.grade_course_id_types.some(t => t !== c.course_id_type)
);

let classification = 'DATA_PATHS_STRUCTURALLY_EQUIVALENT';
if (assignments.length !== cfg.expected_component_count || assignedCourseIds.length !== cfg.expected_component_count) {
  classification = 'ASSIGNMENT_TOPOLOGY_DRIFT';
} else if (courses.length !== assignedCourseIds.length) {
  classification = 'COURSE_REFERENCE_GAP';
} else if (duplicateGradeCourses.length > 0) {
  classification = 'DUPLICATE_GRADE_DOCUMENTS';
} else if (mismatchCourses.length > 0) {
  classification = 'PROMOTION_BYCLASS_STUDENT_SET_DIVERGENCE';
} else if (typeMismatchCourses.length > 0) {
  classification = 'ID_TYPE_DIVERGENCE';
}

emit({
  schema: 'P0_250_F2_PROMOTION_CASE_AUDIT_V1',
  status: 'PASS',
  classification,
  database_mutation: false,
  production_writes: false,
  grade_values_emitted: false,
  target: {
    academic_year: cfg.academic_year,
    school_id: String(school.id),
    class_id: String(classDoc.id),
    staff_id: String(teacherStaff.id),
    user_id: String(teacherUser.id),
  },
  identity,
  assignment_count: assignments.length,
  assigned_course_count: assignedCourseIds.length,
  resolved_course_count: courses.length,
  direct_student_count: directStudents.length,
  enrollment_count: enrollments.length,
  promotion_student_universe_count: promotionStudentIds.size,
  by_class_student_universe_count: byClassStudentIds.size,
  course_summaries: courseSummaries,
});
'''.replace("__CFG__", cfg_json)

    assert_read_only(js)
    return js


def assert_read_only(js: str) -> None:
    for token in MUTATOR_TOKENS:
        if token in js:
            raise ValueError(f"P0_250_F2_MUTATOR_TOKEN_FOUND:{token}")
    if "grade_values_emitted: false" not in js:
        raise ValueError("P0_250_F2_GRADE_VALUE_BOUNDARY_MISSING")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_DEFAULT)
    parser.add_argument("--js", required=True)
    args = parser.parse_args()
    js = build_js(args.db)
    path = Path(args.js)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(js, encoding="utf-8")
    print("P0_250_F2_COLLECTOR_BUILD=PASS")
    print("DATABASE_MUTATION=NO")
    print("GRADE_VALUES_EMITTED=NO")


if __name__ == "__main__":
    main()
