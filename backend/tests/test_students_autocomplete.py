"""
Testes para o pipeline de autocomplete de alunos.

Cobre:
- mask_cpf: formato esperado e edge cases.
- check_autocomplete_rate_limit: bloqueio após N chamadas.
- record/get_autocomplete_metrics: contadores corretos.

Diretriz arquitetural: ver /app/docs/SEARCH_ARCHITECTURE.md
"""
import sys
import os
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.students_search import (
    mask_cpf,
    check_autocomplete_rate_limit,
    record_autocomplete_metrics,
    get_autocomplete_metrics_snapshot,
    _rate_buckets,
    _metrics,
)


# ============================================================================
# mask_cpf
# ============================================================================
class TestMaskCpf:
    def test_cpf_formatado(self):
        assert mask_cpf("123.456.789-01") == "***.456.***-01"

    def test_cpf_apenas_digitos(self):
        assert mask_cpf("12345678901") == "***.456.***-01"

    def test_cpf_com_espacos_e_traços(self):
        assert mask_cpf("  123-456-789-01 ") == "***.456.***-01"

    def test_cpf_invalido_retorna_none(self):
        # Menos de 11 dígitos → não vaza dado parcial
        assert mask_cpf("12345") is None

    def test_cpf_vazio_retorna_none(self):
        assert mask_cpf("") is None
        assert mask_cpf(None) is None

    def test_cpf_com_letras_so_extrai_digitos(self):
        # Se sobram 11 dígitos válidos depois de limpar, mascara
        assert mask_cpf("ABC12345678901XYZ") == "***.456.***-01"


# ============================================================================
# Rate limit
# ============================================================================
class TestRateLimit:
    def setup_method(self):
        # Limpa buckets entre testes
        _rate_buckets.clear()

    def test_permite_até_30_chamadas(self):
        for _ in range(30):
            check_autocomplete_rate_limit("user-A")
        # 31ª deve bloquear
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_autocomplete_rate_limit("user-A")
        assert exc.value.status_code == 429

    def test_isola_users(self):
        # Usuário B não é afetado pelo A
        for _ in range(30):
            check_autocomplete_rate_limit("user-A")
        # B continua livre
        check_autocomplete_rate_limit("user-B")  # não levanta

    def test_user_id_vazio_não_trava(self):
        # Sem user_id, não há como aplicar (auth já barra antes); deve passar
        for _ in range(100):
            check_autocomplete_rate_limit("")  # não levanta


# ============================================================================
# Metrics
# ============================================================================
class TestMetrics:
    def setup_method(self):
        # Reseta contadores
        _metrics["total_calls"] = 0
        _metrics["fallback_contains_calls"] = 0
        _metrics["total_duration_ms"] = 0.0
        _metrics["empty_results"] = 0

    def test_record_e_snapshot(self):
        record_autocomplete_metrics(used_fallback=False, duration_ms=10.0, result_count=5)
        record_autocomplete_metrics(used_fallback=True, duration_ms=20.0, result_count=0)
        record_autocomplete_metrics(used_fallback=False, duration_ms=15.0, result_count=3)

        snap = get_autocomplete_metrics_snapshot()
        assert snap["total_calls"] == 3
        assert snap["fallback_contains_calls"] == 1
        assert snap["fallback_pct"] == pytest.approx(33.33, rel=1e-2)
        assert snap["empty_results"] == 1
        assert snap["empty_pct"] == pytest.approx(33.33, rel=1e-2)
        assert snap["avg_duration_ms"] == pytest.approx(15.0, rel=1e-2)

    def test_snapshot_zero_calls(self):
        snap = get_autocomplete_metrics_snapshot()
        assert snap["total_calls"] == 0
        assert snap["avg_duration_ms"] == 0.0
        assert snap["fallback_pct"] == 0.0
