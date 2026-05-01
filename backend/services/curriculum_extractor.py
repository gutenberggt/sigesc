"""
Extrator de habilidades curriculares de PDFs do DCM (Documento Curricular
Municipal) e da BNCC.

Estratégia simples e robusta:
  1. Lê o PDF página a página com pdfplumber (extract_text).
  2. Identifica códigos BNCC via regex (`EF03LP02`, `EI02EO01`, etc.).
  3. Para cada código, captura o texto que segue até o próximo código
     ou fim de página como descrição candidata.
  4. Deriva ano (dígitos 3-4 do código) e componente (caracteres 5-6).
  5. Deduplica por código mantendo a descrição mais completa.

Funciona com a maioria dos DCMs municipais que seguem o padrão BNCC.
Para casos onde a descrição precisa ser ajustada, o usuário revisa e edita
no UI antes do commit.
"""
from __future__ import annotations

import re
from typing import List, Optional

# EF (Ensino Fundamental) ou EI (Ed. Infantil) ou EM (Médio) seguido de 2
# dígitos (ano), 2 letras maiúsculas (componente) e 2 dígitos (sequencial),
# opcionalmente uma letra adicional para grupos como EF06LP10A.
BNCC_CODE_RE = re.compile(r'\b(E[FIM])(\d{2})([A-Z]{2})(\d{2}[A-Z]?)\b')


# Mapeamento código_componente → (nome_legivel, etapa_padrao)
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
    # Educação Infantil (códigos EI)
    'EO': ('O eu, o outro e o nós', 'infantil'),
    'CG': ('Corpo, gestos e movimentos', 'infantil'),
    'TS': ('Traços, sons, cores e formas', 'infantil'),
    'EF': ('Escuta, fala, pensamento e imaginação', 'infantil'),
    'ET': ('Espaços, tempos, quantidades, relações e transformações', 'infantil'),
}


def _classify_etapa(prefix: str, ano: int) -> str:
    if prefix == 'EI':
        return 'infantil'
    if prefix == 'EM':
        return 'medio'
    if 1 <= ano <= 5:
        return 'anos_iniciais'
    if 6 <= ano <= 9:
        return 'anos_finais'
    return 'anos_iniciais'


def _clean_description(text: str, max_len: int = 600) -> str:
    """Limpa descrição: remove separadores iniciais, normaliza espaços, trunca."""
    if not text:
        return ''
    # Remove separadores iniciais comuns
    text = re.sub(r'^[\s\-:.)\]]+', '', text)
    # Normaliza whitespace e quebra de linha hifenada
    text = re.sub(r'-\s*\n\s*', '', text)
    text = re.sub(r'\s+', ' ', text)
    # Tenta cortar no fim de uma frase (ponto final) próximo ao limite
    text = text.strip()
    if len(text) <= max_len:
        return text
    # Tenta cortar no último ponto antes do limite
    cut = text.rfind('.', 0, max_len)
    if cut > max_len // 2:
        return text[:cut + 1].strip()
    return text[:max_len].strip()


def extract_skills_from_pdf(
    pdf_path: str,
    only_components: Optional[List[str]] = None,
    fonte: str = 'DCM_FA',
) -> List[dict]:
    """
    Extrai habilidades de um PDF curricular.

    Args:
        pdf_path: caminho local do arquivo PDF.
        only_components: lista de prefixos de componente (ex.: ['LP'], ['MA','LP']).
            Se None, extrai todos.
        fonte: rótulo de fonte (DCM_FA, BNCC, MUNICIPAL).

    Returns:
        Lista de candidatos de habilidade, deduplicada por código.
    """
    import pdfplumber

    only = set(only_components) if only_components else None
    candidates: List[dict] = []

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
                prefix = m.group(1)        # 'EF', 'EI', 'EM'
                ano_str = m.group(2)       # '01'..'09'
                comp = m.group(3)          # 'LP', 'MA'...
                seq = m.group(4)           # '02', '02A'
                codigo = f"{prefix}{ano_str}{comp}{seq}"

                if only and comp not in only:
                    continue

                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 800, len(text))
                desc_raw = text[start:end]
                descricao = _clean_description(desc_raw)

                if len(descricao) < 15:
                    # Provavelmente o código apareceu em índice/cabeçalho sem descrição
                    continue

                ano_int = int(ano_str) if ano_str.isdigit() else None
                # BNCC usa códigos de FAIXA: EF15 (1º-5º), EF35 (3º-5º), EF69 (6º-9º), EF89 (8º-9º).
                # Nesses casos, o "ano" não é um único valor — deixamos None e o
                # super_admin escolhe ao revisar.
                ano = ano_int if (ano_int is not None and 1 <= ano_int <= 9) else None
                etapa = _classify_etapa(prefix, ano or 1)
                componente_nome, _ = COMPONENT_MAP.get(comp, (comp, etapa))

                candidates.append({
                    'codigo': codigo,
                    'descricao': descricao,
                    'ano': ano,
                    'ano_range': ano_str if ano is None else None,  # ex.: "15", "89"
                    'bimestre': None,
                    'componente_codigo': comp,
                    'componente_nome': componente_nome,
                    'etapa': etapa,
                    'page': page_num,
                    'fonte': fonte,
                })

    # Dedup por código (mantém a descrição mais longa)
    by_code: dict = {}
    for c in candidates:
        prev = by_code.get(c['codigo'])
        if not prev or len(c['descricao']) > len(prev['descricao']):
            by_code[c['codigo']] = c

    # Ordena por componente → ano → código
    items = list(by_code.values())
    items.sort(key=lambda x: (
        x.get('componente_codigo') or 'ZZ',
        x.get('ano') or 99,
        x.get('codigo'),
    ))
    return items
