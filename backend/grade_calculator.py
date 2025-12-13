"""
Módulo de cálculo de notas do SIGESC
Fórmula: (B1×2 + B2×3 + B3×2 + B4×3) / 10
Média mínima para aprovação: 5,0
Frequência mínima: 75%

Recuperação por semestre:
- Rec. 1º Sem: substitui a menor nota entre B1 e B2 (se for maior)
- Rec. 2º Sem: substitui a menor nota entre B3 e B4 (se for maior)
"""

from typing import Optional, Dict, Tuple

# Pesos dos bimestres
WEIGHTS = {
    'b1': 2,
    'b2': 3,
    'b3': 2,
    'b4': 3
}

# Constantes
MIN_AVERAGE = 5.0
MIN_ATTENDANCE = 75.0


def calculate_weighted_average(b1: Optional[float], b2: Optional[float], 
                                b3: Optional[float], b4: Optional[float],
                                rec_s1: Optional[float] = None,
                                rec_s2: Optional[float] = None,
                                recovery: Optional[float] = None) -> Tuple[Optional[float], Dict]:
    """
    Calcula a média ponderada considerando as recuperações por semestre.
    
    Rec. 1º Semestre (rec_s1): substitui a menor nota entre B1 e B2 se for maior
    Rec. 2º Semestre (rec_s2): substitui a menor nota entre B3 e B4 se for maior
    
    Returns:
        Tuple com (média_final, detalhes do cálculo)
    """
    grades = {'b1': b1, 'b2': b2, 'b3': b3, 'b4': b4}
    
    # Se não tem todas as notas dos bimestres, retorna None
    if any(g is None for g in grades.values()):
        return None, {'incomplete': True, 'message': 'Notas incompletas'}
    
    # Aplica recuperações
    final_grades = grades.copy()
    rec_s1_applied = None
    rec_s2_applied = None
    
    # Recuperação 1º Semestre (B1, B2)
    if rec_s1 is not None:
        # Encontra a menor nota do 1º semestre
        s1_grades = {'b1': b1, 'b2': b2}
        min_grade_s1 = min(s1_grades.values())
        
        # Encontra o bimestre com menor nota
        min_bimesters_s1 = [k for k, v in s1_grades.items() if v == min_grade_s1]
        
        # Se ambos têm a mesma nota, prioriza B2 (maior peso)
        if len(min_bimesters_s1) > 1:
            rec_s1_applied = 'b2'
        else:
            rec_s1_applied = min_bimesters_s1[0]
        
        # Aplica apenas se a recuperação for maior que a nota original
        if rec_s1 > final_grades[rec_s1_applied]:
            final_grades[rec_s1_applied] = rec_s1
        else:
            rec_s1_applied = None  # Não foi aplicada
    
    # Recuperação 2º Semestre (B3, B4)
    if rec_s2 is not None:
        # Encontra a menor nota do 2º semestre
        s2_grades = {'b3': b3, 'b4': b4}
        min_grade_s2 = min(s2_grades.values())
        
        # Encontra o bimestre com menor nota
        min_bimesters_s2 = [k for k, v in s2_grades.items() if v == min_grade_s2]
        
        # Se ambos têm a mesma nota, prioriza B4 (maior peso)
        if len(min_bimesters_s2) > 1:
            rec_s2_applied = 'b4'
        else:
            rec_s2_applied = min_bimesters_s2[0]
        
        # Aplica apenas se a recuperação for maior que a nota original
        if rec_s2 > final_grades[rec_s2_applied]:
            final_grades[rec_s2_applied] = rec_s2
        else:
            rec_s2_applied = None  # Não foi aplicada
    
    # Suporte ao campo legado 'recovery' (substitui menor nota geral)
    recovery_applied = None
    if recovery is not None and rec_s1 is None and rec_s2 is None:
        # Encontra a menor nota
        min_grade = min(final_grades.values())
        min_bimesters = [k for k, v in final_grades.items() if v == min_grade]
        
        if len(min_bimesters) == 1:
            recovery_applied = min_bimesters[0]
        else:
            # Prioridade: B2 > B4 > B1 > B3
            priority = ['b2', 'b4', 'b1', 'b3']
            for p in priority:
                if p in min_bimesters:
                    recovery_applied = p
                    break
        
        if recovery > final_grades[recovery_applied]:
            final_grades[recovery_applied] = recovery
        else:
            recovery_applied = None
    
    # Calcula média ponderada
    total = sum(final_grades[k] * WEIGHTS[k] for k in final_grades)
    average = total / sum(WEIGHTS.values())  # Soma dos pesos = 10
    
    # Arredonda para 1 casa decimal
    average = round(average, 1)
    
    details = {
        'original_grades': grades,
        'final_grades': final_grades,
        'rec_s1': rec_s1,
        'rec_s1_applied_to': rec_s1_applied,
        'rec_s2': rec_s2,
        'rec_s2_applied_to': rec_s2_applied,
        'recovery': recovery,
        'recovery_applied_to': recovery_applied,
        'average': average,
        'weights': WEIGHTS
    }
    
    return average, details


def determine_status(average: Optional[float], attendance_percentage: Optional[float] = None) -> str:
    """
    Determina o status do aluno baseado na média e frequência.
    
    Returns:
        'cursando': Ainda não tem todas as notas
        'aprovado': Média >= 5.0 e frequência >= 75%
        'reprovado_nota': Média < 5.0
        'reprovado_frequencia': Frequência < 75%
        'recuperacao': Em recuperação
    """
    if average is None:
        return 'cursando'
    
    # Verifica frequência primeiro
    if attendance_percentage is not None and attendance_percentage < MIN_ATTENDANCE:
        return 'reprovado_frequencia'
    
    # Verifica média
    if average >= MIN_AVERAGE:
        return 'aprovado'
    else:
        return 'reprovado_nota'


def format_grade(value: Optional[float]) -> str:
    """Formata nota para exibição com vírgula"""
    if value is None:
        return '-'
    return f"{value:.1f}".replace('.', ',')


def parse_grade(value: str) -> Optional[float]:
    """Converte string com vírgula para float"""
    if not value or value == '-':
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


async def calculate_and_update_grade(db, grade_id: str) -> dict:
    """
    Calcula e atualiza a média de uma nota no banco de dados.
    
    Args:
        db: Conexão com MongoDB
        grade_id: ID da nota a ser atualizada
        
    Returns:
        Nota atualizada
    """
    from datetime import datetime, timezone
    
    grade = await db.grades.find_one({"id": grade_id}, {"_id": 0})
    if not grade:
        return None
    
    # Calcula média com suporte a ambos os formatos de recuperação
    average, details = calculate_weighted_average(
        grade.get('b1'),
        grade.get('b2'),
        grade.get('b3'),
        grade.get('b4'),
        grade.get('rec_s1'),
        grade.get('rec_s2'),
        grade.get('recovery')
    )
    
    # Busca frequência do aluno (se existir)
    attendance_percentage = None
    # TODO: Implementar busca de frequência quando o módulo de frequência estiver pronto
    
    # Determina status
    status = determine_status(average, attendance_percentage)
    
    # Atualiza no banco
    update_data = {
        'final_average': average,
        'status': status,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.grades.update_one(
        {"id": grade_id},
        {"$set": update_data}
    )
    
    updated_grade = await db.grades.find_one({"id": grade_id}, {"_id": 0})
    return updated_grade
