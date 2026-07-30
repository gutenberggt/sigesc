"""Exceções tipadas do MIG (agnósticas de framework)."""


class MigError(Exception):
    """Erro base do MIG."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class MigConfigError(MigError):
    """Integração não configurada / configuração inválida."""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class MigAuthError(MigError):
    """Credenciais inválidas/expiradas no provedor externo."""
    def __init__(self, message: str):
        super().__init__(message, status_code=401)


class MigForbiddenError(MigError):
    """Acesso negado pelo provedor externo (ex.: IP não autorizado)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=403)


class MigUpstreamError(MigError):
    """Erro genérico retornado pelo provedor externo."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code=status_code)


class MigUnavailableError(MigError):
    """Falha de conexão com o provedor externo."""
    def __init__(self, message: str):
        super().__init__(message, status_code=503)


class MigTimeoutError(MigError):
    """Tempo limite excedido ao chamar o provedor externo."""
    def __init__(self, message: str):
        super().__init__(message, status_code=504)
