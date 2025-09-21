import React, { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { doc, getDoc, updateDoc } from "firebase/firestore";
import { db } from "../firebase/config";
import Layout from "../components/Layout";
import { LoadingSpinner as Loading } from "../components/ui/loading.jsx";

const EditarServidorPage = () => {
  const { servidorId } = useParams();
  const [servidor, setServidor] = useState(null);
  const [formData, setFormData] = useState({
    nome: "",
    email: "",
    cargo: "",
    escolaId: "",
  });
  const [schoolsList, setSchoolsList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 🔹 Buscar servidor
  useEffect(() => {
    const fetchServidor = async () => {
      setLoading(true);
      try {
        const servidorRef = doc(db, "servidores", servidorId);
        const snapshot = await getDoc(servidorRef);

        if (snapshot.exists()) {
          const data = snapshot.data();
          setServidor({ id: snapshot.id, ...data });
          setFormData({
            nome: data.nome || "",
            email: data.email || "",
            cargo: data.cargo || "",
            escolaId: data.escolaId || "",
          });
        } else {
          console.warn("Servidor não encontrado.");
        }
      } catch (err) {
        console.error("Erro ao buscar servidor:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchServidor();
  }, [servidorId]);

  // 🔹 Buscar lista de escolas (simulação, ajuste para seu backend/firestore)
  useEffect(() => {
    const fetchSchools = async () => {
      try {
        // Exemplo: supondo que tenha uma coleção "escolas"
        // const snapshot = await getDocs(collection(db, "escolas"));
        // setSchoolsList(snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() })));

        // Mock temporário
        setSchoolsList([
          { id: "1", nomeEscola: "Escola Central" },
          { id: "2", nomeEscola: "Colégio Modelo" },
        ]);
      } catch (err) {
        console.error("Erro ao buscar escolas:", err);
      }
    };

    fetchSchools();
  }, []);

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
      const servidorRef = doc(db, "servidores", servidorId);
      await updateDoc(servidorRef, formData);
      alert("Servidor atualizado com sucesso!");
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
        <h1 className="text-2xl font-bold mb-4">Editar Servidor</h1>

        {loading ? (
          <Loading />
        ) : servidor ? (
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
              <label htmlFor="email" className="block font-medium">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                value={formData.email}
                onChange={handleChange}
                className="w-full border rounded p-2"
                required
              />
            </div>

            <div>
              <label htmlFor="cargo" className="block font-medium">
                Cargo
              </label>
              <input
                id="cargo"
                name="cargo"
                type="text"
                value={formData.cargo}
                onChange={handleChange}
                className="w-full border rounded p-2"
              />
            </div>

            <div>
              <label htmlFor="escolaId" className="block font-medium">
                Escola
              </label>
              <select
                id="escolaId"
                name="escolaId"
                value={formData.escolaId}
                onChange={handleChange}
                className="w-full border rounded p-2"
              >
                <option value="">Selecione uma escola</option>
                {schoolsList.map((escola) => (
                  <option key={escola.id} value={escola.id}>
                    {escola.nomeEscola}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              {saving ? "Salvando..." : "Salvar"}
            </button>
          </form>
        ) : (
          <p className="text-gray-500">Servidor não encontrado.</p>
        )}
      </div>
    </Layout>
  );
};

export default EditarServidorPage;
