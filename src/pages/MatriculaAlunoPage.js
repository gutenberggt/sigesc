//📌 Parte 1 — Imports, estados e useEffect
import React, { useEffect, useState } from "react";
import {
  collection,
  doc,
  getDocs,
  setDoc,
  updateDoc,
  query,
  where,
} from "firebase/firestore";
import { db } from "../firebase/config";
import { toast } from "react-toastify";
import Loading from "../components/ui/loading";
import PageHeader from "../components/ui/pageHeader";

const MatriculaAlunoPage = () => {
  const [alunos, setAlunos] = useState([]);
  const [turmas, setTurmas] = useState([]);
  const [selectedAluno, setSelectedAluno] = useState(null);
  const [selectedTurma, setSelectedTurma] = useState(null);
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear());
  const [matriculas, setMatriculas] = useState([]);
  const [loading, setLoading] = useState(false); // corrigido, estava undefined

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);

        const alunosSnapshot = await getDocs(collection(db, "alunos"));
        const turmasSnapshot = await getDocs(collection(db, "turmas"));
        const matriculasSnapshot = await getDocs(collection(db, "matriculas"));

        setAlunos(alunosSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));
        setTurmas(turmasSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));
        setMatriculas(
          matriculasSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );
      } catch (error) {
        console.error("Erro ao carregar dados:", error);
        toast.error("Erro ao carregar dados iniciais.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

//📌 Parte 2 — Funções auxiliares
  const handleSaveMatricula = async () => {
    if (!selectedAluno || !selectedTurma) {
      toast.warning("Selecione um aluno e uma turma.");
      return;
    }

    try {
      setLoading(true);

      const matriculaRef = doc(collection(db, "matriculas"));
      await setDoc(matriculaRef, {
        alunoId: selectedAluno.id,
        turmaId: selectedTurma.id,
        anoLetivo,
        criadoEm: new Date(),
      });

      setMatriculas([
        ...matriculas,
        {
          id: matriculaRef.id,
          alunoId: selectedAluno.id,
          turmaId: selectedTurma.id,
          anoLetivo,
        },
      ]);

      toast.success("Matrícula realizada com sucesso!");
      setSelectedAluno(null);
      setSelectedTurma(null);
    } catch (error) {
      console.error("Erro ao salvar matrícula:", error);
      toast.error("Erro ao salvar matrícula.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateMatricula = async (matriculaId, updates) => {
    try {
      setLoading(true);

      const matriculaRef = doc(db, "matriculas", matriculaId);
      await updateDoc(matriculaRef, updates);

      setMatriculas(
        matriculas.map((mat) =>
          mat.id === matriculaId ? { ...mat, ...updates } : mat
        )
      );

      toast.success("Matrícula atualizada com sucesso!");
    } catch (error) {
      console.error("Erro ao atualizar matrícula:", error);
      toast.error("Erro ao atualizar matrícula.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMatricula = async (matriculaId) => {
    try {
      setLoading(true);

      const matriculaRef = doc(db, "matriculas", matriculaId);
      await updateDoc(matriculaRef, { deletado: true }); // soft delete

      setMatriculas(matriculas.filter((mat) => mat.id !== matriculaId));

      toast.success("Matrícula excluída com sucesso!");
    } catch (error) {
      console.error("Erro ao excluir matrícula:", error);
      toast.error("Erro ao excluir matrícula.");
    } finally {
      setLoading(false);
    }
  };

//📌 Parte 3 — Formulário
  if (loading) {
    return <Loading />;
  }

  return (
    <div className="p-6">
      <PageHeader title="Matrícula de Alunos" />

      <div className="bg-white shadow-md rounded p-6 mb-6">
        <h2 className="text-lg font-bold mb-4">Nova Matrícula</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Select Aluno */}
          <div>
            <label
              htmlFor="aluno"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Aluno
            </label>
            <select
              id="aluno"
              value={selectedAluno ? selectedAluno.id : ""}
              onChange={(e) =>
                setSelectedAluno(alunos.find((a) => a.id === e.target.value))
              }
              className="border rounded px-2 py-1 w-full"
            >
              <option value="">Selecione um aluno</option>
              {alunos.map((aluno) => (
                <option key={aluno.id} value={aluno.id}>
                  {aluno.nome}
                </option>
              ))}
            </select>
          </div>

          {/* Select Turma */}
          <div>
            <label
              htmlFor="turma"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Turma
            </label>
            <select
              id="turma"
              value={selectedTurma ? selectedTurma.id : ""}
              onChange={(e) =>
                setSelectedTurma(turmas.find((t) => t.id === e.target.value))
              }
              className="border rounded px-2 py-1 w-full"
            >
              <option value="">Selecione uma turma</option>
              {turmas.map((turma) => (
                <option key={turma.id} value={turma.id}>
                  {turma.nome}
                </option>
              ))}
            </select>
          </div>

          {/* Ano Letivo */}
          <div>
            <label
              htmlFor="anoLetivo"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Ano Letivo
            </label>
            <input
              type="number"
              id="anoLetivo"
              value={anoLetivo}
              onChange={(e) => setAnoLetivo(e.target.value)}
              className="border rounded px-2 py-1 w-full"
            />
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={handleSaveMatricula}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            Salvar Matrícula
          </button>
        </div>
      </div>

//📌 Parte 4 — Lista de matrículas
      {/* Lista de Matrículas */}
      <div className="bg-white shadow-md rounded p-6">
        <h2 className="text-lg font-bold mb-4">Matrículas Cadastradas</h2>

        {matriculas.length === 0 ? (
          <p className="text-gray-600">Nenhuma matrícula encontrada.</p>
        ) : (
          <table className="w-full border-collapse border border-gray-200">
            <thead>
              <tr className="bg-gray-100">
                <th className="border border-gray-200 px-4 py-2">Aluno</th>
                <th className="border border-gray-200 px-4 py-2">Turma</th>
                <th className="border border-gray-200 px-4 py-2">Ano Letivo</th>
                <th className="border border-gray-200 px-4 py-2">Ações</th>
              </tr>
            </thead>
            <tbody>
              {matriculas.map((matricula) => {
                const aluno = alunos.find((a) => a.id === matricula.alunoId);
                const turma = turmas.find((t) => t.id === matricula.turmaId);

                return (
                  <tr key={matricula.id}>
                    <td className="border px-4 py-2">{aluno?.nome || "—"}</td>
                    <td className="border px-4 py-2">{turma?.nome || "—"}</td>
                    <td className="border px-4 py-2">{matricula.anoLetivo}</td>
                    <td className="border px-4 py-2 flex gap-2">
                      <button
                        onClick={() =>
                          handleUpdateMatricula(matricula.id, {
                            anoLetivo: Number(anoLetivo),
                          })
                        }
                        className="bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDeleteMatricula(matricula.id)}
                        className="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                      >
                        Excluir
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

//📌 Parte 5 — Fechamento do componente
  return (
    <div className="p-6">
      {/* Cabeçalho */}
      <h1 className="text-2xl font-bold mb-6">Gestão de Matrículas</h1>

      {/* Formulário de Matrícula */}
      <div className="bg-white shadow-md rounded p-6 mb-6">
        <h2 className="text-lg font-bold mb-4">Nova Matrícula</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Seleção de Aluno */}
          <div>
            <label htmlFor="alunoId" className="block font-medium mb-1">
              Aluno
            </label>
            <select
              id="alunoId"
              value={alunoId}
              onChange={(e) => setAlunoId(e.target.value)}
              className="border rounded px-3 py-2 w-full"
              required
            >
              <option value="">Selecione um aluno</option>
              {alunos.map((aluno) => (
                <option key={aluno.id} value={aluno.id}>
                  {aluno.nome}
                </option>
              ))}
            </select>
          </div>

          {/* Seleção de Turma */}
          <div>
            <label htmlFor="turmaId" className="block font-medium mb-1">
              Turma
            </label>
            <select
              id="turmaId"
              value={turmaId}
              onChange={(e) => setTurmaId(e.target.value)}
              className="border rounded px-3 py-2 w-full"
              required
            >
              <option value="">Selecione uma turma</option>
              {turmas.map((turma) => (
                <option key={turma.id} value={turma.id}>
                  {turma.nome}
                </option>
              ))}
            </select>
          </div>

          {/* Ano Letivo */}
          <div>
            <label htmlFor="anoLetivo" className="block font-medium mb-1">
              Ano Letivo
            </label>
            <input
              type="number"
              id="anoLetivo"
              value={anoLetivo}
              onChange={(e) => setAnoLetivo(e.target.value)}
              className="border rounded px-3 py-2 w-full"
              required
            />
          </div>

          <button
            type="submit"
            className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
          >
            Salvar Matrícula
          </button>
        </form>
      </div>

      {/* Lista de Matrículas */}
      <div className="bg-white shadow-md rounded p-6">
        <h2 className="text-lg font-bold mb-4">Matrículas Cadastradas</h2>
        {matriculas.length === 0 ? (
          <p className="text-gray-600">Nenhuma matrícula encontrada.</p>
        ) : (
          <table className="w-full border-collapse border border-gray-200">
            <thead>
              <tr className="bg-gray-100">
                <th className="border border-gray-200 px-4 py-2">Aluno</th>
                <th className="border border-gray-200 px-4 py-2">Turma</th>
                <th className="border border-gray-200 px-4 py-2">Ano Letivo</th>
                <th className="border border-gray-200 px-4 py-2">Ações</th>
              </tr>
            </thead>
            <tbody>
              {matriculas.map((matricula) => {
                const aluno = alunos.find((a) => a.id === matricula.alunoId);
                const turma = turmas.find((t) => t.id === matricula.turmaId);

                return (
                  <tr key={matricula.id}>
                    <td className="border px-4 py-2">{aluno?.nome || "—"}</td>
                    <td className="border px-4 py-2">{turma?.nome || "—"}</td>
                    <td className="border px-4 py-2">{matricula.anoLetivo}</td>
                    <td className="border px-4 py-2 flex gap-2">
                      <button
                        onClick={() =>
                          handleUpdateMatricula(matricula.id, {
                            anoLetivo: Number(anoLetivo),
                          })
                        }
                        className="bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDeleteMatricula(matricula.id)}
                        className="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700"
                      >
                        Excluir
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default MatriculaAlunoPage;
