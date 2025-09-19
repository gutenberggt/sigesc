import React, { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { doc, getDoc, updateDoc } from "firebase/firestore";
import { db } from "../firebase/config";
import Layout from "../components/Layout";
import Loading from "../components/ui/loading";

const EditarAlunoPage = () => {
  const { alunoId } = useParams();
  const [aluno, setAluno] = useState(null);
  const [formData, setFormData] = useState({
    nome: "",
    matricula: "",
    dataNascimento: "",
    turma: "",
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 🔹 Buscar dados do aluno
  useEffect(() => {
    const fetchAluno = async () => {
      setLoading(true);
      try {
        const alunoRef = doc(db, "alunos", alunoId);
        const snapshot = await getDoc(alunoRef);

        if (snapshot.exists()) {
          const data = snapshot.data();
          setAluno({ id: snapshot.id, ...data });
          setFormData({
            nome: data.nome || "",
            matricula: data.matricula || "",
            dataNascimento: data.dataNascimento || "",
            turma: data.turma || "",
          });
        } else {
          console.warn("Aluno não encontrado.");
        }
      } catch (err) {
        console.error("Erro ao buscar aluno:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchAluno();
  }, [alunoId]);

  // 🔹 Atualizar inputs
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // 🔹 Salvar alterações
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const alunoRef = doc(db, "alunos", alunoId);
      await updateDoc(alunoRef, formData);
      alert("Aluno atualizado com sucesso!");
    } catch (err) {
      console.error("Erro ao salvar alterações:", err);
      alert("Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Layout>
      <div className="p-6 bg-white rounded shadow-md">
        <h1 className="text-2xl font-bold mb-4">Editar Aluno</h1>

        {loading ? (
          <Loading />
        ) : aluno ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="nome" className="block font-medium">
                Nome
              </label>
              <input
                id="nome"
                name="nome"
                type="text"
                value={formData.nome}
                onChange={handleChange}
                className="w-full border rounded p-2"
                required
              />
            </div>

            <div>
              <label htmlFor="matricula" className="block font-medium">
                Matrícula
              </label>
              <input
                id="matricula"
                name="matricula"
                type="text"
                value={formData.matricula}
                onChange={handleChange}
                className="w-full border rounded p-2"
                required
              />
            </div>

            <div>
              <label htmlFor="dataNascimento" className="block font-medium">
                Data de Nascimento
              </label>
              <input
                id="dataNascimento"
                name="dataNascimento"
                type="date"
                value={formData.dataNascimento}
                onChange={handleChange}
                className="w-full border rounded p-2"
              />
            </div>

            <div>
              <label htmlFor="turma" className="block font-medium">
                Turma
              </label>
              <input
                id="turma"
                name="turma"
                type="text"
                value={formData.turma}
                onChange={handleChange}
                className="w-full border rounded p-2"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
            >
              {saving ? "Salvando..." : "Salvar"}
            </button>
          </form>
        ) : (
          <p className="text-gray-500">Aluno não encontrado.</p>
        )}
      </div>
    </Layout>
  );
};

export default EditarAlunoPage;
