"""Policy overlay reutilizável para reconstrução administrativa por turma-espelho.

Este arquivo é executado depois do motor base
``sibling_class_reconstruction_preflight_readonly.py`` e redefine apenas a
semântica de origem/destino:

- origem é o conteúdo institucional da turma-espelho, independentemente da
  autoria do professor-alvo;
- destino pode ser resolvido por vínculo DVD único OU por vínculo legado único;
- nenhuma escrita é introduzida.

O overlay permanece genérico: não contém nomes de professor, escola ou turma.
"""

_R2_BASE_RESOLVE_CONTEXT = _resolve_context
_R2_LEGACY_ASSIGNMENTS = []


def _resolve_context(db, case):
    global _R2_LEGACY_ASSIGNMENTS
    context = _R2_BASE_RESOLVE_CONTEXT(db, case)
    _R2_LEGACY_ASSIGNMENTS = list(context.get("legacy_assignments") or [])
    return context


def _source_attribution_kind(row, actor_ids, assignment_ids):
    if _teacher_attributed(row, actor_ids, assignment_ids):
        return "TARGET_TEACHER"
    explicit = False
    for field in ACTOR_FIELDS:
        if _sid(row.get(field)):
            explicit = True
            break
    if _sid(row.get("assignment_id")):
        explicit = True
    return "OTHER_ACTOR" if explicit else "UNATTRIBUTED_LEGACY"


def _source_items_by_month(
    canonical,
    legacy,
    *,
    actor_ids,
    assignment_ids,
    months,
):
    """Usa a turma B como espelho curricular, não como prova de autoria.

    Todos os conteúdos de Matemática da turma-espelho entram como candidatos.
    Autoria é preservada apenas como classificação agregada de provenance.
    Qualquer multiplicidade na mesma data continua fail-closed.
    """
    result = {}
    for month in months:
        c_rows = [r for r in canonical if (_iso_day(r.get("date")) or "").startswith(month)]
        l_rows = [r for r in legacy if (_iso_day(r.get("date")) or "").startswith(month)]

        tagged = [(r, "content_entries") for r in c_rows] + [
            (r, "learning_objects") for r in l_rows
        ]
        by_day = defaultdict(list)
        attribution = Counter()
        for row, kind in tagged:
            day = _iso_day(row.get("date"))
            if not day:
                continue
            by_day[day].append((row, kind))
            attribution[_source_attribution_kind(row, actor_ids, assignment_ids)] += 1

        blockers = []
        if any(len(rows) != 1 for rows in by_day.values()):
            blockers.append("SOURCE_MULTIPLE_ROWS_SAME_DATE")

        items = []
        for day in sorted(by_day):
            rows = by_day[day]
            if len(rows) != 1:
                continue
            row, kind = rows[0]
            content = row.get("content") or ""
            if not str(content).strip():
                blockers.append("SOURCE_CONTENT_EMPTY")
                continue
            items.append({
                "source_date": day,
                "source_kind": kind,
                "payload_fingerprint": _payload_fingerprint(row),
                "number_of_classes": int(row.get("number_of_classes") or 1),
                "source_attribution": _source_attribution_kind(
                    row, actor_ids, assignment_ids
                ),
            })

        result[month] = {
            "items": items,
            "blockers": sorted(set(blockers)),
            "foreign_row_count": int(attribution.get("OTHER_ACTOR", 0)),
            "unattributed_legacy_row_count": int(
                attribution.get("UNATTRIBUTED_LEGACY", 0)
            ),
            "target_teacher_row_count": int(
                attribution.get("TARGET_TEACHER", 0)
            ),
            "canonical_row_count": len(c_rows),
            "legacy_row_count": len(l_rows),
        }
    return result


def _assignment_for_date(
    dvd_rows,
    *,
    class_id,
    component_id,
    teacher_id,
    target_date,
):
    """Resolve escrita canônica por DVD ou, na ausência dele, por vínculo legado.

    O vínculo legado NÃO é passado como ``assignment_id`` ao motor canônico no
    futuro apply; ele serve somente como prova read-only de que o professor-alvo
    possui um binding legado único para turma/componente/ano.
    """
    rows = [
        r for r in dvd_rows
        if _sid(r.get("class_id")) == class_id
        and _sid(r.get("teacher_id")) == teacher_id
        and r.get("deleted") is not True
        and ((r.get("diary_settings") or {}).get("enabled") is True)
        and (_component_id(r) in {"", component_id})
    ]

    def active(r):
        valid_from = _sid(r.get("valid_from"))
        valid_until = _sid(r.get("valid_until"))
        return bool(
            valid_from
            and valid_from <= target_date
            and (not valid_until or valid_until >= target_date)
        )

    def choose(candidates):
        exact = [r for r in candidates if _component_id(r) == component_id]
        return exact or [r for r in candidates if not _component_id(r)]

    active_rows = choose([r for r in rows if active(r)])
    if len(active_rows) == 1:
        return {
            "status": "RESOLVED",
            "assignment_fingerprint": _fp(active_rows[0].get("id")),
            "historical_backfill": False,
            "write_mode": "DVD_ASSIGNMENT",
        }
    if len(active_rows) > 1:
        return {
            "status": "AMBIGUOUS_ACTIVE",
            "assignment_fingerprint": None,
            "historical_backfill": False,
            "write_mode": None,
        }

    historical = choose([
        r for r in rows
        if _sid(r.get("valid_from")) and target_date < _sid(r.get("valid_from"))
    ])
    if len(historical) == 1:
        return {
            "status": "RESOLVED",
            "assignment_fingerprint": _fp(historical[0].get("id")),
            "historical_backfill": True,
            "write_mode": "DVD_HISTORICAL_BACKFILL",
        }
    if len(historical) > 1:
        return {
            "status": "AMBIGUOUS_HISTORICAL",
            "assignment_fingerprint": None,
            "historical_backfill": True,
            "write_mode": None,
        }

    legacy = [
        r for r in _R2_LEGACY_ASSIGNMENTS
        if _sid(r.get("class_id")) == class_id
        and _sid(r.get("course_id")) == component_id
        and _norm(r.get("status")) in ACTIVE_STATUSES
    ]
    if len(legacy) == 1:
        return {
            "status": "RESOLVED",
            "assignment_fingerprint": _fp(legacy[0].get("id")),
            "historical_backfill": False,
            "write_mode": "LEGACY_CANONICAL",
        }
    if len(legacy) > 1:
        return {
            "status": "AMBIGUOUS_LEGACY_BINDING",
            "assignment_fingerprint": None,
            "historical_backfill": False,
            "write_mode": None,
        }
    return {
        "status": "NOT_FOUND",
        "assignment_fingerprint": None,
        "historical_backfill": False,
        "write_mode": None,
    }


def _build_month_plan(
    *,
    month,
    source,
    target_attendance,
    occupied_dates,
    assignment_by_date,
):
    blockers = list(source.get("blockers") or [])
    source_items = list(source.get("items") or [])
    target_dates = list(target_attendance.get("dates") or [])

    if target_attendance.get("actor_conflict_dates"):
        blockers.append("TARGET_ATTENDANCE_ACTOR_CONFLICT")
    if len(source_items) != len(target_dates):
        blockers.append("MONTHLY_COUNT_MISMATCH")
    occupied_targets = sorted(set(target_dates) & occupied_dates)
    if occupied_targets:
        blockers.append("TARGET_DATE_ALREADY_HAS_CONTENT")

    unresolved = [
        day for day in target_dates
        if (assignment_by_date.get(day) or {}).get("status") != "RESOLVED"
    ]
    if unresolved:
        blockers.append("TARGET_BINDING_NOT_UNIQUE")

    write_mode_counts = Counter(
        (assignment_by_date.get(day) or {}).get("write_mode") or "UNRESOLVED"
        for day in target_dates
    )

    items = []
    if not blockers:
        for ordinal, (src, target_date) in enumerate(zip(source_items, target_dates), 1):
            binding = assignment_by_date[target_date]
            items.append({
                "ordinal": ordinal,
                "source_date": src["source_date"],
                "target_date": target_date,
                "source_kind": src["source_kind"],
                "source_attribution": src.get("source_attribution"),
                "payload_fingerprint": src["payload_fingerprint"],
                "number_of_classes": src["number_of_classes"],
                "target_binding_fingerprint": binding["assignment_fingerprint"],
                "target_write_mode": binding.get("write_mode"),
                "historical_backfill": bool(binding.get("historical_backfill")),
            })

    return {
        "month": month,
        "status": "READY_TO_APPLY" if not blockers else "BLOCKED_REVIEW_REQUIRED",
        "blockers": sorted(set(blockers)),
        "source_content_count": len(source_items),
        "source_canonical_count": int(source.get("canonical_row_count") or 0),
        "source_legacy_count": int(source.get("legacy_row_count") or 0),
        "source_target_teacher_row_count": int(
            source.get("target_teacher_row_count") or 0
        ),
        "source_other_actor_row_count": int(source.get("foreign_row_count") or 0),
        "source_unattributed_legacy_row_count": int(
            source.get("unattributed_legacy_row_count") or 0
        ),
        "target_attendance_date_count": len(target_dates),
        "target_attendance_document_count": int(
            target_attendance.get("document_count") or 0
        ),
        "target_existing_content_on_anchor_dates": len(occupied_targets),
        "target_unresolved_binding_date_count": len(unresolved),
        "target_write_mode_counts": dict(sorted(write_mode_counts.items())),
        "items": items,
    }
