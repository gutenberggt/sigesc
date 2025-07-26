import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, orderBy, limit, getDoc, doc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

// Importar listas para dropdowns de Nível/Série
import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';

function BuscaAlunoPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  // --- Estados dos Campos de Busca ---
  const [nomeCompletoSearch, setNomeCompletoSearch] = useState('');
  const [cpfSearch, setCpfSearch] = useState('');
  const [nomePaiSearch, setNomePaiSearch] = useState('');
  const [nomeMaeSearch, setNomeMaeSearch] = useState('');
  const [codigoINEPSearch, setCodigoINEPSearch] = useState('');
  const [dataNascimentoSearch, setDataNascimentoSearch] = useState('');
  const [naturalidadeCidadeSearch, setNaturalidadeCidadeSearch] = useState('');
  const [sexoSearch, setSexoSearch] = useState('');
  const [escolaSearchId, setEscolaSearchId] = useState('');
  const [nivelEnsinoSearch, setNivelEnsinoSearch] = useState('');
  const [anoSerieSearch, setAnoSerieSearch] = useState('');
  const [turmaSearchId, setTurmaSearchId] = useState('');
  const [situacaoSearch, setSituacaoSearch] = useState('');

  // --- Estados para População de Dropdowns ---
  const [availableSchools, setAvailableSchools] = useState([]);
  const [availableNiveisEnsino, setAvailableNiveisEnsino] = useState([]);
  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [schoolAnosSeriesData, setSchoolAnosSeriesData] = useState([]);

  // --- Estados de Resultado da Busca ---
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchErrorMessage, setSearchErrorMessage] = useState('');

  // Funções de formatação (reutilizadas, se necessário)
  const formatCPF = (value) => value.replace(/\D/g, '').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2').substring(0, 14);
  // formatCEP removido pois o campo CEP foi removido
  // const formatCEP = (value) => value.replace(/\D/g, '').replace(/^(\d{5})(\d)/, '$1-$2').substring(0, 9);


  // Efeito para carregar escolas (para o dropdown de escola na busca)
  useEffect(() => {
    if (!loading) {
      const fetchSchools = async () => {
        try {
          const schoolsCol = collection(db, 'schools');
          const schoolsSnapshot = await getDocs(schoolsCol);
          const schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, nomeEscola: doc.data().nomeEscola, niveisEnsino: doc.data().niveisEnsino, anosSeriesAtendidas: doc.data().anosSeriesAtendidas }));
          setAvailableSchools(schoolsList);
        } catch (error) {
          console.error("Erro ao buscar escolas para busca:", error);
          setSearchErrorMessage("Erro ao carregar lista de escolas.");
        }
      };
      fetchSchools();
    }
  }, [loading]);

  // Efeito para carregar Níveis de Ensino e Anos/Séries da Escola selecionada (na busca)
  useEffect(() => {
    if (escolaSearchId) {
      const selectedSchool = availableSchools.find(s => s.id === escolaSearchId);
      if (selectedSchool) {
        setAvailableNiveisEnsino(selectedSchool.niveisEnsino || []);
        setSchoolAnosSeriesData(selectedSchool.anosSeriesAtendidas || []);
      } else {
        setAvailableNiveisEnsino([]);
        setSchoolAnosSeriesData([]);
      }
    } else {
      // Quando a escola é deselecionada, resetar os campos dependentes
      setNivelEnsinoSearch('');
      setAnoSerieSearch('');
      setTurmaSearchId('');
    }
    // Não precisa resetar aqui, pois já está no bloco if/else acima
    // setNivelEnsinoSearch('');
    // setAnoSerieSearch('');
    // setTurmaSearchId('');
  }, [escolaSearchId, availableSchools]);

  // Efeito para filtrar Ano/Série/Etapa com base no Nível de Ensino selecionado E nas séries da escola
  useEffect(() => {
    const newAvailableAnosSeriesSet = new Set();
    if (nivelEnsinoSearch && schoolAnosSeriesData.length > 0) {
      const mappedNivel = {
        "Educação Infantil": "Educação Infantil", "Ensino Fundamental - Anos Iniciais": "Ensino Fundamental - Anos Iniciais",
        "Ensino Fundamental - Anos Finais": "Ensino Fundamental - Anos Finais", "Educação de Jovens e Adultos - EJA - Anos Iniciais": "Educação de Jovens e Adultos - EJA",
        "Educação de Jovens e Adultos - EJA - Anos Finais": "Educação de Jovens e Adultos - EJA",
      }[nivelEnsinoSearch] || nivelEnsinoSearch;

      if (seriesAnosEtapasData[mappedNivel]) {
        seriesAnosEtapasData[mappedNivel].forEach(item => {
          if (schoolAnosSeriesData.includes(item)) {
            newAvailableAnosSeriesSet.add(item);
          }
        });
      }
    }
    setAvailableAnosSeries(Array.from(newAvailableAnosSeriesSet));
    if (anoSerieSearch && !Array.from(newAvailableAnosSeriesSet).includes(anoSerieSearch)) {
      setAnoSerieSearch('');
    }
    setTurmaSearchId(''); // Reseta turma ao mudar série/nível
  }, [nivelEnsinoSearch, schoolAnosSeriesData, anoSerieSearch]);

  // Efeito para buscar turmas com base na Escola, Nível e Ano/Série selecionados
  useEffect(() => {
    if (escolaSearchId && nivelEnsinoSearch && anoSerieSearch) {
      const fetchTurmas = async () => {
        try {
          const turmasCol = collection(db, 'turmas');
          const q = query(
            turmasCol,
            where('schoolId', '==', escolaSearchId),
            where('nivelEnsino', '==', nivelEnsinoSearch.toUpperCase()),
            where('anoSerie', '==', anoSerieSearch.toUpperCase()),
            orderBy('nomeTurma')
          );
          const querySnapshot = await getDocs(q);
          const turmasList = querySnapshot.docs.map(doc => ({ id: doc.id, nomeTurma: doc.data().nomeTurma }));
          setAvailableTurmas(turmasList);
        } catch (error) {
          console.error("Erro ao buscar turmas para busca:", error);
          setSearchErrorMessage("Erro ao carregar turmas para a busca.");
        }
      };
      fetchTurmas();
    } else {
      setAvailableTurmas([]);
    }
  }, [escolaSearchId, nivelEnsinoSearch, anoSerieSearch]);


  // Função para lidar com a submissão do formulário de busca
  const handleSearch = async (e) => {
    e.preventDefault();
    setIsSearching(true);
    setSearchErrorMessage('');
    setSearchResults([]);

    try {
      let matriculasQuery = collection(db, 'matriculas');
      let pessoaIdsToFilter = [];

      // --- 1. Buscar na coleção 'pessoas' se houver critérios de pessoa ---
      if (nomeCompletoSearch || cpfSearch || nomePaiSearch || nomeMaeSearch || naturalidadeCidadeSearch || sexoSearch || dataNascimentoSearch) { // Nacionalidade, Naturalidade (Estado), Rua, Numero, Bairro, Municipio, CEP removidos da condição
        let pessoasQuery = collection(db, 'pessoas');
        let hasPessoaCriteria = false;

        if (nomeCompletoSearch) {
          pessoasQuery = query(pessoasQuery, where('nomeCompleto', '>=', nomeCompletoSearch.toUpperCase()), where('nomeCompleto', '<=', nomeCompletoSearch.toUpperCase() + '\uf8ff'));
          hasPessoaCriteria = true;
        }
        if (cpfSearch) {
          pessoasQuery = query(pessoasQuery, where('cpf', '==', cpfSearch.replace(/\D/g, '')));
          hasPessoaCriteria = true;
        }
        if (nomePaiSearch) {
          pessoasQuery = query(pessoasQuery, where('pessoaPai', '>=', nomePaiSearch.toUpperCase()), where('pessoaPai', '<=', nomePaiSearch.toUpperCase() + '\uf8ff'));
          hasPessoaCriteria = true;
        }
        if (nomeMaeSearch) {
          pessoasQuery = query(pessoasQuery, where('pessoaMae', '>=', nomeMaeSearch.toUpperCase()), where('pessoaMae', '<=', nomeMaeSearch.toUpperCase() + '\uf8ff'));
          hasPessoaCriteria = true;
        }
        // REMOVIDO: Filtro por nacionalidadeSearch
        if (naturalidadeCidadeSearch) {
          pessoasQuery = query(pessoasQuery, where('naturalidadeCidade', '==', naturalidadeCidadeSearch.toUpperCase()));
          hasPessoaCriteria = true;
        }
        // REMOVIDO: Filtro por naturalidadeEstadoSearch
        if (sexoSearch) {
            pessoasQuery = query(pessoasQuery, where('sexo', '==', sexoSearch));
            hasPessoaCriteria = true;
        }
        if (dataNascimentoSearch) {
            pessoasQuery = query(pessoasQuery, where('dataNascimento', '==', dataNascimentoSearch));
            hasPessoaCriteria = true;
        }
        // REMOVIDO: Filtros de endereço (ruaSearch, numeroSearch, bairroSearch, municipioSearch, cepSearch)

        if (hasPessoaCriteria) {
          const pessoasSnapshot = await getDocs(pessoasQuery);
          pessoaIdsToFilter = pessoasSnapshot.docs.map(doc => doc.id);

          if (pessoaIdsToFilter.length === 0) {
            setSearchErrorMessage("Nenhum resultado de pessoa encontrado para os critérios de pessoa.");
            setIsSearching(false);
            return;
          }
          if (pessoaIdsToFilter.length > 10) {
            setSearchErrorMessage("Muitos resultados de pessoa, refina a busca (limite de 10 pessoas por busca combinada para 'in' query).");
            setIsSearching(false);
            return;
          }
           matriculasQuery = query(matriculasQuery, where('pessoaId', 'in', pessoaIdsToFilter));
        }
      }

      // --- 2. Aplicar filtros diretamente na coleção 'matriculas' ---
      if (codigoINEPSearch) {
        matriculasQuery = query(matriculasQuery, where('codigoINEP', '==', codigoINEPSearch));
      }
      if (escolaSearchId) {
        matriculasQuery = query(matriculasQuery, where('escolaId', '==', escolaSearchId));
      }
      if (nivelEnsinoSearch) {
        matriculasQuery = query(matriculasQuery, where('nivelEnsino', '==', nivelEnsinoSearch.toUpperCase()));
      }
      if (anoSerieSearch) {
        matriculasQuery = query(matriculasQuery, where('anoSerie', '==', anoSerieSearch.toUpperCase()));
      }
      if (turmaSearchId) {
        matriculasQuery = query(matriculasQuery, where('turmaId', '==', turmaSearchId));
      }
      if (situacaoSearch) {
        matriculasQuery = query(matriculasQuery, where('situacaoMatricula', '==', situacaoSearch.toUpperCase()));
      }
      
      const matriculasSnapshot = await getDocs(matriculasQuery);
      const results = await Promise.all(matriculasSnapshot.docs.map(async docMatricula => {
        const matriculaData = docMatricula.data();
        const pessoaDocRef = doc(db, 'pessoas', matriculaData.pessoaId);
        const pessoaDocSnap = await getDoc(pessoaDocRef);
        const pessoaData = pessoaDocSnap.exists() ? pessoaDocSnap.data() : {};
        
        return { id: docMatricula.id, ...matriculaData, pessoa: pessoaData };
      }));

      const finalResults = results.filter(Boolean);
      setSearchResults(finalResults);
      if (finalResults.length === 0) {
        setSearchErrorMessage("Nenhum aluno encontrado com os critérios de busca especificados.");
      }

    } catch (error) {
      console.error("Erro ao realizar busca:", error);
      setSearchErrorMessage("Erro ao realizar busca: " + error.message);
    } finally {
      setIsSearching(false);
    }
  };


  // Limpar formulário de busca
  const clearSearch = () => {
    setNomeCompletoSearch('');
    setCpfSearch('');
    setNomePaiSearch('');
    setNomeMaeSearch('');
    setCodigoINEPSearch('');
    setDataNascimentoSearch('');
    // REMOVIDO: setNacionalidadeSearch('');
    setNaturalidadeCidadeSearch('');
    // REMOVIDO: setNaturalidadeEstadoSearch('');
    setSexoSearch('');
    setEscolaSearchId('');
    setNivelEnsinoSearch('');
    setAnoSerieSearch('');
    setTurmaSearchId('');
    // REMOVIDO: setRuaSearch('');
    // REMOVIDO: setNumeroSearch('');
    // REMOVIDO: setBairroSearch('');
    // REMOVIDO: setMunicipioSearch('');
    // REMOVIDO: setCepSearch('');
    setSituacaoSearch('');
    setSearchResults([]);
    setSearchErrorMessage('');
  };


  // Renderização da página
  if (loading) {
    return <div className="flex justify-center items-center h-screen text-gray-700">Carregando...</div>;
  }

  // Verifica permissão para acessar a página
  if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario' || userData.funcao.toLowerCase() === 'diretor' || userData.funcao.toLowerCase() === 'coordenador' || userData.funcao.toLowerCase() === 'professor' || userData.funcao.toLowerCase() === 'aluno'))) {
    return <div className="flex justify-center items-center h-screen text-red-600 font-bold">Acesso Negado: Você não tem permissão para acessar esta página.</div>;
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Busca de Alunos</h2>

        {searchErrorMessage && <p className="text-red-600 text-sm mb-4 text-center">{searchErrorMessage}</p>}
        {isSearching && <p className="text-blue-600 text-sm mb-4 text-center">Buscando...</p>}

        <form onSubmit={handleSearch} className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4 border rounded-md bg-gray-50 mb-6">
          {/* Dados Pessoais de Busca */}
          <div className="col-span-full md:col-span-2 lg:col-span-3">
            <label htmlFor="nomeCompletoSearch" className="block text-sm font-medium text-gray-700">Nome</label>
            <input type="text" id="nomeCompletoSearch" className="mt-1 block w-full p-2 border rounded-md" value={nomeCompletoSearch} onChange={(e) => setNomeCompletoSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="cpfSearch" className="block text-sm font-medium text-gray-700">CPF</label>
            <input type="text" id="cpfSearch" className="mt-1 block w-full p-2 border rounded-md" value={formatCPF(cpfSearch)} onChange={(e) => setCpfSearch(e.target.value)} maxLength="14" autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-2 lg:col-span-2">
            <label htmlFor="nomeMaeSearch" className="block text-sm font-medium text-gray-700">Nome da Mãe</label>
            <input type="text" id="nomeMaeSearch" className="mt-1 block w-full p-2 border rounded-md" value={nomeMaeSearch} onChange={(e) => setNomeMaeSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-2 lg:col-span-2">
            <label htmlFor="nomePaiSearch" className="block text-sm font-medium text-gray-700">Nome do Pai</label>
            <input type="text" id="nomePaiSearch" className="mt-1 block w-full p-2 border rounded-md" value={nomePaiSearch} onChange={(e) => setNomePaiSearch(e.target.value)} autoComplete="off" />
          </div>

          {/* Dados de Matrícula/Documento */}
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="codigoINEPSearch" className="block text-sm font-medium text-gray-700">Código INEP</label>
            <input type="text" id="codigoINEPSearch" className="mt-1 block w-full p-2 border rounded-md" value={codigoINEPSearch} onChange={(e) => setCodigoINEPSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="dataNascimentoSearch" className="block text-sm font-medium text-gray-700">Data Nasc.</label>
            <input type="date" id="dataNascimentoSearch" className="mt-1 block w-full p-2 border rounded-md" value={dataNascimentoSearch} onChange={(e) => setDataNascimentoSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-2">
            <label htmlFor="naturalidadeCidadeSearch" className="block text-sm font-medium text-gray-700">Naturalidade</label>
            <input type="text" id="naturalidadeCidadeSearch" className="mt-1 block w-full p-2 border rounded-md" value={naturalidadeCidadeSearch} onChange={(e) => setNaturalidadeCidadeSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="sexoSearch" className="block text-sm font-medium text-gray-700">Sexo</label>
            <select id="sexoSearch" className="mt-1 block w-full p-2 border rounded-md" value={sexoSearch} onChange={(e) => setSexoSearch(e.target.value)} autoComplete="off">
              <option value="">Todos</option>
              <option value="Masculino">Masculino</option>
              <option value="Feminino">Feminino</option>
              <option value="Outro">Outro</option>
            </select>
          </div>

          {/* Filtros de Matrícula (Dropdowns) */}
          <div className="col-span-full md:col-span-2 lg:col-span-3">
            <label htmlFor="escolaSearchId" className="block text-sm font-medium text-gray-700">Escola</label>
            <select id="escolaSearchId" className="mt-1 block w-full p-2 border rounded-md" value={escolaSearchId} onChange={(e) => setEscolaSearchId(e.target.value)} autoComplete="off">
              <option value="">Todas as Escolas</option>
              {availableSchools.map(school => (
                <option key={school.id} value={school.id}>{school.nomeEscola}</option>
              ))}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-2">
            <label htmlFor="nivelEnsinoSearch" className="block text-sm font-medium text-gray-700">Nível Ensino</label>
            <select id="nivelEnsinoSearch" className="mt-1 block w-full p-2 border rounded-md" value={nivelEnsinoSearch} onChange={(e) => setNivelEnsinoSearch(e.target.value)} disabled={!escolaSearchId} autoComplete="off">
              <option value="">Todos</option>
              {availableNiveisEnsino.map((nivel, index) => (
                <option key={index} value={nivel}>{nivel}</option>
              ))}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="anoSerieSearch" className="block text-sm font-medium text-gray-700">Série/Ano</label>
            <select id="anoSerieSearch" className="mt-1 block w-full p-2 border rounded-md" value={anoSerieSearch} onChange={(e) => setAnoSerieSearch(e.target.value)} disabled={!nivelEnsinoSearch} autoComplete="off">
              <option value="">Todas</option>
              {availableAnosSeries.map((ano, index) => (
                <option key={index} value={ano}>{ano}</option>
              ))}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="turmaSearchId" className="block text-sm font-medium text-gray-700">Turma</label>
            <select id="turmaSearchId" className="mt-1 block w-full p-2 border rounded-md" value={turmaSearchId} onChange={(e) => setTurmaSearchId(e.target.value)} disabled={!anoSerieSearch} autoComplete="off">
              <option value="">Todas</option>
              {availableTurmas.map(turma => (
                <option key={turma.id} value={turma.id}>{turma.nomeTurma}</option>
              ))}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="situacaoSearch" className="block text-sm font-medium text-gray-700">Situação</label>
            <select id="situacaoSearch" className="mt-1 block w-full p-2 border rounded-md" value={situacaoSearch} onChange={(e) => setSituacaoSearch(e.target.value)} autoComplete="off">
              <option value="">Todas</option>
              <option value="ATIVA">Ativa</option>
              <option value="TRANCADA">Trancada</option>
              <option value="CONCLUIDA">Concluída</option>
              <option value="PENDENTE">Pendente</option>
              <option value="EVADIDO">Evadido</option>
            </select>
          </div>
          
          {/* Botões de Ação */}
          <div className="col-span-full flex justify-end space-x-3 mt-4">
            <button
              type="button"
              onClick={clearSearch}
              className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition"
            >
              Limpar Busca
            </button>
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition"
            >
              Buscar Alunos
            </button>
          </div>
        </form>

        <hr className="my-8" />

        {/* Tabela de Resultados */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Resultados da Busca</h3>
        {searchResults.length === 0 ? (
          <p className="text-center text-gray-600">Nenhum aluno encontrado.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome do Aluno</th>
                  <th className="py-3 px-6 text-left">CPF</th>
                  <th className="py-3 px-6 text-left">Escola</th>
                  <th className="py-3 px-6 text-left">Série/Ano</th>
                  <th className="py-3 px-6 text-left">Turma</th>
                  <th className="py-3 px-6 text-left">Situação</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {searchResults.map(result => (
                  <tr key={result.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{result.pessoa?.nomeCompleto || 'N/A'}</td>
                    <td className="py-3 px-6 text-left">{result.pessoa?.cpf ? formatCPF(result.pessoa.cpf) : 'N/A'}</td>
                    <td className="py-3 px-6 text-left">{availableSchools.find(s => s.id === result.escolaId)?.nomeEscola || 'N/A'}</td>
                    <td className="py-3 px-6 text-left">{result.anoSerie || 'N/A'}</td>
                    <td className="py-3 px-6 text-left">{availableTurmas.find(t => t.id === result.turmaId)?.nomeTurma || 'N/A'}</td>
                    <td className="py-3 px-6 text-left">{result.situacaoMatricula || 'N/A'}</td>
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

export default BuscaAlunoPage;