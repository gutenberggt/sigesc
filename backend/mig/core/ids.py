"""Correlation ID (rastreio ponta a ponta) e chave de idempotência determinística do MIG."""
import hashlib
import secrets
from datetime import datetime, timezone


def generate_correlation_id(provider: str = "CMDE") -> str:
    """Ex.: CMDE-20260730-A92F3 (prefixo do provider + data UTC + sufixo hex)."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()[:5]
    return f"{(provider or 'MIG').upper()}-{day}-{suffix}"


def compute_idempotency_key(*, tenant, provider: str, operation: str, competencia: str,
                            student_id: str, school_inep: str = "", payload_version=1) -> str:
    """
    Chave DETERMINÍSTICA de idempotência para um item de envio.

    Mesmas entradas → mesma chave (índice unique impede duplicidade). Uma correção de
    dado deve incrementar `payload_version` para gerar nova chave (reenvio controlado).
    """
    raw = "|".join([
        str(tenant), str(provider), str(operation), str(competencia),
        str(student_id), str(school_inep), str(payload_version),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
