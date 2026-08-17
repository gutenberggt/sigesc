#!/usr/bin/env python3
from pathlib import Path

path = Path('frontend/src/pages/StudentsComplete.js')
text = path.read_text(encoding='utf-8')

start_marker = '                  {/* EDUCAÇÃO INFANTIL */}'
end_marker = '                  {/* EJA E MODALIDADES/ATENDIMENTOS */}'
new_marker = '                  {/* EDUCAÇÃO INFANTIL E TOTAIS POR ETAPA */}'

if new_marker in text:
    print('Layout já aplicado; nenhuma alteração necessária.')
    raise SystemExit(0)

if text.count(start_marker) != 1:
    raise SystemExit(f'Marcador inicial esperado 1 vez; encontrado {text.count(start_marker)}')
if text.count(end_marker) != 1:
    raise SystemExit(f'Marcador final esperado 1 vez; encontrado {text.count(end_marker)}')

start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = '''                  {/* EDUCAÇÃO INFANTIL E TOTAIS POR ETAPA */}
                  <div data-testid="series-infantil-counts" className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <p className="text-[11px] font-semibold tracking-wider text-gray-400 uppercase mb-2">
                        Educação Infantil
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {['Berçário I','Berçário II','Maternal I','Maternal II','Pré I','Pré II'].map((label) => (
                          <span
                            key={label}
                            className="inline-flex items-center px-3 py-1.5 rounded-full bg-amber-50 text-amber-700 text-xs font-medium"
                          >
                            {label}: {seriesCounts[label.toUpperCase()] || 0}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div data-testid="totais-etapas-counts">
                      <p className="text-[11px] font-semibold tracking-wider text-gray-400 uppercase mb-2">
                        Totais por Etapa
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <span
                          data-testid="sum-educacao-infantil"
                          className="inline-flex items-center px-3 py-1.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 text-xs font-bold"
                          title="Soma de todas as séries da Educação Infantil"
                        >
                          Educação Infantil: {totalEducacaoInfantil}
                        </span>
                        <span
                          data-testid="sum-anos-iniciais"
                          className="inline-flex items-center px-3 py-1.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300 text-xs font-bold"
                          title="Soma do 1º ao 5º Ano (Anos Iniciais)"
                        >
                          Anos Iniciais: {totalAnosIniciais}
                        </span>
                        <span
                          data-testid="sum-anos-finais"
                          className="inline-flex items-center px-3 py-1.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300 text-xs font-bold"
                          title="Soma do 6º ao 9º Ano (Anos Finais)"
                        >
                          Anos Finais: {totalAnosFinais}
                        </span>
                      </div>
                    </div>
                  </div>

'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding='utf-8')
print('Layout Educação Infantil / Totais por Etapa aplicado.')
