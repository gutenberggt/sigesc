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

function BimestresPage() {
  const { userData, loading: userLoading } = useUser();

  const [bimestres, setBimestres] = useState([]);
  const [editingBimestre, setEditingBimestre] = useState(null);

  const [anoLetivo, setAnoLetivo] = useState(
    new Date().getFullYear().toString()
  );
  const [nome, setNome] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [modoLancamento, setModoLancamento] = useState("Bimestral");
  const [situacao, setSituacao] = useState("ABERTO");

  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const isAdministrador = userData?.funcao?.toLowerCase() === "administrador";

  const fetchBimestres = useCallback(async () => {
    setIsLoading(true);
    try {
      const q = query(
        collection(db, "bimestres"),
        orderBy("anoLetivo", "desc"),
        orderBy("dataInicio", "asc")
      );
      const querySnapshot = await getDocs(q);
      const bimestresList = querySnapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      setBimestres(bimestresList);
    } catch (err) {
      console.error("Erro ao buscar bimestres:", err);
      setError("Não foi possível carregar os bimestres.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!userLoading) {
      fetchBimestres();
    }
  }, [userLoading, fetchBimestres]);

  const resetForm = () => {
    setEditingBimestre(null);
    setAnoLetivo(new Date().getFullYear().toString());
    setNome("");
    setDataInicio("");
    setDataFim("");
    setModoLancamento("Bimestral");
    setSituacao("ABERTO");
    setError("");
    setSuccess("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (
      !anoLetivo ||
      !nome ||
      !dataInicio ||
      !dataFim ||
      !situacao ||
      !modoLancamento
    ) {
      setError("Todos os campos são obrigatórios.");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setSuccess("");

    const bimestreData = {
      anoLetivo,
      nome: nome.toUpperCase(),
      dataInicio,
      dataFim,
      modoLancamento,
      situacao,
    };

    try {
      if (editingBimestre) {
        const docRef = doc(db, "bimestres", editingBimestre.id);
        await updateDoc(docRef, bimestreData);
        setSuccess("Bimestre atualizado com sucesso!");
        setBimestres(
          bimestres.map((b) =>
            b.id === editingBimestre.id ? { id: b.id, ...bimestreData } : b
          )
        );
      } else {
        const docRef = await addDoc(collection(db, "bimestres"), bimestreData);
        setSuccess("Bimestre cadastrado com sucesso!");
        setBimestres([...bimestres, { id: docRef.id, ...bimestreData }]);
      }
      resetForm();
    } catch (err) {
      console.error("Erro ao salvar bimestre:", err);
      setError("Ocorreu um erro ao salvar o bimestre.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEdit = (bimestre) => {
    setEditingBimestre(bimestre);
    setAnoLetivo(bimestre.anoLetivo);
    setNome(bimestre.nome);
    setDataInicio(bimestre.dataInicio);
    setDataFim(bimestre.dataFim);
    setModoLancamento(bimestre.modoLancamento || "Bimestral");
    setSituacao(bimestre.situacao);
    window.scrollTo(0, 0);
  };

  const handleDelete = async (id) => {
    if (window.confirm("Tem certeza que deseja excluir este bimestre?")) {
      try {
        await deleteDoc(doc(db, "bimestres", id));
        setSuccess("Bimestre excluído com sucesso!");
        setBimestres(bimestres.filter((b) => b.id !== id));
      } catch (err) {
        console.error("Erro ao excluir bimestre:", err);
        setError("Ocorreu um erro ao excluir o bimestre.");
      }
    }
  };

  const formatDateForDisplay = (dateString) => {
    if (!dateString) return "";
    const [year, month, day] = dateString.split("-");
    return `${day}/${month}/${year}`;
  };

  if (userLoading || isLoading) {
    return <div className="p-6 text-center">Carregando...</div>;
  }

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          Gestão de Bimestres
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
            className="mb-8 p-4 border rounded-md bg-gray-50"
          >
            <h3 className="text-lg font-semibold mb-4">
              {editingBimestre ? "Editar Bimestre" : "Adicionar Novo Bimestre"}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label
                  htmlFor="anoLetivo"
                  className="block text-sm font-medium text-gray-700"
                >
                  Ano Letivo
                </label>
                <input
                  type="number"
                  id="anoLetivo"
                  value={anoLetivo}
                  onChange={(e) => setAnoLetivo(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
              <div>
                <label
                  htmlFor="nome"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nome do Bimestre
                </label>
                <input
                  type="text"
                  id="nome"
                  placeholder="Ex: 1º BIMESTRE"
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
              <div>
                <label
                  htmlFor="situacao"
                  className="block text-sm font-medium text-gray-700"
                >
                  Situação
                </label>
                <select
                  id="situacao"
                  value={situacao}
                  onChange={(e) => setSituacao(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                >
                  <option value="ABERTO">Aberto</option>
                  <option value="FECHADO">Fechado</option>
                </select>
              </div>
              <div>
                <label
                  htmlFor="dataInicio"
                  className="block text-sm font-medium text-gray-700"
                >
                  Data de Início
                </label>
                <input
                  type="date"
                  id="dataInicio"
                  value={dataInicio}
                  onChange={(e) => setDataInicio(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
              <div>
                <label
                  htmlFor="dataFim"
                  className="block text-sm font-medium text-gray-700"
                >
                  Data de Fim
                </label>
                <input
                  type="date"
                  id="dataFim"
                  value={dataFim}
                  onChange={(e) => setDataFim(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                />
              </div>
              <div>
                <label
                  htmlFor="modoLancamento"
                  className="block text-sm font-medium text-gray-700"
                >
                  Modo de Lançamento
                </label>
                <select
                  id="modoLancamento"
                  value={modoLancamento}
                  onChange={(e) => setModoLancamento(e.target.value)}
                  className="mt-1 block w-full p-2 border rounded-md"
                >
                  <option value="Bimestral">Bimestral</option>
                  <option value="Mensal">Mensal</option>
                  <option value="Semestral">Semestral</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end space-x-2 mt-4">
              {editingBimestre && (
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
                {isSubmitting ? "Salvando..." : "Salvar"}
              </button>
            </div>
          </form>
        )}

        <hr className="my-8" />
        <h3 className="text-xl font-bold mb-4 text-gray-800">
          Bimestres Cadastrados
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                <th className="py-3 px-6 text-left">Ano Letivo</th>
                <th className="py-3 px-6 text-left">Bimestre</th>
                <th className="py-3 px-6 text-left">Início</th>
                <th className="py-3 px-6 text-left">Fim</th>
                <th className="py-3 px-6 text-left">Situação</th>
                {isAdministrador && (
                  <th className="py-3 px-6 text-center">Ações</th>
                )}
              </tr>
            </thead>
            <tbody className="text-gray-700">
              {bimestres.map((bimestre) => (
                <tr key={bimestre.id} className="border-b hover:bg-gray-100">
                  <td className="py-3 px-6">{bimestre.anoLetivo}</td>
                  <td className="py-3 px-6">{bimestre.nome}</td>
                  <td className="py-3 px-6">
                    {formatDateForDisplay(bimestre.dataInicio)}
                  </td>
                  <td className="py-3 px-6">
                    {formatDateForDisplay(bimestre.dataFim)}
                  </td>
                  <td className="py-3 px-6">
                    <span
                      className={`py-1 px-3 rounded-full text-xs ${
                        bimestre.situacao === "ABERTO"
                          ? "bg-green-200 text-green-700"
                          : "bg-red-200 text-red-700"
                      }`}
                    >
                      {bimestre.situacao}
                    </span>
                  </td>
                  {isAdministrador && (
                    <td className="py-3 px-6 text-center">
                      <button
                        onClick={() => handleEdit(bimestre)}
                        className="text-blue-600 hover:text-blue-800 mr-3"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(bimestre.id)}
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

export default BimestresPage;
