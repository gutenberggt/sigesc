"""
Análise de IMPACTO da nova regra de Frequência do Bolsa Família.

[Fev/2026] Compara o método ANTIGO (cada componente faltoso = 1 falta válida)
com o método NOVO (consolidação diária: presença em >= 50% das aulas do dia
torna o dia inteiro PRESENTE) sobre a base real.

100% READ-ONLY. Não altera dados. Não cria collections. Não escreve nada.

Objetivo regulatório/estatístico:
  1. Quantos student-meses mudam de frequência.
  2. Direção e magnitude da mudança (a consolidação só pode aumentar ou
     manter a frequência — nunca diminuir).
  3. CRÍTICO: quantos alunos cruzam o limiar de condicionalidade do PBF
     (60% para 4-5 anos; 75% para 6-17 anos) — i.e., alunos que ANTES
     apareciam em descumprimento e AGORA aparecem cumprindo.
  4. Distribuição do impacto por escola e por modo de lançamento.

Uso:
    cd /app/backend && python scripts/bf_consolidation_impact.py [ANO]
    (ANO default = ano corrente)

Saída: relatório legível no stdout + JSON em
       /app/test_reports/bf_consolidation_impact_<ANO>.json
"""
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Permite importar services.*
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.attendance_utils import (  # noqa: E402
    compute_monthly_valid_absences,  # NOVO (consolidação diária)
    fetch_medical_days_for_students,
)

# Limiares de condicionalidade do Programa Bolsa Família (educação).
# Confirmar com a Secretaria — valores padrão da norma vigente.
PBF_THRESHOLD_4_5 = 60.0      # 4 e 5 anos (pré-escola)
PBF_THRESHOLD_6_17 = 75.0     # 6 a 17 anos


def _connect():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return cli[os.environ["DB_NAME"]]


def compute_monthly_valid_absences_OLD(attendance_docs, medical_days_by_student, student_ids=None):
    """Réplica FIEL do método ANTIGO (pré consolidação diária).

    Cada registro `F` válido conta como 1 falta (por componente). Recuperado
    de git commit 263a1d6a (antes da spec de consolidação)."""
    out = {}
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
            if rec.get("dependency_id"):
                continue
            raw_status = (rec.get("status") or "").strip()
            in_atestado = date_str in (medical_days_by_student.get(sid) or set())
            if in_atestado:
                continue
            if raw_status in ("J", "justified"):
                continue
            if raw_status in ("F", "absent", "ausente", "falta", "A"):
                out.setdefault(sid, {})
                out[sid][month] = out[sid].get(month, 0) + 1
    return out


async def _calc_monthly_school_days(db, academic_year):
    """Réplica simplificada do cálculo de dias letivos por mês do router BF.

    Usa calendário letivo global + eventos. Suficiente para a comparação
    relativa (o denominador é IDÊNTICO nos dois métodos, então não distorce
    o delta)."""
    from datetime import datetime as _dt, timedelta as _td

    calendario = await db.calendario_letivo.find_one(
        {"ano_letivo": academic_year, "school_id": None}, {"_id": 0}
    ) or await db.calendario_letivo.find_one({"ano_letivo": academic_year}, {"_id": 0})
    if not calendario:
        return {m: 0 for m in range(1, 13)}

    eventos_nao_letivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar']
    events = await db.calendar_events.find({"academic_year": academic_year}, {"_id": 0}).to_list(2000)
    datas_nao_letivas = set()
    sabados_letivos = set()
    for ev in events:
        et = ev.get('event_type', '')
        sd = ev.get('start_date')
        ed = ev.get('end_date') or sd
        if not sd:
            continue
        try:
            cur = _dt.strptime(sd[:10], '%Y-%m-%d').date()
            last = _dt.strptime(ed[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue
        while cur <= last:
            if et in eventos_nao_letivos:
                datas_nao_letivas.add(cur)
            elif et == 'sabado_letivo' or (ev.get('is_school_day') and cur.weekday() == 5):
                sabados_letivos.add(cur)
            cur += _td(days=1)

    periodos = calendario.get("periodos_letivos") or calendario.get("periods") or []
    monthly = {m: 0 for m in range(1, 13)}

    def _count(inicio_str, fim_str):
        if not inicio_str or not fim_str:
            return
        try:
            ini = _dt.strptime(inicio_str[:10], '%Y-%m-%d').date()
            fim = _dt.strptime(fim_str[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return
        cur = ini
        while cur <= fim:
            is_weekday = cur.weekday() < 5
            is_sab_letivo = cur in sabados_letivos
            if (is_weekday or is_sab_letivo) and cur not in datas_nao_letivas:
                monthly[cur.month] += 1
            cur += _td(days=1)

    if periodos:
        for p in periodos:
            _count(p.get("data_inicio") or p.get("start_date"),
                   p.get("data_fim") or p.get("end_date"))
    else:
        _count(calendario.get("data_inicio") or calendario.get("start_date"),
               calendario.get("data_fim") or calendario.get("end_date"))
    return monthly


def _age_threshold(birth_date_str, ref_year):
    """Retorna o limiar PBF aplicável conforme idade no ano de referência."""
    try:
        by = int(str(birth_date_str)[:4])
        age = ref_year - by
    except (ValueError, TypeError):
        return PBF_THRESHOLD_6_17  # default conservador
    if age in (4, 5):
        return PBF_THRESHOLD_4_5
    return PBF_THRESHOLD_6_17


def _freq(school_days, absences):
    if school_days <= 0:
        return None
    return round(((school_days - absences) * 100) / school_days, 1)


async def main(academic_year):
    db = _connect()
    print(f"\n=== ANÁLISE DE IMPACTO — Consolidação Diária BF ({academic_year}) ===\n")

    students = await db.students.find(
        {
            "status": {"$in": ["active", "Ativo"]},
            "benefits": {"$in": ["Bolsa Família", "bolsa_familia", "Bolsa Familia"]},
        },
        {"_id": 0, "id": 1, "full_name": 1, "birth_date": 1, "school_id": 1},
    ).to_list(50000)
    student_ids = [s["id"] for s in students]
    sid_set = set(student_ids)
    by_id = {s["id"]: s for s in students}
    print(f"Alunos Bolsa Família (ativos): {len(students)}")

    if not students:
        print("Nenhum aluno BF encontrado — nada a analisar.")
        return

    monthly_school_days = await _calc_monthly_school_days(db, academic_year)
    all_attendance = await db.attendance.find(
        {"academic_year": academic_year}, {"_id": 0, "date": 1, "records": 1}
    ).to_list(100000)
    print(f"Documentos de attendance ({academic_year}): {len(all_attendance)}")

    medical = await fetch_medical_days_for_students(db, student_ids, academic_year)

    new_abs = compute_monthly_valid_absences(all_attendance, medical, sid_set)
    old_abs = compute_monthly_valid_absences_OLD(all_attendance, medical, sid_set)

    # Comparação por student-mês
    total_eval = 0
    changed = 0
    deltas = []
    crossed_threshold = []   # alunos que passam de <limiar p/ >=limiar
    by_school = defaultdict(lambda: {"eval": 0, "changed": 0, "crossed": 0})

    for sid in student_ids:
        s = by_id[sid]
        thr = _age_threshold(s.get("birth_date"), academic_year)
        sch = s.get("school_id", "?")
        for m in range(1, 13):
            sd = monthly_school_days.get(m, 0)
            if sd <= 0:
                continue
            a_old = (old_abs.get(sid) or {}).get(m, 0)
            a_new = (new_abs.get(sid) or {}).get(m, 0)
            f_old = _freq(sd, a_old)
            f_new = _freq(sd, a_new)
            if f_old is None or f_new is None:
                continue
            # Só conta meses com alguma atividade (alguma falta em qualquer método)
            if a_old == 0 and a_new == 0:
                continue
            total_eval += 1
            by_school[sch]["eval"] += 1
            if f_old != f_new:
                changed += 1
                deltas.append(round(f_new - f_old, 1))
                by_school[sch]["changed"] += 1
            if f_old < thr <= f_new:
                crossed_threshold.append({
                    "student_id": sid,
                    "name": s.get("full_name", ""),
                    "school_id": sch,
                    "month": m,
                    "threshold": thr,
                    "freq_old": f_old,
                    "freq_new": f_new,
                    "absences_old": a_old,
                    "absences_new": a_new,
                    "school_days": sd,
                })
                by_school[sch]["crossed"] += 1

    avg_delta = round(sum(deltas) / len(deltas), 2) if deltas else 0.0
    max_delta = max(deltas) if deltas else 0.0
    negative_deltas = [d for d in deltas if d < 0]

    print("\n--- RESULTADO ---")
    print(f"Student-meses avaliados (c/ falta em algum método): {total_eval}")
    print(f"Student-meses com frequência ALTERADA: {changed} ({round(changed/total_eval*100,1) if total_eval else 0}%)")
    print(f"Delta médio de frequência (apenas alterados): +{avg_delta} p.p.")
    print(f"Delta máximo observado: +{max_delta} p.p.")
    print(f"Deltas NEGATIVOS (regressão de frequência — NÃO esperado): {len(negative_deltas)}")
    print(f"\n>>> Alunos-mês que CRUZAM o limiar PBF (de descumprimento p/ cumprimento): {len(crossed_threshold)}")
    print("    (este é o impacto regulatório mais sensível — revisar caso a caso)\n")

    # Top escolas por impacto
    ranked = sorted(by_school.items(), key=lambda kv: kv[1]["crossed"], reverse=True)
    school_ids = [sid for sid, _ in ranked[:15]]
    sch_names = {}
    if school_ids:
        async for sc in db.schools.find({"id": {"$in": school_ids}}, {"_id": 0, "id": 1, "name": 1}):
            sch_names[sc["id"]] = sc.get("name", "")
    print("Top escolas por nº de cruzamentos de limiar:")
    for sid, agg in ranked[:15]:
        if agg["crossed"] == 0 and agg["changed"] == 0:
            continue
        print(f"  - {sch_names.get(sid, sid)[:40]:40s} | avaliados={agg['eval']:4d} alterados={agg['changed']:4d} cruzaram_limiar={agg['crossed']:3d}")

    report = {
        "academic_year": academic_year,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bf_students": len(students),
        "attendance_docs": len(all_attendance),
        "thresholds": {"age_4_5": PBF_THRESHOLD_4_5, "age_6_17": PBF_THRESHOLD_6_17},
        "summary": {
            "student_months_evaluated": total_eval,
            "student_months_changed": changed,
            "avg_delta_pp": avg_delta,
            "max_delta_pp": max_delta,
            "negative_deltas": len(negative_deltas),
            "crossed_threshold_count": len(crossed_threshold),
        },
        "crossed_threshold_samples": crossed_threshold[:200],
        "by_school": {sid: agg for sid, agg in ranked},
    }
    out_path = f"/app/test_reports/bf_consolidation_impact_{academic_year}.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"\nRelatório completo salvo em: {out_path}\n")


if __name__ == "__main__":
    load_dotenv()
    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().year
    asyncio.run(main(year))
