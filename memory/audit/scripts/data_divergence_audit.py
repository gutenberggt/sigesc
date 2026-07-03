"""BI-1A.5 — Auditoria READ-ONLY de divergência (D2/D6). NÃO escreve nada."""
import os, json
from collections import Counter
from pymongo import MongoClient
from dotenv import load_dotenv

os.chdir('/app/backend'); load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]

CANON_ENROLL = {'active','completed','cancelled','transferred','relocated','progressed','dropout'}
ACTIVE_LIKE = {'active','progressed','reclassified'}

out = {}

# ---------- base counts ----------
n_students = db.students.count_documents({})
n_enroll = db.enrollments.count_documents({})
n_class_students = db.class_students.count_documents({})
n_classes = db.classes.count_documents({})
n_schools = db.schools.count_documents({})
out['counts'] = dict(students=n_students, enrollments=n_enroll,
                     class_students=n_class_students, classes=n_classes, schools=n_schools)

# ---------- reference sets ----------
class_ids = set(db.classes.distinct('id'))
school_ids = set(db.schools.distinct('id'))
student_ids = set(db.students.distinct('id'))
class_school = {c['id']: c.get('school_id') for c in db.classes.find({}, {'id':1,'school_id':1})}
class_year = {c['id']: c.get('academic_year') for c in db.classes.find({}, {'id':1,'academic_year':1})}

# ---------- D2: students.class_id ----------
stu_with_class = 0; stu_empty_class = 0; stu_class_orphan = 0
students = list(db.students.find({}, {'id':1,'class_id':1,'school_id':1,'status':1}))
for s in students:
    cid = s.get('class_id')
    if cid:
        stu_with_class += 1
        if cid not in class_ids:
            stu_class_orphan += 1
    else:
        stu_empty_class += 1

# ---------- D2: enrollments integrity ----------
enrolls = list(db.enrollments.find({}, {'id':1,'student_id':1,'class_id':1,'school_id':1,'academic_year':1,'status':1}))
enr_orphan_student = enr_orphan_class = enr_orphan_school = 0
enr_school_mismatch = 0
for e in enrolls:
    if e.get('student_id') not in student_ids: enr_orphan_student += 1
    cid = e.get('class_id')
    if cid not in class_ids: enr_orphan_class += 1
    if e.get('school_id') not in school_ids: enr_orphan_school += 1
    # temporal/structural: enrollment school must equal its class school
    if cid in class_school and class_school[cid] and e.get('school_id') and class_school[cid] != e.get('school_id'):
        enr_school_mismatch += 1

# multiple active enrollments per student per year
active_by_student_year = Counter()
for e in enrolls:
    if e.get('status') in ACTIVE_LIKE:
        active_by_student_year[(e.get('student_id'), e.get('academic_year'))] += 1
multi_active = {k:v for k,v in active_by_student_year.items() if v > 1}

# ---------- D2: consistency students.class_id vs active enrollment ----------
# build map student -> set of active enrollment class_ids (latest year)
from collections import defaultdict
stu_active_classes = defaultdict(set)
stu_any_classes = defaultdict(set)
for e in enrolls:
    stu_any_classes[e.get('student_id')].add(e.get('class_id'))
    if e.get('status') in ACTIVE_LIKE:
        stu_active_classes[e.get('student_id')].add(e.get('class_id'))

consistent = divergent = no_enrollment = 0
divergence_examples = []
for s in students:
    sid = s['id']; cid = s.get('class_id')
    if not cid:
        continue
    active = stu_active_classes.get(sid, set())
    anyc = stu_any_classes.get(sid, set())
    if not anyc:
        no_enrollment += 1
    elif cid in active:
        consistent += 1
    elif cid in anyc:
        # class_id points to a non-active enrollment (e.g., transferred) -> divergence
        divergent += 1
        if len(divergence_examples) < 5:
            divergence_examples.append({'student': sid, 'student_class_id': cid, 'active_enroll_classes': list(active)})
    else:
        divergent += 1
        if len(divergence_examples) < 5:
            divergence_examples.append({'student': sid, 'student_class_id': cid, 'active_enroll_classes': list(active)})

denom = consistent + divergent
out['D2'] = dict(
    students_total=n_students,
    students_with_class_id=stu_with_class,
    students_empty_class_id=stu_empty_class,
    students_class_id_orphan=stu_class_orphan,
    enrollments_total=n_enroll,
    class_students_total=n_class_students,
    enroll_orphan_student=enr_orphan_student,
    enroll_orphan_class=enr_orphan_class,
    enroll_orphan_school=enr_orphan_school,
    enroll_school_mismatch_with_class=enr_school_mismatch,
    students_multi_active_enrollment_year=len(multi_active),
    consistency_class_vs_active_enrollment=dict(
        consistent=consistent, divergent=divergent, no_enrollment=no_enrollment,
        divergence_pct=round(100*divergent/denom,2) if denom else 0.0),
    divergence_examples=divergence_examples,
)

# ---------- D6: status distributions ----------
enr_status = Counter(e.get('status') for e in enrolls)
stu_status = Counter(s.get('status') for s in students)
enr_non_canon = {k:v for k,v in enr_status.items() if k not in CANON_ENROLL}
out['D6'] = dict(
    enrollment_status_distribution=dict(enr_status),
    enrollment_non_canonical=enr_non_canon,
    student_status_distribution=dict(stu_status),
    canonical_enrollment_set=sorted(CANON_ENROLL),
)

# ---------- Data quality per entity ----------
def pct(part, whole): return round(100*part/whole,1) if whole else 100.0
students_missing_school = sum(1 for s in students if not s.get('school_id') or s.get('school_id') not in school_ids)
# enrollment fully valid = student, class and school all exist (single pass, no double count)
enroll_fully_valid = 0
for e in enrolls:
    if (e.get('student_id') in student_ids and e.get('class_id') in class_ids
            and e.get('school_id') in school_ids):
        enroll_fully_valid += 1
out['quality'] = dict(
    students=dict(total=n_students, missing_or_orphan_school=students_missing_school,
                  consistency_pct=pct(n_students-students_missing_school, n_students)),
    enrollments=dict(total=n_enroll, fully_valid=enroll_fully_valid,
                     orphan_student=enr_orphan_student, orphan_class=enr_orphan_class,
                     orphan_school=enr_orphan_school,
                     consistency_pct=pct(enroll_fully_valid, n_enroll)),
    classes=dict(total=n_classes),
    schools=dict(total=n_schools),
)

print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
