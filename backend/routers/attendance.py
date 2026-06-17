"""
Router de Frequência - SIGESC
PATCH 4.x: Rotas de frequência extraídas do server.py

Endpoints para gestão de frequência incluindo:
- Lançamento por turma/data
- Configurações de ano letivo
- Relatórios por aluno e turma
- Alertas de infrequência
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid
import logging

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, resolve_tenant_id_for_create, get_mantenedora_scope
from utils.dependency_validator import validate_dependency_link
from utils.academic_event_lens import resolve_student_ownership, record_lock_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attendance", tags=["Frequência"])

# Roles autorizadas a editar registros migrados de frequência (Feb 2026)
ROLES_CAN_EDIT_MIGRATED_ATTENDANCE = ['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario']


def _block_if_changing_migrated_attendance(existing_records, new_records, user):
    """Para usuários sem role administrativa, mantém intactos os registros que
    foram migrados de outra turma (preserva status original).

    Para usuários autorizados (secretario/gerente/super_admin/admin), preserva
    a flag `migrated_from_class_id` ao atualizar o status — a edição é permitida
    mas o registro continua marcado como migrado para histórico/auditoria.
    """
    existing_by_sid = {r['student_id']: r for r in (existing_records or [])}
    privileged = user.get('role') in ROLES_CAN_EDIT_MIGRATED_ATTENDANCE
    blocked = []
    out = []
    for nr in new_records:
        sid = nr.get('student_id')
        old = existing_by_sid.get(sid)
        if old and old.get('migrated_from_class_id'):
            if privileged:
                # Atualiza preservando metadados de migração
                merged = dict(old)
                merged.update(nr)
                merged['migrated_from_class_id'] = old['migrated_from_class_id']
                if old.get('migrated_at'):
                    merged['migrated_at'] = old['migrated_at']
                out.append(merged)
            else:
                out.append(old)  # status preservado
                blocked.append(sid)
        else:
            out.append(nr)
    return out, blocked


async def save_attendance_canonical(current_db, current_user, request, attendance, audit_service):
    """Motor canônico de gravação de frequência.

    ÚNICO ponto de escrita de frequência no sistema. Usado tanto pelo endpoint
    HTTP `POST /api/attendance` quanto pelo sincronizador offline (`/api/sync/push`),
    garantindo que ambos percorram EXATAMENTE a mesma lógica: upsert por chave
    natural (turma+data+componente+aula), optimistic locking, Academic Event Lock,
    validação de dependências e auditoria. Idempotente por natureza — reenviar o
    mesmo registro NÃO cria duplicata.
    """
    # Detectar se é anos finais para usar aula_numero
    turma = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0})
    education_level = turma.get('education_level', '') if turma else ''
    is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']

    query = {"class_id": attendance.class_id, "date": attendance.date}
    if attendance.course_id:
        query["course_id"] = attendance.course_id
    if attendance.period != "regular":
        query["period"] = attendance.period

    # Para anos finais: cada aula é um registro separado (usa aula_numero na query)
    if is_anos_finais and attendance.aula_numero is not None:
        query["aula_numero"] = attendance.aula_numero

    existing = await current_db.attendance.find_one(query)

    # Fase 2 — anti-spoof: valida coerência de dependency_id em CADA record
    for r in attendance.records:
        if r.dependency_id:
            await validate_dependency_link(
                db=current_db,
                dependency_id=r.dependency_id,
                student_id=r.student_id,
                class_id=attendance.class_id,
                course_id=attendance.course_id,
                tenant_id=get_mantenedora_scope(current_user, request),
            )

    # Fase 3 — Academic Event Lock por aluno (a frequência tem `date` própria)
    tenant_for_lens = get_mantenedora_scope(current_user, request)
    for r in attendance.records:
        ownership = await resolve_student_ownership(
            current_db,
            student_id=r.student_id,
            class_id=attendance.class_id,
            course_id=attendance.course_id,
            target_date=attendance.date,  # frequência usa data da aula
            mantenedora_id=tenant_for_lens,
        )
        if not ownership["editable"]:
            await record_lock_audit(
                current_db,
                event_id=ownership.get("governing_event_id"),
                action="attendance_create_blocked",
                user_id=current_user.get("id"),
                role=current_user.get("role"),
                student_id=r.student_id,
                class_id=attendance.class_id,
                target_date=attendance.date,
                target_resource="attendance",
                reason_code=ownership["blocked_reason"],
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACADEMIC_EVENT_LOCK",
                    "reason_code": ownership["blocked_reason"],
                    "event_id": ownership.get("governing_event_id"),
                    "student_id": r.student_id,
                    "effective_date": ownership.get("governing_effective_date"),
                    "message": "Frequência bloqueada por evento acadêmico para este aluno.",
                },
            )

    records_data = [
        {
            "student_id": r.student_id,
            "status": r.status,
            **({"dependency_id": r.dependency_id} if r.dependency_id else {}),
        }
        for r in attendance.records
    ]

    if existing:
        # ============= OPTIMISTIC LOCKING (Fase 1 — Mai/2026) =============
        current_version = existing.get("version") or 1  # docs legados sem version contam como v1
        ev = attendance.expected_version
        change_kind = "update"
        if ev is not None and ev != current_version:
            if not attendance.force_overwrite:
                last_modifier = None
                last_modified_at = existing.get("updated_at") or existing.get("created_at")
                last_uid = existing.get("updated_by") or existing.get("created_by")
                if last_uid:
                    u = await current_db.users.find_one(
                        {"id": last_uid}, {"_id": 0, "name": 1, "full_name": 1, "email": 1, "role": 1}
                    )
                    if u:
                        last_modifier = {
                            "id": last_uid,
                            "name": u.get("full_name") or u.get("name"),
                            "email": u.get("email"),
                            "role": u.get("role"),
                        }
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ATTENDANCE_VERSION_CONFLICT",
                        "message": (
                            "Esta frequência foi alterada por outro usuário "
                            "desde que você carregou. Recarregue OU reenvie "
                            "com force_overwrite=true e change_note='motivo'."
                        ),
                        "expected_version": ev,
                        "current_version": current_version,
                        "last_modified_by": last_modifier,
                        "last_modified_at": last_modified_at,
                        "attendance_id": existing.get("id"),
                    },
                )
            if not (attendance.change_note and attendance.change_note.strip()):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "OVERWRITE_REQUIRES_NOTE",
                        "message": "Sobrescrita após conflito requer change_note (motivo) obrigatório.",
                    },
                )
            change_kind = "overwrite_after_conflict"
        # ===================================================================

        records_data, blocked_sids = _block_if_changing_migrated_attendance(
            existing.get('records') or [], records_data, current_user
        )

        new_version = current_version + 1
        update_data = {
            "records": records_data,
            "observations": attendance.observations,
            "number_of_classes": 1 if is_anos_finais else attendance.number_of_classes,
            "updated_by": current_user['id'],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": new_version,
        }
        if is_anos_finais and attendance.aula_numero is not None:
            update_data["aula_numero"] = attendance.aula_numero

        await current_db.attendance.update_one(
            {"id": existing['id']},
            {"$set": update_data}
        )

        from services.attendance_audit_diary import diff_records, build_diary_audit_extra
        class_info = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
        per_student = diff_records(existing.get('records') or [], records_data)
        updated_doc = await current_db.attendance.find_one({"id": existing['id']}, {"_id": 0})
        extra = await build_diary_audit_extra(
            db=current_db,
            attendance_doc=updated_doc,
            class_info=class_info,
            per_student_changes=per_student,
            change_kind=change_kind,
            expected_version=ev,
            final_version=new_version,
            change_note=attendance.change_note if change_kind == "overwrite_after_conflict" else None,
        )
        await audit_service.log(
            action='update',
            collection='attendance',
            user=current_user,
            request=request,
            document_id=existing['id'],
            description=(
                f"Atualizou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date} "
                f"({len(per_student)} aluno(s) alterado(s)"
                + (f", SOBRESCRITA pós-conflito" if change_kind == "overwrite_after_conflict" else "")
                + ")"
            ),
            old_value={"records": existing.get('records') or [], "version": current_version},
            new_value={"records": records_data, "version": new_version},
            school_id=class_info.get('school_id') if class_info else None,
            extra_data=extra,
        )

        return updated_doc
    else:
        turma = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0})
        education_level = turma.get('education_level', '') if turma else ''

        attendance_type = 'daily' if education_level in ['fundamental_anos_iniciais', 'eja'] else 'by_course'

        new_attendance = {
            "id": str(uuid.uuid4()),
            "class_id": attendance.class_id,
            "date": attendance.date,
            "course_id": attendance.course_id,
            "period": attendance.period,
            "attendance_type": attendance_type,
            "records": records_data,
            "observations": attendance.observations,
            "number_of_classes": 1 if is_anos_finais else attendance.number_of_classes,
            "academic_year": turma.get('academic_year', datetime.now().year) if turma else datetime.now().year,
            "created_by": current_user['id'],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }

        if is_anos_finais:
            if attendance.aula_numero is not None:
                new_attendance["aula_numero"] = attendance.aula_numero
            else:
                count_query = {"class_id": attendance.class_id, "date": attendance.date}
                if attendance.course_id:
                    count_query["course_id"] = attendance.course_id
                existing_count = await current_db.attendance.count_documents(count_query)
                new_attendance["aula_numero"] = existing_count + 1

        new_attendance['mantenedora_id'] = await resolve_tenant_id_for_create(
            current_db, current_user, request, class_id=attendance.class_id
        )

        await current_db.attendance.insert_one(new_attendance)

        class_info = await current_db.classes.find_one({"id": attendance.class_id}, {"_id": 0, "name": 1, "school_id": 1})
        from services.attendance_audit_diary import build_diary_audit_extra
        extra = await build_diary_audit_extra(
            db=current_db,
            attendance_doc=new_attendance,
            class_info=class_info,
            per_student_changes=[
                {"student_id": r["student_id"], "previous_status": None, "new_status": r.get("status")}
                for r in records_data
            ],
            change_kind="create",
            expected_version=None,
            final_version=1,
        )
        await audit_service.log(
            action='create',
            collection='attendance',
            user=current_user,
            request=request,
            document_id=new_attendance['id'],
            description=f"Lançou frequência da turma {class_info.get('name', 'N/A')} em {attendance.date}",
            school_id=class_info.get('school_id') if class_info else None,
            extra_data=extra,
        )

        return await current_db.attendance.find_one({"id": new_attendance['id']}, {"_id": 0})




class AttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, absent, justified, late - pipe-separated for multi-class: "P|F|P|J"
    dependency_id: Optional[str] = None  # Fase 2: vínculo de dependência (validado server-side)


class AttendanceCreate(BaseModel):
    class_id: str
    date: str
    records: List[AttendanceRecord]
    course_id: Optional[str] = None
    period: str = "regular"
    observations: Optional[str] = None
    number_of_classes: int = 1
    aula_numero: Optional[int] = None  # Para anos finais: identifica a aula (1, 2, 3...)
    # Optimistic locking (Fase 1 Rodada 1 — Mai/2026).
    # Frontend envia a versão que carregou. Se servidor já evoluiu → 409.
    # Para criação (sem doc anterior), expected_version é ignorado.
    expected_version: Optional[int] = None
    # Quando 409 acontece, frontend pode tentar de novo enviando:
    #   force_overwrite=True + change_note='justificativa obrigatória'
    # Audit log marca change_kind='overwrite_after_conflict'.
    force_overwrite: bool = False
    change_note: Optional[str] = None


# ========== Fase 7 (Mai/2026) — Validação Institucional ==========
class ValidateBatchRequest(BaseModel):
    """Validação em lote por turma+datas. Internamente roda N validações
    individuais — UMA por attendance — gerando N audit_logs.

    Justificativa arquitetural (owner): preserva auditoria, reversibilidade
    e legitimidade institucional. Lote não cria 'uma validação única'.
    """
    class_id: str
    dates: List[str]  # YYYY-MM-DD[]


class UnvalidateRequest(BaseModel):
    """Reverte uma validação institucional. Exige rationale ≥ 30 chars.

    Owner: 'Validação NÃO pode virar ação banal'.
    """
    rationale: str


def setup_attendance_router(db, audit_service, sandbox_db=None):
    """Configura o router de frequência com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    @router.get("/settings/{academic_year}")
    async def get_attendance_settings(academic_year: int, request: Request):
        """Obtém configurações de frequência para o ano letivo"""
        await AuthMiddleware.get_current_user(request)
        
        settings = await db.attendance_settings.find_one(
            {"academic_year": academic_year}, 
            {"_id": 0}
        )
        
        if not settings:
            return {
                "academic_year": academic_year,
                "allow_future_dates": False
            }
        
        return settings

    @router.put("/settings/{academic_year}")
    async def update_attendance_settings(academic_year: int, request: Request, allow_future_dates: bool):
        """Atualiza configurações de frequência (apenas Admin/Secretário)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.attendance_settings.find_one({"academic_year": academic_year})
        
        if existing:
            await current_db.attendance_settings.update_one(
                {"academic_year": academic_year},
                {"$set": {
                    "allow_future_dates": allow_future_dates,
                    "updated_by": current_user['id'],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            await current_db.attendance_settings.insert_one({
                "id": str(uuid.uuid4()),
                "academic_year": academic_year,
                "allow_future_dates": allow_future_dates,
                "updated_by": current_user['id'],
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
        
        return await current_db.attendance_settings.find_one({"academic_year": academic_year}, {"_id": 0})

    @router.get("/check-date/{date}")
    async def check_attendance_date(date: str, request: Request):
        """Verifica se uma data é válida para lançamento de frequência"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_future = date > today
        
        year = int(date.split("-")[0])
        settings = await current_db.attendance_settings.find_one({"academic_year": year}, {"_id": 0})
        allow_future = settings.get("allow_future_dates", False) if settings else False
        
        can_use_future = current_user['role'] in ['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario'] and allow_future
        
        # Verifica eventos do calendário
        events = await current_db.calendar_events.find({
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }, {"_id": 0}).to_list(100)
        
        is_school_day = True
        blocking_events = []
        has_sabado_letivo = False
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        
        for event in events:
            et = event.get('event_type', '')
            if et == 'sabado_letivo' or (event.get('is_school_day') and date_obj.weekday() == 5):
                has_sabado_letivo = True
            if not event.get('is_school_day', True):
                blocking_events.append(event)
        
        # Sábado letivo tem prioridade sobre outros eventos de bloqueio
        if has_sabado_letivo:
            is_school_day = True
            blocking_events = []
        elif blocking_events:
            is_school_day = False
        
        is_weekend = date_obj.weekday() in [5, 6]
        is_sabado_letivo = has_sabado_letivo
        
        can_record = is_school_day and (not is_weekend or is_sabado_letivo)
        if is_future and not can_use_future:
            can_record = False
        
        return {
            "date": date,
            "is_school_day": is_school_day,
            "is_weekend": is_weekend,
            "is_sabado_letivo": is_sabado_letivo,
            "is_future": is_future,
            "allow_future_dates": allow_future,
            "can_record": can_record,
            "blocking_events": blocking_events,
            "message": (
                "Data futura não permitida" if is_future and not can_use_future
                else "Sábado Letivo" if is_sabado_letivo
                else "Final de semana" if is_weekend
                else "Dia não letivo" if not is_school_day
                else "Liberado para lançamento"
            )
        }

    @router.get("/by-class/{class_id}/{date}")
    async def get_attendance_by_class(
        class_id: str, 
        date: str, 
        request: Request,
        course_id: Optional[str] = None,
        period: str = "regular"
    ):
        """Obtém frequência de uma turma em uma data"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        education_level = turma.get('education_level', '')
        
        if education_level in ['fundamental_anos_iniciais', 'eja']:
            attendance_type = 'daily'
        else:
            attendance_type = 'by_course'
        
        academic_year = turma.get('academic_year', datetime.now().year)
        
        # Busca alunos matriculados - usando múltiplas fontes para maior robustez
        # Estratégia 1: Busca na coleção enrollments (matrícula formal - ativos)
        enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1, "enrollment_date": 1}
        ).to_list(1000)
        
        enrollment_student_ids = set()
        enrollment_numbers = {}
        enrollment_dates = {}
        for e in enrollments:
            student_id = e.get('student_id')
            enrollment_student_ids.add(student_id)
            if student_id not in enrollment_numbers or e.get('academic_year') == academic_year:
                enrollment_numbers[student_id] = e.get('enrollment_number')
            if e.get('enrollment_date'):
                enrollment_dates[student_id] = e.get('enrollment_date')
        
        # Busca alunos inativos que JÁ ESTIVERAM nesta turma (transferidos, desistentes, etc.)
        # IMPORTANTE: "cancelled" (matrícula cancelada) é EXCLUÍDO de propósito —
        # aluno com matrícula cancelada NÃO deve aparecer em nenhuma lista da turma
        # onde foi cancelada (notas/frequência).
        inactive_enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": {"$in": ["transferred", "dropout", "relocated", "progressed", "reclassified"]}},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1, "status": 1}
        ).to_list(1000)
        
        inactive_student_ids = set()
        inactive_enrollment_status = {}
        for e in inactive_enrollments:
            sid = e.get('student_id')
            if sid not in enrollment_student_ids:
                inactive_student_ids.add(sid)
                if sid not in enrollment_numbers or e.get('academic_year') == academic_year:
                    enrollment_numbers[sid] = e.get('enrollment_number')
                inactive_enrollment_status[sid] = e.get('status')
        
        # Estratégia 2: Busca alunos diretamente com class_id (fallback)
        direct_students = await current_db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1, "enrollment_number": 1}
        ).to_list(1000)
        
        for s in direct_students:
            student_id = s.get('id')
            if student_id not in enrollment_numbers:
                enrollment_numbers[student_id] = s.get('enrollment_number')
        
        direct_student_ids = {s.get('id') for s in direct_students}
        
        # Combina todas as fontes
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids).union(inactive_student_ids))
        
        students = []
        if all_student_ids:
            students = await current_db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "class_id": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)
        
        # Busca ação mais recente (data e tipo) para alunos inativos
        action_info_map = {}
        if inactive_student_ids:
            action_type_map = {
                'transferencia_saida': 'Transferido',
                'remanejamento': 'Remanejado',
                'progressao': 'Progredido',
                'reclassificacao': 'Reclassificado',
                'desistencia': 'Desistente',
                'cancelamento': 'Cancelado'
            }
            history_entries = await current_db.student_history.find(
                {
                    "student_id": {"$in": list(inactive_student_ids)},
                    "class_id": class_id,
                    "action_type": {"$in": list(action_type_map.keys())}
                },
                {"_id": 0, "student_id": 1, "action_type": 1, "action_date": 1}
            ).sort("action_date", -1).to_list(1000)
            
            for h in history_entries:
                sid = h.get('student_id')
                if sid not in action_info_map:
                    action_info_map[sid] = {
                        "action_label": action_type_map.get(h.get('action_type'), ''),
                        "action_date": h.get('action_date', '')
                    }
        
        # Busca frequência existente
        query = {"class_id": class_id, "date": date}
        if course_id:
            query["course_id"] = course_id
        if period != "regular":
            query["period"] = period
        
        # Buscar TODAS as sessões para esta data (anos finais podem ter múltiplas)
        all_sessions = await current_db.attendance.find(query, {"_id": 0}).sort("aula_numero", 1).to_list(100)
        
        # Para compatibilidade: pegar a primeira sessão como "attendance" principal
        attendance = all_sessions[0] if all_sessions else None
        
        records_map = {}
        if attendance and attendance.get('records'):
            records_map = {r['student_id']: r['status'] for r in attendance['records']}
        
        # Montar sessões para anos finais
        sessions = []
        for sess in all_sessions:
            sess_records = {r['student_id']: r['status'] for r in sess.get('records', [])}
            sessions.append({
                "id": sess.get('id'),
                "aula_numero": sess.get('aula_numero', 1),
                "number_of_classes": sess.get('number_of_classes', 1),
                "observations": sess.get('observations'),
                "records": sess_records
            })
        
        result_payload = {
            "class_id": class_id,
            "class_name": turma.get('name'),
            "date": date,
            "attendance_type": attendance_type,
            "course_id": course_id,
            "period": period,
            "attendance_id": attendance.get('id') if attendance else None,
            "observations": attendance.get('observations') if attendance else None,
            "number_of_classes": attendance.get('number_of_classes', 1) if attendance else 1,
            "total_sessions": len(all_sessions),
            "sessions": sessions,
            "students": [
                {
                    "id": s['id'],
                    "full_name": s['full_name'],
                    "enrollment_number": enrollment_numbers.get(s['id']) or s.get('enrollment_number'),
                    "status": records_map.get(s['id'], None),
                    "student_status": s.get('status', 'active'),
                    "current_class_id": s.get('class_id'),
                    "is_transferred_from_class": s.get('class_id') and s.get('class_id') != class_id,
                    "action_label": action_info_map.get(s['id'], {}).get('action_label', ''),
                    "action_date": action_info_map.get(s['id'], {}).get('action_date', ''),
                    "enrollment_date": enrollment_dates.get(s['id'], s.get('enrollment_date', '')),
                    # Fase 2 — Dependência (regulares sempre false)
                    "is_dependency": False,
                    "dependency_id": None,
                    "display_label": "",
                }
                for s in students
            ]
        }

        # =========================================================
        # Fase 2 — injeta alunos em dependência ATIVA neste componente
        # =========================================================
        if course_id:
            from utils.diary_constants import DEPENDENCY_DISPLAY_LABEL
            from tenant_scope import get_mantenedora_scope as _get_scope_att
            active_tenant_att = _get_scope_att(current_user, request)
            dep_filter_att = {
                "class_id": class_id, "course_id": course_id, "status": "active",
            }
            if active_tenant_att:
                dep_filter_att["mantenedora_id"] = active_tenant_att
            deps_active = await current_db.student_dependencies.find(dep_filter_att, {"_id": 0}).to_list(200)
            existing_sids = {s['id'] for s in result_payload['students']}
            dep_sids = [d['student_id'] for d in deps_active
                        if d.get('student_id') and d['student_id'] not in existing_sids]
            if dep_sids:
                dep_students = await current_db.students.find(
                    {"id": {"$in": dep_sids}},
                    {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1,
                     "status": 1, "dependency_mode": 1}
                ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(200)
                dep_by_sid = {d['student_id']: d for d in deps_active}
                stu_by_id = {s['id']: s for s in dep_students}
                for sid in dep_sids:
                    dep = dep_by_sid.get(sid)
                    stu = stu_by_id.get(sid)
                    if not (dep and stu):
                        continue
                    result_payload['students'].append({
                        "id": sid,
                        "full_name": stu.get('full_name', ''),
                        "enrollment_number": stu.get('enrollment_number'),
                        "status": records_map.get(sid, None),
                        "student_status": stu.get('status', 'active'),
                        "current_class_id": None,
                        "is_transferred_from_class": False,
                        "action_label": "",
                        "action_date": "",
                        "enrollment_date": "",
                        # Fase 2
                        "is_dependency": True,
                        "dependency_id": dep.get('id'),
                        "dependency_type": stu.get('dependency_mode'),
                        "origin_academic_year": dep.get('origin_academic_year'),
                        "display_label": DEPENDENCY_DISPLAY_LABEL,
                    })

        return result_payload

    @router.post("")
    async def create_or_update_attendance(attendance: AttendanceCreate, request: Request):
        """Cria ou atualiza frequência de uma turma (motor canônico compartilhado com o sync offline)."""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor', 'coordenador', 'auxiliar_secretaria'])(request)
        current_db = get_db_for_user(current_user)
        return await save_attendance_canonical(current_db, current_user, request, attendance, audit_service)

    # ============================================================
    # Fase 7 (Mai/2026) — Validação Institucional Pedagógica
    # ============================================================
    # Princípios (owner):
    #   - Validação é institucional, não opcional.
    #   - Granularidade interna SEMPRE individual; lote = açúcar.
    #   - Exige attendance.records.length > 0 (não dá pra validar nada).
    #   - audit_log obrigatório em TODA transição.
    #   - Validation NÃO recalcula nada — apenas marca.
    VALIDATE_ROLES = ['coordenador', 'apoio_pedagogico', 'diretor',
                      'secretario', 'admin', 'admin_teste', 'super_admin', 'gerente']

    async def _validate_single(current_db, attendance_id: str, *, user, request, batch_marker: str = None):
        """Executa UMA validação. Retorna o doc atualizado.

        Raises:
          ValueError(code) onde code ∈ {NOT_FOUND, ALREADY_VALIDATED, EMPTY_RECORDS}.
        """
        att = await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})
        if not att:
            raise ValueError("NOT_FOUND")
        if att.get("validated_by"):
            raise ValueError("ALREADY_VALIDATED")
        if not (att.get("records") or []):
            raise ValueError("EMPTY_RECORDS")

        now = datetime.now(timezone.utc).isoformat()
        new_version = (att.get("version") or 0) + 1
        await current_db.attendance.update_one(
            {"id": attendance_id, "version": att.get("version") or 0},
            {"$set": {
                "validated_by": user["id"],
                "validated_by_name": user.get("full_name") or user.get("email"),
                "validated_by_role": user.get("role"),
                "validated_at": now,
                "version": new_version,
                "updated_at": now,
                "updated_by": user["id"],
            }},
        )
        klass = await current_db.classes.find_one(
            {"id": att.get("class_id")}, {"_id": 0, "name": 1, "school_id": 1},
        )
        await audit_service.log(
            action='validate_attendance',
            collection='attendance',
            user=user, request=request, document_id=attendance_id,
            description=(
                f"Validou frequência institucional da turma "
                f"{(klass or {}).get('name', '—')} em {att.get('date')}"
            ),
            school_id=(klass or {}).get('school_id'),
            academic_year=att.get('academic_year'),
            extra_data={
                "entity_type": "attendance",
                "change_kind": "validation",
                "class_id": att.get("class_id"),
                "date": att.get("date"),
                "previous_version": att.get("version") or 0,
                "new_version": new_version,
                "batch_marker": batch_marker,  # link de N validações no mesmo lote
            },
        )
        return await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})

    @router.post("/{attendance_id}/validate")
    async def validate_attendance_endpoint(attendance_id: str, request: Request):
        current_user = await AuthMiddleware.require_roles(VALIDATE_ROLES)(request)
        current_db = get_db_for_user(current_user)
        try:
            return await _validate_single(current_db, attendance_id, user=current_user, request=request)
        except ValueError as e:
            code = str(e)
            if code == "NOT_FOUND":
                raise HTTPException(status_code=404, detail="Frequência não encontrada")
            if code == "ALREADY_VALIDATED":
                raise HTTPException(status_code=409, detail={"code": "ALREADY_VALIDATED",
                                                              "message": "Frequência já validada institucionalmente."})
            if code == "EMPTY_RECORDS":
                raise HTTPException(status_code=422, detail={"code": "EMPTY_RECORDS",
                                                              "message": "Não é possível validar frequência sem registros."})
            raise

    @router.post("/validate-batch")
    async def validate_attendance_batch(payload: ValidateBatchRequest, request: Request):
        """Validação em lote. Internamente: N validações individuais com N
        audit_logs. Retorna `{validated, skipped: [{date, reason}], total}`.
        """
        current_user = await AuthMiddleware.require_roles(VALIDATE_ROLES)(request)
        current_db = get_db_for_user(current_user)
        if not payload.dates:
            raise HTTPException(status_code=422, detail="Lista de datas obrigatória.")
        batch_marker = str(uuid.uuid4())

        validated, skipped = [], []
        for d in payload.dates:
            atts = await current_db.attendance.find(
                {"class_id": payload.class_id, "date": d},
                {"_id": 0, "id": 1},
            ).to_list(50)
            if not atts:
                skipped.append({"date": d, "reason": "NO_ATTENDANCE"})
                continue
            for a in atts:
                try:
                    doc = await _validate_single(
                        current_db, a["id"], user=current_user,
                        request=request, batch_marker=batch_marker,
                    )
                    validated.append({"date": d, "attendance_id": a["id"],
                                      "validated_at": doc.get("validated_at")})
                except ValueError as e:
                    skipped.append({"date": d, "attendance_id": a["id"], "reason": str(e)})
        return {
            "class_id": payload.class_id,
            "batch_marker": batch_marker,
            "total_requested": len(payload.dates),
            "total_validated": len(validated),
            "total_skipped": len(skipped),
            "validated": validated,
            "skipped": skipped,
        }

    @router.post("/{attendance_id}/unvalidate")
    async def unvalidate_attendance(attendance_id: str, payload: UnvalidateRequest, request: Request):
        """Reverte uma validação. Exige rationale ≥ 30 chars. Quem pode:
        quem validou originalmente OR admin/super_admin.
        """
        rationale = (payload.rationale or "").strip()
        if len(rationale) < 30:
            raise HTTPException(status_code=422, detail={
                "code": "RATIONALE_TOO_SHORT",
                "message": "Justificativa deve ter ao menos 30 caracteres.",
            })
        current_user = await AuthMiddleware.require_roles(VALIDATE_ROLES)(request)
        current_db = get_db_for_user(current_user)
        att = await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})
        if not att:
            raise HTTPException(status_code=404, detail="Frequência não encontrada")
        if not att.get("validated_by"):
            raise HTTPException(status_code=409, detail={
                "code": "NOT_VALIDATED",
                "message": "Frequência não está validada — nada a reverter.",
            })
        # Quem pode: quem validou OR admin/super_admin
        is_admin = current_user.get("role") in ("admin", "admin_teste", "super_admin")
        if att["validated_by"] != current_user["id"] and not is_admin:
            raise HTTPException(status_code=403, detail={
                "code": "FORBIDDEN_UNVALIDATE",
                "message": "Apenas o autor da validação ou admin/super_admin podem reverter.",
            })

        now = datetime.now(timezone.utc).isoformat()
        new_version = (att.get("version") or 0) + 1
        previous_validation = {
            "validated_by": att.get("validated_by"),
            "validated_by_name": att.get("validated_by_name"),
            "validated_by_role": att.get("validated_by_role"),
            "validated_at": att.get("validated_at"),
        }
        await current_db.attendance.update_one(
            {"id": attendance_id, "version": att.get("version") or 0},
            {
                "$set": {
                    "validated_by": None,
                    "validated_by_name": None,
                    "validated_by_role": None,
                    "validated_at": None,
                    "version": new_version,
                    "updated_at": now,
                    "updated_by": current_user["id"],
                },
                "$push": {
                    # Histórico append-only de validações revertidas.
                    "validation_history": {
                        **previous_validation,
                        "unvalidated_by": current_user["id"],
                        "unvalidated_by_name": current_user.get("full_name"),
                        "unvalidated_at": now,
                        "rationale": rationale,
                    },
                },
            },
        )
        klass = await current_db.classes.find_one(
            {"id": att.get("class_id")}, {"_id": 0, "name": 1, "school_id": 1},
        )
        await audit_service.log(
            action='unvalidate_attendance',
            collection='attendance',
            user=current_user, request=request, document_id=attendance_id,
            description=(
                f"REVERTEU validação institucional da turma "
                f"{(klass or {}).get('name', '—')} em {att.get('date')}: "
                f"{rationale[:80]}"
            ),
            school_id=(klass or {}).get('school_id'),
            academic_year=att.get('academic_year'),
            old_value=previous_validation,
            extra_data={
                "entity_type": "attendance",
                "change_kind": "unvalidation",
                "class_id": att.get("class_id"),
                "date": att.get("date"),
                "rationale": rationale,
                "previous_version": att.get("version") or 0,
                "new_version": new_version,
            },
        )
        return await current_db.attendance.find_one({"id": attendance_id}, {"_id": 0})

    @router.delete("/{attendance_id}")
    async def delete_attendance(attendance_id: str, request: Request):
        """Remove registro de frequência"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario', 'professor'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.attendance.find_one({"id": attendance_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Registro de frequência não encontrado")
        
        await current_db.attendance.delete_one({"id": attendance_id})
        
        try:
            class_info = await current_db.classes.find_one({"id": existing.get('class_id')}, {"_id": 0, "name": 1, "school_id": 1})
            await audit_service.log(
                action='delete',
                collection='attendance',
                user=current_user,
                request=request,
                document_id=attendance_id,
                description=f"EXCLUIU frequência da turma {class_info.get('name', 'N/A') if class_info else 'N/A'} de {existing.get('date')}",
                school_id=class_info.get('school_id') if class_info else None,
                academic_year=existing.get('academic_year'),
                old_value={'date': existing.get('date'), 'records_count': len(existing.get('records', []))}
            )
        except Exception as e:
            logger.error(f"Falha ao registrar auditoria de exclusão de frequência: {e}")
        
        return {"message": "Frequência removida com sucesso"}

    @router.get("/report/student/{student_id}")
    async def get_student_attendance_report(
        student_id: str,
        request: Request,
        academic_year: Optional[int] = None
    ):
        """Relatório de frequência de um aluno"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        student = await current_db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        
        # Busca todos os registros de frequência do aluno
        attendances = await current_db.attendance.find(
            {"academic_year": academic_year},
            {"_id": 0}
        ).to_list(5000)
        
        # Filtra registros do aluno
        student_attendances = []
        for att in attendances:
            for record in att.get('records', []):
                if record.get('student_id') == student_id:
                    student_attendances.append({
                        'date': att.get('date'),
                        'class_id': att.get('class_id'),
                        'status': record.get('status'),
                        'period': att.get('period', 'regular'),
                        'course_id': att.get('course_id')
                    })
        
        # Calcula estatísticas
        total = len(student_attendances)
        present = sum(1 for a in student_attendances if a['status'] in ['present', 'P'])
        absent = sum(1 for a in student_attendances if a['status'] in ['absent', 'F', 'A'])
        justified = sum(1 for a in student_attendances if a['status'] in ['justified', 'J'])
        late = sum(1 for a in student_attendances if a['status'] in ['late', 'L'])
        
        return {
            "student": student,
            "academic_year": academic_year,
            "total_records": total,
            "present": present,
            "absent": absent,
            "justified": justified,
            "late": late,
            "attendance_rate": round(present / total * 100, 2) if total > 0 else 0,
            "details": sorted(student_attendances, key=lambda x: x['date'], reverse=True)[:50]
        }

    @router.get("/report/class/{class_id}")
    async def get_class_attendance_report(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None,
        bimestre: Optional[int] = None
    ):
        """Relatório de frequência de uma turma (filtro opcional por componente)"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        if not academic_year:
            academic_year = datetime.now().year
        
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")
        
        # Busca alunos matriculados - usando múltiplas fontes
        enrollments = await current_db.enrollments.find(
            {"class_id": class_id, "status": "active"},
            {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1}
        ).to_list(1000)
        
        enrollment_student_ids = set()
        enrollment_numbers = {}
        for e in enrollments:
            student_id = e.get('student_id')
            enrollment_student_ids.add(student_id)
            if student_id not in enrollment_numbers or e.get('academic_year') == academic_year:
                enrollment_numbers[student_id] = e.get('enrollment_number')
        
        # Busca alunos diretamente com class_id (fallback)
        direct_students = await current_db.students.find(
            {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
            {"_id": 0, "id": 1, "enrollment_number": 1}
        ).to_list(1000)
        
        for s in direct_students:
            student_id = s.get('id')
            if student_id not in enrollment_numbers:
                enrollment_numbers[student_id] = s.get('enrollment_number')
        
        direct_student_ids = {s.get('id') for s in direct_students}
        all_student_ids = list(enrollment_student_ids.union(direct_student_ids))
        
        students = []
        if all_student_ids:
            students = await current_db.students.find(
                {"id": {"$in": all_student_ids}},
                {"_id": 0, "id": 1, "full_name": 1}
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)
        
        # Filtrar por bimestre (datas) se informado
        period_start = None
        period_end = None
        if bimestre:
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
            )
            if not calendario:
                calendario = await current_db.calendario_letivo.find_one(
                    {"ano_letivo": academic_year}, {"_id": 0}
                )
            if calendario:
                bim_inicio = calendario.get(f"bimestre_{bimestre}_inicio")
                bim_fim = calendario.get(f"bimestre_{bimestre}_fim")
                if bim_inicio and bim_fim:
                    period_start = str(bim_inicio)[:10]
                    period_end = str(bim_fim)[:10]
            if not period_start:
                bimestre_periodos = {
                    1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                    2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                    3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                    4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
                }
                period_start, period_end = bimestre_periodos.get(bimestre, (None, None))

        # Busca todos os registros de frequência da turma
        att_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            att_query["course_id"] = course_id
        if period_start and period_end:
            att_query["date"] = {"$gte": period_start, "$lte": period_end}
        attendances = await current_db.attendance.find(
            att_query,
            {"_id": 0}
        ).to_list(1000)
        
        # Calcula estatísticas por aluno
        student_stats = {}
        for student in students:
            student_stats[student['id']] = {
                'present': 0,
                'absent': 0,
                'justified': 0,
                'late': 0,
                'total': 0
            }
        
        # Coleta datas de aula para calcular atestados (1ª passada apenas datas)
        attendance_dates = set()
        aula_keys_set = set()
        for att in attendances:
            att_date = att.get('date', '')[:10]
            if att_date:
                attendance_dates.add(att_date)
            has_aula_numero = att.get('aula_numero') is not None
            num_classes = 1 if has_aula_numero else att.get('number_of_classes', 1)
            if has_aula_numero:
                aula_keys_set.add((att_date, att['aula_numero']))
            else:
                for i in range(1, num_classes + 1):
                    aula_keys_set.add((att_date, i))

        # Busca atestados médicos PRIMEIRO (Feb 2026: regra do 'A' substitui status)
        medical_days = {}
        if all_student_ids and attendance_dates:
            sorted_dates = sorted(attendance_dates)
            min_date = sorted_dates[0]
            max_date = sorted_dates[-1]
            certificates = await current_db.medical_certificates.find(
                {
                    "student_id": {"$in": all_student_ids},
                    "start_date": {"$lte": max_date},
                    "end_date": {"$gte": min_date}
                },
                {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1}
            ).to_list(None)
            for cert in certificates:
                sid = cert.get('student_id')
                if sid not in medical_days:
                    medical_days[sid] = set()
                start = cert.get('start_date', '')[:10]
                end = cert.get('end_date', '')[:10]
                for d in attendance_dates:
                    if start <= d <= end:
                        medical_days[sid].add(d)

        # 2ª passada: classifica cada célula respeitando atestado (A vence P/F/J)
        for att in attendances:
            att_date = att.get('date', '')[:10]
            has_aula_numero = att.get('aula_numero') is not None
            num_classes = 1 if has_aula_numero else att.get('number_of_classes', 1)

            for record in att.get('records', []):
                sid = record.get('student_id')
                if sid not in student_stats:
                    continue
                # P0: defesa em profundidade — registros marcados com dependency_id
                # NÃO contam para cálculo de frequência regular da turma.
                if record.get('dependency_id'):
                    continue
                raw_status = record.get('status', '')
                in_atestado = att_date in medical_days.get(sid, set())

                if '|' in raw_status:
                    # Pipe-separated statuses (legado multi-aula)
                    statuses = raw_status.split('|')
                    student_stats[sid]['total'] += len(statuses)
                    for s in statuses:
                        s = s.strip()
                        if in_atestado:
                            student_stats[sid]['medical'] = student_stats[sid].get('medical', 0) + 1
                        elif s in ['present', 'P']:
                            student_stats[sid]['present'] += 1
                        elif s in ['absent', 'F', 'A']:
                            student_stats[sid]['absent'] += 1
                        elif s in ['justified', 'J']:
                            student_stats[sid]['justified'] += 1
                else:
                    student_stats[sid]['total'] += num_classes
                    if in_atestado:
                        student_stats[sid]['medical'] = student_stats[sid].get('medical', 0) + num_classes
                    elif raw_status in ['present', 'P']:
                        student_stats[sid]['present'] += num_classes
                    elif raw_status in ['absent', 'F', 'A']:
                        student_stats[sid]['absent'] += num_classes
                    elif raw_status in ['justified', 'J']:
                        student_stats[sid]['justified'] += num_classes
                    elif raw_status in ['late', 'L']:
                        student_stats[sid]['late'] += num_classes
        
        report = []
        for student in students:
            stats = student_stats.get(student['id'], {})
            total = stats.get('total', 0)
            present = stats.get('present', 0)
            justified = stats.get('justified', 0)
            absent = stats.get('absent', 0)
            medical_count = stats.get('medical', 0)

            # Feb 2026: medical conta como presença (não-falta) — alinhado com PDF
            attendance_percentage = round(
                (present + justified + medical_count) / total * 100, 1
            ) if total > 0 else 0

            # Define status baseado na frequência mínima (75%)
            freq_status = 'regular' if attendance_percentage >= 75 else 'infrequente'

            report.append({
                "student_id": student['id'],
                "student_name": student['full_name'],
                "enrollment_number": enrollment_numbers.get(student['id']),
                "present": present,
                "absent": absent,
                "justified": justified,
                "medical": medical_count,
                "late": stats.get('late', 0),
                "total": total,
                "attendance_percentage": attendance_percentage,
                "status": freq_status
            })
        
        # Detectar se é Anos Finais para ajustar label
        education_level = turma.get('education_level') or turma.get('nivel_ensino') or ''
        if not education_level:
            import re
            ref = (turma.get('grade_level') or turma.get('name') or '').upper()
            if re.search(r'PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL', ref):
                education_level = 'educacao_infantil'
            elif re.search(r'\bEJA\b', ref):
                education_level = 'eja_final' if re.search(r'FINAL|[6-9]', ref) else 'eja_inicial'
            else:
                m = re.match(r'(\d+)', ref)
                if m:
                    num = int(m.group(1))
                    education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'
        
        is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']
        
        return {
            "class": turma,
            "academic_year": academic_year,
            "course_id": course_id,
            "total_records": len(aula_keys_set),
            "total_school_days_recorded": len(aula_keys_set),
            "total_students": len(students),
            "report_type": "aulas" if is_anos_finais else "dias",
            "students": report
        }


    @router.get("/attendance-summary/{class_id}")
    async def get_attendance_summary(
        class_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        course_id: Optional[str] = None
    ):
        """
        Resumo de frequência da turma: dias/aulas previstos, registrados e restantes.
        Para anos iniciais/infantil: conta dias distintos.
        Para anos finais: conta aulas (soma de number_of_classes por registro).
        """
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)

        if not academic_year:
            academic_year = datetime.now().year

        # Buscar turma
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0})
        if not turma:
            raise HTTPException(status_code=404, detail="Turma não encontrada")

        # Buscar calendário letivo (coleção: calendario_letivo, calendário geral com school_id=None)
        calendario = await current_db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
        )
        if not calendario:
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )

        dias_letivos_previstos = 0
        if calendario:
            # Calcular dias letivos — lógica idêntica ao endpoint /calendario-letivo/{ano}/dias-letivos
            from datetime import timedelta

            eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
            events = await current_db.calendar_events.find(
                {"academic_year": academic_year}, {"_id": 0}
            ).to_list(1000)

            datas_nao_letivas = set()
            datas_sabados_letivos = set()
            for event in events:
                event_type = event.get('event_type', '')
                start_date_str = event.get('start_date')
                end_date_str = event.get('end_date') or start_date_str
                if not start_date_str:
                    continue
                try:
                    start_date = datetime.strptime(start_date_str[:10], '%Y-%m-%d').date()
                    end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d').date()
                    current = start_date
                    while current <= end_date:
                        if event_type in eventos_nao_letivos:
                            datas_nao_letivas.add(current)
                        elif event_type == 'sabado_letivo':
                            datas_sabados_letivos.add(current)
                        elif event.get('is_school_day', False) and current.weekday() == 5:
                            datas_sabados_letivos.add(current)
                        current += timedelta(days=1)
                except (ValueError, TypeError):
                    continue

            def _calcular_dias_periodo(inicio_str, fim_str):
                if not inicio_str or not fim_str:
                    return 0
                try:
                    inicio = datetime.strptime(str(inicio_str)[:10], '%Y-%m-%d').date()
                    fim = datetime.strptime(str(fim_str)[:10], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    return 0
                dias = 0
                current = inicio
                while current <= fim:
                    if current in datas_sabados_letivos:
                        dias += 1
                    elif current.weekday() < 5:
                        if current not in datas_nao_letivas:
                            dias += 1
                    current += timedelta(days=1)
                return dias

            b1 = _calcular_dias_periodo(calendario.get('bimestre_1_inicio'), calendario.get('bimestre_1_fim'))
            b2 = _calcular_dias_periodo(calendario.get('bimestre_2_inicio'), calendario.get('bimestre_2_fim'))
            b3 = _calcular_dias_periodo(calendario.get('bimestre_3_inicio'), calendario.get('bimestre_3_fim'))
            b4 = _calcular_dias_periodo(calendario.get('bimestre_4_inicio'), calendario.get('bimestre_4_fim'))
            dias_letivos_previstos = b1 + b2 + b3 + b4

            # Fallback para o campo dias_letivos_previstos se cálculo dos bimestres retornar 0
            if dias_letivos_previstos == 0:
                dias_letivos_previstos = calendario.get('dias_letivos_previstos', 200) or 200

        # Detectar nível de ensino
        education_level = turma.get('education_level') or turma.get('nivel_ensino') or ''
        # Inferir do nome se não tem campo
        if not education_level:
            ref = (turma.get('grade_level') or turma.get('name') or '').upper()
            import re
            if re.search(r'PRÉ|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL', ref):
                education_level = 'educacao_infantil'
            elif re.search(r'\bEJA\b', ref):
                education_level = 'eja_final' if re.search(r'FINAL|[6-9]', ref) else 'eja_inicial'
            else:
                m = re.match(r'(\d+)', ref)
                if m:
                    num = int(m.group(1))
                    education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'
                else:
                    if turma.get('series'):
                        m2 = re.match(r'(\d+)', str(turma['series'][0]))
                        if m2:
                            num = int(m2.group(1))
                            education_level = 'fundamental_anos_iniciais' if num <= 5 else 'fundamental_anos_finais'

        is_anos_finais = education_level in ['fundamental_anos_finais', 'eja_final']

        # Buscar registros de frequência
        att_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            att_query["course_id"] = course_id
        attendances = await current_db.attendance.find(att_query, {"_id": 0}).to_list(5000)

        if is_anos_finais:
            # Deduplicar: expandir todos os registros em tuplas (date, aula) únicas
            aula_keys = set()
            for att in attendances:
                if att.get('aula_numero') is not None:
                    aula_keys.add((att.get('date', '')[:10], att['aula_numero']))
                else:
                    nc = att.get('number_of_classes', 1)
                    for i in range(1, nc + 1):
                        aula_keys.add((att.get('date', '')[:10], i))
            aulas_registradas = len(aula_keys)

            # Calcular aulas previstas: usar carga horária do componente (workload)
            # Fonte primária: workload do curso (total anual de hora-aula)
            aulas_previstas = 0
            if course_id:
                course = await current_db.courses.find_one({"id": course_id}, {"_id": 0})
                if course:
                    aulas_previstas = course.get('workload', 0) or 0

            # Fallback: usar schedule_slots se workload não definido
            if aulas_previstas == 0 and course_id:
                schedule = await current_db.class_schedules.find_one(
                    {"class_id": class_id}, {"_id": 0, "schedule_slots": 1}
                )
                if schedule and schedule.get('schedule_slots'):
                    aulas_semana = await count_schedule_slots_for_course(
                        current_db, schedule['schedule_slots'], course_id
                    )
                    aulas_previstas = int((dias_letivos_previstos / 5) * aulas_semana) if aulas_semana > 0 else 0

            return {
                "type": "aulas",
                "previstos": aulas_previstas,
                "registrados": aulas_registradas,
                "restantes": max(0, aulas_previstas - aulas_registradas)
            }
        else:
            # Para anos iniciais/infantil: contar DIAS distintos
            dias_registrados = len(set(att.get('date') for att in attendances if att.get('date')))

            return {
                "type": "dias",
                "previstos": dias_letivos_previstos,
                "registrados": dias_registrados,
                "restantes": max(0, dias_letivos_previstos - dias_registrados)
            }


    # Helper: contar slots do horário com fallback por nome do componente
    async def count_schedule_slots_for_course(current_db, schedule_slots, course_id, day_filter=None):
        """Conta slots do horário para um componente, com fallback por nome se course_id não bater"""
        # Match direto por course_id
        count = sum(
            1 for s in schedule_slots
            if s.get('course_id') == course_id and (day_filter is None or s.get('day') == day_filter)
        )
        if count > 0:
            return count
        
        # Fallback: match por nome do componente
        course = await current_db.courses.find_one({"id": course_id}, {"_id": 0, "name": 1})
        if course and course.get('name'):
            course_name = course['name'].upper().strip()
            # Buscar course_ids no horário que tenham o mesmo nome
            slot_course_ids = set(s.get('course_id') for s in schedule_slots if s.get('course_id'))
            for scid in slot_course_ids:
                sc = await current_db.courses.find_one({"id": scid}, {"_id": 0, "name": 1})
                if sc and sc.get('name', '').upper().strip() == course_name:
                    count = sum(
                        1 for s in schedule_slots
                        if s.get('course_id') == scid and (day_filter is None or s.get('day') == day_filter)
                    )
                    if count > 0:
                        return count
        return 0

    @router.get("/schedule-classes-count")
    async def get_schedule_classes_count(
        request: Request,
        class_id: str,
        course_id: str,
        date: str,
        academic_year: int
    ):
        """Retorna o número de aulas de um componente para o dia da semana da data informada"""
        user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(user)
        
        # Mapear dia da semana Python para o ID usado no schedule
        from datetime import datetime as dt
        day_map = {0: 'segunda', 1: 'terca', 2: 'quarta', 3: 'quinta', 4: 'sexta', 5: 'sabado', 6: 'domingo'}
        try:
            d = dt.strptime(date, '%Y-%m-%d')
        except Exception:
            return {"count": 1, "has_schedule": False}

        if d.weekday() == 6:  # domingo nunca tem aulas
            return {"count": 0, "has_schedule": True}

        if d.weekday() == 5:
            # SÁBADO LETIVO: segue a rotação (1º=segunda, 2º=terça, …), igual ao
            # Horário de Aulas. Sem isso, a frequência divergia do horário.
            from services.school_calendar_helper import get_saturday_weekday_map
            klass = await current_db.classes.find_one({"id": class_id}, {"_id": 0, "mantenedora_id": 1})
            sat_map = await get_saturday_weekday_map(
                current_db, academic_year=academic_year,
                mantenedora_id=(klass or {}).get('mantenedora_id'),
            )
            corr = sat_map.get(d.strftime('%Y-%m-%d'))
            if not corr:
                # Sábado comum (não letivo) → sem aulas.
                return {"count": 0, "has_schedule": True}
            day_id = {1: 'segunda', 2: 'terca', 3: 'quarta', 4: 'quinta', 5: 'sexta'}.get(corr, '')
        else:
            day_id = day_map.get(d.weekday(), '')

        if not day_id:
            return {"count": 0, "has_schedule": True}
        
        schedule = await current_db.class_schedules.find_one(
            {"class_id": class_id, "academic_year": academic_year},
            {"_id": 0, "schedule_slots": 1}
        )
        
        if not schedule or not schedule.get('schedule_slots'):
            return {"count": 1, "has_schedule": False}
        
        count = await count_schedule_slots_for_course(current_db, schedule['schedule_slots'], course_id, day_filter=day_id)
        
        return {"count": count, "has_schedule": True}

    @router.get("/dates-with-records")
    async def get_dates_with_records(
        request: Request,
        class_id: str,
        academic_year: int,
        course_id: Optional[str] = None
    ):
        """Retorna lista de datas que possuem registros de frequência"""
        user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(user)
        
        query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            query["course_id"] = course_id
        
        attendances = await current_db.attendance.find(
            query, {"_id": 0, "date": 1}
        ).to_list(5000)
        
        dates = sorted(list(set(att.get('date', '')[:10] for att in attendances if att.get('date'))))
        return {"dates": dates}

    @router.get("/bimestre-summary")
    async def get_bimestre_summary(
        request: Request,
        class_id: str,
        academic_year: int,
        course_id: Optional[str] = None
    ):
        """Retorna resumo de previstos/registrados por bimestre"""
        user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(user)
        
        from datetime import datetime as dt, timedelta
        
        # Buscar calendário letivo
        calendario = await current_db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
        )
        if not calendario:
            calendario = await current_db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )
        
        # Buscar eventos do calendário
        events = await current_db.calendar_events.find(
            {"academic_year": academic_year}, {"_id": 0}
        ).to_list(1000)
        
        datas_nao_letivas = set()
        datas_sabados_letivos = set()
        for event in events:
            event_type = event.get('event_type', '')
            start_str = (event.get('start_date') or '')[:10]
            end_str = (event.get('end_date') or start_str)[:10]
            if not start_str:
                continue
            if event_type == 'sabado_letivo' or (event.get('is_school_day') and start_str):
                try:
                    d = dt.strptime(start_str, '%Y-%m-%d')
                    end_d = dt.strptime(end_str, '%Y-%m-%d')
                    while d <= end_d:
                        if d.weekday() == 5:
                            datas_sabados_letivos.add(d.strftime('%Y-%m-%d'))
                        d += timedelta(days=1)
                except:
                    pass
            if event_type.endswith('feriado') or 'feriado' in event_type or event_type == 'recesso_escolar' or event.get('is_school_day') is False:
                try:
                    d = dt.strptime(start_str, '%Y-%m-%d')
                    end_d = dt.strptime(end_str, '%Y-%m-%d')
                    while d <= end_d:
                        datas_nao_letivas.add(d.strftime('%Y-%m-%d'))
                        d += timedelta(days=1)
                except:
                    pass
        
        # Detectar nível de ensino
        turma = await current_db.classes.find_one({"id": class_id}, {"_id": 0, "education_level": 1})
        education_level = turma.get('education_level', '') if turma else ''
        is_anos_finais = education_level in ('fundamental_anos_finais', 'eja_final')
        
        # Para anos finais: buscar horário de aulas do componente (com fallback por nome)
        aulas_semana = 0
        if is_anos_finais and course_id:
            schedule = await current_db.class_schedules.find_one(
                {"class_id": class_id, "academic_year": academic_year},
                {"_id": 0, "schedule_slots": 1}
            )
            if schedule and schedule.get('schedule_slots'):
                aulas_semana = await count_schedule_slots_for_course(
                    current_db, schedule['schedule_slots'], course_id
                )
        
        # Buscar todos os registros de frequência
        att_query = {"class_id": class_id, "academic_year": academic_year}
        if course_id:
            att_query["course_id"] = course_id
        attendances = await current_db.attendance.find(
            att_query, {"_id": 0, "date": 1, "aula_numero": 1, "number_of_classes": 1}
        ).to_list(5000)
        
        result = []
        for bim in range(1, 5):
            bim_key_inicio = f"bimestre_{bim}_inicio"
            bim_key_fim = f"bimestre_{bim}_fim"
            
            if calendario and calendario.get(bim_key_inicio) and calendario.get(bim_key_fim):
                p_start = str(calendario[bim_key_inicio])[:10]
                p_end = str(calendario[bim_key_fim])[:10]
            else:
                fallback = {
                    1: (f"{academic_year}-02-01", f"{academic_year}-04-30"),
                    2: (f"{academic_year}-05-01", f"{academic_year}-07-15"),
                    3: (f"{academic_year}-07-16", f"{academic_year}-09-30"),
                    4: (f"{academic_year}-10-01", f"{academic_year}-12-20"),
                }
                p_start, p_end = fallback[bim]
            
            # Contar dias letivos no período
            dias_letivos = 0
            try:
                d = dt.strptime(p_start, '%Y-%m-%d')
                end_d = dt.strptime(p_end, '%Y-%m-%d')
                while d <= end_d:
                    ds = d.strftime('%Y-%m-%d')
                    dow = d.weekday()
                    is_sunday = dow == 6
                    is_saturday = dow == 5
                    is_blocked = is_sunday or ds in datas_nao_letivas or (is_saturday and ds not in datas_sabados_letivos)
                    if not is_blocked:
                        dias_letivos += 1
                    d += timedelta(days=1)
            except:
                pass
            
            # Registrados no bimestre
            bim_atts = [a for a in attendances if p_start <= a.get('date', '')[:10] <= p_end]
            
            if is_anos_finais:
                # Aulas previstas = dias_letivos * aulas_por_semana / 5
                previstos = round(dias_letivos * aulas_semana / 5) if aulas_semana > 0 else 0
                # Aulas registradas: deduplicar (date, aula) para evitar contagem dupla
                aula_keys = set()
                for att in bim_atts:
                    if att.get('aula_numero') is not None:
                        aula_keys.add((att.get('date', '')[:10], att['aula_numero']))
                    else:
                        nc = att.get('number_of_classes', 1)
                        for i in range(1, nc + 1):
                            aula_keys.add((att.get('date', '')[:10], i))
                registrados = len(aula_keys)
                label_prev = "AULAS PREVISTAS"
                label_reg = "AULAS REGISTRADAS"
            else:
                previstos = dias_letivos
                registrados = len(set(a.get('date', '')[:10] for a in bim_atts))
                label_prev = "DIAS PREVISTOS"
                label_reg = "DIAS REGISTRADOS"
            
            result.append({
                "bimestre": bim,
                "previstos": previstos,
                "registrados": registrados,
                "label_prev": label_prev,
                "label_reg": label_reg,
                "period_start": p_start,
                "period_end": p_end
            })
        
        return result

    @router.get("/class-students-info/{class_id}")
    async def get_class_students_info(
        class_id: str,
        request: Request,
        academic_year: int = None
    ):
        """Retorna informações dos alunos de uma turma (nome, nascimento, mãe, telefone)."""
        await AuthMiddleware.get_current_user(request)

        if not academic_year:
            from datetime import datetime
            academic_year = datetime.now().year

        # Buscar alunos ativos na turma
        excluded = ["deceased", "transferred", "dropout", "relocated", "reclassified", "progressed",
                     "Falecido", "Transferido", "Desistente", "Remanejado", "Reclassificado", "Progredido"]

        students_cursor = db.students.find(
            {"class_id": class_id, "status": {"$nin": excluded + ["inactive"]}},
            {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "mother_name": 1, "mother_phone": 1}
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1})

        students = await students_cursor.to_list(1000)

        return {"students": students, "total": len(students)}

    return router
