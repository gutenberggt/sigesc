"""
Extrator de habilidades curriculares do DCM de Floresta do Araguaia.

ESTRATÉGIA V3 (May 2026): HÍBRIDA com score de confiança.

Pipeline:
  Fase A — Extração estruturada (confidence='high'):
      page.extract_tables() → identifica coluna HABILIDADES via header → extrai
      descrições limpas com ano/bimestre/eixo vindos dos metadados da tabela.
  Fase B — Varredura completa do texto do PDF para encontrar TODOS os códigos BNCC.
  Fase C — Fallback (confidence='low'):
      Para códigos existentes no PDF mas NÃO capturados em A, usa extract_text()
      + regex. Marca como suspeito=True para revisão obrigatória.
  Fase D — Heurísticas de suspeita em TODOS os itens (palavras de outras colunas,
      descrição curta demais, marcadores estranhos).

Resultado: cobertura completa + qualidade alta nos HIGH + revisão obrigatória nos LOW.
"""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

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

# Palavras/frases típicas das colunas VIZINHAS ("Objetos", "Propostas de Atividades")
# que, quando aparecem no meio de uma descrição de Habilidade, indicam vazamento.
SUSPICIOUS_PATTERNS = [
    r'\baula\s+(expositiva|dialogada|pr[aá]tica)',
    r'\broda\s+de\s+conversa',
    r'\bbrincar\s+de\b',
    r'\bsortear?\b',
    r'\bimpress[ãa]o\b',
    r'\btransposi[çc][ãa]o\s+do\s+g[êe]nero',
]
_SUSPICIOUS_RE = re.compile('|'.join(SUSPICIOUS_PATTERNS), re.IGNORECASE)


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
    if not text:
        return ''
    text = re.sub(r'-\s*\n\s*', '', text)
    text = re.sub(r'\s*\n\s*', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_num(s: str, lo: int, hi: int) -> Optional[int]:
    if not s:
        return None
    m = re.search(r'(\d+)', s)
    if not m:
        return None
    n = int(m.group(1))
    return n if lo <= n <= hi else None


def _parse_metadata(table: list) -> dict:
    meta: dict = {
        'componente_nome': None, 'etapa_txt': None,
        'ano': None, 'bimestre': None, 'eixo': None,
    }
    if not table or len(table) < 2:
        return meta
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
            meta['ano'] = _parse_num(v, 1, 9)
        elif 'BIMESTRE' in h:
            meta['bimestre'] = _parse_num(v, 1, 4)
    if not meta['eixo'] and values and values[0]:
        meta['eixo'] = values[0]
    return meta


def _find_column_by_keywords(table: list, keywords: List[str], max_header_rows: int = 5) -> Optional[int]:
    """Mapeia coluna por nome de cabeçalho — não por posição fixa."""
    for row in table[:max_header_rows]:
        for i, cell in enumerate(row or []):
            if not cell:
                continue
            text = _clean_cell(cell).upper()
            if any(kw.upper() in text for kw in keywords):
                return i
    return None


def _componente_codigo_from_nome(nome: str) -> Optional[str]:
    if not nome:
        return None
    nome_up = nome.upper()
    lookup = {
        'LÍNGUA PORTUGUESA': 'LP', 'LINGUA PORTUGUESA': 'LP',
        'MATEMÁTICA': 'MA', 'MATEMATICA': 'MA',
        'CIÊNCIAS': 'CI', 'CIENCIAS': 'CI',
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


def _find_codes(text: str) -> List[Tuple[str, int, int]]:
    out = []
    for m in BNCC_CODE_RE.finditer(text or ''):
        codigo = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
        out.append((codigo, m.start(), m.end()))
    return out


def _is_suspicious(item: dict) -> bool:
    desc = item.get('descricao', '') or ''
    if len(desc) < 30:
        return True
    if _SUSPICIOUS_RE.search(desc):
        return True
    if desc.count('☐') > 0 or desc.count('. .') > 0:
        return True
    return False


def _merge_multiline_cells(table: list, hab_col: int) -> list:
    """Junta linhas de continuação: células de HABILIDADES sem outras colunas
    preenchidas e sem código BNCC são concatenadas à linha anterior."""
    if not table:
        return table
    merged = []
    for row in table:
        if not row or hab_col >= len(row):
            merged.append(row)
            continue
        cell = _clean_cell(row[hab_col] or '')
        other_filled = any(
            _clean_cell(c or '') for i, c in enumerate(row) if i != hab_col
        )
        if cell and not other_filled and not BNCC_CODE_RE.search(cell) and merged:
            prev = merged[-1]
            if prev and hab_col < len(prev):
                prev_cell = _clean_cell(prev[hab_col] or '')
                prev[hab_col] = f"{prev_cell} {cell}".strip()
                continue
        merged.append(list(row))
    return merged


def _extract_via_tables(pdf_path: str, only: Optional[Set[str]], fonte: str) -> List[dict]:
    """Fase A — extração estruturada (confidence='high')."""
    import pdfplumber

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
                hab_col = _find_column_by_keywords(table, ['HABILIDADE', 'BNCC'])
                if hab_col is None:
                    continue
                table = _merge_multiline_cells(table, hab_col)
                componente_nome = meta.get('componente_nome') or ''
                comp_codigo_meta = _componente_codigo_from_nome(componente_nome)
                ano_fallback = meta.get('ano')
                bimestre_fallback = meta.get('bimestre')
                etapa_txt = meta.get('etapa_txt')
                for row in table[3:]:
                    if not row or hab_col >= len(row):
                        continue
                    cell = _clean_cell(row[hab_col] or '')
                    if not cell:
                        continue
                    codes = _find_codes(cell)
                    if not codes:
                        continue
                    for i, (codigo, start, end) in enumerate(codes):
                        comp_from_code = codigo[4:6]
                        if only and comp_from_code not in only:
                            continue
                        next_start = codes[i + 1][1] if i + 1 < len(codes) else len(cell)
                        desc = cell[end:next_start].strip()
                        desc = re.sub(r'^[\s\-:.)\]]+', '', desc)
                        desc = re.sub(r'\s+', ' ', desc).strip()
                        desc = re.sub(r'\s*\(\s*$', '', desc)
                        if len(desc) < 10:
                            continue
                        prefix = codigo[:2]
                        ano_str = codigo[2:4]
                        ano_int = int(ano_str) if ano_str.isdigit() else None
                        ano = ano_int if (ano_int is not None and 1 <= ano_int <= 9) else None
                        if ano is None and ano_fallback:
                            ano = ano_fallback
                        ano_range = ano_str if (ano_int and (ano_int < 1 or ano_int > 9)) else None
                        etapa = _classify_etapa(prefix, ano, etapa_txt or '')
                        candidates.append({
                            'codigo': codigo,
                            'descricao': desc[:600],
                            'ano': ano,
                            'ano_range': ano_range,
                            'bimestre': bimestre_fallback,
                            'componente_codigo': comp_codigo_meta or comp_from_code,
                            'componente_nome': componente_nome or COMPONENT_MAP.get(
                                comp_from_code, (comp_from_code, etapa)
                            )[0],
                            'eixo_estruturante': meta.get('eixo'),
                            'etapa': etapa,
                            'page': page_num,
                            'fonte': fonte,
                            'confidence': 'high',
                            'suspeito': False,
                        })
    return candidates


def _extract_via_regex_fallback(
    pdf_path: str,
    missing_codes: Set[str],
    fonte: str,
) -> List[dict]:
    """Fase C — fallback para códigos não capturados via tabela (confidence='low')."""
    import pdfplumber

    out: List[dict] = []
    found: Set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ''
            except Exception:
                continue
            if not text:
                continue
            matches = list(BNCC_CODE_RE.finditer(text))
            for i, m in enumerate(matches):
                codigo = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
                if codigo in found or codigo not in missing_codes:
                    continue
                found.add(codigo)
                prefix = m.group(1)
                ano_str = m.group(2)
                comp_from_code = m.group(3)
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 500, len(text))
                desc = text[start:end].strip()
                desc = re.sub(r'^[\s\-:.)\]]+', '', desc)
                desc = re.sub(r'-\s*\n\s*', '', desc)
                desc = re.sub(r'\s+', ' ', desc)
                desc = desc[:500].strip()
                if len(desc) < 10:
                    continue
                ano_int = int(ano_str) if ano_str.isdigit() else None
                ano = ano_int if (ano_int is not None and 1 <= ano_int <= 9) else None
                etapa = _classify_etapa(prefix, ano)
                out.append({
                    'codigo': codigo,
                    'descricao': desc,
                    'ano': ano,
                    'ano_range': ano_str if (ano_int and (ano_int < 1 or ano_int > 9)) else None,
                    'bimestre': None,
                    'componente_codigo': comp_from_code,
                    'componente_nome': COMPONENT_MAP.get(comp_from_code, (comp_from_code, etapa))[0],
                    'eixo_estruturante': None,
                    'etapa': etapa,
                    'page': page_num,
                    'fonte': fonte,
                    'confidence': 'low',
                    'suspeito': True,
                })
    return out


def _all_codes_in_pdf(pdf_path: str, only: Optional[Set[str]]) -> Set[str]:
    """Fase B — todos os códigos do PDF, para comparar com os capturados na Fase A."""
    import pdfplumber

    codes: Set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text() or ''
            except Exception:
                continue
            for m in BNCC_CODE_RE.finditer(text):
                codigo = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
                comp = m.group(3)
                if only and comp not in only:
                    continue
                codes.add(codigo)
    return codes


def extract_skills_from_pdf(
    pdf_path: str,
    only_components: Optional[List[str]] = None,
    fonte: str = 'DCM_FA',
) -> List[dict]:
    """Entrada principal — pipeline híbrido."""
    only = set(only_components) if only_components else None

    structured = _extract_via_tables(pdf_path, only, fonte)
    captured = {s['codigo'] for s in structured}
    all_codes = _all_codes_in_pdf(pdf_path, only)
    missing = all_codes - captured
    fallback = _extract_via_regex_fallback(pdf_path, missing, fonte) if missing else []

    # Dedup: HIGH sempre ganha; entre mesmos níveis, descrição mais longa vence.
    by_code: dict = {}
    for c in structured + fallback:
        prev = by_code.get(c['codigo'])
        if not prev:
            by_code[c['codigo']] = c
            continue
        if prev['confidence'] == 'low' and c['confidence'] == 'high':
            by_code[c['codigo']] = c
        elif prev['confidence'] == c['confidence'] and len(c['descricao']) > len(prev['descricao']):
            by_code[c['codigo']] = c

    items = list(by_code.values())
    for item in items:
        if not item.get('suspeito'):
            item['suspeito'] = _is_suspicious(item)

    items.sort(key=lambda x: (
        x.get('componente_codigo') or 'ZZ',
        x.get('ano') or 99,
        x.get('bimestre') or 9,
        x.get('codigo'),
    ))
    return items
