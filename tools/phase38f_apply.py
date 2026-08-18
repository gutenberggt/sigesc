from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 match, encontrado {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Backend: legacy /learning-objects recebe guard anti-bypass e PDF passa a usar
# content_entries visíveis ao professor quando o DVD está ativo.
# ---------------------------------------------------------------------------
path = Path("backend/routers/learning_objects.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create\n",
    "from tenant_scope import (\n"
    "    apply_tenant_filter, assert_same_tenant, resolve_tenant_id_for_create,\n"
    "    get_mantenedora_scope,\n"
    ")\n"
    "from services.content_assignment_scope import filter_visible_content_entries\n"
    "from services.legacy_content_dvd_guard import (\n"
    "    legacy_content_block_detail, professor_has_active_dvd_content,\n"
    ")\n",
    "backend imports",
)

needle = "    check_academic_year_open = kwargs.get('check_academic_year_open')\n\n"
insert = needle + "    async def _block_legacy_if_dvd(current_user, class_id, course_id=None):\n" \
    "        if await professor_has_active_dvd_content(\n" \
    "            db, current_user, class_id=class_id, course_id=course_id\n" \
    "        ):\n" \
    "            raise HTTPException(status_code=409, detail=legacy_content_block_detail())\n\n"
text = replace_once(text, needle, insert, "backend helper")

# LIST
needle = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)\n\n        query = {}\n"
replace = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)\n\n        await _block_legacy_if_dvd(current_user, class_id, course_id)\n\n        query = {}\n"
text = replace_once(text, needle, replace, "list guard")

# GET individual
needle = "        obj = await db.learning_objects.find_one({\"id\": object_id}, {\"_id\": 0})\n        if not obj:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        return obj\n"
replace = "        obj = await db.learning_objects.find_one({\"id\": object_id}, {\"_id\": 0})\n        if not obj:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        await _block_legacy_if_dvd(current_user, obj.get('class_id'), obj.get('course_id'))\n        return obj\n"
text = replace_once(text, needle, replace, "get guard")

# CREATE
needle = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor'])(request)\n        user_role = current_user.get('role', '')\n\n        # Verifica se o ano letivo está aberto"
replace = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor'])(request)\n        user_role = current_user.get('role', '')\n\n        await _block_legacy_if_dvd(current_user, data.class_id, data.course_id)\n\n        # Verifica se o ano letivo está aberto"
text = replace_once(text, needle, replace, "create guard")

# UPDATE
needle = "        existing = await db.learning_objects.find_one({\"id\": object_id})\n        if not existing:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        # Verifica a data limite de edição"
replace = "        existing = await db.learning_objects.find_one({\"id\": object_id})\n        if not existing:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        await _block_legacy_if_dvd(current_user, existing.get('class_id'), existing.get('course_id'))\n\n        # Verifica a data limite de edição"
text = replace_once(text, needle, replace, "update guard")

# DELETE
needle = "        existing = await db.learning_objects.find_one({\"id\": object_id})\n        if not existing:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        await db.learning_objects.delete_one({\"id\": object_id})\n"
replace = "        existing = await db.learning_objects.find_one({\"id\": object_id})\n        if not existing:\n            raise HTTPException(status_code=404, detail=\"Registro não encontrado\")\n\n        await _block_legacy_if_dvd(current_user, existing.get('class_id'), existing.get('course_id'))\n        await db.learning_objects.delete_one({\"id\": object_id})\n"
text = replace_once(text, needle, replace, "delete guard")

# COPY source
needle = "        original = await db.learning_objects.find_one({\"id\": object_id}, {\"_id\": 0})\n        if not original:\n            raise HTTPException(status_code=404, detail=\"Registro original não encontrado\")\n\n        try:\n"
replace = "        original = await db.learning_objects.find_one({\"id\": object_id}, {\"_id\": 0})\n        if not original:\n            raise HTTPException(status_code=404, detail=\"Registro original não encontrado\")\n\n        await _block_legacy_if_dvd(current_user, original.get('class_id'), original.get('course_id'))\n\n        try:\n"
text = replace_once(text, needle, replace, "copy guard")

# CHECK DATE
needle = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)\n\n        existing = await db.learning_objects.find_one({\n            \"class_id\": class_id,\n"
replace = "        current_user = await AuthMiddleware.require_roles(['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3'])(request)\n\n        await _block_legacy_if_dvd(current_user, class_id, course_id)\n\n        existing = await db.learning_objects.find_one({\n            \"class_id\": class_id,\n"
text = replace_once(text, needle, replace, "check-date guard")

# PDF current user
text = replace_once(
    text,
    "        await AuthMiddleware.get_current_user(request)\n\n        if not academic_year:\n",
    "        current_user = await AuthMiddleware.get_current_user(request)\n\n        if not academic_year:\n",
    "pdf current user",
)

# PDF record source
needle = "        # Buscar registros do bimestre\n        query = {\n            \"class_id\": class_id,\n            \"academic_year\": academic_year,\n            \"date\": {\"$gte\": period_start, \"$lte\": period_end}\n        }\n        if course_id:\n            query[\"course_id\"] = course_id\n\n        records = await db.learning_objects.find(query, {\"_id\": 0}).sort(\"date\", 1).to_list(1000)\n"
replace = "        # Buscar registros do bimestre. Professor com DVD ativo usa exclusivamente\n        # content_entries e passa pelo filtro canônico de visibilidade/autoria.\n        dvd_mode = await professor_has_active_dvd_content(\n            db, current_user, class_id=class_id, course_id=course_id\n        )\n        if dvd_mode:\n            query = {\n                \"class_id\": class_id,\n                \"academic_year\": academic_year,\n                \"date\": {\"$gte\": period_start, \"$lte\": period_end},\n                \"deleted\": False,\n            }\n            if course_id:\n                query[\"component_id\"] = course_id\n            candidates = await db.content_entries.find(\n                query, {\"_id\": 0}\n            ).sort(\"date\", 1).to_list(2000)\n            records = await filter_visible_content_entries(\n                db, current_user, candidates,\n                active_mantenedora_id=get_mantenedora_scope(current_user, request),\n            )\n            for record in records:\n                record[\"course_id\"] = record.get(\"course_id\") or record.get(\"component_id\")\n        else:\n            query = {\n                \"class_id\": class_id,\n                \"academic_year\": academic_year,\n                \"date\": {\"$gte\": period_start, \"$lte\": period_end}\n            }\n            if course_id:\n                query[\"course_id\"] = course_id\n            records = await db.learning_objects.find(\n                query, {\"_id\": 0}\n            ).sort(\"date\", 1).to_list(1000)\n"
text = replace_once(text, needle, replace, "pdf records")

# PDF teacher label override after legacy resolution.
needle = "        if teacher_assignment:\n            teacher = await db.staff.find_one(\n                {\"id\": teacher_assignment['staff_id']},\n                {\"_id\": 0, \"nome\": 1}\n            )\n            if teacher:\n                teacher_name = teacher.get('nome', '')\n\n        # Calcular dias previstos"
replace = "        if teacher_assignment:\n            teacher = await db.staff.find_one(\n                {\"id\": teacher_assignment['staff_id']},\n                {\"_id\": 0, \"nome\": 1}\n            )\n            if teacher:\n                teacher_name = teacher.get('nome', '')\n        if dvd_mode:\n            teacher_name = next(\n                (r.get('teacher_name') for r in records if r.get('teacher_name')),\n                current_user.get('full_name') or current_user.get('name') or '',\n            )\n\n        # Calcular dias previstos"
text = replace_once(text, needle, replace, "pdf teacher")

text = replace_once(
    text,
    "            teacher_names = await get_multi_teacher_names_for_pdf(db, turma, academic_year)\n",
    "            teacher_names = (\n"
    "                [teacher_name] if dvd_mode and teacher_name\n"
    "                else await get_multi_teacher_names_for_pdf(db, turma, academic_year)\n"
    "            )\n",
    "pdf teacher names",
)

path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Frontend: habilita o botão Conteúdos no card DVD agora que o motor canônico
# é selecionado pelo contentDvdBridge.
# ---------------------------------------------------------------------------
path = Path("frontend/src/components/professor/MyDiariesSection.jsx")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "                        ? 'Disponível neste perfil; a abertura pelo vínculo aguarda a harmonização do módulo atual.'\n",
    "                        ? 'Operacional por vínculo docente; cada professor acessa seus próprios registros.'\n",
    "capability text",
)

old = """                    {caps.content_enabled && (\n                      <Button\n                        type=\"button\"\n                        size=\"sm\"\n                        variant=\"outline\"\n                        disabled\n                        title=\"Conteúdos por vínculo será habilitado após a harmonização com content_entries.\"\n                        data-testid={`open-content-disabled-${diary.assignment_id}`}\n                      >\n                        <BookOpen size={16} className=\"mr-2\" />\n                        Conteúdos\n                      </Button>\n                    )}\n"""
new = """                    {caps.content_enabled && (\n                      <Button\n                        type=\"button\"\n                        size=\"sm\"\n                        variant=\"outline\"\n                        onClick={() => navigate(buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext))}\n                        data-testid={`open-content-${diary.assignment_id}`}\n                      >\n                        <BookOpen size={16} className=\"mr-2\" />\n                        Conteúdos\n                      </Button>\n                    )}\n"""
text = replace_once(text, old, new, "content button")

text = replace_once(
    text,
    "                    Frequência e Notas/Conceitos abrem com o vínculo, a turma e o componente já definidos. Conteúdos permanece bloqueado no DVD até a harmonização com o backend canônico.\n",
    "                    Frequência, Notas/Conceitos e Conteúdos abrem com o vínculo, a turma e o componente já definidos.\n",
    "card footnote",
)

path.write_text(text, encoding="utf-8")

print("PHASE38F_PATCH_OK")
