"""Geração de Correlation ID para rastreamento ponta a ponta de operações MIG."""
import secrets
from datetime import datetime, timezone


def generate_correlation_id(provider: str = "CMDE") -> str:
    """Ex.: CMDE-20260730-A92F3 (prefixo do provider + data UTC + sufixo hex)."""
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()[:5]
    return f"{(provider or 'MIG').upper()}-{day}-{suffix}"
