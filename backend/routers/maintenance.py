"""
Router para Manutenção.
Extraído automaticamente de server.py.
"""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import logging

from models import *
from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter

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
                issues.append("Estudante não encontrado")
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
        Remove dados órfãos no escopo legado.

        P0 Global: ``teacher_assignments`` não são mais removidos fisicamente por
        esta rotina. Vínculos docentes precisam ser preservados até a reconciliação
        global entre as fontes de verdade concorrentes.
        """
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        # Primeiro, obtém lista de órfãos
        orphan_check = await check_orphan_data(request)

        if dry_run:
            return {
                'mode': 'dry_run',
                'message': 'Nenhuma alteração foi feita. Use dry_run=false para executar.',
                'would_delete': orphan_check['summary'],
                'p0_protection': 'teacher_assignments nunca serão hard-deleted por esta rotina'
            }

        deleted = {
            'enrollments': 0,
            'school_assignments': 0,
            'teacher_assignments': 0,
            'teacher_assignments_protected': 0,
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
                    deleted['teacher_assignments_protected'] += 1
            except Exception as e:
                logger.error(f"Falha ao remover registro órfão {orphan.get('type')}/{orphan.get('id')}: {e}")

        deleted['total'] = deleted['enrollments'] + deleted['school_assignments']

        # Registra auditoria da limpeza
        await audit_service.log(
            action='delete',
            collection='system',
            user=current_user,
            request=request,
            description=(
                f"Executou limpeza de dados órfãos: {deleted['total']} registros removidos; "
                f"{deleted['teacher_assignments_protected']} vínculos docentes preservados pelo P0"
            ),
            extra_data=deleted
        )

        return {
            'mode': 'executed',
            'deleted': deleted
        }


    @router.get("/maintenance/duplicate-courses")
    async def check_duplicate_courses(request: Request):
        """Verifica componentes duplicados somente dentro do tenant autorizado."""
        current_user = await AuthMiddleware.require_roles(['admin'])(request)

        # P0 Global: nunca comparar/mesclar componentes atravessando mantenedoras.
        course_query = apply_tenant_filter({}, current_user, request)
        courses = await db.courses.find(course_query, {"_id": 0}).to_list(5000)

        # Agrupar por tenant + nome + nível de ensino.
        groups = {}
        for course in courses:
            key = (
                course.get('mantenedora_id'),
                course.get('name', ''),
                course.get('nivel_ensino', '')
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(course)

        duplicates = []
        for key, courses_list in groups.items():
            if len(courses_list) > 1:
                duplicates.append({
                    'mantenedora_id': key[0],
                    'name': key[1],
                    'nivel_ensino': key[2],
                    'count': len(courses_list),
                    'courses': courses_list
                })

        return {
            'mode': 'READ_ONLY',
            'total_duplicates': len(duplicates),
            'duplicates': duplicates
        }


    @router.post("/maintenance/consolidate-courses")
    async def consolidate_duplicate_courses(request: Request, dry_run: bool = True):
        """Prévia de duplicados; execução destrutiva congelada pelo P0 Global.

        A implementação anterior apagava ``courses.id`` sem remapear as referências
        em vínculos docentes e dados pedagógicos. Até existir motor transacional de
        merge com manifesto, rollback e pós-check, apenas ``dry_run`` é permitido.
        """
        await AuthMiddleware.require_roles(['admin'])(request)
        dup_check = await check_duplicate_courses(request)

        if dry_run:
            return {
                'mode': 'dry_run',
                'message': (
                    'P0 Global ativo: prévia permitida, consolidação destrutiva desabilitada. '
                    'Nenhuma alteração foi feita.'
                ),
                'would_consolidate': dup_check
            }

        raise HTTPException(
            status_code=409,
            detail={
                'code': 'COURSE_CONSOLIDATION_DISABLED_P0',
                'message': (
                    'Consolidação física de componentes está bloqueada pelo P0 Global. '
                    'É obrigatório remapear todas as referências com dry-run, manifesto, '
                    'rollback e validação pós-migração antes de reabilitar esta operação.'
                ),
            },
        )


    @router.post("/maintenance/cleanup-cancelled-enrollments")
    async def cleanup_cancelled_enrollments(request: Request, dry_run: bool = True):
        """
        Limpeza retroativa de matrículas canceladas.
        Remove frequências, notas e matrículas de alunos com status 'cancelled'.
        Seta o aluno como 'inactive' sem escola/turma.
        Use dry_run=false para executar a limpeza real.
        """
        current_user = await AuthMiddleware.require_roles(['super_admin'])(request)

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
                "message": "Nenhum estudante cancelado encontrado para limpar.",
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


    @router.get("/maintenance/schedules-write-read-diagnostic")
    async def schedules_write_read_diagnostic(
        request: Request,
        academic_year: int = None,
        examples_limit: int = 20,
    ):
        """[Fev/2026] Diagnóstico read-only do anti-pattern WRITE!=READ
        entre `class_schedules` (legacy, onde a UI grava) e
        `teacher_class_assignments` (novo, onde o painel de Integridade lê).

        Sem mutações. Pré-condição para qualquer migração legacy→novo.

        Buckets retornados:
          - both:        em AMBAS as coleções (potencial duplicação)
          - legacy_only: só em `class_schedules` (UI ainda no antigo)
          - new_only:    só em `teacher_class_assignments` (raro hoje)
          - without_any: SEM grade em lugar nenhum (problema real)
        """
        await AuthMiddleware.require_roles(['super_admin'])(request)

        year = academic_year if academic_year is not None else datetime.now(timezone.utc).year

        classes_active = await db.classes.find(
            {"academic_year": year},
            {"_id": 0, "id": 1, "name": 1, "school_id": 1, "status": 1},
        ).to_list(5000)
        classes_active = [
            c for c in classes_active if (c.get("status") or "active") == "active"
        ]
        active_ids = {c["id"] for c in classes_active}

        try:
            legacy_ids_raw = await db.class_schedules.distinct("class_id", {})
        except Exception:
            legacy_ids_raw = []
        legacy_ids = {cid for cid in legacy_ids_raw if cid in active_ids}

        try:
            new_ids_raw = await db.teacher_class_assignments.distinct(
                "class_id", {"deleted": {"$ne": True}}
            )
        except Exception:
            new_ids_raw = []
        new_ids = {cid for cid in new_ids_raw if cid in active_ids}

        both = legacy_ids & new_ids
        legacy_only = legacy_ids - new_ids
        new_only = new_ids - legacy_ids
        without_any = active_ids - legacy_ids - new_ids

        # Enriquece amostra com nome da escola
        examples = []
        school_ids_needed = {
            c.get("school_id") for c in classes_active
            if c["id"] in without_any and c.get("school_id")
        }
        school_name_by_id = {}
        if school_ids_needed:
            async for s in db.schools.find(
                {"id": {"$in": list(school_ids_needed)}},
                {"_id": 0, "id": 1, "name": 1},
            ):
                school_name_by_id[s["id"]] = s.get("name")

        for c in classes_active:
            if c["id"] in without_any:
                examples.append({
                    "class_id": c["id"],
                    "class_name": c.get("name"),
                    "school_id": c.get("school_id"),
                    "school_name": school_name_by_id.get(c.get("school_id")),
                })
                if len(examples) >= examples_limit:
                    break

        return {
            "academic_year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_active_classes": len(active_ids),
            "with_class_schedules": len(legacy_ids),
            "with_teacher_assignments": len(new_ids),
            "both": len(both),
            "legacy_only": len(legacy_only),
            "new_only": len(new_only),
            "without_any_schedule": len(without_any),
            "examples_without_any_schedule": examples,
            "interpretation": {
                "anti_pattern_detected": len(legacy_only) > 0 and len(new_ids) == 0,
                "migration_safe": len(both) == 0,
                "real_missing_schedule_count": len(without_any),
                "notes": (
                    "Se `both > 0`: investigar duplicação antes de migrar."
                    " Se `legacy_only` é predominante e `new_ids` é vazio,"
                    " confirma o anti-pattern WRITE!=READ; o painel de"
                    " Integridade da Grade já considera ambas as coleções"
                    " (hotfix B). Migração definitiva continua como sprint"
                    " dedicado."
                ),
            },
        }


    return router
