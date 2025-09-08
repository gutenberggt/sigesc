import { useState } from "react";

export default function TabelaNotasIniciais({
  alunos,
  notas,
  onNotaChange,
  componentesCurriculares,
}) {
  const [semestreSelecionado, setSemestreSelecionado] = useState("1");

  const camposPorSemestre = {
    1: ["av1_1", "av2_1", "rec_1"],
    2: ["av1_2", "av2_2", "rec_2"],
  };

  const formatarNota = (valor) => {
    if (typeof valor !== "number" || isNaN(valor) || valor === 0) return "";
    return valor.toFixed(1).replace(".", ",");
  };

  const calcularMedia = (n1, n2, rec) => {
    if (n1 === undefined || n2 === undefined || isNaN(n1) || isNaN(n2))
      return null;
    let notas = [n1, n2];
    if (rec !== undefined && !isNaN(rec)) {
      const menorIndex = notas[0] < notas[1] ? 0 : 1;
      notas[menorIndex] = rec;
    }
    const media = (notas[0] + notas[1]) / 2;
    return parseFloat(media.toFixed(1));
  };

  return (
    <div>
      {/* Abas de semestre */}
      <div className="flex gap-2 mb-4">
        <button
          className={`px-4 py-2 rounded ${semestreSelecionado === "1" ? "bg-blue-600 text-white" : "bg-gray-200"}`}
          onClick={() => setSemestreSelecionado("1")}
        >
          1º Semestre
        </button>
        <button
          className={`px-4 py-2 rounded ${semestreSelecionado === "2" ? "bg-blue-600 text-white" : "bg-gray-200"}`}
          onClick={() => setSemestreSelecionado("2")}
        >
          2º Semestre
        </button>
      </div>

      {/* Tabela com rolagem */}
      <div className="overflow-auto max-h-[70vh] border rounded-md shadow-sm">
        <table className="min-w-full border-collapse bg-white">
          <thead>
            <tr className="bg-gray-100 text-gray-700 text-xs uppercase">
              <th className="border p-2 sticky left-0 top-0 bg-gray-100 z-20 text-left min-w-[200px]">
                Aluno
              </th>
              {componentesCurriculares.map((comp) => (
                <>
                  {camposPorSemestre[semestreSelecionado].map((campo) => (
                    <th
                      key={`${comp.codigo}_${campo}`}
                      className="border p-2 text-center sticky top-0 bg-gray-100 z-10"
                    >
                      {String(comp.sigla || comp.codigo)}{" "}
                      {campo.includes("av1")
                        ? "1ª"
                        : campo.includes("av2")
                          ? "2ª"
                          : "REC"}
                    </th>
                  ))}
                  <th
                    key={`${comp.codigo}_media`}
                    className="border p-2 text-center font-semibold sticky top-0 bg-gray-100 z-10"
                  >
                    {String(comp.sigla || comp.codigo)} Média
                  </th>
                </>
              ))}
            </tr>
          </thead>
          <tbody>
            {alunos.map((aluno) => {
              const incompleto = componentesCurriculares.some((comp) =>
                camposPorSemestre[semestreSelecionado].some((campo) => {
                  const chave = `${comp.codigo}_${campo}`;
                  const valor = notas[aluno.pessoaId]?.[chave];
                  return valor === undefined || valor === null || valor === "";
                })
              );

              return (
                <tr
                  key={aluno.pessoaId}
                  className={incompleto ? "bg-yellow-50" : ""}
                >
                  <td className="border p-2 sticky left-0 bg-white z-10 text-left min-w-[200px]">
                    {String(aluno.nomeCompleto || aluno.nome || "—")}
                  </td>
                  {componentesCurriculares.map((comp) => {
                    const av1Key = `${comp.codigo}_${camposPorSemestre[semestreSelecionado][0]}`;
                    const av2Key = `${comp.codigo}_${camposPorSemestre[semestreSelecionado][1]}`;
                    const recKey = `${comp.codigo}_${camposPorSemestre[semestreSelecionado][2]}`;

                    const av1 = notas[aluno.pessoaId]?.[av1Key];
                    const av2 = notas[aluno.pessoaId]?.[av2Key];
                    const rec = notas[aluno.pessoaId]?.[recKey];
                    const media = calcularMedia(av1, av2, rec);

                    return (
                      <>
                        {[av1Key, av2Key, recKey].map((chave) => {
                          const valor = notas[aluno.pessoaId]?.[chave];
                          return (
                            <td key={chave} className="border p-2 text-center">
                              <input
                                type="text"
                                inputMode="decimal"
                                value={formatarNota(valor)}
                                onChange={(e) => {
                                  let texto = e.target.value.replace(",", ".");
                                  let num = parseFloat(texto);
                                  if (!isNaN(num)) {
                                    if (num > 10 && texto.length === 2) {
                                      num = parseFloat(
                                        `${texto[0]}.${texto[1]}`
                                      );
                                    }
                                    onNotaChange(aluno.pessoaId, chave, num);
                                  }
                                }}
                                onBlur={(e) => {
                                  let texto = e.target.value.replace(",", ".");
                                  let num = parseFloat(texto);
                                  if (!isNaN(num)) {
                                    const ajustado = parseFloat(num.toFixed(1));
                                    onNotaChange(
                                      aluno.pessoaId,
                                      chave,
                                      ajustado
                                    );
                                  }
                                }}
                                className={`w-16 p-1 border rounded text-center ${
                                  valor < 5 && valor !== undefined
                                    ? "bg-red-100 border-red-400"
                                    : ""
                                }`}
                                style={{
                                  appearance: "none",
                                  MozAppearance: "textfield",
                                }}
                              />
                            </td>
                          );
                        })}
                        <td
                          className={`border p-2 text-center font-semibold ${
                            media !== null && media < 5
                              ? "bg-yellow-100 text-red-700"
                              : ""
                          }`}
                        >
                          {media !== null ? formatarNota(media) : "—"}
                        </td>
                      </>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
