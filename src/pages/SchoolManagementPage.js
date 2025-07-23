import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

// Importar os dados dos níveis de ensino e séries/anos/etapas
import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';

function SchoolManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [editingSchool, setEditingSchool] = useState(null);

  // Estados dos Dados Gerais
  const [nomeEscola, setNomeEscola] = useState('');
  const [sigla, setSigla] = useState('');
  const [tipoEscola, setTipoEscola] = useState('Sede');
  const [escolaPolo, setEscolaPolo] = useState(''); // Estado para o nome da Escola Polo
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
  const [zonaLocalizacao, setZonaLocalizacao] = useState('urbana');
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState('');

  // Estados do Contato
  const [telefoneContato, setTelefoneContato] = useState('');
  const [emailInstitucional, setEmailInstitucional] = useState('');
  const [siteRedeSocial, setSiteRedeSocial] = useState('');

  // Estados da Gestão Escolar - AGORA UM ARRAY DE OBJETOS
  const [gestores, setGestores] = useState([{ inep: '', nome: '', cargo: 'Selecione' }]);

  // Estados para Níveis de Ensino e Anos/Séries
  const [selectedNiveisEnsino, setSelectedNiveisEnsino] = useState([]);
  const [currentNivelEnsino, setCurrentNivelEnsino] = useState('');

  const [selectedAnosSeries, setSelectedAnosSeries] = useState([]);
  const [currentAnoSerie, setCurrentAnoSerie] = useState('');
  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Funções de formatação CEP/Telefone
  const formatCEP = (value) => {
    value = value.replace(/\D/g, '');
    value = value.replace(/^(\d{5})(\d)/, '$1-$2');
    return value.substring(0, 9);
  };

  const formatTelefone = (value) => {
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
    value = value.replace(/(\d)(\d{4})$/, '$1-$2');
    return value;
  };

  // Funções para gerenciar o array de gestores
  const handleAddGestor = () => {
    setGestores([...gestores, { inep: '', nome: '', cargo: 'Selecione' }]);
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

  // Funções para gerenciar Níveis de Ensino
  const handleAddNivelEnsino = () => {
    if (currentNivelEnsino && !selectedNiveisEnsino.includes(currentNivelEnsino)) {
      setSelectedNiveisEnsino([...selectedNiveisEnsino, currentNivelEnsino]);
      setCurrentNivelEnsino('');
    }
  };

  const handleRemoveNivelEnsino = (nivelToRemove) => {
    setSelectedNiveisEnsino(selectedNiveisEnsino.filter(nivel => nivel !== nivelToRemove));
  };

  // Efeito para atualizar anos/séries disponíveis com base nos níveis de ensino selecionados
  useEffect(() => {
    const newAvailableAnosSeries = new Set();
    selectedNiveisEnsino.forEach(nivel => {
      // Mapeamento para nomes exatos no `seriesAnosEtapasData`
      const mappedNivel = {
        "Educação Infantil": "Educação Infantil",
        "Ensino Fundamental - Anos Iniciais": "Ensino Fundamental - Anos Iniciais",
        "Ensino Fundamental - Anos Finais": "Ensino Fundamental - Anos Finais",
        "Educação de Jovens e Adultos - EJA - Anos Iniciais": "Educação de Jovens e Adultos - EJA",
        "Educação de Jovens e Adultos - EJA - Anos Finais": "Educação de Jovens e Adultos - EJA",
      }[nivel] || nivel;

      if (seriesAnosEtapasData[mappedNivel]) {
        seriesAnosEtapasData[mappedNivel].forEach(item => {
          newAvailableAnosSeries.add(item);
        });
      }
    });
    setAvailableAnosSeries(Array.from(newAvailableAnosSeries));
  }, [selectedNiveisEnsino]);

  // Funções para gerenciar Anos/Séries
  const handleAddAnoSerie = () => {
    if (currentAnoSerie && !selectedAnosSeries.includes(currentAnoSerie)) {
      setSelectedAnosSeries([...selectedAnosSeries, currentAnoSerie]);
      setCurrentAnoSerie('');
    }
  };

  const handleRemoveAnoSerie = (anoSerieToRemove) => {
    setSelectedAnosSeries(selectedAnosSeries.filter(as => as !== anoSerieToRemove));
  };


  // Limpa o formulário
  const resetForm = () => {
    setNomeEscola('');
    setSigla('');
    setTipoEscola('Sede');
    setEscolaPolo(''); // Resetar também a escola polo
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

  // Efeito para carregar escolas existentes (apenas para admins)
  useEffect(() => {
    if (!loading) {
      if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
        navigate('/dashboard');
        return;
      }

      const fetchSchools = async () => {
        try {
          const schoolsCol = collection(db, 'schools');
          const schoolSnapshot = await getDocs(schoolsCol);
          const schoolList = schoolSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setSchools(schoolList);
        } catch (error) {
          console.error("Erro ao buscar escolas:", error);
          setErrorMessage("Erro ao carregar lista de escolas.");
        }
      };
      fetchSchools();
    }
  }, [loading, userData, navigate]);

  // Função para lidar com o cadastro/edição de escola
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    // Validações básicas (adicione mais conforme necessário)
    if (!nomeEscola || !codigoINEP || !municipio || !emailInstitucional) {
      setErrorMessage('Nome da escola, Código INEP, Município e E-mail institucional são campos obrigatórios.');
      return;
    }
    if (situacaoFuncionamento === 'Escolha') {
      setErrorMessage('Por favor, selecione a Situação de funcionamento.');
      return;
    }
    if (dependenciaAdm === 'Selecione') {
      setErrorMessage('Por favor, selecione a Dependência administrativa.');
      return;
    }
    if (orgaoVinculado === 'Escolha') {
      setErrorMessage('Por favor, selecione o Órgão vinculado.');
      return;
    }
    if (tipoEscola === 'Escolha' || !tipoEscola) {
      setErrorMessage('Por favor, selecione o Tipo de Escola (Sede ou Anexa).');
      return;
    }
    // NOVO: Validação para Escola Polo se for Anexa
    if (tipoEscola === 'Anexa' && !escolaPolo) {
      setErrorMessage('O nome da Escola Polo é obrigatório para escolas do tipo "Anexa".');
      return;
    }

    if (gestores.some(g => !g.nome || g.cargo === 'Selecione')) {
      setErrorMessage('Nome e Cargo do(s) Gestor(es) são obrigatórios e devem ser preenchidos corretamente.');
      return;
    }
    if (selectedNiveisEnsino.length === 0) {
      setErrorMessage('Por favor, adicione pelo menos um Nível de Ensino ofertado.');
      return;
    }
    if (selectedAnosSeries.length === 0) {
      setErrorMessage('Por favor, adicione pelo menos um Ano/Série atendida.');
      return;
    }


    const schoolData = {
      // Dados Gerais
      nomeEscola,
      sigla,
      tipoEscola,
      escolaPolo: tipoEscola === 'Anexa' ? escolaPolo : '', // Salva escolaPolo apenas se for Anexa, caso contrário, salva vazio
      codigoINEP,
      situacaoFuncionamento,
      dependenciaAdm,
      orgaoVinculado,
      regulamentacaoAutorizacao,
      // Endereço e Localização
      rua,
      numero,
      complemento,
      bairro,
      municipio,
      cep: cep.replace(/\D/g, ''),
      zonaLocalizacao,
      localizacaoDiferenciada,
      // Contato
      telefoneContato: telefoneContato.replace(/\D/g, ''),
      emailInstitucional,
      siteRedeSocial,
      // Gestão Escolar
      gestores,
      // Oferta de Ensino
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
        setSchools(schools.map(s => s.id === editingSchool.id ? { ...s, ...schoolData } : s));
      } else {
        await addDoc(collection(db, 'schools'), schoolData);
        setSuccessMessage('Escola cadastrada com sucesso!');
        const schoolsCol = collection(db, 'schools');
        const studentSnapshot = await getDocs(schoolsCol);
        const studentList = studentSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        setSchools(studentList);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar escola:", error);
      setErrorMessage("Erro ao salvar dados da escola: " + error.message);
    }
  };

  // Funções para a tabela
  const handleEdit = (school) => {
    setEditingSchool(school);
    setNomeEscola(school.nomeEscola || '');
    setSigla(school.sigla || '');
    setTipoEscola(school.tipoEscola || 'Sede');
    setEscolaPolo(school.escolaPolo || ''); // Popula o campo escolaPolo
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

  // Verificação de permissão (apenas admins podem acessar)
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
    return (
      <div className="flex justify-center items-center h-screen text-red-600 font-bold">
        Acesso Negado: Você não tem permissão para acessar esta página.
      </div>
    );
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">

        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingSchool ? 'Editar Escola' : 'Cadastrar Nova Escola'}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 🏫 Dados Gerais */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Dados Gerais</h3>
              <div className="grid grid-cols-1 md:grid-cols-8 gap-4">
                <div className="col-span-6">
                <label htmlFor="nomeEscola" className="block text-sm font-medium text-gray-700">Nome da Escola <span className="text-red-500">*</span></label>
                <input type="text" id="nomeEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={nomeEscola} onChange={(e) => setNomeEscola(e.target.value)} required />
              </div>
              <div className="col-span-1">
                <label htmlFor="sigla" className="block text-sm font-medium text-gray-700">Sigla</label>
                <input type="text" id="sigla" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={sigla} onChange={(e) => setSigla(e.target.value)} />
              </div>
              <div className="col-span-1">
                <label htmlFor="tipoEscola" className="block text-sm font-medium text-gray-700">Tipo</label>
                <select id="tipoEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={tipoEscola} onChange={(e) => setTipoEscola(e.target.value)}>
                  <option value="Sede">Sede</option>
                  <option value="Anexa">Anexa</option>
                </select>
              </div>

              {/* NOVO: Campo Escola Polo visível apenas se tipoEscola for 'Anexa' */}
              {tipoEscola === 'Anexa' && (
                <div className="md:col-span-8"> {/* Usando md:col-span-8 para ocupar a linha toda */}
                  <label htmlFor="escolaPolo" className="block text-sm font-medium text-gray-700">Nome da Escola Polo <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    id="escolaPolo"
                    className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
                    value={escolaPolo}
                    onChange={(e) => setEscolaPolo(e.target.value)}
                    required // Campo obrigatório quando visível
                  />
                </div>
              )}

              <div>
                <label htmlFor="codigoINEP" className="block text-sm font-medium text-gray-700">Código INEP <span className="text-red-500">*</span></label>
                <input type="text" id="codigoINEP" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoINEP} onChange={(e) => setCodigoINEP(e.target.value)} required />
              </div>
              {/* Select: Situação de funcionamento */}
              <div className="col-span-2">
                <label htmlFor="situacao" className="block text-sm font-medium text-gray-700">Situação</label>
              <select id="situacaoFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={situacaoFuncionamento} onChange={(e) => setSituacaoFuncionamento(e.target.value)}>
                  <option value="Escolha">Escolha</option>
                  <option value="Em atividade">Em atividade</option>
                  <option value="Paralisada">Paralisada</option>
                  <option value="Extinta">Extinta</option>
                </select>
              </div>
              {/* Select: Dependência administrativa */}
              <div className="col-span-2">
                <label htmlFor="dependenciaAdm" className="block text-sm font-medium text-gray-700">Dependência administrativa</label>
              <select id="dependenciaAdm" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={dependenciaAdm} onChange={(e) => setDependenciaAdm(e.target.value)}>
                  <option value="Selecione">Selecione</option>
                  <option value="Municipal">Municipal</option>
                  <option value="Estadual">Estadual</option>
                  <option value="Privada">Privada</option>
                </select>
              </div>
              {/* Select: Órgão vinculado */}
              <div className="col-span-3">
                <label htmlFor="orgaoVinculado" className="block text-sm font-medium text-gray-700">Órgão vinculado</label>
                <select id="orgaoVinculado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={orgaoVinculado} onChange={(e) => setOrgaoVinculado(e.target.value)}>
                  <option value="Escolha">Escolha</option>
                  <option value="Secretaria Municipal de Educação">Secretaria Municipal de Educação</option>
                  <option value="Secretaria Estadual de Educação">Secretaria Estadual de Educação</option>
                </select>
              </div>
              {/* Campo "Regulamentação/autorização" ocupando a largura total */}
              <div className="md:col-span-8">
                <label htmlFor="regulamentacaoAutorizacao" className="block text-sm font-medium text-gray-700">Regulamentação/autorização</label>
                <input type="text" id="regulamentacaoAutorizacao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={regulamentacaoAutorizacao} onChange={(e) => setRegulamentacaoAutorizacao(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 📍 Endereço e Localização */}
<div className="md:col-span-2">
  <h3 className="text-lg font-semibold text-gray-700 mb-2">Endereço e Localização</h3>
  <div className="grid grid-cols-1 md:grid-cols-8 gap-4">

    {/* Rua (linha inteira) */}
    <div className="col-span-7">
      <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
      <input
        type="text"
        id="rua"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={rua}
        onChange={(e) => setRua(e.target.value)}
      />
    </div>

    {/* Número (1/8), Complemento (3/8), Bairro (4/8) */}
    <div className="col-span-1">
      <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
      <input
        type="text"
        id="numero"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={numero}
        onChange={(e) => setNumero(e.target.value)}
      />
    </div>

    <div className="col-span-4">
      <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
      <input
        type="text"
        id="complemento"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={complemento}
        onChange={(e) => setComplemento(e.target.value)}
      />
    </div>

    <div className="col-span-4">
      <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
      <input
        type="text"
        id="bairro"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={bairro}
        onChange={(e) => setBairro(e.target.value)}
      />
    </div>

    {/* Município (4/8), CEP (2/8), Zona (2/8) */}
    <div className="col-span-4">
      <label htmlFor="municipio" className="block text-sm font-medium text-gray-700">
        Município <span className="text-red-500">*</span>
      </label>
      <input
        type="text"
        id="municipio"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={municipio}
        onChange={(e) => setMunicipio(e.target.value)}
        required
      />
    </div>

    <div className="col-span-2">
      <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
      <input
        type="text"
        id="cep"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={formatCEP(cep)}
        onChange={(e) => setCep(e.target.value)}
        maxLength="9"
      />
    </div>

    <div className="col-span-2">
      <label htmlFor="zonaLocalizacao" className="block text-sm font-medium text-gray-700">Zona de localização</label>
      <select
        id="zonaLocalizacao"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={zonaLocalizacao}
        onChange={(e) => setZonaLocalizacao(e.target.value)}
      >
        <option value="urbana">Urbana</option>
        <option value="rural">Rural</option>
      </select>
    </div>

    {/* Localização diferenciada (linha inteira) */}
    <div className="col-span-8">
      <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
      <select
        id="localizacaoDiferenciada"
        className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        value={localizacaoDiferenciada}
        onChange={(e) => setLocalizacaoDiferenciada(e.target.value)}
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
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Contato</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="telefoneContato" className="block text-sm font-medium text-gray-700">Telefone fixo e/ou celular</label>
                <input type="tel" id="telefoneContato" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatTelefone(telefoneContato)} onChange={(e) => setTelefoneContato(e.target.value)} maxLength="15" />
              </div>
              <div>
                <label htmlFor="emailInstitucional" className="block text-sm font-medium text-gray-700">E-mail institucional <span className="text-red-500">*</span></label>
                <input type="email" id="emailInstitucional" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={emailInstitucional} onChange={(e) => setEmailInstitucional(e.target.value)} required />
              </div>
              <div className="md:col-span-2">
                <label htmlFor="siteRedeSocial" className="block text-sm font-medium text-gray-700">Site, blog ou rede social (se houver)</label>
                <input type="url" id="siteRedeSocial" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={siteRedeSocial} onChange={(e) => setSiteRedeSocial(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 🧑‍🏫 Gestão Escolar */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Gestão Escolar</h3>
            {/* Iterar sobre os gestores */}
            {gestores.map((gestor, index) => (
              <div key={index} className="grid grid-cols-1 md:grid-cols-8 gap-4 mb-4 items-end">
                <div className="col-span-1">
                  <label htmlFor={`gestor-inep-${index}`} className="block text-sm font-medium text-gray-700">INEP</label>
                  <input type="text" id={`gestor-inep-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.inep} onChange={(e) => handleGestorChange(index, 'inep', e.target.value)} />
                </div>
                <div className="col-span-5">
                  <label htmlFor={`gestor-nome-${index}`} className="block text-sm font-medium text-gray-700">Nome do(a) gestor(a)</label>
                  <input type="text" id={`gestor-nome-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.nome} onChange={(e) => handleGestorChange(index, 'nome', e.target.value)} />
                </div>
                <div className="col-span-1">
                  <label htmlFor={`gestor-cargo-${index}`} className="block text-sm font-medium text-gray-700">Cargo</label>
                  <select id={`gestor-cargo-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.cargo} onChange={(e) => handleGestorChange(index, 'cargo', e.target.value)}>
                    <option value="Selecione">Selecione</option>
                    <option value="Diretor(a)">Diretor(a)</option>
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
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Oferta de Ensino</h3>
            <div className="grid grid-cols-1 gap-4">
              {/* Níveis de Ensino Ofertados */}
              <div>
                <label htmlFor="niveisEnsino" className="block text-sm font-medium text-gray-700">Níveis de ensino ofertados <span className="text-red-500">*</span></label>
                <div className="flex items-center space-x-2 mt-1">
                  <select
                    id="niveisEnsino"
                    className="block w-full p-2 border border-gray-300 rounded-md"
                    value={currentNivelEnsino}
                    onChange={(e) => setCurrentNivelEnsino(e.target.value)}
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
              <div>
                <label htmlFor="anosSeriesAtendidas" className="block text-sm font-medium text-gray-700">Anos/séries atendidas <span className="text-red-500">*</span></label>
                <div className="flex items-center space-x-2 mt-1">
                  <select
                    id="anosSeriesAtendidas"
                    className="block w-full p-2 border border-gray-300 rounded-md"
                    value={currentAnoSerie}
                    onChange={(e) => setCurrentAnoSerie(e.target.value)}
                    disabled={selectedNiveisEnsino.length === 0}
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
              <div className="md:col-span-2">
                <label htmlFor="anosLetivosFuncionamento" className="block text-sm font-medium text-gray-700">Anos letivos em funcionamento</label>
                <input type="text" id="anosLetivosFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="Ex: 2023, 2024" value={''} onChange={() => {}} />
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