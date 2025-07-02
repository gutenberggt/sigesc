import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

function SchoolManagementPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [editingSchool, setEditingSchool] = useState(null);

  // Estados dos Dados Gerais
  const [nomeEscola, setNomeEscola] = useState('');
  const [sigla, setSigla] = useState('');
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
  const [zonaLocalizacao, setZonaLocalizacao] = useState('urbana'); // 'urbana' ou 'rural'
  const [localizacaoDiferenciada, setLocalizacaoDiferenciada] = useState('');

  // Estados do Contato
  const [telefoneContato, setTelefoneContato] = useState('');
  const [emailInstitucional, setEmailInstitucional] = useState('');
  const [siteRedeSocial, setSiteRedeSocial] = useState('');

  // Estados da Gestão Escolar - AGORA UM ARRAY DE OBJETOS
  const [gestores, setGestores] = useState([{ inep: '', nome: '', cargo: 'Selecione' }]); 
  // REMOVIDO: nomesGestores, cargosGestores, codigoINEPGestor, secretarioEscolar

  // Estados da Oferta de Ensino
  const [niveisEnsino, setNiveisEnsino] = useState(''); // Ex: "Educação Infantil, Ensino Fundamental"
  const [anosSeriesAtendidas, setAnosSeriesAtendidas] = useState(''); // Ex: "1º ao 9º ano, EJA"
  const [anosLetivosFuncionamento, setAnosLetivosFuncionamento] = useState(''); // Ex: "2023, 2024"

  // Estados de Vinculações e Parcerias
  const [parceriaConvenio, setParceriaConvenio] = useState('nao'); // 'sim' ou 'nao'
  const [formaContratacaoConvenio, setFormaContratacaoConvenio] = useState('');
  const [mantenedora, setMantenedora] = useState('');
  const [categoriaEscola, setCategoriaEscola] = useState('publica'); // 'publica' ou 'privada'

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Funções de formatação CPF/Telefone (copiadas para consistência)
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

  // Limpa o formulário
  const resetForm = () => {
    setNomeEscola('');
    setSigla('');
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

    setGestores([{ inep: '', nome: '', cargo: 'Selecione' }]); // Resetar array de gestores
    // REMOVIDO: nomesGestores, cargosGestores, codigoINEPGestor, secretarioEscolar

    setNiveisEnsino('');
    setAnosSeriesAtendidas('');
    setAnosLetivosFuncionamento('');

    setParceriaConvenio('nao');
    setFormaContratacaoConvenio('');
    setMantenedora('');
    setCategoriaEscola('publica');

    setErrorMessage('');
    setSuccessMessage('');
    setEditingSchool(null);
  };

  // Efeito para carregar escolas existentes (apenas para admins)
  useEffect(() => {
    if (!loading) {
      if (!userData || (userData.funcao && userData.funcao.toLowerCase() !== 'administrador')) {
        navigate('/dashboard'); // Redireciona se não for administrador
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
    // Nova validação para gestores
    if (gestores.some(g => !g.inep || !g.nome || g.cargo === 'Selecione')) {
      setErrorMessage('Todos os campos de Gestor (INEP, Nome, Cargo) são obrigatórios e devem ser preenchidos corretamente.');
      return;
    }


    const schoolData = {
      // Dados Gerais
      nomeEscola,
      sigla,
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
      // Gestão Escolar - AGORA SALVANDO O ARRAY COMPLETO
      gestores, 
      // REMOVIDO: nomesGestores, cargosGestores, codigoINEPGestor, secretarioEscolar

      // Oferta de Ensino
      niveisEnsino,
      anosSeriesAtendidas,
      anosLetivosFuncionamento,
      // Vinculações e Parcerias
      parceriaConvenio: parceriaConvenio === 'sim',
      formaContratacaoConvenio,
      mantenedora,
      categoriaEscola,
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
        const schoolSnapshot = await getDocs(schoolsCol);
        const schoolList = schoolSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        setSchools(schoolList);
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

    // Popula o array de gestores na edição
    setGestores(school.gestores && school.gestores.length > 0 ? school.gestores : [{ inep: '', nome: '', cargo: 'Selecione' }]);
    // REMOVIDO: nomesGestores, cargosGestores, codigoINEPGestor, secretarioEscolar

    setNiveisEnsino(school.niveisEnsino || '');
    setAnosSeriesAtendidas(school.anosSeriesAtendidas || '');
    setAnosLetivosFuncionamento(school.anosLetivosFuncionamento || '');

    setParceriaConvenio(school.parceriaConvenio ? 'sim' : 'nao');
    setFormaContratacaoConvenio(school.formaContratacaoConvenio || '');
    setMantenedora(school.mantenedora || '');
    setCategoriaEscola(school.categoriaEscola || 'publica');

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
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Nome da Escola: 75% de largura */}
              <div className="col-span-3">
                <label htmlFor="nomeEscola" className="block text-sm font-medium text-gray-700">Nome da Escola <span className="text-red-500">*</span></label>
                <input type="text" id="nomeEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={nomeEscola} onChange={(e) => setNomeEscola(e.target.value)} required />
              </div>
              {/* Sigla: 25% de largura */}
              <div className="col-span-1">
                <label htmlFor="sigla" className="block text-sm font-medium text-gray-700">Sigla</label>
                <input type="text" id="sigla" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={sigla} onChange={(e) => setSigla(e.target.value)} />
              </div>
              
              <div>
                <label htmlFor="codigoINEP" className="block text-sm font-medium text-gray-700">Código INEP <span className="text-red-500">*</span></label>
                <input type="text" id="codigoINEP" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={codigoINEP} onChange={(e) => setCodigoINEP(e.target.value)} required />
              </div>
              {/* Select: Situação de funcionamento */}
              <div>
                <label htmlFor="situacaoFuncionamento" className="block text-sm font-medium text-gray-700">Situação de funcionamento</label>
                <select id="situacaoFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={situacaoFuncionamento} onChange={(e) => setSituacaoFuncionamento(e.target.value)}>
                  <option value="Escolha">Escolha</option>
                  <option value="Em atividade">Em atividade</option>
                  <option value="Paralisada">Paralisada</option>
                  <option value="Extinta">Extinta</option>
                </select>
              </div>
              {/* Select: Dependência administrativa */}
              <div>
                <label htmlFor="dependenciaAdm" className="block text-sm font-medium text-gray-700">Dependência administrativa</label>
                <select id="dependenciaAdm" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={dependenciaAdm} onChange={(e) => setDependenciaAdm(e.target.value)}>
                  <option value="Selecione">Selecione</option>
                  <option value="Municipal">Municipal</option>
                  <option value="Estadual">Estadual</option>
                  <option value="Privada">Privada</option>
                </select>
              </div>
              {/* Select: Órgão vinculado */}
              <div>
                <label htmlFor="orgaoVinculado" className="block text-sm font-medium text-gray-700">Órgão vinculado</label>
                <select id="orgaoVinculado" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={orgaoVinculado} onChange={(e) => setOrgaoVinculado(e.target.value)}>
                  <option value="Escolha">Escolha</option>
                  <option value="Secretaria Municipal de Educação">Secretaria Municipal de Educação</option>
                  <option value="Secretaria Estadual de Educação">Secretaria Estadual de Educação</option>
                </select>
              </div>
              <div className="md:col-span-2">
                <label htmlFor="regulamentacaoAutorizacao" className="block text-sm font-medium text-gray-700">Regulamentação/autorização</label>
                <input type="text" id="regulamentacaoAutorizacao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={regulamentacaoAutorizacao} onChange={(e) => setRegulamentacaoAutorizacao(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 📍 Endereço e Localização */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Endereço e Localização</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="rua" className="block text-sm font-medium text-gray-700">Rua</label>
                <input type="text" id="rua" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={rua} onChange={(e) => setRua(e.target.value)} />
              </div>
              <div>
                <label htmlFor="numero" className="block text-sm font-medium text-gray-700">Número</label>
                <input type="text" id="numero" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={numero} onChange={(e) => setNumero(e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <label htmlFor="complemento" className="block text-sm font-medium text-gray-700">Complemento</label>
                <input type="text" id="complemento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={complemento} onChange={(e) => setComplemento(e.target.value)} />
              </div>
              <div>
                <label htmlFor="bairro" className="block text-sm font-medium text-gray-700">Bairro</label>
                <input type="text" id="bairro" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={bairro} onChange={(e) => setBairro(e.target.value)} />
              </div>
              <div>
                <label htmlFor="municipio" className="block text-sm font-medium text-gray-700">Município <span className="text-red-500">*</span></label>
                <input type="text" id="municipio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={municipio} onChange={(e) => setMunicipio(e.target.value)} required />
              </div>
              <div>
                <label htmlFor="cep" className="block text-sm font-medium text-gray-700">CEP</label>
                <input type="text" id="cep" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formatCEP(cep)} onChange={(e) => setCep(e.target.value)} maxLength="9" />
              </div>
              <div>
                <label htmlFor="zonaLocalizacao" className="block text-sm font-medium text-gray-700">Zona de localização</label>
                <select id="zonaLocalizacao" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={zonaLocalizacao} onChange={(e) => setZonaLocalizacao(e.target.value)}>
                  <option value="urbana">Urbana</option>
                  <option value="rural">Rural</option>
                </select>
              </div>
              <div className="md:col-span-2">
                <label htmlFor="localizacaoDiferenciada" className="block text-sm font-medium text-gray-700">Localização diferenciada (se aplicável)</label>
                <input type="text" id="localizacaoDiferenciada" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={localizacaoDiferenciada} onChange={(e) => setLocalizacaoDiferenciada(e.target.value)} />
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
              <div key={index} className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4 items-end"> {/* MUDANÇA AQUI: grid de 5 colunas e alinhamento */}
                <div className="col-span-1"> {/* INEP */}
                  <label htmlFor={`gestor-inep-${index}`} className="block text-sm font-medium text-gray-700">INEP</label>
                  <input type="text" id={`gestor-inep-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.inep} onChange={(e) => handleGestorChange(index, 'inep', e.target.value)} />
                </div>
                <div className="col-span-3"> {/* Nome do(a) gestor(a) */}
                  <label htmlFor={`gestor-nome-${index}`} className="block text-sm font-medium text-gray-700">Nome do(a) gestor(a)</label>
                  <input type="text" id={`gestor-nome-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.nome} onChange={(e) => handleGestorChange(index, 'nome', e.target.value)} />
                </div>
                <div className="col-span-1"> {/* Cargo do(a) gestor(a) */}
                  <label htmlFor={`gestor-cargo-${index}`} className="block text-sm font-medium text-gray-700">Cargo do(a) gestor(a)</label>
                  <select id={`gestor-cargo-${index}`} className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={gestor.cargo} onChange={(e) => handleGestorChange(index, 'cargo', e.target.value)}>
                    <option value="Selecione">Selecione</option>
                    <option value="Diretor(a)">Diretor(a)</option>
                    <option value="Coordenador(a)">Coordenador(a)</option>
                    <option value="Secretario(a)">Secretário(a)</option>
                  </select>
                </div>
                {gestores.length > 1 && ( // Botão Remover só aparece se houver mais de um gestor
                  <button type="button" onClick={() => handleRemoveGestor(index)} className="mt-1 p-2 text-red-600 hover:text-red-800">
                    {/* Ícone de lixeira */}
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-6 h-6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0-.352-9m1.546-9a3.75 3.75 0 1 1 0 7.5c-.968 0-1.9-.068-2.75-.193M11.25 15L9 12.75 6.75 15M12 21.75c-4.142 0-7.5-3.358-7.5-7.5S7.858 6.75 12 6.75s7.5 3.358 7.5 7.5-3.358 7.5-7.5 7.5Z" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
            {/* Botão Adicionar Novo */}
            <button type="button" onClick={handleAddGestor} className="flex items-center text-green-600 hover:text-green-800 font-semibold text-sm mt-2">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-1">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v6m3-3H9m12 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              ADICIONAR NOVO
            </button>
          </div>

          {/* 🎓 Oferta de Ensino */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Oferta de Ensino</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="niveisEnsino" className="block text-sm font-medium text-gray-700">Níveis de ensino ofertados</label>
                <input type="text" id="niveisEnsino" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="Ex: Educação Infantil, Ensino Fundamental" value={niveisEnsino} onChange={(e) => setNiveisEnsino(e.target.value)} />
              </div>
              <div>
                <label htmlFor="anosSeriesAtendidas" className="block text-sm font-medium text-gray-700">Anos/séries atendidas</label>
                <input type="text" id="anosSeriesAtendidas" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="Ex: 1º ao 9º ano, EJA" value={anosSeriesAtendidas} onChange={(e) => setAnosSeriesAtendidas(e.target.value)} />
              </div>
              <div className="md:col-span-2">
                <label htmlFor="anosLetivosFuncionamento" className="block text-sm font-medium text-gray-700">Anos letivos em funcionamento</label>
                <input type="text" id="anosLetivosFuncionamento" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="Ex: 2023, 2024" value={anosLetivosFuncionamento} onChange={(e) => setAnosLetivosFuncionamento(e.target.value)} />
              </div>
            </div>
          </div>

          {/* 🤝 Vinculações e Parcerias */}
          <div className="md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-700 mb-2">Vinculações e Parcerias</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="parceriaConvenio" className="block text-sm font-medium text-gray-700">Parceria ou convênio com órgãos públicos</label>
                <select id="parceriaConvenio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={parceriaConvenio} onChange={(e) => setParceriaConvenio(e.target.value)}>
                  <option value="nao">Não</option>
                  <option value="sim">Sim</option>
                </select>
              </div>
              <div>
                <label htmlFor="formaContratacaoConvenio" className="block text-sm font-medium text-gray-700">Forma de contratação do convênio (se houver)</label>
                <input type="text" id="formaContratacaoConvenio" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={formaContratacaoConvenio} onChange={(e) => setFormaContratacaoConvenio(e.target.value)} />
              </div>
              <div>
                <label htmlFor="mantenedora" className="block text-sm font-medium text-gray-700">Mantenedora (para escolas privadas, se aplicável)</label>
                <input type="text" id="mantenedora" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={mantenedora} onChange={(e) => setMantenedora(e.target.value)} />
              </div>
              <div>
                <label htmlFor="categoriaEscola" className="block text-sm font-medium text-gray-700">Categoria da escola</label>
                <select id="categoriaEscola" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={categoriaEscola} onChange={(e) => setCategoriaEscola(e.target.value)}>
                  <option value="publica">Pública</option>
                  <option value="privada">Privada</option>
                </select>
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