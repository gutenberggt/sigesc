"""
Router para módulo de RH / Folha de Pagamento
Gerencia competências mensais, folhas por escola, itens e ocorrências.
Fase 2: Upload de documentos, hora-aula avançado, substituições vinculadas,
        horas complementares detalhadas, auditoria de alterações.
"""

from fastapi import APIRouter, HTTPException, Request, Query, UploadFile, File
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path
import uuid
import logging

from models import (
    PayrollCompetency, PayrollCompetencyCreate,
    SchoolPayroll, PayrollItem, PayrollItemUpdate,
    PayrollOccurrence, PayrollOccurrenceCreate, PayrollOccurrenceUpdate
)
from auth_middleware import AuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hr", tags=["RH / Folha"])

# Roles com acesso ao módulo
ADMIN_ROLES = ['admin', 'admin_teste']
SEMED_ROLES = ['semed', 'semed3']
SCHOOL_ROLES = ['diretor', 'secretario']
ALL_HR_ROLES = ADMIN_ROLES + SEMED_ROLES + SCHOOL_ROLES

# Diretório de uploads de documentos HR
HR_UPLOADS_DIR = Path(__file__).parent.parent / "uploads" / "hr"
HR_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Motivos parametrizados de horas complementares
COMPLEMENTARY_MOTIVES = [
    "Planejamento pedagógico extraordinário",
    "Reforço escolar",
    "Reposição de aulas",
    "Substituição temporária",
    "Atividade administrativa",
    "Projeto especial",
    "Atendimento individualizado",
    "Jornada suplementar autorizada",
    "Formação continuada",
    "Reunião de pais/responsáveis",
    "Outro"
]

# Subtipos de afastamento/licença
LEAVE_SUBTYPES = [
    "Licença médica",
    "Licença maternidade",
    "Licença paternidade",
    "Licença prêmio",
    "Licença sem vencimento",
    "Cessão",
    "Afastamento disciplinar",
    "Readaptação",
    "Férias",
    "Licença para tratamento",
    "Licença para estudo",
    "Outro"
]


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""
    connection_manager = kwargs.get('connection_manager')

    def get_db_for_user(user: dict):
        if user.get('is_sandbox'):
            return sandbox_db if sandbox_db else db
        return db

    async def _notify_school_return(current_db, payroll: dict, reason: str, returned_by_name: str):
        """Cria aviso para diretor e secretário da escola quando folha é devolvida"""
        school_id = payroll.get('school_id')
        if not school_id:
            return

        school = await current_db.schools.find_one({"id": school_id}, {"_id": 0, "name": 1})
        school_name = school.get('name', 'Escola') if school else 'Escola'
        month = payroll.get('month', 0)
        year = payroll.get('year', 0)
        month_names = ['','Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
        comp_label = f"{month_names[month] if 0 < month <= 12 else month}/{year}"

        # Buscar diretores e secretários vinculados a esta escola
        target_users = set()
        async for u in current_db.users.find(
            {
                'school_links.school_id': school_id,
                'role': {'$in': ['diretor', 'secretario']},
                'status': 'active'
            },
            {'id': 1}
        ):
            target_users.add(u['id'])

        if not target_users:
            return

        # Criar aviso no sistema
        announcement = {
            'id': str(uuid.uuid4()),
            'title': f'Folha Devolvida - {comp_label}',
            'content': f'A folha de pagamento da escola {school_name} referente a {comp_label} foi devolvida pela Secretaria para correção.\n\nMotivo: {reason or "Não informado"}\n\nPor favor, acesse o módulo RH/Folha para revisar e corrigir os itens apontados.',
            'recipient': {
                'type': 'school',
                'school_ids': [school_id],
                'target_roles': ['diretor', 'secretario'],
                'class_ids': [],
                'user_ids': []
            },
            'sender_id': 'sistema',
            'sender_name': returned_by_name or 'Secretaria de Educação',
            'sender_role': 'admin',
            'sender_foto_url': None,
            'target_user_ids': list(target_users),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': None
        }
        await current_db.announcements.insert_one(announcement)

        # Notificar em tempo real via WebSocket
        if connection_manager:
            for user_id in target_users:
                try:
                    await connection_manager.send_notification(user_id, {
                        'type': 'new_announcement',
                        'announcement': {
                            'id': announcement['id'],
                            'title': announcement['title'],
                            'sender_name': announcement['sender_name']
                        }
                    })
                except Exception:
                    pass

        logger.info(f"Notificação de devolução enviada para {len(target_users)} usuários da escola {school_name}")

    # ============================================
    # ENUMS / PARAMETROS
    # ============================================

    @router.get("/enums")
    async def get_hr_enums(request: Request):
        """Retorna listas parametrizáveis do módulo RH"""
        await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        return {
            "complementary_motives": COMPLEMENTARY_MOTIVES,
            "leave_subtypes": LEAVE_SUBTYPES,
        }

    # ============================================
    # UPLOAD DE DOCUMENTOS
    # ============================================

    @router.post("/upload")
    async def upload_hr_document(request: Request, file: UploadFile = File(...)):
        """Upload de documento comprobatório (atestado, portaria, etc.)"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)

        allowed_ext = ['.pdf', '.jpg', '.jpeg', '.png', '.webp']
        file_ext = Path(file.filename).suffix.lower() if file.filename else ''
        if file_ext not in allowed_ext:
            raise HTTPException(400, "Tipo não permitido. Use PDF, JPG, PNG ou WEBP.")

        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB max
            raise HTTPException(400, "Arquivo muito grande. Máximo 10MB.")

        unique_name = f"{uuid.uuid4()}{file_ext}"
        file_path = HR_UPLOADS_DIR / unique_name
        with open(file_path, 'wb') as f:
            f.write(content)

        return {"url": f"/api/uploads/hr/{unique_name}", "filename": file.filename}

    # ============================================
    # COMPETÊNCIAS MENSAIS
    # ============================================

    @router.get("/competencies")
    async def list_competencies(
        request: Request,
        year: Optional[int] = None,
        status: Optional[str] = None
    ):
        """Lista competências mensais (apenas admin/semed)"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES + SEMED_ROLES)(request)
        current_db = get_db_for_user(user)

        query = {}
        if year:
            query['year'] = year
        if status:
            query['status'] = status

        items = await current_db.payroll_competencies.find(
            query, {"_id": 0}
        ).sort([("year", -1), ("month", -1)]).to_list(100)
        return items

    @router.post("/competencies")
    async def create_competency(data: PayrollCompetencyCreate, request: Request):
        """Abre uma nova competência mensal"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES)(request)
        current_db = get_db_for_user(user)

        # Verifica duplicata
        existing = await current_db.payroll_competencies.find_one(
            {"year": data.year, "month": data.month}
        )
        if existing:
            raise HTTPException(400, f"Competência {data.month:02d}/{data.year} já existe.")

        comp = PayrollCompetency(
            year=data.year,
            month=data.month,
            launch_start=data.launch_start,
            launch_end=data.launch_end,
            review_end=data.review_end,
            opened_by=user.get('id')
        )
        doc = comp.model_dump()
        await current_db.payroll_competencies.insert_one(doc)

        # Gera pré-folha automática para todas as escolas ativas
        await _generate_pre_payroll(current_db, comp)

        return await current_db.payroll_competencies.find_one({"id": comp.id}, {"_id": 0})

    @router.put("/competencies/{competency_id}/close")
    async def close_competency(competency_id: str, request: Request):
        """Fecha uma competência (bloqueia edições)"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES)(request)
        current_db = get_db_for_user(user)

        comp = await current_db.payroll_competencies.find_one({"id": competency_id})
        if not comp:
            raise HTTPException(404, "Competência não encontrada")

        await current_db.payroll_competencies.update_one(
            {"id": competency_id},
            {"$set": {
                "status": "closed",
                "closed_by": user.get('id'),
                "closed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Fecha todas as folhas aprovadas dessa competência
        await current_db.school_payrolls.update_many(
            {"competency_id": competency_id, "status": "approved"},
            {"$set": {"status": "closed"}}
        )

        return {"message": "Competência fechada com sucesso"}

    @router.put("/competencies/{competency_id}/reopen")
    async def reopen_competency(competency_id: str, request: Request):
        """Reabre uma competência fechada (com justificativa obrigatória e log)"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES)(request)
        current_db = get_db_for_user(user)

        try:
            body = await request.json()
            justification = body.get('justification', '')
        except Exception:
            justification = ''

        if not justification or len(justification.strip()) < 5:
            raise HTTPException(400, "Justificativa obrigatória para reabertura (mínimo 5 caracteres)")

        comp = await current_db.payroll_competencies.find_one({"id": competency_id})
        if not comp:
            raise HTTPException(404, "Competência não encontrada")

        await current_db.payroll_competencies.update_one(
            {"id": competency_id},
            {"$set": {"status": "open", "closed_at": None, "closed_by": None}}
        )

        # Log de auditoria da reabertura
        await current_db.hr_audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "item_id": competency_id,
            "employee_id": None,
            "school_payroll_id": None,
            "user_id": user.get('id'),
            "action": "reopen_competency",
            "changes": [{"field": "status", "old_value": "closed", "new_value": "open"}],
            "justification": justification,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {"message": "Competência reaberta com sucesso"}

    # ============================================
    # FOLHAS POR ESCOLA
    # ============================================

    @router.get("/school-payrolls")
    async def list_school_payrolls(
        request: Request,
        competency_id: Optional[str] = None,
        school_id: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Lista folhas de escola. Diretor/Secretário vê apenas da sua escola."""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        query = {}
        if competency_id:
            query['competency_id'] = competency_id
        if status:
            query['status'] = status

        # Restrição por escola para diretor/secretário
        is_global = user.get('role') in ADMIN_ROLES + SEMED_ROLES
        if not is_global:
            user_school_ids = user.get('school_ids', []) or []
            if user.get('school_links'):
                user_school_ids = [l.get('school_id') for l in user.get('school_links', [])]
            if school_id and school_id in user_school_ids:
                query['school_id'] = school_id
            elif user_school_ids:
                query['school_id'] = {'$in': user_school_ids}
            else:
                return []
        elif school_id:
            query['school_id'] = school_id

        payrolls = await current_db.school_payrolls.find(
            query, {"_id": 0}
        ).sort("school_id", 1).to_list(500)

        # Enriquecer com nome da escola e contadores
        school_ids = list(set(p['school_id'] for p in payrolls))
        schools_map = {}
        if school_ids:
            async for s in current_db.schools.find({"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}):
                schools_map[s['id']] = s['name']

        for p in payrolls:
            p['school_name'] = schools_map.get(p['school_id'], 'N/A')
            # Contadores rápidos
            item_count = await current_db.payroll_items.count_documents({"school_payroll_id": p['id']})
            pending_count = await current_db.payroll_items.count_documents({"school_payroll_id": p['id'], "validation_status": "has_issues"})
            p['total_employees'] = item_count
            p['pending_issues'] = pending_count

        return payrolls

    @router.get("/school-payrolls/{payroll_id}")
    async def get_school_payroll(payroll_id: str, request: Request):
        """Retorna detalhes de uma folha de escola"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        payroll = await current_db.school_payrolls.find_one({"id": payroll_id}, {"_id": 0})
        if not payroll:
            raise HTTPException(404, "Folha não encontrada")

        # Buscar itens (servidores)
        items = await current_db.payroll_items.find(
            {"school_payroll_id": payroll_id}, {"_id": 0}
        ).to_list(500)

        # Enriquecer com dados do servidor
        emp_ids = list(set(i['employee_id'] for i in items))
        emp_map = {}
        if emp_ids:
            async for staff in current_db.staff.find(
                {"id": {"$in": emp_ids}},
                {"_id": 0, "id": 1, "nome": 1, "matricula": 1, "cargo": 1, "tipo_vinculo": 1, "carga_horaria_semanal": 1, "status": 1}
            ):
                emp_map[staff['id']] = staff

        for item in items:
            emp = emp_map.get(item['employee_id'], {})
            item['employee_name'] = emp.get('nome', 'N/A')
            item['employee_matricula'] = emp.get('matricula', '')
            item['employee_cargo'] = emp.get('cargo', '')
            item['employee_vinculo'] = emp.get('tipo_vinculo', '')
            item['employee_ch_semanal'] = emp.get('carga_horaria_semanal', 0)
            item['employee_status'] = emp.get('status', '')

            # Contar ocorrências e documentos
            occ_count = await current_db.payroll_occurrences.count_documents({
                "payroll_item_id": item['id'], "status": "active"
            })
            doc_count = await current_db.payroll_occurrences.count_documents({
                "payroll_item_id": item['id'], "status": "active",
                "document_url": {"$ne": None, "$ne": ""}
            })
            item['occurrences_count'] = occ_count
            item['documents_count'] = doc_count

        # Ordenar por nome
        items.sort(key=lambda x: x.get('employee_name', ''))

        school = await current_db.schools.find_one({"id": payroll['school_id']}, {"_id": 0, "name": 1})
        payroll['school_name'] = school.get('name', 'N/A') if school else 'N/A'
        payroll['items'] = items
        return payroll

    # ============================================
    # FLUXO DE STATUS DA FOLHA
    # ============================================

    @router.put("/school-payrolls/{payroll_id}/submit")
    async def submit_payroll(payroll_id: str, request: Request):
        """Escola envia a folha para análise da Secretaria"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES + SCHOOL_ROLES)(request)
        current_db = get_db_for_user(user)

        payroll = await current_db.school_payrolls.find_one({"id": payroll_id})
        if not payroll:
            raise HTTPException(404, "Folha não encontrada")
        if payroll['status'] not in ('drafting', 'returned', 'not_started', 'reopened'):
            raise HTTPException(400, f"Folha não pode ser enviada no status '{payroll['status']}'")

        # Verificar se competência ainda está aberta
        comp = await current_db.payroll_competencies.find_one({"id": payroll['competency_id']})
        if comp and comp.get('status') == 'closed':
            raise HTTPException(400, "Competência já foi fechada. Não é possível enviar a folha.")

        # Verificar prazo de lançamento
        if comp and comp.get('launch_end'):
            from datetime import date
            try:
                limit = date.fromisoformat(comp['launch_end'])
                if date.today() > limit:
                    is_admin = user.get('role') in ADMIN_ROLES
                    if not is_admin:
                        raise HTTPException(400, f"Prazo de lançamento encerrado em {comp['launch_end']}. Solicite liberação à Secretaria.")
            except ValueError:
                pass

        # Validações rigorosas antes do envio
        warnings = []
        total_items = await current_db.payroll_items.count_documents({"school_payroll_id": payroll_id})
        items_issues = await current_db.payroll_items.count_documents({"school_payroll_id": payroll_id, "validation_status": "has_issues"})
        items_pending = await current_db.payroll_items.count_documents({"school_payroll_id": payroll_id, "validation_status": "pending"})

        # Servidores sem nenhum lançamento (horas = previsto, 0 ocorrências)
        items_no_movement = 0
        async for item in current_db.payroll_items.find({"school_payroll_id": payroll_id}, {"_id": 0, "id": 1, "expected_hours": 1, "worked_hours": 1}):
            occ_count = await current_db.payroll_occurrences.count_documents({"payroll_item_id": item['id'], "status": "active"})
            if occ_count == 0 and item.get('worked_hours', 0) == item.get('expected_hours', 0):
                items_no_movement += 1

        # Ocorrências sem documento
        occs_no_doc = await current_db.payroll_occurrences.count_documents({
            "school_payroll_id": payroll_id,
            "status": "active",
            "type": {"$in": ["atestado", "afastamento", "licenca"]},
            "$or": [{"document_url": None}, {"document_url": ""}]
        })

        if items_issues > 0:
            warnings.append(f"{items_issues} servidor(es) com pendências de validação")
        if items_pending > 0:
            warnings.append(f"{items_pending} servidor(es) ainda não conferido(s)")
        if items_no_movement > 0:
            warnings.append(f"{items_no_movement} servidor(es) sem nenhum lançamento/ocorrência")
        if occs_no_doc > 0:
            warnings.append(f"{occs_no_doc} ocorrência(s) (atestado/afastamento/licença) sem documento anexado")

        obs = '; '.join(warnings) if warnings else None
        await current_db.school_payrolls.update_one(
            {"id": payroll_id},
            {"$set": {
                "status": "submitted",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "submitted_by": user.get('id'),
                "observations": obs
            }}
        )
        return {"message": "Folha enviada para análise", "warnings": warnings}

    @router.put("/school-payrolls/{payroll_id}/approve")
    async def approve_payroll(payroll_id: str, request: Request):
        """Secretaria aprova a folha"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES + SEMED_ROLES)(request)
        current_db = get_db_for_user(user)

        payroll = await current_db.school_payrolls.find_one({"id": payroll_id})
        if not payroll:
            raise HTTPException(404, "Folha não encontrada")
        if payroll['status'] not in ('submitted', 'under_analysis'):
            raise HTTPException(400, "Folha precisa estar enviada para ser aprovada")

        await current_db.school_payrolls.update_one(
            {"id": payroll_id},
            {"$set": {
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "approved_by": user.get('id')
            }}
        )
        return {"message": "Folha aprovada"}

    @router.put("/school-payrolls/{payroll_id}/return")
    async def return_payroll(payroll_id: str, request: Request):
        """Secretaria devolve a folha para correção e notifica a escola"""
        user = await AuthMiddleware.require_roles(ADMIN_ROLES + SEMED_ROLES)(request)
        current_db = get_db_for_user(user)

        body = await request.json()
        reason = body.get('reason', '')

        payroll = await current_db.school_payrolls.find_one({"id": payroll_id})
        if not payroll:
            raise HTTPException(404, "Folha não encontrada")

        await current_db.school_payrolls.update_one(
            {"id": payroll_id},
            {"$set": {
                "status": "returned",
                "returned_at": datetime.now(timezone.utc).isoformat(),
                "returned_by": user.get('id'),
                "return_reason": reason
            }}
        )

        # Enviar notificação para diretor e secretário da escola
        sender_name = user.get('name', 'Secretaria de Educação')
        await _notify_school_return(current_db, payroll, reason, sender_name)

        return {"message": "Folha devolvida para correção. Notificação enviada à escola."}

    # ============================================
    # ITENS DA FOLHA (SERVIDORES)
    # ============================================

    @router.put("/payroll-items/{item_id}")
    async def update_payroll_item(item_id: str, data: PayrollItemUpdate, request: Request):
        """Atualiza dados de um servidor na folha"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        item = await current_db.payroll_items.find_one({"id": item_id})
        if not item:
            raise HTTPException(404, "Item não encontrado")

        # Verifica se a folha ainda permite edição
        payroll = await current_db.school_payrolls.find_one({"id": item['school_payroll_id']})
        if payroll and payroll['status'] in ('approved', 'closed'):
            if user.get('role') not in ADMIN_ROLES:
                raise HTTPException(403, "Folha já aprovada/fechada. Apenas administrador pode editar.")

        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if not update_data:
            return await current_db.payroll_items.find_one({"id": item_id}, {"_id": 0})

        # Registrar auditoria (antes de alterar)
        await _log_item_change(current_db, item, update_data, user)

        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        update_data['updated_by'] = user.get('id')

        # Marca folha como em rascunho se estava não iniciada
        if payroll and payroll['status'] == 'not_started':
            await current_db.school_payrolls.update_one(
                {"id": payroll['id']},
                {"$set": {"status": "drafting"}}
            )

        # Validações automáticas
        merged = {**item, **update_data}
        alerts = _validate_item(merged)
        if alerts:
            update_data['validation_status'] = 'has_issues'
            update_data['validation_notes'] = '; '.join(alerts)
        else:
            update_data['validation_status'] = 'ok'
            update_data['validation_notes'] = None

        await current_db.payroll_items.update_one(
            {"id": item_id},
            {"$set": update_data}
        )

        return await current_db.payroll_items.find_one({"id": item_id}, {"_id": 0})

    @router.get("/payroll-items/{item_id}/history")
    async def get_item_history(item_id: str, request: Request):
        """Retorna histórico de alterações de um item"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        logs = await current_db.hr_audit_logs.find(
            {"item_id": item_id}, {"_id": 0}
        ).sort("timestamp", -1).to_list(100)

        # Enriquecer com nome do usuário
        user_ids = list(set(l.get('user_id', '') for l in logs if l.get('user_id')))
        users_map = {}
        if user_ids:
            async for u in current_db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}):
                users_map[u['id']] = u.get('name', 'N/A')

        for log in logs:
            log['user_name'] = users_map.get(log.get('user_id', ''), 'Sistema')

        return logs

    # ============================================
    # OCORRÊNCIAS
    # ============================================

    @router.get("/occurrences")
    async def list_occurrences(
        request: Request,
        payroll_item_id: Optional[str] = None,
        school_payroll_id: Optional[str] = None
    ):
        """Lista ocorrências de um item ou folha"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        query = {"status": "active"}
        if payroll_item_id:
            query['payroll_item_id'] = payroll_item_id
        if school_payroll_id:
            query['school_payroll_id'] = school_payroll_id

        items = await current_db.payroll_occurrences.find(query, {"_id": 0}).to_list(500)

        # Enriquecer nomes de substituídos
        emp_ids = set()
        for occ in items:
            if occ.get('substituted_employee_id'):
                emp_ids.add(occ['substituted_employee_id'])
            if occ.get('substitute_employee_id'):
                emp_ids.add(occ['substitute_employee_id'])

        emp_map = {}
        if emp_ids:
            async for s in current_db.staff.find({"id": {"$in": list(emp_ids)}}, {"_id": 0, "id": 1, "nome": 1}):
                emp_map[s['id']] = s.get('nome', 'N/A')

        for occ in items:
            if occ.get('substituted_employee_id'):
                occ['substituted_name'] = emp_map.get(occ['substituted_employee_id'], 'N/A')
            if occ.get('substitute_employee_id'):
                occ['substitute_name'] = emp_map.get(occ['substitute_employee_id'], 'N/A')

        return items

    @router.post("/occurrences")
    async def create_occurrence(data: PayrollOccurrenceCreate, request: Request):
        """Registra uma ocorrência para um servidor"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        item = await current_db.payroll_items.find_one({"id": data.payroll_item_id})
        if not item:
            raise HTTPException(404, "Item da folha não encontrado")

        # Validação: hora complementar precisa de motivo
        if data.type == 'hora_complementar' and not data.reason:
            raise HTTPException(400, "Hora complementar exige motivo/justificativa")

        # Validação: substituição precisa de servidor substituído
        if data.type == 'substituicao' and not data.substituted_employee_id:
            raise HTTPException(400, "Substituição exige indicar o servidor substituído")

        # Validação: não duplicar substituição no mesmo período
        if data.type == 'substituicao' and data.substituted_employee_id:
            existing_sub = await current_db.payroll_occurrences.find_one({
                "school_payroll_id": item['school_payroll_id'],
                "type": "substituicao",
                "substituted_employee_id": data.substituted_employee_id,
                "start_date": data.start_date,
                "status": "active"
            })
            if existing_sub:
                raise HTTPException(400, "Já existe substituição ativa para este servidor nesta data")

        # Validação: atestado/afastamento conflitando com presença
        if data.type in ('atestado', 'afastamento', 'licenca'):
            conflict = await current_db.payroll_occurrences.find_one({
                "payroll_item_id": data.payroll_item_id,
                "type": {"$nin": ['atestado', 'afastamento', 'licenca', 'hora_complementar']},
                "start_date": {"$lte": data.end_date or data.start_date},
                "end_date": {"$gte": data.start_date},
                "status": "active"
            })
            if conflict:
                logger.warning(f"Possível conflito de datas: {data.type} vs {conflict.get('type')} para item {data.payroll_item_id}")

        occ = PayrollOccurrence(
            payroll_item_id=data.payroll_item_id,
            school_payroll_id=item['school_payroll_id'],
            employee_id=item['employee_id'],
            type=data.type,
            subtype=data.subtype,
            start_date=data.start_date,
            end_date=data.end_date or data.start_date,
            days=data.days,
            hours=data.hours,
            reason=data.reason,
            justification=data.justification,
            document_url=data.document_url,
            document_number=data.document_number,
            substituted_employee_id=data.substituted_employee_id,
            substitute_employee_id=data.substitute_employee_id,
            created_by=user.get('id')
        )
        doc = occ.model_dump()
        await current_db.payroll_occurrences.insert_one(doc)

        # Atualiza contadores no item
        await _recalc_item_from_occurrences(current_db, data.payroll_item_id)

        # Marca folha como em rascunho
        payroll = await current_db.school_payrolls.find_one({"id": item['school_payroll_id']})
        if payroll and payroll['status'] == 'not_started':
            await current_db.school_payrolls.update_one(
                {"id": payroll['id']},
                {"$set": {"status": "drafting"}}
            )

        return await current_db.payroll_occurrences.find_one({"id": occ.id}, {"_id": 0})

    @router.put("/occurrences/{occurrence_id}")
    async def update_occurrence(occurrence_id: str, data: PayrollOccurrenceUpdate, request: Request):
        """Atualiza uma ocorrência"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        occ = await current_db.payroll_occurrences.find_one({"id": occurrence_id})
        if not occ:
            raise HTTPException(404, "Ocorrência não encontrada")

        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            await current_db.payroll_occurrences.update_one(
                {"id": occurrence_id},
                {"$set": update_data}
            )
            await _recalc_item_from_occurrences(current_db, occ['payroll_item_id'])

        return await current_db.payroll_occurrences.find_one({"id": occurrence_id}, {"_id": 0})

    @router.delete("/occurrences/{occurrence_id}")
    async def cancel_occurrence(occurrence_id: str, request: Request):
        """Cancela uma ocorrência (soft delete)"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        occ = await current_db.payroll_occurrences.find_one({"id": occurrence_id})
        if not occ:
            raise HTTPException(404, "Ocorrência não encontrada")

        await current_db.payroll_occurrences.update_one(
            {"id": occurrence_id},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        await _recalc_item_from_occurrences(current_db, occ['payroll_item_id'])
        return {"message": "Ocorrência cancelada"}

    # ============================================
    # SERVIDORES DA ESCOLA (para seletor de substituição)
    # ============================================

    @router.get("/school-employees/{school_payroll_id}")
    async def list_school_employees(school_payroll_id: str, request: Request):
        """Lista servidores de uma folha (para seletor de substituição)"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        items = await current_db.payroll_items.find(
            {"school_payroll_id": school_payroll_id},
            {"_id": 0, "id": 1, "employee_id": 1}
        ).to_list(500)

        emp_ids = [i['employee_id'] for i in items]
        employees = []
        if emp_ids:
            async for s in current_db.staff.find(
                {"id": {"$in": emp_ids}},
                {"_id": 0, "id": 1, "nome": 1, "matricula": 1, "cargo": 1}
            ):
                employees.append(s)

        employees.sort(key=lambda x: x.get('nome', ''))
        return employees

    # ============================================
    # DASHBOARD / RESUMO
    # ============================================

    @router.get("/dashboard")
    async def hr_dashboard(
        request: Request,
        competency_id: Optional[str] = None,
        year: Optional[int] = None,
        month: Optional[int] = None
    ):
        """Dashboard do módulo RH"""
        user = await AuthMiddleware.require_roles(ALL_HR_ROLES)(request)
        current_db = get_db_for_user(user)

        comp_query = {}
        if competency_id:
            comp_query['id'] = competency_id
        elif year and month:
            comp_query['year'] = year
            comp_query['month'] = month

        comp = await current_db.payroll_competencies.find_one(
            comp_query, {"_id": 0},
            sort=[("year", -1), ("month", -1)]
        )

        if not comp:
            return {
                "competency": None,
                "summary": {"total_schools": 0},
                "payrolls_by_status": {}
            }

        pipeline = [
            {"$match": {"competency_id": comp['id']}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_counts = {}
        async for doc in current_db.school_payrolls.aggregate(pipeline):
            status_counts[doc['_id']] = doc['count']

        total_schools = sum(status_counts.values())
        total_employees = await current_db.payroll_items.count_documents({"competency_id": comp['id']})
        total_issues = await current_db.payroll_items.count_documents({
            "competency_id": comp['id'], "validation_status": "has_issues"
        })
        total_occurrences = await current_db.payroll_occurrences.count_documents({
            "school_payroll_id": {"$in": [p['id'] async for p in current_db.school_payrolls.find({"competency_id": comp['id']}, {"id": 1})]},
            "status": "active"
        })

        return {
            "competency": comp,
            "summary": {
                "total_schools": total_schools,
                "total_employees": total_employees,
                "total_issues": total_issues,
                "total_occurrences": total_occurrences
            },
            "payrolls_by_status": status_counts
        }

    # ============================================
    # FUNÇÕES AUXILIARES
    # ============================================

    async def _generate_pre_payroll(current_db, competency: PayrollCompetency):
        """Gera pré-folha automática para todas as escolas"""
        schools = await current_db.schools.find(
            {"status": "active"}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)

        for school in schools:
            school_id = school['id']

            existing = await current_db.school_payrolls.find_one({
                "competency_id": competency.id,
                "school_id": school_id
            })
            if existing:
                continue

            payroll = SchoolPayroll(
                competency_id=competency.id,
                school_id=school_id,
                year=competency.year,
                month=competency.month
            )
            await current_db.school_payrolls.insert_one(payroll.model_dump())

            assignments = await current_db.school_assignments.find(
                {"school_id": school_id, "status": "ativo"},
                {"_id": 0}
            ).to_list(500)

            seen_employees = set()
            for assign in assignments:
                emp_id = assign.get('staff_id')
                if not emp_id or emp_id in seen_employees:
                    continue
                seen_employees.add(emp_id)

                staff = await current_db.staff.find_one(
                    {"id": emp_id}, {"_id": 0, "carga_horaria_semanal": 1, "cargo": 1, "status": 1}
                )
                if not staff:
                    continue
                if staff.get('status') in ('exonerado', 'aposentado'):
                    continue

                ch_semanal = staff.get('carga_horaria_semanal') or 0
                ch_mensal = round(ch_semanal * 4.33, 1)
                is_professor = staff.get('cargo') == 'professor'
                carga_aulas = int(assign.get('carga_horaria') or 0)

                item = PayrollItem(
                    school_payroll_id=payroll.id,
                    competency_id=competency.id,
                    school_id=school_id,
                    employee_id=emp_id,
                    assignment_id=assign.get('id'),
                    year=competency.year,
                    month=competency.month,
                    expected_hours=ch_mensal,
                    worked_hours=ch_mensal,
                    expected_classes=carga_aulas if is_professor else 0,
                    taught_classes=carga_aulas if is_professor else 0,
                )
                await current_db.payroll_items.insert_one(item.model_dump())

        logger.info(f"Pré-folha gerada para competência {competency.month:02d}/{competency.year}: {len(schools)} escolas")

    def _validate_item(item: dict) -> list:
        """Validações automáticas de um item da folha"""
        alerts = []
        expected = item.get('expected_hours', 0) or 0
        worked = item.get('worked_hours', 0) or 0
        complementary = item.get('complementary_hours', 0) or 0
        absences = item.get('absences', 0) or 0
        medical = item.get('medical_leave_days', 0) or 0
        leave = item.get('leave_days', 0) or 0
        taught = item.get('taught_classes', 0) or 0
        expected_c = item.get('expected_classes', 0) or 0
        not_taught = item.get('classes_not_taught', 0) or 0

        if worked > expected * 1.2 and expected > 0:
            alerts.append(f"Horas trabalhadas ({worked}h) excedem 120% da carga prevista ({expected}h)")

        if complementary > 0 and not item.get('complementary_reason'):
            alerts.append("Horas complementares sem motivo informado")

        total_ausencia = absences + medical + leave
        if total_ausencia > 22:
            alerts.append(f"Total de ausências ({total_ausencia} dias) excede dias úteis do mês")

        # Aulas não cumpridas sem justificativa (sem ocorrências de falta/atestado)
        if not_taught > 0 and absences == 0 and medical == 0 and leave == 0:
            alerts.append(f"{not_taught} aula(s) não cumprida(s) sem ocorrência de falta/atestado registrada")

        # Aulas ministradas + não cumpridas != previstas
        if expected_c > 0 and (taught + not_taught) > expected_c:
            alerts.append(f"Aulas ministradas ({taught}) + não cumpridas ({not_taught}) excedem as previstas ({expected_c})")

        return alerts

    async def _recalc_item_from_occurrences(current_db, payroll_item_id: str):
        """Recalcula totalizadores do item com base nas ocorrências ativas"""
        occurrences = await current_db.payroll_occurrences.find(
            {"payroll_item_id": payroll_item_id, "status": "active"},
            {"_id": 0}
        ).to_list(200)

        totals = {
            'absences': 0,
            'justified_absences': 0,
            'medical_leave_days': 0,
            'leave_days': 0,
            'complementary_hours': 0,
            'extra_classes': 0,
        }

        for occ in occurrences:
            t = occ.get('type', '')
            days = occ.get('days', 0) or 0
            hours = occ.get('hours', 0) or 0

            if t == 'falta':
                totals['absences'] += days
            elif t == 'falta_justificada':
                totals['justified_absences'] += days
            elif t == 'atestado':
                totals['medical_leave_days'] += days
            elif t in ('afastamento', 'licenca'):
                totals['leave_days'] += days
            elif t == 'hora_complementar':
                totals['complementary_hours'] += hours
            elif t == 'substituicao':
                totals['extra_classes'] += days

        item = await current_db.payroll_items.find_one({"id": payroll_item_id})
        if item:
            merged = {**item, **totals}
            alerts = _validate_item(merged)
            totals['validation_status'] = 'has_issues' if alerts else 'ok'
            totals['validation_notes'] = '; '.join(alerts) if alerts else None

        totals['updated_at'] = datetime.now(timezone.utc).isoformat()
        await current_db.payroll_items.update_one(
            {"id": payroll_item_id},
            {"$set": totals}
        )

    async def _log_item_change(current_db, old_item: dict, changes: dict, user: dict):
        """Registra alteração em um item para auditoria"""
        changed_fields = []
        for key, new_val in changes.items():
            old_val = old_item.get(key)
            if old_val != new_val and key not in ('updated_at', 'updated_by', 'validation_status', 'validation_notes'):
                changed_fields.append({
                    "field": key,
                    "old_value": str(old_val) if old_val is not None else None,
                    "new_value": str(new_val) if new_val is not None else None,
                })

        if changed_fields:
            log_entry = {
                "id": str(uuid.uuid4()),
                "item_id": old_item.get('id'),
                "employee_id": old_item.get('employee_id'),
                "school_payroll_id": old_item.get('school_payroll_id'),
                "user_id": user.get('id'),
                "action": "update",
                "changes": changed_fields,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await current_db.hr_audit_logs.insert_one(log_entry)
