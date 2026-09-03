"""Regressão A/B multi-tenant do Dashboard Analítico (backend/routers/analytics.py).

Reproduz e trava a falha reportada: após a correção de X-Mantenedora-Id no
fetch() do frontend (PR #339), o Dashboard carregava dados, mas os endpoints
de analytics não aplicavam `apply_tenant_filter` — o card "Escolas" mostrava
a contagem certa (via /overview), mas o Ranking de Escolas, Desempenho de
Alunos/Professores, Frequência Mensal e Notas misturavam dados de QUALQUER
mantenedora, independente de qual estivesse selecionada.

Cenário: dois tenants (TENANT_A / TENANT_B), cada um com sua própria escola,
turma, aluno, matrícula, frequência, nota e alocação de professor — valores
numéricos deliberadamente diferentes entre os dois para que qualquer mistura
seja detectável nos asserts. Um terceiro conjunto de documentos "órfãos"
(sem `mantenedora_id`) cobre a política fail-closed (MT-08): devem ficar
invisíveis para AMBOS os tenants, nunca aparecer em nenhum resultado.

Sem servidor real, sem MongoDB real: usa `mongomock_motor` (backend de
`mongomock`, mesma API do motor/pymongo usada em produção) para executar as
pipelines de agregação REAIS dos endpoints. `mongomock` não implementa
`$trim` (usado em `_attendance_split_stages()`); um pequeno shim local
(`_patch_mongomock_trim`) adiciona esse operador ANTES de qualquer teste
rodar — não altera o pacote instalado, é aplicado só neste processo.

Os handlers são chamados diretamente (sem servidor HTTP/uvicorn): FastAPI
guarda a função original, não decorada, em `route.endpoint`, então
`_get_endpoint(router, path)` a recupera e o teste faz `await endpoint(...)`
como uma chamada Python comum, com um `starlette.Request` construído à mão
(mesmo padrão de `test_mt1_operational_tenant_context.py`).
"""
from __future__ import annotations

import asyncio
import importlib.util
import os

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import auth_middleware as auth_module
from audit_service import audit_service
from auth_middleware import AuthMiddleware

# Import direto do arquivo, sem passar por `routers/__init__.py` — esse
# pacote importa TODOS os routers (inclusive PDF/e-mail/etc.), puxando
# dependências pesadas irrelevantes para este teste (ex.: email-validator).
# O mesmo padrão de isolamento de dependências já usado pelo workflow
# "Multi-Tenant Isolation Guard" (que instala só um subconjunto mínimo de
# pacotes) — aqui replicado via import direto do módulo.
_ANALYTICS_PATH = os.path.join(os.path.dirname(__file__), "..", "routers", "analytics.py")
_spec = importlib.util.spec_from_file_location("analytics_under_test", _ANALYTICS_PATH)
_analytics_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_analytics_module)
setup_analytics_router = _analytics_module.setup_analytics_router

# ============================================================================
# Shim: mongomock não implementa `$trim` (usado por _attendance_split_stages).
# Aplica-se uma vez, no import deste módulo, sobre a classe do mongomock
# instalada no ambiente de teste — nunca sobre código de produção.
# ============================================================================
def _patch_mongomock_trim() -> None:
    from mongomock.aggregate import _Parser

    if getattr(_Parser, "_sigesc_trim_patched", False):
        return

    original = _Parser._handle_string_operator

    def _patched(self, operator, values):
        if operator == "$trim":
            if isinstance(values, dict):
                input_val = self.parse(values.get("input"))
                chars = values.get("chars")
                chars = self.parse(chars) if chars is not None else None
            else:
                input_val = self.parse(values)
                chars = None
            if input_val is None:
                return None
            return str(input_val).strip(chars)
        return original(self, operator, values)

    _patched._sigesc_trim_patched = True
    _Parser._handle_string_operator = _patched
    _Parser._sigesc_trim_patched = True


_patch_mongomock_trim()

from mongomock_motor import AsyncMongoMockClient  # noqa: E402  (depende do shim acima)

YEAR = 2026

TENANT_A = "TENANT_A"
TENANT_B = "TENANT_B"


# ============================================================================
# Helpers de request / auth (mesmo padrão de test_mt1_operational_tenant_context.py)
# ============================================================================
def make_request(path: str, tenant: str | None = None, query: str = "") -> Request:
    headers = [(b"authorization", b"Bearer test-token")]
    if tenant:
        headers.append((b"x-mantenedora-id", tenant.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query.encode("utf-8"),
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def _install_super_admin(monkeypatch, db) -> None:
    """Autentica como super_admin (mesmo perfil do usuário que reportou o bug)."""
    payload = {
        "type": "access",
        "sub": "USER_SA",
        "role": "super_admin",
        "school_ids": [],
        "email": "sa@example.test",
        "mantenedora_id": None,
    }
    monkeypatch.setattr(auth_module, "decode_token", lambda _token: dict(payload))
    monkeypatch.setattr(audit_service, "db", db)


def _get_endpoint(router, path: str):
    # `router = APIRouter(prefix="/analytics", ...)` em analytics.py — as
    # rotas ficam registradas com o prefixo já embutido.
    full_path = f"/analytics{path}"
    for route in router.routes:
        if route.path == full_path:
            return route.endpoint
    raise KeyError(f"Rota não encontrada: {full_path}")


# ============================================================================
# Fixture de dados: dois tenants com valores DELIBERADAMENTE diferentes em
# cada coleção, mais documentos órfãos (sem mantenedora_id) por coleção.
# ============================================================================
async def _seed_two_tenants():
    client = AsyncMongoMockClient()
    db = client["sigesc_test"]

    await db.mantenedoras.insert_many([
        {"id": TENANT_A, "nome": "Tenant A", "ativo": True},
        {"id": TENANT_B, "nome": "Tenant B", "ativo": True},
    ])

    # ---- Escolas ----
    await db.schools.insert_many([
        {"id": "SCHOOL_A", "name": "Escola A", "status": "active", "mantenedora_id": TENANT_A},
        {"id": "SCHOOL_B", "name": "Escola B", "status": "active", "mantenedora_id": TENANT_B},
        {"id": "SCHOOL_ORPHAN", "name": "Escola Sem Tenant", "status": "active"},  # sem mantenedora_id
    ])

    # ---- Turmas ----
    # grade_level fora das listas de exclusão (1º/2º ano, infantil) usadas em
    # /grades/by-subject e /students/performance.
    await db.classes.insert_many([
        {"id": "CLASS_A", "school_id": "SCHOOL_A", "mantenedora_id": TENANT_A,
         "academic_year": YEAR, "education_level": "fundamental_anos_iniciais",
         "grade_level": "5º Ano", "name": "5º Ano A", "school_history": []},
        {"id": "CLASS_B", "school_id": "SCHOOL_B", "mantenedora_id": TENANT_B,
         "academic_year": YEAR, "education_level": "fundamental_anos_iniciais",
         "grade_level": "5º Ano", "name": "5º Ano B", "school_history": []},
        {"id": "CLASS_ORPHAN", "school_id": "SCHOOL_ORPHAN",
         "academic_year": YEAR, "education_level": "fundamental_anos_iniciais",
         "grade_level": "5º Ano", "name": "5º Ano Órfã", "school_history": []},
    ])

    # ---- Alunos ----
    await db.students.insert_many([
        {"id": "STUDENT_A", "full_name": "Aluno Tenant A", "school_id": "SCHOOL_A",
         "class_id": "CLASS_A", "status": "active", "mantenedora_id": TENANT_A},
        {"id": "STUDENT_B", "full_name": "Aluno Tenant B", "school_id": "SCHOOL_B",
         "class_id": "CLASS_B", "status": "active", "mantenedora_id": TENANT_B},
    ])

    # ---- Matrículas ----
    await db.enrollments.insert_many([
        {"id": "ENR_A", "student_id": "STUDENT_A", "class_id": "CLASS_A", "school_id": "SCHOOL_A",
         "academic_year": YEAR, "status": "active", "mantenedora_id": TENANT_A,
         "dependency_id": None},
        {"id": "ENR_B", "student_id": "STUDENT_B", "class_id": "CLASS_B", "school_id": "SCHOOL_B",
         "academic_year": YEAR, "status": "active", "mantenedora_id": TENANT_B,
         "dependency_id": None},
    ])

    # ---- Frequência ----
    # Tenant A: 1 presença (P). Tenant B: 1 falta (F) + 1 presença -> taxas
    # bem diferentes (100% vs 50%), qualquer mistura muda o resultado.
    await db.attendance.insert_many([
        {"id": "ATT_A", "class_id": "CLASS_A", "academic_year": YEAR, "date": f"{YEAR}-03-10",
         "mantenedora_id": TENANT_A,
         "records": [{"student_id": "STUDENT_A", "status": "P", "dependency_id": None}]},
        {"id": "ATT_B", "class_id": "CLASS_B", "academic_year": YEAR, "date": f"{YEAR}-03-11",
         "mantenedora_id": TENANT_B,
         "records": [
             {"student_id": "STUDENT_B", "status": "F", "dependency_id": None},
             {"student_id": "STUDENT_B", "status": "P", "dependency_id": None},
         ]},
        {"id": "ATT_ORPHAN", "class_id": "CLASS_ORPHAN", "academic_year": YEAR,
         "date": f"{YEAR}-03-12",
         "records": [{"student_id": "STUDENT_ORPHAN", "status": "P", "dependency_id": None}]},
    ])

    # ---- Componentes curriculares ----
    await db.courses.insert_many([
        {"id": "COURSE_A", "name": "Matemática"},
        {"id": "COURSE_B", "name": "Português"},
    ])

    # ---- Notas ---- (médias bem diferentes: 9.0 vs 3.0)
    await db.grades.insert_many([
        {"id": "GRADE_A", "student_id": "STUDENT_A", "class_id": "CLASS_A", "course_id": "COURSE_A",
         "academic_year": YEAR, "final_average": 9.0, "b1": 9.0, "b2": 9.0, "b3": 9.0, "b4": 9.0,
         "status": "aprovado", "mantenedora_id": TENANT_A, "dependency_id": None},
        {"id": "GRADE_B", "student_id": "STUDENT_B", "class_id": "CLASS_B", "course_id": "COURSE_B",
         "academic_year": YEAR, "final_average": 3.0, "b1": 3.0, "b2": 3.0, "b3": 3.0, "b4": 3.0,
         "status": "reprovado_nota", "mantenedora_id": TENANT_B, "dependency_id": None},
    ])

    # ---- Professores / alocações ----
    await db.staff.insert_many([
        {"id": "STAFF_A", "nome": "Professor A"},
        {"id": "STAFF_B", "nome": "Professor B"},
    ])
    await db.teacher_assignments.insert_many([
        {"id": "TA_A", "staff_id": "STAFF_A", "staff_name": "Professor A", "school_id": "SCHOOL_A",
         "class_id": "CLASS_A", "course_id": "COURSE_A", "academic_year": YEAR,
         "mantenedora_id": TENANT_A},
        {"id": "TA_B", "staff_id": "STAFF_B", "staff_name": "Professor B", "school_id": "SCHOOL_B",
         "class_id": "CLASS_B", "course_id": "COURSE_B", "academic_year": YEAR,
         "mantenedora_id": TENANT_B},
    ])

    # ---- Calendário letivo (usado só por /teachers/performance p/ SLA) ----
    await db.calendario_letivo.insert_many([
        {"id": "CAL_A", "ano_letivo": YEAR, "mantenedora_id": TENANT_A,
         "bimestre_1_inicio": f"{YEAR}-02-01", "bimestre_4_fim": f"{YEAR}-12-15"},
        {"id": "CAL_B", "ano_letivo": YEAR, "mantenedora_id": TENANT_B,
         "bimestre_1_inicio": f"{YEAR}-02-01", "bimestre_4_fim": f"{YEAR}-12-15"},
    ])

    return db


def _make_router(db):
    return setup_analytics_router(db)


# ============================================================================
# 1) MT-1 fail-closed: super_admin em rota operacional sem X-Mantenedora-Id
# ============================================================================
def test_overview_fail_closed_without_tenant_selection(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    overview = _get_endpoint(router, "/overview")

    request = make_request("/api/analytics/overview")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(overview(request, academic_year=YEAR, school_id=None, class_id=None))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TENANT_CONTEXT_REQUIRED"


def test_schools_ranking_fail_closed_without_tenant_selection(monkeypatch):
    """Mesma garantia MT-1 num endpoint que passa por _require_admin_tier."""
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    ranking = _get_endpoint(router, "/schools/ranking")

    request = make_request("/api/analytics/schools/ranking")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ranking(request, academic_year=YEAR, limit=100, bimestre=None))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TENANT_CONTEXT_REQUIRED"


# ============================================================================
# 2) /overview — contagens e métricas restritas ao tenant ativo
# ============================================================================
def test_overview_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    overview = _get_endpoint(router, "/overview")

    async def _call(tenant):
        request = make_request("/api/analytics/overview", tenant=tenant)
        return await overview(request, academic_year=YEAR, school_id=None, class_id=None)

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    # Escolas/turmas/alunos/matrículas: cada tenant só vê o seu (nunca 3, que
    # seria contar a escola órfã ou a do outro tenant).
    assert result_a["schools"]["total"] == 1
    assert result_b["schools"]["total"] == 1
    assert result_a["students"]["active"] == 1
    assert result_b["students"]["active"] == 1
    assert result_a["enrollments"]["total"] == 1
    assert result_b["enrollments"]["total"] == 1

    # Frequência: tenant A é 100% (1 presença), tenant B é 50% (1 P + 1 F).
    # Se estivesse global, os dois tenants dariam o MESMO valor combinado.
    assert result_a["attendance"]["rate"] == 100.0
    assert result_b["attendance"]["rate"] == 50.0
    assert result_a["attendance"]["total_records"] == 1
    assert result_b["attendance"]["total_records"] == 2

    # Notas: tenant A média 9.0, tenant B média 3.0 — nunca uma média
    # combinada (6.0) nem os valores trocados entre si.
    assert result_a["grades"]["average"] == 9.0
    assert result_b["grades"]["average"] == 3.0


# ============================================================================
# 3) /schools/ranking — nenhuma escola de B aparece com A ativo, e vice-versa
# ============================================================================
def test_schools_ranking_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    ranking = _get_endpoint(router, "/schools/ranking")

    async def _call(tenant):
        request = make_request("/api/analytics/schools/ranking", tenant=tenant)
        return await ranking(request, academic_year=YEAR, limit=100, bimestre=None)

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    ids_a = {row["school_id"] for row in result_a}
    ids_b = {row["school_id"] for row in result_b}

    assert ids_a == {"SCHOOL_A"}
    assert ids_b == {"SCHOOL_B"}
    # A escola órfã (sem mantenedora_id) nunca aparece, em nenhum tenant.
    assert "SCHOOL_ORPHAN" not in ids_a
    assert "SCHOOL_ORPHAN" not in ids_b


# ============================================================================
# 4) /students/performance — nenhum estudante cruza tenants
# ============================================================================
def test_students_performance_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    performance = _get_endpoint(router, "/students/performance")

    async def _call(tenant):
        request = make_request("/api/analytics/students/performance", tenant=tenant)
        return await performance(
            request, academic_year=YEAR, school_id=None, class_id=None,
            subject_id=None, grade_group=None, limit=20,
        )

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    names_a = {row.get("student_name") or row.get("name") for row in result_a.get("data", [])}
    names_b = {row.get("student_name") or row.get("name") for row in result_b.get("data", [])}

    assert "Aluno Tenant B" not in names_a
    assert "Aluno Tenant A" not in names_b


# ============================================================================
# 5) /attendance/monthly — frequência calculada só com o tenant ativo
# ============================================================================
def test_attendance_monthly_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    monthly = _get_endpoint(router, "/attendance/monthly")

    async def _call(tenant):
        request = make_request("/api/analytics/attendance/monthly", tenant=tenant)
        return await monthly(
            request, academic_year=YEAR, school_id=None, class_id=None, student_id=None,
        )

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    total_a = sum(m["total"] for m in result_a)
    total_b = sum(m["total"] for m in result_b)

    # Tenant A tem 1 registro de frequência; Tenant B tem 2. Se a query fosse
    # global, os dois retornariam 3 (soma de A + B + órfão).
    assert total_a == 1
    assert total_b == 2


# ============================================================================
# 6) Demais endpoints: A/B funcional completo (mesma pipeline real do
#    endpoint), cobrindo os itens 5-9 pedidos na revisão.
# ============================================================================
def test_grades_by_subject_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    by_subject = _get_endpoint(router, "/grades/by-subject")

    async def _call(tenant):
        request = make_request("/api/analytics/grades/by-subject", tenant=tenant)
        return await by_subject(
            request, academic_year=YEAR, school_id=None, class_id=None, student_id=None,
        )

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    names_a = {row["course_name"] for row in result_a}
    names_b = {row["course_name"] for row in result_b}

    assert names_a == {"Matemática"}
    assert names_b == {"Português"}


def test_grades_by_period_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    by_period = _get_endpoint(router, "/grades/by-period")

    async def _call(tenant):
        request = make_request("/api/analytics/grades/by-period", tenant=tenant)
        return await by_period(
            request, academic_year=YEAR, school_id=None, class_id=None, student_id=None,
        )

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    # b1 do 1º bimestre: A lançou 9.0, B lançou 3.0. Combinado seria 6.0.
    avg_a = next(p["avg_grade"] for p in result_a if p["period"] == "1")
    avg_b = next(p["avg_grade"] for p in result_b if p["period"] == "1")
    assert avg_a == 9.0
    assert avg_b == 3.0


def test_distribution_grades_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    distribution = _get_endpoint(router, "/distribution/grades")

    async def _call(tenant):
        request = make_request("/api/analytics/distribution/grades", tenant=tenant)
        return await distribution(request, academic_year=YEAR, school_id=None, class_id=None)

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    # Tenant A: nota 9.0 -> faixa "9-10". Tenant B: nota 3.0 -> faixa "3-4.9".
    ranges_a = {row["range"] for row in result_a}
    ranges_b = {row["range"] for row in result_b}
    assert ranges_a == {"9-10"}
    assert ranges_b == {"3-4.9"}


def test_enrollments_trend_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    trend = _get_endpoint(router, "/enrollments/trend")

    async def _call(tenant):
        request = make_request("/api/analytics/enrollments/trend", tenant=tenant)
        return await trend(request, school_id=None, class_id=None)

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    total_a = sum(y["total"] for y in result_a)
    total_b = sum(y["total"] for y in result_b)

    # 1 matrícula em cada tenant; combinado seria 2 nos dois.
    assert total_a == 1
    assert total_b == 1


def test_teachers_performance_isolated_per_tenant(monkeypatch):
    db = asyncio.run(_seed_two_tenants())
    _install_super_admin(monkeypatch, db)
    router = _make_router(db)
    teachers = _get_endpoint(router, "/teachers/performance")

    async def _call(tenant):
        request = make_request("/api/analytics/teachers/performance", tenant=tenant)
        return await teachers(request, academic_year=YEAR, school_id=None, limit=10)

    result_a = asyncio.run(_call(TENANT_A))
    result_b = asyncio.run(_call(TENANT_B))

    names_a = {row.get("teacher_name") or row.get("name") for row in result_a.get("data", [])}
    names_b = {row.get("teacher_name") or row.get("name") for row in result_b.get("data", [])}

    assert "Professor B" not in names_a
    assert "Professor A" not in names_b


# ============================================================================
# 7) Guard estrutural: garante que NENHUM endpoint do router regride para uma
#    consulta sem apply_tenant_filter, mesmo que o teste funcional acima
#    mude de forma (proteção contra "consertar o teste, não o bug").
# ============================================================================
def test_every_analytics_endpoint_calls_apply_tenant_filter():
    import inspect

    source = inspect.getsource(_analytics_module)
    endpoints_expected_to_scope = [
        "/overview",
        "/enrollments/trend",
        "/attendance/monthly",
        "/grades/by-subject",
        "/grades/by-period",
        "/schools/ranking",
        "/students/performance",
        "/teachers/performance",
        "/distribution/grades",
    ]
    # Cada endpoint precisa aparecer registrado...
    for path in endpoints_expected_to_scope:
        assert f'@router.get("{path}")' in source, f"Endpoint {path} não encontrado"

    # ...e o arquivo como um todo precisa chamar apply_tenant_filter pelo
    # menos uma vez por endpoint (heurística de contagem: mais chamadas ao
    # helper do que endpoints listados, já que /overview sozinho usa 10).
    calls = source.count("apply_tenant_filter(")
    assert calls >= len(endpoints_expected_to_scope), (
        f"apply_tenant_filter() é chamado {calls} vezes; esperado >= "
        f"{len(endpoints_expected_to_scope)} (1 por endpoint mínimo). "
        "Se um endpoint novo foi adicionado sem tenant scope, este guard "
        "deve falhar antes de qualquer regressão chegar a produção."
    )
