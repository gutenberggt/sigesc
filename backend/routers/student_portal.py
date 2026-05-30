"""
Router do Boletim Virtual do Aluno.

Endpoints:
- GET /student/me — dados identificação do aluno logado
- GET /student/me/report-card — boletim completo com notas, faltas, frequência
  e situação (aprovado/reprovado/cursando). 

Pré-requisitos do banco:
- `users` com role="aluno" e campo `student_id` vinculando a um `students.id`.
- `students` com os dados do aluno.
- `enrollments` vinculando aluno → turma.
- `classes` → escola + grade_level + education_level.
- `courses` → componentes curriculares.
- `grades` → notas b1/b2/b3/b4 (+ rec_b1/rec_b2/... opcional + rec_final opcional).
- `attendance.records[]` com student_id + status.
"""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware

router = APIRouter(prefix="/student", tags=["Student Report Card"])


def _is_higher_grade(grade_level: Optional[str], education_level: Optional[str]) -> bool:
    """Retorna True se 6º-9º ano (Fund II) ou EJA 3ª/4ª etapa — faltas por componente."""
    if not grade_level:
        return False
    g = grade_level.lower()
    if any(tok in g for tok in ("6º", "7º", "8º", "9º", "6°", "7°", "8°", "9°")):
        return True
    if "3ª" in g or "4ª" in g or "3a" in g.replace(" ", "") or "4a" in g.replace(" ", ""):
        return True
    return False


def _is_conceito(grade_level: Optional[str], education_level: Optional[str]) -> bool:
    """Retorna True para turmas avaliadas por CONCEITO (sem média numérica / sem recuperação):
    - Educação Infantil (qualquer idade)
    - 1º Ano (Fundamental I)
    - 2º Ano (Fundamental I)
    """
    edu = (education_level or "").lower()
    g = (grade_level or "").lower()
    if "infantil" in edu or "creche" in edu or "pré" in edu or "pre-escola" in edu or "pre escola" in edu:
        return True
    if "infantil" in g or "creche" in g or "pré" in g or "berçário" in g or "maternal" in g:
        return True
    # Detecta 1º / 2º ano (Fund I)
    norm = g.replace(" ", "")
    for tok in ("1º", "1°", "2º", "2°"):
        if tok + "ano" in norm or tok + "ano" in g.replace(" ", "").replace("-", ""):
            return True
    # Fallback: "1 ano" / "2 ano" com espaço
    if g.strip().startswith(("1 ano", "2 ano", "1º ano", "2º ano", "1° ano", "2° ano")):
        return True
    return False


def _is_educacao_infantil(grade_level: Optional[str], education_level: Optional[str]) -> bool:
    """Retorna True somente para Educação Infantil (Creche / Pré-Escola).
    Usado para diferenciar o status final: Ed. Infantil 'Concluiu a etapa'
    vs 1º/2º ano 'Promovido(a)'."""
    edu = (education_level or "").lower()
    g = (grade_level or "").lower()
    if "infantil" in edu or "creche" in edu:
        return True
    if any(t in g for t in ("infantil", "creche", "berçário", "bercario",
                            "maternal", "pré", "pre-escola", "pre escola", "pré-escola")):
        return True
    return False


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):

    def _get_db(user: dict):
        return sandbox_db if user.get("is_sandbox") and sandbox_db is not None else db

    async def _resolve_student(user: dict, current_db) -> dict:
        """Resolve o doc do aluno a partir do user logado.
        User deve ter role='aluno' e student_id vinculado, OU o próprio user doc
        pode ter os dados do aluno (caso legacy).
        """
        if user.get("role") not in ("aluno", "student"):
            raise HTTPException(status_code=403, detail="Apenas alunos acessam esta rota")
        # JWT não carrega student_id — busca no user doc
        user_doc = await current_db.users.find_one(
            {"id": user.get("id")}, {"_id": 0, "student_id": 1, "email": 1}
        ) or {}
        student_id = user_doc.get("student_id") or user.get("student_id")
        if student_id:
            st = await current_db.students.find_one({"id": student_id}, {"_id": 0})
            if st:
                return st
        # Fallback: tenta match por email (caso students tenha email)
        email = user_doc.get("email") or user.get("email")
        if email:
            st = await current_db.students.find_one({"email": email}, {"_id": 0})
            if st:
                return st
        raise HTTPException(
            status_code=404,
            detail="Aluno sem vínculo no sistema. Contate a secretaria para vincular seu cadastro.",
        )

    @router.get("/me")
    async def get_me(request: Request):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        student = await _resolve_student(user, current_db)
        # Enriquecimento mínimo para o dashboard do aluno: nome da turma + escola.
        if student.get("class_id"):
            cls = await current_db.classes.find_one(
                {"id": student["class_id"]},
                {"_id": 0, "name": 1, "grade_level": 1, "shift": 1},
            )
            if cls:
                student["class_name"] = cls.get("name")
                student["class_grade_level"] = cls.get("grade_level")
                student["class_shift"] = cls.get("shift")
        if student.get("school_id"):
            sch = await current_db.schools.find_one(
                {"id": student["school_id"]}, {"_id": 0, "name": 1}
            )
            if sch:
                student["school_name"] = sch.get("name")
        return student

    @router.get("/me/report-card")
    async def my_report_card(request: Request, academic_year: Optional[int] = None):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        student = await _resolve_student(user, current_db)

        now = datetime.now(timezone.utc)
        year = academic_year or now.year

        # ----- Enrollment ativa -----
        enrollment = await current_db.enrollments.find_one(
            {"student_id": student["id"],
             "academic_year": year,
             "status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}},
            {"_id": 0},
        )
        if not enrollment:
            # Busca a mais recente (sem filtrar ano)
            enrollment = await current_db.enrollments.find_one(
                {"student_id": student["id"]}, {"_id": 0}, sort=[("academic_year", -1)]
            )
        if not enrollment:
            raise HTTPException(status_code=404, detail="Nenhuma matrícula encontrada")
        year = enrollment.get("academic_year") or year

        # ----- Turma + Escola + Mantenedora -----
        class_doc = await current_db.classes.find_one(
            {"id": enrollment.get("class_id")}, {"_id": 0}
        ) or {}
        school = await current_db.schools.find_one(
            {"id": class_doc.get("school_id") or enrollment.get("school_id") or student.get("school_id")},
            {"_id": 0},
        ) or {}
        mant_id = school.get("mantenedora_id")
        mantenedora = await current_db.mantenedoras.find_one(
            {"id": mant_id}, {"_id": 0}
        ) if mant_id else {}
        mantenedora = mantenedora or {}

        media_aprovacao = float(mantenedora.get("media_aprovacao") or 6.0)
        freq_minima = float(mantenedora.get("frequencia_minima") or 75.0)

        # ----- Notas do aluno -----
        grades_by_course = {}
        async for g in current_db.grades.find(
            {"student_id": student["id"], "academic_year": year}, {"_id": 0}
        ):
            cid = g.get("course_id")
            if cid:
                grades_by_course[cid] = g

        # ----- Componentes da turma -----
        course_ids = class_doc.get("course_ids") or []
        courses = []
        if course_ids:
            async for c in current_db.courses.find({"id": {"$in": course_ids}}, {"_id": 0}):
                courses.append(c)
        else:
            # Fallback 1: courses linkados à turma/escola (alguns tenants)
            async for c in current_db.courses.find(
                {"$or": [{"class_id": class_doc.get("id")}, {"school_id": school.get("id")}]},
                {"_id": 0},
            ):
                courses.append(c)

        # Fallback 2: componentes obtidos a partir dos grades lançados do aluno
        if not courses and grades_by_course:
            cids = list(grades_by_course.keys())
            async for c in current_db.courses.find({"id": {"$in": cids}}, {"_id": 0}):
                courses.append(c)

        # Fallback 3: componentes da mantenedora compatíveis com o nível de ensino
        if not courses and mant_id:
            edu_level = class_doc.get("education_level")
            q = {"mantenedora_id": mant_id}
            if edu_level:
                q["$or"] = [{"nivel_ensino": edu_level}, {"nivel_ensino": None}, {"nivel_ensino": {"$exists": False}}]
            async for c in current_db.courses.find(q, {"_id": 0}).limit(30):
                courses.append(c)

        # ----- Faltas por turma (e por componente se Fund II/EJA) -----
        attendance_total = 0
        attendance_presentes = 0
        faltas_por_componente = {}  # course_id -> int
        async for att in current_db.attendance.find(
            {"class_id": enrollment.get("class_id")},
            {"_id": 0, "records": 1, "course_id": 1, "date": 1},
        ).limit(5000):
            cid = att.get("course_id")
            for rec in (att.get("records") or []):
                if rec.get("student_id") != student["id"]:
                    continue
                attendance_total += 1
                status = (rec.get("status") or "").lower()
                if status in ("presente", "present", "p"):
                    attendance_presentes += 1
                elif status in ("falta", "faltou", "absent", "f"):
                    if cid:
                        faltas_por_componente[cid] = faltas_por_componente.get(cid, 0) + 1

        total_faltas = attendance_total - attendance_presentes
        freq_percent = round(100.0 * attendance_presentes / attendance_total, 2) if attendance_total else None

        # ----- Dias letivos até hoje (via calendario_letivo) -----
        dias_letivos_total = 0
        dias_letivos_ate_hoje = 0
        hoje = date.today()
        async for evt in current_db.calendario_letivo.find(
            {"academic_year": year,
             "$or": [{"school_id": school.get("id")}, {"school_id": None},
                     {"mantenedora_id": mant_id}]},
            {"_id": 0, "date": 1, "letivo": 1, "is_letivo": 1},
        ):
            is_letivo = evt.get("letivo") if "letivo" in evt else evt.get("is_letivo", True)
            if not is_letivo:
                continue
            try:
                d = date.fromisoformat(str(evt.get("date"))[:10])
                dias_letivos_total += 1
                if d <= hoje:
                    dias_letivos_ate_hoje += 1
            except Exception:
                continue

        # Se não houver calendario_letivo, estima por dias úteis
        if dias_letivos_total == 0:
            # Ano letivo padrão: 200 dias letivos
            dias_letivos_total = 200
            # Estima dias decorridos via proporção mês-a-mês (Fev-Dez = 11 meses)
            first_day = date(year, 2, 1)
            if hoje < first_day:
                dias_letivos_ate_hoje = 0
            elif hoje >= date(year, 12, 15):
                dias_letivos_ate_hoje = 200
            else:
                delta = (hoje - first_day).days
                dias_letivos_ate_hoje = min(int(delta * 200 / 300), 200)

        # Cálculo de freq com base em dias letivos (mais preciso que contagem de attendance)
        if dias_letivos_ate_hoje > 0 and attendance_total == 0:
            # Ainda não há attendance lançada
            freq_percent_letivo = None
        elif dias_letivos_ate_hoje > 0:
            freq_percent_letivo = round(100.0 * (dias_letivos_ate_hoje - total_faltas) / dias_letivos_ate_hoje, 2)
        else:
            freq_percent_letivo = None

        # ----- Monta linhas do boletim por componente -----
        higher_grade = _is_higher_grade(class_doc.get("grade_level"), class_doc.get("education_level"))
        usa_conceito = _is_conceito(class_doc.get("grade_level"), class_doc.get("education_level"))
        linhas = []
        soma_medias = 0.0
        n_com_nota = 0
        for course in courses:
            g = grades_by_course.get(course.get("id"), {})
            b1 = g.get("b1")
            b2 = g.get("b2")
            b3 = g.get("b3")
            b4 = g.get("b4")
            rec_b1 = g.get("rec_b1") or g.get("rec1")
            rec_b2 = g.get("rec_b2") or g.get("rec2")
            rec_b3 = g.get("rec_b3") or g.get("rec3")
            rec_b4 = g.get("rec_b4") or g.get("rec4")
            rec_final = g.get("rec_final") or g.get("recuperacao_final")

            if usa_conceito:
                # Educação Infantil / 1º ano / 2º ano: conceito, sem recuperação, sem média numérica
                bims_preenchidos = [x for x in (b1, b2, b3, b4) if x is not None and x != ""]
                situacao_comp = "cursando" if len(bims_preenchidos) < 4 else "aprovado"
                linhas.append({
                    "course_id": course.get("id"),
                    "course_name": course.get("name"),
                    "workload": course.get("workload"),
                    "b1": b1, "b2": b2, "b3": b3, "b4": b4,
                    "rec_b1": None, "rec_b2": None, "rec_b3": None, "rec_b4": None,
                    "rec_final": None,
                    "media": None,
                    "media_final": None,
                    "situacao": situacao_comp,
                    "usa_conceito": True,
                    "faltas_componente": faltas_por_componente.get(course.get("id"), 0) if higher_grade else None,
                })
                continue

            # Aplica recuperação (maior entre bim e rec_bim)
            def _eff(bim, rec):
                vals = [x for x in (bim, rec) if x is not None]
                return max(vals) if vals else None
            e1, e2, e3, e4 = _eff(b1, rec_b1), _eff(b2, rec_b2), _eff(b3, rec_b3), _eff(b4, rec_b4)
            bims_validos = [x for x in (e1, e2, e3, e4) if x is not None]
            media = round(sum(bims_validos) / len(bims_validos), 2) if bims_validos else None
            # Aplica recuperação final: se média < aprovação, tenta rec_final
            situacao_comp = None
            media_final = media
            if media is not None and len(bims_validos) == 4:
                if media >= media_aprovacao:
                    situacao_comp = "aprovado"
                elif rec_final is not None:
                    # Regra clássica: nova média = (média + rec_final)/2
                    media_final = round((media + rec_final) / 2, 2)
                    situacao_comp = "aprovado" if media_final >= media_aprovacao else "reprovado"
                else:
                    situacao_comp = "cursando"
            elif media is not None:
                situacao_comp = "cursando"

            if media is not None:
                soma_medias += media
                n_com_nota += 1

            linhas.append({
                "course_id": course.get("id"),
                "course_name": course.get("name"),
                "workload": course.get("workload"),
                "b1": b1, "b2": b2, "b3": b3, "b4": b4,
                "rec_b1": rec_b1, "rec_b2": rec_b2,
                "rec_b3": rec_b3, "rec_b4": rec_b4,
                "rec_final": rec_final,
                "media": media,
                "media_final": media_final,
                "situacao": situacao_comp,
                "usa_conceito": False,
                "faltas_componente": faltas_por_componente.get(course.get("id"), 0) if higher_grade else None,
            })

        media_geral = round(soma_medias / n_com_nota, 2) if n_com_nota else None

        # ----- Situação final global (considera média e frequência) -----
        situacao_final = "cursando"
        freq_ok = (freq_percent_letivo or 100.0) >= freq_minima
        if usa_conceito:
            # Em turmas por conceito: aprovação depende apenas da frequência e preenchimento
            todos_bims_preenchidos = all(
                all(row.get(b) not in (None, "") for b in ("b1", "b2", "b3", "b4"))
                for row in linhas
            ) if linhas else False
            if todos_bims_preenchidos:
                situacao_final = "aprovado" if freq_ok else "reprovado"
        else:
            any_finalizada = any(row.get("situacao") in ("aprovado", "reprovado") for row in linhas)
            if any_finalizada:
                any_reprovada = any(row.get("situacao") == "reprovado" for row in linhas)
                if any_reprovada or not freq_ok:
                    situacao_final = "reprovado"
                else:
                    situacao_final = "aprovado"

        # ----- Alertas de frequência -----
        alerts = []
        # Excesso de faltas: >25% em relação aos dias letivos até hoje
        if dias_letivos_ate_hoje > 0:
            pct_faltas = 100.0 * total_faltas / dias_letivos_ate_hoje
            if pct_faltas > 25:
                alerts.append({
                    "type": "excesso_faltas",
                    "severity": "high",
                    "message": f"Atenção! Você já acumulou {total_faltas} faltas "
                               f"({round(pct_faltas, 1)}% dos {dias_letivos_ate_hoje} dias letivos até hoje). "
                               f"O limite permitido é 25%. Risco de reprovação por frequência.",
                })
            elif freq_percent_letivo is not None and freq_percent_letivo >= 95:
                alerts.append({
                    "type": "parabens_presenca",
                    "severity": "success",
                    "message": f"Parabéns! Você tem {freq_percent_letivo}% de presença. "
                               f"Continue assim!",
                })

        return {
            "aluno": {
                "id": student.get("id"),
                "nome": student.get("full_name") or student.get("name"),
                "inep": student.get("inep_code"),
                "nascimento": student.get("birth_date"),
                "sexo": student.get("sex"),
                "cpf": student.get("cpf"),
            },
            "escola": {
                "id": school.get("id"),
                "nome": school.get("name"),
                "inep": school.get("inep_code"),
                "municipio": school.get("municipio"),
                "estado": school.get("estado"),
            },
            "mantenedora": {
                "nome": mantenedora.get("nome"),
                "secretaria": mantenedora.get("secretaria"),
                "brasao_url": mantenedora.get("brasao_url"),
                "logotipo_url": mantenedora.get("logotipo_url"),
            },
            "turma": {
                "id": class_doc.get("id"),
                "nome": class_doc.get("name"),
                "grade_level": class_doc.get("grade_level"),
                "education_level": class_doc.get("education_level"),
                "shift": class_doc.get("shift"),
            },
            "academic_year": year,
            "media_aprovacao": media_aprovacao,
            "frequencia_minima": freq_minima,
            "higher_grade": higher_grade,
            "usa_conceito": usa_conceito,
            "componentes": linhas,
            "media_geral": media_geral,
            "frequencia": {
                "dias_letivos_ate_hoje": dias_letivos_ate_hoje,
                "dias_letivos_previstos": dias_letivos_total,
                "total_faltas": total_faltas,
                "total_presencas": attendance_presentes,
                "total_aulas_registradas": attendance_total,
                "percentual_presenca_attendance": freq_percent,
                "percentual_presenca_dias_letivos": freq_percent_letivo,
            },
            "situacao_final": situacao_final,
            "alerts": alerts,
            "computed_at": now.isoformat(),
        }

    # ==============================================================
    # Próximos Eventos do Calendário Letivo (da escola do aluno)
    # ==============================================================
    @router.get("/me/upcoming-events")
    async def get_upcoming_events(request: Request, limit: int = 6):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        student = await _resolve_student(user, current_db)

        # Resolve escola a partir da matrícula ativa; fallback para student.school_id
        enrollment = await current_db.enrollments.find_one(
            {"student_id": student["id"],
             "status": {"$in": ["ativa", "active", "matriculado", "matriculada"]}},
            {"_id": 0},
        ) or {}
        school_id = enrollment.get("school_id") or student.get("school_id")
        class_doc = {}
        if enrollment.get("class_id"):
            class_doc = await current_db.classes.find_one({"id": enrollment["class_id"]}, {"_id": 0}) or {}
        if not school_id:
            school_id = class_doc.get("school_id")

        today = date.today().isoformat()
        q: dict = {"start_date": {"$gte": today}}
        # Alguns eventos são globais (sem school_id) e valem para toda a mantenedora;
        # incluímos também os da escola específica.
        if school_id:
            q = {"start_date": {"$gte": today},
                 "$or": [{"school_id": school_id}, {"school_id": None}, {"school_id": {"$exists": False}}]}

        events = await current_db.calendar_events.find(q, {"_id": 0}).sort("start_date", 1).to_list(limit)
        return {"events": events, "today": today, "school_id": school_id}

    # ==============================================================
    # Avisos direcionados ao aluno
    # ==============================================================
    @router.get("/me/announcements")
    async def get_my_announcements(request: Request, limit: int = 10):
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in ("aluno", "student"):
            raise HTTPException(status_code=403, detail="Apenas alunos acessam esta rota")
        current_db = _get_db(user)

        announcements = await current_db.announcements.find(
            {"target_user_ids": user["id"]},
            {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)

        read_statuses = await current_db.announcement_reads.find(
            {"user_id": user["id"]}, {"_id": 0, "announcement_id": 1, "read_at": 1},
        ).to_list(500)
        read_map = {r["announcement_id"]: r.get("read_at") for r in read_statuses}

        result = []
        for ann in announcements:
            result.append({
                "id": ann["id"],
                "title": ann.get("title"),
                "content": ann.get("content"),
                "sender_name": ann.get("sender_name"),
                "sender_role": ann.get("sender_role"),
                "created_at": ann.get("created_at"),
                "is_read": ann["id"] in read_map,
            })
        return {"announcements": result, "total": len(result)}

    return router
