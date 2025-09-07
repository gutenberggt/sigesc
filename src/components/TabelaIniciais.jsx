import React from 'react';

export default function TabelaIniciais({ dados, onChange }) {
  const calcularMedia = (aluno) => {
    const notas = [aluno.b1, aluno.b2, aluno.b3, aluno.b4]
      .map(n => parseFloat(n) || 0);
    const soma = notas.reduce((acc, n) => acc + n, 0);
    return (soma / notas.length).toFixed(1);
  };

  return (
    <table>
      <thead>
        <tr>
          <th>Aluno</th>
          <th>1º Bim</th>
          <th>2º Bim</th>
          <th>3º Bim</th>
          <th>4º Bim</th>
          <th>Média</th>
        </tr>
      </thead>
      <tbody>
        {dados.map(aluno => {
          const media = calcularMedia(aluno);
          return (
            <tr key={aluno.id}>
              <td>{aluno.nome}</td>
              {['b1', 'b2', 'b3', 'b4'].map(campo => (
                <td key={campo}>
                  <input
                    type="number"
                    step="0.1"
                    value={aluno[campo] || ''}
                    onChange={e => onChange(aluno.id, campo, e.target.value, { media })}
                  />
                </td>
              ))}
              <td>{media}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
