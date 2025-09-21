import React, { useState, useEffect } from "react";
import { db } from "../firebase/config";
import {
  collection,
  addDoc,
  getDocs,
  doc,
  updateDoc,
  deleteDoc,
} from "firebase/firestore";
import { useUser } from "../context/UserContext";
import { useNavigate, Link } from "react-router-dom";
import {
  niveisDeEnsinoList,
  seriesAnosEtapasData,
} from "../data/ensinoConstants";

function SchoolManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [editingSchool, setEditingSchool] = useState(null);

  // Estados dos Dados Gerais
  const [nomeEscola, setNomeEscola] = useState("");
  const [integral, setIntegral] = useState("Não");
  const [tipoEscola, setTipoEscola] = useState("Sede");
  const [escolaPolo, setEscolaPolo] = useState("");
  const [codigoINEP, setCodigoINEP] = useState("");
  const [situacaoFuncionamento, setSituacaoFuncionamento] = useState("Ativa");
  const [dependenciaAdm, setDependenciaAdm] = useState("Municipal");
  const [orgaoVinculado, setOrgaoVinculado] = useState(
    "Secretaria Municipal de Educação"
  );
  const [regulamentacaoAutorizacao, setRegulamentacaoAutorizacao] =
    useState("");

  // Estados do Endereço e Localização
  const [rua, setRua] = useState("");
  const [numero, setNumero] = useState("");
  const [complemento, setComplemento] = useState("");
  const [bairro, setBairro] = useState("");
  const [municipio, setMunicipio] = useState("FLORESTA DO ARAGUAIA");
  const [cep, setCep] = useState("68543-000");
  const [estadoResidencia, setEstadoResidencia] = useState("PARÁ");
  const [zonaLocalizacao, setZonaLocalizacao] = useState("urbana");
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState(
    "Não está em área de localização diferenciada"
  );

  // Estados do Contato
  const [telefoneContato, setTelefoneContato] = useState("");
  const [emailInstitucional, setEmailInstitucional] = useState("");
  const [siteRedeSocial, setSiteRedeSocial] = useState("");

  // Estados da Gestão Escolar
  const [gestores, setGestores] = useState([
    { inep: "", nome: "", cargo: "Selecione" },
  ]);

  // Estados para Níveis de Ensino e Anos/Séries
  const [selectedNiveisEnsino, setSelectedNiveisEnsino] = useState([]);
  const [currentNivelEnsino, setCurrentNivelEnsino] = useState("");
  const [selectedAnosSeries, setSelectedAnosSeries] = useState([]);
  const [currentAnoSerie, setCurrentAnoSerie] = useState("");
  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const formatCEP = (value) => {
    value = value.replace(/\D/g, "");
    value = value.replace(/^(\d{5})(\d)/, "$1-$2");
    return value.substring(0, 9);
  };
  const formatTelefone = (value) => {
    value = value.replace(/\D/g, "");
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, "($1) $2");
    value = value.replace(/(\d)(\d{4})$/, "$1-$2");
    return value;
  };
  const handleAddGestor = () => {
    setGestores([...gestores, { inep: "", nome: "", cargo: "Selecione" }]);
  };
  const handleRemoveGestor = (index) => {
    const newGestores = [...gestores];
    newGestores.splice(index, 1);
    setGestores(newGestores);
  };
  const handleGestorChange = (index, field, value) => {
    const newGestores = [...gestores];
    newGestores[index][field] = value;
    setGestores(newGestores);
  };
  const handleAddNivelEnsino = () => {
    if (
      currentNivelEnsino &&
      !selectedNiveisEnsino.includes(currentNivelEnsino)
    ) {
      setSelectedNiveisEnsino([...selectedNiveisEnsino, currentNivelEnsino]);
      setCurrentNivelEnsino("");
    }
  };
  const handleRemoveNivelEnsino = (nivelToRemove) => {
    setSelectedNiveisEnsino(
      selectedNiveisEnsino.filter((nivel) => nivel !== nivelToRemove)
    );
  };

  useEffect(() => {
    const newAvailableAnosSeries = new Set();
    selectedNiveisEnsino.forEach((nivel) => {
      if (seriesAnosEtapasData[nivel]) {
        seriesAnosEtapasData[nivel].forEach((item) => {
          newAvailableAnosSeries.add(item);
        });
      }
    });
    setAvailableAnosSeries(Array.from(newAvailableAnosSeries));
  }, [selectedNiveisEnsino]);

  const handleAddAnoSerie = () => {
    if (currentAnoSerie && !selectedAnosSeries.includes(currentAnoSerie)) {
      setSelectedAnosSeries([...selectedAnosSeries, currentAnoSerie]);
      setCurrentAnoSerie("");
    }
  };
  const handleRemoveAnoSerie = (anoSerieToRemove) => {
    setSelectedAnosSeries(
      selectedAnosSeries.filter((as) => as !== anoSerieToRemove)
    );
  };

  const resetForm = () => {
    setNomeEscola("");
    setIntegral("Não");
    setTipoEscola("Sede");
    setEscolaPolo("");
    setCodigoINEP("");
    setSituacaoFuncionamento("Ativa");
    setDependenciaAdm("Municipal");
    setOrgaoVinculado("Secretaria Municipal de educação");
    setRegulamentacaoAutorizacao("");
    setRua("");
    setNumero("");
    setComplemento("");
    setBairro("");
    setMunicipio("");
    setCep("");
    setEstadoResidencia("");
    setZonaLocalizacao("urbana");
    setLocalizacaoDiferenciada("");
    setTelefoneContato("");
    setEmailInstitucional("");
    setSiteRedeSocial("");
    setGestores([{ inep: "", nome: "", cargo: "Selecione" }]);
    setSelectedNiveisEnsino([]);
    setCurrentNivelEnsino("");
    setSelectedAnosSeries([]);
    setCurrentAnoSerie("");
    setAvailableAnosSeries([]);
    setErrorMessage("");
    setSuccessMessage("");
    setEditingSchool(null);
  };

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
      const fetchSchools = async () => {
        try {
          const schoolsCol = collection(db, "schools");
          const allSchoolsSnapshot = await getDocs(schoolsCol);
          let schoolList = allSchoolsSnapshot.docs.map((doc) => ({
            id: doc.id,
            ...doc.data(),
          }));
          if (userData.funcao.toLowerCase() === "secretario") {
            const userSchoolsIds =
              userData.escolasIds ||
              (userData.escolaId ? [userData.escolaId] : []);
            if (userSchoolsIds.length > 0) {
              schoolList = schoolList.filter((school) =>
                userSchoolsIds.includes(school.id)
              );
            } else {
              setErrorMessage("Secretário não associado a nenhuma escola.");
              schoolList = [];
            }
          }
          setSchools(schoolList);
        } catch (error) {
          console.error("Erro ao buscar escolas:", error);
          setErrorMessage("Erro ao carregar lista de escolas.");
        }
      };
      fetchSchools();
    }
  }, [loading, userData, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");

    if (!nomeEscola || !codigoINEP || !municipio || !emailInstitucional) {
      setErrorMessage(
        "Nome da escola, Código INEP, Município e E-mail institucional são campos obrigatórios."
      );
      return;
    }

    const schoolData = {
      nomeEscola: nomeEscola.toUpperCase(),
      integral,
      tipoEscola,
      escolaPolo: tipoEscola === "Anexa" ? escolaPolo.toUpperCase() : "",
      codigoINEP,
      situacaoFuncionamento,
      dependenciaAdm,
      orgaoVinculado,
      regulamentacaoAutorizacao: regulamentacaoAutorizacao.toUpperCase(),
      rua: rua.toUpperCase(),
      numero,
      complemento: complemento.toUpperCase(),
      bairro: bairro.toUpperCase(),
      municipio: municipio.toUpperCase(),
      cep: cep.replace(/\D/g, ""),
      EstadoResidencia: estadoResidencia.toUpperCase(),
      zonaLocalizacao,
      localizacaoDiferenciada,
      telefoneContato: telefoneContato.replace(/\D/g, ""),
      emailInstitucional,
      siteRedeSocial,
      gestores: gestores.map((g) => ({ ...g, nome: g.nome.toUpperCase() })),
      niveisEnsino: selectedNiveisEnsino,
      anosSeriesAtendidas: selectedAnosSeries,
      anosLetivosFuncionamento: "",
      ultimaAtualizacao: new Date(),
    };

    try {
      if (editingSchool) {
        const schoolDocRef = doc(db, "schools", editingSchool.id);
        await updateDoc(schoolDocRef, schoolData);
        setSuccessMessage("Dados da escola atualizados com sucesso!");
        const updatedSchools = schools.map((s) =>
          s.id === editingSchool.id ? { id: s.id, ...schoolData } : s
        );
        setSchools(updatedSchools);
      } else {
        const docRef = await addDoc(collection(db, "schools"), schoolData);
        setSuccessMessage("Escola cadastrada com sucesso!");
        setSchools([...schools, { id: docRef.id, ...schoolData }]);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar escola:", error);
      setErrorMessage("Erro ao salvar dados da escola: " + error.message);
    }
  };

  const handleEdit = (school) => {
    setEditingSchool(school);
    setNomeEscola(school.nomeEscola || "");
    setIntegral(school.integral || "Não");
    setTipoEscola(school.tipoEscola || "Sede");
    setEscolaPolo(school.escolaPolo || "");
    setCodigoINEP(school.codigoINEP || "");
    setSituacaoFuncionamento(school.situacaoFuncionamento || "Ativa");
    setDependenciaAdm(school.dependenciaAdm || "Municipal");
    setOrgaoVinculado(
      school.orgaoVinculado || "Secretaria Municipal de Educação"
    );
    setRegulamentacaoAutorizacao(school.regulamentacaoAutorizacao || "");
    setRua(school.rua || "");
    setNumero(school.numero || "");
    setComplemento(school.complemento || "");
    setBairro(school.bairro || "");
    setMunicipio(school.municipio || "");
    setCep(school.cep || "");
    setEstadoResidencia(school.EstadoResidencia || "");
    setZonaLocalizacao(school.zonaLocalizacao || "urbana");
    setLocalizacaoDiferenciada(school.localizacaoDiferenciada || "");
    setTelefoneContato(school.telefoneContato || "");
    setEmailInstitucional(school.emailInstitucional || "");
    setSiteRedeSocial(school.siteRedeSocial || "");
    setGestores(
      school.gestores && school.gestores.length > 0
        ? school.gestores
        : [{ inep: "", nome: "", cargo: "Selecione" }]
    );
    setSelectedNiveisEnsino(school.niveisEnsino || []);
    setSelectedAnosSeries(school.anosSeriesAtendidas || []);
    setErrorMessage("");
    setSuccessMessage("");
  };

  const handleDelete = async (schoolId) => {
    if (
      window.confirm(
        "Tem certeza que deseja excluir esta escola? Esta ação não pode ser desfeita!"
      )
    ) {
      try {
        await deleteDoc(doc(db, "schools", schoolId));
        setSuccessMessage("Escola excluída com sucesso!");
        setSchools(schools.filter((school) => school.id !== schoolId));
      } catch (error) {
        console.error("Erro ao excluir escola:", error);
        setErrorMessage("Erro ao excluir escola: " + error.message);
      }
    }
  };

  if (loading) return <div className="p-6">Carregando...</div>;
  if (
    !userData ||
    !(
      userData.funcao.toLowerCase() === "administrador" ||
      userData.funcao.toLowerCase() === "secretario"
    )
  ) {
    return <div className="p-6 text-red-500 font-bold">Acesso Negado.</div>;
  }

  return (
    <div className="w-full">
      <div className="bg-white p-8 rounded-lg shadow-md mx-auto my-6 max-w-lg md:max-w-4xl">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingSchool ? "Editar Escola" : "Cadastrar Nova Escola"}
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

        <form
          onSubmit={handleSubmit}
          className="grid grid-cols-1 md:grid-cols-2 gap-4"
        >
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              Dados Gerais
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-6">
                <label
                  htmlFor="nomeEscola"
                  className="block text-sm font-medium text-gray-700"
                >
                  Nome da Escola <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="nomeEscola"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={nomeEscola}
                  onChange={(e) => setNomeEscola(e.target.value.toUpperCase())}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="integral"
                  className="block text-sm font-medium text-gray-700"
                >
                  Integral
                </label>
                <select
                  id="integral"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={integral}
                  onChange={(e) => setIntegral(e.target.value)}
                  autoComplete="off"
                >
                  <option value="Não">Não</option>
                  <option value="Sim">Sim</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="tipoEscola"
                  className="block text-sm font-medium text-gray-700"
                >
                  Tipo
                </label>
                <select
                  id="tipoEscola"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={tipoEscola}
                  onChange={(e) => setTipoEscola(e.target.value)}
                  autoComplete="off"
                >
                  <option value="Sede">Sede</option>
                  <option value="Anexa">Anexa</option>
                </select>
              </div>
              {tipoEscola === "Anexa" && (
                <div className="col-span-full md:col-span-8">
                  <label
                    htmlFor="escolaPolo"
                    className="block text-sm font-medium text-gray-700"
                  >
                    Nome da Escola Polo <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    id="escolaPolo"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={escolaPolo}
                    onChange={(e) =>
                      setEscolaPolo(e.target.value.toUpperCase())
                    }
                    required
                    autoComplete="off"
                  />
                </div>
              )}
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="codigoINEP"
                  className="block text-sm font-medium text-gray-700"
                >
                  Código INEP <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="codigoINEP"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={codigoINEP}
                  onChange={(e) => setCodigoINEP(e.target.value)}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="situacaoFuncionamento"
                  className="block text-sm font-medium text-gray-700"
                >
                  Situação
                </label>
                <select
                  id="situacaoFuncionamento"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={situacaoFuncionamento}
                  onChange={(e) => setSituacaoFuncionamento(e.target.value)}
                  autoComplete="off"
                >
                  <option value="Ativa">Ativa</option>
                  <option value="Paralisada">Paralisada</option>
                  <option value="Extinta">Extinta</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="dependenciaAdm"
                  className="block text-sm font-medium text-gray-700"
                >
                  Dependência administrativa
                </label>
                <select
                  id="dependenciaAdm"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={dependenciaAdm}
                  onChange={(e) => setDependenciaAdm(e.target.value)}
                  autoComplete="off"
                >
                  <option value="Selecione">Selecione</option>
                  <option value="Municipal">Municipal</option>
                  <option value="Estadual">Estadual</option>
                  <option value="Privada">Privada</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="orgaoVinculado"
                  className="block text-sm font-medium text-gray-700"
                >
                  Órgão vinculado
                </label>
                <select
                  id="orgaoVinculado"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={orgaoVinculado}
                  onChange={(e) => setOrgaoVinculado(e.target.value)}
                  autoComplete="off"
                >
                  <option value="Secretaria Municipal de Educação">
                    Secretaria Municipal de Educação
                  </option>
                  <option value="Secretaria Estadual de Educação">
                    Secretaria Estadual de Educação
                  </option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8">
                <label
                  htmlFor="regulamentacaoAutorizacao"
                  className="block text-sm font-medium text-gray-700"
                >
                  Regulamentação/autorização
                </label>
                <input
                  type="text"
                  id="regulamentacaoAutorizacao"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={regulamentacaoAutorizacao}
                  onChange={(e) => setRegulamentacaoAutorizacao(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>
          </div>

          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              📍Endereço e Localização
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
              <div className="col-span-full md:col-span-5">
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
              <div className="col-span-full md:col-span-1">
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
                  value={numero}
                  onChange={(e) => setNumero(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4">
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
                  value={complemento}
                  onChange={(e) => setComplemento(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4">
                <label
                  htmlFor="bairro"
                  className="block text-sm font-medium text-gray-700"
                >
                  Bairro / Vila / Distrito
                </label>
                <input
                  type="text"
                  id="bairro"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={bairro}
                  onChange={(e) => setBairro(e.target.value.toUpperCase())}
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-4">
                <label
                  htmlFor="municipio"
                  className="block text-sm font-medium text-gray-700"
                >
                  Município <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="municipio"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={municipio}
                  onChange={(e) => setMunicipio(e.target.value.toUpperCase())}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="estadoResidencia"
                  className="block text-sm font-medium text-gray-700"
                >
                  Estado <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="estadoResidencia"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase"
                  value={estadoResidencia}
                  onChange={(e) =>
                    setEstadoResidencia(e.target.value.toUpperCase())
                  }
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-2">
                <label
                  htmlFor="zonaLocalizacao"
                  className="block text-sm font-medium text-gray-700"
                >
                  Zona de localização
                </label>
                <select
                  id="zonaLocalizacao"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={zonaLocalizacao}
                  onChange={(e) => setZonaLocalizacao(e.target.value)}
                  autoComplete="off"
                >
                  <option value="urbana">Urbana</option>
                  <option value="rural">Rural</option>
                </select>
              </div>
              <div className="col-span-full md:col-span-8">
                <label
                  htmlFor="localizacaoDiferenciada"
                  className="block text-sm font-medium text-gray-700"
                >
                  Localização diferenciada
                </label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                  autoComplete="off"
                >
                  <option value="">Selecione</option>
                  <option value="Não está em área de localização diferenciada">
                    Não está em área de localização diferenciada
                  </option>
                </select>
              </div>
            </div>
          </div>

          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              ☎️ Contato
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="telefoneContato"
                  className="block text-sm font-medium text-gray-700"
                >
                  Telefone
                </label>
                <input
                  type="tel"
                  id="telefoneContato"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={formatTelefone(telefoneContato)}
                  onChange={(e) => setTelefoneContato(e.target.value)}
                  maxLength="15"
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full md:col-span-1">
                <label
                  htmlFor="emailInstitucional"
                  className="block text-sm font-medium text-gray-700"
                >
                  E-mail institucional <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  id="emailInstitucional"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={emailInstitucional}
                  onChange={(e) => setEmailInstitucional(e.target.value)}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="col-span-full">
                <label
                  htmlFor="siteRedeSocial"
                  className="block text-sm font-medium text-gray-700"
                >
                  Site ou Rede Social
                </label>
                <input
                  type="url"
                  id="siteRedeSocial"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={siteRedeSocial}
                  onChange={(e) => setSiteRedeSocial(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>
          </div>

          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              🧑‍🏫 Gestão Escolar
            </h3>
            {gestores.map((gestor, index) => (
              <div
                key={index}
                className="grid grid-cols-1 md:grid-cols-8 gap-4 mb-4 items-end"
              >
                <div className="col-span-full md:col-span-1">
                  {/* CORREÇÃO: Adicionado htmlFor */}
                  <label htmlFor={`gestor-inep-${index}`}>INEP</label>
                  <input
                    id={`gestor-inep-${index}`} // CORREÇÃO: Adicionado id
                    type="text"
                    value={gestor.inep}
                    onChange={(e) =>
                      handleGestorChange(index, "inep", e.target.value)
                    }
                    className="w-full p-2 border rounded"
                  />
                </div>
                <div className="col-span-full md:col-span-4">
                  {/* CORREÇÃO: Adicionado htmlFor */}
                  <label htmlFor={`gestor-nome-${index}`}>Nome</label>
                  <input
                    id={`gestor-nome-${index}`} // CORREÇÃO: Adicionado id
                    type="text"
                    value={gestor.nome}
                    onChange={(e) =>
                      handleGestorChange(
                        index,
                        "nome",
                        e.target.value.toUpperCase()
                      )
                    }
                    className="w-full p-2 border rounded"
                  />
                </div>
                <div className="col-span-full md:col-span-2">
                  {/* CORREÇÃO: Adicionado htmlFor */}
                  <label htmlFor={`gestor-cargo-${index}`}>Cargo</label>
                  <select
                    id={`gestor-cargo-${index}`} // CORREÇÃO: Adicionado id
                    value={gestor.cargo}
                    onChange={(e) =>
                      handleGestorChange(index, "cargo", e.target.value)
                    }
                    className="w-full p-2 border rounded"
                  >
                    <option>Selecione</option>
                    <option>Diretor(a)</option>
                    <option>Vice-diretor(a)</option>
                    <option>Coordenador(a)</option>
                    <option>Secretário(a)</option>
                  </select>
                </div>
                {gestores.length > 1 && (
                  <button
                    type="button"
                    onClick={() => handleRemoveGestor(index)}
                    className="bg-red-500 text-white p-2 rounded"
                  >
                    -
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={handleAddGestor}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              + Adicionar Gestor
            </button>
          </div>

          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">
              🎓 Oferta de Ensino
            </h3>
            <div>
              {/* CORREÇÃO: Adicionado htmlFor */}
              <label htmlFor="currentNivelEnsino">
                Níveis de ensino <span className="text-red-500">*</span>
              </label>
              <div className="flex">
                <select
                  id="currentNivelEnsino" // CORREÇÃO: Adicionado id
                  value={currentNivelEnsino}
                  onChange={(e) => setCurrentNivelEnsino(e.target.value)}
                  className="w-full p-2 border rounded-l"
                >
                  <option value="">Selecione</option>
                  {niveisDeEnsinoList.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAddNivelEnsino}
                  className="bg-blue-500 text-white p-2 rounded-r"
                >
                  +
                </button>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {selectedNiveisEnsino.map((n) => (
                  <span
                    key={n}
                    className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full"
                  >
                    {n}{" "}
                    <button
                      onClick={() => handleRemoveNivelEnsino(n)}
                      className="ml-1 text-red-500"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-4">
              {/* CORREÇÃO: Adicionado htmlFor */}
              <label htmlFor="currentAnoSerie">
                Anos/séries atendidas <span className="text-red-500">*</span>
              </label>
              <div className="flex">
                <select
                  id="currentAnoSerie" // CORREÇÃO: Adicionado id
                  value={currentAnoSerie}
                  onChange={(e) => setCurrentAnoSerie(e.target.value)}
                  className="w-full p-2 border rounded-l"
                  disabled={selectedNiveisEnsino.length === 0}
                >
                  <option value="">Selecione</option>
                  {availableAnosSeries.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAddAnoSerie}
                  className="bg-blue-500 text-white p-2 rounded-r"
                  disabled={!currentAnoSerie}
                >
                  +
                </button>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {selectedAnosSeries.map((s) => (
                  <span
                    key={s}
                    className="bg-green-100 text-green-800 px-2 py-1 rounded-full"
                  >
                    {s}{" "}
                    <button
                      onClick={() => handleRemoveAnoSerie(s)}
                      className="ml-1 text-red-500"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingSchool && (
              <button
                type="button"
                onClick={resetForm}
                className="bg-gray-300 text-gray-800 font-bold py-2 px-4 rounded"
              >
                Cancelar Edição
              </button>
            )}
            <button
              type="submit"
              className="bg-blue-600 text-white font-bold py-2 px-4 rounded"
            >
              {editingSchool ? "Salvar Alterações" : "Cadastrar Escola"}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">
          Lista de Escolas
        </h3>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border">
            <thead>
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm leading-normal">
                <th className="py-3 px-6 text-left">Nome da Escola</th>
                <th className="py-3 px-6 text-left">Código INEP</th>
                <th className="py-3 px-6 text-left">Situação</th>
                <th className="py-3 px-6 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="text-gray-600 text-sm font-light">
              {schools.map((school) => (
                <tr
                  key={school.id}
                  className="border-b border-gray-200 hover:bg-gray-100"
                >
                  <td className="py-3 px-6 text-left whitespace-nowrap">
                    {school.nomeEscola}
                  </td>
                  <td className="py-3 px-6 text-left">{school.codigoINEP}</td>
                  <td className="py-3 px-6 text-left">
                    {school.situacaoFuncionamento || "N/A"}
                  </td>
                  <td className="py-3 px-6 text-center">
                    <div className="flex item-center justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleEdit(school)}
                        className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-1 px-3 rounded text-xs"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(school.id)}
                        className="bg-red-500 hover:bg-red-700 text-white font-bold py-1 px-3 rounded text-xs"
                      >
                        Excluir
                      </button>
                      <Link
                        to={`/dashboard/escola/turmas/${school.id}`}
                        className="bg-purple-500 hover:bg-purple-700 text-white font-bold py-1 px-3 rounded text-xs inline-block"
                      >
                        Turmas
                      </Link>
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

export default SchoolManagementPage;
