"""Testes da canonicalização de séries (Indicadores da Rede)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.serie_canonical import canonicalize_serie as cs


def test_pre_escola_variants():
    assert cs('PRÉ-ESCOLA I') == 'PRÉ I'
    assert cs('PRE ESCOLA I') == 'PRÉ I'
    assert cs('PRE I') == 'PRÉ I'
    assert cs('Pré I') == 'PRÉ I'
    assert cs('PRÉ-ESCOLA II') == 'PRÉ II'
    assert cs('PRE ESCOLA II') == 'PRÉ II'
    assert cs('Pré II') == 'PRÉ II'
    assert cs('PREESCOLA II') == 'PRÉ II'


def test_bercario_maternal():
    assert cs('Berçário I') == 'BERÇÁRIO I'
    assert cs('BERCARIO II') == 'BERÇÁRIO II'
    assert cs('Maternal I') == 'MATERNAL I'
    assert cs('MATERNAL II') == 'MATERNAL II'
    assert cs('Maternal') == 'MATERNAL I'  # sem nível -> I


def test_fundamental():
    assert cs('1º ANO') == '1º ANO'
    assert cs('9º Ano') == '9º ANO'
    assert cs('1 ano') == '1º ANO'
    assert cs('PRIMEIRO ANO') == '1º ANO'
    assert cs('5° Ano') == '5º ANO'


def test_eja():
    assert cs('EJA 1ª ETAPA') == '1ª ETAPA'
    assert cs('1ª Etapa') == '1ª ETAPA'
    assert cs('2 etapa') == '2ª ETAPA'
    assert cs('QUARTA ETAPA') == '4ª ETAPA'


def test_nao_reconhecidas():
    assert cs('Jardim A') is None
    assert cs('Prézinho') is None
    assert cs('Maternal III') is None
    assert cs('Classe Especial') is None
    assert cs('') is None
    assert cs(None) is None
    assert cs('Creche') is None
