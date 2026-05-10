"""
Router para endpoints administrativos.
Extraído de server.py durante a refatoração modular.
"""

import logging
from fastapi import APIRouter, HTTPException, status, Request
import unicodedata

from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin"])


def setup_router(db, active_sessions=None, connection_manager=None, get_db_for_user=None, **kwargs):
    """Configura o router com dependências."""

    @router.post("/admin/migrate-uppercase")
    async def migrate_to_uppercase(request: Request):
        """Converte todos os campos de texto para CAIXA ALTA no banco de dados."""
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['super_admin']
        )(request)

        COLLECTIONS_CONFIG = {
            'students': [
                'full_name', 'father_name', 'mother_name', 'guardian_name',
                'address', 'neighborhood', 'city', 'state', 'birthplace_city', 'birthplace_state',
                'father_workplace', 'mother_workplace', 'guardian_workplace',
                'health_observations', 'special_needs_description', 'allergy_description',
                'previous_school', 'transfer_reason'
            ],
            'staff': [
                'full_name', 'address', 'neighborhood', 'city', 'state',
                'birthplace_city', 'birthplace_state', 'marital_status_spouse_name',
                'education_institution', 'education_course', 'specialization_area',
                'bank_name', 'bank_branch'
            ],
            'schools': [
                'name', 'address', 'neighborhood', 'city', 'state',
                'principal_name', 'secretary_name', 'coordinator_name',
                'school_characteristic', 'authorization_recognition'
            ],
            'classes': ['name', 'room'],
            'courses': ['name', 'description'],
            'users': ['full_name'],
            'enrollments': ['student_name', 'class_name', 'school_name'],
            'learning_objects': ['content', 'observations', 'methodology', 'resources']
        }

        results = {}
        total_updated = 0

        for collection_name, fields in COLLECTIONS_CONFIG.items():
            collection = db[collection_name]
            total = await collection.count_documents({})
            updated_count = 0

            if total > 0:
                cursor = collection.find({}, {"_id": 1} | {f: 1 for f in fields})
                async for doc in cursor:
                    update_data = {}
                    for field in fields:
                        if field in doc and doc[field] and isinstance(doc[field], str):
                            upper_value = doc[field].upper()
                            if doc[field] != upper_value:
                                update_data[field] = upper_value
                    if update_data:
                        await collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": update_data}
                        )
                        updated_count += 1

            results[collection_name] = {"total": total, "updated": updated_count}
            total_updated += updated_count

        return {
            "success": True,
            "message": f"Migração concluída! {total_updated} documentos atualizados.",
            "details": results
        }

    @router.get("/admin/online-users")
    async def get_online_users(request: Request):
        """Retorna lista de usuários online (Super Administrador + Administração)"""
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-online-users-button', ['admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        online = active_sessions.get_online(threshold_minutes=5) if active_sessions else {}

        if not online:
            return []

        all_school_ids = set()
        for uid, data in online.items():
            u = data["user_data"]
            for sid in (u.get('school_ids') or []):
                all_school_ids.add(sid)
            for link in (u.get('school_links') or []):
                all_school_ids.add(link.get('school_id', ''))

        schools_map = {}
        if all_school_ids:
            schools = await current_db.schools.find(
                {"id": {"$in": list(all_school_ids)}},
                {"_id": 0, "id": 1, "name": 1}
            ).to_list(100)
            schools_map = {s['id']: s['name'] for s in schools}

        result = []
        for uid, data in online.items():
            u = data["user_data"]
            school_names = []
            for sid in (u.get('school_ids') or []):
                if sid in schools_map:
                    school_names.append(schools_map[sid])
            for link in (u.get('school_links') or []):
                sid = link.get('school_id', '')
                if sid in schools_map and schools_map[sid] not in school_names:
                    school_names.append(schools_map[sid])

            ws_connections = len(connection_manager.active_connections.get(uid, [])) if connection_manager else 0

            result.append({
                "id": u.get('id', uid),
                "full_name": u.get('full_name', 'N/A'),
                "email": u.get('email', ''),
                "role": u.get('role', ''),
                "avatar_url": u.get('avatar_url'),
                "schools": school_names,
                "connections": max(ws_connections, 1),
                "last_activity": data["last_activity"].isoformat()
            })

        result.sort(key=lambda x: unicodedata.normalize('NFD', x['full_name']).encode('ascii', 'ignore').decode('ascii'))
        return result

    @router.post("/admin/sessions/revoke/{user_id}")
    async def force_logout_user(user_id: str, request: Request):
        """
        Força logout remoto: revoga todos os access/refresh tokens de um usuário.
        Apenas super_admin pode invocar — útil quando aluno/professor esquece
        sessão aberta em PC compartilhado e secretaria precisa encerrar
        sem saber a senha.
        """
        from auth_utils import token_blacklist
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-online-users-button', ['admin']
        )(request)

        # Carrega dados do alvo para audit (com escopo correto se multi-tenant)
        current_db = get_db_for_user(current_user) if get_db_for_user else db
        target = await current_db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1})
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

        # Não permite super_admin se desconectar via essa rota (use logout normal)
        if target['id'] == current_user['id']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use /api/auth/logout para encerrar sua própria sessão"
            )

        # Revoga todos os tokens (access + refresh via revoke_all_before)
        await token_blacklist.revoke_all_user_tokens(
            user_id=user_id,
            reason=f'admin_force_logout_by_{current_user["id"]}'
        )

        # Remove do tracker de sessões ativas (deixa de aparecer em /online-users)
        if active_sessions:
            active_sessions.remove(user_id)

        # Audit log
        try:
            from services.audit_service import audit_service
            await audit_service.log(
                action='force_logout',
                collection='users',
                user=current_user,
                request=request,
                document_id=user_id,
                description=f"Logout remoto forçado: {target.get('full_name')} ({target.get('email')}) - {target.get('role')}"
            )
        except Exception as e:
            logger.error(f"Falha ao registrar audit de force_logout: {e}")

        # Notifica via WebSocket (se conectado) para que o frontend trate o logout em tempo real
        if connection_manager:
            try:
                await connection_manager.send_message(user_id, {
                    "type": "force_logout",
                    "reason": "admin_force_logout",
                    "message": "Sua sessão foi encerrada pelo administrador"
                })
            except Exception as e:
                logger.error(f"Falha ao notificar via WS: {e}")

        return {
            "message": "Sessões revogadas com sucesso",
            "user_id": user_id,
            "user_name": target.get('full_name'),
            "user_email": target.get('email'),
        }

    @router.post("/admin/migrate-payroll-hours")
    async def migrate_payroll_hours(request: Request):
        """
        Recalcula expected_hours e worked_hours de todos os payroll_items existentes.
        Fórmula antiga: carga_horaria_semanal * 4.33
        Fórmula nova: carga_horaria_semanal * 5
        """
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['super_admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        items_cursor = current_db.payroll_items.find({}, {"_id": 1, "employee_id": 1, "expected_hours": 1, "worked_hours": 1})
        updated_count = 0
        skipped_count = 0
        total_count = 0

        async for item in items_cursor:
            total_count += 1
            emp_id = item.get('employee_id')
            if not emp_id:
                skipped_count += 1
                continue

            staff = await current_db.staff.find_one(
                {"id": emp_id}, {"_id": 0, "carga_horaria_semanal": 1, "nome": 1}
            )
            if not staff:
                skipped_count += 1
                continue

            ch_semanal = staff.get('carga_horaria_semanal') or 0
            new_expected = round(ch_semanal * 5, 1)
            old_expected = item.get('expected_hours', 0) or 0
            old_worked = item.get('worked_hours', 0) or 0

            if old_expected == new_expected:
                skipped_count += 1
                continue

            update_fields = {"expected_hours": new_expected}
            if old_worked == old_expected:
                update_fields["worked_hours"] = new_expected

            await current_db.payroll_items.update_one(
                {"_id": item["_id"]},
                {"$set": update_fields}
            )
            updated_count += 1

        return {
            "success": True,
            "message": f"Migração de horas concluída! {updated_count} itens atualizados de {total_count} total.",
            "details": {
                "total": total_count,
                "updated": updated_count,
                "skipped": skipped_count
            }
        }

    @router.post("/admin/migrate-staff-ch-to-lotacao")
    async def migrate_staff_ch_to_lotacao(request: Request):
        """
        Migra staff.carga_horaria_semanal → school_assignments.carga_horaria.
        Para cada lotação ativa sem carga_horaria definida, copia a CH global do servidor.
        Para casos de múltiplas lotações (ex.: professor em 2 escolas), REPETE o valor em todas
        (comportamento alinhado com a regra de negócio: as duas escolas assumem a mesma CH inicial
        e podem ser ajustadas individualmente depois).

        Idempotente: lotações que já têm carga_horaria > 0 definida não são sobrescritas.
        """
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['super_admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        total = 0
        updated = 0
        skipped_had_ch = 0
        skipped_no_source = 0

        async for lot in current_db.school_assignments.find({}, {"_id": 1, "staff_id": 1, "carga_horaria": 1}):
            total += 1
            if lot.get('carga_horaria') not in (None, 0, ''):
                skipped_had_ch += 1
                continue
            staff = await current_db.staff.find_one(
                {"id": lot.get('staff_id')}, {"_id": 0, "carga_horaria_semanal": 1}
            )
            ch = (staff or {}).get('carga_horaria_semanal')
            if not ch:
                skipped_no_source += 1
                continue
            await current_db.school_assignments.update_one(
                {"_id": lot["_id"]},
                {"$set": {"carga_horaria": int(ch)}}
            )
            updated += 1

        return {
            "success": True,
            "message": f"{updated} lotações receberam a CH do servidor (de {total}).",
            "details": {
                "total_lotacoes": total,
                "updated": updated,
                "skipped_ch_already_set": skipped_had_ch,
                "skipped_staff_without_ch": skipped_no_source,
            }
        }

    @router.post("/admin/cleanup-anexa-payroll")
    async def cleanup_anexa_payroll(request: Request):
        """
        Remove itens da folha de pagamento onde o servidor possui lotação 'anexa' naquela escola.
        Busca por combinação employee_id + school_id, não depende de assignment_id.
        """
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['super_admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        # Buscar todas as lotações "anexa" ativas: mapear (staff_id, school_id)
        anexa_pairs = set()
        async for a in current_db.school_assignments.find(
            {"tipo_lotacao": "anexa", "status": "ativo"},
            {"_id": 0, "staff_id": 1, "school_id": 1}
        ):
            anexa_pairs.add((a['staff_id'], a['school_id']))

        if not anexa_pairs:
            return {
                "success": True,
                "message": "Nenhuma lotação do tipo 'anexa' encontrada. Nada a limpar.",
                "details": {"total": 0, "deleted": 0, "skipped": 0}
            }

        # Buscar payroll_items que correspondem a essas combinações
        items_to_delete_ids = []
        async for item in current_db.payroll_items.find(
            {}, {"_id": 0, "id": 1, "employee_id": 1, "school_id": 1}
        ):
            if (item.get('employee_id'), item.get('school_id')) in anexa_pairs:
                items_to_delete_ids.append(item['id'])

        deleted_count = 0
        if items_to_delete_ids:
            # Remover ocorrências vinculadas
            await current_db.payroll_occurrences.delete_many(
                {"payroll_item_id": {"$in": items_to_delete_ids}}
            )
            # Remover os itens
            result = await current_db.payroll_items.delete_many(
                {"id": {"$in": items_to_delete_ids}}
            )
            deleted_count = result.deleted_count

        return {
            "success": True,
            "message": f"Limpeza concluída! {deleted_count} itens removidos de {len(anexa_pairs)} lotações 'anexa'.",
            "details": {
                "total": len(anexa_pairs),
                "deleted": deleted_count,
                "skipped": 0
            }
        }

    @router.post("/admin/migrate-history-dates")
    async def migrate_history_dates(request: Request):
        """
        Define data de matrícula como 15/01/2026 para todos os registros.
        Atualiza: student_history, students e enrollments.
        """
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['super_admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        target_date = "2026-01-15"
        target_date_iso = "2026-01-15T12:00:00+00:00"

        # 1. Histórico: todas as matrículas
        r1 = await current_db.student_history.update_many(
            {"action_type": "matricula", "action_date": {"$ne": target_date_iso}},
            {"$set": {"action_date": target_date_iso}}
        )

        # 2. Alunos ativos: enrollment_date diferente de 15/01/2026
        r2 = await current_db.students.update_many(
            {"status": "active", "enrollment_date": {"$ne": target_date}},
            {"$set": {"enrollment_date": target_date}}
        )

        # 3. Matrículas ativas: enrollment_date diferente de 15/01/2026
        r3 = await current_db.enrollments.update_many(
            {"status": "active", "enrollment_date": {"$ne": target_date}},
            {"$set": {"enrollment_date": target_date}}
        )

        return {
            "message": f"Migração concluída: histórico={r1.modified_count}, alunos={r2.modified_count}, matrículas={r3.modified_count} atualizados para 15/01/2026",
            "updated_history": r1.modified_count,
            "updated_students": r2.modified_count,
            "updated_enrollments": r3.modified_count
        }

    @router.get("/admin/diagnose-class-courses/{class_id}")
    async def diagnose_class_courses(class_id: str, request: Request):
        """Diagnóstico de componentes curriculares de uma turma.

        Identifica:
          - Cursos cadastrados em `class.course_ids` agrupados por nome
            (detecta duplicidade real por mesmo nome);
          - Quantidade de notas (`grades`) e registros de presença
            (`attendance`) associados a cada `course_id`;
          - Cursos "fantasma" (sem qualquer lançamento e/ou sem aluno
            ativo registrando ocorrência);
          - "Notas órfãs" — `grades` referenciando `course_id` que NÃO
            está em `class.course_ids` (cursos desvinculados após uso).

        NÃO faz alterações. NÃO sugere ações destrutivas.
        Saneamento é decisão administrativa supervisionada (P1 — endpoint
        de merge separado).
        """
        current_user = await AuthMiddleware.require_permission(
            db, 'nav-admin-tools-button', ['admin']
        )(request)
        current_db = get_db_for_user(current_user) if get_db_for_user else db

        cls = await current_db.classes.find_one(
            {"id": class_id},
            {"_id": 0, "id": 1, "name": 1, "course_ids": 1,
             "school_id": 1, "academic_year": 1},
        )
        if not cls:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Turma não encontrada")

        course_ids_in_class: list[str] = list(cls.get("course_ids") or [])

        # Carrega cursos referenciados na turma
        courses_in_class: dict[str, dict] = {}
        if course_ids_in_class:
            async for c in current_db.courses.find(
                {"id": {"$in": course_ids_in_class}},
                {"_id": 0, "id": 1, "name": 1, "active": 1,
                 "atendimento_programa": 1, "optativo": 1, "deleted_at": 1},
            ):
                courses_in_class[c["id"]] = c

        # Conta notas e presenças por course_id da turma
        async def _grades_count(course_id: str) -> tuple[int, int]:
            total = await current_db.grades.count_documents(
                {"class_id": class_id, "course_id": course_id}
            )
            students = await current_db.grades.distinct(
                "student_id", {"class_id": class_id, "course_id": course_id}
            )
            return total, len(students)

        async def _attendance_count(course_id: str) -> int:
            return await current_db.attendance.count_documents(
                {"class_id": class_id, "course_id": course_id}
            )

        # Builda info detalhada por curso
        per_course: list[dict] = []
        # Inclui também cursos referenciados na turma porém sem documento
        # `courses` correspondente (curso deletado/inexistente)
        all_referenced_ids = set(course_ids_in_class)
        for cid in all_referenced_ids:
            doc = courses_in_class.get(cid)
            grades_count, students_count = await _grades_count(cid)
            att_count = await _attendance_count(cid)
            is_active = bool(doc.get("active", True)) if doc else False
            is_deleted = bool(doc and doc.get("deleted_at"))
            suspected_ghost = (
                grades_count == 0
                and att_count == 0
                and (not doc or is_deleted or not is_active)
            )
            per_course.append({
                "course_id": cid,
                "course_name": (doc or {}).get("name"),
                "exists": bool(doc),
                "active": is_active,
                "deleted_at": (doc or {}).get("deleted_at"),
                "atendimento_programa": (doc or {}).get("atendimento_programa") or "regular",
                "optativo": bool((doc or {}).get("optativo", False)),
                "in_class_course_ids": True,
                "grades_count": grades_count,
                "attendance_count": att_count,
                "students_with_records": students_count,
                "suspected_ghost": suspected_ghost,
            })

        # Agrupa por nome (case/space-insensitive) — só lista grupos com >1
        by_name: dict[str, list[dict]] = {}
        for entry in per_course:
            n = (entry.get("course_name") or "").strip().casefold()
            n = " ".join(n.split())
            if not n:
                n = f"__sem_nome__{entry['course_id']}"
            by_name.setdefault(n, []).append(entry)

        duplicates_by_name: list[dict] = []
        for norm, group in by_name.items():
            if len(group) <= 1:
                continue
            duplicates_by_name.append({
                "course_name": group[0].get("course_name") or "(sem nome)",
                "courses": group,
            })

        # Notas órfãs: grades com course_id que não está mais em class.course_ids
        orphan_pipeline = [
            {"$match": {"class_id": class_id,
                        "course_id": {"$nin": course_ids_in_class or [""]}}},
            {"$group": {
                "_id": "$course_id",
                "grades_count": {"$sum": 1},
                "students": {"$addToSet": "$student_id"},
                "any_course_name": {"$first": "$course_name"},
            }},
            {"$project": {
                "_id": 0,
                "course_id": "$_id",
                "grades_count": 1,
                "students_with_records": {"$size": "$students"},
                "course_name_from_grade": "$any_course_name",
            }},
        ]
        orphan_grades: list[dict] = []
        async for o in current_db.grades.aggregate(orphan_pipeline):
            # Resolve nome do curso a partir do documento atual (se ainda existe)
            cdoc = await current_db.courses.find_one(
                {"id": o["course_id"]},
                {"_id": 0, "name": 1, "active": 1, "deleted_at": 1},
            )
            o["course_exists"] = bool(cdoc)
            o["course_active"] = bool(cdoc and cdoc.get("active", True))
            o["course_deleted_at"] = (cdoc or {}).get("deleted_at")
            o["course_name_resolved"] = (cdoc or {}).get("name")
            orphan_grades.append(o)

        return {
            "class_id": cls["id"],
            "class_name": cls.get("name"),
            "school_id": cls.get("school_id"),
            "academic_year": cls.get("academic_year"),
            "course_ids_in_class": course_ids_in_class,
            "courses": per_course,
            "duplicates_by_name": duplicates_by_name,
            "orphan_grades": orphan_grades,
            "summary": {
                "total_courses_in_class": len(course_ids_in_class),
                "duplicate_groups": len(duplicates_by_name),
                "ghost_courses": sum(1 for c in per_course if c["suspected_ghost"]),
                "orphan_course_ids": len(orphan_grades),
            },
        }

    return router
