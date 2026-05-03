"""Testes G3 — Relatório Mensal Executivo (Sprint Fev/2026).

Cobre:
- Validação de período
- Agregação determinística (zero alunos/zero escolas)
- Sanitização da resposta IA (limites, tipos, campos obrigatórios)
- Idempotência (mesmo período → mesmo snapshot)
- Stub de fallback quando IA indisponível
- Renderização de email
- Validade de 30 dias do código público (G1.6)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv("/app/backend/.env")

from services import monthly_report_service as mr_svc
from services.monthly_report_email import (render_monthly_report_email,
                                            report_url_for, verify_url_for)


# ---------- Helpers ----------

def _fresh_db():
    """Banco isolado por execução para evitar lixo cruzado."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "sigesc_db") + "_test_g3"]
    return client, db


async def _wipe(db):
    for coll in (
        "monthly_reports", "ai_analysis_snapshots", "verifiable_documents",
        "schools", "students", "intervention_alerts", "mantenedoras",
        "attendance", "classes", "learning_objects", "ai_plans",
        "snapshot_retention_policies", "curriculum_coverage_stats",
    ):
        await db[coll].drop()


# -----------------------
# Validação síncrona
# -----------------------

def test_norm_month_valido():
    assert mr_svc._norm_month(2026, 1) == (2026, 1)
    assert mr_svc._norm_month(2026, 12) == (2026, 12)


def test_norm_month_invalido():
    with pytest.raises(ValueError):
        mr_svc._norm_month(2026, 0)
    with pytest.raises(ValueError):
        mr_svc._norm_month(2026, 13)
    with pytest.raises(ValueError):
        mr_svc._norm_month(1999, 6)


def test_previous_month():
    y, m = mr_svc._previous_month(datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert (y, m) == (2026, 2)
    y, m = mr_svc._previous_month(datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert (y, m) == (2025, 12)


def test_validate_report_estrutura_completa():
    raw = {
        "resumo_executivo": "ok",
        "ranking": {
            "top5": [{"escola": "A", "score": 92, "destaque": "alta freq"}],
            "bottom3": [{"escola": "B", "score": 30, "alerta": "baixa cobertura"}],
        },
        "diagnostico_causal": "diag",
        "acoes_prioritarias": [
            {"acao": "ir lá", "justificativa": "x", "responsavel": "secretario",
             "prazo_dias": 7, "escolas_alvo": ["A"], "impacto": "alto"},
        ],
        "risco": "alto",
        "evidencias": [{"metrica": "x", "valor": "1", "fonte": "rede.x"}],
    }
    safe = mr_svc._validate_report(raw)
    assert safe["resumo_executivo"] == "ok"
    assert safe["risco"] == "alto"
    assert len(safe["ranking"]["top5"]) == 1
    assert safe["ranking"]["top5"][0]["score"] == 92
    assert len(safe["acoes_prioritarias"]) == 1
    assert safe["acoes_prioritarias"][0]["prazo_dias"] == 7


def test_validate_report_score_clamp():
    raw = {
        "resumo_executivo": "x",
        "ranking": {
            "top5": [{"escola": "A", "score": 150, "destaque": "x"}],
            "bottom3": [{"escola": "B", "score": -5, "alerta": "x"}],
        },
        "diagnostico_causal": "x",
        "acoes_prioritarias": [],
        "risco": "invalido",
        "evidencias": [],
    }
    safe = mr_svc._validate_report(raw)
    assert safe["ranking"]["top5"][0]["score"] == 100
    assert safe["ranking"]["bottom3"][0]["score"] == 0
    assert safe["risco"] == "medio"


def test_validate_report_max_3_acoes():
    raw = {
        "resumo_executivo": "x",
        "ranking": {"top5": [], "bottom3": []},
        "diagnostico_causal": "x",
        "acoes_prioritarias": [
            {"acao": f"a{i}", "justificativa": "j", "responsavel": "secretario",
             "prazo_dias": 7, "escolas_alvo": [], "impacto": "alto"}
            for i in range(8)
        ],
        "risco": "baixo",
        "evidencias": [],
    }
    safe = mr_svc._validate_report(raw)
    assert len(safe["acoes_prioritarias"]) == 3


def test_validate_report_prazo_invalido_vira_7():
    raw = {
        "resumo_executivo": "x",
        "ranking": {"top5": [], "bottom3": []},
        "diagnostico_causal": "x",
        "acoes_prioritarias": [
            {"acao": "x", "justificativa": "y", "responsavel": "diretor",
             "prazo_dias": 99, "escolas_alvo": [], "impacto": "medio"},
        ],
        "risco": "medio",
        "evidencias": [],
    }
    safe = mr_svc._validate_report(raw)
    assert safe["acoes_prioritarias"][0]["prazo_dias"] == 7


def test_sanitize_evidencias_filtro_vazio():
    items = [
        {"metrica": "ok", "valor": "1", "fonte": "rede.x"},
        {"metrica": "", "valor": "2", "fonte": "rede.y"},
        {"metrica": "z", "valor": "3", "fonte": "rede.z"},
    ]
    out = mr_svc._sanitize_evidencias(items)
    assert len(out) == 2
    assert out[0]["metrica"] == "ok"


# -----------------------
# Stub fallback
# -----------------------

def test_stub_report_baixo_risco_rede_saudavel():
    payload = {
        "rede": {
            "mantenedora_nome": "TesteRede", "ano": 2026, "mes": 1,
            "mes_label": "01/2026", "total_escolas": 5, "total_alunos": 1000,
            "frequencia_media_pct": 96.0, "cobertura_curricular_media_pct": 90.0,
            "alertas_no_mes_total": 2, "alertas_ativos_fim_mes_total": 1,
            "escolas_com_alertas_ativos": 1, "pct_escolas_com_alertas": 5.0,
        },
        "escolas": [
            {"id": str(i), "nome": f"E{i}", "frequencia_mes_pct": 95.0,
             "cobertura_curricular_pct": 90.0, "alertas_no_mes": 0,
             "alertas_ativos_fim_mes": 0, "aulas_lancadas_mes": 100}
            for i in range(5)
        ],
        "componentes_negligenciados": [],
    }
    out = mr_svc._stub_report(payload)
    assert out["risco"] == "baixo"
    assert len(out["acoes_prioritarias"]) == 3
    assert out["resumo_executivo"]
    assert len(out["evidencias"]) >= 4


def test_stub_report_alto_risco():
    payload = {
        "rede": {
            "mantenedora_nome": "TesteRede", "ano": 2026, "mes": 1,
            "mes_label": "01/2026", "total_escolas": 4, "total_alunos": 100,
            "frequencia_media_pct": 60.0, "cobertura_curricular_media_pct": 55.0,
            "alertas_no_mes_total": 20, "alertas_ativos_fim_mes_total": 8,
            "escolas_com_alertas_ativos": 2, "pct_escolas_com_alertas": 50.0,
        },
        "escolas": [
            {"id": str(i), "nome": f"E{i}", "frequencia_mes_pct": 60.0,
             "cobertura_curricular_pct": 50.0, "alertas_no_mes": 5,
             "alertas_ativos_fim_mes": 2, "aulas_lancadas_mes": 5}
            for i in range(4)
        ],
        "componentes_negligenciados": [{"codigo": "MAT", "alertas_ativos": 5}],
    }
    out = mr_svc._stub_report(payload)
    assert out["risco"] == "alto"
    assert len(out["ranking"]["bottom3"]) >= 1
    assert any(a.get("escolas_alvo") for a in out["acoes_prioritarias"])


# -----------------------
# Email
# -----------------------

def test_email_render_assunto_acao_urgente():
    subj, html, text = render_monthly_report_email(
        rede_nome="Mantenedora X", year=2026, month=1, risco="alto",
        n_escolas_alerta=3,
        bottom3=[{"escola": "Escola A", "alerta": "queda freq"}],
        acoes_top3=[{"acao": "visitar", "justificativa": "x",
                     "responsavel": "secretario", "prazo_dias": 7}],
        report_url="https://sigesc.app/admin/relatorios-mensais/abc",
        verify_url="https://sigesc.app/verificar/SIGESC-XXXX-YYYY",
        verification_code="SIGESC-XXXX-YYYY",
    )
    assert "AÇÃO URGENTE" in subj
    assert "3 escolas" in subj
    assert "janeiro/2026" in subj
    assert "Escola A" in html
    assert "SIGESC-XXXX-YYYY" in html
    assert "30 dias" in html
    assert "Escola A" in text


def test_email_render_assunto_baixo_risco():
    subj, html, text = render_monthly_report_email(
        rede_nome="Mantenedora X", year=2026, month=2, risco="baixo",
        n_escolas_alerta=0, bottom3=[], acoes_top3=[],
        report_url="https://sigesc.app/admin/relatorios-mensais/abc",
    )
    assert "[OK]" in subj
    assert "fevereiro/2026" in subj


def test_url_helpers():
    assert "/admin/relatorios-mensais/abc-123" in report_url_for("abc-123")
    assert "/verificar/SIGESC-XXXX" in verify_url_for("SIGESC-XXXX")


# -----------------------
# Integração com Mongo (asyncio.run)
# -----------------------

def test_aggregate_month_rede_vazia():
    async def run():
        client, db = _fresh_db()
        try:
            await _wipe(db)
            await mr_svc.ensure_indexes(db)
            payload = await mr_svc._aggregate_month(db, "tenant-x", 2026, 1)
            return payload
        finally:
            client.close()

    payload = asyncio.run(run())
    assert payload["rede"]["total_escolas"] == 0
    assert payload["escolas"] == []
    assert payload["rede"]["frequencia_media_pct"] is None


def test_aggregate_month_com_escolas():
    async def run():
        client, db = _fresh_db()
        try:
            await _wipe(db)
            await mr_svc.ensure_indexes(db)
            await db.mantenedoras.insert_one({
                "id": "tenant-1", "nome": "Mantenedora Teste", "status": "active",
            })
            await db.schools.insert_many([
                {"id": "s1", "name": "Escola Um", "mantenedora_id": "tenant-1", "status": "active"},
                {"id": "s2", "name": "Escola Dois", "mantenedora_id": "tenant-1", "status": "active"},
            ])
            await db.students.insert_many([
                {"id": f"st{i}", "mantenedora_id": "tenant-1",
                 "school_id": "s1", "status": "active"}
                for i in range(10)
            ])
            await db.intervention_alerts.insert_many([
                {"id": "a1", "school_id": "s1", "componente_codigo": "MAT",
                 "first_detected_at": "2026-01-15T10:00:00+00:00", "resolved_at": None,
                 "escalation_level": 1, "status": "active"},
                {"id": "a2", "school_id": "s1", "componente_codigo": "POR",
                 "first_detected_at": "2026-01-20T10:00:00+00:00", "resolved_at": None,
                 "escalation_level": 1, "status": "active"},
            ])
            return await mr_svc._aggregate_month(db, "tenant-1", 2026, 1)
        finally:
            client.close()

    payload = asyncio.run(run())
    assert payload["rede"]["total_escolas"] == 2
    assert payload["rede"]["total_alunos"] == 10
    assert payload["rede"]["mantenedora_nome"] == "Mantenedora Teste"
    assert payload["rede"]["alertas_ativos_fim_mes_total"] == 2
    assert payload["rede"]["alertas_no_mes_total"] == 2
    s1 = next(e for e in payload["escolas"] if e["id"] == "s1")
    assert s1["alertas_ativos_fim_mes"] == 2
    assert payload["componentes_negligenciados"]


def test_generate_idempotente(monkeypatch):
    async def fake_claude(*a, **kw):
        return None
    monkeypatch.setattr(mr_svc, "_call_claude", fake_claude)

    async def run():
        client, db = _fresh_db()
        try:
            await _wipe(db)
            await mr_svc.ensure_indexes(db)
            await db.mantenedoras.insert_one({
                "id": "tenant-1", "nome": "Mantenedora Teste", "status": "active",
            })
            await db.schools.insert_one({
                "id": "s1", "name": "Escola Um", "mantenedora_id": "tenant-1", "status": "active",
            })
            user = {"id": "u1", "email": "u1@test", "role": "admin"}
            r1 = await mr_svc.generate_monthly_report(
                db, mantenedora_id="tenant-1", year=2026, month=1, user=user
            )
            r2 = await mr_svc.generate_monthly_report(
                db, mantenedora_id="tenant-1", year=2026, month=1, user=user
            )
            return r1, r2
        finally:
            client.close()

    r1, r2 = asyncio.run(run())
    assert r1["from_cache"] is False
    assert r1["risco"] in mr_svc._RISK_VALUES
    code = r1["verification_code"]
    assert code and code.startswith("SIGESC-")
    assert r2["from_cache"] is True
    assert r2["id"] == r1["id"]
    assert r2["verification_code"] == r1["verification_code"]


def test_generate_rede_vazia_falha(monkeypatch):
    async def fake_claude(*a, **kw):
        return None
    monkeypatch.setattr(mr_svc, "_call_claude", fake_claude)

    async def run():
        client, db = _fresh_db()
        try:
            await _wipe(db)
            await mr_svc.ensure_indexes(db)
            user = {"id": "u1", "email": "u1@test", "role": "admin"}
            await mr_svc.generate_monthly_report(
                db, mantenedora_id="tenant-vazio", year=2026, month=1, user=user
            )
        finally:
            client.close()

    with pytest.raises(ValueError, match="Rede vazia"):
        asyncio.run(run())


def test_generate_aplica_validade_30_dias(monkeypatch):
    async def fake_claude(*a, **kw):
        return None
    monkeypatch.setattr(mr_svc, "_call_claude", fake_claude)

    async def run():
        client, db = _fresh_db()
        try:
            await _wipe(db)
            await mr_svc.ensure_indexes(db)
            await db.mantenedoras.insert_one({
                "id": "tenant-1", "nome": "Test", "status": "active",
            })
            await db.schools.insert_one({
                "id": "s1", "name": "Escola", "mantenedora_id": "tenant-1", "status": "active",
            })
            user = {"id": "u1", "email": "u1@test", "role": "admin"}
            r = await mr_svc.generate_monthly_report(
                db, mantenedora_id="tenant-1", year=2026, month=1, user=user
            )
            vdoc = await db.verifiable_documents.find_one(
                {"code": r["verification_code"]}, {"_id": 0}
            )
            return vdoc
        finally:
            client.close()

    vdoc = asyncio.run(run())
    assert vdoc is not None
    assert vdoc["expires_at"] is not None
    exp = datetime.fromisoformat(vdoc["expires_at"].replace("Z", "+00:00"))
    delta = exp - datetime.now(timezone.utc)
    assert 29 * 86400 < delta.total_seconds() < 31 * 86400
