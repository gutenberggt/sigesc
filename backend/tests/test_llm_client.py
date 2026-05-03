"""Testes G3+ — wrapper híbrido LLM (anthropic direct ↔ emergent universal)."""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import llm_client


def test_provider_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    assert llm_client.llm_provider() == "none"


def test_provider_anthropic_takes_precedence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-emergent-test")
    assert llm_client.llm_provider() == "anthropic_direct"


def test_provider_emergent_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-emergent-test")
    assert llm_client.llm_provider() == "emergent_universal"


def test_chat_returns_none_when_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    res = asyncio.run(llm_client.chat_with_claude(
        system_prompt="x", user_text="y", session_id="z"
    ))
    assert res is None


def test_default_model_is_sonnet_4_5():
    assert llm_client.DEFAULT_MODEL == "claude-sonnet-4-5-20250929"
