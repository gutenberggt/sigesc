"""
Helpers de contabilização de frequência considerando atestado médico.

Regra Feb 2026: o atestado médico vence sobre qualquer status (P/F/J)
lançado pelo professor. Ao calcular totais sintéticos (relatórios, KPIs,
declaração de frequência, boletim), um dia coberto por atestado é contado
como **presença justificada** (não-falta), espelhando o que o PDF de
frequência da turma exibe com a letra 'A'.
"""
from typing import Iterable, Optional, Set


def fetch_medical_days_for_student(
    certificates: Iterable[dict],
    candidate_dates: Optional[Set[str]] = None,
) -> Set[str]:
    """A partir de uma lista de certificates (start_date/end_date em YYYY-MM-DD),
    retorna o conjunto de datas (YYYY-MM-DD) cobertas. Se ``candidate_dates``
    é fornecido, filtra para incluir apenas datas presentes nesse conjunto
    (útil para limitar ao calendário letivo)."""
    days: Set[str] = set()
    for c in certificates or []:
        start = (c.get('start_date') or '')[:10]
        end = (c.get('end_date') or '')[:10]
        if not start or not end or start > end:
            continue
        if candidate_dates is not None:
            for d in candidate_dates:
                d10 = str(d)[:10]
                if start <= d10 <= end:
                    days.add(d10)
        else:
            # Fallback: range diário entre start e end (datas simples).
            from datetime import datetime, timedelta
            try:
                cur = datetime.strptime(start, "%Y-%m-%d")
                last = datetime.strptime(end, "%Y-%m-%d")
                while cur <= last:
                    days.add(cur.strftime("%Y-%m-%d"))
                    cur += timedelta(days=1)
            except ValueError:
                continue
    return days


def classify_with_atestado(date_iso: str, raw_status: str, medical_days: Set[str]) -> str:
    """Para uma data e status crus, retorna o status efetivo aplicando atestado.

    Resultado é um dos: 'A' (atestado), 'P' (presente), 'F' (falta),
    'J' (justificada), 'L' (atraso) ou string vazia se não classificável.
    """
    d10 = (date_iso or '')[:10]
    if d10 and d10 in medical_days:
        return 'A'
    s = (raw_status or '').strip()
    if s in ('P', 'present'):
        return 'P'
    if s in ('F', 'absent'):
        return 'F'
    if s in ('J', 'justified'):
        return 'J'
    if s in ('L', 'late'):
        return 'L'
    return ''


def compute_attendance_buckets(
    records: Iterable[dict],
    medical_days: Set[str],
) -> dict:
    """Conta P/F/J/L/A por aluno aplicando a regra de atestado.

    `records`: iterable de dicts no formato
        {'date': 'YYYY-MM-DD', 'status': 'P'|'F'|'J'|'L', 'classes': int}
    `medical_days`: conjunto de datas (YYYY-MM-DD) cobertas por atestado.

    Retorna: {'present', 'absent', 'justified', 'late', 'medical', 'total'}
    onde os totais já refletem 'A' substituindo F/P/J — atestado conta como
    não-falta. Útil para attendance_percentage = (P+J+A)/total * 100.
    """
    out = {'present': 0, 'absent': 0, 'justified': 0, 'late': 0, 'medical': 0, 'total': 0}
    for r in records or []:
        n = int(r.get('classes', 1) or 1)
        out['total'] += n
        eff = classify_with_atestado(r.get('date', ''), r.get('status', ''), medical_days)
        if eff == 'A':
            out['medical'] += n
        elif eff == 'P':
            out['present'] += n
        elif eff == 'F':
            out['absent'] += n
        elif eff == 'J':
            out['justified'] += n
        elif eff == 'L':
            out['late'] += n
    return out


def attendance_percentage(buckets: dict) -> float:
    """% considerando P + J + A no numerador (atestado é não-falta)."""
    total = buckets.get('total', 0)
    if not total:
        return 0.0
    num = buckets.get('present', 0) + buckets.get('justified', 0) + buckets.get('medical', 0)
    return round(num / total * 100, 1)


def compute_monthly_valid_absences(
    attendance_docs: Iterable[dict],
    medical_days_by_student: dict,
    student_ids: Optional[Set[str]] = None,
) -> dict:
    """Conta faltas **válidas** por aluno por mês via **consolidação diária**.

    [Fev/2026 — Spec owner Bolsa Família]
    ANTES: cada registro `by_course` faltoso virava 1 falta válida →
    inflava estatística (aluno com 1 ausência num componente perdia o dia).
    AGORA: agrupa todos os registros do MESMO `(student_id, date)`, computa
    `% presença = present / (present + absent)` e converte em status binário:
        - ≥ 50% → PRESENTE (não conta falta)
        - <  50% → FALTA (conta 1 falta no mês)

    Exclusões aplicadas POR REGISTRO antes da consolidação (não contaminam
    o denominador):
      - `dependency_id` no registro → aula de dependência, ignorada
      - data coberta por atestado médico → registro inteiro vence
      - `status ∈ {J, justified}` → justificada pelo professor
      - `invalidated`/`invalid` no registro → componente invalidado

    Equivalência com `attendance_type='daily'`: docs daily têm 1 registro
    por (sid, date), então a consolidação devolve o mesmo resultado
    anterior (F isolado → 0% presença → falta válida).

    Args:
      attendance_docs: iterable de documentos da coleção `attendance`
        `{date: 'YYYY-MM-DD', records: [{student_id, status, dependency_id?,
        invalidated?}, ...]}` — funciona para `attendance_type` 'daily' e 'by_course'.
      medical_days_by_student: `{student_id: Set[YYYY-MM-DD coberto por atestado]}`
      student_ids: opcional. Se fornecido, ignora records de outros alunos.

    Returns:
      `{student_id: {month_int: valid_absence_count}}`
    """
    # Acumulador intermediário: {sid: {date: {"present": N, "absent": N}}}
    daily_counts: dict = {}

    for doc in attendance_docs or []:
        date_str = (doc.get("date") or "")[:10]
        if not date_str or len(date_str) != 10:
            continue

        for rec in doc.get("records", []) or []:
            sid = rec.get("student_id")
            if not sid:
                continue
            if student_ids is not None and sid not in student_ids:
                continue
            # Exclusão 1: dependência não contamina cálculo regular (P0)
            if rec.get("dependency_id"):
                continue
            # Exclusão 2: componente invalidado
            if rec.get("invalidated") or rec.get("invalid"):
                continue

            raw_status = (rec.get("status") or "").strip()
            in_atestado = date_str in (medical_days_by_student.get(sid) or set())

            # Exclusão 3: atestado médico vence — registro ignorado
            if in_atestado:
                continue
            # Exclusão 4: justificada pelo professor — registro ignorado
            if raw_status in ("J", "justified"):
                continue

            # Agora o registro entra no denominador do dia
            day = daily_counts.setdefault(sid, {}).setdefault(
                date_str, {"present": 0, "absent": 0}
            )
            if raw_status in ("P", "present", "presente"):
                day["present"] += 1
            elif raw_status in ("F", "absent", "ausente", "falta", "A"):
                # 'A' legado às vezes representava ausência;
                # quando 'A' = atestado, já saiu via `in_atestado`.
                day["absent"] += 1
            # Status desconhecido / vazio → ignorado (não entra no denominador)

    # Conversão final: aplica regra dos 50% por (sid, date) e agrega por mês
    out: dict = {}
    for sid, days in daily_counts.items():
        for date_str, counts in days.items():
            total = counts["present"] + counts["absent"]
            if total == 0:
                continue  # Dia sem registros válidos — não conta nem como presença nem falta
            present_pct = (counts["present"] / total) * 100
            if present_pct < 50.0:
                try:
                    month = int(date_str[5:7])
                except (ValueError, TypeError):
                    continue
                if sid not in out:
                    out[sid] = {}
                out[sid][month] = out[sid].get(month, 0) + 1
    return out


async def fetch_medical_days_for_students(db, student_ids: Iterable[str], academic_year: int) -> dict:
    """Wrapper assíncrono que busca em batch os medical_certificates do ano e
    devolve `{student_id: Set[YYYY-MM-DD]}` — pronto para
    `compute_monthly_valid_absences`. Mantém a engine de cálculo desacoplada
    do I/O.
    """
    sids = [s for s in (student_ids or []) if s]
    if not sids:
        return {}
    year_start = f"{academic_year}-01-01"
    year_end = f"{academic_year}-12-31"
    certs = await db.medical_certificates.find(
        {
            "student_id": {"$in": sids},
            "start_date": {"$lte": year_end},
            "end_date": {"$gte": year_start},
        },
        {"_id": 0, "student_id": 1, "start_date": 1, "end_date": 1},
    ).to_list(None)
    out: dict = {}
    from datetime import datetime as _dt, timedelta as _td
    for c in certs:
        sid = c.get("student_id")
        start = (c.get("start_date") or "")[:10]
        end = (c.get("end_date") or "")[:10]
        if not sid or not start or not end or start > end:
            continue
        # Clipa ao ano letivo
        if start < year_start:
            start = year_start
        if end > year_end:
            end = year_end
        try:
            cur = _dt.strptime(start, "%Y-%m-%d")
            last = _dt.strptime(end, "%Y-%m-%d")
        except ValueError:
            continue
        if sid not in out:
            out[sid] = set()
        while cur <= last:
            out[sid].add(cur.strftime("%Y-%m-%d"))
            cur += _td(days=1)
    return out
