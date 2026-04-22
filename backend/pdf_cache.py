"""
Cache TTL simples em memória para dados frequentes usados nos PDFs.

⚠️  PERFORMANCE — LEIA ANTES DE MUDAR CÓDIGO DE PDF  ⚠️
-------------------------------------------------------
A geração de PDFs foi otimizada em 2026-02 para eliminar gargalos:

  1. **Sem N+1 queries** — sempre use `$in` para buscar múltiplos docs
     (ex.: course_names, enrollments). NÃO coloque find_one() dentro
     de loops.
  2. **Cache TTL** — mantenedora, logo e calendário letivo usam este
     cache (ver get_mantenedora_cached, etc). TTL padrão: 5 min.
  3. **asyncio.gather** — queries independentes devem rodar em paralelo.
  4. **Projeções** — sempre passe {"_id": 0, "campo": 1} nos find(),
     reduzindo bytes em trânsito.
  5. **Índices MongoDB** — adicione novos índices via ensure_indexes()
     em backend/server.py startup. NÃO deixe queries sem índice no hot path.
  6. **Cache de estilos/logos** — já existe em /app/backend/pdf/utils.py
     (_styles_cache, _logo_memory_cache). Reutilize.

Se precisar expandir o pipeline de PDFs:
  - Evite processamento síncrono pesado (ReportLab é CPU-bound; um PDF
    grande deve terminar em < 2s).
  - Se demorar mais que isso, mova para background task + status polling.
  - Nunca baixe imagens externas sem cache em disco/memória.
"""
from __future__ import annotations
import asyncio
import time
from typing import Any, Callable, Optional


class _TTLCache:
    """Dict simples com TTL por chave (thread/async seguro o suficiente para FastAPI)."""

    def __init__(self, default_ttl: float = 300.0):
        self._data: dict[Any, tuple[float, Any]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: Any) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    async def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._data[key] = (time.monotonic() + ttl, value)

    async def get_or_fetch(self, key: Any, fetcher: Callable, ttl: Optional[float] = None):
        cached = await self.get(key)
        if cached is not None:
            return cached
        async with self._lock:
            # Double-check após o lock
            cached = await self.get(key)
            if cached is not None:
                return cached
            value = await fetcher() if asyncio.iscoroutinefunction(fetcher) else fetcher()
            await self.set(key, value, ttl)
            return value

    def invalidate(self, key: Any = None) -> None:
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)


# Instância global
pdf_cache = _TTLCache(default_ttl=300.0)  # 5 minutos


async def get_mantenedora_cached(db, tenant_id: Optional[str] = None) -> Optional[dict]:
    """Retorna mantenedora ativa (multi-tenant) com cache de 5 min.
    
    Prioridade:
      1. Se tenant_id informado → busca na coleção multi-tenant `mantenedoras`.
      2. Fallback: única mantenedora da coleção `mantenedoras`.
      3. Fallback legado: coleção singular `mantenedora` (deprecada).
    """
    key = f"mantenedora:{tenant_id or 'global'}"
    async def fetch():
        # 1) Busca no multi-tenant
        if tenant_id:
            doc = await db.mantenedoras.find_one({"id": tenant_id}, {"_id": 0})
            if doc:
                return doc
        # 2) Single-tenant típico: 1 mantenedora só
        doc = await db.mantenedoras.find_one({}, {"_id": 0})
        if doc:
            return doc
        # 3) Fallback legado
        return await db.mantenedora.find_one({}, {"_id": 0})
    return await pdf_cache.get_or_fetch(key, fetch, ttl=300.0)


async def read_mantenedora_for_request(db, request=None, user=None) -> Optional[dict]:
    """Helper para rotas: resolve o tenant ativo a partir do request/user e retorna
    o documento da mantenedora. Substitui os usos legados de `db.mantenedora.find_one({})`.
    """
    tenant_id = None
    try:
        from tenant_scope import get_mantenedora_scope
        if user is None and request is not None:
            from auth_middleware import AuthMiddleware
            try:
                user = await AuthMiddleware.get_current_user(request)
            except Exception:
                user = None
        if user is not None:
            tenant_id = get_mantenedora_scope(user, request)
    except Exception:
        tenant_id = None
    return await get_mantenedora_cached(db, tenant_id)


async def get_calendario_cached(db, academic_year: int, school_id: Optional[str] = None) -> Optional[dict]:
    """Retorna calendário letivo com cache de 5 min."""
    key = f"calendario:{academic_year}:{school_id or 'global'}"
    async def fetch():
        cal = await db.calendario_letivo.find_one(
            {"ano_letivo": academic_year, "school_id": school_id}, {"_id": 0}
        )
        if not cal:
            cal = await db.calendario_letivo.find_one(
                {"ano_letivo": academic_year}, {"_id": 0}
            )
        return cal
    return await pdf_cache.get_or_fetch(key, fetch, ttl=300.0)


async def get_school_cached(db, school_id: str) -> Optional[dict]:
    """Retorna escola pelo ID com cache de 5 min."""
    key = f"school:{school_id}"
    async def fetch():
        return await db.schools.find_one({"id": school_id}, {"_id": 0})
    return await pdf_cache.get_or_fetch(key, fetch, ttl=300.0)
