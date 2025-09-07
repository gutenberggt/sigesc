import React from 'react';

export default function TabelaInfantil({ dados, onChange }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Aluno</th>
          <th>Desenvolvimento</th>
          <th>Observações</th>
        </tr>
      </thead>
      <tbody>
        {dados.map(aluno => (
          <tr key={aluno.id}>
            <td>{aluno.nome}</td>
            <td>
              <input
                type="text"
                value={aluno.desenvolvimento || ''}
                onChange={e => onChange(aluno.id, 'desenvolvimento', e.target.value)}
              />
            </td>
            <td>
              <input
                type="text"
                value={aluno.observacoes || ''}
                onChange={e => onChange(aluno.id, 'observacoes', e.target.value)}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
