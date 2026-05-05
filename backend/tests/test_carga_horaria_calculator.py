"""
Testes do calculador central de Carga Horária (CH).
Cobertura:
  - Modo 'atual' vs 'periodo'
  - Fallback 40h (sem alocações/substituições, com lotação)
  - Fallback 40h ÷ N para múltiplas lotações
  - ignore_workload (voluntários)
  - Substituições vigentes/expiradas
"""
from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock

from utils.carga_horaria_calculator import (
    calcular_carga_horaria_servidor,
    calcular_carga_por_lotacao,
    _substituicao_vigente,
    CH_PADRAO,
)


def _mock_db(*, alocacoes=None, substituicoes=None, lotacoes=None):
    """Cria um mock do `db` que devolve cursor.to_list() conforme query."""
    db = MagicMock()
    al = list(alocacoes or [])
    sb = list(substituicoes or [])
    lo = list(lotacoes or [])

    def _ta_find(query, _proj=None):
        items = []
        if query.get('is_substituicao') == True:  # noqa: E712
            items = sb
        elif query.get('is_substituicao') == {'$ne': True}:
            items = al
        else:
            items = al + sb
        # Filtros adicionais
        sid = query.get('school_id')
        ay = query.get('academic_year')
        st = query.get('status')
        out = []
        for it in items:
            if sid and it.get('school_id') != sid:
                continue
            if ay is not None and it.get('academic_year') != ay:
                continue
            if st and it.get('status') != st:
                continue
            out.append(it)
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=out)
        return cursor

    def _sa_find(query, _proj=None):
        out = [l for l in lo if (not query.get('staff_id') or l.get('staff_id') == query['staff_id'])
               and (not query.get('status') or l.get('status') == query['status'])]
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=out)
        return cursor

    db.teacher_assignments.find = MagicMock(side_effect=_ta_find)
    db.school_assignments.find = MagicMock(side_effect=_sa_find)
    return db


@pytest.mark.asyncio
async def test_servidor_sem_lotacao_retorna_zero():
    db = _mock_db()
    ch = await calcular_carga_horaria_servidor(db, 'sid')
    assert ch == 0


@pytest.mark.asyncio
async def test_servidor_com_uma_lotacao_sem_alocacao_fallback_40h():
    db = _mock_db(lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_horaria_servidor(db, 'sid')
    assert ch == CH_PADRAO


@pytest.mark.asyncio
async def test_servidor_com_alocacoes_soma_normal():
    al = [
        {'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'carga_horaria_semanal': 10},
        {'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'carga_horaria_semanal': 5},
    ]
    db = _mock_db(alocacoes=al, lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_horaria_servidor(db, 'sid')
    assert ch == 15  # não aplica fallback pois tem alocação


@pytest.mark.asyncio
async def test_alocacao_com_ignore_workload_zera():
    al = [
        {'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'carga_horaria_semanal': 10, 'ignore_workload': True},
    ]
    db = _mock_db(alocacoes=al, lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_horaria_servidor(db, 'sid')
    # alocação ignorada → cai no fallback 40h
    assert ch == CH_PADRAO


@pytest.mark.asyncio
async def test_substituicao_vigente_soma_no_modo_atual():
    sb = [{
        'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'is_substituicao': True,
        'carga_horaria_semanal': 10,
        'data_inicio_substituicao': '2026-01-01',
        'data_fim_substituicao': None,
    }]
    db = _mock_db(substituicoes=sb, lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_horaria_servidor(db, 'sid', modo='atual')
    assert ch == 10  # somou substituição vigente


@pytest.mark.asyncio
async def test_substituicao_expirada_nao_soma():
    sb = [{
        'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'is_substituicao': True,
        'carga_horaria_semanal': 10,
        'data_inicio_substituicao': '2025-01-01',
        'data_fim_substituicao': '2025-12-01',
    }]
    db = _mock_db(substituicoes=sb, lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_horaria_servidor(db, 'sid', modo='atual')
    assert ch == CH_PADRAO  # não soma substituição passada → cai no fallback


@pytest.mark.asyncio
async def test_lotacao_fallback_dividido_entre_multiplas():
    db = _mock_db(lotacoes=[
        {'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'},
        {'staff_id': 'sid', 'school_id': 'esc2', 'status': 'ativo'},
    ])
    ch_e1 = await calcular_carga_por_lotacao(db, 'sid', 'esc1')
    ch_e2 = await calcular_carga_por_lotacao(db, 'sid', 'esc2')
    assert ch_e1 == 20
    assert ch_e2 == 20


@pytest.mark.asyncio
async def test_lotacao_com_alocacao_em_outra_escola_retorna_zero():
    """Servidor com alocação em esc1 mas consulta esc2 → 0 (CH 'mora' na esc1)."""
    al = [{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo', 'carga_horaria_semanal': 30}]
    db = _mock_db(alocacoes=al, lotacoes=[
        {'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'},
        {'staff_id': 'sid', 'school_id': 'esc2', 'status': 'ativo'},
    ])
    ch = await calcular_carga_por_lotacao(db, 'sid', 'esc2')
    assert ch == 0


@pytest.mark.asyncio
async def test_lotacao_consulta_escola_sem_lotacao_ativa_retorna_zero():
    db = _mock_db(lotacoes=[{'staff_id': 'sid', 'school_id': 'esc1', 'status': 'ativo'}])
    ch = await calcular_carga_por_lotacao(db, 'sid', 'esc_inexistente')
    assert ch == 0


def test_substituicao_vigente_modo_atual_data_no_intervalo():
    s = {
        'status': 'ativo', 'is_substituicao': True,
        'data_inicio_substituicao': '2026-01-01',
        'data_fim_substituicao': '2026-12-31',
    }
    assert _substituicao_vigente(s, modo='atual', ref_date=date(2026, 6, 1)) is True
    assert _substituicao_vigente(s, modo='atual', ref_date=date(2025, 12, 31)) is False
    assert _substituicao_vigente(s, modo='atual', ref_date=date(2027, 1, 2)) is False


def test_substituicao_status_inativo_retorna_falso():
    s = {'status': 'encerrado', 'is_substituicao': True,
         'data_inicio_substituicao': '2026-01-01', 'data_fim_substituicao': None}
    assert _substituicao_vigente(s, modo='atual') is False
