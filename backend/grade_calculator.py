"""
Módulo de cálculo de notas do SIGESC
Fórmula: (B1×2 + B2×3 + B3×2 + B4×3) / 10
Média mínima para aprovação: 5,0
Frequência mínima: 75%

Recuperação por semestre:
- Rec. 1º Sem: substitui a menor nota entre B1 e B2 (se for maior)
- Rec. 2º Sem: substitui a menor nota entre B3 e B4 (se for maior)

EDUCAÇÃO INFANTIL (Avaliação Conceitual):
- Sem recuperação
- Média = Maior conceito alcançado nos 4 bimestres
- Aprovação automática (exceto desistência, falecimento, transferência)
- Conceitos: OD=10.0, DP=7.5, ND=5.0, NT=0.0

IMPORTANTE: Campos vazios são tratados como 0 para exibir a média desde a 1ª nota.
"""

from typing import Optional, Dict, Tuple, List

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

# Séries/Anos da Educação Infantil
SERIES_EDUCACAO_INFANTIL = [
    'Berçário', 'Berçário I', 'Berçário II',
    'Maternal', 'Maternal I', 'Maternal II',
    'Pré', 'Pré I', 'Pré II', 'Pré-Escola',
    'Creche', 'Jardim', 'Jardim I', 'Jardim II'
]

# Conceitos para Educação Infantil
CONCEITOS_EDUCACAO_INFANTIL = {
    'OD': 10.0,  # Objetivo Desenvolvido
    'DP': 7.5,   # Desenvolvido Parcialmente
    'ND': 5.0,   # Não Desenvolvido
    'NT': 0.0,   # Não Trabalhado
}


def is_educacao_infantil(grade_level: str, nivel_ensino: str = None) -> bool:
    """Verifica se é série da Educação Infantil"""
    if nivel_ensino == 'educacao_infantil':
        return True
    if not grade_level:
        return False
    return any(serie.lower() in grade_level.lower() for serie in SERIES_EDUCACAO_INFANTIL)


def calculate_maior_conceito(b1: Optional[float], b2: Optional[float], 
                             b3: Optional[float], b4: Optional[float]) -> Optional[float]:
    """
    Calcula o maior conceito alcançado (para Educação Infantil).
    A média é o MAIOR valor entre os 4 bimestres.
    """
    valores = [v for v in [b1, b2, b3, b4] if v is not None and v != 0]
    if not valores:
        return None
    return max(valores)


def calculate_weighted_average(b1: Optional[float], b2: Optional[float], 
                                b3: Optional[float], b4: Optional[float],
                                rec_s1: Optional[float] = None,
                                rec_s2: Optional[float] = None,
                                recovery: Optional[float] = None) -> Tuple[float, Dict]:
    """
    Calcula a média ponderada considerando as recuperações por semestre.
    Campos vazios (None) são tratados como 0.
    
    Rec. 1º Semestre (rec_s1): substitui a menor nota entre B1 e B2 se for maior
    Rec. 2º Semestre (rec_s2): substitui a menor nota entre B3 e B4 se for maior
    
    Returns:
        Tuple com (média_final, detalhes do cálculo)
    """
    # Converte None para 0 - campos vazios são tratados como 0
    original_grades = {'b1': b1, 'b2': b2, 'b3': b3, 'b4': b4}
    grades = {
        'b1': b1 if b1 is not None else 0,
        'b2': b2 if b2 is not None else 0,
        'b3': b3 if b3 is not None else 0,
        'b4': b4 if b4 is not None else 0
    }
    
    # Aplica recuperações
    final_grades = grades.copy()
    rec_s1_applied = None
    rec_s2_applied = None
    
    # Recuperação 1º Semestre (B1, B2)
    if rec_s1 is not None:
        # Encontra a menor nota do 1º semestre
        s1_grades = {'b1': grades['b1'], 'b2': grades['b2']}
        min_grade_s1 = min(s1_grades.values())
        
        # Encontra o bimestre com menor nota (se empate, prioriza B2)
        if s1_grades['b1'] <= s1_grades['b2']:
            rec_s1_applied = 'b1'
        else:
            rec_s1_applied = 'b2'
        
        # Aplica apenas se a recuperação for maior que a nota original
        if rec_s1 > final_grades[rec_s1_applied]:
            final_grades[rec_s1_applied] = rec_s1
        else:
            rec_s1_applied = None  # Não foi aplicada
    
    # Recuperação 2º Semestre (B3, B4)
    if rec_s2 is not None:
        # Encontra a menor nota do 2º semestre
        s2_grades = {'b3': grades['b3'], 'b4': grades['b4']}
        
        # Encontra o bimestre com menor nota (se empate, prioriza B4)
        if s2_grades['b3'] <= s2_grades['b4']:
            rec_s2_applied = 'b3'
        else:
            rec_s2_applied = 'b4'
        
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
        'original_grades': original_grades,
        'grades_with_zero': grades,
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
    
    Para Educação Infantil:
    - Usa o MAIOR conceito alcançado como média
    - Aprovação automática
    
    Para outros níveis:
    - Usa média ponderada com recuperações
    
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
    
    # Busca informações da turma para verificar se é Educação Infantil
    class_info = await db.classes.find_one(
        {"id": grade.get('class_id')}, 
        {"_id": 0, "grade_level": 1, "nivel_ensino": 1, "education_level": 1}
    )
    
    grade_level = class_info.get('grade_level', '') if class_info else ''
    nivel_ensino = class_info.get('nivel_ensino') or class_info.get('education_level', '') if class_info else ''
    
    # Verifica se é Educação Infantil
    ed_infantil = is_educacao_infantil(grade_level, nivel_ensino)
    
    if ed_infantil:
        # EDUCAÇÃO INFANTIL: Média = Maior conceito alcançado
        average = calculate_maior_conceito(
            grade.get('b1'),
            grade.get('b2'),
            grade.get('b3'),
            grade.get('b4')
        )
        # Aprovação automática para Educação Infantil
        status = 'aprovado'
    else:
        # OUTROS NÍVEIS: Média ponderada com recuperações
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


def calcular_resultado_final_aluno(
    medias_por_componente: List[Dict],
    regras_aprovacao: Dict,
    enrollment_status: str = 'active',
    is_educacao_infantil: bool = False,
    frequencia_aluno: float = None
) -> Dict:
    """
    Calcula o resultado final do aluno considerando as regras de aprovação da mantenedora.
    
    Args:
        medias_por_componente: Lista de dicts com {'nome': str, 'media': float, 'optativo': bool}
        regras_aprovacao: Dict com regras da mantenedora:
            - media_aprovacao: float (5.0 a 10.0)
            - frequencia_minima: float (60 a 85, padrão 75)
            - aprovacao_com_dependencia: bool
            - max_componentes_dependencia: int (1-5)
            - cursar_apenas_dependencia: bool
            - qtd_componentes_apenas_dependencia: int (1-5)
        enrollment_status: Status da matrícula (active, transferido, desistente, etc.)
        is_educacao_infantil: Se é Educação Infantil (aprovação automática)
        frequencia_aluno: Frequência do aluno em porcentagem (0-100)
    
    Returns:
        Dict com:
            - resultado: str ('APROVADO', 'REPROVADO', 'APROVADO COM DEPENDÊNCIA', 'CURSAR DEPENDÊNCIA', etc.)
            - cor: str (hex color)
            - componentes_reprovados: List[str] - nomes dos componentes reprovados
            - media_geral: float
            - detalhes: str - explicação do resultado
            - reprovado_por_frequencia: bool
    """
    # Verificar status especiais da matrícula
    status_especiais = {
        'desistencia': ('DESISTENTE', '#dc2626'),
        'desistente': ('DESISTENTE', '#dc2626'),
        'falecimento': ('FALECIDO', '#6b7280'),
        'falecido': ('FALECIDO', '#6b7280'),
        'transferencia': ('TRANSFERIDO', '#f59e0b'),
        'transferido': ('TRANSFERIDO', '#f59e0b'),
    }
    
    if enrollment_status.lower() in status_especiais:
        resultado, cor = status_especiais[enrollment_status.lower()]
        return {
            'resultado': resultado,
            'cor': cor,
            'componentes_reprovados': [],
            'media_geral': None,
            'detalhes': f'Aluno com status: {resultado}',
            'reprovado_por_frequencia': False
        }
    
    # Educação Infantil: aprovação automática
    if is_educacao_infantil:
        return {
            'resultado': 'APROVADO',
            'cor': '#16a34a',
            'componentes_reprovados': [],
            'media_geral': None,
            'detalhes': 'Educação Infantil - aprovação automática',
            'reprovado_por_frequencia': False
        }
    
    # Extrair regras da mantenedora (com valores padrão)
    media_minima = regras_aprovacao.get('media_aprovacao', 6.0) or 6.0
    frequencia_minima = regras_aprovacao.get('frequencia_minima', 75.0) or 75.0
    permite_dependencia = regras_aprovacao.get('aprovacao_com_dependencia', False)
    max_componentes_dep = regras_aprovacao.get('max_componentes_dependencia', 0) or 0
    permite_cursar_dep = regras_aprovacao.get('cursar_apenas_dependencia', False)
    qtd_cursar_dep = regras_aprovacao.get('qtd_componentes_apenas_dependencia', 0) or 0
    
    # Verificar reprovação por frequência
    reprovado_por_frequencia = False
    if frequencia_aluno is not None and frequencia_aluno < frequencia_minima:
        reprovado_por_frequencia = True
    
    # Filtrar componentes válidos (não optativos sem notas)
    componentes_validos = []
    for comp in medias_por_componente:
        is_optativo = comp.get('optativo', False)
        media = comp.get('media')
        
        # Se for optativo e não tem média, ignora
        if is_optativo and media is None:
            continue
        
        componentes_validos.append(comp)
    
    # Se não há componentes válidos, está em andamento
    if not componentes_validos:
        return {
            'resultado': 'EM ANDAMENTO',
            'cor': '#2563eb',
            'componentes_reprovados': [],
            'media_geral': None,
            'detalhes': 'Sem notas registradas',
            'reprovado_por_frequencia': False
        }
    
    # Calcular média geral e identificar componentes reprovados
    medias = []
    componentes_reprovados = []
    
    for comp in componentes_validos:
        media = comp.get('media')
        if media is not None:
            medias.append(media)
            if media < media_minima:
                componentes_reprovados.append(comp.get('nome', 'N/A'))
    
    if not medias:
        return {
            'resultado': 'EM ANDAMENTO',
            'cor': '#2563eb',
            'componentes_reprovados': [],
            'media_geral': None,
            'detalhes': 'Sem notas registradas',
            'reprovado_por_frequencia': False
        }
    
    media_geral = sum(medias) / len(medias)
    qtd_reprovados = len(componentes_reprovados)
    
    # VERIFICAÇÃO PRIORITÁRIA: Reprovação por frequência
    if reprovado_por_frequencia:
        freq_str = f'{frequencia_aluno:.1f}%' if frequencia_aluno else 'N/A'
        detalhes = f'Reprovado por frequência insuficiente ({freq_str} < {frequencia_minima:.0f}% mínimo)'
        if qtd_reprovados > 0:
            detalhes += f'. Também reprovado em {qtd_reprovados} componente(s): {", ".join(componentes_reprovados)}'
        
        return {
            'resultado': 'REPROVADO POR FREQUÊNCIA',
            'cor': '#991b1b',  # Vermelho escuro
            'componentes_reprovados': componentes_reprovados,
            'media_geral': media_geral,
            'detalhes': detalhes,
            'reprovado_por_frequencia': True
        }
    
    # Lógica de resultado (frequência OK)
    if qtd_reprovados == 0:
        # Aprovado direto - nenhum componente reprovado
        return {
            'resultado': 'APROVADO',
            'cor': '#16a34a',
            'componentes_reprovados': [],
            'media_geral': media_geral,
            'detalhes': f'Média geral: {media_geral:.1f} - Aprovado em todos os componentes',
            'reprovado_por_frequencia': False
        }
    
    # Tem componentes reprovados - verificar regras de dependência
    
    # 1. Verificar se pode cursar apenas dependência
    if permite_cursar_dep and qtd_reprovados >= qtd_cursar_dep and qtd_cursar_dep > 0:
        return {
            'resultado': 'CURSAR DEPENDÊNCIA',
            'cor': '#7c3aed',  # Roxo
            'componentes_reprovados': componentes_reprovados,
            'media_geral': media_geral,
            'detalhes': f'Reprovado em {qtd_reprovados} componente(s) - deve cursar apenas dependência: {", ".join(componentes_reprovados)}',
            'reprovado_por_frequencia': False
        }
    
    # 2. Verificar se pode ser aprovado com dependência
    if permite_dependencia and qtd_reprovados <= max_componentes_dep:
        return {
            'resultado': 'APROVADO COM DEPENDÊNCIA',
            'cor': '#ca8a04',  # Amarelo
            'componentes_reprovados': componentes_reprovados,
            'media_geral': media_geral,
            'detalhes': f'Aprovado com dependência em {qtd_reprovados} componente(s): {", ".join(componentes_reprovados)}',
            'reprovado_por_frequencia': False
        }
    
    # 3. Reprovado - excedeu o limite de componentes para dependência
    if qtd_reprovados > 0:
        if permite_dependencia:
            detalhes = f'Reprovado em {qtd_reprovados} componente(s) - excede o limite de {max_componentes_dep} para dependência: {", ".join(componentes_reprovados)}'
        else:
            detalhes = f'Reprovado em {qtd_reprovados} componente(s): {", ".join(componentes_reprovados)}'
        
        return {
            'resultado': 'REPROVADO',
            'cor': '#dc2626',
            'componentes_reprovados': componentes_reprovados,
            'media_geral': media_geral,
            'detalhes': detalhes,
            'reprovado_por_frequencia': False
        }
    
    # Fallback - não deveria chegar aqui
    return {
        'resultado': 'EM ANDAMENTO',
        'cor': '#2563eb',
        'componentes_reprovados': [],
        'media_geral': media_geral,
        'detalhes': 'Avaliação em andamento',
        'reprovado_por_frequencia': False
    }



# Séries do 1º e 2º Ano (promoção automática)
SERIES_PROMOCAO_AUTOMATICA = [
    '1º Ano', '1° Ano', '1 Ano', 'Primeiro Ano',
    '2º Ano', '2° Ano', '2 Ano', 'Segundo Ano'
]

# Séries do 3º ao 5º Ano (Anos Iniciais com avaliação)
SERIES_ANOS_INICIAIS_AVALIACAO = [
    '3º Ano', '3° Ano', '3 Ano', 'Terceiro Ano',
    '4º Ano', '4° Ano', '4 Ano', 'Quarto Ano',
    '5º Ano', '5° Ano', '5 Ano', 'Quinto Ano'
]

# Séries do 6º ao 9º Ano (Anos Finais)
SERIES_ANOS_FINAIS = [
    '6º Ano', '6° Ano', '6 Ano', 'Sexto Ano',
    '7º Ano', '7° Ano', '7 Ano', 'Sétimo Ano',
    '8º Ano', '8° Ano', '8 Ano', 'Oitavo Ano',
    '9º Ano', '9° Ano', '9 Ano', 'Nono Ano'
]

# Etapas EJA Iniciais (1ª e 2ª Etapa)
ETAPAS_EJA_INICIAIS = [
    '1ª Etapa', '1° Etapa', '1 Etapa', 'Primeira Etapa',
    '2ª Etapa', '2° Etapa', '2 Etapa', 'Segunda Etapa'
]

# Etapas EJA Finais (3ª e 4ª Etapa)
ETAPAS_EJA_FINAIS = [
    '3ª Etapa', '3° Etapa', '3 Etapa', 'Terceira Etapa',
    '4ª Etapa', '4° Etapa', '4 Etapa', 'Quarta Etapa'
]


def _match_serie(grade_level: str, series_list: List[str]) -> bool:
    """Verifica se a série corresponde a alguma da lista"""
    if not grade_level:
        return False
    gl_lower = grade_level.lower()
    return any(serie.lower() in gl_lower for serie in series_list)


def is_promocao_automatica(grade_level: str) -> bool:
    """Verifica se é série com promoção automática (1º e 2º Ano)"""
    return _match_serie(grade_level, SERIES_PROMOCAO_AUTOMATICA)


def is_anos_iniciais_avaliacao(grade_level: str) -> bool:
    """Verifica se é série dos Anos Iniciais com avaliação (3º ao 5º Ano)"""
    return _match_serie(grade_level, SERIES_ANOS_INICIAIS_AVALIACAO)


def is_anos_finais(grade_level: str) -> bool:
    """Verifica se é série dos Anos Finais (6º ao 9º Ano)"""
    return _match_serie(grade_level, SERIES_ANOS_FINAIS)


def is_eja_inicial(grade_level: str, nivel_ensino: str = None) -> bool:
    """Verifica se é EJA Inicial (1ª e 2ª Etapa)"""
    if nivel_ensino == 'eja':
        return _match_serie(grade_level, ETAPAS_EJA_INICIAIS)
    return False


def is_eja_final(grade_level: str, nivel_ensino: str = None) -> bool:
    """Verifica se é EJA Final (3ª e 4ª Etapa)"""
    if nivel_ensino in ['eja', 'eja_final']:
        return _match_serie(grade_level, ETAPAS_EJA_FINAIS)
    return False


def determinar_resultado_documento(
    enrollment_status: str,
    grade_level: str,
    nivel_ensino: str,
    data_fim_4bim: str,
    medias_por_componente: List[Dict],
    regras_aprovacao: Dict,
    frequencia_aluno: float = None
) -> Dict:
    """
    Determina o resultado do aluno para exibição no Boletim/Ficha Individual.
    
    Regras:
    - ATÉ a data fim do 4º bimestre: Status "Ativo" → "CURSANDO", outros mantém
    - APÓS a data fim do 4º bimestre:
        - Status diferente de "Ativo" → manter status
        - Status "Ativo":
            - Educação Infantil → "CONCLUIU"
            - 1º e 2º Ano → "PROMOVIDO"
            - 3º ao 5º Ano, 1ª/2ª Etapa EJA → Verificar frequência e média
            - 6º ao 9º Ano, 3ª/4ª Etapa EJA → Verificar frequência, média e dependência
    
    Args:
        enrollment_status: Status da matrícula (active, transferred, etc.)
        grade_level: Série/Ano do aluno (ex: "5º Ano", "3ª Etapa")
        nivel_ensino: Nível de ensino (educacao_infantil, fundamental_anos_iniciais, etc.)
        data_fim_4bim: Data de fim do 4º bimestre (YYYY-MM-DD)
        medias_por_componente: Lista de dicts com {'nome': str, 'media': float, 'optativo': bool}
        regras_aprovacao: Dict com regras da mantenedora
        frequencia_aluno: Frequência do aluno em porcentagem (0-100)
    
    Returns:
        Dict com 'resultado', 'cor', 'detalhes'
    """
    from datetime import datetime, timezone
    
    # Verificar se estamos antes ou depois do fim do 4º bimestre
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    apos_fim_4bim = hoje > data_fim_4bim if data_fim_4bim else False
    
    # Normalizar status
    status_lower = (enrollment_status or 'active').lower()
    
    # ========== ANTES DO FIM DO 4º BIMESTRE ==========
    if not apos_fim_4bim:
        # Verificar status especiais
        status_especiais = {
            'desistencia': ('DESISTENTE', '#dc2626'),
            'desistente': ('DESISTENTE', '#dc2626'),
            'falecimento': ('FALECIDO', '#6b7280'),
            'falecido': ('FALECIDO', '#6b7280'),
            'transferencia': ('TRANSFERIDO', '#f59e0b'),
            'transferido': ('TRANSFERIDO', '#f59e0b'),
        }
        
        if status_lower in status_especiais:
            resultado, cor = status_especiais[status_lower]
            return {'resultado': resultado, 'cor': cor, 'detalhes': f'Status: {resultado}'}
        
        # Status "Ativo" → "CURSANDO"
        return {
            'resultado': 'CURSANDO',
            'cor': '#2563eb',  # Azul
            'detalhes': 'Ano letivo em andamento'
        }
    
    # ========== APÓS O FIM DO 4º BIMESTRE ==========
    
    # Verificar status especiais primeiro
    status_especiais = {
        'desistencia': ('DESISTENTE', '#dc2626'),
        'desistente': ('DESISTENTE', '#dc2626'),
        'falecimento': ('FALECIDO', '#6b7280'),
        'falecido': ('FALECIDO', '#6b7280'),
        'transferencia': ('TRANSFERIDO', '#f59e0b'),
        'transferido': ('TRANSFERIDO', '#f59e0b'),
    }
    
    if status_lower in status_especiais:
        resultado, cor = status_especiais[status_lower]
        return {'resultado': resultado, 'cor': cor, 'detalhes': f'Status: {resultado}'}
    
    # Status "Ativo" - aplicar regras por nível/série
    
    # 1. EDUCAÇÃO INFANTIL → "CONCLUIU"
    if is_educacao_infantil(grade_level, nivel_ensino):
        return {
            'resultado': 'CONCLUIU',
            'cor': '#16a34a',  # Verde
            'detalhes': 'Educação Infantil - conclusão automática'
        }
    
    # 2. 1º e 2º ANO → "PROMOVIDO"
    if is_promocao_automatica(grade_level):
        return {
            'resultado': 'PROMOVIDO',
            'cor': '#16a34a',  # Verde
            'detalhes': 'Promoção automática - 1º/2º Ano'
        }
    
    # 3. 3º ao 5º ANO ou 1ª/2ª ETAPA EJA → Verificar frequência e média
    if is_anos_iniciais_avaliacao(grade_level) or is_eja_inicial(grade_level, nivel_ensino):
        return _calcular_resultado_com_avaliacao(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            frequencia_aluno=frequencia_aluno,
            permite_dependencia=False  # Sem dependência para anos iniciais
        )
    
    # 4. 6º ao 9º ANO ou 3ª/4ª ETAPA EJA → Verificar com possibilidade de dependência
    if is_anos_finais(grade_level) or is_eja_final(grade_level, nivel_ensino):
        return _calcular_resultado_com_avaliacao(
            medias_por_componente=medias_por_componente,
            regras_aprovacao=regras_aprovacao,
            frequencia_aluno=frequencia_aluno,
            permite_dependencia=True  # Com dependência para anos finais
        )
    
    # Fallback: usar a função existente
    resultado_calc = calcular_resultado_final_aluno(
        medias_por_componente=medias_por_componente,
        regras_aprovacao=regras_aprovacao,
        enrollment_status=enrollment_status,
        is_educacao_infantil=False,
        frequencia_aluno=frequencia_aluno
    )
    return {
        'resultado': resultado_calc['resultado'],
        'cor': resultado_calc['cor'],
        'detalhes': resultado_calc.get('detalhes', '')
    }


def _calcular_resultado_com_avaliacao(
    medias_por_componente: List[Dict],
    regras_aprovacao: Dict,
    frequencia_aluno: float = None,
    permite_dependencia: bool = False
) -> Dict:
    """
    Calcula resultado verificando frequência e média.
    
    Args:
        medias_por_componente: Lista de médias por componente
        regras_aprovacao: Regras da mantenedora
        frequencia_aluno: Frequência do aluno
        permite_dependencia: Se permite aprovação com dependência
    """
    # Extrair regras
    media_minima = regras_aprovacao.get('media_aprovacao', 6.0) or 6.0
    frequencia_minima = regras_aprovacao.get('frequencia_minima', 75.0) or 75.0
    aprovacao_dependencia = regras_aprovacao.get('aprovacao_com_dependencia', False) and permite_dependencia
    max_componentes_dep = regras_aprovacao.get('max_componentes_dependencia', 0) or 0
    cursar_dependencia = regras_aprovacao.get('cursar_apenas_dependencia', False) and permite_dependencia
    qtd_cursar_dep = regras_aprovacao.get('qtd_componentes_apenas_dependencia', 0) or 0
    
    # Verificar frequência mínima
    if frequencia_aluno is not None and frequencia_aluno < frequencia_minima:
        return {
            'resultado': 'REPROVADO',
            'cor': '#dc2626',
            'detalhes': f'Frequência insuficiente ({frequencia_aluno:.1f}% < {frequencia_minima:.0f}%)'
        }
    
    # Verificar médias por componente
    componentes_reprovados = []
    for comp in medias_por_componente:
        is_optativo = comp.get('optativo', False)
        media = comp.get('media')
        
        # Ignorar optativos sem nota
        if is_optativo and media is None:
            continue
        
        # Verificar se reprovou no componente
        if media is not None and media < media_minima:
            componentes_reprovados.append(comp.get('nome', 'N/A'))
    
    qtd_reprovados = len(componentes_reprovados)
    
    # Sem reprovações → APROVADO
    if qtd_reprovados == 0:
        return {
            'resultado': 'APROVADO',
            'cor': '#16a34a',
            'detalhes': 'Aprovado em todos os componentes'
        }
    
    # Com reprovações - verificar dependência (apenas se permitido)
    if permite_dependencia:
        # Verificar "Cursar apenas dependência"
        if cursar_dependencia and qtd_cursar_dep > 0 and qtd_reprovados >= qtd_cursar_dep:
            return {
                'resultado': 'EM DEPENDÊNCIA',
                'cor': '#7c3aed',  # Roxo
                'detalhes': f'Deve cursar apenas dependência em: {", ".join(componentes_reprovados)}'
            }
        
        # Verificar "Aprovado com dependência"
        if aprovacao_dependencia and max_componentes_dep > 0 and qtd_reprovados <= max_componentes_dep:
            return {
                'resultado': 'APROVADO COM DEPENDÊNCIA',
                'cor': '#ca8a04',  # Amarelo
                'detalhes': f'Aprovado com dependência em: {", ".join(componentes_reprovados)}'
            }
    
    # Reprovado
    return {
        'resultado': 'REPROVADO',
        'cor': '#dc2626',
        'detalhes': f'Reprovado em {qtd_reprovados} componente(s): {", ".join(componentes_reprovados)}'
    }
