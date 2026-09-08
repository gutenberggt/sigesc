"""Read model institucional de Conteúdo para relatórios e KPIs.

Fundação de shadow para o cutover dos consumidores que ainda leem
``learning_objects`` diretamente. Esta camada é deliberadamente READ-ONLY e não
altera nenhum consumidor operacional nesta fase.

Princípios:
- ``content_entries`` é a fonte canônica de novas escritas;
- ``learning_objects`` permanece apenas como histórico/fallback compatível;
- o corte legado→canônico NÃO é inferido de ``diary_settings.enabled``;
- os escopos de corte são entrada explícita e devem vir de um resolver DVD já
  autorizado/canônico em uma etapa posterior;
- após o corte de um escopo, ``learning_objects`` posterior ao ``valid_from`` não
  entra na projeção;
- no histórico sobreposto, o canônico prevalece sobre o legado pela mesma chave
  semântica usada pelo ``content_history_bridge``;
- o tenant é ancorado por ``classes`` e qualquer tenant explicitamente divergente
  em um registro histórico é rejeitado da projeção.

Nenhuma função deste módulo executa insert/update/replace/delete/bulk_write.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional


class ContentReportingProjectionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _component_id(item: Mapping[str, Any]) -> str:
    return _norm(item.get("component_id") or item.get("course_id"))


def _tenant_compatible(item: Mapping[str, Any], tenant_id: str) -> bool:
    """Ausência histórica é tolerada só depois de a turma ancorar o tenant.

    Um ``mantenedora_id`` explícito e divergente nunca cruza a projeção.
    """
    item_tenant = _norm(item.get("mantenedora_id"))
    return not item_tenant or item_tenant == tenant_id


def _semantic_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Mesma identidade defensiva usada pelo ``content_history_bridge``.

    A autoria aqui serve somente para reconhecer sobreposição histórica; nunca é
    usada como chave de autorização institucional.
    """
    return (
        _norm(item.get("class_id")),
        _component_id(item),
        _norm(item.get("teacher_id") or item.get("recorded_by")),
        _norm(item.get("date"))[:10],
    )


@dataclass(frozen=True)
class ContentReportingCutoverScope:
    """Escopo de corte já resolvido/validado por uma camada canônica externa.

    ``component_id=None`` representa um vínculo class-wide. Um corte específico
    de componente tem precedência sobre o class-wide da mesma turma.
    """

    class_id: str
    valid_from: str
    component_id: Optional[str] = None

    def normalized(self) -> "ContentReportingCutoverScope":
        class_id = _norm(self.class_id)
        component_id = _norm(self.component_id) or None
        valid_from = _norm(self.valid_from)[:10]
        if not class_id:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_CLASS_REQUIRED",
                "Escopo de reporting exige class_id.",
            )
        try:
            date.fromisoformat(valid_from)
        except ValueError as exc:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_VALID_FROM_INVALID",
                "Escopo de reporting exige valid_from ISO YYYY-MM-DD.",
            ) from exc
        return ContentReportingCutoverScope(
            class_id=class_id,
            component_id=component_id,
            valid_from=valid_from,
        )


def normalize_cutover_scopes(
    scopes: Iterable[ContentReportingCutoverScope],
) -> dict[tuple[str, Optional[str]], str]:
    """Normaliza cortes e falha fechado em escopos contraditórios."""
    result: dict[tuple[str, Optional[str]], str] = {}
    for raw in scopes:
        scope = raw.normalized()
        key = (scope.class_id, scope.component_id)
        current = result.get(key)
        if current and current != scope.valid_from:
            raise ContentReportingProjectionError(
                "CONTENT_REPORTING_CUTOVER_AMBIGUOUS",
                "Há mais de uma data de corte para o mesmo escopo de conteúdo.",
            )
        result[key] = scope.valid_from
    return result


def _cutover_for(
    item: Mapping[str, Any],
    cutovers: Mapping[tuple[str, Optional[str]], str],
) -> Optional[str]:
    class_id = _norm(item.get("class_id"))
    component_id = _component_id(item)
    if not class_id:
        return None
    exact = cutovers.get((class_id, component_id or None))
    if exact:
        return exact
    return cutovers.get((class_id, None))


def _canonical_public(item: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out.pop("_id", None)
    component_id = _component_id(out)
    out["component_id"] = component_id or None
    out["course_id"] = component_id or None
    out["source"] = "content_entries"
    out["legacy"] = False
    return out


def _legacy_public(item: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out.pop("_id", None)
    component_id = _component_id(out)
    out["component_id"] = component_id or None
    out["course_id"] = component_id or None
    out["source"] = "learning_objects"
    out["legacy"] = True
    out["read_only"] = True
    return out


def merge_reporting_content(
    canonical_items: Iterable[Mapping[str, Any]],
    legacy_items: Iterable[Mapping[str, Any]],
    *,
    tenant_id: str,
    cutover_scopes: Iterable[ContentReportingCutoverScope] = (),
) -> dict[str, Any]:
    """Compõe uma projeção única sem alterar origem alguma.

    A função é pura. Os cortes precisam ser explícitos: sem corte conhecido para
    um escopo, o legado continua elegível como fallback histórico. Isso evita que
    esta fundação transforme presença de dados, flags cruas ou heurísticas em uma
    decisão de cutover.
    """
    tenant = _norm(tenant_id)
    if not tenant:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_TENANT_REQUIRED",
            "A projeção institucional exige mantenedora_id explícito.",
        )

    cutovers = normalize_cutover_scopes(cutover_scopes)
    canonical: list[dict[str, Any]] = []
    rejected_tenant = 0
    for raw in canonical_items:
        if not _tenant_compatible(raw, tenant):
            rejected_tenant += 1
            continue
        canonical.append(_canonical_public(raw))

    canonical_keys = {_semantic_key(item) for item in canonical}
    legacy_kept: list[dict[str, Any]] = []
    excluded_post_cutover = 0
    duplicate_suppressed = 0
    legacy_seen = 0

    for raw in legacy_items:
        legacy_seen += 1
        if not _tenant_compatible(raw, tenant):
            rejected_tenant += 1
            continue
        item = _legacy_public(raw)
        cutover = _cutover_for(item, cutovers)
        item_date = _norm(item.get("date"))[:10]
        if cutover and item_date and item_date > cutover:
            excluded_post_cutover += 1
            continue
        if _semantic_key(item) in canonical_keys:
            duplicate_suppressed += 1
            continue
        legacy_kept.append(item)

    merged = [*canonical, *legacy_kept]
    merged.sort(
        key=lambda item: (
            item.get("aula_numero") is None,
            item.get("aula_numero") if item.get("aula_numero") is not None else 0,
        )
    )
    merged.sort(key=lambda item: _norm(item.get("date")), reverse=True)

    return {
        "items": merged,
        "total": len(merged),
        "shadow": {
            "canonical_count": len(canonical),
            "legacy_input_count": legacy_seen,
            "legacy_kept_count": len(legacy_kept),
            "legacy_excluded_post_cutover": excluded_post_cutover,
            "legacy_duplicate_suppressed": duplicate_suppressed,
            "tenant_mismatch_rejected": rejected_tenant,
            "cutover_scope_count": len(cutovers),
        },
    }


def _date_filter(start_date: Optional[str], end_date: Optional[str]) -> Optional[dict[str, str]]:
    if not start_date and not end_date:
        return None
    result: dict[str, str] = {}
    if start_date:
        result["$gte"] = _norm(start_date)[:10]
    if end_date:
        result["$lte"] = _norm(end_date)[:10]
    return result


async def list_reporting_content_shadow(
    db,
    *,
    mantenedora_id: str,
    academic_year: int,
    cutover_scopes: Iterable[ContentReportingCutoverScope] = (),
    class_ids: Optional[Iterable[str]] = None,
    component_ids: Optional[Iterable[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Carrega as duas fontes e aplica o merge read-only para observação.

    ``classes`` é a âncora tenant-scoped. Se o chamador pedir uma turma que não
    pertence à mantenedora/ano, a operação falha em vez de ampliar ou reduzir o
    escopo silenciosamente.
    """
    tenant = _norm(mantenedora_id)
    if not tenant:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_TENANT_REQUIRED",
            "A projeção institucional exige mantenedora_id explícito.",
        )
    try:
        year = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_YEAR_INVALID",
            "A projeção institucional exige academic_year válido.",
        ) from exc

    requested_classes = {_norm(value) for value in (class_ids or []) if _norm(value)}
    class_query: dict[str, Any] = {
        "mantenedora_id": tenant,
        "academic_year": year,
    }
    if requested_classes:
        class_query["id"] = {"$in": sorted(requested_classes)}
    class_docs = await db.classes.find(
        class_query, {"_id": 0, "id": 1, "mantenedora_id": 1, "academic_year": 1}
    ).to_list(5000)
    allowed_classes = {_norm(doc.get("id")) for doc in class_docs if _norm(doc.get("id"))}
    if requested_classes and allowed_classes != requested_classes:
        raise ContentReportingProjectionError(
            "CONTENT_REPORTING_CLASS_OUT_OF_SCOPE",
            "Uma ou mais turmas não pertencem à mantenedora/ano consultados.",
        )
    if not allowed_classes:
        return {
            "items": [],
            "total": 0,
            "shadow": {
                "canonical_count": 0,
                "legacy_input_count": 0,
                "legacy_kept_count": 0,
                "legacy_excluded_post_cutover": 0,
                "legacy_duplicate_suppressed": 0,
                "tenant_mismatch_rejected": 0,
                "cutover_scope_count": len(normalize_cutover_scopes(cutover_scopes)),
            },
        }

    components = {_norm(value) for value in (component_ids or []) if _norm(value)}
    date_filter = _date_filter(start_date, end_date)

    canonical_query: dict[str, Any] = {
        "mantenedora_id": tenant,
        "academic_year": year,
        "class_id": {"$in": sorted(allowed_classes)},
        "deleted": {"$ne": True},
    }
    if components:
        canonical_query["$or"] = [
            {"component_id": {"$in": sorted(components)}},
            {"course_id": {"$in": sorted(components)}},
        ]
    if date_filter:
        canonical_query["date"] = date_filter

    legacy_query: dict[str, Any] = {
        "academic_year": year,
        "class_id": {"$in": sorted(allowed_classes)},
    }
    if components:
        legacy_query["course_id"] = {"$in": sorted(components)}
    if date_filter:
        legacy_query["date"] = date_filter

    canonical = await db.content_entries.find(canonical_query, {"_id": 0}).to_list(50000)
    legacy = await db.learning_objects.find(legacy_query, {"_id": 0}).to_list(50000)
    result = merge_reporting_content(
        canonical,
        legacy,
        tenant_id=tenant,
        cutover_scopes=cutover_scopes,
    )
    result["scope"] = {
        "mantenedora_id": tenant,
        "academic_year": year,
        "class_ids": sorted(allowed_classes),
        "component_ids": sorted(components),
        "start_date": _norm(start_date)[:10] or None,
        "end_date": _norm(end_date)[:10] or None,
    }
    return result
