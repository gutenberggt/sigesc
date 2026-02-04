"""
Router de Calendário - SIGESC
PATCH 4.x: Rotas de calendário extraídas do server.py

Endpoints para gestão do calendário letivo incluindo:
- CRUD de eventos (feriados, sábados letivos, recessos)
- Configuração de períodos bimestrais
- Cálculo automático de dias letivos
- Verificação de datas
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid

from models import CalendarEventCreate, CalendarEventUpdate
from auth_middleware import AuthMiddleware

router = APIRouter(tags=["Calendário"])

# Cores padrão para tipos de eventos
EVENT_COLORS = {
    'feriado_nacional': '#DC2626',  # Vermelho
    'feriado_estadual': '#EA580C',  # Laranja
    'feriado_municipal': '#F59E0B',  # Amarelo
    'recesso_escolar': '#8B5CF6',   # Roxo
    'sabado_letivo': '#10B981',     # Verde
    'evento_escolar': '#3B82F6',    # Azul
    'reuniao_pedagogica': '#6366F1', # Indigo
    'conselho_classe': '#EC4899',   # Rosa
    'outros': '#6B7280'             # Cinza
}


def setup_calendar_router(db, audit_service, sandbox_db=None):
    """Configura o router de calendário com as dependências necessárias"""
    
    def get_db_for_user(user: dict):
        """Retorna o banco correto baseado no usuário"""
        if False:  # Sandbox desabilitado
            return sandbox_db
        return db

    @router.get("/calendar/events")
    async def list_calendar_events(
        request: Request,
        academic_year: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        event_type: Optional[str] = None
    ):
        """Lista eventos do calendário com filtros opcionais"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        query = {}
        
        if academic_year:
            query["academic_year"] = academic_year
        
        if start_date and end_date:
            query["$or"] = [
                {"start_date": {"$gte": start_date, "$lte": end_date}},
                {"end_date": {"$gte": start_date, "$lte": end_date}},
                {"$and": [{"start_date": {"$lte": start_date}}, {"end_date": {"$gte": end_date}}]}
            ]
        elif start_date:
            query["end_date"] = {"$gte": start_date}
        elif end_date:
            query["start_date"] = {"$lte": end_date}
        
        if event_type:
            query["event_type"] = event_type
        
        events = await current_db.calendar_events.find(query, {"_id": 0}).sort("start_date", 1).to_list(1000)
        return events

    @router.get("/calendar/events/{event_id}")
    async def get_calendar_event(event_id: str, request: Request):
        """Obtém um evento específico"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        event = await current_db.calendar_events.find_one({"id": event_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        return event

    @router.post("/calendar/events", status_code=status.HTTP_201_CREATED)
    async def create_calendar_event(event: CalendarEventCreate, request: Request):
        """Cria um novo evento no calendário"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        event_dict = event.model_dump()
        if not event_dict.get('color'):
            event_dict['color'] = EVENT_COLORS.get(event_dict['event_type'], '#6B7280')
        
        new_event = {
            "id": str(uuid.uuid4()),
            **event_dict,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await current_db.calendar_events.insert_one(new_event)
        
        await audit_service.log(
            action='create',
            collection='calendar_events',
            user=current_user,
            request=request,
            document_id=new_event['id'],
            description=f"Criou evento: {new_event.get('title')} ({new_event.get('event_type')})"
        )
        
        return await current_db.calendar_events.find_one({"id": new_event["id"]}, {"_id": 0})

    @router.put("/calendar/events/{event_id}")
    async def update_calendar_event(event_id: str, event: CalendarEventUpdate, request: Request):
        """Atualiza um evento existente"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.calendar_events.find_one({"id": event_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        
        update_data = {k: v for k, v in event.model_dump().items() if v is not None}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await current_db.calendar_events.update_one({"id": event_id}, {"$set": update_data})
        
        await audit_service.log(
            action='update',
            collection='calendar_events',
            user=current_user,
            request=request,
            document_id=event_id,
            description=f"Atualizou evento: {existing.get('title')}"
        )
        
        return await current_db.calendar_events.find_one({"id": event_id}, {"_id": 0})

    @router.delete("/calendar/events/{event_id}")
    async def delete_calendar_event(event_id: str, request: Request):
        """Remove um evento do calendário"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        existing = await current_db.calendar_events.find_one({"id": event_id}, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        
        await current_db.calendar_events.delete_one({"id": event_id})
        
        await audit_service.log(
            action='delete',
            collection='calendar_events',
            user=current_user,
            request=request,
            document_id=event_id,
            description=f"EXCLUIU evento: {existing.get('title')}"
        )
        
        return {"message": "Evento removido com sucesso"}

    @router.get("/calendar/check-date/{date}")
    async def check_calendar_date(date: str, request: Request):
        """Verifica se uma data específica é dia letivo"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        events = await current_db.calendar_events.find({
            "start_date": {"$lte": date},
            "end_date": {"$gte": date}
        }, {"_id": 0}).to_list(100)
        
        is_school_day = True
        blocking_events = []
        enabling_events = []
        
        for event in events:
            if event.get('is_school_day'):
                enabling_events.append(event)
            else:
                blocking_events.append(event)
                is_school_day = False
        
        for event in enabling_events:
            if event.get('event_type') == 'sabado_letivo':
                is_school_day = True
                break
        
        return {
            "date": date,
            "is_school_day": is_school_day,
            "events": events,
            "blocking_events": blocking_events,
            "enabling_events": enabling_events
        }

    @router.get("/calendar/summary/{academic_year}")
    async def get_calendar_summary(academic_year: int, request: Request):
        """Retorna resumo do calendário letivo para um ano"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        events = await current_db.calendar_events.find(
            {"academic_year": academic_year}, 
            {"_id": 0}
        ).to_list(1000)
        
        summary = {
            "academic_year": academic_year,
            "total_events": len(events),
            "by_type": {},
            "school_days_added": 0,
            "non_school_days": 0
        }
        
        for event in events:
            event_type = event.get('event_type', 'outros')
            if event_type not in summary["by_type"]:
                summary["by_type"][event_type] = 0
            summary["by_type"][event_type] += 1
            
            if event.get('is_school_day'):
                summary["school_days_added"] += 1
            else:
                summary["non_school_days"] += 1
        
        return summary

    @router.get("/calendario-letivo/{ano_letivo}")
    async def get_calendario_letivo(ano_letivo: int, request: Request, school_id: Optional[str] = None):
        """Obtém a configuração do calendário letivo com os períodos bimestrais"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        query = {"ano_letivo": ano_letivo}
        if school_id:
            query["school_id"] = school_id
        else:
            query["school_id"] = None
        
        calendario = await current_db.calendario_letivo.find_one(query, {"_id": 0})
        
        if not calendario:
            return {
                "ano_letivo": ano_letivo,
                "school_id": school_id,
                "bimestre_1_inicio": None,
                "bimestre_1_fim": None,
                "bimestre_2_inicio": None,
                "bimestre_2_fim": None,
                "bimestre_3_inicio": None,
                "bimestre_3_fim": None,
                "bimestre_4_inicio": None,
                "bimestre_4_fim": None,
                "recesso_inicio": None,
                "recesso_fim": None,
                "dias_letivos_previstos": 200
            }
        
        return calendario

    @router.get("/calendario-letivo/{ano_letivo}/dias-letivos")
    async def calcular_dias_letivos(ano_letivo: int, request: Request, school_id: Optional[str] = None):
        """Calcula automaticamente os dias letivos de cada bimestre"""
        current_user = await AuthMiddleware.get_current_user(request)
        current_db = get_db_for_user(current_user)
        
        query = {"ano_letivo": ano_letivo}
        if school_id:
            query["school_id"] = school_id
        else:
            query["school_id"] = None
        
        calendario = await current_db.calendario_letivo.find_one(query, {"_id": 0})
        
        if not calendario:
            return {
                "bimestre_1_dias_letivos": 0,
                "bimestre_2_dias_letivos": 0,
                "bimestre_3_dias_letivos": 0,
                "bimestre_4_dias_letivos": 0,
                "total_dias_letivos": 0
            }
        
        events = await current_db.calendar_events.find({
            "academic_year": ano_letivo
        }, {"_id": 0}).to_list(1000)
        
        eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
        
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
        
        def calcular_dias_letivos_periodo(inicio_str, fim_str):
            """Calcula dias letivos entre duas datas"""
            if not inicio_str or not fim_str:
                return 0
            
            try:
                inicio = datetime.strptime(inicio_str[:10], '%Y-%m-%d').date()
                fim = datetime.strptime(fim_str[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return 0
            
            dias_letivos = 0
            current = inicio
            
            while current <= fim:
                dia_semana = current.weekday()
                
                if current in datas_sabados_letivos:
                    dias_letivos += 1
                elif dia_semana < 5:  # Seg-Sex
                    if current not in datas_nao_letivas:
                        dias_letivos += 1
                
                current += timedelta(days=1)
            
            return dias_letivos
        
        bim1 = calcular_dias_letivos_periodo(
            calendario.get('bimestre_1_inicio'),
            calendario.get('bimestre_1_fim')
        )
        bim2 = calcular_dias_letivos_periodo(
            calendario.get('bimestre_2_inicio'),
            calendario.get('bimestre_2_fim')
        )
        bim3 = calcular_dias_letivos_periodo(
            calendario.get('bimestre_3_inicio'),
            calendario.get('bimestre_3_fim')
        )
        bim4 = calcular_dias_letivos_periodo(
            calendario.get('bimestre_4_inicio'),
            calendario.get('bimestre_4_fim')
        )
        
        return {
            "bimestre_1_dias_letivos": bim1,
            "bimestre_2_dias_letivos": bim2,
            "bimestre_3_dias_letivos": bim3,
            "bimestre_4_dias_letivos": bim4,
            "total_dias_letivos": bim1 + bim2 + bim3 + bim4,
            "sabados_letivos": len(datas_sabados_letivos),
            "feriados_recessos": len(datas_nao_letivas)
        }

    @router.put("/calendario-letivo/{ano_letivo}")
    async def update_calendario_letivo(ano_letivo: int, request: Request):
        """Atualiza a configuração do calendário letivo"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'secretario'])(request)
        current_db = get_db_for_user(current_user)
        
        body = await request.json()
        school_id = body.get('school_id')
        
        query = {"ano_letivo": ano_letivo}
        if school_id:
            query["school_id"] = school_id
        else:
            query["school_id"] = None
        
        existing = await current_db.calendario_letivo.find_one(query)
        
        update_data = {k: v for k, v in body.items() if k != 'id' and k != '_id'}
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        update_data['updated_by'] = current_user['id']
        
        if existing:
            await current_db.calendario_letivo.update_one(query, {"$set": update_data})
        else:
            update_data['id'] = str(uuid.uuid4())
            update_data['ano_letivo'] = ano_letivo
            update_data['school_id'] = school_id
            update_data['created_at'] = datetime.now(timezone.utc).isoformat()
            await current_db.calendario_letivo.insert_one(update_data)
        
        await audit_service.log(
            action='update' if existing else 'create',
            collection='calendario_letivo',
            user=current_user,
            request=request,
            description=f"{'Atualizou' if existing else 'Criou'} calendário letivo {ano_letivo}"
        )
        
        return await current_db.calendario_letivo.find_one(query, {"_id": 0})

    return router
