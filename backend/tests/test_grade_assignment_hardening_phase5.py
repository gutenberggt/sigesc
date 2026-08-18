"""Guards estruturais do hardening residual da Fase 5."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENING = (ROOT / "routers" / "grades_dvd_hardening.py").read_text(encoding="utf-8")
ROUTERS_INIT = (ROOT / "routers" / "__init__.py").read_text(encoding="utf-8")


def test_hardening_e_instalado_depois_do_adapter_principal():
    assert "from .grades_dvd_hardening import install_grades_dvd_hardening" in ROUTERS_INIT
    assert "configured = install_grades_dvd_adapter(" in ROUTERS_INIT
    assert "return install_grades_dvd_hardening(" in ROUTERS_INIT
    assert ROUTERS_INIT.index("install_grades_dvd_adapter(") < ROUTERS_INIT.index("install_grades_dvd_hardening(")


def test_hardening_bloqueia_escrita_com_ownership_historico_sem_vinculo_ativo():
    assert "DVD_HISTORICAL_OWNERSHIP_REQUIRES_ACTIVE_ASSIGNMENT" in HARDENING
    assert "_has_historical_ownership(" in HARDENING
    assert "_block_historical_write_bypass(" in HARDENING


def test_sync_pull_filtra_por_autoria_antes_da_paginacao():
    assert 'grade_ownership.{field}.teacher_id' in HARDENING
    assert "count_documents(query)" in HARDENING
    assert ".skip(skip).limit(safe_size)" in HARDENING
    assert "sync_mod.fetch_collection_data_paginated = hardened_fetch" in HARDENING


def test_sync_push_historico_tambem_falha_fechado():
    assert "sync_mod.process_sync_operation = hardened_process" in HARDENING
    assert 'if op.collection == "grades" and user.get("role") == "professor"' in HARDENING
    assert "DVD_HISTORICAL_OWNERSHIP_REQUIRES_ACTIVE_ASSIGNMENT" in HARDENING
