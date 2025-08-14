import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, orderBy, getDoc, doc, documentId } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate, Link } from 'react-router-dom';
import { seriesAnosEtapasData } from '../data/ensinoConstants';

function BuscaAlunoPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();

  // Campos de busca
  const [nomeCompletoSearch, setNomeCompletoSearch] = useState('');
  const [cpfSearch, setCpfSearch] = useState('');
  const [escolaSearchId, setEscolaSearchId] = useState('');
  const [nivelEnsinoSearch, setNivelEnsinoSearch] = useState('');
  const [anoSerieSearch, setAnoSerieSearch] = useState('');
  const [turmaSearchId, setTurmaSearchId] = useState('');
  const [situacaoSearch, setSituacaoSearch] = useState('');

  // Listas disponíveis
  const [availableSchools, setAvailableSchools] = useState([]);
  const [availableNiveisEnsino, setAvailableNiveisEnsino] = useState([]);
  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [schoolAnosSeriesData, setSchoolAnosSeriesData] = useState([]);

  // Resultados
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchErrorMessage, setSearchErrorMessage] = useState('');

  const formatCPF = (value) => value.replace(/\D/g, '').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2').substring(0, 14);

  useEffect(() => {
    if (!loading) {
      const fetchSchools = async () => {
        try {
          const schoolsSnapshot = await getDocs(collection(db, 'schools'));
          const schoolsList = schoolsSnapshot.docs.map(doc => ({
            id: doc.id,
            nomeEscola: doc.data().nomeEscola,
            niveisEnsino: doc.data().niveisEnsino || [],
            anosSeriesAtendidas: doc.data().anosSeriesAtendidas || [],
          }));
          setAvailableSchools(schoolsList);
        } catch (error) {
          console.error(error);
          setSearchErrorMessage('Erro ao carregar lista de escolas.');
        }
      };
      fetchSchools();
    }
  }, [loading]);

  useEffect(() => {
    if (escolaSearchId) {
      const selectedSchool = availableSchools.find(s => s.id === escolaSearchId);
      setAvailableNiveisEnsino(selectedSchool?.niveisEnsino || []);
      setSchoolAnosSeriesData(selectedSchool?.anosSeriesAtendidas || []);
    } else {
      setAvailableNiveisEnsino([]);
      setSchoolAnosSeriesData([]);
    }
    setNivelEnsinoSearch('');
    setAnoSerieSearch('');
    setTurmaSearchId('');
  }, [escolaSearchId, availableSchools]);

  useEffect(() => {
    if (nivelEnsinoSearch) {
      const seriesForLevel = seriesAnosEtapasData[nivelEnsinoSearch] || [];
      const filteredSeries = seriesForLevel.filter(serie => schoolAnosSeriesData.includes(serie));
      setAvailableAnosSeries(filteredSeries);
    } else {
      setAvailableAnosSeries([]);
    }
    setAnoSerieSearch('');
    setTurmaSearchId('');
  }, [nivelEnsinoSearch, schoolAnosSeriesData]);

  useEffect(() => {
    if (escolaSearchId && nivelEnsinoSearch && anoSerieSearch) {
      const fetchTurmas = async () => {
        try {
          const q = query(
            collection(db, 'turmas'),
            where('schoolId', '==', escolaSearchId),
            where('nivelEnsino', '==', nivelEnsinoSearch),
            where('anoSerie', '==', anoSerieSearch),
            orderBy('nomeTurma')
          );
          const snapshot = await getDocs(q);
          const turmasList = snapshot.docs.map(doc => ({ id: doc.id, nomeTurma: doc.data().nomeTurma }));
          setAvailableTurmas(turmasList);
        } catch (error) { console.error(error); }
      };
      fetchTurmas();
    } else {
      setAvailableTurmas([]);
    }
    setTurmaSearchId('');
  }, [escolaSearchId, nivelEnsinoSearch, anoSerieSearch]);

  const handleSearch = async (e) => {
    e.preventDefault();
    setIsSearching(true);
    setSearchErrorMessage('');
    setSearchResults([]);

    try {
      let finalQueryConstraints = [];
      let pessoaIdsFinal = null;

      if (nomeCompletoSearch.trim() || cpfSearch.trim()) {
        let pessoaQueryConstraints = [];
        if (nomeCompletoSearch.trim()) {
          pessoaQueryConstraints.push(where('nomeCompleto', '>=', nomeCompletoSearch.trim().toUpperCase()));
          pessoaQueryConstraints.push(where('nomeCompleto', '<=', nomeCompletoSearch.trim().toUpperCase() + '\uf8ff'));
        }
        if (cpfSearch.trim()) {
          pessoaQueryConstraints.push(where('cpf', '==', cpfSearch.replace(/\D/g, '')));
        }
        
        if (pessoaQueryConstraints.length > 0) {
          const pessoasQuery = query(collection(db, 'pessoas'), ...pessoaQueryConstraints);
          const pessoasSnapshot = await getDocs(pessoasQuery);
          pessoaIdsFinal = pessoasSnapshot.docs.map(doc => doc.id);

          if (pessoaIdsFinal.length === 0) {
              setSearchErrorMessage("Nenhum aluno encontrado com os dados pessoais informados.");
              setIsSearching(false);
              return;
          }
        }
      }

      const matriculasQueryBase = collection(db, 'matriculas');
      if (pessoaIdsFinal !== null) {
        if (pessoaIdsFinal.length === 0) {
            setSearchErrorMessage("Nenhum aluno encontrado com os critérios de busca especificados.");
            setIsSearching(false);
            return;
        }
        if (pessoaIdsFinal.length > 30) {
            setSearchErrorMessage("A busca por nome/CPF retornou muitos resultados. Refine a busca ou adicione filtros de matrícula (escola, turma, etc).");
            setIsSearching(false);
            return;
        }
        finalQueryConstraints.push(where('pessoaId', 'in', pessoaIdsFinal));
      }

      if (escolaSearchId) finalQueryConstraints.push(where('escolaId', '==', escolaSearchId));
      if (nivelEnsinoSearch) finalQueryConstraints.push(where('nivelEnsino', '==', nivelEnsinoSearch));
      if (anoSerieSearch) finalQueryConstraints.push(where('anoSerie', '==', anoSerieSearch));
      if (turmaSearchId) finalQueryConstraints.push(where('turmaId', '==', turmaSearchId));
      if (situacaoSearch) finalQueryConstraints.push(where('situacaoMatricula', '==', situacaoSearch));

      if (finalQueryConstraints.length === 0) {
        setSearchErrorMessage("Por favor, preencha ao menos um campo para realizar a busca.");
        setIsSearching(false);
        return;
      }

      const finalQuery = query(matriculasQueryBase, ...finalQueryConstraints);
      const matriculasSnapshot = await getDocs(finalQuery);

      if (matriculasSnapshot.empty) {
        setSearchErrorMessage("Nenhum aluno encontrado com os critérios de busca especificados.");
        setIsSearching(false);
        return;
      }
      
      const resultsData = await Promise.all(matriculasSnapshot.docs.map(async docMatricula => {
        const matriculaData = docMatricula.data();
        if (!matriculaData.pessoaId || !matriculaData.escolaId) return null;
        
        const pessoaDocSnap = await getDoc(doc(db, 'pessoas', matriculaData.pessoaId));
        const escolaDocSnap = await getDoc(doc(db, 'schools', matriculaData.escolaId));
        const turmaDocSnap = matriculaData.turmaId ? await getDoc(doc(db, 'turmas', matriculaData.turmaId)) : null;

        return {
          id: docMatricula.id,
          ...matriculaData,
          pessoa: pessoaDocSnap.exists() ? pessoaDocSnap.data() : {},
          nomeEscola: escolaDocSnap.exists() ? escolaDocSnap.data().nomeEscola : 'N/A',
          nomeTurma: turmaDocSnap?.exists() ? turmaDocSnap.data().nomeTurma : 'N/A',
        };
      }));

      setSearchResults(resultsData.filter(item => item !== null));

    } catch (error) {
      console.error("Erro ao realizar busca:", error);
      setSearchErrorMessage("Ocorreu um erro inesperado ao realizar a busca. Tente novamente.");
    } finally {
      setIsSearching(false);
    }
  };
  
  const clearSearch = () => {
    setNomeCompletoSearch(''); setCpfSearch(''); setEscolaSearchId('');
    setNivelEnsinoSearch(''); setAnoSerieSearch(''); setTurmaSearchId('');
    setSituacaoSearch(''); setSearchResults([]); setSearchErrorMessage('');
  };

  if (loading) {
    return <div className="text-center p-6">Carregando permissões...</div>;
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">Busca de Alunos</h2>

        <form onSubmit={handleSearch} className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4 border rounded-md bg-gray-50 mb-6">
          <div className="col-span-full md:col-span-2 lg:col-span-3">
            <label htmlFor="nomeCompletoSearch" className="block text-sm font-medium text-gray-700">Nome Completo</label>
            <input type="text" id="nomeCompletoSearch" className="mt-1 block w-full p-2 border rounded-md" value={nomeCompletoSearch} onChange={(e) => setNomeCompletoSearch(e.target.value)} autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="cpfSearch" className="block text-sm font-medium text-gray-700">CPF</label>
            <input type="text" id="cpfSearch" className="mt-1 block w-full p-2 border rounded-md" value={cpfSearch} onChange={(e) => setCpfSearch(formatCPF(e.target.value))} maxLength="14" autoComplete="off" />
          </div>
          <div className="col-span-full md:col-span-2 lg:col-span-2">
            <label htmlFor="escolaSearchId" className="block text-sm font-medium text-gray-700">Escola</label>
            <select id="escolaSearchId" className="mt-1 block w-full p-2 border rounded-md" value={escolaSearchId} onChange={(e) => setEscolaSearchId(e.target.value)} autoComplete="off">
              <option value="">Todas as Escolas</option>
              {availableSchools.map(school => <option key={school.id} value={school.id}>{school.nomeEscola}</option>)}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-2">
            <label htmlFor="nivelEnsinoSearch" className="block text-sm font-medium text-gray-700">Nível Ensino</label>
            <select id="nivelEnsinoSearch" className="mt-1 block w-full p-2 border rounded-md" value={nivelEnsinoSearch} onChange={(e) => setNivelEnsinoSearch(e.target.value)} disabled={!escolaSearchId} autoComplete="off">
              <option value="">Todos</option>
              {availableNiveisEnsino.map((nivel, index) => <option key={index} value={nivel}>{nivel}</option>)}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="anoSerieSearch" className="block text-sm font-medium text-gray-700">Série/Ano</label>
            <select id="anoSerieSearch" className="mt-1 block w-full p-2 border rounded-md" value={anoSerieSearch} onChange={(e) => setAnoSerieSearch(e.target.value)} disabled={!nivelEnsinoSearch} autoComplete="off">
              <option value="">Todas</option>
              {availableAnosSeries.map((ano, index) => <option key={index} value={ano}>{ano}</option>)}
            </select>
          </div>
          <div className="col-span-full md:col-span-1 lg:col-span-1">
            <label htmlFor="turmaSearchId" className="block text-sm font-medium text-gray-700">Turma</label>
            <select id="turmaSearchId" className="mt-1 block w-full p-2 border rounded-md" value={turmaSearchId} onChange={(e) => setTurmaSearchId(e.target.value)} disabled={!anoSerieSearch} autoComplete="off">
              <option value="">Todas</option>
              {availableTurmas.map(turma => <option key={turma.id} value={turma.id}>{turma.nomeTurma}</option>)}
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
          <div className="col-span-full flex justify-end space-x-3 mt-4">
            <button type="button" onClick={clearSearch} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded">Limpar</button>
            <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded" disabled={isSearching}>{isSearching ? 'Buscando...' : 'Buscar'}</button>
          </div>
        </form>

        <hr className="my-8" />

        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Resultados da Busca</h3>
        {isSearching ? <p className="text-center text-blue-600">Buscando...</p> : 
          (searchResults.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full bg-white border">
                <thead className="bg-gray-200">
                  <tr>
                    <th className="p-2 border">Nome do Aluno</th>
                    <th className="p-2 border">CPF</th>
                    <th className="p-2 border">Escola</th>
                    <th className="p-2 border">Turma</th>
                    <th className="p-2 border">Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {searchResults.map(result => (
                    <tr key={result.id} className="text-center">
                      <td className="border p-2 text-left">
                        <Link to={`/dashboard/escola/aluno/ficha/${result.pessoaId}`} className="text-blue-600 hover:underline">
                          {result.pessoa?.nomeCompleto || 'N/A'}
                        </Link>
                      </td>
                      <td className="border p-2">{result.pessoa?.cpf ? formatCPF(result.pessoa.cpf) : 'N/A'}</td>
                      <td className="border p-2 text-left">{result.nomeEscola}</td>
                      <td className="border p-2">{result.nomeTurma}</td>
                      <td className="border p-2">{result.situacaoMatricula || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-center text-gray-500">{searchErrorMessage || "Nenhum resultado para exibir. Refine sua busca."}</p>)
        }
      </div>
    </div>
  );
}

export default BuscaAlunoPage;