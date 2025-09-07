import { useState } from 'react';
import { calcularTotais } from '../utils/calculoNotas';

export default function TabelaNotas({ alunos, notas, onNotaChange }) {
  const [ordenarPor, setOrdenarPor] = useState('numeroChamada');
  const [filtroMinMedia, setFiltroMinMedia] = useState('');
  const [buscaNome, setBuscaNome] = useState('');
  const [inputValues, setInputValues] = useState({});

  const alunosProcessados = alunos.map(aluno => {
    const pessoaId = aluno.pessoaId || aluno.id;
    const row = notas[pessoaId] || {};
    const { total, media } = calcularTotais(row.b1, row.b2, row.r1, row.b3, row.b4, row.r2);
    return { ...aluno, pessoaId, row, total, media };
  });

  const alunosFiltrados = alunosProcessados
    .filter(a => {
      if (filtroMinMedia && a.media < Number(filtroMinMedia)) return false;
      if (buscaNome && !a.nomeCompleto?.toLowerCase().includes(buscaNome.toLowerCase())) return false;
      return true;
    })
    .sort((a, b) => {
      if (ordenarPor === 'media') return b.media - a.media;
      return (a.numeroChamada || 0) - (b.numeroChamada || 0);
    });

  const formatarNotaParaExibicao = (pessoaId, campo, valor) => {
    const chave = pessoaId + '_' + campo;
    if (inputValues[chave] !== undefined) return inputValues[chave];
    if (typeof valor !== 'number' || isNaN(valor) || valor === 0) return '';
    return valor.toFixed(1).replace('.', ',');
  };

  const formatarDecimal = valor => {
    if (typeof valor !== 'number' || isNaN(valor) || valor === 0) return '';
    return valor.toFixed(1).replace('.', ',');
  };

  return (
    <div>
      {/* Filtros */}
      <div className="flex gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium mb-1">Ordenar por</label>
          <select
            value={ordenarPor}
            onChange={e => setOrdenarPor(e.target.value)}
            className="border rounded px-2 py-1"
          >
            <option value="numeroChamada">Número de Chamada</option>
            <option value="media">Média</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Filtrar média mínima</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="10"
            value={filtroMinMedia}
            onChange={e => setFiltroMinMedia(e.target.value)}
            className="border rounded px-2 py-1 w-24"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Buscar por nome</label>
          <input
            type="text"
            value={buscaNome}
            onChange={e => setBuscaNome(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </div>
      </div>

      {/* Tabela */}
      <table className="min-w-full border-collapse bg-white">
        <thead>
          <tr className="bg-gray-100">
            <th className="border p-2">Nº</th>
            <th className="border p-2">Aluno</th>
            <th className="border p-2">1º Bim</th>
            <th className="border p-2">2º Bim</th>
            <th className="border p-2">Recup. 1</th>
            <th className="border p-2">3º Bim</th>
            <th className="border p-2">4º Bim</th>
            <th className="border p-2">Recup. 2</th>
            <th className="border p-2">Total</th>
            <th className="border p-2">Média</th>
          </tr>
        </thead>
        <tbody>
          {alunosFiltrados.map((aluno, index) => (
            <tr key={aluno.pessoaId}>
              <td className="border p-2 text-center">{index + 1}</td>
              <td className="border p-2">
                {String(aluno.nomeCompleto || aluno.nome || '—')}
              </td>
              {['b1', 'b2', 'r1', 'b3', 'b4', 'r2'].map(campo => {
                const chave = aluno.pessoaId + '_' + campo;
                return (
                  <td key={campo} className="border p-2 text-center">
                    <input
                      type="text"
                      inputMode="decimal"
                      value={formatarNotaParaExibicao(aluno.pessoaId, campo, aluno.row[campo])}
                      onChange={e => {
                        const texto = e.target.value;
                        setInputValues(prev => ({ ...prev, [chave]: texto }));
                      }}
                      onBlur={e => {
                        let texto = e.target.value.replace(',', '.');
                        let num = parseFloat(texto);

                        if (!isNaN(num)) {
                          let exibicao = '';
                          if (num > 10 && texto.length === 2) {
                            exibicao = `${texto[0]},${texto[1]}`;
                            num = parseFloat(exibicao.replace(',', '.'));
                          } else {
                            num = parseFloat(num.toFixed(1));
                            exibicao = num.toFixed(1).replace('.', ',');
                          }

                          onNotaChange(aluno.pessoaId, campo, num);
                          setInputValues(prev => ({ ...prev, [chave]: exibicao }));
                        } else {
                          setInputValues(prev => ({ ...prev, [chave]: '' }));
                        }
                      }}
                      className={`w-16 p-1 border rounded text-center ${
                        aluno.row[campo] < 5 && aluno.row[campo] !== undefined
                          ? 'bg-red-100 border-red-400'
                          : ''
                      }`}
                      style={{ appearance: 'none', MozAppearance: 'textfield' }}
                    />
                  </td>
                );
              })}
              <td className="border p-2 text-center font-semibold">
                {formatarDecimal(aluno.total)}
              </td>
              <td
                className={`border p-2 text-center font-semibold ${
                  aluno.media < 5 && aluno.media !== 0
                    ? 'bg-yellow-100 text-red-700'
                    : ''
                }`}
              >
                {formatarDecimal(aluno.media)}
                {aluno.media < 5 && aluno.media !== 0 && (
                  <span className="ml-2 text-sm text-red-600 font-medium">⚠️</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
