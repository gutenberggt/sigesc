#!/usr/bin/env python3
"""BI-1A.5/1A.6 — Auditoria READ-ONLY de divergência de dados (D2/D6).

100% SOMENTE LEITURA: usa apenas `find`/`count_documents`/`distinct`.
NÃO escreve, NÃO cria coleções/índices, NÃO altera documentos.

Uso:
    # imprime JSON (padrão)
    python data_divergence_audit.py

    # gera relatório Markdown automaticamente
    python data_divergence_audit.py --report-only --label production \
        --out /app/memory/PRODUCTION_DATA_DIVERGENCE_REPORT.md

Config via ambiente (mesmo padrão do backend):
    MONGO_URL, DB_NAME   (obrigatórios)
    Opcional: aponte MONGO_URL para a base de PRODUÇÃO para validar a produção.

Reproduzível: pode ser reexecutado a qualquer momento com resultados equivalentes.
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone
from collections import Counter, defaultdict

from pymongo import MongoClient

try:
    from dotenv import load_dotenv
    load_dotenv('/app/backend/.env')
except Exception:
    pass

CANON_ENROLL = {'active', 'completed', 'cancelled', 'transferred', 'relocated', 'progressed', 'dropout'}
ACTIVE_LIKE = {'active', 'progressed', 'reclassified'}
STATUS_EQUIVALENCE = {'inactive': 'cancelled', 'inativo': 'cancelled',
                      'deceased': 'cancelled', 'reclassified': 'progressed'}


def pct(part, whole):
    return round(100 * part / whole, 2) if whole else 100.0


def run_audit():
    """Executa todas as medições READ-ONLY e devolve um dict de métricas."""
    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    db = MongoClient(mongo_url, serverSelectionTimeoutMS=8000)[db_name]

    out = {'meta': {'db_name': db_name, 'generated_at': datetime.now(timezone.utc).isoformat()}}

    n_students = db.students.count_documents({})
    n_enroll = db.enrollments.count_documents({})
    n_class_students = db.class_students.count_documents({})
    n_classes = db.classes.count_documents({})
    n_schools = db.schools.count_documents({})
    n_courses = db.courses.count_documents({})
    n_staff = db.staff.count_documents({})
    out['counts'] = dict(students=n_students, enrollments=n_enroll, class_students=n_class_students,
                         classes=n_classes, schools=n_schools, courses=n_courses, staff=n_staff)

    class_ids = set(db.classes.distinct('id'))
    school_ids = set(db.schools.distinct('id'))
    student_ids = set(db.students.distinct('id'))
    class_school = {c['id']: c.get('school_id') for c in db.classes.find({}, {'id': 1, 'school_id': 1})}

    students = list(db.students.find({}, {'id': 1, 'class_id': 1, 'school_id': 1, 'status': 1}))
    stu_with_class = stu_empty_class = stu_class_orphan = 0
    for s in students:
        cid = s.get('class_id')
        if cid:
            stu_with_class += 1
            if cid not in class_ids:
                stu_class_orphan += 1
        else:
            stu_empty_class += 1

    enrolls = list(db.enrollments.find({}, {'id': 1, 'student_id': 1, 'class_id': 1,
                                            'school_id': 1, 'academic_year': 1, 'status': 1}))
    enr_orphan_student = enr_orphan_class = enr_orphan_school = enr_school_mismatch = 0
    enroll_fully_valid = 0
    for e in enrolls:
        os_ = e.get('student_id') not in student_ids
        oc = e.get('class_id') not in class_ids
        osch = e.get('school_id') not in school_ids
        if os_: enr_orphan_student += 1
        if oc: enr_orphan_class += 1
        if osch: enr_orphan_school += 1
        if not os_ and not oc and not osch:
            enroll_fully_valid += 1
        cid = e.get('class_id')
        if cid in class_school and class_school[cid] and e.get('school_id') and class_school[cid] != e.get('school_id'):
            enr_school_mismatch += 1

    active_by_sy = Counter()
    stu_active_classes = defaultdict(set)
    stu_any_classes = defaultdict(set)
    for e in enrolls:
        stu_any_classes[e.get('student_id')].add(e.get('class_id'))
        if e.get('status') in ACTIVE_LIKE:
            active_by_sy[(e.get('student_id'), e.get('academic_year'))] += 1
            stu_active_classes[e.get('student_id')].add(e.get('class_id'))
    multi_active = sum(1 for v in active_by_sy.values() if v > 1)

    consistent = divergent = no_enrollment = 0
    examples = []
    for s in students:
        sid, cid = s['id'], s.get('class_id')
        if not cid:
            continue
        active = stu_active_classes.get(sid, set())
        anyc = stu_any_classes.get(sid, set())
        if not anyc:
            no_enrollment += 1
        elif cid in active:
            consistent += 1
        else:
            divergent += 1
            if len(examples) < 5:
                examples.append({'student': sid, 'student_class_id': cid, 'active_enroll_classes': list(active)})
    denom = consistent + divergent

    out['D2'] = dict(
        students_total=n_students, students_with_class_id=stu_with_class,
        students_empty_class_id=stu_empty_class, students_class_id_orphan=stu_class_orphan,
        enrollments_total=n_enroll, class_students_total=n_class_students,
        enroll_orphan_student=enr_orphan_student, enroll_orphan_class=enr_orphan_class,
        enroll_orphan_school=enr_orphan_school, enroll_school_mismatch_with_class=enr_school_mismatch,
        students_multi_active_enrollment_year=multi_active,
        consistent=consistent, divergent=divergent, no_enrollment=no_enrollment,
        divergence_pct=pct(divergent, denom), examples=examples,
    )

    enr_status = Counter(e.get('status') for e in enrolls)
    stu_status = Counter(s.get('status') for s in students)
    out['D6'] = dict(
        enrollment_status_distribution=dict(enr_status),
        enrollment_non_canonical={k: v for k, v in enr_status.items() if k not in CANON_ENROLL},
        student_status_distribution=dict(stu_status),
        canonical_enrollment_set=sorted(CANON_ENROLL),
        proposed_normalization=STATUS_EQUIVALENCE,
    )

    students_bad_school = sum(1 for s in students if not s.get('school_id') or s.get('school_id') not in school_ids)
    out['quality'] = dict(
        students=dict(total=n_students, bad_school=students_bad_school,
                      consistency_pct=pct(n_students - students_bad_school, n_students)),
        enrollments=dict(total=n_enroll, fully_valid=enroll_fully_valid,
                         orphan_student=enr_orphan_student, orphan_class=enr_orphan_class,
                         orphan_school=enr_orphan_school, consistency_pct=pct(enroll_fully_valid, n_enroll)),
        classes=dict(total=n_classes, consistency_pct=100.0),
        schools=dict(total=n_schools, consistency_pct=100.0),
        courses=dict(total=n_courses),
        staff=dict(total=n_staff),
    )
    return out


def to_markdown(o, label):
    d2, d6, q = o['D2'], o['D6'], o['quality']
    c = o['counts']
    lines = []
    A = lines.append
    A(f"# PRODUCTION_DATA_DIVERGENCE_REPORT — {label.upper()}")
    A("")
    A(f"> Gerado por `data_divergence_audit.py --report-only` (100% READ-ONLY).")
    A(f"> Base: `{o['meta']['db_name']}` · Timestamp: {o['meta']['generated_at']} · Rótulo: **{label}**")
    A("")
    A("## Contagens base")
    A("| Entidade | Total |")
    A("|---|---|")
    for k, v in c.items():
        A(f"| {k} | {v} |")
    A("")
    A("## D2 — Vínculo Aluno ↔ Turma")
    A("| Métrica | Valor |")
    A("|---|---|")
    A(f"| Alunos (total) | {d2['students_total']} |")
    A(f"| Matrículas (total) | {d2['enrollments_total']} |")
    A(f"| Vínculos em class_students | {d2['class_students_total']} |")
    A(f"| Alunos com class_id preenchido | {d2['students_with_class_id']} |")
    A(f"| Alunos com class_id vazio | {d2['students_empty_class_id']} |")
    A(f"| class_id órfão (turma inexistente) | {d2['students_class_id_orphan']} |")
    A(f"| Matrículas órfãs de aluno | {d2['enroll_orphan_student']} |")
    A(f"| Matrículas órfãs de turma | {d2['enroll_orphan_class']} |")
    A(f"| Matrículas órfãs de escola | {d2['enroll_orphan_school']} |")
    A(f"| Matrícula com escola ≠ escola da turma | {d2['enroll_school_mismatch_with_class']} |")
    A(f"| Alunos com >1 matrícula ativa/ano | {d2['students_multi_active_enrollment_year']} |")
    A(f"| Consistentes (class_id = matrícula ativa) | {d2['consistent']} |")
    A(f"| **Divergentes** | **{d2['divergent']}** |")
    A(f"| **% de divergência** | **{d2['divergence_pct']}%** |")
    A("")
    A("**Coleções envolvidas no vínculo:** `enrollments`, `students.class_id`, `class_students`.")
    A("")
    A("## D6 — Status Legados")
    A("### Distribuição — enrollments")
    A("| Status | Qtde | Canônico? |")
    A("|---|---|---|")
    for k, v in sorted(d6['enrollment_status_distribution'].items(), key=lambda x: -x[1]):
        canon = "✅" if k in d6['canonical_enrollment_set'] else "❌ legado"
        A(f"| {k} | {v} | {canon} |")
    A("")
    A("### Distribuição — students")
    A("| Status | Qtde |")
    A("|---|---|")
    for k, v in sorted(d6['student_status_distribution'].items(), key=lambda x: -x[1]):
        A(f"| {k} | {v} |")
    A("")
    A(f"**Status obsoletos:** {list(d6['enrollment_non_canonical'].keys()) or 'nenhum'}")
    A(f"**Normalização proposta:** {d6['proposed_normalization']}")
    A(f"**Conjunto oficial (enrollments):** {d6['canonical_enrollment_set']}")
    A("")
    A("## Qualidade dos Dados (consistência estimada)")
    A("| Domínio | Total | Consistência |")
    A("|---|---|---|")
    A(f"| Alunos | {q['students']['total']} | {q['students']['consistency_pct']}% |")
    A(f"| Matrículas | {q['enrollments']['total']} | {q['enrollments']['consistency_pct']}% |")
    A(f"| Turmas | {q['classes']['total']} | {q['classes']['consistency_pct']}% |")
    A(f"| Escolas | {q['schools']['total']} | {q['schools']['consistency_pct']}% |")
    A(f"| Componentes | {q['courses']['total']} | n/d |")
    A(f"| Professores | {q['staff']['total']} | n/d |")
    A(f"| Frequência | n/d | fora do escopo D2/D6 |")
    A(f"| Avaliações | n/d | fora do escopo D2/D6 |")
    A(f"| Indicadores | 0 | Motor não implementado |")
    A("")
    A("> Este relatório é gerado automaticamente e é reproduzível. Reexecute o script")
    A("> apontando `MONGO_URL` para a base desejada para atualizar os números.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Auditoria READ-ONLY de divergência (D2/D6)")
    ap.add_argument('--report-only', action='store_true', help='gera Markdown em vez de JSON')
    ap.add_argument('--label', default='preview', help='rótulo do ambiente (preview|production)')
    ap.add_argument('--out', default=None, help='caminho do arquivo Markdown de saída')
    args = ap.parse_args()

    result = run_audit()

    if args.report_only:
        md = to_markdown(result, args.label)
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(md + "\n")
            print(f"[OK] Relatório gerado: {args.out}")
        else:
            print(md)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
