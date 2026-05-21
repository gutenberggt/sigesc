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
    """Conta faltas **válidas** por aluno por mês — fonte única de verdade
    para módulos que precisam saber "quantos dias o aluno faltou e que
    realmente contam contra a frequência" (ex.: Bolsa Família, Busca Ativa).

    Regra Fev/2026 (alinhada a `classify_with_atestado` e ao PDF de frequência):
      - Atestado médico vence o status original → NÃO conta como falta.
      - Status `J` (justificado pelo professor) → NÃO conta como falta.
      - `dependency_id` em registro → NÃO contamina cálculo regular (P0).
      - Apenas `F`/`absent`/`ausente`/`falta` sem atestado contam.

    Args:
      attendance_docs: iterable de documentos da coleção `attendance`
        `{date: 'YYYY-MM-DD', records: [{student_id, status, dependency_id?}, ...]}`
      medical_days_by_student: `{student_id: Set[YYYY-MM-DD coberto por atestado]}`
      student_ids: opcional. Se fornecido, ignora records de outros alunos.

    Returns:
      `{student_id: {month_int: valid_absence_count}}`
    """
    out: dict = {}
    for doc in attendance_docs or []:
        date_str = (doc.get("date") or "")[:10]
        if not date_str or len(date_str) != 10:
            continue
        try:
            month = int(date_str[5:7])
        except (ValueError, TypeError):
            continue

        for rec in doc.get("records", []) or []:
            sid = rec.get("student_id")
            if not sid:
                continue
            if student_ids is not None and sid not in student_ids:
                continue
            # P0: dependência não contamina cálculo regular
            if rec.get("dependency_id"):
                continue

            raw_status = (rec.get("status") or "").strip()
            in_atestado = date_str in (medical_days_by_student.get(sid) or set())

            # Atestado vence — nunca conta como falta
            if in_atestado:
                continue
            # Justificado pelo professor — nunca conta como falta
            if raw_status in ("J", "justified"):
                continue
            # Falta efetiva
            if raw_status in ("F", "absent", "ausente", "falta", "A"):
                # Nota: 'A' legado às vezes representava ausência;
                # quando 'A' é atestado, já foi tratado em `in_atestado`.
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
