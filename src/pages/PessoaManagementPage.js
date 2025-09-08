import React, { useState, useEffect } from "react";
import { db, auth } from "../firebase/config";
import {
  collection,
  addDoc,
  getDocs,
  doc,
  updateDoc,
  deleteDoc,
  query,
  where,
  orderBy,
  setDoc,
  getDoc,
} from "firebase/firestore";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { useUser } from "../context/UserContext";
import { useNavigate } from "react-router-dom";

function PessoaManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [pessoas, setPessoas] = useState([]);
  const [editingPessoa, setEditingPessoa] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [personSearchSuggestions, setPersonSearchSuggestions] = useState([]);
  const [userStatus, setUserStatus] = useState("");

  // --- Estados dos Dados Pessoais (e todos os outros) ---
  const [cpf, setCpf] = useState("");
  const [nomeCompleto, setNomeCompleto] = useState("");
  const [nomeSocialAfetivo, setNomeSocialAfetivo] = useState("");
  const [sexo, setSexo] = useState("Nao Informado");
  const [estadoCivil, setEstadoCivil] = useState("Solteiro(a)");
  const [dataNascimento, setDataNascimento] = useState("");
  const [nacionalidade, setNacionalidade] = useState("");
  const [raca, setRaca] = useState("Nao Declarada");
  const [povoIndigena, setPovoIndigena] = useState("");
  const [religiao, setReligiao] = useState("");
  const [naturalidadeCidade, setNaturalidadeCidade] = useState("");
  const [naturalidadeEstado, setNaturalidadeEstado] = useState("");
  const [falecido, setFalecido] = useState("nao");
  const [pessoaPai, setPessoaPai] = useState("");
  const [telefonePai, setTelefonePai] = useState("");
  const [escolaridadePai, setEscolaridadePai] = useState("Nao Informado");
  const [profissaoPai, setProfissaoPai] = useState("");
  const [pessoaMae, setPessoaMae] = useState("");
  const [telefoneMae, setTelefoneMae] = useState("");
  const [escolaridadeMae, setEscolaridadeMae] = useState("Nao Informado");
  const [profissaoMae, setProfissaoMae] = useState("");
  const [rgNumero, setRgNumero] = useState("");
  const [rgDataEmissao, setRgDataEmissao] = useState("");
  const [rgOrgaoEmissor, setRgOrgaoEmissor] = useState("");
  const [rgEstado, setRgEstado] = useState("");
  const [nisPisPasep, setNisPisPasep] = useState("");
  const [carteiraSUS, setCarteiraSUS] = useState("");
  const [certidaoTipo, setCertidaoTipo] = useState("Nascimento");
  const [certidaoEstado, setCertidaoEstado] = useState("");
  const [certidaoCartorio, setCertidaoCartorio] = useState("");
  const [certidaoDataEmissao, setCertidaoDataEmissao] = useState("");
  const [certidaoNumero, setCertidaoNumero] = useState("");
  const [certidaoCidade, setCertidaoCidade] = useState("");
  const [passaporteNumero, setPassaporteNumero] = useState("");
  const [passaportePaisEmissor, setPassaportePaisEmissor] = useState("");
  const [passaporteDataEmissao, setPassaporteDataEmissao] = useState("");
  const [cep, setCep] = useState("");
  const [rua, setRua] = useState("");
  const [enderecoNumero, setEnderecoNumero] = useState("");
  const [enderecoComplemento, setEnderecoComplemento] = useState("");
  const [enderecoBairro, setEnderecoBairro] = useState("");
  const [municipioResidencia, setMunicipioResidencia] = useState("");
  const [paisResidencia, setPaisResidencia] = useState("BRASIL");
  const [zonaResidencia, setZonaResidencia] = useState("urbana");
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState("");
  const [pontoReferencia, setPontoReferencia] = useState("");
  const [telefoneResidencial, setTelefoneResidencial] = useState("");
  const [celular, setCelular] = useState("");
  const [telefoneAdicional, setTelefoneAdicional] = useState("");
  const [emailContato, setEmailContato] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const escolaridadeOptions = [
    "Não Informado",
    "Não alfabetizada",
    "Ensino Fundamental Incompleto",
    "Ensino Fundamental Completo",
    "Ensino Médio Incompleto",
    "Ensino Médio Completo",
    "Ensino Superior Incompleto",
    "Ensino Superior Completo",
  ];
  const formatCPF = (value) =>
    value
      .replace(/\D/g, "")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2")
      .substring(0, 14);
  const formatRG = (value) => value.replace(/\D/g, "").substring(0, 15);
  const formatNIS = (value) => value.replace(/\D/g, "").substring(0, 11);
  const formatCarteiraSUS = (value) =>
    value.replace(/\D/g, "").substring(0, 15);
  const formatTelefone = (value) => {
    value = value.replace(/\D/g, "");
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, "($1) $2");
    value = value.replace(/(\d)(\d{4})$/, "$1-$2");
    return value;
  };
  const formatCEP = (value) => {
    value = value.replace(/\D/g, "");
    value = value.replace(/^(\d{5})(\d)/, "$1-$2");
    return value.substring(0, 9);
  };
  const validateCPF = (rawCpf) => {
    let cpfCleaned = rawCpf.replace(/\D/g, "");
    if (cpfCleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cpfCleaned)) return false;
    let sum = 0;
    let remainder;
    for (let i = 1; i <= 9; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(9, 10))) return false;
    sum = 0;
    for (let i = 1; i <= 10; i++) {
      sum = sum + parseInt(cpfCleaned.substring(i - 1, i)) * (12 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cpfCleaned.substring(10, 11))) return false;
    return true;
  };

  const resetForm = () => {
    setCpf("");
    setNomeCompleto("");
    setNomeSocialAfetivo("");
    setSexo("Nao Informado");
    setEstadoCivil("Solteiro(a)");
    setDataNascimento("");
    setNacionalidade("");
    setRaca("Nao Declarada");
    setPovoIndigena("");
    setReligiao("");
    setNaturalidadeCidade("");
    setNaturalidadeEstado("");
    setFalecido("nao");
    setPessoaPai("");
    setTelefonePai("");
    setEscolaridadePai("Nao Informado");
    setProfissaoPai("");
    setPessoaMae("");
    setTelefoneMae("");
    setEscolaridadeMae("Nao Informado");
    setProfissaoMae("");
    setRgNumero("");
    setRgDataEmissao("");
    setRgOrgaoEmissor("");
    setRgEstado("");
    setNisPisPasep("");
    setCarteiraSUS("");
    setCertidaoTipo("Nascimento");
    setCertidaoEstado("");
    setCertidaoCartorio("");
    setCertidaoDataEmissao("");
    setCertidaoNumero("");
    setCertidaoCidade("");
    setPassaporteNumero("");
    setPassaportePaisEmissor("");
    setPassaporteDataEmissao("");
    setCep("");
    setRua("");
    setEnderecoNumero("");
    setEnderecoComplemento("");
    setEnderecoBairro("");
    setMunicipioResidencia("");
    setPaisResidencia("BRASIL");
    setZonaResidencia("urbana");
    setLocalizacaoDiferenciada("");
    setPontoReferencia("");
    setTelefoneResidencial("");
    setCelular("");
    setTelefoneAdicional("");
    setEmailContato("");
    setErrorMessage("");
    setSuccessMessage("");
    setEditingPessoa(null);
    setUserStatus("");
  };

  const filteredPessoas = pessoas.filter(
    (pessoa) =>
      (pessoa.nomeCompleto &&
        pessoa.nomeCompleto.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (pessoa.cpf && pessoa.cpf.includes(searchTerm))
  );

  useEffect(() => {
    if (!loading) {
      if (
        !userData ||
        !(
          userData.funcao &&
          (userData.funcao.toLowerCase() === "administrador" ||
            userData.funcao.toLowerCase() === "secretario")
        )
      ) {
        navigate("/dashboard");
        return;
      }
      const fetchPessoas = async () => {
        try {
          const pessoasCol = collection(db, "pessoas");
          const pessoaSnapshot = await getDocs(pessoasCol);
          const pessoaList = pessoaSnapshot.docs.map((doc) => ({
            id: doc.id,
            ...doc.data(),
          }));
          setPessoas(pessoaList);
        } catch (error) {
          console.error("Erro ao buscar pessoas:", error);
          setErrorMessage("Erro ao carregar lista de pessoas.");
        }
      };
      fetchPessoas();
    }
  }, [loading, userData, navigate]);

  useEffect(() => {
    if (searchTerm.length >= 3) {
      const fetchSuggestions = async () => {
        try {
          const searchLower = searchTerm.toLowerCase();
          const q = query(
            collection(db, "pessoas"),
            where("nomeCompleto", ">=", searchLower.toUpperCase()),
            where("nomeCompleto", "<=", searchLower.toUpperCase() + "\uf8ff"),
            orderBy("nomeCompleto")
          );
          const querySnapshot = await getDocs(q);
          const suggestions = querySnapshot.docs.map((doc) => ({
            id: doc.id,
            ...doc.data(),
          }));
          setPersonSearchSuggestions(suggestions);
        } catch (error) {
          console.error("Erro ao buscar sugestões de pessoas:", error);
          setPersonSearchSuggestions([]);
        }
      };
      const handler = setTimeout(() => {
        fetchSuggestions();
      }, 300);
      return () => clearTimeout(handler);
    } else {
      setPersonSearchSuggestions([]);
    }
  }, [searchTerm]);

  useEffect(() => {
    const checkUserStatus = async () => {
      const cpfCleaned = cpf.replace(/\D/g, "");
      if (cpfCleaned.length === 11 && !editingPessoa) {
        setUserStatus("Verificando...");
        const q = query(
          collection(db, "users"),
          where("cpf", "==", cpfCleaned)
        );
        const querySnapshot = await getDocs(q);
        if (!querySnapshot.empty) {
          setUserStatus("CADASTRADO");
        } else {
          setUserStatus("CADASTRAR");
        }
      } else {
        setUserStatus("");
      }
    };
    const handler = setTimeout(() => {
      checkUserStatus();
    }, 500);
    return () => {
      clearTimeout(handler);
    };
  }, [cpf, editingPessoa]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    const cpfCleaned = cpf.replace(/\D/g, "");
    if (!validateCPF(cpfCleaned)) {
      setErrorMessage("CPF inválido.");
      return;
    }

    if (
      !nomeCompleto ||
      !dataNascimento ||
      !emailContato ||
      !municipioResidencia ||
      !sexo ||
      !estadoCivil ||
      !nacionalidade ||
      !raca ||
      !pessoaMae
    ) {
      setErrorMessage(
        "Todos os campos obrigatórios em Dados Pessoais e Informações Familiares são necessários."
      );
      return;
    }

    const pessoaData = {
      cpf: cpfCleaned,
      nomeCompleto,
      nomeSocialAfetivo,
      sexo,
      estadoCivil,
      dataNascimento,
      nacionalidade,
      raca,
      povoIndigena,
      religiao,
      naturalidadeCidade,
      naturalidadeEstado,
      falecido: falecido === "sim",
      pessoaPai,
      telefonePai,
      escolaridadePai,
      profissaoPai,
      pessoaMae,
      telefoneMae,
      escolaridadeMae,
      profissaoMae,
      rgNumero,
      rgDataEmissao,
      rgOrgaoEmissor,
      rgEstado,
      nisPisPasep,
      carteiraSUS,
      certidaoTipo,
      certidaoEstado,
      certidaoCartorio,
      certidaoDataEmissao,
      certidaoNumero,
      certidaoCidade,
      passaporteNumero,
      passaportePaisEmissor,
      passaporteDataEmissao,
      cep,
      enderecoLogradouro: rua,
      enderecoNumero,
      enderecoComplemento,
      enderecoBairro,
      municipioResidencia,
      paisResidencia,
      zonaResidencia,
      localizacaoDiferenciada,
      pontoReferencia,
      telefoneResidencial,
      celular,
      telefoneAdicional,
      emailContato,
      ultimaAtualizacao: new Date(),
    };

    try {
      if (editingPessoa) {
        const pessoaDocRef = doc(db, "pessoas", editingPessoa.id);
        await updateDoc(pessoaDocRef, pessoaData);
        setSuccessMessage("Pessoa atualizada com sucesso!");
        setPessoas(
          pessoas.map((p) =>
            p.id === editingPessoa.id ? { id: p.id, ...pessoaData } : p
          )
        );
      } else {
        const docRef = await addDoc(collection(db, "pessoas"), {
          ...pessoaData,
          dataCadastro: new Date(),
        });
        setSuccessMessage("Pessoa cadastrada com sucesso!");
        setPessoas([...pessoas, { id: docRef.id, ...pessoaData }]);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar pessoa:", error);
      setErrorMessage("Erro ao salvar dados: " + error.message);
    }
  };

  const handleEdit = (pessoaToEdit) => {
    setEditingPessoa(pessoaToEdit);
    setNomeCompleto(pessoaToEdit.nomeCompleto || "");
    setCpf(pessoaToEdit.cpf || "");
    setNomeSocialAfetivo(pessoaToEdit.nomeSocialAfetivo || "");
    setSexo(pessoaToEdit.sexo || "Nao Informado");
    setEstadoCivil(pessoaToEdit.estadoCivil || "Solteiro(a)");
    setDataNascimento(pessoaToEdit.dataNascimento || "");
    setNacionalidade(pessoaToEdit.nacionalidade || "");
    setRaca(pessoaToEdit.raca || "Nao Declarada");
    setPovoIndigena(pessoaToEdit.povoIndigena || "");
    setReligiao(pessoaToEdit.religiao || "");
    setNaturalidadeCidade(pessoaToEdit.naturalidadeCidade || "");
    setNaturalidadeEstado(pessoaToEdit.naturalidadeEstado || "");
    setFalecido(pessoaToEdit.falecido ? "sim" : "nao");
    setPessoaPai(pessoaToEdit.pessoaPai || "");
    setTelefonePai(pessoaToEdit.telefonePai || "");
    setEscolaridadePai(pessoaToEdit.escolaridadePai || "Nao Informado");
    setProfissaoPai(pessoaToEdit.profissaoPai || "");
    setPessoaMae(pessoaToEdit.pessoaMae || "");
    setTelefoneMae(pessoaToEdit.telefoneMae || "");
    setEscolaridadeMae(pessoaToEdit.escolaridadeMae || "Nao Informado");
    setProfissaoMae(pessoaToEdit.profissaoMae || "");
    setRgNumero(pessoaToEdit.rgNumero || "");
    setRgDataEmissao(pessoaToEdit.rgDataEmissao || "");
    setRgOrgaoEmissor(pessoaToEdit.rgOrgaoEmissor || "");
    setRgEstado(pessoaToEdit.rgEstado || "");
    setNisPisPasep(pessoaToEdit.nisPisPasep || "");
    setCarteiraSUS(pessoaToEdit.carteiraSUS || "");
    setCertidaoTipo(pessoaToEdit.certidaoTipo || "Nascimento");
    setCertidaoEstado(pessoaToEdit.certidaoEstado || "");
    setCertidaoCartorio(pessoaToEdit.certidaoCartorio || "");
    setCertidaoDataEmissao(pessoaToEdit.certidaoDataEmissao || "");
    setCertidaoNumero(pessoaToEdit.certidaoNumero || "");
    setCertidaoCidade(pessoaToEdit.certidaoCidade || "");
    setPassaporteNumero(pessoaToEdit.passaporteNumero || "");
    setPassaportePaisEmissor(pessoaToEdit.passaportePaisEmissor || "");
    setPassaporteDataEmissao(pessoaToEdit.passaporteDataEmissao || "");
    setCep(pessoaToEdit.cep || "");
    setRua(pessoaToEdit.enderecoLogradouro || "");
    setEnderecoNumero(pessoaToEdit.enderecoNumero || "");
    setEnderecoComplemento(pessoaToEdit.enderecoComplemento || "");
    setEnderecoBairro(pessoaToEdit.enderecoBairro || "");
    setMunicipioResidencia(pessoaToEdit.municipioResidencia || "");
    setPaisResidencia(pessoaToEdit.paisResidencia || "BRASIL");
    setZonaResidencia(pessoaToEdit.zonaResidencia || "urbana");
    setLocalizacaoDiferenciada(pessoaToEdit.localizacaoDiferenciada || "");
    setPontoReferencia(pessoaToEdit.pontoReferencia || "");
    setTelefoneResidencial(pessoaToEdit.telefoneResidencial || "");
    setCelular(pessoaToEdit.celular || "");
    setTelefoneAdicional(pessoaToEdit.telefoneAdicional || "");
    setEmailContato(pessoaToEdit.emailContato || "");
    setErrorMessage("");
    setSuccessMessage("");
  };

  const handleDelete = async (pessoaId) => {
    if (
      window.confirm(
        "Tem certeza que deseja excluir esta pessoa? Esta ação não pode ser desfeita."
      )
    ) {
      try {
        await deleteDoc(doc(db, "pessoas", pessoaId));
        setSuccessMessage("Pessoa excluída com sucesso!");
        setPessoas(pessoas.filter((p) => p.id !== pessoaId));
      } catch (error) {
        console.error("Erro ao excluir pessoa:", error);
        setErrorMessage("Erro ao excluir pessoa: " + error.message);
      }
    }
  };

  if (loading) {
    return <div className="p-6 text-center">Carregando...</div>;
  }
  if (
    !userData ||
    !(
      userData.funcao &&
      (userData.funcao.toLowerCase() === "administrador" ||
        userData.funcao.toLowerCase() === "secretario")
    )
  ) {
    return <div className="p-6 text-center text-red-500">Acesso Negado.</div>;
  }

  // ======================= INÍCIO DA ADIÇÃO =======================
  // NOVA FUNÇÃO PARA LIDAR COM A SELEÇÃO DA SUGESTÃO
  const handleSelectSuggestion = (pessoa) => {
    handleEdit(pessoa); // Reutiliza a sua função de edição que já preenche todos os campos
    setSearchTerm(""); // Limpa o termo de busca para esconder a lista de sugestões
  };
  // ======================== FIM DA ADIÇÃO =========================

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-lg mx-auto md:max-w-4xl">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingPessoa ? "Editar Pessoa Cadastrada" : "Cadastrar Nova Pessoa"}
        </h2>

        {errorMessage && (
          <p className="text-red-600 text-sm mb-4 text-center">
            {errorMessage}
          </p>
        )}
        {successMessage && (
          <p className="text-green-600 text-sm mb-4 text-center">
            {successMessage}
          </p>
        )}

        <div className="relative mb-4 max-w-full mx-auto">
          <input
            type="text"
            placeholder="Buscar por nome"
            className="w-full p-2 border border-gray-300 rounded-md"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
          />
          {searchTerm.length >= 3 && personSearchSuggestions.length > 0 && (
            <ul className="absolute z-10 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto mt-1">
              {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
              {/* O onClick agora chama a nova função handleSelectSuggestion */}
              {personSearchSuggestions.map((pessoa) => (
                <li
                  key={pessoa.id}
                  className="p-2 cursor-pointer hover:bg-gray-200"
                  onClick={() => handleSelectSuggestion(pessoa)}
                >
                  {pessoa.nomeCompleto} - {formatCPF(pessoa.cpf)}
                </li>
              ))}
              {/* ======================== FIM DA ALTERAÇÃO ========================= */}
            </ul>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Dados Pessoais
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="nomeCompleto"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nome completo <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="nomeCompleto"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={nomeCompleto}
                  onChange={(e) =>
                    setNomeCompleto(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="cpf"
                  className="block text-sm font-medium text-gray-700"
                >
                  CPF <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="cpf"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatCPF(cpf)}
                  onChange={(e) => setCpf(e.target.value)}
                  maxLength="14"
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label className="block text-sm font-medium text-gray-700">
                  Status do Usuário
                </label>
                <div
                  className={`mt-1 flex items-center justify-center w-full h-10 p-2 border rounded-md text-center font-bold text-sm transition-colors ${userStatus === "CADASTRADO" ? "bg-red-100 text-red-800 border-red-300" : userStatus === "CADASTRAR" ? "bg-green-100 text-green-800 border-green-300" : "bg-gray-100"}`}
                >
                  {userStatus || "-"}
                </div>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="nomeSocialAfetivo"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nome social e/ou afetivo
                </label>
                <input
                  type="text"
                  id="nomeSocialAfetivo"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={nomeSocialAfetivo}
                  onChange={(e) =>
                    setNomeSocialAfetivo(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="sexo"
                  className="block text-sm font-medium text-gray-700"
                >
                  Sexo <span className="text-red-500">*</span>
                </label>
                <select
                  id="sexo"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={sexo}
                  onChange={(e) => setSexo(e.target.value)}
                  required
                  autoComplete="off"
                >
                  <option value="Nao Informado">Não Informado</option>{" "}
                  <option value="Masculino">Masculino</option>{" "}
                  <option value="Feminino">Feminino</option>{" "}
                  <option value="Outro">Outro</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="estadoCivil"
                  className="block text-sm font-medium text-gray-700"
                >
                  Estado civil <span className="text-red-500">*</span>
                </label>
                <select
                  id="estadoCivil"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={estadoCivil}
                  onChange={(e) => setEstadoCivil(e.target.value)}
                  required
                  autoComplete="off"
                >
                  <option value="Solteiro(a)">Solteiro(a)</option>{" "}
                  <option value="Casado(a)">Casado(a)</option>{" "}
                  <option value="Divorciado(a)">Divorciado(a)</option>{" "}
                  <option value="Viúvo(a)">Viúvo(a)</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="dataNascimento"
                  className="block text-sm font-medium text-gray-700"
                >
                  Data de nascimento <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  id="dataNascimento"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={dataNascimento}
                  onChange={(e) => setDataNascimento(e.target.value)}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="nacionalidade"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nacionalidade <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="nacionalidade"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={nacionalidade}
                  onChange={(e) =>
                    setNacionalidade(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="raca"
                  className="block text-sm font-medium text-gray-700"
                >
                  Raça <span className="text-red-500">*</span>
                </label>
                <select
                  id="raca"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={raca}
                  onChange={(e) => setRaca(e.target.value)}
                  required
                  autoComplete="off"
                >
                  <option value="Nao Declarada">Não Declarada</option>{" "}
                  <option value="Branca">Branca</option>{" "}
                  <option value="Preta">Preta</option>{" "}
                  <option value="Parda">Parda</option>{" "}
                  <option value="Amarela">Amarela</option>{" "}
                  <option value="Indígena">Indígena</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="povoIndigena"
                  className="block text-sm font-medium text-gray-700"
                >
                  Povo Indígena
                </label>
                <input
                  type="text"
                  id="povoIndigena"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={povoIndigena}
                  onChange={(e) =>
                    setPovoIndigena(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="religiao"
                  className="block text-sm font-medium text-gray-700"
                >
                  Religião
                </label>
                <input
                  type="text"
                  id="religiao"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={religiao}
                  onChange={(e) => setReligiao(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="naturalidadeCidade"
                  className="block text-sm font-medium text-gray-700"
                >
                  Naturalidade (Cidade) <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="naturalidadeCidade"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={naturalidadeCidade}
                  onChange={(e) =>
                    setNaturalidadeCidade(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="naturalidadeEstado"
                  className="block text-sm font-medium text-gray-700"
                >
                  Naturalidade (UF) <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="naturalidadeEstado"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={naturalidadeEstado}
                  onChange={(e) =>
                    setNaturalidadeEstado(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="falecido"
                  className="block text-sm font-medium text-gray-700"
                >
                  Falecido?
                </label>
                <select
                  id="falecido"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={falecido}
                  onChange={(e) => setFalecido(e.target.value)}
                  autoComplete="off"
                >
                  <option value="nao">Não</option>{" "}
                  <option value="sim">Sim</option>
                </select>
              </div>
            </div>
          </div>
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Informações Familiares
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-3">
                <label
                  htmlFor="pessoaMae"
                  className="block text-sm font-medium text-gray-700"
                >
                  Pessoa Mãe (Nome Completo){" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="pessoaMae"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={pessoaMae}
                  onChange={(e) => setPessoaMae(e.target.value.toUpperCase())}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="telefoneMae"
                  className="block text-sm font-medium text-gray-700"
                >
                  Telefone
                </label>
                <input
                  type="tel"
                  id="telefoneMae"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(telefoneMae)}
                  onChange={(e) => setTelefoneMae(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="escolaridadeMae"
                  className="block text-sm font-medium text-gray-700"
                >
                  Escolaridade da Mãe
                </label>
                <select
                  id="escolaridadeMae"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={escolaridadeMae}
                  onChange={(e) => setEscolaridadeMae(e.target.value)}
                  autoComplete="off"
                >
                  {escolaridadeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="profissaoMae"
                  className="block text-sm font-medium text-gray-700"
                >
                  Profissão da Mãe
                </label>
                <input
                  type="text"
                  id="profissaoMae"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={profissaoMae}
                  onChange={(e) =>
                    setProfissaoMae(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-3">
                <label
                  htmlFor="pessoaPai"
                  className="block text-sm font-medium text-gray-700"
                >
                  Pessoa Pai (Nome Completo)
                </label>
                <input
                  type="text"
                  id="pessoaPai"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={pessoaPai}
                  onChange={(e) => setPessoaPai(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="telefonePai"
                  className="block text-sm font-medium text-gray-700"
                >
                  Telefone
                </label>
                <input
                  type="tel"
                  id="telefonePai"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(telefonePai)}
                  onChange={(e) => setTelefonePai(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="escolaridadePai"
                  className="block text-sm font-medium text-gray-700"
                >
                  Escolaridade do Pai
                </label>
                <select
                  id="escolaridadePai"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={escolaridadePai}
                  onChange={(e) => setEscolaridadePai(e.target.value)}
                  autoComplete="off"
                >
                  {escolaridadeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="profissaoPai"
                  className="block text-sm font-medium text-gray-700"
                >
                  Profissão do Pai
                </label>
                <input
                  type="text"
                  id="profissaoPai"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={profissaoPai}
                  onChange={(e) =>
                    setProfissaoPai(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
            </div>
          </div>
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Documentação
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="rgNumero"
                  className="block text-sm font-medium text-gray-700"
                >
                  RG (Número)
                </label>
                <input
                  type="text"
                  id="rgNumero"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatRG(rgNumero)}
                  onChange={(e) => setRgNumero(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="rgDataEmissao"
                  className="block text-sm font-medium text-gray-700"
                >
                  RG (Data de Emissão)
                </label>
                <input
                  type="date"
                  id="rgDataEmissao"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={rgDataEmissao}
                  onChange={(e) => setRgDataEmissao(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="rgOrgaoEmissor"
                  className="block text-sm font-medium text-gray-700"
                >
                  RG (Órgão Emissor)
                </label>
                <input
                  type="text"
                  id="rgOrgaoEmissor"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={rgOrgaoEmissor}
                  onChange={(e) =>
                    setRgOrgaoEmissor(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="rgEstado"
                  className="block text-sm font-medium text-gray-700"
                >
                  RG (Estado)
                </label>
                <input
                  type="text"
                  id="rgEstado"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={rgEstado}
                  onChange={(e) => setRgEstado(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="nisPisPasep"
                  className="block text-sm font-medium text-gray-700"
                >
                  NIS (PIS/PASEP)
                </label>
                <input
                  type="text"
                  id="nisPisPasep"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatNIS(nisPisPasep)}
                  onChange={(e) => setNisPisPasep(e.target.value)}
                  maxLength="11"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="carteiraSUS"
                  className="block text-sm font-medium text-gray-700"
                >
                  Carteira do SUS
                </label>
                <input
                  type="text"
                  id="carteiraSUS"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatCarteiraSUS(carteiraSUS)}
                  onChange={(e) => setCarteiraSUS(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="col-span-full md:col-span-1">
                  <label
                    htmlFor="certidaoTipo"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Certidão civil <span className="text-red-500">*</span>
                  </label>
                  <select
                    id="certidaoTipo"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={certidaoTipo}
                    onChange={(e) => setCertidaoTipo(e.target.value)}
                    required
                    autoComplete="off"
                  >
                    <option value="Nascimento">Nascimento</option>{" "}
                    <option value="Casamento">Casamento</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-3">
                  <label
                    htmlFor="certidaoNumero"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Número
                  </label>
                  <input
                    type="text"
                    id="certidaoNumero"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={certidaoNumero}
                    onChange={(e) => setCertidaoNumero(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label
                    htmlFor="certidaoDataEmissao"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Data Emissão
                  </label>
                  <input
                    type="date"
                    id="certidaoDataEmissao"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={certidaoDataEmissao}
                    onChange={(e) => setCertidaoDataEmissao(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-3">
                  <label
                    htmlFor="certidaoCartorio"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Cartório
                  </label>
                  <input
                    type="text"
                    id="certidaoCartorio"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={certidaoCartorio}
                    onChange={(e) =>
                      setCertidaoCartorio(e.target.value.toUpperCase())
                    }
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label
                    htmlFor="certidaoCidade"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Certidão (Cidade)
                  </label>
                  <input
                    type="text"
                    id="certidaoCidade"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={certidaoCidade}
                    onChange={(e) =>
                      setCertidaoCidade(e.target.value.toUpperCase())
                    }
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label
                    htmlFor="certidaoEstado"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Certidão (Estado)
                  </label>
                  <input
                    type="text"
                    id="certidaoEstado"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={certidaoEstado}
                    onChange={(e) =>
                      setCertidaoEstado(e.target.value.toUpperCase())
                    }
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="col-span-full md:col-span-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="col-span-full md:col-span-2">
                  <label
                    htmlFor="passaporteNumero"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Passaporte (Número)
                  </label>
                  <input
                    type="text"
                    id="passaporteNumero"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={passaporteNumero}
                    onChange={(e) =>
                      setPassaporteNumero(e.target.value.toUpperCase())
                    }
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label
                    htmlFor="passaporteDataEmissao"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Data Emissão
                  </label>
                  <input
                    type="date"
                    id="passaporteDataEmissao"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={passaporteDataEmissao}
                    onChange={(e) => setPassaporteDataEmissao(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label
                    htmlFor="passaportePaisEmissor"
                    className="block text-sm font-medium text-gray-700"
                  >
                    País Emissor
                  </label>
                  <input
                    type="text"
                    id="passaportePaisEmissor"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                    value={passaportePaisEmissor}
                    onChange={(e) =>
                      setPassaportePaisEmissor(e.target.value.toUpperCase())
                    }
                    autoComplete="off"
                  />
                </div>
              </div>
            </div>
          </div>
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Endereço
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="cep"
                  className="block text-sm font-medium text-gray-700"
                >
                  CEP
                </label>
                <input
                  type="text"
                  id="cep"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatCEP(cep)}
                  onChange={(e) => setCep(e.target.value)}
                  maxLength="9"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-6">
                <label
                  htmlFor="rua"
                  className="block text-sm font-medium text-gray-700"
                >
                  Rua
                </label>
                <input
                  type="text"
                  id="rua"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={rua}
                  onChange={(e) => setRua(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="numero"
                  className="block text-sm font-medium text-gray-700"
                >
                  Número
                </label>
                <input
                  type="text"
                  id="numero"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={enderecoNumero}
                  onChange={(e) => setEnderecoNumero(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="complemento"
                  className="block text-sm font-medium text-gray-700"
                >
                  Complemento
                </label>
                <input
                  type="text"
                  id="complemento"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={enderecoComplemento}
                  onChange={(e) =>
                    setEnderecoComplemento(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4">
                <label
                  htmlFor="bairro"
                  className="block text-sm font-medium text-gray-700"
                >
                  Bairro
                </label>
                <input
                  type="text"
                  id="bairro"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={enderecoBairro}
                  onChange={(e) =>
                    setEnderecoBairro(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4">
                <label
                  htmlFor="municipioResidencia"
                  className="block text-sm font-medium text-gray-700"
                >
                  Município <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="municipioResidencia"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={municipioResidencia}
                  onChange={(e) =>
                    setMunicipioResidencia(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="paisResidencia"
                  className="block text-sm font-medium text-gray-700"
                >
                  País <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="paisResidencia"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={paisResidencia}
                  onChange={(e) =>
                    setPaisResidencia(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="zonaResidencia"
                  className="block text-sm font-medium text-gray-700"
                >
                  Zona de residência
                </label>
                <select
                  id="zonaResidencia"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={zonaResidencia}
                  onChange={(e) => setZonaResidencia(e.target.value)}
                  autoComplete="off"
                >
                  <option value="urbana">Urbana</option>{" "}
                  <option value="rural">Rural</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8">
                <label
                  htmlFor="localizacaoDiferenciada"
                  className="block text-sm font-medium text-gray-700"
                >
                  Localização diferenciada (se aplicável)
                </label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                  autoComplete="off"
                >
                  <option value="">Selecione</option>{" "}
                  <option value="Não está em área de localização diferenciada">
                    Não está em área de localização diferenciada
                  </option>{" "}
                  <option value="Área rural">Área rural</option>{" "}
                  <option value="Área indígena">Área indígena</option>{" "}
                  <option value="Área de assentamento">
                    Área de assentamento
                  </option>{" "}
                  <option value="Área quilombola">Área quilombola</option>{" "}
                  <option value="Área ribeirinha">Área ribeirinha</option>{" "}
                  <option value="Área de comunidade tradicional">
                    Área de comunidade tradicional
                  </option>{" "}
                  <option value="Área de difícil acesso">
                    Área de difícil acesso
                  </option>{" "}
                  <option value="Área de fronteira">Área de fronteira</option>{" "}
                  <option value="Área urbana periférica">
                    Área urbana periférica
                  </option>{" "}
                  <option value="Área de zona de conflito">
                    Área de zona de conflito
                  </option>{" "}
                  <option value="Área de vulnerabilidade social">
                    Área de vulnerabilidade social
                  </option>
                </select>
              </div>
              <div className="col-span-full">
                <label
                  htmlFor="pontoReferencia"
                  className="block text-sm font-medium text-gray-700"
                >
                  Ponto de Referência
                </label>
                <input
                  type="text"
                  id="pontoReferencia"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={pontoReferencia}
                  onChange={(e) =>
                    setPontoReferencia(e.target.value.toUpperCase())
                  }
                  autoComplete="off"
                />
              </div>
            </div>
          </div>
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Contato
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="telefoneResidencial"
                  className="block text-sm font-medium text-gray-700"
                >
                  Telefone residencial
                </label>
                <input
                  type="tel"
                  id="telefoneResidencial"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(telefoneResidencial)}
                  onChange={(e) => setTelefoneResidencial(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="celular"
                  className="block text-sm font-medium text-gray-700"
                >
                  Celular
                </label>
                <input
                  type="tel"
                  id="celular"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(celular)}
                  onChange={(e) => setCelular(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="telefoneAdicional"
                  className="block text-sm font-medium text-gray-700"
                >
                  Telefone adicional
                </label>
                <input
                  type="tel"
                  id="telefoneAdicional"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(telefoneAdicional)}
                  onChange={(e) => setTelefoneAdicional(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="emailContato"
                  className="block text-sm font-medium text-gray-700"
                >
                  E-mail <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  id="emailContato"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={emailContato}
                  onChange={(e) => setEmailContato(e.target.value)}
                  required
                  autoComplete="off"
                />
              </div>
            </div>
          </div>
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingPessoa && (
              <button
                type="button"
                onClick={resetForm}
                className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded"
              >
                Cancelar Edição
              </button>
            )}
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              {editingPessoa ? "Salvar Alterações" : "Cadastrar Pessoa"}
            </button>
          </div>
        </form>
        <hr className="my-8" />
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">
          Lista de Pessoas
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border border-gray-300 rounded-md">
            <thead>
              <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                <th className="py-3 px-6 text-left">Nome Completo</th>
                <th className="py-3 px-6 text-left">CPF</th>
                <th className="py-3 px-6 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="text-gray-600 text-sm font-light">
              {filteredPessoas.map((pessoa) => (
                <tr
                  key={pessoa.id}
                  className="border-b border-gray-200 hover:bg-gray-100"
                >
                  <td className="py-3 px-6 text-left whitespace-nowrap">
                    {pessoa.nomeCompleto}
                  </td>
                  <td className="py-3 px-6 text-left">
                    {formatCPF(pessoa.cpf)}
                  </td>
                  <td className="py-3 px-6 text-center">
                    <div className="flex item-center justify-center space-x-2">
                      <button
                        onClick={() => handleEdit(pessoa)}
                        className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(pessoa.id)}
                        className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs"
                      >
                        Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default PessoaManagementPage;
