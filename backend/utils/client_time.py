"""Contexto temporal global do SIGESC.

Contrato:
- persistência técnica/auditoria canônica permanece em UTC;
- data/hora civil exibida ao usuário e impressa em documentos usa o fuso do
  navegador/computador que originou a requisição;
- o cliente informa fuso/offset, mas NÃO fornece o instante autoritativo: o
  instante vem do relógio UTC do servidor e é apenas convertido para o fuso;
- rotinas sem requisição usam SIGESC_DEFAULT_TIMEZONE (default UTC).
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from starlette.middleware.base import BaseHTTPMiddleware


DEFAULT_TIMEZONE = os.getenv("SIGESC_DEFAULT_TIMEZONE", "UTC")
HEADER_TIMEZONE = "X-SIGESC-Timezone"
HEADER_OFFSET = "X-SIGESC-UTC-Offset-Minutes"
HEADER_LOCAL_DATE = "X-SIGESC-Local-Date"

_tz_name_var: ContextVar[str] = ContextVar("sigesc_tz_name", default=DEFAULT_TIMEZONE)
_offset_var: ContextVar[Optional[int]] = ContextVar("sigesc_tz_offset", default=None)
_source_var: ContextVar[str] = ContextVar("sigesc_tz_source", default="default")
_reported_local_date_var: ContextVar[Optional[str]] = ContextVar("sigesc_reported_local_date", default=None)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zoneinfo(name: str | None):
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return None


def _safe_offset(raw: str | int | None) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    # IANA civil offsets observed in practice fit comfortably inside +/- 14h.
    if value < -14 * 60 or value > 14 * 60:
        return None
    return value


def _current_tzinfo():
    name = _tz_name_var.get()
    zone = _safe_zoneinfo(name)
    if zone is not None:
        return zone
    offset = _offset_var.get()
    if offset is not None:
        return timezone(timedelta(minutes=offset))
    return _safe_zoneinfo(DEFAULT_TIMEZONE) or timezone.utc


def local_now(now_utc: datetime | None = None) -> datetime:
    base = now_utc or utc_now()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(_current_tzinfo())


def local_today(now_utc: datetime | None = None) -> date:
    return local_now(now_utc).date()


def local_date_iso(now_utc: datetime | None = None) -> str:
    return local_today(now_utc).isoformat()


def local_datetime_iso(now_utc: datetime | None = None, *, timespec: str = "seconds") -> str:
    return local_now(now_utc).isoformat(timespec=timespec)


def current_time_context(now_utc: datetime | None = None) -> dict:
    local = local_now(now_utc)
    offset = local.utcoffset() or timedelta(0)
    return {
        "timezone": _tz_name_var.get(),
        "timezone_source": _source_var.get(),
        "utc_offset_minutes": int(offset.total_seconds() // 60),
        "timestamp_local": local.isoformat(timespec="seconds"),
        "timestamp_utc": (now_utc or utc_now()).astimezone(timezone.utc).isoformat(timespec="seconds"),
        "reported_local_date": _reported_local_date_var.get(),
    }


def local_day_bounds_utc(day_from: str | None, day_to: str | None) -> tuple[str | None, str | None]:
    """Converte limites de datas civis do usuário em limites UTC para consulta."""
    tz = _current_tzinfo()
    start_utc = None
    end_utc = None
    if day_from:
        d = date.fromisoformat(day_from)
        start = datetime.combine(d, time.min, tzinfo=tz)
        start_utc = start.astimezone(timezone.utc).isoformat()
    if day_to:
        d = date.fromisoformat(day_to)
        end = datetime.combine(d, time.max, tzinfo=tz)
        end_utc = end.astimezone(timezone.utc).isoformat()
    return start_utc, end_utc


def _resolve_context(headers: Mapping[str, str]) -> tuple[str, Optional[int], str, Optional[str]]:
    name = headers.get(HEADER_TIMEZONE) or headers.get(HEADER_TIMEZONE.lower())
    offset = _safe_offset(headers.get(HEADER_OFFSET) or headers.get(HEADER_OFFSET.lower()))
    reported_local_date = headers.get(HEADER_LOCAL_DATE) or headers.get(HEADER_LOCAL_DATE.lower())

    if _safe_zoneinfo(name) is not None:
        return str(name), offset, "browser_timezone", reported_local_date
    if offset is not None:
        # Mantemos um nome descritivo; _current_tzinfo usa o offset como fallback.
        return "client-offset", offset, "browser_offset", reported_local_date
    return DEFAULT_TIMEZONE, None, "default", reported_local_date


@contextmanager
def use_time_context(*, timezone_name: str | None = None, utc_offset_minutes: int | None = None, source: str = "explicit"):
    """Aplica contexto temporal temporário (útil para render jobs/background)."""
    safe_name = timezone_name if _safe_zoneinfo(timezone_name) is not None else ("client-offset" if utc_offset_minutes is not None else DEFAULT_TIMEZONE)
    safe_offset = _safe_offset(utc_offset_minutes)
    t1 = _tz_name_var.set(safe_name)
    t2 = _offset_var.set(safe_offset)
    t3 = _source_var.set(source)
    try:
        yield
    finally:
        _tz_name_var.reset(t1)
        _offset_var.reset(t2)
        _source_var.reset(t3)


class ClientTimeContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        name, offset, source, reported_local_date = _resolve_context(request.headers)
        t1 = _tz_name_var.set(name)
        t2 = _offset_var.set(offset)
        t3 = _source_var.set(source)
        t4 = _reported_local_date_var.set(reported_local_date)
        try:
            request.state.sigesc_timezone = name
            request.state.sigesc_utc_offset_minutes = offset
            request.state.sigesc_time_source = source
            return await call_next(request)
        finally:
            _reported_local_date_var.reset(t4)
            _source_var.reset(t3)
            _offset_var.reset(t2)
            _tz_name_var.reset(t1)
