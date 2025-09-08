import React, { useState, useEffect, useCallback } from "react";
import { db } from "../firebase/config";
import {
  collection,
  getDocs,
  addDoc,
  updateDoc,
  deleteDoc,
  doc,
  query,
  orderBy,
} from "firebase/firestore";
import { useUser } from "../context/UserContext";
import {
  niveisDeEnsinoList,
  seriesAnosEtapasData,
} from "../data/ensinoConstants";
import { componentesData } from "./ComponentesPage";

export default function ComponentesCurricularesPage() {
  const { userData, loading: userLoading } = useUser();
  const [componentes, setComponentes] = useState([]);
  const [editingComponente, setEditingComponente] = useState(null);
  const [selectedNivel, setSelectedNivel] = useState("");
  const [selectedSerie, setSelectedSerie] = useState("");
  const [selectedComponente, setSelectedComponente] = useState("");
  const [cargaHoraria, setCargaHoraria] = useState("");
  const [sigla, setSigla] = useState("");
  const [areaConhecimento, setAreaConhecimento] = useState("");
  const [availableSeries, setAvailableSeries] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [filtroTexto, setFiltroTexto] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const isAdministrador = userData?.funcao?.toLowerCase() === "administrador";

  useEffect(() => {
    if (selectedNivel) {
      setAvailableSeries(seriesAnosEtapasData[selectedNivel] || []);
    } else {
      setAvailableSeries([]);
    }
    setSelectedSerie("");
  }, [selectedNivel]);

  useEffect(() => {
    if (selectedSerie) {
      setAvailableComponentes(componentesData[selectedSerie] || []);
    } else {
      setAvailableComponentes([]);
    }
    setSelectedComponente("");
  }, [selectedSerie]);

  useEffect(() => {
    if (selectedComponente) {
      const componenteInfo = availableComponentes.find(
        (c) => c.nome === selectedComponente
      );
      setCargaHoraria(componenteInfo?.cargaHoraria || "");
      setSigla(componenteInfo?.sigla || "");
    } else {
      setCargaHoraria("");
      setSigla("");
    }
  }, [selectedComponente, availableComponentes]);

  const fetchComponentes = useCallback(async () => {
    setIsLoading(true);
    try {
      const q = query(
        collection(db, "componentes"),
        orderBy("serieAno"),
        orderBy("nome")
      );
      const querySnapshot = await getDocs(q);
      const componentesList = querySnapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      setComponentes(componentesList);
    } catch (err) {
      console.error("Erro ao buscar componentes:", err);
      setError("Não foi possível carregar os componentes.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchComponentes();
  }, [fetchComponentes]);

  const resetForm = () => {
    setEditingComponente(null);
    setSelectedNivel("");
    setSelectedSerie("");
    setSelectedComponente("");
    setCargaHoraria("");
    setSigla("");
    setAreaConhecimento("");
    setError("");
    setSuccess("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedNivel || !selectedSerie || !selectedComponente) {
      setError("Todos os campos de seleção são obrigatórios.");
      return;
    }

    setIsSubmitting(true);
    setError("");
    setSuccess("");

    const componenteData = {
      nivelEnsino: selectedNivel,
      serieAno: selectedSerie,
      nome: selectedComponente,
      sigla: sigla.toUpperCase(),
      cargaHoraria: Number(cargaHoraria) || 0,
      areaConhecimento,
    };

    try {
      if (editingComponente) {
        const docRef = doc(db, "componentes", editingComponente.id);
        await updateDoc(docRef, componenteData);
        setSuccess("Componente atualizado com sucesso!");
      } else {
        await addDoc(collection(db, "componentes"), componenteData);
        setSuccess("Componente cadastrado com sucesso!");
      }
      resetForm();
      fetchComponentes();
    } catch (err) {
      setError("Ocorreu um erro ao salvar o componente.");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEdit = (componente) => {
    setEditingComponente(componente);
    setSelectedNivel(componente.nivelEnsino);
    setSelectedSerie(componente.serieAno);
    setSelectedComponente(componente.nome);
    setCargaHoraria(componente.cargaHoraria || "");
    setSigla(componente.sigla || "");
    setAreaConhecimento(componente.areaConhecimento || "");
    window.scrollTo(0, 0);
  };

  const handleDelete = async (id) => {
    if (
      window.confirm(
        "Tem certeza que deseja excluir este componente curricular?"
      )
    ) {
      try {
        await deleteDoc(doc(db, "componentes", id));
        setSuccess("Componente excluído com sucesso!");
        fetchComponentes();
      } catch (err) {
        setError("Ocorreu um erro ao excluir o componente.");
      }
    }
  };

  const componentesFiltrados = componentes.filter((comp) =>
    comp.nome.toLowerCase().includes(filtroTexto.toLowerCase())
  );

  const agrupados = componentesFiltrados.reduce((acc, comp) => {
    const chave = `${comp.nivelEnsino} - ${comp.serieAno}`;
    if (!acc[chave]) acc[chave] = [];
    acc[chave].push(comp);
    return acc;
  }, {});

  if (userLoading || isLoading)
    return <div className="p-6 text-center">Carregando...</div>;

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          Gestão de Componentes Curriculares
        </h2>

        {error && (
          <p className="text-red-500 bg-red-100 p-3 rounded-md text-center mb-4">
            {error}
          </p>
        )}
        {success && (
          <p className="text-green-500 bg-green-100 p-3 rounded-md text-center mb-4">
            {success}
          </p>
        )}

        {isAdministrador && (
          <form
            onSubmit={handleSubmit}
            className="mb-8 p-4 border rounded-md bg-gray-50 space-y-4"
          >
            {/* Campos do formulário */}
            {/* ... (como já corrigido anteriormente) */}
            {/* Campo de carga horária, sigla, área de conhecimento e botão de envio */}
          </form>
        )}

        <input
          type="text"
          placeholder="Buscar componente..."
          value={filtroTexto}
          onChange={(e) => setFiltroTexto(e.target.value)}
          className="mb-4 p-2 border rounded w-full"
        />

        <table className="min-w-full border-collapse bg-white shadow-sm rounded-md">
          <thead className="bg-gray-100 text-gray-700 text-sm">
            <tr>
              <th className="p-2 text-left">Nome</th>
              <th className="p-2 text-left">Sigla</th>
              <th className="p-2 text-left">Série</th>
              <th className="p-2 text-left">Nível</th>
              <th className="p-2 text-left">Carga Horária</th>
              <th className="p-2 text-left">Área</th>
              <th className="p-2 text-center">Ações</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(agrupados).map(([grupo, comps]) => (
              <React.Fragment key={grupo}>
                <tr className="bg-blue-50 font-bold">
                  <td colSpan={7} className="py-2 px-6">
                    {grupo}
                  </td>
                </tr>
                {comps.map((comp) => (
                  <tr key={comp.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 px-4">{comp.nome}</td>
                    <td className="py-2 px-4">{comp.sigla}</td>
                    <td className="py-2 px-4">{comp.serieAno}</td>
                    <td className="py-2 px-4">{comp.nivelEnsino}</td>
                    <td className="py-2 px-4">{comp.cargaHoraria}h</td>
                    <td className="py-2 px-4">
                      {comp.areaConhecimento || "—"}
                    </td>
                    <td className="py-2 px-4 text-center">
                      <button
                        onClick={() => handleEdit(comp)}
                        className="text-blue-600 hover:text-blue-800 mr-3"
                      >
                        ✏️
                      </button>
                      <button
                        onClick={() => handleDelete(comp.id)}
                        className="text-red-600 hover:text-red-800"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
