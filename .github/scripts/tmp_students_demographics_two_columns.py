#!/usr/bin/env python3
from pathlib import Path

path = Path('frontend/src/pages/StudentsComplete.js')
text = path.read_text(encoding='utf-8')

old_open = '''                  {/* COR / RAÇA */}\n                  <div data-testid="race-counts">\n'''
new_open = '''                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">\n                    {/* COR / RAÇA */}\n                    <div data-testid="race-counts">\n'''

if text.count(old_open) != 1:
    raise SystemExit(f'Abertura esperada 1 vez; encontrada {text.count(old_open)}')
text = text.replace(old_open, new_open, 1)

old_close = '''                  </div>\n\n                  {/* ENSINO FUNDAMENTAL */}\n'''
new_close = '''                  </div>\n                  </div>\n\n                  {/* ENSINO FUNDAMENTAL */}\n'''

# Esta âncora deve corresponder ao fechamento do bloco Comunidades Tradicionais.
# Há outras ocorrências de </div>, por isso validamos a posição após o marcador.
marker = '{/* COMUNIDADES TRADICIONAIS */}'
marker_pos = text.find(marker)
if marker_pos == -1:
    raise SystemExit('Marcador de Comunidades Tradicionais não encontrado')
close_pos = text.find(old_close, marker_pos)
if close_pos == -1:
    raise SystemExit('Fechamento esperado após Comunidades Tradicionais não encontrado')
text = text[:close_pos] + new_close + text[close_pos + len(old_close):]

path.write_text(text, encoding='utf-8')
print('Layout demográfico em duas colunas aplicado com sucesso.')
