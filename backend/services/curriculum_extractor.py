"""
Extrator de habilidades curriculares do DCM de Floresta do Araguaia.

ESTRATÉGIA V2 (May 2026): extração estruturada por tabela.

O DCM usa tabelas com o seguinte padrão (verificado em múltiplas páginas):

  Linha 0: ['', 'COMPONENTE CURRICULAR', 'ETAPA DE ENSINO', 'ANO', 'BIMESTRE']
  Linha 1: ['EIXOS ESTRUTURANTES', 'LÍNGUA PORTUGUESA', 'ENSINO FUNDAMENTAL - ANOS FINAIS', '6º', '3º']
  Linha 2: ['', 'OBJETOS DO CONHECIMENTO', 'HABILIDADES', 'PROPOSTAS DE', 'Nº DE']
  Linha 3+: conteúdo, onde a coluna HABILIDADES contém o texto limpo.

O extractor:
  1. Lê `page.extract_tables()` (respeita estrutura de colunas).
  2. Detecta metadados (componente, etapa, ano, bimestre, eixo) nas linhas 0-1.
  3. Identifica índice da coluna "HABILIDADES" na linha 2.
  4. Para cada linha de conteúdo, extrai códigos BNCC + descrição SÓ da coluna HABILIDADES.
  5. Sem mistura de colunas.

Fallback: se uma página não tem estrutura de tabela reconhecível, ignora (em vez
de extrair com ruído pelo regex). Isso prioriza qualidade sobre quantidade.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

BNCC_CODE_RE = re.compile(r'\b(E[FIM])(\d{2})([A-Z]{2})(\d{2}[A-Z]?)\b')

COMPONENT_MAP = {
    'LP': ('Língua Portuguesa', 'anos_iniciais'),
    'MA': ('Matemática', 'anos_iniciais'),
    'CI': ('Ciências', 'anos_iniciais'),
    'GE': ('Geografia', 'anos_iniciais'),
    'HI': ('História', 'anos_iniciais'),
    'AR': ('Arte', 'anos_iniciais'),
    'EF': ('Educação Física', 'anos_iniciais'),
    'LI': ('Língua Inglesa', 'anos_finais'),
    'ER': ('Ensino Religioso', 'anos_iniciais'),
    'CO': ('Computação', 'anos_iniciais'),
    'EA': ('Estudos Amazônicos', 'anos_iniciais'),
    'EO': ('O eu, o outro e o nós', 'infantil'),
    'CG': ('Corpo, gestos e movimentos', 'infantil'),
    'TS': ('Traços, sons, cores e formas', 'infantil'),
    'ET': ('Espaços, tempos, quantidades, relações e transformações', 'infantil'),
}


def _classify_etapa(prefix: str, ano: Optional[int], etapa_txt: str = '') -> str:
    etapa_txt = (etapa_txt or '').lower()
    if prefix == 'EI' or 'infantil' in etapa_txt:
        return 'infantil'
    if prefix == 'EM' or 'médio' in etapa_txt or 'medio' in etapa_txt:
        return 'medio'
    if 'eja' in etapa_txt:
        return 'eja'
    if 'anos finais' in etapa_txt:
        return 'anos_finais'
    if 'anos iniciais' in etapa_txt:
        return 'anos_iniciais'
    if ano and 1 <= ano <= 5:
        return 'anos_iniciais'
    if ano and 6 <= ano <= 9:
        return 'anos_finais'
    return 'anos_iniciais'


def _clean_cell(text: str) -> str:
    """Limpa uma célula de tabela PDF: normaliza espaços, remove quebras soltas."""
    if not text:
        return ''
    text = re.sub(r'-\s*\n\s*', '', text)  # junta hifenação
    text = re.sub(r'\s*\n\s*', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_ano(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r'(\d+)', s)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 9 else None


def _parse_bimestre(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r'(\d+)', s)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 4 else None


def _parse_metadata(table: list) -> dict:
    """
    Extrai metadados (componente, ano, bimestre, etapa, eixo) das linhas de
    cabeçalho. Tolerante a variações: procura as palavras-chave nas 2 primeiras
    linhas e pega o valor correspondente na linha seguinte.
    """
    meta: dict = {
        'componente_nome': None, 'etapa_txt': None,
        'ano': None, 'bimestre': None, 'eixo': None,
    }
    if not table or len(table) < 2:
        return meta

    # Linha 0 = header, Linha 1 = valores
    header = [(_clean_cell(c) or '').upper() for c in (table[0] or [])]
    values = [(_clean_cell(c) or '') for c in (table[1] or [])]

    for i, h in enumerate(header):
        if i >= len(values):
            break
        v = values[i]
        if not v:
            continue
        if 'EIXO' in h:
            meta['eixo'] = v
        elif 'COMPONENTE' in h:
            meta['componente_nome'] = v
        elif 'ETAPA' in h:
            meta['etapa_txt'] = v
        elif 'ANO' in h and 'BIMESTRE' not in h:
            meta['ano'] = _parse_ano(v)
        elif 'BIMESTRE' in h:
            meta['bimestre'] = _parse_bimestre(v)

    # Algumas tabelas colocam o eixo na célula [1][0] (merged); tenta cobrir.
    if not meta['eixo'] and values and values[0]:
        meta['eixo'] = values[0]

    return meta


def _find_habilidades_column(table: list) -> Optional[int]:
    """Procura o índice da coluna 'HABILIDADES' nos cabeçalhos intermediários."""
    # Olha até as 5 primeiras linhas
    for row in table[:5]:
        for i, cell in enumerate(row or []):
            if cell and 'HABILIDADE' in _clean_cell(cell).upper():
                return i
    return None


def _componente_codigo_from_nome(nome: str) -> Optional[str]:
    if not nome:
        return None
    nome_up = nome.upper()
    lookup = {
        'LÍNGUA PORTUGUESA': 'LP',
        'LINGUA PORTUGUESA': 'LP',
        'MATEMÁTICA': 'MA', 'MATEMATICA': 'MA',
        'CIÊNCIAS': 'CI', 'CIENCIAS': 'CI', 'CIÊNCIAS DA NATUREZA': 'CI',
        'GEOGRAFIA': 'GE',
        'HISTÓRIA': 'HI', 'HISTORIA': 'HI',
        'ARTE': 'AR', 'ARTES': 'AR',
        'EDUCAÇÃO FÍSICA': 'EF', 'EDUCACAO FISICA': 'EF',
        'LÍNGUA INGLESA': 'LI', 'LINGUA INGLESA': 'LI',
        'ENSINO RELIGIOSO': 'ER',
        'COMPUTAÇÃO': 'CO', 'COMPUTACAO': 'CO',
        'ESTUDOS AMAZÔNICOS': 'EA', 'ESTUDOS AMAZONICOS': 'EA',
    }
    for k, v in lookup.items():
        if k in nome_up:
            return v
    return None


def _extract_codes_from_text(text: str) -> List[Tuple[str, int, int]]:
    """Retorna [(codigo, start, end), ...] dos códigos BNCC encontrados no texto."""
    out = []
    for m in BNCC_CODE_RE.finditer(text or ''):
        prefix = m.group(1)
        ano_str = m.group(2)
        comp = m.group(3)
        seq = m.group(4)
        out.append((f"{prefix}{ano_str}{comp}{seq}", m.start(), m.end()))
    return out


def extract_skills_from_pdf(
    pdf_path: str,
    only_components: Optional[List[str]] = None,
    fonte: str = 'DCM_FA',
) -> List[dict]:
    """Versão V2 — extração estruturada por tabela."""
    import pdfplumber

    only = set(only_components) if only_components else None
    candidates: List[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables()
            except Exception:
                continue
            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 3:
                    continue

                meta = _parse_metadata(table)
                hab_col = _find_habilidades_column(table)
                if hab_col is None:
                    continue

                componente_nome = meta.get('componente_nome') or ''
                comp_codigo = _componente_codigo_from_nome(componente_nome)
                ano_fallback = meta.get('ano')
                bimestre_fallback = meta.get('bimestre')
                etapa_txt = meta.get('etapa_txt')

                # Linhas de conteúdo: depois dos 2-3 cabeçalhos
                for row in table[3:]:
                    if not row or hab_col >= len(row):
                        continue
                    cell = _clean_cell(row[hab_col] or '')
                    if not cell:
                        continue

                    codes = _extract_codes_from_text(cell)
                    if not codes:
                        continue

                    # Uma célula pode ter múltiplos códigos. Cada código
                    # "pega" o texto entre ele e o próximo código (ou fim).
                    for i, (codigo, start, end) in enumerate(codes):
                        prefix = codigo[:2]
                        comp_from_code = codigo[4:6]

                        # Filtro por componente
                        if only and comp_from_code not in only:
                            continue

                        # Descrição: texto depois do código até o próximo (ou fim)
                        next_start = codes[i + 1][1] if i + 1 < len(codes) else len(cell)
                        desc = cell[end:next_start].strip()
                        # Remove parênteses vazios e separadores iniciais
                        desc = re.sub(r'^[\s\-:.)\]]+', '', desc)
                        desc = re.sub(r'\s+', ' ', desc).strip()
                        # Remove parêntese de abertura órfão no final (sobra comum)
                        desc = re.sub(r'\s*\(\s*$', '', desc)
                        if len(desc) < 10:
                            continue

                        ano_str = codigo[2:4]
                        ano_int = int(ano_str) if ano_str.isdigit() else None
                        ano = ano_int if (ano_int is not None and 1 <= ano_int <= 9) else None
                        # Se ano vem de faixa (ex.: EF15), usa meta ou None
                        if ano is None and ano_fallback:
                            ano = ano_fallback

                        ano_range = ano_str if ano is None or (ano_int and ano_int > 9) else None

                        etapa = _classify_etapa(prefix, ano, etapa_txt or '')
                        componente_nome_final = componente_nome or COMPONENT_MAP.get(
                            comp_from_code, (comp_from_code, etapa)
                        )[0]

                        candidates.append({
                            'codigo': codigo,
                            'descricao': desc[:600],
                            'ano': ano,
                            'ano_range': ano_range,
                            'bimestre': bimestre_fallback,
                            'componente_codigo': comp_codigo or comp_from_code,
                            'componente_nome': componente_nome_final,
                            'eixo_estruturante': meta.get('eixo'),
                            'etapa': etapa,
                            'page': page_num,
                            'fonte': fonte,
                        })

    # Dedup por código: mantém o registro com descrição mais longa.
    # Se o mesmo código aparece em múltiplos bimestres, unimos — fica no mais recente
    # e preservamos os demais metadados no primeiro.
    by_code: dict = {}
    for c in candidates:
        prev = by_code.get(c['codigo'])
        if not prev or len(c['descricao']) > len(prev['descricao']):
            by_code[c['codigo']] = c

    items = list(by_code.values())
    items.sort(key=lambda x: (
        x.get('componente_codigo') or 'ZZ',
        x.get('ano') or 99,
        x.get('bimestre') or 9,
        x.get('codigo'),
    ))
    return items
