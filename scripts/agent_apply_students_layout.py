from pathlib import Path

path = Path("frontend/src/pages/StudentsComplete.js")
text = path.read_text(encoding="utf-8")

start_marker = "                  {/* EDUCAÇÃO INFANTIL */}"
end_marker = "                  {/* EJA E MODALIDADES/ATENDIMENTOS */}"

# Idempotência: se o novo agrupamento já existir, não altera novamente.
if 'data-testid="etapas-ensino-counts"' in text:
    raise SystemExit(0)

if text.count(start_marker) != 1:
    raise SystemExit(f"Expected exactly one start marker, found {text.count(start_marker)}")
if text.count(end_marker) != 1:
    raise SystemExit(f"Expected exactly one end marker, found {text.count(end_marker)}")

start = text.index(start_marker)
end = text.index(end_marker, start)

replacement = '''                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* EDUCAÇÃO INFANTIL */}
                    <div data-testid="series-infantil-counts">
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

                    {/* ETAPAS DE ENSINO */}
                    <div data-testid="etapas-ensino-counts">
                      <p className="text-[11px] font-semibold tracking-wider text-gray-400 uppercase mb-2">
                        Etapas de Ensino
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {/* Somas por agrupamento (totais destacados) */}
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

updated = text[:start] + replacement + text[end:]

required = [
    'data-testid="series-infantil-counts"',
    'data-testid="etapas-ensino-counts"',
    'data-testid="sum-educacao-infantil"',
    'data-testid="sum-anos-iniciais"',
    'data-testid="sum-anos-finais"',
    "Etapas de Ensino",
]
for token in required:
    if token not in updated:
        raise SystemExit(f"Missing expected token after patch: {token}")

path.write_text(updated, encoding="utf-8")
