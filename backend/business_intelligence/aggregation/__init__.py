"""Aggregation — agregação por granularidade (base)."""
from .base import BaseAggregator, IdentityAggregator, GrainLadder

__all__ = ["BaseAggregator", "IdentityAggregator", "GrainLadder"]
