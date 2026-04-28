"""Helpers de busca textual com tolerância a acentos."""
import re

# Mapa de classes de equivalência: cada letra base → conjunto de variantes.
_ACCENT_CLASSES = {
    'a': '[aáàâãäåAÁÀÂÃÄÅ]',
    'e': '[eéèêëEÉÈÊË]',
    'i': '[iíìîïIÍÌÎÏ]',
    'o': '[oóòôõöOÓÒÔÕÖ]',
    'u': '[uúùûüUÚÙÛÜ]',
    'c': '[cçCÇ]',
    'n': '[nñNÑ]',
    'y': '[yýYÝ]',
}


def accent_insensitive_regex(term: str) -> str:
    """Converte um termo de busca em um padrão regex insensível a acentos.

    Cada letra-base é substituída por sua classe de variantes acentuadas.
    Demais caracteres são escapados literalmente.

    >>> accent_insensitive_regex("joao")
    '[jJ][oóòôõö...].[aáàâãäåAÁÀÂÃÄÅ]...'
    """
    if not term:
        return ''
    parts = []
    for ch in term:
        low = ch.lower()
        if low in _ACCENT_CLASSES:
            parts.append(_ACCENT_CLASSES[low])
        else:
            parts.append(re.escape(ch))
    return ''.join(parts)
