"""
Cache utilitário para o SIGESC.
Cache in-memory com TTL para endpoints frequentemente acessados.
"""

import time
import hashlib
import json
from typing import Any, Optional


class TTLCache:
    """Cache simples com TTL (Time-To-Live) em segundos."""
    
    def __init__(self):
        self._store = {}
    
    def _make_key(self, prefix: str, params: dict) -> str:
        """Gera chave de cache baseada no prefixo e parâmetros."""
        raw = json.dumps(params, sort_keys=True, default=str)
        return f"{prefix}:{hashlib.md5(raw.encode()).hexdigest()}"
    
    def get(self, prefix: str, params: dict) -> Optional[Any]:
        """Busca valor do cache. Retorna None se expirado ou não existe."""
        key = self._make_key(prefix, params)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry['expires']:
            del self._store[key]
            return None
        return entry['value']
    
    def set(self, prefix: str, params: dict, value: Any, ttl: int):
        """Armazena valor no cache com TTL em segundos."""
        key = self._make_key(prefix, params)
        self._store[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
    
    def invalidate(self, prefix: str):
        """Invalida todas as entradas com o prefixo dado."""
        keys_to_delete = [k for k in self._store if k.startswith(f"{prefix}:")]
        for k in keys_to_delete:
            del self._store[k]
    
    def clear(self):
        """Limpa todo o cache."""
        self._store.clear()


# Instância global
cache = TTLCache()

# TTLs em segundos
CACHE_TTL_SCHOOLS = 180    # 3 minutos
CACHE_TTL_CLASSES = 120    # 2 minutos
CACHE_TTL_COURSES = 300    # 5 minutos
