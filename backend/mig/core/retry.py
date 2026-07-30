"""RetryManager — contrato de política de retentativa (estrutura da fundação).

O uso pleno (backoff + dead-letter em fila) pertence à sprint de infra. Aqui só o contrato,
para que o cliente HTTP já possa referenciá-lo sem alterar comportamento atual.
"""
from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_attempts: int = 1          # fundação: sem retentativa automática (comportamento atual)
    base_delay_seconds: float = 0.5
    backoff_factor: float = 2.0
    retry_on_status: tuple = (502, 503, 504)

    def should_retry(self, attempt: int, status_code: int) -> bool:
        return attempt < self.max_attempts and status_code in self.retry_on_status

    def delay_for(self, attempt: int) -> float:
        return self.base_delay_seconds * (self.backoff_factor ** max(0, attempt - 1))


NO_RETRY = RetryPolicy(max_attempts=1)
