import React, { useState, useEffect } from "react";
import { collection, query, where, getDocs } from "firebase/firestore";
import { db } from "../firebase/config";
import Layout from "../components/Layout";
import Loading from "../components/ui/loading";

const BuscaAlunoPage = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [alunos, setAlunos] = useState([]);
  const [loading, setLoading] = useState(false); // ✅ corrigido

  useEffect(() => {
    if (searchTerm.trim() === "") {
      setAlunos([]);
      return;
    }

    const fetchAlunos = async () => {
      setLoading(true); // inicia o loading
      try {
        const alunosRef = collection(db, "alunos");
        const q = query(
          alunosRef,
          where("nome", ">=", searchTerm),
          where("nome", "<=", searchTerm + "\uf8ff")
        );

        const querySnapshot = await getDocs(q);
        const alunosEncontrados = querySnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        setAlunos(alunosEncontrados);
      } catch (error) {
        console.error("Erro ao buscar alunos:", error);
      } finally {
        setLoading(false); // finaliza o loading
      }
    };

    fetchAlunos();
  }, [searchTerm]);

  return (
    <Layout>
      <div className="p-6 bg-white rounded-lg shadow-md">
        <h1 className="text-2xl font-bold mb-4">Buscar Aluno</h1>

        <input
          type="text"
          placeholder="Digite o nome do aluno..."
          className="w-full p-2 border rounded mb-4"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        {loading && <Loading />} {/* ✅ indicador de carregamento */}

        {!loading && alunos.length > 0 && (
          <ul className="divide-y divide-gray-200">
            {alunos.map((aluno) => (
              <li key={aluno.id} className="p-2">
                <span className="font-medium">{aluno.nome}</span> —{" "}
                {aluno.matricula || "Sem matrícula"}
              </li>
            ))}
          </ul>
        )}

        {!loading && searchTerm && alunos.length === 0 && (
          <p className="text-gray-500">Nenhum aluno encontrado.</p>
        )}
      </div>
    </Layout>
  );
};

export default BuscaAlunoPage;
