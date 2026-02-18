"""
Utilitários de formatação de texto - SIGESC
Funções para padronização de strings (maiúsculas, etc)
"""

# Lista de campos que NÃO devem ser convertidos para maiúsculas
LOWERCASE_FIELDS = {
    'email', 'e_mail', 'e-mail',
    'password', 'senha', 'hashed_password',
    'confirm_password', 'confirmar_senha',
    'url', 'website', 'site', 'link',
    'avatar', 'photo', 'image', 'foto', 'imagem', 'photo_url', 'avatar_url',
    'token', 'access_token', 'refresh_token',
    'id', '_id', 'uuid'
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
