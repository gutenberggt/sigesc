"""
Validação automática de planos de execução do MongoDB.

[Fev/2026] Garante que queries críticas usem índice (IXSCAN) e nunca caiam em COLLSCAN.

Modos de uso:
  1. Em testes (pytest): força `assert_uses_index(plan)` em queries do diário/autocomplete.
  2. Em ambiente DEV: ao subir o backend (env QUERY_INDEX_GUARD=1), valida queries críticas
     e falha o startup se cair em COLLSCAN.

Em produção: validação só roda se explicitamente habilitada (não impacta latência runtime).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class QueryNotUsingIndexError(RuntimeError):
    """Query crítica caiu em COLLSCAN ou sem winning plan indexado."""


def _walk_stages(stage: Optional[dict]) -> list[str]:
    """Coleta nomes de stages recursivamente (winningPlan + inputStage)."""
    if not stage:
        return []
    out = [stage.get("stage", "")]
    if "inputStage" in stage:
        out.extend(_walk_stages(stage["inputStage"]))
    if "inputStages" in stage:
        for s in stage["inputStages"]:
            out.extend(_walk_stages(s))
    return out


def assert_uses_index(
    explain_output: dict,
    *,
    expected_index_name: Optional[str] = None,
    description: str = "query crítica",
) -> None:
    """Levanta `QueryNotUsingIndexError` se o plano não usa IXSCAN.

    Args:
        explain_output: resultado de `coll.find(...).explain("executionStats")`.
        expected_index_name: se passado, valida também que o índice usado é exatamente este.
        description: para mensagem de erro.
    """
    qp = explain_output.get("queryPlanner", {})
    winning = qp.get("winningPlan", {})
    stages = _walk_stages(winning)
    if "COLLSCAN" in stages:
        raise QueryNotUsingIndexError(
            f"[{description}] caiu em COLLSCAN — query crítica DEVE usar índice. "
            f"winningPlan stages: {stages}"
        )
    if "IXSCAN" not in stages:
        raise QueryNotUsingIndexError(
            f"[{description}] não usa IXSCAN. Stages encontradas: {stages}"
        )
    if expected_index_name:
        # Procura indexName no plano
        names = _collect_index_names(winning)
        if expected_index_name not in names:
            raise QueryNotUsingIndexError(
                f"[{description}] usa índice diferente do esperado. "
                f"Esperado: '{expected_index_name}', encontrado: {names}"
            )


def _collect_index_names(stage: Optional[dict]) -> list[str]:
    if not stage:
        return []
    out = []
    if stage.get("indexName"):
        out.append(stage["indexName"])
    if "inputStage" in stage:
        out.extend(_collect_index_names(stage["inputStage"]))
    if "inputStages" in stage:
        for s in stage["inputStages"]:
            out.extend(_collect_index_names(s))
    return out


# ============================================================================
# Lista de queries críticas — guard de startup em DEV.
# Chamar `await validate_critical_queries(db)` no startup quando QUERY_INDEX_GUARD=1.
# ============================================================================
async def validate_critical_queries(db) -> None:
    """Valida que queries críticas usam índices esperados.

    Roda apenas se env `QUERY_INDEX_GUARD=1`. Falha startup se alguma query
    crítica cair em COLLSCAN.
    """
    if os.environ.get("QUERY_INDEX_GUARD", "").strip() != "1":
        return  # produção / opt-in apenas

    critical = [
        {
            "name": "students.autocomplete (prefix nome_busca)",
            "coll": db.students,
            "filter": {"mantenedora_id": "test", "nome_busca": {"$regex": "^ana"}},
            "expected_index": None,  # algum índice serve, contanto que IXSCAN
        },
        {
            "name": "student_dependencies.diary_load (tenant+class+course+status)",
            "coll": db.student_dependencies,
            "filter": {
                "mantenedora_id": "test", "class_id": "x", "course_id": "y",
                "status": "active",
            },
            "expected_index": "ix_dep_tenant_class_course_status",
        },
    ]

    for q in critical:
        try:
            plan = await q["coll"].find(q["filter"]).explain()
            assert_uses_index(plan, expected_index_name=q["expected_index"], description=q["name"])
            logger.info("[query-guard] OK: %s usa índice", q["name"])
        except QueryNotUsingIndexError:
            raise  # fail startup
        except Exception as e:
            # Coleção vazia ou outro erro do Mongo — não falha startup.
            logger.warning("[query-guard] %s pulado: %s", q["name"], e)
