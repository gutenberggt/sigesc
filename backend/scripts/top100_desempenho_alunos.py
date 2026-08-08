"""
Top 100 alunos por DESEMPENHO — mesma regra do Dashboard Analítico
(endpoint GET /api/analytics/students/performance), porém sem o corte em 20.

Score = 60% (média final × 10) + 40% frequência (% de presença).
Escopo: rede inteira (todas as escolas) do ano letivo informado.
Regras iguais ao dashboard:
  - Exclui Educação Infantil, 1º e 2º ano (só 3º ao 9º e EJA).
  - Notas: apenas 'final_average' não nulo e componentes REGULARES (sem dependência).
  - Frequência: status P/F/J (present = P).

Uso:
    cd /app/backend
    python scripts/top100_desempenho_alunos.py            # ano 2026 (padrão), top 100
    python scripts/top100_desempenho_alunos.py 2025 50    # ano 2025, top 50
    python scripts/top100_desempenho_alunos.py 2026 100 csv > top100.csv
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

EXCLUDED_EDUCATION_LEVELS = ['educacao_infantil']
EXCLUDED_GRADE_LEVELS = [
    '1º ANO', '1 ANO', '2º ANO', '2 ANO', 'PRÉ I', 'PRÉ II', 'PRE I', 'PRE II',
    'MATERNAL', 'BERÇÁRIO', 'BERCARIO', 'CRECHE', 'INFANTIL I', 'INFANTIL II',
    'INFANTIL III', 'INFANTIL IV', 'INFANTIL V',
]


def year_filter(year):
    return {'$in': [str(year), year]}


async def compute(academic_year: int, limit: int):
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]

    # 1) Turmas elegíveis (exclui infantil/1º/2º ano)
    eligible_classes = []
    class_name_by_id = {}
    class_school_by_id = {}
    async for cls in db.classes.find(
        {'academic_year': year_filter(academic_year)},
        {'_id': 0, 'id': 1, 'education_level': 1, 'grade_level': 1, 'name': 1, 'school_id': 1},
    ):
        grade = (cls.get('grade_level') or cls.get('name') or '').upper()
        if cls.get('education_level', '') in EXCLUDED_EDUCATION_LEVELS:
            continue
        if any(eg in grade for eg in EXCLUDED_GRADE_LEVELS):
            continue
        eligible_classes.append(cls['id'])
        class_name_by_id[cls['id']] = cls.get('name') or 'N/A'
        class_school_by_id[cls['id']] = cls.get('school_id')

    if not eligible_classes:
        print('Nenhuma turma elegível encontrada para o ano', academic_year)
        return []

    # 2) Matrículas ativas nas turmas elegíveis
    enrollments = await db.enrollments.find(
        {
            'academic_year': year_filter(academic_year),
            'status': {'$in': ['active', 'ativo', 'Ativo', None]},
            'class_id': {'$in': eligible_classes},
        },
        {'_id': 0, 'student_id': 1, 'class_id': 1, 'school_id': 1},
    ).to_list(None)

    if not enrollments:
        print('Nenhuma matrícula ativa encontrada para o ano', academic_year)
        return []

    enrollment_map = {e['student_id']: e for e in enrollments}
    student_ids = list(enrollment_map.keys())

    # 3) Nomes dos alunos
    students = {}
    async for st in db.students.find({'id': {'$in': student_ids}}, {'_id': 0, 'id': 1, 'full_name': 1, 'name': 1}):
        enr = enrollment_map.get(st['id'], {})
        students[st['id']] = {
            'name': st.get('full_name') or st.get('name', 'N/A'),
            'class_id': enr.get('class_id'),
            'school_id': enr.get('school_id') or class_school_by_id.get(enr.get('class_id')),
            'avg_grade': 0.0,
            'attendance_rate': 0.0,
        }

    # 4) Média final por aluno (apenas componentes regulares, final_average não nulo)
    grades_pipeline = [
        {'$match': {
            'student_id': {'$in': student_ids},
            'academic_year': year_filter(academic_year),
            'final_average': {'$ne': None},
            'dependency_id': {'$in': [None]},
        }},
        {'$group': {'_id': '$student_id', 'avg_grade': {'$avg': '$final_average'}}},
    ]
    async for doc in db.grades.aggregate(grades_pipeline):
        if doc['_id'] in students:
            students[doc['_id']]['avg_grade'] = round(doc['avg_grade'] or 0, 1)

    # 5) Frequência por aluno (P/F/J; present = P)
    attendance_pipeline = [
        {'$match': {'academic_year': year_filter(academic_year)}},
        {'$unwind': '$records'},
        {'$match': {'records.dependency_id': {'$in': [None]}, 'records.student_id': {'$in': student_ids}}},
        {'$addFields': {'_sts': {'$split': [{'$toUpper': {'$ifNull': ['$records.status', '']}}, '|']}}},
        {'$unwind': '$_sts'},
        {'$addFields': {'_st': {'$trim': {'input': '$_sts'}}}},
        {'$match': {'_st': {'$in': ['P', 'F', 'J']}}},
        {'$group': {
            '_id': '$records.student_id',
            'total': {'$sum': 1},
            'present': {'$sum': {'$cond': [{'$eq': ['$_st', 'P']}, 1, 0]}},
        }},
    ]
    async for doc in db.attendance.aggregate(attendance_pipeline):
        if doc['_id'] in students and doc['total'] > 0:
            students[doc['_id']]['attendance_rate'] = round(doc['present'] / doc['total'] * 100, 1)

    # 6) Nomes das escolas
    school_ids = list({s['school_id'] for s in students.values() if s.get('school_id')})
    school_name_by_id = {}
    async for sc in db.schools.find({'id': {'$in': school_ids}}, {'_id': 0, 'id': 1, 'name': 1}):
        school_name_by_id[sc['id']] = sc.get('name') or 'N/A'

    # 7) Score = 60% (média×10) + 40% frequência
    result = []
    for data in students.values():
        avg = data['avg_grade']
        freq = data['attendance_rate']
        indice_media = round(avg * 10, 1) if avg > 0 else 0
        score = round(indice_media * 0.6 + freq * 0.4, 1)
        result.append({
            'student_name': data['name'],
            'school_name': school_name_by_id.get(data.get('school_id'), 'N/A'),
            'class_name': class_name_by_id.get(data.get('class_id'), 'N/A'),
            'avg_grade': avg,
            'attendance_rate': freq,
            'score': score,
        })

    result.sort(key=lambda x: x['score'], reverse=True)
    return result[:limit]


def print_table(rows):
    print(f"{'#':>3}  {'ALUNO':<34} {'ESCOLA':<34} {'TURMA':<14} {'SCORE':>6}")
    print('-' * 96)
    for i, r in enumerate(rows, start=1):
        print(f"{i:>3}  {r['student_name'][:33]:<34} {r['school_name'][:33]:<34} "
              f"{r['class_name'][:13]:<14} {r['score']:>6}")


def print_csv(rows):
    print('colocacao;aluno;escola;turma;media;frequencia;score')
    for i, r in enumerate(rows, start=1):
        print(f"{i};{r['student_name']};{r['school_name']};{r['class_name']};"
              f"{r['avg_grade']};{r['attendance_rate']};{r['score']}")


async def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    fmt = sys.argv[3] if len(sys.argv) > 3 else 'table'
    rows = await compute(year, limit)
    if not rows:
        return
    if fmt == 'csv':
        print_csv(rows)
    else:
        print(f"\nTOP {limit} ALUNOS POR DESEMPENHO — Ano letivo {year} (rede completa)")
        print(f"(Score = 60% média×10 + 40% frequência — mesma regra do Dashboard Analítico)\n")
        print_table(rows)
        print(f"\nTotal exibido: {len(rows)} aluno(s).")


if __name__ == '__main__':
    asyncio.run(main())
