"""Cache providers. No-op default (não altera comportamento)."""
from .null_cache import NullCacheProvider

__all__ = ["NullCacheProvider"]
