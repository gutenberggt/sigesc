import React, { useEffect, useReducer, useState } from "react";
import { db } from "../firebase/config";
import {
  collection,
  getDocs,
  query,
  where,
  writeBatch,
  doc,
  getDoc,
} from "firebase/firestore";
import { useUser } from "../context/UserContext";

// Utilidades
const roundUp1 = (value) => {
  if (value === null || value === undefined || value === "") return "";
  const num = Number(value);
  if (Number.isNaN(num)) return "";
  return Math.ceil(num * 10) / 10;
};

const fmt1 = (value) => {
  if (value === "" || value === null || value === undefined) return "";
  const v = roundUp1(value);
  return v.toFixed(1).replace(".", ","); // vírgula no lugar do ponto
};

const aplicarRecuperacoes = (B1, B2, R1, B3, B4, R2) => {
  let eB1 = B1 ?? 0,
    eB2 = B2 ?? 0,
    eB3 = B3 ?? 0,
    eB4 = B4 ?? 0;
  const r1 = R1 ?? 0,
    r2 = R2 ?? 0;
  if (r1 > 0) {
    if (eB1 < eB2) {
      if (r1 > eB1) eB1 = r1;
    } else if (eB2 < eB1) {
      if (r1 > eB2) eB2 = r1;
    } else {
      if (r1 > eB2) eB2 = r1;
    }
  }
  if (r2 > 0) {
    if (eB3 < eB4) {
      if (r2 > eB3) eB3 = r2;
    } else if (eB4 < eB3) {
      if (r2 > eB4) eB4 = r2;
    } else {
      if (r2 > eB4) eB4 = r2;
    }
  }
  return [eB1, eB2, eB3, eB4];
};

const calcularTotais = (B1, B2, R1, B3, B4, R2) => {
  const [eB1, eB2, eB3, eB4] = aplicarRecuperacoes(
    Number(B1 || 0),
    Number(B2 || 0),
    Number(R1 || 0),
    Number(B3 || 0),
    Number(B4 || 0),
    Number(R2 || 0)
  );
  const total = eB1 * 2 + eB2 * 3 + eB3 * 2 + eB4 * 3;
  const media = total / 10;
  return { total: roundUp1(total), media: roundUp1(media) };
};

// Campo de nota
const NotaInput = ({ value, onChange, disabled }) => {
  const [display, setDisplay] = React.useState("");
  const formatDisplay = (num) => {
    const n = Number(num);
    if (Number.isNaN(n)) return "";
    return n.toFixed(1).replace(".", ",");
  };
  useEffect(() => {
    if (value === "" || value === null || value === undefined) {
      setDisplay("");
    } else {
      setDisplay(formatDisplay(value));
    }
  }, [value]);
  const handleChange = (e) => {
    const raw = e.target.value;
    const sanitized = raw.replace(/[^\d.,]/g, "");
    const normalized = sanitized.replace(",", ".");
    if (normalized === "") {
      setDisplay("");
      return;
    }
    const maybeNumber = Number(normalized);
    if (Number.isNaN(maybeNumber)) {
      setDisplay(sanitized);
      return;
    }
    if (maybeNumber > 10) return;
    setDisplay(sanitized);
  };
  const handleBlur = () => {
    if (display === "") {
      onChange("");
      return;
    }
    let n = Number(display.replace(",", "."));
    if (Number.isNaN(n)) {
      setDisplay("");
      onChange("");
      return;
    }
    if (n < 0) n = 0;
    if (n > 10) n = 10;
    const formatted = n.toFixed(1).replace(".", ",");
    setDisplay(formatted);
    onChange(Number(n.toFixed(1)));
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      value={display}
      onChange={handleChange}
      onBlur={handleBlur}
      className={`w-20 p-1 border rounded text-center ${disabled ? "bg-gray-100 text-gray-500" : ""}`}
      disabled={disabled}
    />
  );
};

function NotasPage() {
  const { userData } = useUser();
  const initialFilters = {
    selectedSchoolId: "",
    selectedTurmaId: "",
    selectedComponente: "",
    selectedYear: new Date().getFullYear(),
  };
  const [filters, setFilters] = useReducer(
    (s, a) => ({ ...s, ...a }),
    initialFilters
  );
  const [availableSchools, setAvailableSchools] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [alunosDaTurma, setAlunosDaTurma] = useState([]);
  const [notas, setNotas] = useState({});
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const funcao = userData?.funcao?.toLowerCase();
  const acessoPermitido = ["professor", "secretário", "administrador"].includes(
    funcao
  );
  const canEdit = acessoPermitido && !isSubmitting;

  const selectedTurmaObject = availableTurmas.find(
    (t) => t.id === filters.selectedTurmaId
  );
  const isAnosFinais =
    selectedTurmaObject &&
    selectedTurmaObject.nivelEnsino?.includes("ANOS FINAIS");
  const showComponenteFilter = isAnosFinais;

  // Escolas
  useEffect(() => {
    getDocs(collection(db, "schools")).then((snap) =>
      setAvailableSchools(
        snap.docs.map((docu) => ({ id: docu.id, ...docu.data() }))
      )
    );
  }, []);

  // Turmas
  useEffect(() => {
    if (!filters.selectedSchoolId) {
      setAvailableTurmas([]);
      setFilters({ selectedTurmaId: "", selectedComponente: "" });
      return;
    }
    getDocs(
      query(
        collection(db, "turmas"),
        where("schoolId", "==", filters.selectedSchoolId)
      )
    ).then((snap) => {
      setAvailableTurmas(
        snap.docs.map((docu) => ({ id: docu.id, ...docu.data() }))
      );
      setFilters({ selectedTurmaId: "", selectedComponente: "" });
    });
  }, [filters.selectedSchoolId]);

  // Componentes via horários
  useEffect(() => {
    const load = async () => {
      if (!filters.selectedTurmaId || !showComponenteFilter) {
        setAvailableComponentes([]);
        setFilters({ selectedComponente: "" });
        return;
      }
      const horarioSnap = await getDoc(
        doc(db, "horarios", filters.selectedTurmaId)
      );
      if (!horarioSnap.exists()) {
        setAvailableComponentes([]);
        setFilters({ selectedComponente: "" });
        return;
      }
      const horarioData = horarioSnap.data().horario;
      let comps = new Set();
      Object.values(horarioData || {}).forEach((aulas) => {
        if (Array.isArray(aulas))
          aulas.forEach((aula) => aula && comps.add(aula.split(" - ")[0]));
      });
      if (funcao === "professor" && userData?.alocacoes) {
        const compsProf = new Set();
        userData.alocacoes.forEach((aloc) => {
          aloc.funcoes?.forEach((f) => {
            if (f.turmaId === filters.selectedTurmaId) {
              (f.componentesCurriculares || []).forEach((c) =>
                compsProf.add(c)
              );
            }
          });
        });
        comps = new Set([...comps].filter((c) => compsProf.has(c)));
      }
      setAvailableComponentes([...comps].sort());
      setFilters({ selectedComponente: "" });
    };
    load();
  }, [filters.selectedTurmaId, showComponenteFilter, funcao, userData]);

  // Alunos + notas
  useEffect(() => {
    if (!filters.selectedTurmaId) {
      setAlunosDaTurma([]);
      setNotas({});
      return;
    }

    // 🔹 Se for anos finais e não tiver componente selecionado, limpa campos
    if (showComponenteFilter && !filters.selectedComponente) {
      const vazio = {};
      alunosDaTurma.forEach((a) => {
        vazio[a.pessoaId] = { b1: "", b2: "", r1: "", b3: "", b4: "", r2: "" };
      });
      setNotas(vazio);
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      setError("");
      try {
        // Matriculas da turma
        const matriculasSnap = await getDocs(
          query(
            collection(db, "matriculas"),
            where("turmaId", "==", filters.selectedTurmaId)
          )
        );
        const matriculasList = matriculasSnap.docs.map((docu) => ({
          id: docu.id,
          ...docu.data(),
        }));

        // Pessoas (em lotes de 10)
        const pessoaIds = matriculasList
          .map((m) => m.pessoaId)
          .filter((id) => typeof id === "string" && id.trim() !== "");
        let alunosDetalhes = [];
        for (let i = 0; i < pessoaIds.length; i += 10) {
          const chunk = pessoaIds.slice(i, i + 10);
          const pessoasSnap = await getDocs(
            query(collection(db, "pessoas"), where("__name__", "in", chunk))
          );
          alunosDetalhes = [
            ...alunosDetalhes,
            ...pessoasSnap.docs.map((docu) => ({
              id: docu.id,
              ...docu.data(),
            })),
          ];
        }

        // Merge matrícula + pessoa
        const alunosCompletos = matriculasList
          .map((m) => {
            const pessoa = alunosDetalhes.find((p) => p.id === m.pessoaId);
            return {
              ...m,
              nomeCompleto: pessoa?.nomeCompleto || pessoa?.nome || "Sem nome",
            };
          })
          .sort((a, b) => (a.numeroChamada || 0) - (b.numeroChamada || 0));

        setAlunosDaTurma(alunosCompletos);

        // Notas filtradas por turma, ano e componente (se houver)
        let notasQuery = query(
          collection(db, "notas"),
          where("turmaId", "==", filters.selectedTurmaId),
          where("ano", "==", Number(filters.selectedYear))
        );
        if (filters.selectedComponente) {
          notasQuery = query(
            collection(db, "notas"),
            where("turmaId", "==", filters.selectedTurmaId),
            where("ano", "==", Number(filters.selectedYear)),
            where("componenteId", "==", filters.selectedComponente)
          );
        }
        const notasSnap = await getDocs(notasQuery);
        const notasMap = {};
        notasSnap.docs.forEach((docu) => {
          const d = docu.data();
          const chave = d.pessoaId || d.alunoId;
          if (chave) notasMap[chave] = d;
        });

        if (Object.keys(notasMap).length === 0) {
          const vazio = {};
          alunosCompletos.forEach((a) => {
            vazio[a.pessoaId] = {
              b1: "",
              b2: "",
              r1: "",
              b3: "",
              b4: "",
              r2: "",
            };
          });
          setNotas(vazio);
        } else {
          setNotas(notasMap);
        }
      } catch (err) {
        console.error(err);
        setError("Erro ao carregar alunos ou notas");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [
    filters.selectedTurmaId,
    filters.selectedYear,
    filters.selectedComponente,
  ]);

  if (!acessoPermitido) {
    return (
      <div className="p-6 text-red-600 font-semibold">
        Acesso negado. Esta página é restrita a professores, secretários e
        administradores.
      </div>
    );
  }

  const handleNotaChange = (pessoaId, campo, valor) => {
    setNotas((prev) => ({
      ...prev,
      [pessoaId]: {
        ...prev[pessoaId],
        [campo]: valor,
      },
    }));
  };

  const handleSaveNotas = async () => {
    if (!filters.selectedTurmaId) return;
    setIsSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const batch = writeBatch(db);
      for (const pessoaId of Object.keys(notas)) {
        const ref = doc(
          db,
          "notas",
          `${filters.selectedTurmaId}_${pessoaId}_${filters.selectedComponente || "geral"}_${filters.selectedYear}`
        );
        batch.set(
          ref,
          {
            turmaId: filters.selectedTurmaId,
            componenteId: filters.selectedComponente || "",
            ano: Number(filters.selectedYear),
            pessoaId,
            alunoId: pessoaId,
            ...notas[pessoaId],
            updatedAt: new Date(),
          },
          { merge: true }
        );
      }
      await batch.commit();
      setSuccess("Notas salvas com sucesso!");
    } catch (err) {
      console.error(err);
      setError("Erro ao salvar notas.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGenerateReport = () => window.print();

  const anos = [
    new Date().getFullYear(),
    new Date().getFullYear() - 1,
    new Date().getFullYear() - 2,
  ];

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">
          Lançamento de Notas
        </h2>

        {/* Filtros */}
        <div className="grid grid-cols-1 md:grid-cols-10 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <div className="md:col-span-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Escola
            </label>
            <select
              value={filters.selectedSchoolId}
              onChange={(e) =>
                setFilters({
                  selectedSchoolId: e.target.value,
                  selectedTurmaId: "",
                  selectedComponente: "",
                })
              }
              className="p-2 border rounded-md w-full"
            >
              <option value="">Selecione a Escola</option>
              {availableSchools.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nomeEscola}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Turma
            </label>
            <select
              value={filters.selectedTurmaId}
              onChange={(e) =>
                setFilters({
                  selectedTurmaId: e.target.value,
                  selectedComponente: "",
                })
              }
              className="p-2 border rounded-md w-full"
              disabled={!filters.selectedSchoolId}
            >
              <option value="">Selecione a Turma</option>
              {availableTurmas.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nomeTurma}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Ano
            </label>
            <select
              value={filters.selectedYear}
              onChange={(e) =>
                setFilters({ selectedYear: Number(e.target.value) })
              }
              className="p-2 border rounded-md w-full"
            >
              {anos.map((ano) => (
                <option key={ano} value={ano}>
                  {ano}
                </option>
              ))}
            </select>
          </div>

          {showComponenteFilter && (
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Componente
              </label>
              <select
                value={filters.selectedComponente}
                onChange={(e) =>
                  setFilters({ selectedComponente: e.target.value })
                }
                className="p-2 border rounded-md w-full"
              >
                <option value="">Selecione o Componente</option>
                {availableComponentes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && (
          <p className="text-green-500 text-center mb-4">{success}</p>
        )}
        {loading && (
          <p className="text-center text-gray-500">Carregando dados...</p>
        )}

        {!loading && alunosDaTurma.length > 0 && (
          <div className="overflow-x-auto max-h-[70vh]">
            <table className="min-w-full bg-white border-collapse">
              <thead>
                <tr className="bg-gray-200 text-gray-600 uppercase text-xs">
                  <th className="py-2 px-2 border">Nº</th>
                  <th className="py-2 px-2 border">Aluno</th>
                  <th className="py-2 px-2 border">1º Bim</th>
                  <th className="py-2 px-2 border">2º Bim</th>
                  <th className="py-2 px-2 border">Recup. 1</th>
                  <th className="py-2 px-2 border">3º Bim</th>
                  <th className="py-2 px-2 border">4º Bim</th>
                  <th className="py-2 px-2 border">Recup. 2</th>
                  <th className="py-2 px-2 border">Total</th>
                  <th className="py-2 px-2 border">Média</th>
                </tr>
              </thead>
              <tbody>
                {alunosDaTurma.map((aluno, index) => {
                  const row = notas[aluno.pessoaId] || {
                    b1: "",
                    b2: "",
                    r1: "",
                    b3: "",
                    b4: "",
                    r2: "",
                  };
                  const { total, media } = calcularTotais(
                    row.b1 || 0,
                    row.b2 || 0,
                    row.r1 || 0,
                    row.b3 || 0,
                    row.b4 || 0,
                    row.r2 || 0
                  );
                  return (
                    <tr key={aluno.id}>
                      <td className="border text-center">{index + 1}</td>
                      <td className="border">{aluno.nomeCompleto}</td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.b1}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "b1", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.b2}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "b2", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.r1}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "r1", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.b3}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "b3", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.b4}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "b4", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center">
                        <NotaInput
                          value={row.r2}
                          onChange={(v) =>
                            handleNotaChange(aluno.pessoaId, "r2", v)
                          }
                          disabled={!canEdit}
                        />
                      </td>
                      <td className="border text-center font-semibold">
                        {fmt1(total)}
                      </td>
                      <td className="border text-center font-semibold">
                        {fmt1(media)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {alunosDaTurma.length > 0 && (
          <div className="flex justify-end items-center mt-6 gap-4">
            <button
              onClick={handleGenerateReport}
              className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition"
            >
              Gerar Relatório
            </button>
            <button
              onClick={handleSaveNotas}
              disabled={!canEdit}
              className={`bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition ${
                !canEdit ? "opacity-50 cursor-not-allowed" : ""
              }`}
            >
              {isSubmitting ? "Salvando..." : "Salvar Notas"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default NotasPage;
