"""
Router para endpoints administrativos.
Extraído de server.py durante a refatoração modular.
"""

from fastapi import APIRouter, HTTPException, status, Request

from auth_middleware import AuthMiddleware

router = APIRouter(tags=["Admin"])


def setup_router(db, active_sessions=None, connection_manager=None, get_db_for_user=None, **kwargs):
    """Configura o router com dependências."""

    @router.post("/admin/migrate-uppercase")
    async def migrate_to_uppercase(request: Request):
        """Converte todos os campos de texto para CAIXA ALTA no banco de dados."""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste'])(request)

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
            'enrollments': ['student_name', 'class_name', 'school_name']
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
        """Retorna lista de usuários online (apenas admin e semed3)"""
        current_user = await AuthMiddleware.require_roles(['admin', 'admin_teste', 'semed3'])(request)
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

        result.sort(key=lambda x: x['full_name'])
        return result

    return router
