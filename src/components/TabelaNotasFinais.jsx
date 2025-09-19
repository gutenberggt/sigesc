import React, { useState } from "react";

export default function TabelaNotasFinais({ notas }) {
  const [ordenarPor, setOrdenarPor] = useState("nome");

  const notasOrdenadas = [...notas].sort((a, b) => {
    if (ordenarPor === "nota") {
      return b.nota - a.nota;
    }
    return a.nome.localeCompare(b.nome);
  });

  return (
    <div>
      <div className="mb-4">
        <label htmlFor="ordenarPor" className="block text-sm font-medium mb-1">
          Ordenar por
        </label>
        <select
          id="ordenarPor"
          value={ordenarPor}
          onChange={(e) => setOrdenarPor(e.target.value)}
          className="border rounded px-2 py-1"
        >
          <option value="nome">Nome</option>
          <option value="nota">Nota</option>
        </select>
      </div>

      <table className="min-w-full border border-gray-300">
        <thead>
          <tr className="bg-gray-100">
            <th className="border px-4 py-2">Nome</th>
            <th className="border px-4 py-2">Nota</th>
          </tr>
        </thead>
        <tbody>
          {notasOrdenadas.map((aluno, idx) => (
            <tr key={idx}>
              <td className="border px-4 py-2">{aluno.nome}</td>
              <td className="border px-4 py-2">{aluno.nota}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
