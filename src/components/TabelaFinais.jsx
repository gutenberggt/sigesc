import React from "react";

export default function TabelaFinais({ dados, onChange }) {
  const calcularTotais = (aluno) => {
    const campos = ["b1", "r1", "b2", "b3", "r2", "b4"];
    const notas = campos.map((c) => parseFloat(aluno[c]) || 0);
    const total = notas.reduce((acc, n) => acc + n, 0);
    const media = (total / campos.length).toFixed(1);
    return { total, media };
  };

  return (
    <table>
      <thead>
        <tr>
          <th>Aluno</th>
          <th>1º Bim</th>
          <th>Recup. 1</th>
          <th>2º Bim</th>
          <th>3º Bim</th>
          <th>Recup. 2</th>
          <th>4º Bim</th>
          <th>Total</th>
          <th>Média</th>
        </tr>
      </thead>
      <tbody>
        {dados.map((aluno) => {
          const { total, media } = calcularTotais(aluno);
          return (
            <tr key={aluno.id}>
              <td>{aluno.nome}</td>
              {["b1", "r1", "b2", "b3", "r2", "b4"].map((campo) => (
                <td key={campo}>
                  <input
                    type="number"
                    step="0.1"
                    value={aluno[campo] || ""}
                    onChange={(e) =>
                      onChange(aluno.id, campo, e.target.value, {
                        total,
                        media,
                      })
                    }
                  />
                </td>
              ))}
              <td>{total}</td>
              <td>{media}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
