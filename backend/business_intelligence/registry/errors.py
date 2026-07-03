"""Erros do Formula Registry."""


class RegistryError(Exception):
    """Base para erros do Registry."""


class IndicatorNotFoundError(RegistryError):
    """Indicador/versão inexistente."""


class DuplicateDefinitionError(RegistryError):
    """Tentativa de registrar (code, version) já existente."""


class NoActiveVersionError(RegistryError):
    """Nenhuma versão ACTIVE disponível para o code."""
