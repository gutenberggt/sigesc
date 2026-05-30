"""
Canonicalização de SÉRIES/ETAPAS para os Indicadores da Rede.

Problema: o cadastro da rede usa nomenclaturas variadas para a mesma série
(ex.: "PRÉ-ESCOLA I", "Pré I", "PRE ESCOLA I"). Comparação exata de texto faz
alunos "sumirem" das contagens. Aqui normalizamos (acentos, caixa, hífens,
espaços) e aplicamos uma tabela de equivalências para chegar ao rótulo canônico
usado pelo frontend.

Rótulos canônicos (devem casar com os labels do frontend em UPPERCASE):
  Educação Infantil: BERÇÁRIO I, BERÇÁRIO II, MATERNAL I, MATERNAL II, PRÉ I, PRÉ II
  Ensino Fundamental: 1º ANO ... 9º ANO
  EJA: 1ª ETAPA ... 4ª ETAPA

Quando não houver correspondência confiável, retorna None (o chamador
contabiliza como "Série não reconhecida" e registra para auditoria).
"""

import re
import unicodedata
from typing import Optional

# Chave do "balde" de reconciliação (séries sem correspondência)
UNRECOGNIZED_KEY = "SÉRIE NÃO RECONHECIDA"


def _strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def _normalize(raw: str) -> str:
    """Caixa alta, sem acentos, sem hífens; ordinais (º/ª) e pontuação viram
    espaço; espaços colapsados."""
    s = _strip_accents(raw or '')
    s = s.upper()
    # ordinais e separadores -> espaço
    s = s.replace('º', ' ').replace('°', ' ').replace('ª', ' ').replace('ᵃ', ' ')
    s = re.sub(r'[\-_/.,]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# Mapas de palavras-ordinais -> número
_ORDINAL_WORDS = {
    'PRIMEIRO': 1, 'PRIMEIRA': 1, 'SEGUNDO': 2, 'SEGUNDA': 2,
    'TERCEIRO': 3, 'TERCEIRA': 3, 'QUARTO': 4, 'QUARTA': 4,
    'QUINTO': 5, 'QUINTA': 5, 'SEXTO': 6, 'SEXTA': 6,
    'SETIMO': 7, 'SETIMA': 7, 'OITAVO': 8, 'OITAVA': 8,
    'NONO': 9, 'NONA': 9,
}

# Roman numerals (níveis I/II/III...) -> número
_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5}


def _detect_number(norm: str, max_n: int) -> Optional[int]:
    """Detecta um número de 1..max_n via dígito, algarismo romano (token) ou
    palavra-ordinal. Retorna None se ambíguo/ausente."""
    tokens = norm.split(' ')
    # Algarismos arábicos
    for t in tokens:
        if t.isdigit():
            n = int(t)
            if 1 <= n <= max_n:
                return n
    # Palavras ordinais
    for t in tokens:
        if t in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[t]
    # Algarismos romanos (apenas tokens isolados, evita falso-positivo com "I" de "ESCOLA")
    for t in tokens:
        if t in _ROMAN:
            n = _ROMAN[t]
            if 1 <= n <= max_n:
                return n
    return None


def canonicalize_serie(raw: Optional[str]) -> Optional[str]:
    """Retorna o rótulo canônico (UPPERCASE) ou None se não reconhecido."""
    if not raw or not str(raw).strip():
        return None
    norm = _normalize(str(raw))
    if not norm:
        return None

    # Remove prefixo de modalidade EJA (ex.: "EJA 1 ETAPA")
    if norm.startswith('EJA '):
        norm = norm[4:].strip()

    # ---- EJA (Etapas) ----
    if 'ETAPA' in norm:
        n = _detect_number(norm, 4)
        if n:
            return f"{n}ª ETAPA"
        return None

    # ---- Ensino Fundamental (Anos) ----
    if 'ANO' in norm:
        n = _detect_number(norm, 9)
        if n:
            return f"{n}º ANO"
        return None

    # ---- Educação Infantil ----
    # Nível I/II exigido; níveis >II (III/IV) caem em "não reconhecida".
    def _infantil_level(default_to_i=True):
        n = _detect_number(norm, 5)
        if n in (1, 2):
            return n
        if n is None and default_to_i:
            return 1  # "Pré" / "Maternal" sem nível -> nível I
        return None  # III, IV, V... -> não reconhecida

    if 'BERCARIO' in norm or 'BERCARIA' in norm:
        lvl = _infantil_level()
        return f"BERÇÁRIO {'II' if lvl == 2 else 'I'}" if lvl else None
    if 'MATERNAL' in norm:
        lvl = _infantil_level()
        return f"MATERNAL {'II' if lvl == 2 else 'I'}" if lvl else None
    # PRÉ / PRÉ-ESCOLA — detecção por TOKEN para evitar falso-positivo
    # (ex.: "Prézinho" NÃO deve virar Pré; deve ser sinalizado p/ auditoria).
    _tokens = norm.split(' ')
    is_pre = (
        'PRE' in _tokens
        or 'PRE ESCOLA' in norm
        or any(t.startswith('PREESCOL') or t.startswith('PRESCOL') for t in _tokens)
    )
    if is_pre:
        lvl = _infantil_level()
        return f"PRÉ {'II' if lvl == 2 else 'I'}" if lvl else None

    # Não reconhecido (Creche, Jardim, Classe Especial, nomenclaturas novas...)
    return None
