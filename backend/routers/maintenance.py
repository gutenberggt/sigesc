"""
Router para Manutenção.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, Request
from datetime import datetime, timezone
import logging

from models import *
from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)


router = APIRouter(tags=["Manutenção"])


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    
    # Helper para obter DB correto (produção ou sandbox)
    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db



    @router.get("/maintenance/orphan-check")
    async def check_orphan_data(request: Request):
        """
        Verifica dados órfãos no sistema.
        Apenas admin pode executar.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'orphans': [],
            'summary': {
                'enrollments': 0,
                'grades': 0,
                'school_assignments': 0,
                'teacher_assignments': 0,
                'total': 0
            }
        }

        # Verifica matrículas órfãs
        enrollments = await db.enrollments.find({}, {"_id": 0, "id": 1, "student_id": 1, "school_id": 1, "class_id": 1}).to_list(10000)
        for enrollment in enrollments:
            issues = []
            student = await db.students.find_one({"id": enrollment.get('student_id')})
            if not student:
                issues.append("Aluno não encontrado")
            school = await db.schools.find_one({"id": enrollment.get('school_id')})
            if not school:
                issues.append("Escola não encontrada")
            if enrollment.get('class_id'):
                class_doc = await db.classes.find_one({"id": enrollment.get('class_id')})
                if not class_doc:
                    issues.append("Turma não encontrada")
            if issues:
                results['orphans'].append({'type': 'enrollment', 'id': enrollment.get('id'), 'issues': issues})
                results['summary']['enrollments'] += 1

        # Verifica lotações órfãs
        assignments = await db.school_assignments.find({}, {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1}).to_list(10000)
        for assignment in assignments:
            issues = []
            staff = await db.staff.find_one({"id": assignment.get('staff_id')})
            if not staff:
                issues.append("Servidor não encontrado")
            school = await db.schools.find_one({"id": assignment.get('school_id')})
            if not school:
                issues.append("Escola não encontrada")
            if issues:
                results['orphans'].append({'type': 'school_assignment', 'id': assignment.get('id'), 'issues': issues})
                results['summary']['school_assignments'] += 1

        # Verifica alocações de professores órfãs
        teacher_assignments = await db.teacher_assignments.find({}, {"_id": 0, "id": 1, "staff_id": 1, "school_id": 1, "class_id": 1}).to_list(10000)
        for assignment in teacher_assignments:
            issues = []
            staff = await db.staff.find_one({"id": assignment.get('staff_id')})
            if not staff:
                issues.append("Servidor não encontrado")
            school = await db.schools.find_one({"id": assignment.get('school_id')})
            if not school:
                issues.append("Escola não encontrada")
            class_doc = await db.classes.find_one({"id": assignment.get('class_id')})
            if not class_doc:
                issues.append("Turma não encontrada")
            if issues:
                results['orphans'].append({'type': 'teacher_assignment', 'id': assignment.get('id'), 'issues': issues})
                results['summary']['teacher_assignments'] += 1

        results['summary']['total'] = (
            results['summary']['enrollments'] +
            results['summary']['grades'] +
            results['summary']['school_assignments'] +
            results['summary']['teacher_assignments']
        )

        return results


    @router.delete("/maintenance/orphan-cleanup")
    async def cleanup_orphan_data(request: Request, dry_run: bool = True):
        """
        Remove dados órfãos do sistema.
        Apenas admin pode executar.
        Use dry_run=false para executar a limpeza real.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        # Primeiro, obtém lista de órfãos
        orphan_check = await check_orphan_data(request)

        if dry_run:
            return {
                'mode': 'dry_run',
                'message': 'Nenhuma alteração foi feita. Use dry_run=false para executar a limpeza.',
                'would_delete': orphan_check['summary']
            }

        deleted = {
            'enrollments': 0,
            'school_assignments': 0,
            'teacher_assignments': 0,
            'total': 0
        }

        for orphan in orphan_check['orphans']:
            try:
                if orphan['type'] == 'enrollment':
                    await db.enrollments.delete_one({"id": orphan['id']})
                    deleted['enrollments'] += 1
                elif orphan['type'] == 'school_assignment':
                    await db.school_assignments.delete_one({"id": orphan['id']})
                    deleted['school_assignments'] += 1
                elif orphan['type'] == 'teacher_assignment':
                    await db.teacher_assignments.delete_one({"id": orphan['id']})
                    deleted['teacher_assignments'] += 1
            except Exception as e:
                logger.error(f"Falha ao remover registro órfão {orphan.get('type')}/{orphan.get('id')}: {e}")

        deleted['total'] = deleted['enrollments'] + deleted['school_assignments'] + deleted['teacher_assignments']

        # Registra auditoria da limpeza
        await audit_service.log(
            action='delete',
            collection='system',
            user=current_user,
            request=request,
            description=f"Executou limpeza de dados órfãos: {deleted['total']} registros removidos",
            extra_data=deleted
        )

        return {
            'mode': 'executed',
            'deleted': deleted
        }


    @router.get("/maintenance/duplicate-courses")
    async def check_duplicate_courses(request: Request):
        """
        Verifica componentes curriculares duplicados.
        Apenas admin pode executar.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        courses = await db.courses.find({}, {"_id": 0}).to_list(500)

        # Agrupar por nome + nivel_ensino
        groups = {}
        for course in courses:
            key = (course.get('name', ''), course.get('nivel_ensino', ''))
            if key not in groups:
                groups[key] = []
            groups[key].append(course)

        # Encontrar duplicados
        duplicates = []
        for key, courses_list in groups.items():
            if len(courses_list) > 1:
                duplicates.append({
                    'name': key[0],
                    'nivel_ensino': key[1],
                    'count': len(courses_list),
                    'courses': courses_list
                })

        return {
            'total_duplicates': len(duplicates),
            'duplicates': duplicates
        }


    @router.post("/maintenance/consolidate-courses")
    async def consolidate_duplicate_courses(request: Request, dry_run: bool = True):
        """
        Consolida componentes curriculares duplicados.
        Apenas admin pode executar.
        Une os grade_levels de componentes com mesmo nome e nivel_ensino.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        # Obter duplicados
        dup_check = await check_duplicate_courses(request)

        if dry_run:
            return {
                'mode': 'dry_run',
                'message': 'Nenhuma alteração foi feita. Use dry_run=false para executar.',
                'would_consolidate': dup_check
            }

        consolidated = []

        for dup in dup_check['duplicates']:
            courses_list = dup['courses']
            if len(courses_list) < 2:
                continue

            # Escolher o primeiro como base
            base_course = courses_list[0]
            base_id = base_course.get('id')

            # Unir grade_levels de todos os duplicados
            all_grade_levels = set()
            for c in courses_list:
                grade_levels = c.get('grade_levels', [])
                if grade_levels:
                    all_grade_levels.update(grade_levels)

            # Atualizar o componente base com todos os grade_levels
            if all_grade_levels:
                sorted_levels = sorted(list(all_grade_levels), key=lambda x: (
                    0 if 'º Ano' in x else 1,
                    int(''.join(filter(str.isdigit, x)) or 0)
                ))
                await db.courses.update_one(
                    {"id": base_id},
                    {"$set": {"grade_levels": sorted_levels}}
                )

            # Remover os duplicados (manter apenas o primeiro)
            removed_ids = []
            for c in courses_list[1:]:
                await db.courses.delete_one({"id": c.get('id')})
                removed_ids.append(c.get('id'))

            consolidated.append({
                'name': dup['name'],
                'nivel_ensino': dup['nivel_ensino'],
                'kept_id': base_id,
                'removed_ids': removed_ids,
                'unified_grade_levels': sorted_levels if all_grade_levels else []
            })

        # Registra auditoria
        await audit_service.log(
            action='update',
            collection='courses',
            user=current_user,
            request=request,
            description=f"Consolidou {len(consolidated)} componentes curriculares duplicados",
            extra_data={'consolidated': consolidated}
        )

        return {
            'mode': 'executed',
            'consolidated': consolidated,
            'total': len(consolidated)
        }



    @router.post("/maintenance/cleanup-cancelled-enrollments")
    async def cleanup_cancelled_enrollments(request: Request, dry_run: bool = True):
        """
        Limpeza retroativa de matrículas canceladas.
        Remove frequências, notas e matrículas de alunos com status 'cancelled'.
        Seta o aluno como 'inactive' sem escola/turma.
        Use dry_run=false para executar a limpeza real.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        cancelled_students = await db.students.find(
            {"status": {"$in": ["cancelled", "cancelado"]}},
            {"_id": 0, "id": 1, "full_name": 1, "status": 1}
        ).to_list(1000)

        cancelled_enrollments = await db.enrollments.find(
            {"status": "cancelled"},
            {"_id": 0, "student_id": 1, "class_id": 1}
        ).to_list(5000)

        ids_from_students = {s["id"] for s in cancelled_students}
        ids_from_enrollments = {e["student_id"] for e in cancelled_enrollments}
        all_ids = ids_from_students | ids_from_enrollments

        if not all_ids:
            return {
                "message": "Nenhum aluno cancelado encontrado para limpar.",
                "totals": {"students": 0, "enrollments": 0, "attendance": 0, "grades": 0}
            }

        t_att = t_gr = t_en = t_st = 0
        affected = []

        for sid in sorted(all_ids):
            student = await db.students.find_one({"id": sid}, {"_id": 0, "id": 1, "full_name": 1, "status": 1})
            name = student.get("full_name", "???") if student else "???"

            enrollments_list = await db.enrollments.find(
                {"student_id": sid, "status": "cancelled"},
                {"_id": 0, "class_id": 1}
            ).to_list(50)
            class_ids = list(set(e.get("class_id") for e in enrollments_list if e.get("class_id")))

            att_count = 0
            grade_count = 0
            if class_ids:
                att_count = await db.attendance.count_documents(
                    {"class_id": {"$in": class_ids}, "records.student_id": sid}
                )
                grade_count = await db.grades.count_documents(
                    {"student_id": sid, "class_id": {"$in": class_ids}}
                )

            entry = {
                "name": name,
                "enrollments": len(enrollments_list),
                "attendance": att_count,
                "grades": grade_count
            }

            if not dry_run:
                if class_ids:
                    r = await db.attendance.update_many(
                        {"class_id": {"$in": class_ids}},
                        {"$pull": {"records": {"student_id": sid}}}
                    )
                    t_att += r.modified_count
                    r = await db.grades.delete_many(
                        {"student_id": sid, "class_id": {"$in": class_ids}}
                    )
                    t_gr += r.deleted_count
                r = await db.enrollments.delete_many(
                    {"student_id": sid, "status": "cancelled"}
                )
                t_en += r.deleted_count
                if student and student.get("status") in ["cancelled", "cancelado"]:
                    await db.students.update_one(
                        {"id": sid},
                        {"$set": {"status": "inactive", "school_id": "", "class_id": ""}}
                    )
                    t_st += 1
            else:
                t_att += att_count
                t_gr += grade_count
                t_en += len(enrollments_list)
                if student and student.get("status") in ["cancelled", "cancelado"]:
                    t_st += 1

            affected.append(entry)

        if not dry_run:
            await audit_service.log(
                action='delete',
                collection='system',
                user=current_user,
                request=request,
                description=f"Limpeza de matrículas canceladas: {t_st} alunos, {t_en} matrículas, {t_att} frequências, {t_gr} notas",
                extra_data={"students": t_st, "enrollments": t_en, "attendance": t_att, "grades": t_gr}
            )

        return {
            "mode": "dry_run" if dry_run else "executed",
            "message": f"{'Prévia' if dry_run else 'Limpeza concluída'}: {t_st} alunos, {t_en} matrículas, {t_att} frequências, {t_gr} notas",
            "totals": {"students": t_st, "enrollments": t_en, "attendance": t_att, "grades": t_gr},
            "affected": affected
        }


    return router
