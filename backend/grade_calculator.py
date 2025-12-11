"""
Utilitários para cálculo de notas e recuperação do SIGESC

Sistema de Pesos:
- B1 × 2 (1º bimestre)
- B2 × 3 (2º bimestre)
- B3 × 2 (3º bimestre)
- B4 × 3 (4º bimestre)

Recuperação:
- Rec2: após 2º bimestre, substitui a menor entre B1 e B2 (se Rec2 > nota original)
- Rec4: após 4º bimestre, substitui a menor entre B3 e B4 (se Rec4 > nota original)
- Em caso de empate, substitui a de maior peso
"""

from typing import Optional, Tuple

# Pesos dos bimestres
WEIGHTS = {
    'b1': 2,
    'b2': 3,
    'b3': 2,
    'b4': 3
}

def apply_recovery(b1: Optional[float], b2: Optional[float], 
                   b3: Optional[float], b4: Optional[float],
                   rec2: Optional[float], rec4: Optional[float]) -> Tuple[float, float, float, float]:
    """
    Aplica recuperação às notas dos bimestres
    
    Returns:
        Tuple com as notas finais (b1_final, b2_final, b3_final, b4_final)
    """
    # Inicializa notas finais com as originais (ou 0 se None)
    b1_final = b1 if b1 is not None else 0
    b2_final = b2 if b2 is not None else 0
    b3_final = b3 if b3 is not None else 0
    b4_final = b4 if b4 is not None else 0
    
    # Aplicar Rec2 (substitui menor entre B1 e B2)
    if rec2 is not None and b1 is not None and b2 is not None:
        # Identifica a menor nota
        if b1 < b2:
            # B1 é menor, substitui se rec2 for maior
            if rec2 > b1:
                b1_final = rec2
        elif b2 < b1:
            # B2 é menor, substitui se rec2 for maior
            if rec2 > b2:
                b2_final = rec2
        else:
            # Empate: substitui a de maior peso (B2 tem peso 3, B1 tem peso 2)
            if rec2 > b2:
                b2_final = rec2
    
    # Aplicar Rec4 (substitui menor entre B3 e B4)
    if rec4 is not None and b3 is not None and b4 is not None:
        # Identifica a menor nota
        if b3 < b4:
            # B3 é menor, substitui se rec4 for maior
            if rec4 > b3:
                b3_final = rec4
        elif b4 < b3:
            # B4 é menor, substitui se rec4 for maior
            if rec4 > b4:
                b4_final = rec4
        else:
            # Empate: substitui a de maior peso (B4 tem peso 3, B3 tem peso 2)
            if rec4 > b4:
                b4_final = rec4
    
    return b1_final, b2_final, b3_final, b4_final

def calculate_final_average(b1: Optional[float], b2: Optional[float],
                            b3: Optional[float], b4: Optional[float],
                            rec2: Optional[float] = None, 
                            rec4: Optional[float] = None) -> Optional[float]:
    """
    Calcula a média final ponderada aplicando recuperação se necessário
    
    Fórmula: (B1×2 + B2×3 + B3×2 + B4×3) / 10
    
    Args:
        b1, b2, b3, b4: Notas dos bimestres (0-10)
        rec2: Nota de recuperação após 2º bimestre
        rec4: Nota de recuperação após 4º bimestre
    
    Returns:
        Média final ou None se não houver notas suficientes
    """
    # Se não há nenhuma nota, retorna None
    if all(x is None for x in [b1, b2, b3, b4]):
        return None
    
    # Aplica recuperação
    b1_final, b2_final, b3_final, b4_final = apply_recovery(b1, b2, b3, b4, rec2, rec4)
    
    # Calcula média ponderada
    total_weight = WEIGHTS['b1'] + WEIGHTS['b2'] + WEIGHTS['b3'] + WEIGHTS['b4']
    weighted_sum = (
        b1_final * WEIGHTS['b1'] +
        b2_final * WEIGHTS['b2'] +
        b3_final * WEIGHTS['b3'] +
        b4_final * WEIGHTS['b4']
    )
    
    average = weighted_sum / total_weight
    return round(average, 2)

def is_approved(final_average: Optional[float], min_average: float = 6.0) -> Optional[bool]:
    """
    Verifica se o aluno foi aprovado
    
    Args:
        final_average: Média final
        min_average: Média mínima para aprovação (padrão: 6.0)
    
    Returns:
        True se aprovado, False se reprovado, None se média não disponível
    """
    if final_average is None:
        return None
    
    return final_average >= min_average

def calculate_and_update_grade(grade_data: dict, min_average: float = 6.0) -> dict:
    """
    Calcula média final e status de aprovação para um registro de nota
    
    Args:
        grade_data: Dicionário com as notas (b1, b2, b3, b4, rec2, rec4)
        min_average: Média mínima para aprovação
    
    Returns:
        Dicionário atualizado com final_average e approved
    """
    final_avg = calculate_final_average(
        grade_data.get('b1'),
        grade_data.get('b2'),
        grade_data.get('b3'),
        grade_data.get('b4'),
        grade_data.get('rec2'),
        grade_data.get('rec4')
    )
    
    grade_data['final_average'] = final_avg
    grade_data['approved'] = is_approved(final_avg, min_average)
    
    return grade_data
