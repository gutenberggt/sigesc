"""R2.0c — adjudicação read-only de uma data-alvo órfã.

Executado após os overlays R2.0a/R2.0b. Não altera produção. Publica somente
metadados sanitizados, fingerprints e classificação; nunca emite plaintext
pedagógico nem IDs técnicos brutos.
"""

# ruff: noqa: F821

ORPHAN_SCHEMA = "SIBLING_CLASS_RECONSTRUCTION_ORPHAN_ADJUDICATION_V1"
ORPHAN_TARGET_CLASS = "9º ANO A"
ORPHAN_SOURCE_CLASS = "9º ANO B"
ORPHAN_DATE = "2026-04-30"
BOUNDARY_LOOKAHEAD_END = "2026-05-15"

ORPHAN_ATTENDANCE_PROJECTION = {
    "_id": 0,
    "id": 1,
    "class_id": 1,
    "course_id": 1,
    "date": 1,
    "academic_year": 1,
    "recorded_by": 1,
    "created_by": 1,
    "updated_by": 1,
    "teacher_id": 1,
    "staff_id": 1,
    "assignment_id": 1,
    "number_of_classes": 1,
    "period": 1,
    "aula_numero": 1,
    "version": 1,
    "observations": 1,
    "created_at": 1,
    "updated_at": 1,
}


def _safe_attendance_meta(row):
    return {
        "date": _iso_day(row.get("date")),
        "number_of_classes": int(row.get("number_of_classes") or 1),
        "period_present": bool(_sid(row.get("period"))),
        "aula_numero_present": row.get("aula_numero") is not None,
        "version": int(row.get("version") or 1),
        "observations_present": bool(_sid(row.get("observations"))),
        "created_at_day": _iso_day(row.get("created_at")),
        "updated_at_day": _iso_day(row.get("updated_at")),
    }


def _target_attendance_rows(db, *, class_id, math_ids, actor_ids, assignment_ids):
    rows = list(db.attendance.find(
        {
            "class_id": class_id,
            "course_id": {"$in": sorted(math_ids)},
            "date": {"$gte": "2026-04-20", "$lt": BOUNDARY_LOOKAHEAD_END},
        },
        ORPHAN_ATTENDANCE_PROJECTION,
    ))
    own = [r for r in rows if _teacher_attributed(r, actor_ids, assignment_ids)]
    own.sort(key=lambda r: _iso_day(r.get("date")) or "")
    return own


def _source_boundary_rows(db, *, class_id, math_ids):
    canonical, legacy = _find_rows_for_class(
        db,
        class_id=class_id,
        math_ids=math_ids,
        start_date="2026-04-20",
        end_date=BOUNDARY_LOOKAHEAD_END,
    )
    tagged = [(r, "content_entries") for r in canonical] + [
        (r, "learning_objects") for r in legacy
    ]
    by_day = defaultdict(list)
    for row, kind in tagged:
        day = _iso_day(row.get("date"))
        if day:
            by_day[day].append((row, kind))

    items = []
    duplicate_days = []
    for day in sorted(by_day):
        entries = by_day[day]
        if len(entries) != 1:
            duplicate_days.append(day)
            continue
        row, kind = entries[0]
        if not str(row.get("content") or "").strip():
            continue
        items.append({
            "source_date": day,
            "source_kind": kind,
            "payload_fingerprint": _payload_fingerprint(row),
            "number_of_classes": int(row.get("number_of_classes") or 1),
        })
    return items, duplicate_days


def run_orphan_adjudication(case):
    _validate_case(case)
    if case.get("strategy") != GLOBAL_STRATEGY:
        raise PreflightError("ORPHAN_GLOBAL_STRATEGY_REQUIRED")

    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "sigesc")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ping")
        db = client[db_name]
        context = _resolve_context(db, case)
        source_id = context["class_ids"][ORPHAN_SOURCE_CLASS]
        target_id = context["class_ids"][ORPHAN_TARGET_CLASS]

        # Reexecuta o manifesto global vigente para provar que a órfã continua
        # sendo exatamente 30/04 antes de qualquer adjudicação.
        global_manifest = run_live_preflight(case)
        pair = next(
            p for p in global_manifest["pairs"]
            if p["source_class"] == ORPHAN_SOURCE_CLASS
            and p["target_class"] == ORPHAN_TARGET_CLASS
        )
        plan = pair["global_plan"]
        unpaired = plan.get("unpaired_target_dates") or []
        orphan_still_exact = bool(
            len(unpaired) == 1
            and unpaired[0].get("target_date") == ORPHAN_DATE
        )

        target_rows = _target_attendance_rows(
            db,
            class_id=target_id,
            math_ids=context["math_ids"],
            actor_ids=context["actor_ids"],
            assignment_ids=context["assignment_ids"],
        )
        by_day = defaultdict(list)
        for row in target_rows:
            day = _iso_day(row.get("date"))
            if day:
                by_day[day].append(row)

        orphan_rows = by_day.get(ORPHAN_DATE, [])
        duplicate_orphan = len(orphan_rows) != 1
        orphan_meta = _safe_attendance_meta(orphan_rows[0]) if len(orphan_rows) == 1 else None

        target_dates = sorted(by_day)
        previous_dates = [d for d in target_dates if d < ORPHAN_DATE]
        next_dates = [d for d in target_dates if d > ORPHAN_DATE]
        prev_date = previous_dates[-1] if previous_dates else None
        next_date = next_dates[0] if next_dates else None
        prev_meta = (
            _safe_attendance_meta(by_day[prev_date][0])
            if prev_date and len(by_day[prev_date]) == 1 else None
        )
        next_meta = (
            _safe_attendance_meta(by_day[next_date][0])
            if next_date and len(by_day[next_date]) == 1 else None
        )

        source_items, duplicate_source_days = _source_boundary_rows(
            db,
            class_id=source_id,
            math_ids=context["math_ids"],
        )
        source_before_or_on = [i for i in source_items if i["source_date"] <= ORPHAN_DATE]
        source_after = [i for i in source_items if i["source_date"] > ORPHAN_DATE]
        last_source = source_before_or_on[-1] if source_before_or_on else None
        first_source_after = source_after[0] if source_after else None

        # Hipótese 1: artefato/duplicidade objetiva de frequência.
        duplicate_evidence = duplicate_orphan

        # Hipótese 2: aula adicional sem conteúdo novo. Só aceitamos evidência
        # estrutural quando a própria frequência fornece uma pista de sessão/carga
        # diferente do padrão vizinho; ausência de conteúdo NÃO basta.
        extra_session_evidence = False
        if orphan_meta and prev_meta:
            extra_session_evidence = bool(
                orphan_meta["aula_numero_present"]
                and orphan_meta["number_of_classes"] == 1
                and prev_meta["number_of_classes"] > 1
            )

        # Hipótese 3: deslocamento de fronteira. Exige um próximo conteúdo-fonte
        # único, após 30/04, dentro da janela curta de lookahead.
        boundary_shift_evidence = bool(
            not duplicate_source_days
            and first_source_after is not None
            and first_source_after["source_date"] < BOUNDARY_LOOKAHEAD_END
        )

        if not orphan_still_exact:
            classification = "ORPHAN_STATE_CHANGED_REVIEW_REQUIRED"
            recommended_action = "BLOCK_APPLY"
        elif duplicate_evidence:
            classification = "ORPHAN_ATTENDANCE_DUPLICATE_OR_AMBIGUOUS"
            recommended_action = "REVIEW_ATTENDANCE_BEFORE_APPLY"
        elif boundary_shift_evidence:
            classification = "ORPHAN_BOUNDARY_SHIFT_NEXT_SOURCE_AVAILABLE"
            recommended_action = "CONSIDER_EXTENDING_SOURCE_SEQUENCE_TO_NEXT_ITEM"
        elif extra_session_evidence:
            classification = "ORPHAN_EXTRA_SESSION_METADATA_SUPPORTED"
            recommended_action = "CONSIDER_SHARED_PREVIOUS_CONTENT_WITH_EXPLICIT_POLICY"
        else:
            classification = "ORPHAN_ADJUDICATION_INCONCLUSIVE"
            recommended_action = "BLOCK_ORPHAN_ONLY"

        result = {
            "schema": ORPHAN_SCHEMA,
            "case_id": _sid(case["case_id"]),
            "target_class": ORPHAN_TARGET_CLASS,
            "source_class": ORPHAN_SOURCE_CLASS,
            "orphan_date": ORPHAN_DATE,
            "r2b_manifest_hash": global_manifest["manifest_hash"],
            "orphan_still_exact": orphan_still_exact,
            "classification": classification,
            "recommended_action": recommended_action,
            "evidence": {
                "orphan_attendance_document_count": len(orphan_rows),
                "duplicate_or_ambiguous_orphan_attendance": duplicate_orphan,
                "orphan_attendance_meta": orphan_meta,
                "previous_target_date": prev_date,
                "previous_target_meta": prev_meta,
                "next_target_date_within_window": next_date,
                "next_target_meta": next_meta,
                "last_source_on_or_before_orphan": last_source,
                "first_source_after_orphan": first_source_after,
                "source_duplicate_days_in_boundary_window_count": len(duplicate_source_days),
                "boundary_lookahead_end_exclusive": BOUNDARY_LOOKAHEAD_END,
                "duplicate_evidence": duplicate_evidence,
                "extra_session_evidence": extra_session_evidence,
                "boundary_shift_evidence": boundary_shift_evidence,
            },
            "boundaries": {
                "mongo_reads_only": True,
                "production_writes": False,
                "attendance_records_read": False,
                "students_read": False,
                "enrollments_read": False,
                "grades_read": False,
                "pedagogical_plaintext_emitted": False,
                "technical_ids_emitted": False,
                "lookahead_beyond_april_readonly": True,
                "lookahead_apply_authorized": False,
            },
        }
        result["adjudication_hash"] = _canonical_hash(result)
        return result
    finally:
        client.close()
