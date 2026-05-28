"""
Integrity Report da Grade Horária (Fase 6 — Mai/2026).

Diretriz crítica do owner (resumida):
  "Sem grade correta: completude é falsa, alertas mentem, PDFs mentem,
   validação vira teatro. A grade horária agora é infraestrutura crítica."

Detecta inconsistências em `teacher_class_assignments`:

  1. TEMPORAL_GAP       — Mesmo (class, component, weekday, aula) com
                          intervalo sem cobertura entre fim de um e início
                          de outro.
  2. OVERLAP            — Mesmo (class, weekday, aula) com 2+ assignments
                          ativos simultaneamente (sem substituição).
  3. EXPIRED_NO_SUCCESSOR — `valid_until < reference_date` e nenhum sucessor.
  4. ORPHAN_TEACHER     — `teacher_id` não existe em `users` ou está apagado.
  5. INVERTED_VALIDITY  — `valid_until < valid_from`.
  6. DUPLICATE_SLOT     — Duplicação dentro do mesmo `weekly_slots[]`.
  7. TEACHER_DOUBLE_BOOKING — Mesmo professor em 2 turmas diferentes no
                          mesmo (weekday, aula) com vigências sobrepostas.
  8. CLASS_WITHOUT_ASSIGNMENT — Turma ativa do ano corrente SEM nenhum
                          assignment vigente (zero responsabilidade).

Severidades:
  high   — bloqueia confiança institucional (gap, overlap, double_booking).
  medium — exige revisão (expired_no_successor, orphan_teacher).
  low    — higiene de dados (duplicate_slot, inverted_validity).
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date as date_cls, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

# Workflow states (Fase 6b — UI operacional do owner)
VALID_ISSUE_STATUSES = ("open", "in_analysis", "resolved", "wont_fix")

KIND_SEVERITY = {
    "TEMPORAL_GAP": SEVERITY_HIGH,
    "OVERLAP": SEVERITY_HIGH,
    "TEACHER_DOUBLE_BOOKING": SEVERITY_HIGH,
    "CLASS_WITHOUT_ASSIGNMENT": SEVERITY_HIGH,
    "EXPIRED_NO_SUCCESSOR": SEVERITY_MEDIUM,
    "ORPHAN_TEACHER": SEVERITY_MEDIUM,
    "DUPLICATE_SLOT": SEVERITY_LOW,
    "INVERTED_VALIDITY": SEVERITY_LOW,
}

KIND_RECOMMENDATION_PT = {
    "TEMPORAL_GAP": "Crie um assignment cobrindo o intervalo sem responsável ou retroceda o valid_until anterior.",
    "OVERLAP": "Defina is_substitute=True para o cobertor temporário OU encerre valid_until do anterior.",
    "TEACHER_DOUBLE_BOOKING": "Mesmo professor não pode reger 2 turmas simultaneamente. Reatribua.",
    "CLASS_WITHOUT_ASSIGNMENT": "Turma do ano corrente sem nenhum responsável. Cadastre a grade.",
    "EXPIRED_NO_SUCCESSOR": "Assignment expirou sem sucessor. Estenda valid_until OU cadastre o sucessor.",
    "ORPHAN_TEACHER": "Professor não existe ou foi apagado. Reatribua o assignment a um usuário válido.",
    "DUPLICATE_SLOT": "Mesmo (weekday, aula_numero) duplicado em weekly_slots[]. Limpe.",
    "INVERTED_VALIDITY": "valid_until < valid_from — período inválido. Corrija manualmente.",
}


def _parse_iso(d: Optional[str]) -> Optional[date_cls]:
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _date_le(a: Optional[date_cls], b: Optional[date_cls]) -> bool:
    """a <= b, tratando None do `valid_until` como infinito."""
    if a is None:
        return False
    if b is None:
        return True
    return a <= b


def _periods_overlap(
    af: Optional[date_cls], au: Optional[date_cls],
    bf: Optional[date_cls], bu: Optional[date_cls],
) -> bool:
    """Sobreposição com semântica `valid_until=None` = vigente."""
    if af is None or bf is None:
        return False
    end_a = au if au is not None else date_cls.max
    end_b = bu if bu is not None else date_cls.max
    return af <= end_b and bf <= end_a


async def compute_integrity_report(
    db,
    *,
    school_id: Optional[str] = None,
    class_id: Optional[str] = None,
    reference_date: Optional[str] = None,
    academic_year: Optional[int] = None,
) -> dict:
    ref_date = _parse_iso(reference_date) or datetime.now(timezone.utc).date()
    issues: list[dict] = []

    # ---- Filtro base ----
    base_filter: dict = {"deleted": False}
    if school_id:
        base_filter["school_id"] = school_id
    if class_id:
        base_filter["class_id"] = class_id

    assignments = await db.teacher_class_assignments.find(base_filter, {"_id": 0}).to_list(20000)

    # =========================================================================
    # 1. ORPHAN_TEACHER — coletar teacher_ids e resolver
    # =========================================================================
    teacher_ids = {a.get("teacher_id") for a in assignments if a.get("teacher_id")}
    valid_users = set()
    if teacher_ids:
        cursor = db.users.find(
            {"id": {"$in": list(teacher_ids)}},
            {"_id": 0, "id": 1, "deleted": 1, "status": 1},
        )
        async for u in cursor:
            if u.get("deleted"):
                continue
            if u.get("status") == "inactive":
                continue
            valid_users.add(u["id"])

    for a in assignments:
        tid = a.get("teacher_id")
        if not tid:
            continue
        if tid not in valid_users:
            issues.append({
                "kind": "ORPHAN_TEACHER",
                "severity": SEVERITY_MEDIUM,
                "class_id": a.get("class_id"),
                "class_name": a.get("class_name"),
                "school_id": a.get("school_id"),
                "component_id": a.get("component_id"),
                "assignment_ids": [a["id"]],
                "teacher_id": tid,
                "recommendation": KIND_RECOMMENDATION_PT["ORPHAN_TEACHER"],
            })

    # =========================================================================
    # 2. INVERTED_VALIDITY + DUPLICATE_SLOT (por assignment isoladamente)
    # =========================================================================
    for a in assignments:
        vf = _parse_iso(a.get("valid_from"))
        vu = _parse_iso(a.get("valid_until"))
        if vf and vu and vu < vf:
            issues.append({
                "kind": "INVERTED_VALIDITY",
                "severity": SEVERITY_LOW,
                "class_id": a.get("class_id"),
                "class_name": a.get("class_name"),
                "school_id": a.get("school_id"),
                "component_id": a.get("component_id"),
                "assignment_ids": [a["id"]],
                "valid_from": a.get("valid_from"),
                "valid_until": a.get("valid_until"),
                "recommendation": KIND_RECOMMENDATION_PT["INVERTED_VALIDITY"],
            })

        # Duplicate slot dentro do mesmo array
        slot_keys = [(s.get("weekday"), s.get("aula_numero")) for s in (a.get("weekly_slots") or [])]
        seen = set()
        dups = set()
        for k in slot_keys:
            if k in seen:
                dups.add(k)
            seen.add(k)
        if dups:
            issues.append({
                "kind": "DUPLICATE_SLOT",
                "severity": SEVERITY_LOW,
                "class_id": a.get("class_id"),
                "class_name": a.get("class_name"),
                "school_id": a.get("school_id"),
                "component_id": a.get("component_id"),
                "assignment_ids": [a["id"]],
                "duplicated_slots": [{"weekday": k[0], "aula_numero": k[1]} for k in dups],
                "recommendation": KIND_RECOMMENDATION_PT["DUPLICATE_SLOT"],
            })

    # =========================================================================
    # 3. OVERLAP — mesmo (class_id, weekday, aula_numero) com 2 ativos simultâneos
    # =========================================================================
    slot_index: dict = defaultdict(list)  # (class_id, weekday, aula) -> [(assignment, slot)]
    for a in assignments:
        for s in (a.get("weekly_slots") or []):
            key = (a.get("class_id"), s.get("weekday"), s.get("aula_numero"))
            slot_index[key].append((a, s))

    overlap_keys: dict = defaultdict(set)  # key -> {assignment_ids}
    for key, items in slot_index.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a1, _ = items[i]
                a2, _ = items[j]
                if a1.get("is_substitute") or a2.get("is_substitute"):
                    continue
                if _periods_overlap(
                    _parse_iso(a1.get("valid_from")), _parse_iso(a1.get("valid_until")),
                    _parse_iso(a2.get("valid_from")), _parse_iso(a2.get("valid_until")),
                ):
                    overlap_keys[key].add(a1["id"])
                    overlap_keys[key].add(a2["id"])
    for key, aids in overlap_keys.items():
        cid, wd, aula = key
        sample = next(a for a in assignments if a["id"] == next(iter(aids)))
        issues.append({
            "kind": "OVERLAP",
            "severity": SEVERITY_HIGH,
            "class_id": cid,
            "class_name": sample.get("class_name"),
            "school_id": sample.get("school_id"),
            "component_id": sample.get("component_id"),
            "weekday": wd,
            "aula_numero": aula,
            "assignment_ids": sorted(aids),
            "recommendation": KIND_RECOMMENDATION_PT["OVERLAP"],
        })

    # =========================================================================
    # 4. TEMPORAL_GAP + EXPIRED_NO_SUCCESSOR (por chave funcional)
    # =========================================================================
    # Agrupa por (class, component, weekday, aula) e ordena por valid_from.
    func_groups: dict = defaultdict(list)
    for a in assignments:
        for s in (a.get("weekly_slots") or []):
            k = (a.get("class_id"), a.get("component_id"), s.get("weekday"), s.get("aula_numero"))
            func_groups[k].append({
                "assignment": a,
                "vf": _parse_iso(a.get("valid_from")),
                "vu": _parse_iso(a.get("valid_until")),
            })

    for key, group in func_groups.items():
        group.sort(key=lambda x: (x["vf"] or date_cls.min))
        # GAP entre i e i+1
        for i in range(len(group) - 1):
            a_end = group[i]["vu"]
            b_start = group[i + 1]["vf"]
            if a_end is None:  # ativo + outro à frente já é OVERLAP (tratado)
                continue
            if b_start is None:
                continue
            # gap = a_end+1 .. b_start-1
            from datetime import timedelta
            if a_end + timedelta(days=1) < b_start:
                cid, comp, wd, aula = key
                issues.append({
                    "kind": "TEMPORAL_GAP",
                    "severity": SEVERITY_HIGH,
                    "class_id": cid,
                    "class_name": group[i]["assignment"].get("class_name"),
                    "school_id": group[i]["assignment"].get("school_id"),
                    "component_id": comp,
                    "weekday": wd,
                    "aula_numero": aula,
                    "gap_from": (a_end + timedelta(days=1)).isoformat(),
                    "gap_to": (b_start - timedelta(days=1)).isoformat(),
                    "assignment_ids": [group[i]["assignment"]["id"], group[i + 1]["assignment"]["id"]],
                    "recommendation": KIND_RECOMMENDATION_PT["TEMPORAL_GAP"],
                })
        # EXPIRED_NO_SUCCESSOR: último valid_until < ref_date AND nenhum sucessor cobre ref_date
        covers_ref = any(
            (g["vf"] is not None and g["vf"] <= ref_date) and
            (g["vu"] is None or g["vu"] >= ref_date)
            for g in group
        )
        if not covers_ref and group:
            last = max(group, key=lambda x: x["vu"] or date_cls.max)
            if last["vu"] is not None and last["vu"] < ref_date:
                cid, comp, wd, aula = key
                issues.append({
                    "kind": "EXPIRED_NO_SUCCESSOR",
                    "severity": SEVERITY_MEDIUM,
                    "class_id": cid,
                    "class_name": last["assignment"].get("class_name"),
                    "school_id": last["assignment"].get("school_id"),
                    "component_id": comp,
                    "weekday": wd,
                    "aula_numero": aula,
                    "expired_at": last["vu"].isoformat(),
                    "days_since_expiration": (ref_date - last["vu"]).days,
                    "assignment_ids": [last["assignment"]["id"]],
                    "recommendation": KIND_RECOMMENDATION_PT["EXPIRED_NO_SUCCESSOR"],
                })

    # =========================================================================
    # 5. TEACHER_DOUBLE_BOOKING — mesmo professor em 2 turmas diferentes
    #    no mesmo (weekday, aula) com vigências sobrepostas
    # =========================================================================
    teacher_slots: dict = defaultdict(list)
    for a in assignments:
        tid = a.get("teacher_id")
        if not tid:
            continue
        if a.get("is_substitute"):
            continue
        for s in (a.get("weekly_slots") or []):
            teacher_slots[(tid, s.get("weekday"), s.get("aula_numero"))].append(a)
    for key, lst in teacher_slots.items():
        if len(lst) < 2:
            continue
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a1, a2 = lst[i], lst[j]
                if a1.get("class_id") == a2.get("class_id"):
                    continue  # mesma turma = OVERLAP, já tratado
                if _periods_overlap(
                    _parse_iso(a1.get("valid_from")), _parse_iso(a1.get("valid_until")),
                    _parse_iso(a2.get("valid_from")), _parse_iso(a2.get("valid_until")),
                ):
                    tid, wd, aula = key
                    issues.append({
                        "kind": "TEACHER_DOUBLE_BOOKING",
                        "severity": SEVERITY_HIGH,
                        "teacher_id": tid,
                        "teacher_name": a1.get("teacher_name"),
                        "weekday": wd,
                        "aula_numero": aula,
                        "class_ids": [a1.get("class_id"), a2.get("class_id")],
                        "class_names": [a1.get("class_name"), a2.get("class_name")],
                        "assignment_ids": sorted([a1["id"], a2["id"]]),
                        "school_id": a1.get("school_id"),
                        "recommendation": KIND_RECOMMENDATION_PT["TEACHER_DOUBLE_BOOKING"],
                    })

    # =========================================================================
    # 6. CLASS_WITHOUT_ASSIGNMENT — turma ativa do ano corrente sem grade.
    #
    # [Fev/2026 — Hotfix B do owner]
    # WRITE_PATH != READ_PATH: a UI atual de "Horário de Aulas" grava em
    # `class_schedules` (legacy), mas este painel lia APENAS
    # `teacher_class_assignments` (novo). Resultado: ~todas turmas viravam
    # falso positivo de severidade crítica.
    # Correção: união das duas coleções como fonte de "tem grade?".
    # Migração definitiva legacy→novo é DÉBITO ARQUITETURAL EXPLÍCITO,
    # tratado em sprint dedicado (NÃO desativar este caminho híbrido até lá).
    # =========================================================================
    class_filter: dict = {}
    if school_id:
        class_filter["school_id"] = school_id
    if class_id:
        class_filter["id"] = class_id
    if academic_year is not None:
        class_filter["academic_year"] = academic_year
    else:
        class_filter["academic_year"] = ref_date.year
    classes_active = await db.classes.find(
        class_filter, {"_id": 0, "id": 1, "name": 1, "school_id": 1, "academic_year": 1, "status": 1},
    ).to_list(5000)
    # Apenas turmas ativas (status==active ou sem status)
    classes_active = [c for c in classes_active if (c.get("status") or "active") == "active"]

    classes_with_assignment_new = {a.get("class_id") for a in assignments if not a.get("deleted")}
    # Fonte legacy: cada doc em class_schedules representa um bloco
    # (turma × dia × horário) com professor + componente cadastrados.
    # Para o painel, basta `distinct(class_id)` — não precisamos do conteúdo.
    try:
        legacy_class_ids = await db.class_schedules.distinct("class_id", {})
        classes_with_schedule_legacy = {cid for cid in legacy_class_ids if cid}
    except Exception as e:
        # Se a coleção legacy não existir (ambiente novo), só não há cobertura adicional.
        logger.warning(f"[grade_integrity] class_schedules.distinct falhou: {e}")
        classes_with_schedule_legacy = set()
    classes_with_any_schedule = classes_with_assignment_new | classes_with_schedule_legacy

    for c in classes_active:
        if c["id"] not in classes_with_any_schedule:
            issues.append({
                "kind": "CLASS_WITHOUT_ASSIGNMENT",
                "severity": SEVERITY_HIGH,
                "class_id": c["id"],
                "class_name": c.get("name"),
                "school_id": c.get("school_id"),
                "academic_year": c.get("academic_year"),
                "assignment_ids": [],
                "recommendation": KIND_RECOMMENDATION_PT["CLASS_WITHOUT_ASSIGNMENT"],
            })

    # =========================================================================
    # FINGERPRINT + HUMAN COPY + WORKFLOW STATE MERGE
    # =========================================================================
    for it in issues:
        it["fingerprint"] = _compute_fingerprint(it)
        it["human_title"], it["human_summary"], it["impact"] = _humanize(it)

    fingerprints = [it["fingerprint"] for it in issues]
    states = await _load_states(db, fingerprints)
    affected_schools = set()
    affected_teachers = set()
    affected_classes = set()
    for it in issues:
        st = states.get(it["fingerprint"]) or {}
        it["state"] = {
            "status": st.get("status", "open"),
            "assigned_to_user_id": st.get("assigned_to_user_id"),
            "assigned_to_name": st.get("assigned_to_name"),
            "notes": st.get("notes", []),
            "updated_at": st.get("updated_at"),
            "resolved_at": st.get("resolved_at"),
            "resolved_by_user_id": st.get("resolved_by_user_id"),
        }
        if it.get("school_id"):
            affected_schools.add(it["school_id"])
        if it.get("teacher_id"):
            affected_teachers.add(it["teacher_id"])
        if it.get("class_id"):
            affected_classes.add(it["class_id"])

    # =========================================================================
    # SUMÁRIO
    # =========================================================================
    by_severity = defaultdict(int)
    by_kind = defaultdict(int)
    by_status = defaultdict(int)
    for it in issues:
        by_severity[it["severity"]] += 1
        by_kind[it["kind"]] += 1
        by_status[it["state"]["status"]] += 1
    return {
        "reference_date": ref_date.isoformat(),
        "filters": {
            "school_id": school_id, "class_id": class_id,
            "academic_year": class_filter.get("academic_year"),
        },
        "summary": {
            "total_issues": len(issues),
            "by_severity": dict(by_severity),
            "by_kind": dict(by_kind),
            "by_status": dict(by_status),
            "affected_schools": len(affected_schools),
            "affected_teachers": len(affected_teachers),
            "affected_classes": len(affected_classes),
            "classes_scanned": len({a.get("class_id") for a in assignments}) + len(
                [c for c in classes_active if c["id"] not in classes_with_any_schedule]
            ),
            "assignments_scanned": len(assignments),
        },
        "issues": issues,
    }


# ============================================================================
# FINGERPRINT — chave determinística por issue para persistir workflow state
# ============================================================================
def _compute_fingerprint(issue: dict) -> str:
    """Constrói uma chave estável por conteúdo da issue.

    Mesma issue detectada amanhã → mesmo fingerprint → estado workflow
    persiste. Issue resolvida desaparece naturalmente.
    """
    kind = issue.get("kind", "")
    parts: list = [kind]
    if kind == "TEACHER_DOUBLE_BOOKING":
        parts += [
            issue.get("teacher_id", ""),
            str(issue.get("weekday", "")),
            str(issue.get("aula_numero", "")),
            "|".join(sorted(issue.get("assignment_ids", []))),
        ]
    elif kind in ("OVERLAP", "TEMPORAL_GAP", "EXPIRED_NO_SUCCESSOR"):
        parts += [
            issue.get("class_id", ""),
            issue.get("component_id", ""),
            str(issue.get("weekday", "")),
            str(issue.get("aula_numero", "")),
            "|".join(sorted(issue.get("assignment_ids", []))),
        ]
    elif kind == "CLASS_WITHOUT_ASSIGNMENT":
        parts += [issue.get("class_id", "")]
    elif kind in ("ORPHAN_TEACHER", "DUPLICATE_SLOT", "INVERTED_VALIDITY"):
        parts += ["|".join(sorted(issue.get("assignment_ids", [])))]
    return hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:16]


def _humanize(issue: dict) -> tuple[str, str, str]:
    """Devolve (título, sumário, impacto) em PT — diretriz do owner:
    'O sistema NÃO deve parecer um log técnico'.
    """
    k = issue.get("kind")
    if k == "TEACHER_DOUBLE_BOOKING":
        return (
            "Conflito de Professor",
            f"{issue.get('teacher_name') or 'Professor(a)'} está vinculado(a) "
            f"a {' e '.join(issue.get('class_names', []) or ['—'])} "
            f"no mesmo horário (segunda a sábado é dia {issue.get('weekday')}, "
            f"aula {issue.get('aula_numero')}).",
            "O sistema não consegue determinar autoria válida do diário. "
            "Validação institucional fica comprometida.",
        )
    if k == "OVERLAP":
        return (
            "Sobreposição na Grade",
            f"Turma {issue.get('class_name') or '—'} tem dois (ou mais) "
            f"professores ativos simultaneamente no slot "
            f"(dia {issue.get('weekday')}, aula {issue.get('aula_numero')}) — "
            "sem nenhum marcado como substituto.",
            "Calendário operacional não consegue computar completude. "
            "Há ambiguidade institucional.",
        )
    if k == "TEMPORAL_GAP":
        return (
            "Lacuna na Cobertura",
            f"Entre {issue.get('gap_from')} e {issue.get('gap_to')}, a turma "
            f"{issue.get('class_name')} fica sem responsável para o componente "
            f"{issue.get('component_id')} (dia {issue.get('weekday')}, "
            f"aula {issue.get('aula_numero')}).",
            "Dias dentro da lacuna aparecerão como 'sem aula esperada' "
            "indevidamente — alarmes silenciados.",
        )
    if k == "CLASS_WITHOUT_ASSIGNMENT":
        return (
            "Turma sem Grade Cadastrada",
            f"Turma {issue.get('class_name')} do ano letivo "
            f"{issue.get('academic_year')} não possui nenhum vínculo "
            "professor↔componente↔horário cadastrado.",
            "Todos os dias aparecem como 'sem aula esperada' — frequência "
            "e conteúdo não são exigidos pela arquitetura.",
        )
    if k == "EXPIRED_NO_SUCCESSOR":
        return (
            "Vínculo Expirado sem Substituto",
            f"O vínculo da turma {issue.get('class_name')} expirou em "
            f"{issue.get('expired_at')} "
            f"({issue.get('days_since_expiration')} dias atrás) e nenhum "
            "sucessor foi cadastrado para o slot.",
            "Aulas posteriores à expiração aparecem como 'sem aula esperada' "
            "incorretamente.",
        )
    if k == "ORPHAN_TEACHER":
        return (
            "Professor Inexistente",
            f"O vínculo da turma {issue.get('class_name')} aponta para um "
            f"usuário ({issue.get('teacher_id')}) que não existe ou foi "
            "desativado.",
            "Atribuição de autoria fica órfã. Validação institucional "
            "registra responsável vazio.",
        )
    if k == "DUPLICATE_SLOT":
        return (
            "Slots Duplicados",
            f"O vínculo da turma {issue.get('class_name')} contém o mesmo "
            f"(dia da semana, aula) duplicado em weekly_slots[].",
            "Higiene de dados. Pode causar contagem dupla em relatórios.",
        )
    if k == "INVERTED_VALIDITY":
        return (
            "Período de Validade Invertido",
            f"O vínculo da turma {issue.get('class_name')} tem "
            f"valid_until ({issue.get('valid_until')}) menor que valid_from "
            f"({issue.get('valid_from')}).",
            "Vínculo logicamente impossível. Não cobre nenhum dia.",
        )
    return (k or "Inconsistência", "—", "—")


# ============================================================================
# WORKFLOW STATE — collection `grade_integrity_issue_states`
# ============================================================================
async def _load_states(db, fingerprints: list[str]) -> dict[str, dict]:
    if not fingerprints:
        return {}
    cursor = db.grade_integrity_issue_states.find(
        {"fingerprint": {"$in": fingerprints}}, {"_id": 0},
    )
    return {doc["fingerprint"]: doc async for doc in cursor}


async def update_issue_state(
    db, *,
    fingerprint: str,
    status: Optional[str] = None,
    note_text: Optional[str] = None,
    assigned_to_user_id: Optional[str] = None,
    assigned_to_name: Optional[str] = None,
    user: dict,
) -> dict:
    """Cria/atualiza estado workflow da issue. Notes são append-only."""
    if status is not None and status not in VALID_ISSUE_STATUSES:
        raise ValueError(f"INVALID_STATUS: {status} ∉ {VALID_ISSUE_STATUSES}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    set_fields: dict = {"updated_at": now, "updated_by_user_id": user.get("id")}
    push_fields: dict = {}
    if status is not None:
        set_fields["status"] = status
        if status == "resolved":
            set_fields["resolved_at"] = now
            set_fields["resolved_by_user_id"] = user.get("id")
        elif status == "open":
            set_fields["resolved_at"] = None
            set_fields["resolved_by_user_id"] = None
    if assigned_to_user_id is not None:
        set_fields["assigned_to_user_id"] = assigned_to_user_id
        set_fields["assigned_to_name"] = assigned_to_name

    if note_text:
        push_fields["notes"] = {
            "text": note_text[:2000],
            "by_user_id": user.get("id"),
            "by_user_name": user.get("full_name") or user.get("email"),
            "at": now,
        }

    update_doc: dict = {"$set": set_fields, "$setOnInsert": {
        "fingerprint": fingerprint,
        "created_at": now,
        "created_by_user_id": user.get("id"),
    }}
    if push_fields:
        update_doc["$push"] = push_fields

    await db.grade_integrity_issue_states.update_one(
        {"fingerprint": fingerprint}, update_doc, upsert=True,
    )
    return await db.grade_integrity_issue_states.find_one(
        {"fingerprint": fingerprint}, {"_id": 0},
    )


async def ensure_integrity_indexes(db) -> None:
    await db.grade_integrity_issue_states.create_index(
        "fingerprint", unique=True, background=True,
    )
    await db.grade_integrity_issue_states.create_index("status", background=True)
    await db.grade_integrity_issue_states.create_index("updated_at", background=True)
