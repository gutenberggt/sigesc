import React, { useState, useEffect } from "react";
import { collection, getDocs, addDoc } from "firebase/firestore";
import { db } from "../firebase/config";
import Layout from "../components/Layout";
import { LoadingSpinner as Loading } from "../components/ui/loading.jsx";

const ComponentesCurricularesPage = () => {
  const [componentes, setComponentes] = useState([]);
  const [seriesAnosEtapasData, setSeriesAnosEtapasData] = useState([]);
  const [novoComponente, setNovoComponente] = useState({
    nome: "",
    serieAnoEtapaId: "",
  });
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 🔹 Buscar componentes e séries/anos
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const compSnapshot = await getDocs(collection(db, "componentes"));
        const comps = compSnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        const seriesSnapshot = await getDocs(
          collection(db, "seriesAnosEtapas")
        );
        const seriesData = seriesSnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        setComponentes(comps);
        setSeriesAnosEtapasData(seriesData);
      } catch (err) {
        console.error("Erro ao carregar dados:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // 🔹 Atualizar input do formulário
  const handleChange = (e) => {
    const { name, value } = e.target;
    setNovoComponente((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // 🔹 Salvar componente
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!novoComponente.nome || !novoComponente.serieAnoEtapaId) {
      alert("Preencha todos os campos!");
      return;
    }

    setIsSubmitting(true);
    try {
      const newComp = {
        ...novoComponente,
        createdAt: new Date(),
      };
      const docRef = await addDoc(collection(db, "componentes"), newComp);

      setComponentes((prev) => [...prev, { id: docRef.id, ...newComp }]);

      setNovoComponente({ nome: "", serieAnoEtapaId: "" });
      alert("Componente curricular cadastrado com sucesso!");
    } catch (err) {
      console.error("Erro ao cadastrar componente:", err);
      alert("Erro ao cadastrar.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Layout>
      <div className="p-6 bg-white rounded shadow-md">
        <h1 className="text-2xl font-bold mb-4">Componentes Curriculares</h1>

        {loading ? (
          <Loading />
        ) : (
          <>
            {/* Formulário */}
            <form onSubmit={handleSubmit} className="space-y-4 mb-6">
              <div>
                <label htmlFor="nome" className="block font-medium">
                  Nome do Componente
                </label>
                <input
                  id="nome"
                  type="text"
                  name="nome"
                  value={novoComponente.nome}
                  onChange={handleChange}
                  className="w-full border rounded p-2"
                  required
                />
              </div>

              <div>
                <label htmlFor="serieAnoEtapaId" className="block font-medium">
                  Série/Ano/Etapa
                </label>
                <select
                  id="serieAnoEtapaId"
                  name="serieAnoEtapaId"
                  value={novoComponente.serieAnoEtapaId}
                  onChange={handleChange}
                  className="w-full border rounded p-2"
                  required
                >
                  <option value="">Selecione</option>
                  {seriesAnosEtapasData.map((serie) => (
                    <option key={serie.id} value={serie.id}>
                      {serie.nome}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                {isSubmitting ? "Salvando..." : "Cadastrar"}
              </button>
            </form>

            {/* Lista */}
            <ul className="divide-y divide-gray-200">
              {componentes.map((comp) => (
                <li key={comp.id} className="py-2">
                  {comp.nome} -{" "}
                  <span className="text-gray-500">{comp.serieAnoEtapaId}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Layout>
  );
};

export default ComponentesCurricularesPage;
