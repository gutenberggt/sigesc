from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1 match, encontrado {count}")
    return text.replace(old, new, 1)


# Backend: PDF recebe assignment_id explícito e o revalida centralmente.
path = Path("backend/routers/learning_objects.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from services.content_assignment_scope import filter_visible_content_entries\n",
    "from services.content_assignment_scope import filter_visible_content_entries\n"
    "from services.diary_assignment_access import (\n"
    "    DiaryAction, DiaryAssignmentAccessError, authorize_assignment_access,\n"
    ")\n",
    "backend access imports",
)

text = replace_once(
    text,
    "        academic_year: Optional[int] = None,\n        course_id: Optional[str] = None\n    ):\n",
    "        academic_year: Optional[int] = None,\n        course_id: Optional[str] = None,\n        assignment_id: Optional[str] = None\n    ):\n",
    "pdf signature",
)

old = """        # Buscar registros do bimestre. Professor com DVD ativo usa exclusivamente\n        # content_entries e passa pelo filtro canônico de visibilidade/autoria.\n        dvd_mode = await professor_has_active_dvd_content(\n            db, current_user, class_id=class_id, course_id=course_id\n        )\n        if dvd_mode:\n            query = {\n                \"class_id\": class_id,\n                \"academic_year\": academic_year,\n                \"date\": {\"$gte\": period_start, \"$lte\": period_end},\n                \"deleted\": False,\n            }\n            if course_id:\n                query[\"component_id\"] = course_id\n"""
new = """        # Buscar registros do bimestre. No DVD, assignment_id é a identidade\n        # técnica do PDF e nunca é aceito sem revalidação central.\n        dvd_mode = False\n        if assignment_id:\n            try:\n                await authorize_assignment_access(\n                    db, current_user, assignment_id,\n                    action=DiaryAction.VIEW,\n                    on_date=datetime.now().date().isoformat(),\n                    expected_class_id=class_id,\n                    active_mantenedora_id=get_mantenedora_scope(current_user, request),\n                )\n            except DiaryAssignmentAccessError as exc:\n                raise HTTPException(\n                    status_code=403,\n                    detail={\"code\": exc.code, \"message\": exc.message},\n                ) from exc\n            dvd_mode = True\n        else:\n            dvd_mode = await professor_has_active_dvd_content(\n                db, current_user, class_id=class_id, course_id=course_id\n            )\n            if dvd_mode and current_user.get('role') == 'professor':\n                raise HTTPException(\n                    status_code=409,\n                    detail={\n                        \"code\": \"DVD_CONTENT_ASSIGNMENT_REQUIRED\",\n                        \"message\": \"Informe assignment_id para gerar o PDF deste Diário por Vínculo.\",\n                    },\n                )\n\n        if dvd_mode:\n            query = {\n                \"class_id\": class_id,\n                \"academic_year\": academic_year,\n                \"date\": {\"$gte\": period_start, \"$lte\": period_end},\n                \"deleted\": False,\n            }\n            if assignment_id:\n                query[\"assignment_id\"] = assignment_id\n            if course_id:\n                query[\"component_id\"] = course_id\n"""
text = replace_once(text, old, new, "pdf dvd resolution")
path.write_text(text, encoding="utf-8")


# Frontend: propaga o assignment_id do contexto do dashboard para o PDF.
path = Path("frontend/src/pages/LearningObjects.js")
text = path.read_text(encoding="utf-8")
old = """      if (pdfCourseId) {\n        params.append('course_id', pdfCourseId);\n      }\n      const response = await fetch(\n"""
new = """      if (pdfCourseId) {\n        params.append('course_id', pdfCourseId);\n      }\n      const assignmentId = new URLSearchParams(window.location.search).get('assignment_id');\n      if (assignmentId) {\n        params.append('assignment_id', assignmentId);\n      }\n      const response = await fetch(\n"""
text = replace_once(text, old, new, "frontend pdf assignment")
path.write_text(text, encoding="utf-8")

print("PHASE38F_PDF_PATCH_OK")
