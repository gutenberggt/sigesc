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

function ComponentesCurricularesPage() {
  const { userData, loading: userLoading } = useUser();

  const [componentes, setComponentes] = useState([]);
  const [editingComponente, setEditingComponente] = useState(null);

  const [selectedNivel, setSelectedNivel] = useState("");
  const [selectedSerie, setSelectedSerie] = useState("");
  const [selectedComponente, setSelectedComponente] = useState("");
  const [cargaHoraria, setCargaHoraria] = useState("");
  const [sigla, setSigla] = useState("");

  const [availableSeries, setAvailableSeries] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);

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
      // ======================= CORREÇÃO: Nome da Coleção Revertido para o Correto =======================
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
      setError(
        "Não foi possível carregar os componentes. Verifique o nome da coleção e os índices do Firestore."
      );
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
    };

    try {
      if (editingComponente) {
        // ======================= CORREÇÃO: Nome da Coleção Revertido para o Correto =======================
        const docRef = doc(db, "componentes", editingComponente.id);
        await updateDoc(docRef, componenteData);
        setSuccess("Componente atualizado com sucesso!");
      } else {
        // ======================= CORREÇÃO: Nome da Coleção Revertido para o Correto =======================
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
    window.scrollTo(0, 0);
  };

  const handleDelete = async (id) => {
    if (
      window.confirm(
        "Tem certeza que deseja excluir este componente curricular?"
      )
    ) {
      try {
        // ======================= CORREÇÃO: Nome da Coleção Revertido para o Correto =======================
        await deleteDoc(doc(db, "componentes", id));
        setSuccess("Componente excluído com sucesso!");
        fetchComponentes();
      } catch (err) {
        setError("Ocorreu um erro ao excluir o componente.");
      }
    }
  };

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
            <h3 className="text-lg font-semibold">
              {editingComponente
                ? "Editar Componente"
                : "Adicionar Novo Componente"}
            </h3>

            <div>
              <label
                htmlFor="nivelEnsino"
                className="block text-sm font-medium text-gray-700"
              >
                1º - Nível de Ensino
              </label>
              <select
                id="nivelEnsino"
                value={selectedNivel}
                onChange={(e) => setSelectedNivel(e.target.value)}
                className="mt-1 block w-full p-2 border rounded-md"
                required
              >
                <option value="">Selecione...</option>
                {niveisDeEnsinoList.map((nivel) => (
                  <option key={nivel} value={nivel}>
                    {nivel}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="serieAno"
                className="block text-sm font-medium text-gray-700"
              >
                2º - Série / Ano / Etapa
              </label>
              <select
                id="serieAno"
                value={selectedSerie}
                onChange={(e) => setSelectedSerie(e.target.value)}
                className="mt-1 block w-full p-2 border rounded-md"
                required
                disabled={!selectedNivel}
              >
                <option value="">Selecione...</option>
                {availableSeries.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="componente"
                className="block text-sm font-medium text-gray-700"
              >
                3º - Componente Curricular
              </label>
              <select
                id="componente"
                value={selectedComponente}
                onChange={(e) => setSelectedComponente(e.target.value)}
                className="mt-1 block w-full p-2 border rounded-md"
                required
                disabled={!selectedSerie}
              >
                <option value="">Selecione...</option>
                {availableComponentes.map((c) => (
                  <option key={c.nome} value={c.nome}>
                    {c.nome}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="cargaHoraria"
                  className="block text-sm font-medium text-gray-700"
                >
                  4º - Carga Horária (h)
                </label>
                <input
                  type="number"
                  id="cargaHoraria"
                  value={cargaHoraria}
                  onChange={(e) => setCargaHoraria(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
              <div>
                <label
                  htmlFor="sigla"
                  className="block text-sm font-medium text-gray-700"
                >
                  Sigla (Opcional)
                </label>
                <input
                  type="text"
                  id="sigla"
                  value={sigla}
                  onChange={(e) => setSigla(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
            </div>

            <div className="flex justify-end space-x-2 mt-4">
              {editingComponente && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="bg-gray-500 text-white py-2 px-4 rounded"
                >
                  Cancelar Edição
                </button>
              )}
              <button
                type="submit"
                disabled={isSubmitting}
                className="bg-blue-600 text-white py-2 px-4 rounded"
              >
                {isSubmitting ? "Salvando..." : "Salvar Componente"}
              </button>
            </div>
          </form>
        )}

        <hr className="my-8" />
        <h3 className="text-xl font-bold mb-4 text-gray-800">
          Componentes Cadastrados
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                <th className="py-3 px-6 text-left">Nome</th>
                <th className="py-3 px-6 text-left">Série/Ano</th>
                <th className="py-3 px-6 text-left">C.H.</th>
                {isAdministrador && (
                  <th className="py-3 px-6 text-center">Ações</th>
                )}
              </tr>
            </thead>
            <tbody className="text-gray-700">
              {componentes.map((comp) => (
                <tr key={comp.id} className="border-b hover:bg-gray-100">
                  <td className="py-3 px-6 font-medium">{comp.nome}</td>
                  <td className="py-3 px-6">{comp.serieAno}</td>
                  <td className="py-3 px-6">{comp.cargaHoraria}h</td>
                  {isAdministrador && (
                    <td className="py-3 px-6 text-center">
                      <button
                        onClick={() => handleEdit(comp)}
                        className="text-blue-600 hover:text-blue-800 mr-3"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(comp.id)}
                        className="text-red-600 hover:text-red-800"
                      >
                        Excluir
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ComponentesCurricularesPage;
