import React, { useEffect, useState } from "react";
import {
  collection,
  doc,
  getDocs,
  setDoc,
  updateDoc,
  deleteDoc,
} from "firebase/firestore";
import { db } from "../firebase/config";
import { toast } from "react-hot-toast";
// CORREÇÃO: Caminho ajustado para o correto
import { LoadingSpinner as Loading } from "../components/ui/loading.jsx";
import { PageHeader } from "../components/ui/pageHeader.jsx";

const MatriculaAlunoPage = () => {
  const [alunos, setAlunos] = useState([]);
  const [turmas, setTurmas] = useState([]);
  const [selectedAluno, setSelectedAluno] = useState("");
  const [selectedTurma, setSelectedTurma] = useState("");
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear());
  const [matriculas, setMatriculas] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const alunosSnapshot = await getDocs(collection(db, "alunos"));
        const turmasSnapshot = await getDocs(collection(db, "turmas"));
        const matriculasSnapshot = await getDocs(collection(db, "matriculas"));

        setAlunos(
          alunosSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );
        setTurmas(
          turmasSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );
        setMatriculas(
          matriculasSnapshot.docs.map((doc) => ({
            id: doc.id,
            ...doc.data(),
          }))
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

  const handleSaveMatricula = async () => {
    if (!selectedAluno || !selectedTurma) {
      toast.error("Selecione um aluno e uma turma.");
      return;
    }

    setLoading(true);
    try {
      const matriculaRef = doc(collection(db, "matriculas"));
      const novaMatricula = {
        alunoId: selectedAluno,
        turmaId: selectedTurma,
        anoLetivo,
        criadoEm: new Date(),
        deletado: false,
      };
      await setDoc(matriculaRef, novaMatricula);

      setMatriculas([...matriculas, { id: matriculaRef.id, ...novaMatricula }]);
      toast.success("Matrícula realizada com sucesso!");

      setSelectedAluno("");
      setSelectedTurma("");
    } catch (error) {
      console.error("Erro ao salvar matrícula:", error);
      toast.error("Erro ao salvar matrícula.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateMatricula = async (matriculaId, updates) => {
    setLoading(true);
    try {
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
    if (!window.confirm("Tem certeza que deseja excluir esta matrícula?"))
      return;

    setLoading(true);
    try {
      await deleteDoc(doc(db, "matriculas", matriculaId));
      setMatriculas(matriculas.filter((mat) => mat.id !== matriculaId));
      toast.success("Matrícula excluída com sucesso!");
    } catch (error) {
      console.error("Erro ao excluir matrícula:", error);
      toast.error("Erro ao excluir matrícula.");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full">
        <Loading />
      </div>
    );
  }

  return (
    <div className="p-6">
      <PageHeader title="Matrícula de Alunos" />

      <div className="bg-white shadow-md rounded p-6 mb-6">
        <h2 className="text-lg font-bold mb-4">Nova Matrícula</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label
              htmlFor="aluno"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Aluno
            </label>
            <select
              id="aluno"
              value={selectedAluno}
              onChange={(e) => setSelectedAluno(e.target.value)}
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

          <div>
            <label
              htmlFor="turma"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Turma
            </label>
            <select
              id="turma"
              value={selectedTurma}
              onChange={(e) => setSelectedTurma(e.target.value)}
              className="border rounded px-2 py-1 w-full"
            >
              <option value="">Selecione uma turma</option>
              {turmas.map((turma) => (
                <option key={turma.id} value={turma.id}>
                  {turma.nomeTurma}
                </option>
              ))}
            </select>
          </div>

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

      <div className="bg-white shadow-md rounded p-6">
        <h2 className="text-lg font-bold mb-4">Matrículas Cadastradas</h2>
        {matriculas.length === 0 ? (
          <p className="text-gray-600">Nenhuma matrícula encontrada.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border border-gray-200">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border border-gray-200 px-4 py-2">Aluno</th>
                  <th className="border border-gray-200 px-4 py-2">Turma</th>
                  <th className="border border-gray-200 px-4 py-2">
                    Ano Letivo
                  </th>
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
                      <td className="border px-4 py-2">
                        {turma?.nomeTurma || "—"}
                      </td>
                      <td className="border px-4 py-2">
                        {matricula.anoLetivo}
                      </td>
                      <td className="border px-4 py-2 flex gap-2 justify-center">
                        <button
                          onClick={() =>
                            handleUpdateMatricula(matricula.id, {
                              anoLetivo: 2026,
                            })
                          }
                          className="bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600 text-sm"
                        >
                          Editar
                        </button>
                        <button
                          onClick={() => handleDeleteMatricula(matricula.id)}
                          className="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 text-sm"
                        >
                          Excluir
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default MatriculaAlunoPage;
