"""Materialization providers. No-op default (marts desligados)."""
from .null_materializer import NullMaterializer

__all__ = ["NullMaterializer"]
