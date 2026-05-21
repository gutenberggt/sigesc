"""Agregados institucionais Bolsa Família — Fase 3A (Fev/2026).

Camada analítica para o futuro Núcleo de Busca Ativa Escolar.
Owner spec:
  - UMA única pipeline `$facet` (não múltiplas queries dispersas).
  - Agregados, NÃO lista de alunos (esse é escopo do `/followup`).
  - Versionado (`stats_version`) para evolução segura.
  - Cacheável (TTL definido no router).

A engine é PURA do ponto de vista de regra agregadora — recebe `db` (motor)
e parâmetros, devolve dict pronto. Toda a inteligência de classificação
(category, severity, requires_followup) já está nos documentos seedados
das collections `attendance_frequency_reason_groups` e
`attendance_frequency_reasons`. Aqui só agregamos.
"""
from datetime import datetime, timezone
from typing import Optional


STATS_VERSION = "v1.0"
TOP_SCHOOLS_LIMIT = 10


async def compute_network_stats(
    db,
    *,
    academic_year: Optional[int] = None,
    mec_version: str = "4.2",
) -> dict:
    """Pipeline `$facet` único sobre `bolsa_familia_tracking`.

    Lookup com `attendance_frequency_reasons` para resolver categoria e
    severity. Documentos sem `reason_id` (legacy ou pendentes) NÃO entram
    no agregado — owner spec: agregados refletem dados estruturados.
    """
    match: dict = {"reason_id": {"$ne": None}}
    if academic_year is not None:
        match["academic_year"] = academic_year

    pipeline = [
        {"$match": match},
        # Resolve reason → group (precisa de 2 lookups encadeados)
        {
            "$lookup": {
                "from": "attendance_frequency_reasons",
                "localField": "reason_id",
                "foreignField": "id",
                "as": "_reason",
            }
        },
        {"$unwind": {"path": "$_reason", "preserveNullAndEmptyArrays": False}},
        {"$match": {"_reason.mec_version": mec_version}},
        {
            "$lookup": {
                "from": "attendance_frequency_reason_groups",
                "localField": "_reason.group_id",
                "foreignField": "id",
                "as": "_group",
            }
        },
        {"$unwind": {"path": "$_group", "preserveNullAndEmptyArrays": False}},
        {
            "$facet": {
                "total": [{"$count": "n"}],
                "by_category": [
                    {"$group": {"_id": "$_group.category", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ],
                "by_severity": [
                    {"$group": {"_id": "$_reason.severity_level", "count": {"$sum": 1}}},
                    {"$sort": {"_id": 1}},
                ],
                "requires_followup": [
                    {"$match": {"_reason.requires_followup": True}},
                    {"$count": "n"},
                ],
                "severity_5_plus": [
                    {"$match": {"_reason.severity_level": {"$gte": 5}}},
                    {"$count": "n"},
                ],
                "top_schools": [
                    {"$group": {"_id": "$school_id", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": TOP_SCHOOLS_LIMIT},
                ],
                "by_subcode": [
                    {
                        "$group": {
                            "_id": {
                                "subcode": "$_reason.mec_subcode",
                                "name": "$_reason.name",
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"count": -1}},
                    {"$limit": 15},
                ],
            }
        },
    ]

    raw = await db.bolsa_familia_tracking.aggregate(pipeline).to_list(1)
    facet = (raw or [{}])[0] if raw else {}

    # Métricas adicionais (Fev/2026): registros legacy e sem nenhum motivo.
    # Permite ao dashboard mostrar empty state útil ("X registros legacy
    # aguardam classificação MEC").
    legacy_match: dict = {"reason_id": None, "motive_legacy": {"$exists": True, "$ne": ""}}
    if academic_year is not None:
        legacy_match["academic_year"] = academic_year
    total_legacy = await db.bolsa_familia_tracking.count_documents(legacy_match)

    pending_match: dict = {
        "reason_id": None,
        "$or": [
            {"motive_legacy": {"$exists": False}},
            {"motive_legacy": ""},
            {"motive_legacy": None},
        ],
    }
    if academic_year is not None:
        pending_match["academic_year"] = academic_year
    total_pending = await db.bolsa_familia_tracking.count_documents(pending_match)

    def _first_count(key: str) -> int:
        arr = facet.get(key) or []
        if not arr:
            return 0
        return int(arr[0].get("n", 0))

    by_category = {
        item["_id"]: item["count"]
        for item in (facet.get("by_category") or [])
        if item.get("_id") is not None
    }
    by_severity = {
        str(item["_id"]): item["count"]
        for item in (facet.get("by_severity") or [])
        if item.get("_id") is not None
    }
    top_subcodes = [
        {
            "mec_subcode": item["_id"].get("subcode"),
            "name": item["_id"].get("name"),
            "count": item["count"],
        }
        for item in (facet.get("by_subcode") or [])
        if item.get("_id")
    ]
    top_schools_raw = facet.get("top_schools") or []
    school_ids = [s["_id"] for s in top_schools_raw if s.get("_id")]
    school_name_map: dict = {}
    if school_ids:
        cursor = db.schools.find(
            {"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}
        )
        async for s in cursor:
            school_name_map[s["id"]] = s.get("name")
    top_schools = [
        {
            "school_id": s["_id"],
            "school_name": school_name_map.get(s["_id"]),
            "count": s["count"],
        }
        for s in top_schools_raw
    ]

    return {
        "stats_version": STATS_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "academic_year": academic_year,
            "mec_version": mec_version,
        },
        "total_with_reason": _first_count("total"),
        "total_legacy": total_legacy,
        "total_pending": total_pending,
        "by_category": by_category,
        "by_severity": by_severity,
        "requires_followup": _first_count("requires_followup"),
        "severity_5_plus": _first_count("severity_5_plus"),
        "top_schools": top_schools,
        "top_subcodes": top_subcodes,
    }


async def list_followup_cases(
    db,
    *,
    academic_year: Optional[int] = None,
    mec_version: str = "4.2",
    severity_min: int = 5,
    limit: int = 200,
    category: Optional[str] = None,
    school_id: Optional[str] = None,
) -> dict:
    """Lista casos prioritários para Busca Ativa.

    Retorna trackings com `severity_level >= severity_min` OU
    `requires_followup=True`. Inclui denormalizações leves para a UI
    (student_name, school_name, reason_name) — 1 query agregada.

    Owner spec: lista limitada (`limit`), nunca dump da rede inteira.
    Filtros opcionais (Fase 3B): `category` (HEALTH, VIOLENCE, ...),
    `school_id`.
    """
    match: dict = {"reason_id": {"$ne": None}}
    if academic_year is not None:
        match["academic_year"] = academic_year
    if school_id:
        match["school_id"] = school_id

    pipeline = [
        {"$match": match},
        {
            "$lookup": {
                "from": "attendance_frequency_reasons",
                "localField": "reason_id",
                "foreignField": "id",
                "as": "_reason",
            }
        },
        {"$unwind": "$_reason"},
        {"$match": {"_reason.mec_version": mec_version}},
        {
            "$match": {
                "$or": [
                    {"_reason.severity_level": {"$gte": severity_min}},
                    {"_reason.requires_followup": True},
                ]
            }
        },
        {
            "$lookup": {
                "from": "attendance_frequency_reason_groups",
                "localField": "_reason.group_id",
                "foreignField": "id",
                "as": "_group",
            }
        },
        {"$unwind": "$_group"},
    ]
    if category:
        pipeline.append({"$match": {"_group.category": category}})
    pipeline.extend([
        {
            "$lookup": {
                "from": "students",
                "localField": "student_id",
                "foreignField": "id",
                "as": "_student",
            }
        },
        {"$unwind": {"path": "$_student", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "schools",
                "localField": "school_id",
                "foreignField": "id",
                "as": "_school",
            }
        },
        {"$unwind": {"path": "$_school", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "student_id": 1,
                "student_name": "$_student.full_name",
                "school_id": 1,
                "school_name": "$_school.name",
                "month": 1,
                "academic_year": 1,
                "reason_id": 1,
                "reason_subcode": "$_reason.mec_subcode",
                "reason_name": "$_reason.name",
                "severity_level": "$_reason.severity_level",
                "requires_followup": "$_reason.requires_followup",
                "category": "$_group.category",
                "group_name": "$_group.name",
                "notes": 1,
                "updated_at": 1,
            }
        },
        {"$sort": {"severity_level": -1, "updated_at": -1}},
        {"$limit": limit},
    ])
    cases = await db.bolsa_familia_tracking.aggregate(pipeline).to_list(limit)
    return {
        "stats_version": STATS_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "academic_year": academic_year,
            "mec_version": mec_version,
            "severity_min": severity_min,
            "limit": limit,
            "category": category,
            "school_id": school_id,
        },
        "total": len(cases),
        "cases": cases,
    }
