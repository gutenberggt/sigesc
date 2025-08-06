import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate, Link } from 'react-router-dom';

import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';

function SchoolManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [editingSchool, setEditingSchool] = useState(null);

  // Estados dos Dados Gerais
  const [nomeEscola, setNomeEscola] = useState('');
  const [integral, setIntegral] = useState('Não'); // Estado para o campo "Integral"
  
  const [tipoEscola, setTipoEscola] = useState('Sede');
  const [escolaPolo, setEscolaPolo] = useState('');
  const [codigoINEP, setCodigoINEP] = useState('');
  const [situacaoFuncionamento, setSituacaoFuncionamento] = useState('Em atividade');
  const [dependenciaAdm, setDependenciaAdm] = useState('Municipal');
  const [orgaoVinculado, setOrgaoVinculado] = useState('Escolha');
  const [regulamentacaoAutorizacao, setRegulamentacaoAutorizacao] = useState('');

  // Estados do Endereço e Localização
  const [rua, setRua] = useState('');
  const [numero, setNumero] = useState('');
  const [complemento, setComplemento] = useState('');
  const [bairro, setBairro] = useState('');
  const [municipio, setMunicipio] = useState('');
  const [cep, setCep] = useState('');
  const [estadoResidencia, setEstadoResidencia] = useState('');
  const [zonaLocalizacao, setZonaLocalizacao] = useState('urbana');
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState('');

  // Estados do Contato
  const [telefoneContato, setTelefoneContato] = useState('');
  const [emailInstitucional, setEmailInstitucional] = useState('');
  const [siteRedeSocial, setSiteRedeSocial] = useState('');

  // Estados da Gestão Escolar
  const [gestores, setGestores] = useState([{ inep: '', nome: '', cargo: 'Selecione' }]);

  // Estados para Níveis de Ensino e Anos/Séries
  const [selectedNiveisEnsino, setSelectedNiveisEnsino] = useState([]);
  const [currentNivelEnsino, setCurrentNivelEnsino] = useState('');
  const [selectedAnosSeries, setSelectedAnosSeries] = useState([]);
  const [currentAnoSerie, setCurrentAnoSerie] = useState('');
  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const formatCEP = (value) => { value = value.replace(/\D/g, ''); value = value.replace(/^(\d{5})(\d)/, '$1-$2'); return value.substring(0, 9); };
  const formatTelefone = (value) => { value = value.replace(/\D/g, ''); if (value.length > 11) value = value.substring(0, 11); value = value.replace(/^(\d{2})(\d)/g, '($1) $2'); value = value.replace(/(\d)(\d{4})$/, '$1-$2'); return value; };
  const handleAddGestor = () => { setGestores([...gestores, { inep: '', nome: '', cargo: 'Selecione' }]); };
  const handleRemoveGestor = (index) => { const newGestores = [...gestores]; newGestores.splice(index, 1); setGestores(newGestores); };
  const handleGestorChange = (index, field, value) => { const newGestores = [...gestores]; newGestores[index][field] = value; setGestores(newGestores); };
  const handleAddNivelEnsino = () => { if (currentNivelEnsino && !selectedNiveisEnsino.includes(currentNivelEnsino)) { setSelectedNiveisEnsino([...selectedNiveisEnsino, currentNivelEnsino]); setCurrentNivelEnsino(''); } };
  const handleRemoveNivelEnsino = (nivelToRemove) => { setSelectedNiveisEnsino(selectedNiveisEnsino.filter(nivel => nivel !== nivelToRemove)); };
  
  useEffect(() => {
    const newAvailableAnosSeries = new Set();
    selectedNiveisEnsino.forEach(nivel => {
      if (seriesAnosEtapasData[nivel]) {
        seriesAnosEtapasData[nivel].forEach(item => {
          newAvailableAnosSeries.add(item);
        });
      }
    });
    setAvailableAnosSeries(Array.from(newAvailableAnosSeries));
  }, [selectedNiveisEnsino]);
  
  const handleAddAnoSerie = () => { if (currentAnoSerie && !selectedAnosSeries.includes(currentAnoSerie)) { setSelectedAnosSeries([...selectedAnosSeries, currentAnoSerie]); setCurrentAnoSerie(''); } };
  const handleRemoveAnoSerie = (anoSerieToRemove) => { setSelectedAnosSeries(selectedAnosSeries.filter(as => as !== anoSerieToRemove)); };

  const resetForm = () => {
    setNomeEscola('');
    setIntegral('Não');
    setTipoEscola('Sede');
    setEscolaPolo('');
    setCodigoINEP('');
    setSituacaoFuncionamento('Em atividade');
    setDependenciaAdm('Municipal');
    setOrgaoVinculado('Escolha');
    setRegulamentacaoAutorizacao('');
    setRua('');
    setNumero('');
    setComplemento('');
    setBairro('');
    setMunicipio('');
    setCep('');
	  setEstadoResidencia('');
    setZonaLocalizacao('urbana');
    setLocalizacaoDiferenciada('');
    setTelefoneContato('');
    setEmailInstitucional('');
    setSiteRedeSocial('');
    setGestores([{ inep: '', nome: '', cargo: 'Selecione' }]);
    setSelectedNiveisEnsino([]);
    setCurrentNivelEnsino('');
    setSelectedAnosSeries([]);
    setCurrentAnoSerie('');
    setAvailableAnosSeries([]);
    setErrorMessage('');
    setSuccessMessage('');
    setEditingSchool(null);
  };

  useEffect(() => {
    if (!loading) {
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }
      const fetchSchools = async () => {
        try {
          const schoolsCol = collection(db, 'schools');
          const allSchoolsSnapshot = await getDocs(schoolsCol);
          let schoolList = allSchoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
          if (userData.funcao.toLowerCase() === 'secretario') {
            const userSchoolsIds = userData.escolasIds || (userData.escolaId ? [userData.escolaId] : []);
            if (userSchoolsIds.length > 0) {
              schoolList = schoolList.filter(school => userSchoolsIds.includes(school.id));
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
    setErrorMessage('');
    setSuccessMessage('');

    if (!nomeEscola || !codigoINEP || !municipio || !emailInstitucional) {
      setErrorMessage('Nome da escola, Código INEP, Município e E-mail institucional são campos obrigatórios.');
      return;
    }
    
    const schoolData = {
      nomeEscola: nomeEscola.toUpperCase(),
      integral: integral,
      tipoEscola,
      escolaPolo: tipoEscola === 'Anexa' ? escolaPolo.toUpperCase() : '',
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
      cep: cep.replace(/\D/g, ''),
      EstadoResidencia: estadoResidencia.toUpperCase(),
      zonaLocalizacao,
      localizacaoDiferenciada,
      telefoneContato: telefoneContato.replace(/\D/g, ''),
      emailInstitucional,
      siteRedeSocial,
      gestores: gestores.map(g => ({ ...g, nome: g.nome.toUpperCase() })),
      niveisEnsino: selectedNiveisEnsino,
      anosSeriesAtendidas: selectedAnosSeries,
      anosLetivosFuncionamento: '',
      ultimaAtualizacao: new Date(),
    };

    try {
      if (editingSchool) {
        const schoolDocRef = doc(db, 'schools', editingSchool.id);
        await updateDoc(schoolDocRef, schoolData);
        setSuccessMessage('Dados da escola atualizados com sucesso!');
        const updatedSchools = schools.map(s => s.id === editingSchool.id ? { id: s.id, ...schoolData } : s);
        setSchools(updatedSchools);
      } else {
        const docRef = await addDoc(collection(db, 'schools'), schoolData);
        setSuccessMessage('Escola cadastrada com sucesso!');
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
    setNomeEscola(school.nomeEscola || '');
    setIntegral(school.integral || 'Não');
    setTipoEscola(school.tipoEscola || 'Sede');
    setEscolaPolo(school.escolaPolo || '');
    setCodigoINEP(school.codigoINEP || '');
    setSituacaoFuncionamento(school.situacaoFuncionamento || 'Em atividade');
    setDependenciaAdm(school.dependenciaAdm || 'Municipal');
    setOrgaoVinculado(school.orgaoVinculado || 'Escolha');
    setRegulamentacaoAutorizacao(school.regulamentacaoAutorizacao || '');
    setRua(school.rua || '');
    setNumero(school.numero || '');
    setComplemento(school.complemento || '');
    setBairro(school.bairro || '');
    setMunicipio(school.municipio || '');
    setCep(school.cep || '');
	  setEstadoResidencia(school.estadoResidencia || '');
    setZonaLocalizacao(school.zonaLocalizacao || 'urbana');
    setLocalizacaoDiferenciada(school.localizacaoDiferenciada || '');
    setTelefoneContato(school.telefoneContato || '');
    setEmailInstitucional(school.emailInstitucional || '');
    setSiteRedeSocial(school.siteRedeSocial || '');
    setGestores(school.gestores && school.gestores.length > 0 ? school.gestores : [{ inep: '', nome: '', cargo: 'Selecione' }]);
    setSelectedNiveisEnsino(school.niveisEnsino || []);
    setSelectedAnosSeries(school.anosSeriesAtendidas || []);
    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleDelete = async (schoolId) => {
    if (window.confirm('Tem certeza que deseja excluir esta escola? Esta ação não pode ser desfeita!')) {
      try {
        await deleteDoc(doc(db, 'schools', schoolId));
        setSuccessMessage('Escola excluída com sucesso!');
        setSchools(schools.filter(school => school.id !== schoolId));
      } catch (error) {
        console.error("Erro ao excluir escola:", error);
        setErrorMessage("Erro ao excluir escola: " + error.message);
      }
    }
  };

  if (loading) return <div className="p-6">Carregando...</div>;
  if (!userData || !(userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) { return <div className="p-6 text-red-500 font-bold">Acesso Negado.</div>; }

  return (
    <div className="w-full">
      <div className="bg-white p-8 rounded-lg shadow-md mx-auto my-6 max-w-lg md:max-w-4xl">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingSchool ? 'Editar Escola' : 'Cadastrar Nova Escola'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Gerais</h3>
              <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
                <div className="col-span-full md:col-span-6">
                  <label htmlFor="nomeEscola" className="block text-sm font-medium text-gray-700">Nome da Escola <span className="text-red-500">*</span></label>
                  <input type="text" id="nomeEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={nomeEscola} onChange={(e) => setNomeEscola(e.target.value.toUpperCase())} required autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-1">
                  <label htmlFor="integral" className="block text-sm font-medium text-gray-700">Integral</label>
                  <select id="integral" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={integral} onChange={(e) => setIntegral(e.target.value)} autoComplete="off">
                    <option value="Não">Não</option>
                    <option value="Sim">Sim</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-1">
                  <label htmlFor="tipoEscola" className="block text-sm font-medium text-gray-700">Tipo</label>
                  <select id="tipoEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={tipoEscola} onChange={(e) => setTipoEscola(e.target.value)} autoComplete="off">
                    <option value="Sede">Sede</option>
                    <option value="Anexa">Anexa</option>
                  </select>
                </div>
                {tipoEscola === 'Anexa' && (
                  <div className="col-span-full md:col-span-8">
                    <label htmlFor="escolaPolo" className="block text-sm font-medium text-gray-700">Nome da Escola Polo <span className="text-red-500">*</span></label>
                    <input type="text" id="escolaPolo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={escolaPolo} onChange={(e) => setEscolaPolo(e.target.value.toUpperCase())} required autoComplete="off" />
                  </div>
                )}
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="codigoINEP" className="block text-sm font-medium text-gray-700">Código INEP <span className="text-red-500">*</span></label>
                  <input type="text" id="codigoINEP" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoINEP} onChange={(e) => setCodigoINEP(e.target.value)} required autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="situacao" className="block text-sm font-medium text-gray-700">Situação</label>
                  <select id="situacaoFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={situacaoFuncionamento} onChange={(e) => setSituacaoFuncionamento(e.target.value)} autoComplete="off">
                    <option value="Escolha">Escolha</option>
                    <option value="Em atividade">Em atividade</option>
                    <option value="Paralisada">Paralisada</option>
                    <option value="Extinta">Extinta</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="dependenciaAdm" className="block text-sm font-medium text-gray-700">Dependência administrativa</label>
                  <select id="dependenciaAdm" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={dependenciaAdm} onChange={(e) => setDependenciaAdm(e.target.value)} autoComplete="off">
                    <option value="Selecione">Selecione</option>
                    <option value="Municipal">Municipal</option>
                    <option value="Estadual">Estadual</option>
                    <option value="Privada">Privada</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor="orgaoVinculado" className="block text-sm font-medium text-gray-700">Órgão vinculado</label>
                  <select id="orgaoVinculado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={orgaoVinculado} onChange={(e) => setOrgaoVinculado(e.target.value)} autoComplete="off">
                    <option value="Escolha">Escolha</option>
                    <option value="Secretaria Municipal de Educação">Secretaria Municipal de Educação</option>
                    <option value="Secretaria Estadual de Educação">Secretaria Estadual de Educação</option>
                  </select>
                </div>
                <div className="col-span-full md:col-span-8">
                  <label htmlFor="regulamentacaoAutorizacao" className="block text-sm font-medium text-gray-700">Regulamentação/autorização</label>
                  <input type="text" id="regulamentacaoAutorizacao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={regulamentacaoAutorizacao} onChange={(e) => setRegulamentacaoAutorizacao(e.target.value)} autoComplete="off" />
                </div>
              </div>
          </div>

          {/* 📍 Endereço e Localização */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">📍Endereço e Localização</h3>
            {/* Grid de 1 para mobile, 8 para desktop */}
            <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
              <div className="col-span-full md:col-span-2">
                <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
                <input type="text" id="cep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCEP(cep)} onChange={(e) => setCep(e.target.value)} maxLength="9" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-5">
                <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
                <input type="text" id="rua" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={rua} onChange={(e) => setRua(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
                <input type="text" id="numero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={numero} onChange={(e) => setNumero(e.target.value)} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
                <input type="text" id="complemento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={complemento} onChange={(e) => setComplemento(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
                <input type="text" id="bairro" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={bairro} onChange={(e) => setBairro(e.target.value.toUpperCase())} autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-4">
                <label htmlFor="municipio" className="block text-sm font-medium text-gray-700">Município <span className="text-red-500">*</span></label>
                <input type="text" id="municipio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={municipio} onChange={(e) => setMunicipio(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="estadoResidencia" className="block text-sm font-medium text-gray-700">Estado <span className="text-red-500">*</span></label>
                <input type="text" id="estadoResidencia" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={estadoResidencia} onChange={(e) => setEstadoResidencia(e.target.value.toUpperCase())} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="zonaLocalizacao" className="block text-sm font-medium text-gray-700">Zona de localização</label>
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
                <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
                <select
                  id="localizacaoDiferenciada"
                  className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                  value={localizacaoDiferenciada}
                  onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
                  autoComplete="off"
                >
                  <option value="">Selecione</option>
                  <option value="Não está em área de localização diferenciada">Não está em área de localização diferenciada</option>
                  <option value="Área rural">Área rural</option>
                  <option value="Área indígena">Área indígena</option>
                  <option value="Área de assentamento">Área de assentamento</option>
                  <option value="Área quilombola">Área quilombola</option>
                  <option value="Área ribeirinha">Área ribeirinha</option>
                  <option value="Área de comunidade tradicional">Área de comunidade tradicional</option>
                  <option value="Área de difícil acesso">Área de difícil acesso</option>
                  <option value="Área de fronteira">Área de fronteira</option>
                  <option value="Área urbana periférica">Área urbana periférica</option>
                  <option value="Área de zona de conflito">Área de zona de conflito</option>
                  <option value="Área de vulnerabilidade social">Área de vulnerabilidade social</option>
                </select>
              </div>
            </div>
          </div>

          {/* ☎️ Contato */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">☎️ Contato</h3>
            {/* Grid de 1 para mobile, 2 para desktop */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="col-span-full md:col-span-1">
                <label htmlFor="telefoneContato" className="block text-sm font-medium text-gray-700">Telefone fixo e/ou celular</label>
                <input type="tel" id="telefoneContato" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneContato)} onChange={(e) => setTelefoneContato(e.target.value)} maxLength="15" autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="emailInstitucional" className="block text-sm font-medium text-gray-700">E-mail institucional <span className="text-red-500">*</span></label>
                <input type="email" id="emailInstitucional" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={emailInstitucional} onChange={(e) => setEmailInstitucional(e.target.value)} required autoComplete="off" />
              </div>
              <div className="col-span-full md:col-span-1">
                <label htmlFor="siteRedeSocial" className="block text-sm font-medium text-gray-700">Site ou blog (se houver)</label>
                <input type="url" id="siteRedeSocial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={siteRedeSocial} onChange={(e) => setSiteRedeSocial(e.target.value)} autoComplete="off" />
              </div>
			  <div className="col-span-full md:col-span-1">
                <label htmlFor="siteRedeSocial" className="block text-sm font-medium text-gray-700">Facebook (se houver)</label>
                <input type="url" id="siteRedeSocial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={siteRedeSocial} onChange={(e) => setSiteRedeSocial(e.target.value)} autoComplete="off" />
              </div>
			  <div className="col-span-full md:col-span-1">
                <label htmlFor="siteRedeSocial" className="block text-sm font-medium text-gray-700">Instagram (se houver)</label>
                <input type="url" id="siteRedeSocial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={siteRedeSocial} onChange={(e) => setSiteRedeSocial(e.target.value)} autoComplete="off" />
              </div>
			  <div className="col-span-full md:col-span-1">
                <label htmlFor="siteRedeSocial" className="block text-sm font-medium text-gray-700">Outra rede social (se houver)</label>
                <input type="url" id="siteRedeSocial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={siteRedeSocial} onChange={(e) => setSiteRedeSocial(e.target.value)} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* 🧑‍🏫 Gestão Escolar */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">🧑‍🏫 Gestão Escolar - Inserir Diretor(a), Vice-diretor(a), Coordenador(a) e Secretário(a)</h3>
            {/* Iterar sobre os gestores */}
            {gestores.map((gestor, index) => (
              <div key={index} className="grid grid-cols-1 md:grid-cols-8 gap-4 mb-4 items-end">
                <div className="col-span-full md:col-span-1">
                  <label htmlFor={`gestor-inep-${index}`} className="block text-sm font-medium text-gray-700">INEP</label>
                  <input type="text" id={`gestor-inep-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.inep} onChange={(e) => handleGestorChange(index, 'inep', e.target.value)} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-4">
                  <label htmlFor={`gestor-nome-${index}`} className="block text-sm font-medium text-gray-700">Nome do(a) gestor(a)</label>
                  <input type="text" id={`gestor-nome-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.nome} onChange={(e) => handleGestorChange(index, 'nome', e.target.value.toUpperCase())} autoComplete="off" />
                </div>
                <div className="col-span-full md:col-span-2">
                  <label htmlFor={`gestor-cargo-${index}`} className="block text-sm font-medium text-gray-700">Cargo</label>
                  <select id={`gestor-cargo-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.cargo} onChange={(e) => handleGestorChange(index, 'cargo', e.target.value)} autoComplete="off">
                    <option value="Selecione">Selecione</option>
                    <option value="Diretor(a)">Diretor(a)</option>
					<option value="Diretor(a)">Vice-diretor(a)</option>
                    <option value="Coordenador(a)">Coordenador(a)</option>
                    <option value="Secretario(a)">Secretário(a)</option>
                  </select>
                </div>
                {gestores.length > 1 && (
                  <button
                  type="button"
                  onClick={() => handleRemoveGestor(index)}
                  className="flex items-center justify-center w-8 h-8 rounded-full bg-red-600 text-white hover:bg-red-700 transition duration-200"
                  title="Remover gestor"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>

                )}
              </div>
            ))}
            <button type="button" onClick={handleAddGestor} className="flex items-center text-green-600 hover:text-green-800 font-semibold text-sm mt-2">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-1">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              ADICIONAR NOVO
            </button>
          </div>

          {/* 🎓 Oferta de Ensino (Atualizado) */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">🎓 Oferta de Ensino</h3>
            <div className="grid grid-cols-1 gap-4">
              {/* Níveis de Ensino Ofertados */}
              <div className="col-span-full md:col-span-1">
                <label htmlFor="niveisEnsino" className="block text-sm font-medium text-gray-700">Níveis de ensino ofertados <span className="text-red-500">*</span></label>
                <div className="flex items-center space-x-2 mt-1">
                  <select
                    id="niveisEnsino"
                    className="block w-full p-2 border border-gray-300 rounded-md"
                    value={currentNivelEnsino}
                    onChange={(e) => setCurrentNivelEnsino(e.target.value)}
                    autoComplete="off"
                  >
                    <option value="">Selecione um nível</option>
                    {niveisDeEnsinoList.map((nivel, index) => (
                      <option key={index} value={nivel}>{nivel}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={handleAddNivelEnsino}
                    className="flex items-center justify-center w-10 h-10 rounded-full bg-green-600 text-white hover:bg-green-700 transition duration-200"
                    title="Adicionar Nível de Ensino"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                  </button>
                </div>
                {selectedNiveisEnsino.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {selectedNiveisEnsino.map((nivel, index) => (
                      <li key={index} className="flex items-center justify-between bg-gray-50 p-2 rounded-md border border-gray-200">
                        {nivel}
                        <button
                          type="button"
                          onClick={() => handleRemoveNivelEnsino(nivel)}
                          className="text-red-500 hover:text-red-700 ml-2"
                          title="Remover"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Anos/Séries Atendidas */}
              <div className="col-span-full md:col-span-1">
                <label htmlFor="anosSeriesAtendidas" className="block text-sm font-medium text-gray-700">Anos/séries atendidas <span className="text-red-500">*</span></label>
                <div className="flex items-center space-x-2 mt-1">
                  <select
                    id="anosSeriesAtendidas"
                    className="block w-full p-2 border border-gray-300 rounded-md"
                    value={currentAnoSerie}
                    onChange={(e) => setCurrentAnoSerie(e.target.value)}
                    disabled={selectedNiveisEnsino.length === 0}
                    autoComplete="off"
                  >
                    <option value="">Selecione um ano/série</option>
                    {availableAnosSeries.length > 0 ? (
                      availableAnosSeries.map((anoSerie, index) => (
                        <option key={index} value={anoSerie}>{anoSerie}</option>
                      ))
                    ) : (
                      <option value="" disabled>Selecione um Nível de Ensino primeiro</option>
                    )}
                  </select>
                  <button
                    type="button"
                    onClick={handleAddAnoSerie}
                    className="flex items-center justify-center w-10 h-10 rounded-full bg-green-600 text-white hover:bg-green-700 transition duration-200"
                    title="Adicionar Ano/Série"
                    disabled={selectedNiveisEnsino.length === 0 || !currentAnoSerie}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                  </button>
                </div>
                {selectedAnosSeries.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {selectedAnosSeries.map((anoSerie, index) => (
                      <li key={index} className="flex items-center justify-between bg-gray-50 p-2 rounded-md border border-gray-200">
                        {anoSerie}
                        <button
                          type="button"
                          onClick={() => handleRemoveAnoSerie(anoSerie)}
                          className="text-red-500 hover:text-red-700 ml-2"
                          title="Remover"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="col-span-full md:col-span-2">
                <label htmlFor="anosLetivosFuncionamento" className="block text-sm font-medium text-gray-700">Anos letivos em funcionamento com este sistema</label>
                <input type="text" id="anosLetivosFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="Ex: 2025, 2026" value={''} onChange={() => {}} autoComplete="off" />
              </div>
            </div>
          </div>

          {/* Botões de Ação */}
          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingSchool && (
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
              {editingSchool ? 'Salvar Alterações' : 'Cadastrar Escola'}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        {/* Tabela de Escolas Existentes */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Escolas</h3>
        {schools.length === 0 ? (
          <p className="text-center text-gray-600">Nenhuma escola cadastrada ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome da Escola</th>
                  <th className="py-3 px-6 text-left">Código INEP</th>
                  <th className="py-3 px-6 text-left">Município</th>
                  <th className="py-3 px-6 text-left">Situação</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {schools.map((school) => (
                  <tr key={school.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{school.nomeEscola}</td>
                    <td className="py-3 px-6 text-left">{school.codigoINEP}</td>
                    <td className="py-3 px-6 text-left">{school.municipio}</td>
                    <td className="py-3 px-6 text-left">{school.situacaoFuncionamento || 'N/A'}</td>
                    <td className="py-3 px-6 text-center">
                      <div className="flex item-center justify-center space-x-2">
                        <button onClick={() => handleEdit(school)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">
                          Editar
                        </button>
                        <button onClick={() => handleDelete(school.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">
                          Excluir
                        </button>
                        {/* NOVO BOTÃO: Gerenciar Turmas */}
                        <Link
                          to={`/dashboard/escola/turmas/${school.id}`}
                          className="bg-purple-600 hover:bg-purple-700 text-white p-2 rounded-full text-xs"
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
        )}
      </div>
    </div>
  );
}

export default SchoolManagementPage;