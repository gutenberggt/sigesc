"""F5 — Cobertura Curricular v2 baseada em Plano de Ensino + content_entries.

Endpoint aditivo: ``GET /api/curriculum/coverage-v2``.

A cobertura legada permanece disponível durante o rollout. Nesta versão:
- denominador = itens do Plano de Ensino Bimestral publicado da versão curricular vigente;
- numerador = relações estruturadas explícitas em ``content_entries``;
- ``learning_objects`` nunca compõe o numerador e é apenas contabilizado como
  histórico não estruturado;
- sem plano publicado não existe percentual de cobertura;
- tenant, turma e versão são resolvidos fail-closed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime as dt
from functools import wraps
import re
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from auth_middleware import AuthMiddleware
from tenant_scope import INVALID_TENANT_SENTINEL, assert_same_tenant, get_mantenedora_scope, is_super_admin

READ_PERMISSION_KEY = "nav-curriculum-button"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _grade_number(value: str) -> int:
    match = re.search(r"(\d+)", _norm(value))
    return int(match.group(1)) if match else 0


def _entry_component(entry: Mapping[str, Any]) -> str:
    return _norm(entry.get("component_id") or entry.get("course_id"))


def _entry_adaptation_ids(entry: Mapping[str, Any]) -> set[str]:
    links = entry.get("curriculum_links") or {}
    raw = links.get("adaptation_ids")
    if raw is None:
        raw = entry.get("adaptation_ids")
    return {_norm(item) for item in (raw or []) if _norm(item)}


def _entry_plan_item_ids(entry: Mapping[str, Any]) -> set[str]:
    links = entry.get("curriculum_links") or {}
    return {_norm(item) for item in (links.get("teaching_plan_item_ids") or []) if _norm(item)}


def _tenant_id(user: Mapping[str, Any], request: Request) -> str:
    tenant_id = get_mantenedora_scope(user, request)
    if not tenant_id or tenant_id == INVALID_TENANT_SENTINEL:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CURRICULUM_TENANT_REQUIRED",
                "message": "Selecione uma mantenedora para consultar a cobertura curricular.",
            },
        )
    return _norm(tenant_id)


async def _require_read(db, request: Request) -> dict:
    """Replica a leitura permissiva do Currículo v2, honrando revogação explícita."""
    user = await AuthMiddleware.get_current_user(request)
    if is_super_admin(user):
        return user
    role = user.get("role")
    try:
        override = await db.permission_overrides.find_one(
            {"item_key": READ_PERMISSION_KEY, "role": role}, {"_id": 0, "visible": 1}
        )
    except Exception:
        override = None
    if override is not None and not override.get("visible"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado pela Matriz de Permissões ({READ_PERMISSION_KEY} × {role})",
        )
    return user


async def _calendar_windows(db, tenant_id: str, academic_year: int) -> dict[int, tuple[str, str]]:
    cal = await db.calendario_letivo.find_one(
        {
            "ano_letivo": academic_year,
            "$or": [
                {"mantenedora_id": tenant_id},
                {"mantenedora_id": None},
                {"mantenedora_id": {"$exists": False}},
            ],
        },
        {"_id": 0},
    )
    result: dict[int, tuple[str, str]] = {}
    if not cal:
        return result
    for bimestre in range(1, 5):
        start = _norm(cal.get(f"bimestre_{bimestre}_inicio"))[:10]
        end = _norm(cal.get(f"bimestre_{bimestre}_fim"))[:10]
        if start and end:
            result[bimestre] = (start, end)
    return result


def _bim_for_date(target_date: str, windows: Mapping[int, tuple[str, str]]) -> Optional[int]:
    ymd = _norm(target_date)[:10]
    if not ymd:
        return None
    for bimestre, (start, end) in windows.items():
        if start <= ymd <= end:
            return bimestre
    return None


def _bim_state(bimestre: int, windows: Mapping[int, tuple[str, str]], today_ymd: str) -> str:
    if bimestre not in windows:
        return "em_andamento"
    start, end = windows[bimestre]
    if today_ymd < start:
        return "futuro"
    if today_ymd > end:
        return "fechado"
    return "em_andamento"


def _days_between(start: str, end: str) -> int:
    try:
        return max((dt.fromisoformat(end).date() - dt.fromisoformat(start).date()).days, 0)
    except Exception:
        return 0


def _forecast(total: int, covered: int, bimestre: int, state: str, windows: Mapping[int, tuple[str, str]], today_ymd: str) -> str:
    if state == "futuro":
        return "nao_iniciado"
    if total <= 0:
        return "nao_iniciado"
    pct = covered / total
    if state == "fechado":
        return "no_ritmo" if pct >= 0.9 else "fechado_critico"
    if bimestre not in windows:
        if pct >= 0.9:
            return "no_ritmo"
        if pct >= 0.5:
            return "em_risco"
        return "nao_cumpre"
    start, end = windows[bimestre]
    total_days = max(_days_between(start, end), 1)
    elapsed = min(_days_between(start, today_ymd), total_days)
    if elapsed <= 0:
        return "no_ritmo"
    projected = pct * (total_days / elapsed)
    if projected >= 1.0:
        return "no_ritmo"
    if projected >= 0.7:
        return "em_risco"
    return "nao_cumpre"


def _status_by_pct(pct: float, state: str) -> str:
    if state == "futuro":
        return "nao_iniciado"
    if pct >= 90:
        return "ok"
    if pct >= 70:
        return "atencao"
    return "critico"


async def _component_map(db, component_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not component_ids:
        return {}
    docs = await db.curriculum_components.find(
        {"id": {"$in": sorted(component_ids)}},
        {"_id": 0, "id": 1, "codigo": 1, "nome": 1},
    ).to_list(length=len(component_ids))
    return {doc["id"]: doc for doc in docs}


async def _class_map(db, tenant_id: str, academic_year: int, class_id: Optional[str], user: Mapping[str, Any], request: Request) -> dict[str, dict[str, Any]]:
    if class_id:
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(404, "Turma não encontrada")
        assert_same_tenant(class_doc, user, request)
        return {class_id: class_doc}
    docs = await db.classes.find(
        {"mantenedora_id": tenant_id, "academic_year": academic_year}, {"_id": 0}
    ).to_list(length=5000)
    return {_norm(doc.get("id")): doc for doc in docs if _norm(doc.get("id"))}


def _grade_of(class_doc: Optional[Mapping[str, Any]]) -> str:
    if not class_doc:
        return ""
    return _norm(class_doc.get("grade_level") or class_doc.get("series") or class_doc.get("serie"))


def _missing_plan_response(*, tenant_id: str, academic_year: int, class_id: Optional[str], component_id: Optional[str], windows: Mapping[int, tuple[str, str]], curriculum_version_id: Optional[str], reason: str, structured_outside_plan: int = 0, historical_unstructured: int = 0) -> dict[str, Any]:
    return {
        "version": "coverage_v2",
        "coverage_state": "plano_inexistente",
        "message": reason,
        "scope": {
            "mantenedora_id": tenant_id,
            "academic_year": academic_year,
            "class_id": class_id,
            "component_id": component_id,
        },
        "curriculum_version_id": curriculum_version_id,
        "totals": {
            "total": 0,
            "covered": 0,
            "pct": None,
            "percentage_available": False,
            "critical_rows": 0,
            "closed_critical": 0,
            "pending_count": 0,
            "worked_outside_plan_count": structured_outside_plan,
            "historical_unstructured_count": historical_unstructured,
            "plan_missing": True,
        },
        "classification_counts": {
            "previsto_trabalhado": 0,
            "previsto_pendente": 0,
            "trabalhado_fora_plano": structured_outside_plan,
            "historico_nao_estruturado": historical_unstructured,
            "periodo_futuro": 0,
            "plano_inexistente": 1,
        },
        "rows": [],
        "bimestre_windows": {str(k): list(v) for k, v in windows.items()},
    }


async def calculate_curriculum_coverage_v2(
    db,
    current_user: Mapping[str, Any],
    request: Request,
    *,
    class_id: Optional[str] = None,
    academic_year: Optional[int] = None,
    component_id: Optional[str] = None,
    today_ymd: Optional[str] = None,
) -> dict[str, Any]:
    tenant_id = _tenant_id(current_user, request)
    class_doc = None
    if class_id:
        class_doc = await db.classes.find_one({"id": class_id}, {"_id": 0})
        if not class_doc:
            raise HTTPException(404, "Turma não encontrada")
        assert_same_tenant(class_doc, current_user, request)
    year = int(academic_year or (class_doc or {}).get("academic_year") or date.today().year)
    windows = await _calendar_windows(db, tenant_id, year)
    today_value = today_ymd or date.today().isoformat()

    version = await db.curriculum_versions.find_one(
        {"mantenedora_id": tenant_id, "academic_year": year, "status": "published"},
        {"_id": 0},
        sort=[("revision", -1)],
    )
    if not version:
        return _missing_plan_response(
            tenant_id=tenant_id,
            academic_year=year,
            class_id=class_id,
            component_id=component_id,
            windows=windows,
            curriculum_version_id=None,
            reason="Não há versão curricular publicada para o ano letivo consultado.",
        )

    class_by_id = await _class_map(db, tenant_id, year, class_id, current_user, request)
    selected_grade = _grade_of(class_doc)
    plan_query: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "academic_year": year,
        "curriculum_version_id": version["id"],
        "status": "published",
    }
    if component_id:
        plan_query["component_id"] = component_id
    if selected_grade:
        plan_query["grade_scope"] = selected_grade
    plans = await db.teaching_plans.find(plan_query, {"_id": 0}).sort(
        [("component_id", 1), ("bimestre", 1), ("revision", -1)]
    ).to_list(length=5000)

    content_query: dict[str, Any] = {
        "mantenedora_id": tenant_id,
        "academic_year": year,
        "deleted": {"$ne": True},
    }
    if class_id:
        content_query["class_id"] = class_id
    if component_id:
        content_query["$or"] = [{"component_id": component_id}, {"course_id": component_id}]
    entries = await db.content_entries.find(
        content_query,
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "component_id": 1,
            "course_id": 1,
            "date": 1,
            "adaptation_ids": 1,
            "curriculum_binding": 1,
            "curriculum_links": 1,
        },
    ).to_list(length=50000)

    # Só classes comprovadamente pertencentes ao tenant entram na cobertura de rede.
    if not class_id:
        entries = [entry for entry in entries if _norm(entry.get("class_id")) in class_by_id]

    structured_entries: list[dict[str, Any]] = []
    unstructured_entries: list[dict[str, Any]] = []
    for entry in entries:
        adaptations = _entry_adaptation_ids(entry)
        plan_items = _entry_plan_item_ids(entry)
        enriched = {
            **entry,
            "_adaptations": adaptations,
            "_plan_items": plan_items,
            "_grade": _grade_of(class_by_id.get(_norm(entry.get("class_id")))) if not class_id else selected_grade,
            "_bimestre": (entry.get("curriculum_binding") or {}).get("bimestre") or _bim_for_date(entry.get("date"), windows),
        }
        if adaptations or plan_items:
            structured_entries.append(enriched)
        else:
            unstructured_entries.append(enriched)

    legacy_query: dict[str, Any] = {"academic_year": year}
    allowed_class_ids = sorted(class_by_id.keys())
    if class_id:
        legacy_query["class_id"] = class_id
    elif allowed_class_ids:
        legacy_query["class_id"] = {"$in": allowed_class_ids}
    else:
        legacy_query["class_id"] = {"$in": []}
    if component_id:
        legacy_query["course_id"] = component_id
    legacy_historical_count = await db.learning_objects.count_documents(legacy_query)
    historical_unstructured_total = len(unstructured_entries) + int(legacy_historical_count)

    if not plans:
        return _missing_plan_response(
            tenant_id=tenant_id,
            academic_year=year,
            class_id=class_id,
            component_id=component_id,
            windows=windows,
            curriculum_version_id=version["id"],
            reason="Não há Plano de Ensino Bimestral publicado para o escopo consultado.",
            structured_outside_plan=len(structured_entries),
            historical_unstructured=historical_unstructured_total,
        )

    # Expande planos por faixa para preservar o contrato visual componente→ano→bimestre.
    row_plans: dict[tuple[str, int, str], dict[str, Any]] = {}
    for plan in plans:
        grades = [selected_grade] if selected_grade else [_norm(g) for g in (plan.get("grade_scope") or []) if _norm(g)]
        for grade in grades:
            key = (_norm(plan.get("component_id")), int(plan.get("bimestre") or 0), grade)
            if key in row_plans and row_plans[key].get("id") != plan.get("id"):
                raise HTTPException(
                    409,
                    detail={
                        "code": "COVERAGE_PLAN_SCOPE_AMBIGUOUS",
                        "message": "Há mais de um Plano de Ensino publicado aplicável ao mesmo componente/faixa/bimestre.",
                        "component_id": key[0],
                        "bimestre": key[1],
                        "grade": key[2],
                    },
                )
            row_plans[key] = plan

    component_ids = {key[0] for key in row_plans}
    component_ids.update(_entry_component(entry) for entry in structured_entries if _entry_component(entry))
    components = await _component_map(db, component_ids)

    rows: list[dict[str, Any]] = []
    all_plan_adaptations: set[str] = set()
    all_plan_item_ids: set[str] = set()
    consumed_structured_ids: set[str] = set()
    future_item_count = 0

    for (row_component, bimestre, grade), plan in sorted(
        row_plans.items(), key=lambda item: (components.get(item[0][0], {}).get("codigo") or item[0][0], _grade_number(item[0][2]), item[0][1])
    ):
        items = list(plan.get("items") or [])
        item_by_id = {_norm(item.get("id")): item for item in items if _norm(item.get("id"))}
        item_by_adaptation: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            adaptation_id = _norm(item.get("adaptation_id"))
            if adaptation_id:
                item_by_adaptation[adaptation_id].append(item)
                all_plan_adaptations.add(adaptation_id)
            if _norm(item.get("id")):
                all_plan_item_ids.add(_norm(item.get("id")))

        row_entries = [
            entry for entry in structured_entries
            if _entry_component(entry) == row_component
            and int(entry.get("_bimestre") or 0) == bimestre
            and (not grade or _norm(entry.get("_grade")) == grade)
        ]
        covered_item_ids: set[str] = set()
        outside_refs: set[str] = set()
        for entry in row_entries:
            direct_ids = entry["_plan_items"] & set(item_by_id)
            covered_item_ids.update(direct_ids)
            for adaptation_id in entry["_adaptations"]:
                matches = item_by_adaptation.get(adaptation_id) or []
                if matches:
                    covered_item_ids.update(_norm(item.get("id")) for item in matches if _norm(item.get("id")))
                else:
                    outside_refs.add(adaptation_id)
            for plan_item_id in entry["_plan_items"] - set(item_by_id):
                outside_refs.add(f"plan_item:{plan_item_id}")
            if direct_ids or any(aid in item_by_adaptation for aid in entry["_adaptations"]):
                if entry.get("id"):
                    consumed_structured_ids.add(_norm(entry.get("id")))

        pending_items = [item for item_id, item in item_by_id.items() if item_id not in covered_item_ids]
        state = _bim_state(bimestre, windows, today_value)
        total = len(item_by_id)
        covered = len(covered_item_ids)
        pct = round((covered / total * 100) if total else 0.0, 1)
        if state == "futuro":
            future_item_count += total
        component = components.get(row_component) or {}
        row_historical = sum(
            1 for entry in unstructured_entries
            if _entry_component(entry) == row_component
            and int(entry.get("_bimestre") or 0) == bimestre
            and (not grade or _norm(entry.get("_grade")) == grade)
        )
        rows.append({
            "coverage_version": "v2",
            "coverage_state": "periodo_futuro" if state == "futuro" else ("previsto_pendente" if pending_items else "previsto_trabalhado"),
            "teaching_plan_id": plan.get("id"),
            "teaching_plan_revision": plan.get("revision"),
            "curriculum_version_id": version["id"],
            "component_id": row_component,
            "componente_codigo": component.get("codigo") or row_component,
            "componente_nome": component.get("nome"),
            "grade_scope": grade,
            "ano": _grade_number(grade),
            "bimestre": bimestre,
            "total": total,
            "covered": covered,
            "pct": pct,
            "status": _status_by_pct(pct, state),
            "forecast": _forecast(total, covered, bimestre, state, windows, today_value),
            "bimestre_state": state,
            "pending": [
                {
                    "plan_item_id": item.get("id"),
                    "adaptation_id": item.get("adaptation_id"),
                    "codigo": item.get("skill_code_snapshot"),
                    "descricao": item.get("skill_description_snapshot"),
                }
                for item in pending_items[:20]
            ],
            "pending_count": len(pending_items),
            "worked_outside_plan": sorted(outside_refs)[:20],
            "worked_outside_plan_count": len(outside_refs),
            "historical_unstructured_count": row_historical,
        })

    outside_entry_ids = {
        _norm(entry.get("id")) for entry in structured_entries
        if _norm(entry.get("id")) and _norm(entry.get("id")) not in consumed_structured_ids
    }
    # Referências estruturadas explicitamente fora do plano vigente também contam.
    outside_refs_global: set[str] = set()
    for entry in structured_entries:
        outside_refs_global.update(entry["_adaptations"] - all_plan_adaptations)
        outside_refs_global.update(f"plan_item:{pid}" for pid in entry["_plan_items"] - all_plan_item_ids)
    worked_outside_plan_count = max(len(outside_entry_ids), len(outside_refs_global))

    eligible_rows = [row for row in rows if row["bimestre_state"] != "futuro"]
    total = sum(row["total"] for row in eligible_rows)
    covered = sum(row["covered"] for row in eligible_rows)
    pct_total = round((covered / total * 100) if total else 0.0, 1)
    pending_total = sum(row["pending_count"] for row in eligible_rows)
    closed_critical = sum(1 for row in eligible_rows if row["forecast"] == "fechado_critico")
    critical_rows = sum(1 for row in eligible_rows if row["status"] == "critico")

    return {
        "version": "coverage_v2",
        "coverage_state": "ok",
        "scope": {
            "mantenedora_id": tenant_id,
            "academic_year": year,
            "class_id": class_id,
            "component_id": component_id,
        },
        "curriculum_version_id": version["id"],
        "curriculum_version_revision": version.get("revision"),
        "totals": {
            "total": total,
            "covered": covered,
            "pct": pct_total,
            "percentage_available": True,
            "critical_rows": critical_rows,
            "closed_critical": closed_critical,
            "pending_count": pending_total,
            "worked_outside_plan_count": worked_outside_plan_count,
            "historical_unstructured_count": historical_unstructured_total,
            "plan_missing": False,
        },
        "classification_counts": {
            "previsto_trabalhado": covered,
            "previsto_pendente": pending_total,
            "trabalhado_fora_plano": worked_outside_plan_count,
            "historico_nao_estruturado": historical_unstructured_total,
            "periodo_futuro": future_item_count,
            "plano_inexistente": 0,
        },
        "rows": rows,
        "bimestre_windows": {str(k): list(v) for k, v in windows.items()},
    }


def build_curriculum_coverage_v2_router(db) -> APIRouter:
    router = APIRouter(tags=["Cobertura Curricular v2"])

    @router.get("/coverage-v2")
    async def curriculum_coverage_v2(
        request: Request,
        class_id: Optional[str] = None,
        academic_year: Optional[int] = Query(default=None, ge=2000, le=2200),
        component_id: Optional[str] = None,
    ):
        user = await _require_read(db, request)
        return await calculate_curriculum_coverage_v2(
            db,
            user,
            request,
            class_id=class_id,
            academic_year=academic_year,
            component_id=component_id,
        )

    return router


def install_curriculum_coverage_v2_setup(curriculum_v2_mod: Any) -> None:
    """Anexa a F5 ao router curricular sem substituir a cobertura legada."""
    if getattr(curriculum_v2_mod, "_canonical_curriculum_coverage_v2_installed", False):
        return
    original_setup = curriculum_v2_mod.setup_router

    @wraps(original_setup)
    def setup_router(db):
        configured = original_setup(db)
        if not getattr(configured, "_canonical_curriculum_coverage_v2_routes", False):
            configured.include_router(build_curriculum_coverage_v2_router(db))
            configured._canonical_curriculum_coverage_v2_routes = True
        return configured

    curriculum_v2_mod.setup_router = setup_router
    curriculum_v2_mod._canonical_curriculum_coverage_v2_installed = True
