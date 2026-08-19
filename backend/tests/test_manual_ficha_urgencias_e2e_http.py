"""Homologação funcional HTTP — Urgências / Ficha Individual.

Executa contra backend real + Mongo efêmero no GitHub Actions.
Não toca produção.

Cobre:
- turma regular + avaliação numérica;
- turma multisseriada + avaliação conceitual;
- currículo evidence-first via matriz explícita da turma;
- faltas/frequência lidas do SIGESC;
- resultado e data manuais refletidos no PDF;
- fidelidade estrutural com o gerador oficial;
- validações server-side;
- nenhuma mutação em coleções acadêmicas;
- única escrita: manual_document_issuances.
"""
from __future__ import annotations

import base64
import os
import re
import unicodedata
from io import BytesIO
from pathlib import Path

import pytest
import requests
from PyPDF2 import PdfReader
from pymongo import MongoClient

from pdf.ficha_individual import generate_ficha_individual_pdf

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "sigesc_ci")
EMAIL = os.environ.get("CI_ADMIN_EMAIL", "ci-admin@sigesc.aprenderdigital.top")
PASSWORD = os.environ.get("CI_ADMIN_PASSWORD", "CiRegress!2026")

TENANT = "urg-fixt-tenant"
SCHOOL = "urg-fixt-school"
REGULAR_CLASS = "urg-fixt-class-regular"
MULTI_CLASS = "urg-fixt-class-multi"
REGULAR_STUDENT = "urg-fixt-student-regular"
MULTI_STUDENT = "urg-fixt-student-multi"
REGULAR_ENROLLMENT = "urg-fixt-enroll-regular"
MULTI_ENROLLMENT = "urg-fixt-enroll-multi"
C_PORT = "urg-fixt-course-port"
C_MATH = "urg-fixt-course-math"
C_PORT_AI = "urg-fixt-course-port-ai"
C_MATH_AI = "urg-fixt-course-math-ai"
YEAR = 2026
FIXTURE_IDS = {
    SCHOOL,
    REGULAR_CLASS,
    MULTI_CLASS,
    REGULAR_STUDENT,
    MULTI_STUDENT,
    REGULAR_ENROLLMENT,
    MULTI_ENROLLMENT,
    C_PORT,
    C_MATH,
    C_PORT_AI,
    C_MATH_AI,
}

# PNG 1x1 local para impedir dependência de rede na geração do PDF.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2iVQAAAAASUVORK5CYII="
)
_LOGO_PATH = Path("/tmp/sigesc-urgencias-ci-logo.png")


def _norm(value: str) -> str:
    value = "".join(
        ch for ch in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(ch)
    )
    return " ".join(value.upper().split())


def _pdf_text(raw: bytes) -> str:
    reader = PdfReader(BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _cleanup(db) -> None:
    db.manual_document_issuances.delete_many({"source": "urgencias_ci_fixture"})
    db.manual_document_issuances.delete_many({"student_id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}})
    db.student_history.delete_many({"student_id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}})
    db.attendance.delete_many({"class_id": {"$in": [REGULAR_CLASS, MULTI_CLASS]}})
    db.grades.delete_many({"student_id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}})
    db.enrollments.delete_many({"id": {"$in": [REGULAR_ENROLLMENT, MULTI_ENROLLMENT]}})
    db.students.delete_many({"id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}})
    db.classes.delete_many({"id": {"$in": [REGULAR_CLASS, MULTI_CLASS]}})
    db.courses.delete_many({"id": {"$in": [C_PORT, C_MATH, C_PORT_AI, C_MATH_AI]}})
    db.schools.delete_many({"id": SCHOOL})
    db.mantenedora.delete_many({"id": TENANT})
    db.mantenedoras.delete_many({"id": TENANT})
    db.calendario_letivo.delete_many({"fixture": "urgencias_ci"})
    db.calendar_events.delete_many({"fixture": "urgencias_ci"})


def _seed(db) -> None:
    _LOGO_PATH.write_bytes(_PNG_1X1)

    mantenedora = {
        "id": TENANT,
        "mantenedora_id": TENANT,
        "nome": "Prefeitura Municipal de Floresta do Araguaia",
        "secretaria": "Secretaria Municipal de Educação",
        "municipio": "Floresta do Araguaia",
        "estado": "PA",
        "brasao_url": _LOGO_PATH.as_uri(),
        "media_aprovacao": 5.0,
        "frequencia_minima": 75.0,
        "aprovacao_com_dependencia": True,
        "max_componentes_dependencia": 2,
    }
    db.mantenedora.insert_one(dict(mantenedora))
    db.mantenedoras.insert_one(dict(mantenedora))

    db.schools.insert_one({
        "id": SCHOOL,
        "mantenedora_id": TENANT,
        "name": "EMEF CI Homologação Urgências",
        "status": "active",
        "atendimento_integral": False,
    })

    db.courses.insert_many([
        {
            "id": C_PORT,
            "mantenedora_id": TENANT,
            "name": "Língua Portuguesa",
            "nivel_ensino": "fundamental_anos_finais",
            "active": True,
            "carga_horaria": 160,
            "atendimento_programa": "regular",
        },
        {
            "id": C_MATH,
            "mantenedora_id": TENANT,
            "name": "Matemática",
            "nivel_ensino": "fundamental_anos_finais",
            "active": True,
            "carga_horaria": 160,
            "atendimento_programa": "regular",
        },
        {
            "id": C_PORT_AI,
            "mantenedora_id": TENANT,
            "name": "Língua Portuguesa",
            "nivel_ensino": "fundamental_anos_iniciais",
            "active": True,
            "carga_horaria": 160,
            "carga_horaria_por_serie": {"1º ANO": 160, "2º ANO": 160},
            "atendimento_programa": "regular",
        },
        {
            "id": C_MATH_AI,
            "mantenedora_id": TENANT,
            "name": "Matemática",
            "nivel_ensino": "fundamental_anos_iniciais",
            "active": True,
            "carga_horaria": 160,
            "carga_horaria_por_serie": {"1º ANO": 160, "2º ANO": 160},
            "atendimento_programa": "regular",
        },
    ])

    db.classes.insert_many([
        {
            "id": REGULAR_CLASS,
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "name": "6º ANO CI",
            "academic_year": YEAR,
            "grade_level": "6º ANO",
            "education_level": "fundamental_anos_finais",
            "nivel_ensino": "fundamental_anos_finais",
            "shift": "morning",
            "course_ids": [C_PORT, C_MATH],
            "is_multi_grade": False,
        },
        {
            "id": MULTI_CLASS,
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "name": "1º/2º ANO MULTI CI",
            "academic_year": YEAR,
            "grade_level": "MULTISSERIADA",
            "education_level": "fundamental_anos_iniciais",
            "nivel_ensino": "fundamental_anos_iniciais",
            "shift": "morning",
            "course_ids": [C_PORT_AI, C_MATH_AI],
            "is_multi_grade": True,
            "series": ["1º ANO", "2º ANO"],
        },
    ])

    db.students.insert_many([
        {
            "id": REGULAR_STUDENT,
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "class_id": REGULAR_CLASS,
            "full_name": "Estudante Regular de Homologação",
            "birth_date": "2013-03-15",
            "sex": "M",
            "inep_code": "CI000001",
            "status": "active",
            "student_series": "6º ANO",
        },
        {
            "id": MULTI_STUDENT,
            "mantenedora_id": TENANT,
            "school_id": SCHOOL,
            "class_id": MULTI_CLASS,
            "full_name": "Estudante Multisseriado de Homologação",
            "birth_date": "2019-04-20",
            "sex": "F",
            "inep_code": "CI000002",
            "status": "active",
            "student_series": "1º ANO",
        },
    ])

    db.enrollments.insert_many([
        {
            "id": REGULAR_ENROLLMENT,
            "mantenedora_id": TENANT,
            "student_id": REGULAR_STUDENT,
            "school_id": SCHOOL,
            "class_id": REGULAR_CLASS,
            "academic_year": YEAR,
            "student_series": "6º ANO",
            "status": "active",
            "registration_number": "CI202600001",
        },
        {
            "id": MULTI_ENROLLMENT,
            "mantenedora_id": TENANT,
            "student_id": MULTI_STUDENT,
            "school_id": SCHOOL,
            "class_id": MULTI_CLASS,
            "academic_year": YEAR,
            "student_series": "1º ANO",
            "status": "active",
            "registration_number": "CI202600002",
        },
    ])

    # Evidência acadêmica pré-existente: precisa permanecer byte-a-byte logicamente igual.
    db.grades.insert_many([
        {
            "id": "urg-fixt-grade-port",
            "mantenedora_id": TENANT,
            "student_id": REGULAR_STUDENT,
            "class_id": REGULAR_CLASS,
            "course_id": C_PORT,
            "academic_year": YEAR,
            "b1": 6.0,
            "b2": 6.5,
            "b3": None,
            "b4": None,
            "version": 3,
        },
        {
            "id": "urg-fixt-grade-math",
            "mantenedora_id": TENANT,
            "student_id": REGULAR_STUDENT,
            "class_id": REGULAR_CLASS,
            "course_id": C_MATH,
            "academic_year": YEAR,
            "b1": 7.0,
            "b2": 7.5,
            "b3": None,
            "b4": None,
            "version": 2,
        },
    ])

    db.attendance.insert_many([
        {
            "id": "urg-fixt-att-port-1",
            "mantenedora_id": TENANT,
            "class_id": REGULAR_CLASS,
            "academic_year": YEAR,
            "date": "2026-02-10",
            "course_id": C_PORT,
            "attendance_type": "by_course",
            "period": "regular",
            "records": [{"student_id": REGULAR_STUDENT, "status": "F"}],
        },
        {
            "id": "urg-fixt-att-port-2",
            "mantenedora_id": TENANT,
            "class_id": REGULAR_CLASS,
            "academic_year": YEAR,
            "date": "2026-02-11",
            "course_id": C_PORT,
            "attendance_type": "by_course",
            "period": "regular",
            "records": [{"student_id": REGULAR_STUDENT, "status": "P"}],
        },
        {
            "id": "urg-fixt-att-math-1",
            "mantenedora_id": TENANT,
            "class_id": REGULAR_CLASS,
            "academic_year": YEAR,
            "date": "2026-02-12",
            "course_id": C_MATH,
            "attendance_type": "by_course",
            "period": "regular",
            "records": [{"student_id": REGULAR_STUDENT, "status": "P"}],
        },
    ])

    db.student_history.insert_one({
        "id": "urg-fixt-history",
        "mantenedora_id": TENANT,
        "student_id": REGULAR_STUDENT,
        "event_type": "enrollment",
        "academic_year": YEAR,
        "class_id": REGULAR_CLASS,
        "note": "Fixture imutável para homologação",
    })

    db.calendario_letivo.insert_one({
        "id": "urg-fixt-calendar",
        "mantenedora_id": TENANT,
        "fixture": "urgencias_ci",
        "ano_letivo": YEAR,
        "school_id": None,
        "dias_letivos_previstos": 200,
        "bimestre_1_inicio": "2026-02-02",
        "bimestre_1_fim": "2026-04-17",
        "bimestre_2_inicio": "2026-04-20",
        "bimestre_2_fim": "2026-06-30",
        "bimestre_3_inicio": "2026-08-03",
        "bimestre_3_fim": "2026-10-09",
        "bimestre_4_inicio": "2026-10-13",
        "bimestre_4_fim": "2026-12-18",
    })


def _snapshot_academic(db) -> dict:
    def rows(collection: str, query: dict) -> list[dict]:
        return list(db[collection].find(query, {"_id": 0}).sort("id", 1))

    return {
        "grades": rows("grades", {"student_id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}}),
        "attendance": rows("attendance", {"class_id": {"$in": [REGULAR_CLASS, MULTI_CLASS]}}),
        "students": rows("students", {"id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}}),
        "enrollments": rows("enrollments", {"id": {"$in": [REGULAR_ENROLLMENT, MULTI_ENROLLMENT]}}),
        "student_history": rows("student_history", {"student_id": {"$in": [REGULAR_STUDENT, MULTI_STUDENT]}}),
    }


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    database = client[DB_NAME]
    _cleanup(database)
    _seed(database)
    yield database
    _cleanup(database)
    client.close()


@pytest.fixture(scope="module")
def auth(db):
    session = requests.Session()
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    assert response.status_code == 200, f"login: {response.status_code} {response.text[:500]}"
    data = response.json()
    token = data.get("access_token") or data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    csrf = data.get("csrf_token") or session.cookies.get("csrf_token")
    if csrf:
        session.headers.update({"X-CSRF-Token": csrf})
    return session


def test_regular_preview_resolves_numeric_curriculum_and_frequency(auth):
    response = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-manual/preview",
        params={
            "school_id": SCHOOL,
            "class_id": REGULAR_CLASS,
            "student_id": REGULAR_STUDENT,
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text[:800]
    data = response.json()
    assert data["evaluation_mode"] == "numeric"
    assert data["student_series"] == "6º ANO"
    assert [c["id"] for c in data["courses"]] == [C_PORT, C_MATH]

    by_id = {c["id"]: c for c in data["courses"]}
    assert by_id[C_PORT]["absences"] == 1
    assert by_id[C_PORT]["frequency_percentage"] == pytest.approx(50.0)
    assert by_id[C_MATH]["absences"] == 0
    assert by_id[C_MATH]["frequency_percentage"] == pytest.approx(100.0)


def test_regular_generate_pdf_manual_result_date_and_no_academic_mutation(auth, db):
    before = _snapshot_academic(db)
    issuance_before = db.manual_document_issuances.count_documents({"student_id": REGULAR_STUDENT})

    payload = {
        "school_id": SCHOOL,
        "class_id": REGULAR_CLASS,
        "student_id": REGULAR_STUDENT,
        "student_series": "6º ANO",
        "resultado": "APROVADO COM DEPENDÊNCIA",
        "data_emissao": "2026-07-31",
        "grades": [
            {"course_id": C_PORT, "b1": 8.0, "b2": 7.0, "rec_s1": None, "b3": 9.0, "b4": 8.0, "rec_s2": None},
            {"course_id": C_MATH, "b1": 6.0, "b2": 7.0, "rec_s1": 8.0, "b3": 6.5, "b4": 7.5, "rec_s2": None},
        ],
    }
    response = auth.post(
        f"{BASE_URL}/api/documents/ficha-individual-manual",
        json=payload,
        timeout=60,
    )
    assert response.status_code == 200, response.text[:800]
    assert response.headers.get("content-type", "").startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 1500

    text = _norm(_pdf_text(response.content))
    assert "FICHA INDIVIDUAL" in text
    assert "ESTUDANTE REGULAR DE HOMOLOGACAO" in text
    assert "LINGUA PORTUGUESA" in text
    assert "MATEMATICA" in text
    assert "APROVADO COM DEPENDENCIA" in text
    assert "31 DE JULHO DE 2026" in text
    assert "FLORESTA DO ARAGUAIA - PA" in text

    # Fidelidade estrutural: o PDF oficial, com os mesmos dados-base, mantém
    # mesma página A4 e os mesmos blocos/campos nucleares. Resultado/data são
    # justamente os dois pontos que a contingência pode substituir.
    school = db.schools.find_one({"id": SCHOOL}, {"_id": 0})
    class_info = db.classes.find_one({"id": REGULAR_CLASS}, {"_id": 0})
    student = db.students.find_one({"id": REGULAR_STUDENT}, {"_id": 0})
    enrollment = db.enrollments.find_one({"id": REGULAR_ENROLLMENT}, {"_id": 0})
    courses = list(db.courses.find({"id": {"$in": [C_PORT, C_MATH]}}, {"_id": 0}))
    mantenedora = db.mantenedora.find_one({"id": TENANT}, {"_id": 0})
    calendario = db.calendario_letivo.find_one({"id": "urg-fixt-calendar"}, {"_id": 0})
    official = generate_ficha_individual_pdf(
        student=student,
        school=school,
        class_info=class_info,
        enrollment=enrollment,
        academic_year=YEAR,
        grades=payload["grades"],
        courses=courses,
        attendance_data={
            "_meta": {"faltas_regular": 0, "faltas_por_componente": {}},
            C_PORT: {"absences": 1, "frequency_percentage": 50.0},
            C_MATH: {"absences": 0, "frequency_percentage": 100.0},
        },
        mantenedora=mantenedora,
        calendario_letivo=calendario,
    ).getvalue()

    manual_reader = PdfReader(BytesIO(response.content))
    official_reader = PdfReader(BytesIO(official))
    assert len(manual_reader.pages) == len(official_reader.pages)
    assert float(manual_reader.pages[0].mediabox.width) == pytest.approx(float(official_reader.pages[0].mediabox.width))
    assert float(manual_reader.pages[0].mediabox.height) == pytest.approx(float(official_reader.pages[0].mediabox.height))

    official_text = _norm(_pdf_text(official))
    for marker in (
        "FICHA INDIVIDUAL",
        "NOME DA ESCOLA",
        "NOME DO ESTUDANTE",
        "ANO LETIVO",
        "ANO/ETAPA",
        "TURMA",
        "TURNO",
        "FREQUENCIA ANUAL",
        "LINGUA PORTUGUESA",
        "MATEMATICA",
        "SECRETARIO(A)",
        "DIRETOR(A)",
    ):
        assert marker in text, f"marker ausente no manual: {marker}"
        assert marker in official_text, f"marker ausente no oficial: {marker}"

    after = _snapshot_academic(db)
    assert after == before, "A emissão manual alterou coleção acadêmica protegida"

    issuance_after = db.manual_document_issuances.count_documents({"student_id": REGULAR_STUDENT})
    assert issuance_after == issuance_before + 1
    issuance = db.manual_document_issuances.find_one(
        {"student_id": REGULAR_STUDENT}, {"_id": 0}, sort=[("issued_at", -1)]
    )
    assert issuance["source"] == "urgencias"
    assert issuance["resultado"] == "APROVADO COM DEPENDÊNCIA"
    assert issuance["data_emissao"] == "2026-07-31"
    assert re.fullmatch(r"[0-9a-f]{64}", issuance["pdf_sha256"])


def test_multigrade_requires_series_and_rejects_wrong_series(auth):
    common = {
        "school_id": SCHOOL,
        "class_id": MULTI_CLASS,
        "student_id": MULTI_STUDENT,
    }
    missing = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-manual/preview",
        params=common,
        timeout=30,
    )
    assert missing.status_code == 400
    assert "obrigatório" in missing.text.lower()

    wrong = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-manual/preview",
        params={**common, "student_series": "2º ANO"},
        timeout=30,
    )
    assert wrong.status_code == 400
    assert "1º ANO" in wrong.text


def test_multigrade_conceptual_preview_and_pdf(auth, db):
    preview = auth.get(
        f"{BASE_URL}/api/documents/ficha-individual-manual/preview",
        params={
            "school_id": SCHOOL,
            "class_id": MULTI_CLASS,
            "student_id": MULTI_STUDENT,
            "student_series": "1º ANO",
        },
        timeout=30,
    )
    assert preview.status_code == 200, preview.text[:800]
    data = preview.json()
    assert data["student_series"] == "1º ANO"
    assert data["evaluation_mode"] == "concept"
    assert {item["value"] for item in data["concept_options"]} == {"C", "ED", "ND"}
    assert [c["id"] for c in data["courses"]] == [C_PORT_AI, C_MATH_AI]

    before = _snapshot_academic(db)
    issuance_before = db.manual_document_issuances.count_documents({"student_id": MULTI_STUDENT})
    response = auth.post(
        f"{BASE_URL}/api/documents/ficha-individual-manual",
        json={
            "school_id": SCHOOL,
            "class_id": MULTI_CLASS,
            "student_id": MULTI_STUDENT,
            "student_series": "1º ANO",
            "resultado": "PROMOVIDO(A)",
            "data_emissao": "2026-08-15",
            "grades": [
                {"course_id": C_PORT_AI, "b1": "C", "b2": "ED", "b3": "C", "b4": "C"},
                {"course_id": C_MATH_AI, "b1": "ED", "b2": "ED", "b3": "C", "b4": "C"},
            ],
        },
        timeout=60,
    )
    assert response.status_code == 200, response.text[:800]
    text = _norm(_pdf_text(response.content))
    assert "ESTUDANTE MULTISSERIADO DE HOMOLOGACAO" in text
    assert "1º ANO" in text or "1O ANO" in text
    assert "CONCEITO FINAL" in text
    assert "LEGENDA" in text
    assert "CONSOLIDADO" in text
    assert "EM DESENVOLVIMENTO" in text
    assert "PROMOVIDO(A)" in text
    assert "15 DE AGOSTO DE 2026" in text

    assert _snapshot_academic(db) == before
    assert db.manual_document_issuances.count_documents({"student_id": MULTI_STUDENT}) == issuance_before + 1


def test_numeric_validation_blocks_grade_above_ten_without_audit_write(auth, db):
    before = db.manual_document_issuances.count_documents({"student_id": REGULAR_STUDENT})
    response = auth.post(
        f"{BASE_URL}/api/documents/ficha-individual-manual",
        json={
            "school_id": SCHOOL,
            "class_id": REGULAR_CLASS,
            "student_id": REGULAR_STUDENT,
            "student_series": "6º ANO",
            "resultado": "APROVADO",
            "data_emissao": "2026-08-10",
            "grades": [{"course_id": C_PORT, "b1": 10.1}],
        },
        timeout=30,
    )
    assert response.status_code == 400
    assert "entre 0 e 10" in response.text
    assert db.manual_document_issuances.count_documents({"student_id": REGULAR_STUDENT}) == before


def test_concept_validation_blocks_code_from_wrong_stage(auth, db):
    before = db.manual_document_issuances.count_documents({"student_id": MULTI_STUDENT})
    response = auth.post(
        f"{BASE_URL}/api/documents/ficha-individual-manual",
        json={
            "school_id": SCHOOL,
            "class_id": MULTI_CLASS,
            "student_id": MULTI_STUDENT,
            "student_series": "1º ANO",
            "resultado": "PROMOVIDO(A)",
            "data_emissao": "2026-08-10",
            "grades": [{"course_id": C_PORT_AI, "b1": "OD"}],
        },
        timeout=30,
    )
    assert response.status_code == 400
    assert "Conceito inválido" in response.text
    assert db.manual_document_issuances.count_documents({"student_id": MULTI_STUDENT}) == before


def test_requires_authentication():
    response = requests.get(
        f"{BASE_URL}/api/documents/ficha-individual-manual/preview",
        params={
            "school_id": SCHOOL,
            "class_id": REGULAR_CLASS,
            "student_id": REGULAR_STUDENT,
        },
        timeout=15,
    )
    assert response.status_code in (401, 403)
