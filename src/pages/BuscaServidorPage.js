import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, documentId } from 'firebase/firestore';
import { Link, useNavigate } from 'react-router-dom';

// ======================= INÍCIO DA CORREÇÃO =======================
// Importando os dados do arquivo centralizado
import { niveisDeEnsinoList, seriesAnosEtapasData } from '../data/ensinoConstants';
// ======================== FIM DA CORREÇÃO =========================

function BuscaServidorPage() {
  const navigate = useNavigate();
  const [schools, setSchools] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  
  // Estados dos filtros
  const [escolaId, setEscolaId] = useState('');
  const [funcao, setFuncao] = useState('');
  const [turmaId, setTurmaId] = useState('');
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [serieAno, setSerieAno] = useState('');
  const [nivelEnsino, setNivelEnsino] = useState('');
  const [nomeServidor, setNomeServidor] = useState('');

  // Estados para dropdowns dinâmicos
  const [availableSeries, setAvailableSeries] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);

  // Carrega escolas
  useEffect(() => {
    const fetchSchools = async () => {
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      setSchools(schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    fetchSchools();
  }, []);

  // Atualiza Séries/Anos com base no Nível de Ensino
  useEffect(() => {
    if (nivelEnsino && seriesAnosEtapasData[nivelEnsino]) {
      setAvailableSeries(seriesAnosEtapasData[nivelEnsino]);
    } else {
      setAvailableSeries([]);
    }
    setSerieAno(''); // Reseta a série ao mudar o nível
  }, [nivelEnsino]);

  // Atualiza Turmas com base na Escola e Nível de Ensino
  useEffect(() => {
    const fetchTurmas = async () => {
      if (escolaId && nivelEnsino) {
        const q = query(
          collection(db, 'turmas'),
          where('schoolId', '==', escolaId),
          where('nivelEnsino', '==', nivelEnsino)
        );
        const snapshot = await getDocs(q);
        setAvailableTurmas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
      } else {
        setAvailableTurmas([]);
      }
    };
    fetchTurmas();
    setTurmaId(''); // Reseta a turma
  }, [escolaId, nivelEnsino]);

  // Função de busca principal
  const handleSearch = async () => {
    setIsSearching(true);
    setSearchResults([]);

    try {
      let pessoaIds = [];
      if (nomeServidor.length >= 3) {
        const pessoasQuery = query(
          collection(db, 'pessoas'), 
          where('nomeCompleto', '>=', nomeServidor.toUpperCase()),
          where('nomeCompleto', '<=', nomeServidor.toUpperCase() + '\uf8ff')
        );
        const pessoasSnapshot = await getDocs(pessoasQuery);
        pessoaIds = pessoasSnapshot.docs.map(doc => doc.id);
        if (pessoaIds.length === 0) {
          setIsSearching(false);
          setSearchResults([]);
          return;
        }
      }

      let servidoresQuery = query(collection(db, 'servidores'));
      if (pessoaIds.length > 0) {
        servidoresQuery = query(servidoresQuery, where('pessoaId', 'in', pessoaIds));
      }
      
      const servidoresSnapshot = await getDocs(servidoresQuery);
      let servidoresList = servidoresSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));

      let filteredList = servidoresList;

      if (escolaId) {
        filteredList = filteredList.filter(s => s.alocacoes.some(a => a.schoolId === escolaId));
      }
      if (anoLetivo) {
        filteredList = filteredList.filter(s => s.alocacoes.some(a => a.anoLetivo === anoLetivo));
      }
      if (funcao) {
        filteredList = filteredList.filter(s => s.alocacoes.some(a => a.funcoes.some(f => f.funcao === funcao)));
      }
      if (turmaId) {
        filteredList = filteredList.filter(s => s.alocacoes.some(a => a.funcoes.some(f => f.turmaId === turmaId)));
      }
      if (nivelEnsino) {
        filteredList = filteredList.filter(s => s.alocacoes.some(a => a.funcoes.some(f => f.niveisEnsino.includes(nivelEnsino))));
      }
      if (serieAno && !turmaId) {
        const turmasComSerieQuery = query(collection(db, 'turmas'), where('anoSerie', '==', serieAno));
        const turmasSnapshot = await getDocs(turmasComSerieQuery);
        const turmasIdsComSerie = turmasSnapshot.docs.map(doc => doc.id);
        if (turmasIdsComSerie.length > 0) {
          filteredList = filteredList.filter(s => s.alocacoes.some(a => a.funcoes.some(f => turmasIdsComSerie.includes(f.turmaId))));
        } else {
          filteredList = [];
        }
      }

      if (filteredList.length > 0) {
        const finalPessoaIds = [...new Set(filteredList.map(s => s.pessoaId))];
        if (finalPessoaIds.length > 0) {
            const pessoasQuery = query(collection(db, 'pessoas'), where(documentId(), 'in', finalPessoaIds));
            const pessoasSnapshot = await getDocs(pessoasQuery);
            const pessoasMap = new Map();
            pessoasSnapshot.docs.forEach(doc => pessoasMap.set(doc.id, doc.data()));

            const results = filteredList.map(servidor => ({
              ...servidor,
              pessoa: pessoasMap.get(servidor.pessoaId)
            })).filter(s => s.pessoa); // Garante que apenas servidores com pessoa correspondente sejam incluídos
            setSearchResults(results);
        } else {
            setSearchResults([]);
        }
      } else {
        setSearchResults([]);
      }

    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };
  
  const handleClearSearch = () => {
    setEscolaId('');
    setFuncao('');
    setTurmaId('');
    setAnoLetivo(new Date().getFullYear().toString());
    setSerieAno('');
    setNivelEnsino('');
    setNomeServidor('');
    setSearchResults([]);
  };

  const handleAddNew = () => {
    navigate('/dashboard/escola/servidores/cadastro');
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Busca de Servidores</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
          <input type="text" value={nomeServidor} onChange={(e) => setNomeServidor(e.target.value)} placeholder="Nome do servidor" className="p-2 border rounded md:col-span-2" />
          <select value={escolaId} onChange={(e) => setEscolaId(e.target.value)} className="p-2 border rounded md:col-span-2">
              <option value="">Todas as escolas</option>
              {schools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
          </select>
          <input type="text" value={anoLetivo} onChange={(e) => setAnoLetivo(e.target.value)} placeholder="Ano letivo" className="p-2 border rounded" />
          
          <div className="md:col-span-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <select value={funcao} onChange={(e) => setFuncao(e.target.value)} className="p-2 border rounded">
              <option value="">Todas as funções</option>
              <option value="Professor(a)">Professor(a)</option>
              <option value="Coordenador(a)">Coordenador(a)</option>
              <option value="Diretor(a)">Diretor(a)</option>
              <option value="Secretário(a)">Secretário(a)</option>
            </select>
            <select value={nivelEnsino} onChange={(e) => setNivelEnsino(e.target.value)} className="p-2 border rounded">
              <option value="">Todos os níveis de ensino</option>
              {niveisDeEnsinoList.map(n => <option key={n} value={n}>{n}</option>)}
            </select>
            <select value={serieAno} onChange={(e) => setSerieAno(e.target.value)} className="p-2 border rounded" disabled={!nivelEnsino}>
              <option value="">Todas as séries/anos</option>
              {availableSeries.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={turmaId} onChange={(e) => setTurmaId(e.target.value)} className="p-2 border rounded" disabled={!escolaId || !nivelEnsino}>
              <option value="">Todas as turmas</option>
              {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}
            </select>
          </div>
          
          <div className="md:col-span-5 flex justify-end space-x-2">
            <button onClick={handleClearSearch} type="button" className="bg-gray-500 hover:bg-gray-600 text-white font-bold py-2 px-4 rounded transition">
              Limpar Busca
            </button>
            <button onClick={handleSearch} disabled={isSearching} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">
              {isSearching ? 'Buscando...' : 'Buscar'}
            </button>
            <button onClick={handleAddNew} type="button" className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition">
              Novo
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
            <table className="min-w-full bg-white">
                <thead>
                    <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                        <th className="py-3 px-6 text-left">Nome do Servidor</th>
                        <th className="py-3 px-6 text-left">CPF</th>
                        <th className="py-3 px-6 text-left">Função Principal</th>
                    </tr>
                </thead>
                <tbody className="text-gray-600 text-sm">
                    {searchResults.length > 0 ? (
                        searchResults.map(res => (
                            <tr key={res.id} className="border-b hover:bg-gray-100">
                                <td className="py-3 px-6 text-left">
                                    <Link to={`/dashboard/escola/servidor/ficha/${res.id}`} className="text-blue-600 hover:underline">{res.pessoa?.nomeCompleto}</Link>
                                </td>
                                <td className="py-3 px-6 text-left">{res.pessoa?.cpf}</td>
                                <td className="py-3 px-6 text-left">{res.alocacoes?.[0]?.funcoes?.[0]?.funcao || 'N/A'}</td>
                            </tr>
                        ))
                    ) : (
                        <tr><td colSpan="3" className="text-center p-4 text-gray-500">Nenhum resultado encontrado.</td></tr>
                    )}
                </tbody>
            </table>
        </div>
      </div>
    </div>
  );
}

export default BuscaServidorPage;