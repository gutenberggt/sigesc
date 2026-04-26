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
