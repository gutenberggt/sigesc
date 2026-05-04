"""
Utilitários de formatação de texto - SIGESC

[Mai/2026] CAPS lock automático foi descontinuado. As funções
`format_data_uppercase` e `to_uppercase_field` permanecem aqui apenas
como referência histórica — NÃO são chamadas em código novo.

Use `compute_name_indexes()` ao salvar entidades nominais para alimentar
os campos auxiliares `nome_normalizado` e `nome_busca` (indexáveis).
"""
import re
import unicodedata
from typing import Optional, Tuple


def strip_accents(text: str) -> str:
    """Remove acentos via NFD + filtro categoria Mn."""
    if not text:
        return text
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_for_search(value: Optional[str]) -> Optional[str]:
    """Normaliza nome para BUSCA: lowercase + sem acentos + espaços colapsados.

    Use para alimentar o campo `nome_busca` (indexável). Buscas case- e
    accent-insensitive aplicam a mesma normalização ao termo do usuário e
    fazem `regex` simples ou `$eq` sobre `nome_busca`.
    """
    if not value or not isinstance(value, str):
        return value
    cleaned = strip_accents(value).lower()
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_for_sort(value: Optional[str]) -> Optional[str]:
    """Normaliza nome para ORDENAÇÃO: lowercase preservando acentos.

    Use para alimentar `nome_normalizado` (ordenação determinística e
    case-insensitive sem perder a forma acentuada).
    """
    if not value or not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", value).strip().lower()


def compute_name_indexes(
    doc: dict, primary_field: str = "full_name"
) -> Tuple[Optional[str], Optional[str]]:
    """Calcula (nome_normalizado, nome_busca) a partir do campo primário.

    Uso típico em routers de POST/PUT:

        from text_utils import compute_name_indexes
        normalized, busca = compute_name_indexes(doc, 'full_name')
        if normalized is not None:
            doc['nome_normalizado'] = normalized
            doc['nome_busca'] = busca

    Retorna (None, None) se o campo primário estiver ausente/vazio.
    """
    primary = doc.get(primary_field)
    if not primary or not isinstance(primary, str) or not primary.strip():
        return (None, None)
    return (normalize_for_sort(primary), normalize_for_search(primary))


# ============================================================
# DEPRECATED — não usar em código novo
# ============================================================

# Lista de campos que NÃO devem ser convertidos para maiúsculas
LOWERCASE_FIELDS = {
    'email', 'e_mail', 'e-mail',
    'password', 'senha', 'hashed_password',
    'confirm_password', 'confirmar_senha',
    'url', 'website', 'site', 'link',
    'avatar', 'photo', 'image', 'foto', 'imagem', 'photo_url', 'avatar_url', 'foto_url',
    'token', 'access_token', 'refresh_token',
    'id', '_id', 'uuid',
    # Campos de seleção (enum) que devem manter minúsculas
    'sexo', 'sex', 'gender',
    'cor_raca', 'race', 'ethnicity',
    'cargo', 'role', 'position',
    'tipo_vinculo', 'bond_type', 'contract_type',
    'status',
    'turno', 'shift',
    'funcao', 'function',
    'nivel_ensino', 'education_level',
    'modalidade', 'modality',
    'periodo', 'period',
    'legal_guardian_type',
    'civil_certificate_type',
    'color_race', 'cor_raca_aluno',
    'publico_alvo', 'nivel_apoio',
    'relationship',
    # Campos Literal de modelos Pydantic
    'zona_localizacao', 'tipo_unidade', 'atendimento_programa',
    'tipo_atividade', 'tipo_atendimento', 'tipo_deficiencia',
    'form_pagamento', 'comunidade_tradicional',
    # Campos Literal do módulo AEE (Plano, Atendimento, Articulação)
    'dias_atendimento', 'prazo', 'tipo',
    'frequencia_revisao',  # Feb 2026: 'mensal'/'bimestral'/'trimestral'/'semestral'
    # IDs referenciados
    'escola_id', 'student_id', 'class_id', 'teacher_id',
    'school_id', 'user_id', 'enrollment_id',
    'atendimento_programa_tipo', 'atendimento_programa_class_id',
    'atendimento_programa_school_id',
    'anexa_a',
    'student_series',
    # Campos com valores predefinidos (checkboxes) - não devem ser convertidos
    'benefits', 'disabilities'
}


def to_uppercase_field(value, field_name=''):
    """
    Converte string para maiúsculas, ignorando campos específicos.
    
    Args:
        value: Valor a ser convertido
        field_name: Nome do campo (para verificar se deve ser ignorado)
    
    Returns:
        String em maiúsculas ou valor original
    """
    if not value or not isinstance(value, str):
        return value
    
    # Verifica se é um campo que não deve ser convertido
    field_lower = field_name.lower()
    if any(f in field_lower for f in LOWERCASE_FIELDS):
        return value
    
    # Verifica se parece ser um email (contém @) ou URL (contém :// ou www)
    if '@' in value or '://' in value or value.startswith('www.'):
        return value
    
    return value.upper()


def format_data_uppercase(data):
    """
    Converte todos os campos de texto de um dict/objeto para maiúsculas.
    Exceto campos de email, senha, URLs e similares.
    
    Args:
        data: Dicionário ou objeto Pydantic com os dados
    
    Returns:
        Dicionário com strings em maiúsculas
    """
    if data is None:
        return data
    
    # Se for um modelo Pydantic, converter para dict
    if hasattr(data, 'dict'):
        data = data.dict()
    elif hasattr(data, 'model_dump'):
        data = data.model_dump()
    
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = to_uppercase_field(value, key)
        elif isinstance(value, list):
            result[key] = [
                to_uppercase_field(item, key) if isinstance(item, str) 
                else format_data_uppercase(item) if isinstance(item, dict) 
                else item
                for item in value
            ]
        elif isinstance(value, dict):
            result[key] = format_data_uppercase(value)
        else:
            result[key] = value
    return result
