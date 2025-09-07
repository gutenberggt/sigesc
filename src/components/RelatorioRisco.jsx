import { calcularTotais } from '../utils/calculoNotas';

export default function RelatorioRisco({ alunos, notas }) {
  const alunosEmRisco = alunos.filter(aluno => {
    const pessoaId = aluno.pessoaId || aluno.id;
    const row = notas[pessoaId] || {};
    const { media } = calcularTotais(row.b1, row.b2, row.r1, row.b3, row.b4, row.r2);

    const semNotas = Object.values(row).every(v => v === '' || v === undefined);
    if (semNotas) return false;

    return typeof media === 'number' && media < 5;
  });

  const alunosOrdenados = [...alunosEmRisco].sort(
    (a, b) => (a.numeroChamada || 0) - (b.numeroChamada || 0)
  );

  const percentual =
    alunos.length > 0
      ? ((alunosEmRisco.length / alunos.length) * 100).toFixed(1).replace('.', ',')
      : '0,0';

  return (
    <div className="mt-4">
      <h3 className="text-lg font-bold text-red-700 mb-2">
        Alunos em Risco (Média abaixo de 5,0)
      </h3>

      <ul className="list-disc pl-6 mb-6">
        {alunosOrdenados.map((aluno, index) => {
          const pessoaId = aluno.pessoaId || aluno.id;
          const row = notas[pessoaId] || {};
          const { media } = calcularTotais(row.b1, row.b2, row.r1, row.b3, row.b4, row.r2);

          const numero =
            aluno.numeroChamada && typeof aluno.numeroChamada === 'number'
              ? aluno.numeroChamada
              : index + 1;

          const nomeSeguro = String(aluno.nomeCompleto || aluno.nome || '—');
          const mediaFormatada =
            typeof media === 'number'
              ? media.toFixed(1).replace('.', ',')
              : '—';

          return (
            <li key={pessoaId} className="text-red-600">
              {numero} - {nomeSeguro} (Média: {mediaFormatada})
            </li>
          );
        })}
      </ul>

      <div className="w-full bg-gray-200 rounded h-6 overflow-hidden">
        <div
          className="bg-red-500 h-full text-white text-xs flex items-center justify-center"
          style={{ width: `${percentual}%` }}
        >
          {percentual}% em risco
        </div>
      </div>
    </div>
  );
}
