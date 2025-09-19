import React, { useState, useEffect } from "react";
import { collection, addDoc, getDocs } from "firebase/firestore";
import { db } from "../firebase/config";
import Layout from "../components/Layout";
import Loading from "../components/ui/loading";

const CadastroServidorPage = () => {
  const [servidor, setServidor] = useState({
    nome: "",
    cpf: "",
    email: "",
    telefone: "",
    escolaId: "",
    anoLetivo: "",
    funcoes: [],
  });

  const [availableSchools, setAvailableSchools] = useState([]);
  const [currentFuncoes, setCurrentFuncoes] = useState([]);
  const [loading, setLoading] = useState(false);

  // 🔹 Carregar escolas do Firestore
  useEffect(() => {
    const fetchSchools = async () => {
      try {
        const querySnapshot = await getDocs(collection(db, "escolas"));
        const schoolsData = querySnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));
        setAvailableSchools(schoolsData);
      } catch (err) {
        console.error("Erro ao buscar escolas:", err);
      }
    };

    fetchSchools();
  }, []);

  // 🔹 Atualizar servidor dinamicamente
  const handleChange = (e) => {
    const { name, value } = e.target;
    setServidor((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  // 🔹 Adicionar função
  const addFuncao = () => {
    if (servidor.funcoes.includes("")) return;
    setServidor((prev) => ({
      ...prev,
      funcoes: [...prev.funcoes, ""],
    }));
  };

  // 🔹 Alterar função
  const handleFuncaoChange = (index, value) => {
    const novasFuncoes = [...servidor.funcoes];
    novasFuncoes[index] = value;
    setServidor((prev) => ({
      ...prev,
      funcoes: novasFuncoes,
    }));
  };

  // 🔹 Salvar no Firestore
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const newServidor = {
        ...servidor,
        createdAt: new Date(),
      };

      await addDoc(collection(db, "servidores"), newServidor);

      setServidor({
        nome: "",
        cpf: "",
        email: "",
        telefone: "",
        escolaId: "",
        anoLetivo: "",
        funcoes: [],
      });

      alert("Servidor cadastrado com sucesso!");
    } catch (err) {
      console.error("Erro ao cadastrar servidor:", err);
      alert("Erro ao cadastrar servidor.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout>
      <div className="p-6 bg-white shadow-md rounded-lg">
        <h1 className="text-2xl font-bold mb-4">Cadastro de Servidor</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Nome */}
          <div>
            <label htmlFor="nome" className="block font-medium">
              Nome
            </label>
            <input
              id="nome"
              type="text"
              name="nome"
              value={servidor.nome}
              onChange={handleChange}
              className="w-full border rounded p-2"
              required
            />
          </div>

          {/* CPF */}
          <div>
            <label htmlFor="cpf" className="block font-medium">
              CPF
            </label>
            <input
              id="cpf"
              type="text"
              name="cpf"
              value={servidor.cpf}
              onChange={handleChange}
              className="w-full border rounded p-2"
              required
            />
          </div>

          {/* Email */}
          <div>
            <label htmlFor="email" className="block font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              name="email"
              value={servidor.email}
              onChange={handleChange}
              className="w-full border rounded p-2"
              required
            />
          </div>

          {/* Telefone */}
          <div>
            <label htmlFor="telefone" className="block font-medium">
              Telefone
            </label>
            <input
              id="telefone"
              type="text"
              name="telefone"
              value={servidor.telefone}
              onChange={handleChange}
              className="w-full border rounded p-2"
            />
          </div>

          {/* Escola */}
          <div>
            <label htmlFor="escolaId" className="block font-medium">
              Escola
            </label>
            <select
              id="escolaId"
              name="escolaId"
              value={servidor.escolaId}
              onChange={handleChange}
              className="w-full border rounded p-2"
              required
            >
              <option value="">Selecione uma escola</option>
              {availableSchools.map((escola) => (
                <option key={escola.id} value={escola.id}>
                  {escola.nomeEscola}
                </option>
              ))}
            </select>
          </div>

          {/* Ano Letivo */}
          <div>
            <label htmlFor="anoLetivo" className="block font-medium">
              Ano Letivo
            </label>
            <input
              id="anoLetivo"
              type="text"
              name="anoLetivo"
              value={servidor.anoLetivo}
              onChange={handleChange}
              className="w-full border rounded p-2"
            />
          </div>

          {/* Funções */}
          <div>
            <label className="block font-medium">Funções</label>
            {servidor.funcoes.map((funcao, index) => (
              <input
                key={index}
                type="text"
                value={funcao}
                onChange={(e) => handleFuncaoChange(index, e.target.value)}
                className="w-full border rounded p-2 mb-2"
              />
            ))}

            <button
              type="button"
              onClick={addFuncao}
              className="px-3 py-1 bg-blue-600 text-white rounded"
            >
              Adicionar Função
            </button>
          </div>

          {/* Botão de enviar */}
          <div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-green-600 text-white rounded hover:bg-green-700"
            >
              {loading ? "Salvando..." : "Cadastrar Servidor"}
            </button>
          </div>
        </form>
      </div>
    </Layout>
  );
};

export default CadastroServidorPage;
