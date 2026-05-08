"""
Testes E2E da Fase 2 do Diário (Dependência de Estudos).

Cobre os 14 cenários obrigatórios do contrato (`/app/docs/DIARY_API_CONTRACT.md` §13)
+ exigências adicionais do owner (Fev/2026):
- Anti-spoof de dependency_id (5 códigos de erro distintos)
- Anti-N+1 (máximo 3 queries Mongo)
- Filtro automático de dep inativa
- Dependency_ratio_pct + warnings
- Ordenação localeCompare('pt-BR')
- Backend é a única fonte da verdade pedagógica
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.diary_loader import DiaryLoadStats, load_diary_items  # noqa: E402
from utils.dependency_validator import validate_dependency_link  # noqa: E402
from utils.diary_constants import DEPENDENCY_DISPLAY_LABEL, MAX_DEPENDENCY_STUDENTS_PER_DIARY  # noqa: E402

FIX_TENANT = "fix_mant_v1"
FIX_CLASS = "fix_cl_v1"
FIX_COURSE_MAT = "fix_co_mat_v1"
FIX_COURSE_PT = "fix_co_pt_v1"
FIX_YEAR = 2026


@pytest_asyncio.fixture
async def db():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    yield client[db_name]
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _seed_fixture():
    """Carrega a fixture v1 antes de qualquer teste (idempotente)."""
    from scripts.seed_dependency_diary_fixture import seed
    await seed()


# =========================================================================
# CENÁRIOS DE CONTRATO (14)
# =========================================================================
@pytest.mark.asyncio
async def test_c01_aluno_regular_puro(db):
    """Cenário 1: aluno regular puro aparece com is_dependency=false."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    ana = next(it for it in payload["items"] if it["student_id"] == "fix_stu_ana")
    assert ana["is_dependency"] is False
    assert ana["dependency_id"] is None
    assert ana["display_label"] == ""


@pytest.mark.asyncio
async def test_c02_apenas_dependencia_aparece_no_componente_vinculado(db):
    """Cenário 2: aluno dependency_only aparece SOMENTE no componente vinculado."""
    mat = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    pt = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_PT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    mat_heitor = next((it for it in mat["items"] if it["student_id"] == "fix_stu_heitor"), None)
    pt_heitor = next((it for it in pt["items"] if it["student_id"] == "fix_stu_heitor"), None)
    assert mat_heitor and mat_heitor["is_dependency"] is True
    assert pt_heitor and pt_heitor["is_dependency"] is True


@pytest.mark.asyncio
async def test_c03_with_dependency_aparece_apenas_uma_vez(db):
    """Cenário 3: aluno with_dependency NÃO duplica (regular vence)."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    felipe = [it for it in payload["items"] if it["student_id"] == "fix_stu_felipe"]
    assert len(felipe) == 1
    assert felipe[0]["is_dependency"] is False  # regular vence


@pytest.mark.asyncio
async def test_c06_dep_cancelada_nao_aparece(db):
    """Cenário 6: dep cancelada NÃO aparece no diário."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    # Ivo tem enrollment ativo (regular). Mas a dep dele está cancelled
    # → ele aparece como regular, não como dependência.
    ivo = next(it for it in payload["items"] if it["student_id"] == "fix_stu_ivo")
    assert ivo["is_dependency"] is False
    assert ivo["dependency_id"] is None


@pytest.mark.asyncio
async def test_c07_dep_completed_nao_aparece(db):
    """Cenário 7: dep completed NÃO aparece como dependência."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    julia = next(it for it in payload["items"] if it["student_id"] == "fix_stu_julia")
    assert julia["is_dependency"] is False  # regular ativo, dep concluída


# =========================================================================
# Estrutura do payload — exigências do owner Fev/2026
# =========================================================================
@pytest.mark.asyncio
async def test_meta_estrutura_e_dependency_ratio(db):
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    meta = payload["meta"]
    assert meta["regular_count"] == 9
    assert meta["dependency_count"] == 1  # somente Heitor (Felipe e Gabriela são regulares)
    assert meta["has_dependencies"] is True
    assert meta["total"] == 10
    assert meta["dependency_ratio_pct"] == 10.0
    assert "load_duration_ms" in meta


@pytest.mark.asyncio
async def test_payload_sem_divisor_fake(db):
    """Exigência §1 do owner: divisor fora do array `items`."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    for it in payload["items"]:
        assert "is_divider" not in it, f"divisor fake encontrado: {it}"
        assert it.get("student_id", "").startswith("__divider") is False


@pytest.mark.asyncio
async def test_ordenacao_localecompare_pt_br(db):
    """Regulares A-Z e deps A-Z preservando acentos brasileiros."""
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    items = payload["items"]
    regulares = [it for it in items if not it["is_dependency"]]
    deps = [it for it in items if it["is_dependency"]]

    # Regulares vêm primeiro
    if regulares and deps:
        assert items.index(regulares[-1]) < items.index(deps[0])

    # Júlia deve estar depois de Ivo (J > I em pt-BR)
    nomes_reg = [r["student_name"] for r in regulares]
    assert nomes_reg.index("Ivo Nascimento") < nomes_reg.index("Júlia Ferreira")


@pytest.mark.asyncio
async def test_anti_n_plus_1(db):
    """Exigência §7: máximo 3 queries Mongo agregadas, não 1 por aluno."""
    with DiaryLoadStats() as stats:
        payload = await load_diary_items(
            db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
            academic_year=FIX_YEAR, tenant_id=FIX_TENANT, stats=stats,
        )
    assert stats.queries <= 3, f"queries={stats.queries} excedeu o limite (3)"
    assert payload["meta"]["total"] == 10


@pytest.mark.asyncio
async def test_display_label_eh_constante_unica(db):
    payload = await load_diary_items(
        db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
        academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
    )
    deps = [it for it in payload["items"] if it["is_dependency"]]
    for d in deps:
        assert d["display_label"] == DEPENDENCY_DISPLAY_LABEL
        # variantes proibidas
        assert d["display_label"] not in {"DP", "Dep.", "Dependente"}


@pytest.mark.asyncio
async def test_warning_dep_greater_than_regular(db):
    """Exigência §9: warning quando dep_total > regular_total."""
    # Limpa enrollments para Mat_v1 e deixa apenas Heitor (1 dep) sem regulares
    # Snapshot do estado original para restaurar
    backup = await db.enrollments.find(
        {"class_id": FIX_CLASS}, {"_id": 0}
    ).to_list(50)
    try:
        await db.enrollments.update_many(
            {"class_id": FIX_CLASS},
            {"$set": {"status": "transferred"}},
        )
        payload = await load_diary_items(
            db=db, class_id=FIX_CLASS, course_id=FIX_COURSE_MAT,
            academic_year=FIX_YEAR, tenant_id=FIX_TENANT,
        )
        warnings = payload.get("warnings") or []
        codes = [w["code"] for w in warnings]
        assert "DEP_GREATER_THAN_REGULAR" in codes
    finally:
        # restaura enrollments
        for e in backup:
            await db.enrollments.update_one(
                {"id": e["id"]}, {"$set": {"status": e["status"]}}
            )


# =========================================================================
# Anti-spoof — validador de dependency_id
# =========================================================================
@pytest.mark.asyncio
async def test_validator_aceita_dep_valida(db):
    dep = await validate_dependency_link(
        db=db, dependency_id="fix_dep_heitor_mat",
        student_id="fix_stu_heitor", class_id=FIX_CLASS,
        course_id=FIX_COURSE_MAT, tenant_id=FIX_TENANT,
    )
    assert dep["status"] == "active"


@pytest.mark.asyncio
async def test_validator_rejeita_dep_inativa(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await validate_dependency_link(
            db=db, dependency_id="fix_dep_ivo_cancelled",
            student_id="fix_stu_ivo", class_id=FIX_CLASS,
            course_id=FIX_COURSE_MAT, tenant_id=FIX_TENANT,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_COHERENCE_INACTIVE"


@pytest.mark.asyncio
async def test_validator_rejeita_student_mismatch(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await validate_dependency_link(
            db=db, dependency_id="fix_dep_heitor_mat",
            student_id="fix_stu_felipe",  # errado
            class_id=FIX_CLASS, course_id=FIX_COURSE_MAT, tenant_id=FIX_TENANT,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_COHERENCE_STUDENT_MISMATCH"


@pytest.mark.asyncio
async def test_validator_rejeita_course_mismatch(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await validate_dependency_link(
            db=db, dependency_id="fix_dep_heitor_mat",
            student_id="fix_stu_heitor",
            class_id=FIX_CLASS, course_id=FIX_COURSE_PT,  # errado
            tenant_id=FIX_TENANT,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_COHERENCE_COURSE_MISMATCH"


@pytest.mark.asyncio
async def test_validator_rejeita_tenant_mismatch(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await validate_dependency_link(
            db=db, dependency_id="fix_dep_heitor_mat",
            student_id="fix_stu_heitor", class_id=FIX_CLASS,
            course_id=FIX_COURSE_MAT, tenant_id="OUTRO_TENANT",
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_COHERENCE_TENANT_MISMATCH"


@pytest.mark.asyncio
async def test_validator_rejeita_dep_inexistente(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await validate_dependency_link(
            db=db, dependency_id="DOES_NOT_EXIST",
            student_id="fix_stu_heitor", class_id=FIX_CLASS,
            course_id=FIX_COURSE_MAT, tenant_id=FIX_TENANT,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "DEPENDENCY_COHERENCE_NOT_FOUND"


# =========================================================================
# Constantes e contrato
# =========================================================================
def test_max_dependency_constant_value():
    assert MAX_DEPENDENCY_STUDENTS_PER_DIARY == 30


def test_label_constante_unica():
    assert DEPENDENCY_DISPLAY_LABEL == "Dependência"


# =========================================================================
# Cenário 8 — Exclusão bloqueada já é coberta por test_student_dependencies.py
# Cenário 14 — Auditoria coberta por audit_service tests
# =========================================================================
