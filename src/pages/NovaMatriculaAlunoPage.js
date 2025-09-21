import React, { useState, useEffect } from "react";
import {
  collection,
  getDocs,
  addDoc,
  query,
  where,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../firebase/config";
import { useUser } from "../context/UserContext";
import Layout from "../components/Layout";
import { toast } from "react-hot-toast"; // CORREÇÃO: Alterado de 'react-toastify' para 'react-hot-toast'

const NovaMatriculaAlunoPage = () => {
  const { currentEscolaId, currentAnoLetivo } = useUser();

  const [alunos, setAlunos] = useState([]);
  const [turmas, setTurmas] = useState([]);
  const [selectedAluno, setSelectedAluno] = useState("");
  const [selectedTurma, setSelectedTurma] = useState("");
  const [loading, setLoading] = useState(false);

  // 🔹 Buscar alunos disponíveis para matrícula
  useEffect(() => {
    const fetchAlunos = async () => {
      try {
        const alunosRef = collection(db, "alunos");
        const q = query(alunosRef, where("escolaId", "==", currentEscolaId));
        const snapshot = await getDocs(q);
        setAlunos(snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));
      } catch (error) {
        console.error("Erro ao buscar alunos:", error);
        toast.error("Erro ao carregar alunos");
      }
    };

    if (currentEscolaId) {
      fetchAlunos();
    }
  }, [currentEscolaId]);

  // 🔹 Buscar turmas disponíveis para o ano letivo atual
  useEffect(() => {
    const fetchTurmas = async () => {
      try {
        const turmasRef = collection(db, "turmas");
        const q = query(
          turmasRef,
          where("escolaId", "==", currentEscolaId),
          where("anoLetivo", "==", currentAnoLetivo)
        );
        const snapshot = await getDocs(q);
        setTurmas(snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));
      } catch (error) {
        console.error("Erro ao buscar turmas:", error);
        toast.error("Erro ao carregar turmas");
      }
    };

    if (currentEscolaId && currentAnoLetivo) {
      fetchTurmas();
    }
  }, [currentEscolaId, currentAnoLetivo]);

  // 🔹 Criar matrícula
  const handleMatricular = async (e) => {
    e.preventDefault();
    if (!selectedAluno || !selectedTurma) {
      toast.warn("Selecione aluno e turma antes de salvar");
      return;
    }

    setLoading(true);
    try {
      await addDoc(collection(db, "matriculas"), {
        alunoId: selectedAluno,
        turmaId: selectedTurma,
        escolaId: currentEscolaId,
        anoLetivo: currentAnoLetivo,
        criadoEm: serverTimestamp(),
      });
      toast.success("Matrícula realizada com sucesso!");
      setSelectedAluno("");
      setSelectedTurma("");
    } catch (error) {
      console.error("Erro ao salvar matrícula:", error);
      toast.error("Erro ao realizar matrícula");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-6">Nova Matrícula</h1>

        <form
          onSubmit={handleMatricular}
          className="bg-white shadow-md rounded p-6 space-y-4"
        >
          {/* 🔹 Seleção de Aluno */}
          <div>
            <label
              htmlFor="aluno"
              className="block text-sm font-medium text-gray-700"
            >
              Aluno
            </label>
            <select
              id="aluno"
              value={selectedAluno}
              onChange={(e) => setSelectedAluno(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
            >
              <option value="">Selecione um aluno</option>
              {alunos.map((aluno) => (
                <option key={aluno.id} value={aluno.id}>
                  {aluno.nome}
                </option>
              ))}
            </select>
          </div>
          {/* 🔹 Seleção de Turma */}
          <div>
            <label
              htmlFor="turma"
              className="block text-sm font-medium text-gray-700"
            >
              Turma
            </label>
            <select
              id="turma"
              value={selectedTurma}
              onChange={(e) => setSelectedTurma(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
            >
              <option value="">Selecione uma turma</option>
              {turmas.map((turma) => (
                <option key={turma.id} value={turma.id}>
                  {turma.nome} - {turma.serie}
                </option>
              ))}
            </select>
          </div>

          {/* 🔹 Botão de Salvar */}
          <div>
            <button
              type="submit"
              disabled={loading}
              className={`w-full py-2 px-4 rounded-md text-white font-semibold ${
                loading
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700"
              }`}
            >
              {loading ? "Salvando..." : "Matricular"}
            </button>
          </div>
        </form>
      </div>
    </Layout>
  );
};

export default NovaMatriculaAlunoPage;
