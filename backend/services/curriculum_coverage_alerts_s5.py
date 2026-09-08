"""S5.5 — Alertas informativos de Cobertura Curricular.

Regra institucional:
- a cobertura vem exclusivamente da F5 (Plano de Ensino publicado + content_entries);
- os prazos são contados em dias letivos reais;
- primeiros 15 dias letivos do bimestre: tolerância, sem alerta de atraso;
- depois do 15º dia letivo: cobertura < 70% gera alerta informativo;
- nos últimos 15 dias letivos: cobertura <= 50% é grave;
- sem percentual F5 não há alerta por inferência;
- bimestre futuro ou encerrado não cria/mantém alerta de atraso;
- o alerta é informativo e deduplicado, com trilha de eventos.

A audiência ativa é: professor(es) responsável(is) pelo vínculo temporal da
Turma+Componente, coordenação da escola, SEMED, gerente e administrador.
Super Administrador pode consultar o feed, mas nunca é destinatário ativo.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from typing import Any, Iterable, Mapping, Optional
import uuid

from fastapi import Request

from services.school_calendar_helper import load_school_calendar

POLICY_VERSION = "coverage-alert-v1"
ALERT_THRESHOLD_PCT = 70.0
GRAVE_THRESHOLD_PCT = 50.0
INITIAL_TOLERANCE_SCHOOL_DAYS = 15
FINAL_WINDOW_SCHOOL_DAYS = 15

NETWORK_TARGET_ROLES = frozenset({
    "admin",
    "gerente",
    "semed",
    "semed1",
    "semed2",
    "semed3",
})
COORDINATION_TARGET_ROLES = frozenset({"coordenador"})
ACTIVE_TARGET_ROLES = NETWORK_TARGET_ROLES | COORDINATION_TARGET_ROLES


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _year_filter(year: int) -> dict[str, list[Any]]:
    return {"$in": [year, str(year)]}


def _sha(*parts: Any, length: int = 40) -> str:
    raw = "::".join(_norm(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True)
class CoverageAlertDecision:
    active: bool
    severity: Optional[str]
    policy_state: str
    coverage_pct: Optional[float]
    instructional_days_total: int
    instructional_days_elapsed: int
    instructional_days_remaining: int
    period_start: Optional[str]
    period_end: Optional[str]

    @property
    def severity_rank(self) -> int:
        if self.severity == "grave":
            return 2
        if self.severity == "informativo":
            return 1
        return 0


def classify_coverage_alert(
    *,
    pct: Optional[float],
    percentage_available: bool,
    bimestre_state: str,
    today_ymd: str,
    period_start: Optional[str],
    period_end: Optional[str],
    instructional_days: Iterable[str],
) -> CoverageAlertDecision:
    """Classifica uma linha F5 usando somente dias letivos.

    O dia letivo atual conta tanto para a posição percorrida quanto para a janela
    final. Assim: 15º dia letivo ainda é tolerância; 16º pode alertar. Quando
    restam 15 dias letivos (incluindo o atual), <=50% passa a grave.
    """
    days = sorted({_norm(day)[:10] for day in instructional_days if _norm(day)})
    total = len(days)
    elapsed = sum(1 for day in days if day <= today_ymd)
    remaining = sum(1 for day in days if day >= today_ymd)

    base = dict(
        coverage_pct=(round(float(pct), 1) if pct is not None else None),
        instructional_days_total=total,
        instructional_days_elapsed=elapsed,
        instructional_days_remaining=remaining,
        period_start=_norm(period_start)[:10] or None,
        period_end=_norm(period_end)[:10] or None,
    )

    if not percentage_available or pct is None:
        return CoverageAlertDecision(False, None, "percentual_indisponivel", **base)
    if bimestre_state == "futuro" or (period_start and today_ymd < period_start):
        return CoverageAlertDecision(False, None, "periodo_futuro", **base)
    if bimestre_state == "fechado" or (period_end and today_ymd > period_end):
        return CoverageAlertDecision(False, None, "bimestre_encerrado", **base)
    if total <= 0:
        return CoverageAlertDecision(False, None, "calendario_letivo_indisponivel", **base)
    if elapsed <= INITIAL_TOLERANCE_SCHOOL_DAYS:
        return CoverageAlertDecision(False, None, "janela_inicial_tolerancia", **base)
    if float(pct) >= ALERT_THRESHOLD_PCT:
        return CoverageAlertDecision(False, None, "cobertura_adequada", **base)
    if remaining <= FINAL_WINDOW_SCHOOL_DAYS and float(pct) <= GRAVE_THRESHOLD_PCT:
        return CoverageAlertDecision(True, "grave", "grave_ultimos_15_dias", **base)
    return CoverageAlertDecision(True, "informativo", "abaixo_70_apos_tolerancia", **base)


async def _instructional_days(
    db,
    *,
    academic_year: int,
    tenant_id: str,
    school_id: Optional[str],
    period_start: str,
    period_end: str,
) -> list[str]:
    """Enumera dias letivos segundo o helper institucional do SIGESC."""
    try:
        start = date.fromisoformat(period_start)
        end = date.fromisoformat(period_end)
    except ValueError:
        return []
    if end < start:
        return []

    calendar = await load_school_calendar(
        db,
        academic_year=academic_year,
        period_from=period_start,
        period_to=period_end,
        mantenedora_id=tenant_id,
        school_id=school_id,
    )
    non_school = set((calendar.get("non_school_days") or {}).keys())
    explicit = set((calendar.get("explicit_school_days") or {}).keys())

    result: list[str] = []
    current = start
    while current <= end:
        iso = current.isoformat()
        if iso in explicit or (current.weekday() < 5 and iso not in non_school):
            result.append(iso)
        current += timedelta(days=1)
    return result


def _internal_f5_request(tenant_id: str) -> Request:
    headers = [(b"x-mantenedora-id", tenant_id.encode("utf-8"))]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/curriculum/coverage-v2",
        "raw_path": b"/api/curriculum/coverage-v2",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("internal", 443),
    })


async def _calculate_f5_for_class(
    db,
    *,
    tenant_id: str,
    academic_year: int,
    class_id: str,
    today_ymd: str,
) -> dict[str, Any]:
    """Ponte interna que reutiliza o cálculo F5 exato, sem duplicá-lo."""
    from routers.curriculum_coverage_v2 import calculate_curriculum_coverage_v2

    user = {
        "id": "__curriculum_coverage_alert_detector__",
        "role": "super_admin",
    }
    return await calculate_curriculum_coverage_v2(
        db,
        user,
        _internal_f5_request(tenant_id),
        class_id=class_id,
        academic_year=academic_year,
        today_ymd=today_ymd,
    )


def _school_ids_for_user(user: Mapping[str, Any]) -> set[str]:
    result = {_norm(value) for value in (user.get("school_ids") or []) if _norm(value)}
    if _norm(user.get("school_id")):
        result.add(_norm(user.get("school_id")))
    for link in user.get("school_links") or []:
        school_id = _norm((link or {}).get("school_id"))
        if school_id:
            result.add(school_id)
    return result


async def _responsible_teacher_ids(
    db,
    *,
    tenant_id: str,
    class_id: str,
    component_id: str,
    school_id: Optional[str],
    on_date: str,
) -> set[str]:
    """Resolve responsabilidade temporal por Turma+Componente sem inferência.

    Vínculo específico do componente tem precedência. Na ausência dele, aceita
    vínculo class-wide (regência). `diary_settings.enabled` não é requisito para
    responsabilidade institucional.
    """
    query: dict[str, Any] = {
        "class_id": class_id,
        "deleted": {"$ne": True},
        "valid_from": {"$lte": on_date},
        "$or": [
            {"valid_until": None},
            {"valid_until": {"$exists": False}},
            {"valid_until": {"$gte": on_date}},
        ],
    }
    if school_id:
        query["school_id"] = school_id
    rows = await db.teacher_class_assignments.find(
        query,
        {"_id": 0, "teacher_id": 1, "component_id": 1},
    ).to_list(length=500)
    exact = [row for row in rows if _norm(row.get("component_id")) == component_id]
    selected = exact or [row for row in rows if not _norm(row.get("component_id"))]
    teacher_ids = {_norm(row.get("teacher_id")) for row in selected if _norm(row.get("teacher_id"))}
    if not teacher_ids:
        return set()

    users = await db.users.find(
        {
            "id": {"$in": sorted(teacher_ids)},
            "status": "active",
            "mantenedora_id": tenant_id,
            "role": {"$ne": "super_admin"},
        },
        {"_id": 0, "id": 1},
    ).to_list(length=len(teacher_ids))
    return {_norm(user.get("id")) for user in users if _norm(user.get("id"))}


async def _active_targets(
    db,
    *,
    tenant_id: str,
    school_id: Optional[str],
    class_id: str,
    component_id: str,
    on_date: str,
) -> list[dict[str, Any]]:
    """Monta audiência deduplicada. Super Administrador é sempre excluído."""
    by_id: dict[str, dict[str, Any]] = {}

    teacher_ids = await _responsible_teacher_ids(
        db,
        tenant_id=tenant_id,
        class_id=class_id,
        component_id=component_id,
        school_id=school_id,
        on_date=on_date,
    )
    if teacher_ids:
        teachers = await db.users.find(
            {"id": {"$in": sorted(teacher_ids)}, "status": "active", "mantenedora_id": tenant_id},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1,
             "school_id": 1, "school_ids": 1, "school_links": 1},
        ).to_list(length=len(teacher_ids))
        for user in teachers:
            uid = _norm(user.get("id"))
            if uid and user.get("role") != "super_admin":
                by_id[uid] = {**user, "audience": ["professor_responsavel"]}

    managers = await db.users.find(
        {
            "status": "active",
            "mantenedora_id": tenant_id,
            "role": {"$in": sorted(ACTIVE_TARGET_ROLES)},
        },
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1,
         "school_id": 1, "school_ids": 1, "school_links": 1},
    ).to_list(length=1000)

    for user in managers:
        role = _norm(user.get("role"))
        uid = _norm(user.get("id"))
        if not uid or role == "super_admin":
            continue
        if role in COORDINATION_TARGET_ROLES:
            if not school_id or school_id not in _school_ids_for_user(user):
                continue
            audience = "coordenacao"
        elif role.startswith("semed"):
            audience = "semed"
        elif role == "gerente":
            audience = "gerente"
        elif role == "admin":
            audience = "administrador"
        else:
            continue
        if uid in by_id:
            current = set(by_id[uid].get("audience") or [])
            current.add(audience)
            by_id[uid]["audience"] = sorted(current)
        else:
            by_id[uid] = {**user, "audience": [audience]}

    return [by_id[key] for key in sorted(by_id)]


def _alert_scope_filter(
    *,
    tenant_id: str,
    class_id: str,
    component_id: str,
    academic_year: int,
    bimestre: int,
) -> dict[str, Any]:
    return {
        "mantenedora_id": tenant_id,
        "class_id": class_id,
        "component_id": component_id,
        "ano_letivo": academic_year,
        "bimestre": bimestre,
    }


async def _append_event(db, alert: Mapping[str, Any], event_type: str, **extra: Any) -> None:
    await db.intervention_alert_events.insert_one({
        "id": str(uuid.uuid4()),
        "alert_id": alert.get("id"),
        "mantenedora_id": alert.get("mantenedora_id"),
        "school_id": alert.get("school_id"),
        "class_id": alert.get("class_id"),
        "component_id": alert.get("component_id"),
        "ano_letivo": alert.get("ano_letivo"),
        "bimestre": alert.get("bimestre"),
        "event_type": event_type,
        "policy_version": POLICY_VERSION,
        "created_at": _now_iso(),
        **extra,
    })


async def _notify_targets(
    db,
    *,
    alert: Mapping[str, Any],
    targets: list[dict[str, Any]],
    notification_epoch: str,
) -> int:
    count = 0
    severity = alert.get("severity") or "informativo"
    title = (
        "Cobertura curricular — situação grave"
        if severity == "grave"
        else "Cobertura curricular abaixo de 70%"
    )
    pct = alert.get("last_coverage_pct")
    remaining = alert.get("instructional_days_remaining")
    code = alert.get("componente_codigo") or alert.get("component_id") or "Componente"
    class_name = alert.get("class_name") or "Turma"
    message = (
        f"{code} · {class_name} · {pct}% de cobertura. "
        f"Restam {remaining} dia(s) letivo(s) no bimestre. Alerta informativo."
    )
    link = (
        f"/admin/curriculo/cobertura?class_id={alert.get('class_id') or ''}"
        f"&component={alert.get('componente_codigo') or ''}"
        f"&ano={alert.get('ano') or ''}&bim={alert.get('bimestre') or ''}"
    )

    for user in targets:
        uid = _norm(user.get("id"))
        if not uid or user.get("role") == "super_admin":
            continue
        notification_id = _sha(alert.get("id"), uid, notification_epoch, severity)
        existing = await db.intervention_notifications.find_one(
            {"id": notification_id}, {"_id": 0, "id": 1}
        )
        if existing:
            continue
        await db.intervention_notifications.insert_one({
            "id": notification_id,
            "alert_id": alert.get("id"),
            "mantenedora_id": alert.get("mantenedora_id"),
            "school_id": alert.get("school_id"),
            "user_id": uid,
            "audience": list(user.get("audience") or []),
            "severity": severity,
            "title": title,
            "message": message,
            "link": link,
            "read": False,
            "created_at": _now_iso(),
            "policy_version": POLICY_VERSION,
        })
        count += 1
    return count


async def _resolve_scope_alert(
    db,
    *,
    scope_filter: Mapping[str, Any],
    reason: str,
    pct: Optional[float],
) -> bool:
    existing = await db.intervention_alerts.find_one(
        {**scope_filter, "resolved_at": None}, {"_id": 0}
    )
    if not existing:
        return False
    resolved_at = _now_iso()
    await db.intervention_alerts.update_one(
        {"id": existing["id"], "resolved_at": None},
        {"$set": {
            "resolved_at": resolved_at,
            "resolution_reason": reason,
            "last_coverage_pct": pct,
            "updated_at": resolved_at,
            "policy_state": reason,
        }},
    )
    await _append_event(db, existing, "resolved", reason=reason, coverage_pct=pct)
    return True


async def _resolve_class_alerts(
    db,
    *,
    tenant_id: str,
    class_id: str,
    academic_year: int,
    reason: str,
) -> int:
    alerts = await db.intervention_alerts.find(
        {
            "mantenedora_id": tenant_id,
            "class_id": class_id,
            "ano_letivo": academic_year,
            "resolved_at": None,
        },
        {"_id": 0},
    ).to_list(length=1000)
    count = 0
    for alert in alerts:
        if await _resolve_scope_alert(
            db,
            scope_filter={"id": alert["id"]},
            reason=reason,
            pct=None,
        ):
            count += 1
    return count


async def _upsert_active_alert(
    db,
    *,
    cls: Mapping[str, Any],
    row: Mapping[str, Any],
    academic_year: int,
    decision: CoverageAlertDecision,
) -> tuple[dict[str, Any], str]:
    tenant_id = _norm(cls.get("mantenedora_id"))
    class_id = _norm(cls.get("id"))
    component_id = _norm(row.get("component_id"))
    bimestre = int(row.get("bimestre") or 0)
    scope_filter = _alert_scope_filter(
        tenant_id=tenant_id,
        class_id=class_id,
        component_id=component_id,
        academic_year=academic_year,
        bimestre=bimestre,
    )
    existing = await db.intervention_alerts.find_one(scope_filter, {"_id": 0})
    now = _now_iso()
    opened = existing is None or bool(existing.get("resolved_at"))
    epoch = now if opened else _norm(existing.get("notification_epoch") or existing.get("first_detected_at") or now)
    alert_id = (existing or {}).get("id") or _sha(
        POLICY_VERSION,
        tenant_id,
        cls.get("school_id"),
        class_id,
        component_id,
        academic_year,
        bimestre,
        length=32,
    )

    doc = {
        "id": alert_id,
        "mantenedora_id": tenant_id,
        "school_id": cls.get("school_id"),
        "class_id": class_id,
        "class_name": cls.get("name"),
        "component_id": component_id,
        "componente_codigo": row.get("componente_codigo"),
        "componente_nome": row.get("componente_nome"),
        "ano": row.get("ano"),
        "ano_letivo": academic_year,
        "bimestre": bimestre,
        "status": decision.severity,
        "severity": decision.severity,
        "severity_rank": decision.severity_rank,
        "policy_state": decision.policy_state,
        "policy_version": POLICY_VERSION,
        "coverage_source": "curriculum_coverage_v2",
        "last_coverage_pct": decision.coverage_pct,
        "threshold_pct": ALERT_THRESHOLD_PCT,
        "grave_threshold_pct": GRAVE_THRESHOLD_PCT,
        "instructional_days_total": decision.instructional_days_total,
        "instructional_days_elapsed": decision.instructional_days_elapsed,
        "instructional_days_remaining": decision.instructional_days_remaining,
        "period_start": decision.period_start,
        "period_end": decision.period_end,
        "resolved_at": None,
        "resolution_reason": None,
        "updated_at": now,
        "notification_epoch": epoch,
        # Compatibilidade temporária com ranking legado. Não representa punição
        # nem escalonamento por semanas: 1=informativo, 3=grave.
        "escalation_level": 3 if decision.severity == "grave" else 1,
    }
    if opened:
        doc["first_detected_at"] = now
    else:
        doc["first_detected_at"] = existing.get("first_detected_at") or now

    if existing is None:
        doc["last_notified_at"] = None
        await db.intervention_alerts.insert_one(doc)
        await _append_event(db, doc, "created", decision=asdict(decision))
        change = "created"
    else:
        old_severity = existing.get("severity") or existing.get("status")
        await db.intervention_alerts.update_one({"id": alert_id}, {"$set": doc})
        if opened:
            await _append_event(db, doc, "reopened", decision=asdict(decision))
            change = "reopened"
        elif old_severity != decision.severity:
            await _append_event(
                db, doc, "severity_changed",
                old_severity=old_severity,
                new_severity=decision.severity,
                decision=asdict(decision),
            )
            change = "severity_changed"
        else:
            change = "updated"
    return doc, change


async def run_curriculum_coverage_alert_detection(
    db,
    *,
    academic_year: Optional[int] = None,
    tenant_id: Optional[str] = None,
    today_ymd: Optional[str] = None,
) -> dict[str, int]:
    """Executa a política S5.5 de forma idempotente e tenant-safe."""
    year = int(academic_year or date.today().year)
    today = _norm(today_ymd)[:10] or date.today().isoformat()
    # valida cedo, antes de qualquer write
    date.fromisoformat(today)

    stats = {
        "tenants_scanned": 0,
        "classes_scanned": 0,
        "rows_evaluated": 0,
        "created": 0,
        "reopened": 0,
        "updated": 0,
        "severity_changed": 0,
        "resolved": 0,
        "notified_inapp": 0,
        "notified_email": 0,
        "teacher_target_missing": 0,
        "coverage_unavailable": 0,
        "errors": 0,
    }

    tenant_ids: list[str]
    if tenant_id:
        tenant_ids = [_norm(tenant_id)]
    else:
        raw = await db.classes.distinct(
            "mantenedora_id", {"academic_year": _year_filter(year)}
        )
        tenant_ids = sorted({_norm(value) for value in raw if _norm(value)})

    calendar_cache: dict[tuple[str, str, str, str], list[str]] = {}

    for current_tenant in tenant_ids:
        if not current_tenant:
            continue
        stats["tenants_scanned"] += 1
        classes = await db.classes.find(
            {
                "mantenedora_id": current_tenant,
                "academic_year": _year_filter(year),
            },
            {"_id": 0, "id": 1, "name": 1, "school_id": 1,
             "mantenedora_id": 1, "academic_year": 1, "grade_level": 1,
             "series": 1, "serie": 1},
        ).to_list(length=10000)

        for cls in classes:
            class_id = _norm(cls.get("id"))
            if not class_id:
                stats["errors"] += 1
                continue
            stats["classes_scanned"] += 1
            try:
                coverage = await _calculate_f5_for_class(
                    db,
                    tenant_id=current_tenant,
                    academic_year=year,
                    class_id=class_id,
                    today_ymd=today,
                )
            except Exception:
                stats["errors"] += 1
                continue

            if coverage.get("coverage_state") != "ok" or not (
                (coverage.get("totals") or {}).get("percentage_available")
            ):
                stats["coverage_unavailable"] += 1
                stats["resolved"] += await _resolve_class_alerts(
                    db,
                    tenant_id=current_tenant,
                    class_id=class_id,
                    academic_year=year,
                    reason="percentual_f5_indisponivel",
                )
                continue

            windows = coverage.get("bimestre_windows") or {}
            seen_scopes: set[tuple[str, int]] = set()

            for row in coverage.get("rows") or []:
                component_id = _norm(row.get("component_id"))
                bimestre = int(row.get("bimestre") or 0)
                if not component_id or bimestre not in (1, 2, 3, 4):
                    continue
                seen_scopes.add((component_id, bimestre))
                stats["rows_evaluated"] += 1
                window = windows.get(str(bimestre)) or []
                period_start = _norm(window[0])[:10] if len(window) >= 1 else ""
                period_end = _norm(window[1])[:10] if len(window) >= 2 else ""
                cache_key = (
                    current_tenant,
                    _norm(cls.get("school_id")),
                    period_start,
                    period_end,
                )
                if cache_key not in calendar_cache:
                    if period_start and period_end:
                        calendar_cache[cache_key] = await _instructional_days(
                            db,
                            academic_year=year,
                            tenant_id=current_tenant,
                            school_id=cls.get("school_id"),
                            period_start=period_start,
                            period_end=period_end,
                        )
                    else:
                        calendar_cache[cache_key] = []

                decision = classify_coverage_alert(
                    pct=row.get("pct"),
                    percentage_available=True,
                    bimestre_state=_norm(row.get("bimestre_state")),
                    today_ymd=today,
                    period_start=period_start or None,
                    period_end=period_end or None,
                    instructional_days=calendar_cache[cache_key],
                )
                scope_filter = _alert_scope_filter(
                    tenant_id=current_tenant,
                    class_id=class_id,
                    component_id=component_id,
                    academic_year=year,
                    bimestre=bimestre,
                )
                if not decision.active:
                    if await _resolve_scope_alert(
                        db,
                        scope_filter=scope_filter,
                        reason=decision.policy_state,
                        pct=decision.coverage_pct,
                    ):
                        stats["resolved"] += 1
                    continue

                alert, change = await _upsert_active_alert(
                    db,
                    cls=cls,
                    row=row,
                    academic_year=year,
                    decision=decision,
                )
                stats[change] += 1
                targets = await _active_targets(
                    db,
                    tenant_id=current_tenant,
                    school_id=cls.get("school_id"),
                    class_id=class_id,
                    component_id=component_id,
                    on_date=today,
                )
                if not any("professor_responsavel" in (t.get("audience") or []) for t in targets):
                    stats["teacher_target_missing"] += 1
                notified = await _notify_targets(
                    db,
                    alert=alert,
                    targets=targets,
                    notification_epoch=_norm(alert.get("notification_epoch")),
                )
                if notified:
                    stats["notified_inapp"] += notified
                    notified_at = _now_iso()
                    await db.intervention_alerts.update_one(
                        {"id": alert["id"]},
                        {"$set": {"last_notified_at": notified_at, "last_notified_channel": "in_app"}},
                    )

            # Fecha alertas antigos cujo escopo deixou de existir na F5 vigente.
            active = await db.intervention_alerts.find(
                {
                    "mantenedora_id": current_tenant,
                    "class_id": class_id,
                    "ano_letivo": year,
                    "resolved_at": None,
                },
                {"_id": 0, "id": 1, "component_id": 1, "bimestre": 1},
            ).to_list(length=1000)
            for alert in active:
                key = (_norm(alert.get("component_id")), int(alert.get("bimestre") or 0))
                if key in seen_scopes:
                    continue
                if await _resolve_scope_alert(
                    db,
                    scope_filter={"id": alert["id"]},
                    reason="escopo_f5_ausente",
                    pct=None,
                ):
                    stats["resolved"] += 1

    return stats
