"""Ficha Individual manual para a área de Urgências.

Princípios:
- leitura dos dados acadêmicos/cadastrais oficiais do SIGESC;
- notas/conceitos, resultado e data valem APENAS para a emissão solicitada;
- nenhuma escrita em grades, attendance, students, enrollments ou student_history;
- o PDF usa exatamente o código do ``generate_ficha_individual_pdf`` oficial;
- resultado/data são sobrescritos em uma cópia isolada da função, sem monkeypatch
  global e sem risco de alterar uma emissão normal concorrente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import types
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from auth_middleware import AuthMiddleware
from pdf import ficha_individual as ficha_individual_module
from pdf.utils import (
    CONCEITOS_ANOS_INICIAIS,
    CONCEITOS_EDUCACAO_INFANTIL,
    conceito_para_valor,
    inferir_nivel_ensino,
    is_serie_conceitual_anos_iniciais,
    ordenar_componentes_por_nivel,
)
from services.attendance_utils import fetch_medical_days_for_student
from tenant_scope import apply_tenant_filter, assert_same_tenant, resolve_active_mantenedora
from utils.curriculum_resolver import resolve_curriculum

router = APIRouter(tags=["Urgências - Ficha Individual"])

_ALLOWED_ROLES = {
    "super_admin", "admin", "admin_teste", "gerente",
    "secretario", "diretor", "auxiliar_secretaria",
}

_ALLOWED_RESULTS = {
    "CURSANDO",
    "EM ANDAMENTO",
    "PROMOVIDO(A)",
    "CONCLUIU A ETAPA",
    "APROVADO",
    "APROVADO COM DEPENDÊNCIA",
    "EM DEPENDÊNCIA",
    "REPROVADO",
    "REPROVADO POR FREQUÊNCIA",
    "TRANSFERIDO",
    "DESISTENTE",
    "FALECIDO",
}

_RESULT_COLORS = {
    "CURSANDO": "#2563eb",
    "EM ANDAMENTO": "#2563eb",
    "PROMOVIDO(A)": "#16a34a",
    "CONCLUIU A ETAPA": "#16a34a",
    "APROVADO": "#16a34a",
    "APROVADO COM DEPENDÊNCIA": "#ca8a04",
    "EM DEPENDÊNCIA": "#7c3aed",
    "REPROVADO": "#dc2626",
    "REPROVADO POR FREQUÊNCIA": "#991b1b",
    "TRANSFERIDO": "#2563eb",
    "DESISTENTE": "#6b7280",
    "FALECIDO": "#6b7280",
}


class ManualGradeIn(BaseModel):
    course_id: str
    b1: Optional[float | str] = None
    b2: Optional[float | str] = None
    rec_s1: Optional[float | str] = None
    b3: Optional[float | str] = None
    b4: Optional[float | str] = None
    rec_s2: Optional[float | str] = None


class ManualFichaIn(BaseModel):
    school_id: str
    class_id: str
    student_id: str
    student_series: Optional[str] = None
    resultado: str
    data_emissao: date
    grades: list[ManualGradeIn] = Field(default_factory=list)

    @field_validator("resultado")
    @classmethod
    def validate_resultado(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in _ALLOWED_RESULTS:
            raise ValueError("Resultado inválido")
        return normalized


def _user_school_ids(user: dict) -> set[str]:
    ids: set[str] = set()
    if user.get("school_id"):
        ids.add(str(user["school_id"]))
    for sid in user.get("school_ids") or []:
        if sid:
            ids.add(str(sid))
    for link in user.get("school_links") or []:
        if isinstance(link, dict) and link.get("school_id"):
            ids.add(str(link["school_id"]))
    return ids


def _ensure_role_and_school(user: dict, school_id: str) -> None:
    role = (user.get("role") or "").strip().lower()
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Usuário sem permissão para acessar Urgências")
    if role in {"super_admin", "admin", "admin_teste", "gerente"}:
        return
    allowed = _user_school_ids(user)
    if not allowed or str(school_id) not in allowed:
        raise HTTPException(status_code=403, detail="Escola fora do escopo do usuário")


def _is_multigrade(class_info: dict) -> bool:
    return bool(
        class_info.get("is_multi_grade")
        or class_info.get("is_multigrade")
        or class_info.get("multigrade")
    )


def _concept_options(nivel_ensino: str, grade_level: str) -> list[dict[str, str]]:
    if nivel_ensino == "educacao_infantil":
        return [
            {"value": code, "label": f"{code} — {meta['descricao']}"}
            for code, meta in CONCEITOS_EDUCACAO_INFANTIL.items()
        ]
    if is_serie_conceitual_anos_iniciais(grade_level):
        return [
            {"value": code, "label": f"{code} — {meta['descricao']}"}
            for code, meta in CONCEITOS_ANOS_INICIAIS.items()
        ]
    return []


def _is_conceptual(nivel_ensino: str, grade_level: str) -> bool:
    return nivel_ensino == "educacao_infantil" or is_serie_conceitual_anos_iniciais(grade_level)


async def _load_context(
    db,
    *,
    user: dict,
    request: Request,
    school_id: str,
    class_id: str,
    student_id: str,
    student_series: Optional[str],
) -> dict[str, Any]:
    _ensure_role_and_school(user, school_id)

    school = await db.schools.find_one(
        apply_tenant_filter({"id": school_id}, user, request), {"_id": 0}
    )
    if not school:
        raise HTTPException(status_code=404, detail="Escola não encontrada")
    assert_same_tenant(school, user, request)

    class_info = await db.classes.find_one(
        apply_tenant_filter({"id": class_id}, user, request), {"_id": 0}
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    assert_same_tenant(class_info, user, request)
    if str(class_info.get("school_id")) != str(school_id):
        raise HTTPException(status_code=400, detail="A turma selecionada não pertence à escola informada")

    student = await db.students.find_one(
        apply_tenant_filter({"id": student_id}, user, request), {"_id": 0}
    )
    if not student:
        raise HTTPException(status_code=404, detail="Estudante não encontrado")
    assert_same_tenant(student, user, request)

    academic_year = int(class_info.get("academic_year") or datetime.now().year)
    enrollment = await db.enrollments.find_one(
        apply_tenant_filter(
            {
                "student_id": student_id,
                "class_id": class_id,
                "academic_year": academic_year,
                "status": {"$in": ["active", "relocated", "transferred"]},
            },
            user,
            request,
        ),
        {"_id": 0},
        sort=[("status", 1)],
    )
    if not enrollment:
        raise HTTPException(
            status_code=400,
            detail="Não existe matrícula do estudante na turma e ano letivo selecionados",
        )
    assert_same_tenant(enrollment, user, request)

    enrollment_series = (enrollment.get("student_series") or "").strip()
    if _is_multigrade(class_info):
        if not student_series:
            raise HTTPException(status_code=400, detail="Ano/Série/Etapa é obrigatório para turma multisseriada")
        if enrollment_series and enrollment_series.casefold() != student_series.strip().casefold():
            raise HTTPException(
                status_code=400,
                detail=f"A matrícula do estudante pertence a {enrollment_series}, não a {student_series}",
            )
        enrollment = dict(enrollment)
        enrollment["student_series"] = student_series.strip()
    elif not enrollment_series:
        enrollment = dict(enrollment)
        enrollment["student_series"] = class_info.get("grade_level") or student.get("student_series")

    grade_level = enrollment.get("student_series") or class_info.get("grade_level") or ""
    nivel_ensino = inferir_nivel_ensino(class_info, enrollment) or "fundamental_anos_iniciais"

    resolution = await resolve_curriculum(
        db,
        student_id=student_id,
        class_id=class_id,
        academic_year=academic_year,
        class_info=class_info,
        student_info={
            "id": student_id,
            "student_series": grade_level,
            "class_id": class_id,
        },
        atendimento_programa_filter=class_info.get("atendimento_programa"),
    )
    resolved = resolution.get("components") or []
    ids = [item.get("course_id") for item in resolved if item.get("course_id")]
    if ids:
        course_query = apply_tenant_filter({"id": {"$in": ids}}, user, request)
        course_docs = await db.courses.find(course_query, {"_id": 0}).to_list(300)
    else:
        course_docs = []
    for course in course_docs:
        assert_same_tenant(course, user, request)
    by_id = {c.get("id"): c for c in course_docs}
    courses = [by_id[cid] for cid in ids if cid in by_id]
    courses = ordenar_componentes_por_nivel(courses, nivel_ensino)

    if not courses:
        raise HTTPException(status_code=400, detail="Não foi possível resolver o currículo da turma selecionada")

    attendance_data = await _build_attendance_data(
        db,
        user=user,
        request=request,
        student_id=student_id,
        class_id=class_id,
        academic_year=academic_year,
        courses=courses,
    )

    calendario = await _load_calendar(db, academic_year, user=user, request=request)
    mantenedora = await resolve_active_mantenedora(
        db, user, request, fallback_to_first=True
    ) or {}

    # Replica a resolução do nome de escola anexa usada no módulo oficial de documentos.
    school = dict(school)
    anexa_a = school.get("anexa_a")
    if school.get("tipo_unidade") == "anexa" and anexa_a:
        sede = await db.schools.find_one(
            apply_tenant_filter({"id": anexa_a}, user, request),
            {"_id": 0, "name": 1, "mantenedora_id": 1},
        )
        if sede:
            assert_same_tenant(sede, user, request)
            if sede.get("name"):
                school["anexa_a"] = sede["name"]

    return {
        "school": school,
        "class_info": class_info,
        "student": student,
        "enrollment": enrollment,
        "academic_year": academic_year,
        "grade_level": grade_level,
        "nivel_ensino": nivel_ensino,
        "courses": courses,
        "attendance_data": attendance_data,
        "calendario": calendario,
        "mantenedora": mantenedora,
        "resolution_warnings": resolution.get("warnings") or [],
    }


async def _load_calendar(
    db,
    academic_year: int,
    *,
    user: dict,
    request: Request,
) -> dict[str, Any]:
    calendario = await db.calendario_letivo.find_one(
        apply_tenant_filter(
            {"ano_letivo": academic_year, "school_id": None}, user, request
        ),
        {"_id": 0},
    )
    if not calendario:
        calendario = await db.calendario_letivo.find_one(
            apply_tenant_filter({"ano_letivo": academic_year}, user, request),
            {"_id": 0},
        )
    if not calendario:
        return {}
    assert_same_tenant(calendario, user, request)

    events = await db.calendar_events.find(
        apply_tenant_filter(
            {"academic_year": {"$in": [academic_year, str(academic_year)]}},
            user,
            request,
        ),
        {"_id": 0},
    ).to_list(1000)
    non_school: set[date] = set()
    school_saturdays: set[date] = set()
    for event in events:
        assert_same_tenant(event, user, request)
        start = (event.get("start_date") or "")[:10]
        end = (event.get("end_date") or start)[:10]
        if not start:
            continue
        try:
            current = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        while current <= end_date:
            event_type = event.get("event_type") or ""
            if "feriado" in event_type or event_type == "recesso_escolar" or event.get("is_school_day") is False:
                non_school.add(current)
            elif current.weekday() == 5 and (event_type == "sabado_letivo" or event.get("is_school_day") is True):
                school_saturdays.add(current)
            current += timedelta(days=1)

    total = 0
    for b in range(1, 5):
        start = calendario.get(f"bimestre_{b}_inicio")
        end = calendario.get(f"bimestre_{b}_fim")
        if not start or not end:
            continue
        try:
            current = datetime.strptime(str(start)[:10], "%Y-%m-%d").date()
            end_date = datetime.strptime(str(end)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        while current <= end_date:
            if current.weekday() < 5 and current not in non_school:
                total += 1
            elif current.weekday() == 5 and current in school_saturdays:
                total += 1
            current += timedelta(days=1)

    calendario = dict(calendario)
    calendario["dias_letivos_calculados"] = total or calendario.get("dias_letivos_previstos") or 200
    return calendario


async def _build_attendance_data(
    db,
    *,
    user: dict,
    request: Request,
    student_id: str,
    class_id: str,
    academic_year: int,
    courses: list[dict],
) -> dict[str, Any]:
    records = await db.attendance.find(
        apply_tenant_filter(
            {"class_id": class_id, "academic_year": academic_year}, user, request
        ),
        {"_id": 0},
    ).to_list(None)
    for record in records:
        assert_same_tenant(record, user, request)

    dates = {(doc.get("date") or "")[:10] for doc in records if doc.get("date")}
    # A busca de atestado é limitada pelo student_id já validado no tenant. Alguns
    # documentos legados não possuem mantenedora_id, então não aplicamos filtro que
    # os faria desaparecer indevidamente.
    certs = await db.medical_certificates.find(
        {
            "student_id": student_id,
            "start_date": {"$lte": f"{academic_year}-12-31"},
            "end_date": {"$gte": f"{academic_year}-01-01"},
        },
        {"_id": 0, "start_date": 1, "end_date": 1},
    ).to_list(None)
    medical_days = fetch_medical_days_for_student(certs, dates) if dates else set()

    faltas_regular = 0
    faltas_por_componente: dict[str, int] = {}
    seen_regular_dates: set[str] = set()
    totals_by_course: dict[str, int] = {}
    absences_by_course: dict[str, int] = {}

    for doc in records:
        d10 = (doc.get("date") or "")[:10]
        cid = doc.get("course_id")
        attendance_type = doc.get("attendance_type") or "daily"
        period = doc.get("period") or "regular"
        student_rec = next(
            (r for r in (doc.get("records") or []) if r.get("student_id") == student_id),
            None,
        )
        if not student_rec:
            continue
        status = (student_rec.get("status") or "").upper()
        absent = status in {"F", "A", "ABSENT"} and d10 not in medical_days

        if cid:
            totals_by_course[cid] = totals_by_course.get(cid, 0) + 1
            if absent:
                absences_by_course[cid] = absences_by_course.get(cid, 0) + 1

        if attendance_type == "daily" and period == "regular":
            if absent and d10 and d10 not in seen_regular_dates:
                seen_regular_dates.add(d10)
                faltas_regular += 1
        elif cid and absent:
            faltas_por_componente[cid] = faltas_por_componente.get(cid, 0) + 1

    out: dict[str, Any] = {
        "_meta": {
            "faltas_regular": faltas_regular,
            "faltas_por_componente": faltas_por_componente,
        }
    }
    for course in courses:
        cid = course.get("id")
        total = totals_by_course.get(cid, 0)
        absences = absences_by_course.get(cid, 0)
        freq = ((total - absences) / total * 100) if total else 100.0
        out[cid] = {
            "absences": absences,
            "frequency_percentage": max(0.0, min(100.0, freq)),
            "atendimento_programa": course.get("atendimento_programa"),
        }
    return out


def _preview_courses(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    courses = []
    attendance_data = ctx["attendance_data"]
    grade_level = ctx["grade_level"]
    for c in ctx["courses"]:
        cid = c.get("id")
        attendance = attendance_data.get(cid, {})
        carga_por_serie = c.get("carga_horaria_por_serie") or {}
        workload = carga_por_serie.get(
            grade_level,
            c.get("carga_horaria", c.get("workload", 80)),
        )
        courses.append({
            "id": cid,
            "name": c.get("name") or c.get("nome") or "N/A",
            "carga_horaria": workload,
            "workload": workload,
            "absences": attendance.get("absences", 0),
            "frequency_percentage": attendance.get("frequency_percentage", 100.0),
            "atendimento_programa": c.get("atendimento_programa"),
            "optativo": bool(c.get("optativo", False)),
        })
    return courses


def _convert_manual_grades(payload: ManualFichaIn, ctx: dict[str, Any]) -> list[dict[str, Any]]:
    valid_ids = {c.get("id") for c in ctx["courses"]}
    received_ids = [g.course_id for g in payload.grades]
    if len(received_ids) != len(set(received_ids)):
        raise HTTPException(status_code=400, detail="Componente curricular duplicado no preenchimento")
    invalid = [cid for cid in received_ids if cid not in valid_ids]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Componente fora do currículo resolvido: {invalid[0]}")

    conceptual = _is_conceptual(ctx["nivel_ensino"], ctx["grade_level"])
    if ctx["nivel_ensino"] == "educacao_infantil":
        allowed_concepts = set(CONCEITOS_EDUCACAO_INFANTIL)
    elif is_serie_conceitual_anos_iniciais(ctx["grade_level"]):
        allowed_concepts = set(CONCEITOS_ANOS_INICIAIS)
    else:
        allowed_concepts = set()

    converted: list[dict[str, Any]] = []
    fields = ("b1", "b2", "rec_s1", "b3", "b4", "rec_s2")
    for item in payload.grades:
        row: dict[str, Any] = {
            "student_id": payload.student_id,
            "class_id": payload.class_id,
            "course_id": item.course_id,
            "academic_year": ctx["academic_year"],
        }
        for field in fields:
            value = getattr(item, field)
            if value is None or value == "":
                row[field] = None
                continue
            if conceptual:
                if field in {"rec_s1", "rec_s2"}:
                    row[field] = None
                    continue
                code = str(value).strip().upper()
                if code not in allowed_concepts:
                    raise HTTPException(status_code=400, detail=f"Conceito inválido para a etapa: {code}")
                numeric = conceito_para_valor(code)
                if numeric is None:
                    raise HTTPException(status_code=400, detail=f"Conceito inválido: {code}")
                row[field] = numeric
            else:
                try:
                    numeric = float(str(value).replace(",", "."))
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail=f"Nota inválida no campo {field}")
                if numeric < 0 or numeric > 10:
                    raise HTTPException(status_code=400, detail="As notas devem estar entre 0 e 10")
                row[field] = numeric
        converted.append(row)
    return converted


def _generate_official_pdf_with_overrides(*, resultado: str, data_emissao: date, **kwargs) -> BytesIO:
    """Executa o MESMO código da ficha oficial com globals isolados por emissão.

    Não altera ``pdf.ficha_individual`` globalmente. A função é clonada com o mesmo
    code object e recebe apenas duas dependências substituídas no dicionário de globals:
    o cálculo do resultado e ``date.today()``. Portanto emissões oficiais concorrentes
    continuam usando comportamento normal.
    """
    original = ficha_individual_module.generate_ficha_individual_pdf
    isolated_globals = dict(original.__globals__)

    def manual_result(*args, **inner_kwargs):
        return {
            "resultado": resultado,
            "cor": _RESULT_COLORS.get(resultado, "#111827"),
            "componentes_reprovados": [],
            "media_geral": None,
            "detalhes": "Resultado informado manualmente na emissão de contingência",
            "reprovado_por_frequencia": resultado == "REPROVADO POR FREQUÊNCIA",
        }

    override_value = data_emissao

    class ManualDate(date):
        @classmethod
        def today(cls):
            return override_value

    isolated_globals["determinar_resultado_documento"] = manual_result
    isolated_globals["date"] = ManualDate

    cloned = types.FunctionType(
        original.__code__,
        isolated_globals,
        name=original.__name__,
        argdefs=original.__defaults__,
        closure=original.__closure__,
    )
    cloned.__kwdefaults__ = original.__kwdefaults__
    return cloned(**kwargs)


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    @router.get("/documents/ficha-individual-manual/preview")
    async def preview_manual_ficha(
        school_id: str,
        class_id: str,
        student_id: str,
        request: Request,
        student_series: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        active_db = sandbox_db if user.get("is_sandbox") and sandbox_db is not None else db
        ctx = await _load_context(
            active_db,
            user=user,
            request=request,
            school_id=school_id,
            class_id=class_id,
            student_id=student_id,
            student_series=student_series,
        )
        conceptual = _is_conceptual(ctx["nivel_ensino"], ctx["grade_level"])
        return {
            "school": {"id": ctx["school"].get("id"), "name": ctx["school"].get("name")},
            "class": {
                "id": ctx["class_info"].get("id"),
                "name": ctx["class_info"].get("name"),
                "shift": ctx["class_info"].get("shift"),
                "academic_year": ctx["academic_year"],
            },
            "student": {
                "id": ctx["student"].get("id"),
                "full_name": ctx["student"].get("full_name"),
                "birth_date": ctx["student"].get("birth_date"),
                "sex": ctx["student"].get("sex"),
                "inep_code": ctx["student"].get("inep_code") or ctx["student"].get("inep_number"),
            },
            "student_series": ctx["grade_level"],
            "nivel_ensino": ctx["nivel_ensino"],
            "evaluation_mode": "concept" if conceptual else "numeric",
            "concept_options": _concept_options(ctx["nivel_ensino"], ctx["grade_level"]),
            "courses": _preview_courses(ctx),
            "resolution_warnings": ctx["resolution_warnings"],
        }

    @router.post("/documents/ficha-individual-manual")
    async def generate_manual_ficha(payload: ManualFichaIn, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        active_db = sandbox_db if user.get("is_sandbox") and sandbox_db is not None else db
        ctx = await _load_context(
            active_db,
            user=user,
            request=request,
            school_id=payload.school_id,
            class_id=payload.class_id,
            student_id=payload.student_id,
            student_series=payload.student_series,
        )
        grades = _convert_manual_grades(payload, ctx)

        pdf_buffer = _generate_official_pdf_with_overrides(
            resultado=payload.resultado,
            data_emissao=payload.data_emissao,
            student=ctx["student"],
            school=ctx["school"],
            class_info=ctx["class_info"],
            enrollment=ctx["enrollment"],
            academic_year=ctx["academic_year"],
            grades=grades,
            courses=ctx["courses"],
            attendance_data=ctx["attendance_data"],
            mantenedora=ctx["mantenedora"],
            calendario_letivo=ctx["calendario"],
        )

        raw = pdf_buffer.getvalue()
        digest = sha256(raw).hexdigest()
        issuance = {
            "id": str(uuid4()),
            "document_type": "ficha_individual",
            "student_id": payload.student_id,
            "school_id": payload.school_id,
            "class_id": payload.class_id,
            "academic_year": ctx["academic_year"],
            "student_series": ctx["grade_level"],
            "resultado": payload.resultado,
            "data_emissao": payload.data_emissao.isoformat(),
            "manual_grades_snapshot": grades,
            "issued_by": user.get("id") or user.get("user_id"),
            "issued_by_name": user.get("full_name") or user.get("name") or user.get("username"),
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "pdf_sha256": digest,
            "source": "urgencias",
            "mantenedora_id": ctx["mantenedora"].get("id") or ctx["school"].get("mantenedora_id"),
        }
        # Única escrita do fluxo: trilha documental independente. Não é dado acadêmico.
        await active_db.manual_document_issuances.insert_one(issuance)

        filename_base = (ctx["student"].get("full_name") or "estudante").replace(" ", "_")
        return StreamingResponse(
            BytesIO(raw),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="ficha_individual_urgencia_{filename_base}.pdf"'},
        )

    return router
