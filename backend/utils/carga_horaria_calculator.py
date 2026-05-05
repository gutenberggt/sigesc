"""
Calculadora central de Carga Horária (CH) — fonte única de verdade.

Princípio (Fev/2026): a CH do servidor não é mais armazenada manualmente. É **derivada**
de:
  - alocações ativas (`teacher_assignments` regulares)
  - substituições no período (`teacher_assignments` com `is_substituicao=True`)

Fallback: na ausência total de alocações/substituições, **40h/semana** distribuídas
igualmente entre as lotações ativas do servidor.

Modos:
  - `atual`: considera substituições vigentes na data de referência (default: hoje).
    Usado por: folha de pagamento, telas operacionais, headers do cadastro.
  - `periodo`: considera substituições que se sobrepõem a um intervalo `[from, to]`
    OU ao ano letivo informado. Usado por: relatórios anuais, folha histórica.

Funções públicas:
  - calcular_carga_horaria_servidor(db, staff_id, *, modo, ...) -> int
  - calcular_carga_por_lotacao(db, staff_id, school_id, *, modo, ...) -> int
  - calcular_carga_horaria_servidor_breakdown(...) -> dict (auditoria)

NÃO duplique esta lógica. Endpoints HR, telas, scripts e relatórios devem chamar
estas funções.
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Optional, Literal, Dict, Any

CH_PADRAO = 40
Modo = Literal['atual', 'periodo']


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _substituicao_vigente(
    assign: Dict[str, Any],
    *,
    modo: Modo,
    ref_date: Optional[date] = None,
    periodo_de: Optional[date] = None,
    periodo_ate: Optional[date] = None,
    academic_year: Optional[int] = None,
) -> bool:
    """Determina se uma substituição é considerada ativa no contexto pedido.

    `modo='atual'`: vigente na `ref_date` (default = hoje).
    `modo='periodo'`: sobrepõe-se a `[periodo_de, periodo_ate]` OU pertence ao
    `academic_year` informado. Se ambos `periodo_*` e `academic_year` ausentes,
    cai para `modo='atual'`.
    """
    if assign.get('status') != 'ativo':
        return False
    if not assign.get('is_substituicao'):
        return False

    di = _parse_date(assign.get('data_inicio_substituicao'))
    df = _parse_date(assign.get('data_fim_substituicao'))

    if modo == 'atual':
        ref = ref_date or date.today()
        if di and di > ref:
            return False
        if df and df < ref:
            return False
        return True

    # modo == 'periodo'
    if periodo_de or periodo_ate:
        de = periodo_de
        ate = periodo_ate
        # Se substituição não tem datas, considera vigente no período informado.
        if di is None and df is None:
            return assign.get('academic_year') == academic_year if academic_year else True
        # Sobreposição [di, df] ∩ [de, ate]
        if de and df and df < de:
            return False
        if ate and di and di > ate:
            return False
        return True

    if academic_year is not None:
        return assign.get('academic_year') == academic_year

    # fallback duro: trata como 'atual'
    return _substituicao_vigente(assign, modo='atual')


async def _fetch_alocacoes_regulares(db, staff_id: str, *, school_id: Optional[str], academic_year: Optional[int]):
    q: Dict[str, Any] = {
        'staff_id': staff_id,
        'status': 'ativo',
        'is_substituicao': {'$ne': True},
    }
    if school_id:
        q['school_id'] = school_id
    if academic_year is not None:
        q['academic_year'] = academic_year
    return await db.teacher_assignments.find(q, {'_id': 0}).to_list(2000)


async def _fetch_substituicoes(db, staff_id: str, *, school_id: Optional[str], academic_year: Optional[int]):
    q: Dict[str, Any] = {
        'staff_id': staff_id,
        'is_substituicao': True,
    }
    if school_id:
        q['school_id'] = school_id
    if academic_year is not None:
        q['academic_year'] = academic_year
    return await db.teacher_assignments.find(q, {'_id': 0}).to_list(2000)


async def _fetch_lotacoes_ativas(db, staff_id: str):
    return await db.school_assignments.find(
        {'staff_id': staff_id, 'status': 'ativo'}, {'_id': 0}
    ).to_list(200)


def _ch_alocacao(assign: Dict[str, Any]) -> int:
    """CH semanal de uma alocação, respeitando ignore_workload (voluntário)."""
    if assign.get('ignore_workload'):
        return 0
    return int(assign.get('carga_horaria_semanal') or 0)


async def calcular_carga_horaria_servidor(
    db,
    staff_id: str,
    *,
    modo: Modo = 'atual',
    ref_date: Optional[date] = None,
    periodo_de: Optional[date] = None,
    periodo_ate: Optional[date] = None,
    academic_year: Optional[int] = None,
) -> int:
    """Carga horária total do servidor (todas as escolas).

    = Σ alocações ativas + Σ substituições no período
    Fallback: 40h se servidor possui lotação(ões) e nenhuma alocação/substituição.
    Retorna 0 se servidor não possui nenhuma lotação ativa.
    """
    alocs = await _fetch_alocacoes_regulares(db, staff_id, school_id=None, academic_year=academic_year)
    substs = await _fetch_substituicoes(db, staff_id, school_id=None, academic_year=academic_year)

    total = sum(_ch_alocacao(a) for a in alocs)
    for s in substs:
        if _substituicao_vigente(
            s, modo=modo, ref_date=ref_date,
            periodo_de=periodo_de, periodo_ate=periodo_ate, academic_year=academic_year,
        ):
            total += _ch_alocacao(s)

    if total > 0:
        return total

    # Fallback: 40h se servidor tem ao menos 1 lotação ativa
    lotacoes = await _fetch_lotacoes_ativas(db, staff_id)
    if lotacoes:
        return CH_PADRAO
    return 0


async def calcular_carga_por_lotacao(
    db,
    staff_id: str,
    school_id: str,
    *,
    modo: Modo = 'atual',
    ref_date: Optional[date] = None,
    periodo_de: Optional[date] = None,
    periodo_ate: Optional[date] = None,
    academic_year: Optional[int] = None,
) -> int:
    """Carga horária do servidor numa escola específica.

    = Σ alocações naquela escola + Σ substituições naquela escola no período
    Fallback (sem alocação/substituição em nenhuma escola): 40h dividido pelo
    número de lotações ativas do servidor.
    """
    alocs = await _fetch_alocacoes_regulares(db, staff_id, school_id=school_id, academic_year=academic_year)
    substs = await _fetch_substituicoes(db, staff_id, school_id=school_id, academic_year=academic_year)

    total = sum(_ch_alocacao(a) for a in alocs)
    for s in substs:
        if _substituicao_vigente(
            s, modo=modo, ref_date=ref_date,
            periodo_de=periodo_de, periodo_ate=periodo_ate, academic_year=academic_year,
        ):
            total += _ch_alocacao(s)

    if total > 0:
        return total

    # Fallback: confere se servidor tem QUALQUER alocação/substituição (em outra escola)
    # — nesse caso esta lotação contribui 0 (a CH "vive" nas outras escolas).
    alocs_total = await _fetch_alocacoes_regulares(db, staff_id, school_id=None, academic_year=academic_year)
    substs_total = await _fetch_substituicoes(db, staff_id, school_id=None, academic_year=academic_year)
    if alocs_total:
        return 0
    for s in substs_total:
        if _substituicao_vigente(
            s, modo=modo, ref_date=ref_date,
            periodo_de=periodo_de, periodo_ate=periodo_ate, academic_year=academic_year,
        ):
            return 0

    # Sem alocação/substituição em nenhuma escola: distribui 40h entre lotações ativas.
    lotacoes = await _fetch_lotacoes_ativas(db, staff_id)
    n = len(lotacoes)
    if n == 0:
        return 0
    # Garante que a lotação consultada está entre as ativas, senão retorna 0.
    if not any(lot.get('school_id') == school_id for lot in lotacoes):
        return 0
    return CH_PADRAO // n if n > 0 else 0


async def calcular_carga_horaria_servidor_breakdown(
    db,
    staff_id: str,
    *,
    modo: Modo = 'atual',
    ref_date: Optional[date] = None,
    academic_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Versão detalhada para UI/auditoria — retorna total, por escola e fonte (alocacao/substituicao/fallback)."""
    alocs = await _fetch_alocacoes_regulares(db, staff_id, school_id=None, academic_year=academic_year)
    substs_all = await _fetch_substituicoes(db, staff_id, school_id=None, academic_year=academic_year)
    substs = [
        s for s in substs_all
        if _substituicao_vigente(s, modo=modo, ref_date=ref_date, academic_year=academic_year)
    ]
    lotacoes = await _fetch_lotacoes_ativas(db, staff_id)

    por_escola: Dict[str, Dict[str, Any]] = {}
    for a in alocs:
        sid = a.get('school_id') or '_'
        por_escola.setdefault(sid, {'school_id': sid, 'alocacoes': 0, 'substituicoes': 0, 'fallback': False})
        por_escola[sid]['alocacoes'] += _ch_alocacao(a)
    for s in substs:
        sid = s.get('school_id') or '_'
        por_escola.setdefault(sid, {'school_id': sid, 'alocacoes': 0, 'substituicoes': 0, 'fallback': False})
        por_escola[sid]['substituicoes'] += _ch_alocacao(s)

    total_calc = sum(e['alocacoes'] + e['substituicoes'] for e in por_escola.values())
    fallback_aplicado = False

    if total_calc == 0 and lotacoes:
        fallback_aplicado = True
        n = len(lotacoes)
        ch_each = CH_PADRAO // n if n > 0 else 0
        for lot in lotacoes:
            sid = lot.get('school_id') or '_'
            por_escola.setdefault(sid, {'school_id': sid, 'alocacoes': 0, 'substituicoes': 0, 'fallback': False})
            por_escola[sid]['fallback'] = True
            por_escola[sid]['ch_fallback'] = ch_each
        total_calc = CH_PADRAO if any(e.get('fallback') for e in por_escola.values()) else 0

    return {
        'staff_id': staff_id,
        'modo': modo,
        'total': total_calc,
        'fallback_aplicado': fallback_aplicado,
        'por_escola': list(por_escola.values()),
        'qtd_alocacoes': len(alocs),
        'qtd_substituicoes_vigentes': len(substs),
        'qtd_lotacoes_ativas': len(lotacoes),
    }
