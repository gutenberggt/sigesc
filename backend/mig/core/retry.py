"""
RetryManager — política de retentativa completa para chamadas a provedores governamentais.

Classifica erros recuperáveis (5xx transitórios, timeout, indisponibilidade) vs.
não recuperáveis (401/403/400/config) e aplica backoff exponencial. As tentativas são
contabilizadas e podem ser registradas no audit pelo chamador.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from mig.core.exceptions import MigError

logger = logging.getLogger("mig.retry")


@dataclass
class RetryPolicy:
    max_attempts: int = 1                         # 1 = sem retentativa (comportamento neutro)
    base_delay_seconds: float = 0.5
    backoff_factor: float = 2.0
    retry_on_status: tuple = (502, 503, 504)

    def is_recoverable(self, exc: Exception) -> bool:
        return isinstance(exc, MigError) and exc.status_code in self.retry_on_status

    def should_retry(self, attempt: int, exc: Exception) -> bool:
        return attempt < self.max_attempts and self.is_recoverable(exc)

    def delay_for(self, attempt: int) -> float:
        return self.base_delay_seconds * (self.backoff_factor ** max(0, attempt - 1))


NO_RETRY = RetryPolicy(max_attempts=1)
CMDE_DEFAULT = RetryPolicy(max_attempts=3, base_delay_seconds=0.5, backoff_factor=2.0)


@dataclass
class RetryResult:
    value: object = None
    attempts: int = 0
    errors: list = field(default_factory=list)   # códigos/mensagens das tentativas falhas


async def run_with_retry(operation, policy: RetryPolicy, on_attempt=None) -> RetryResult:
    """
    Executa `operation` (coroutine sem args) aplicando `policy`.
    `on_attempt(attempt, exc, recoverable)` é chamado a cada falha (opcional).
    Retorna RetryResult com o valor e o número de tentativas.
    """
    attempt = 0
    result = RetryResult()
    while True:
        attempt += 1
        result.attempts = attempt
        try:
            result.value = await operation()
            return result
        except Exception as exc:  # noqa: BLE001 — reclassificado abaixo
            recoverable = policy.is_recoverable(exc)
            code = getattr(exc, "status_code", None)
            result.errors.append({"attempt": attempt, "code": code, "message": str(exc)})
            if on_attempt:
                try:
                    on_attempt(attempt, exc, recoverable)
                except Exception:  # pragma: no cover
                    pass
            if policy.should_retry(attempt, exc):
                delay = policy.delay_for(attempt)
                logger.warning("MIG retry attempt=%s recoverable=%s code=%s delay=%.2fs",
                               attempt, recoverable, code, delay)
                await asyncio.sleep(delay)
                continue
            raise
