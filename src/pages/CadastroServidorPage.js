import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, orderBy, addDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';
import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';
import { componentesCurricularesData } from './ComponentesCurricularesPage';

function CadastroServidorPage() {
  const navigate = useNavigate();

  // Estados da Página
  const [personSearchTerm, setPersonSearchTerm] = useState('');
  const [personSuggestions, setPersonSuggestions] = useState([]);
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [availableSchools, setAvailableSchools] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Estado para a lista de alocações do servidor
  const [alocacoes, setAlocacoes] = useState([]);

  // Estados para o formulário de UMA alocação que está sendo criada
  const [currentEscolaId, setCurrentEscolaId] = useState('');
  const [currentAnoLetivo, setCurrentAnoLetivo] = useState(new Date().getFullYear().toString());
  const [currentFuncoes, setCurrentFuncoes] = useState([]);
  
  // Estados para o formulário de UMA função que está sendo criada
  const [currentFuncao, setCurrentFuncao] = useState('');
  const [currentNiveis, setCurrentNiveis] = useState([]); // Renomeado de currentCursos
  const [currentTurmaId, setCurrentTurmaId] = useState('');
  const [currentComponentes, setCurrentComponentes] = useState([]);
  
  // Estados para os dropdowns dinâmicos
  const [availableNiveis, setAvailableNiveis] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);

  // Busca escolas
  useEffect(() => {
    const fetchSchools = async () => {
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      setAvailableSchools(schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    fetchSchools();
  }, []);

  // Busca sugestões de pessoas
  useEffect(() => {
    if (personSearchTerm.length < 3) {
      setPersonSuggestions([]);
      return;
    }
    const fetchSuggestions = async () => {
      const q = query(collection(db, 'pessoas'), where('nomeCompleto', '>=', personSearchTerm.toUpperCase()), where('nomeCompleto', '<=', personSearchTerm.toUpperCase() + '\uf8ff'));
      const snapshot = await getDocs(q);
      setPersonSuggestions(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    const handler = setTimeout(() => fetchSuggestions(), 500);
    return () => clearTimeout(handler);
  }, [personSearchTerm]);
  
  // Atualiza Níveis de Ensino disponíveis com base na escola selecionada
  useEffect(() => {
      if (currentEscolaId) {
          const school = availableSchools.find(s => s.id === currentEscolaId);
          setAvailableNiveis(school?.niveisEnsino || []);
      } else {
          setAvailableNiveis([]);
      }
      setCurrentNiveis([]); // Reseta ao mudar de escola
  }, [currentEscolaId, availableSchools]);
  
  // Atualiza Turmas disponíveis com base na escola e níveis de ensino
  useEffect(() => {
    const fetchTurmas = async () => {
        if (currentEscolaId && currentNiveis.length > 0) {
            const q = query(collection(db, 'turmas'), 
                where('schoolId', '==', currentEscolaId),
                where('nivelEnsino', 'in', currentNiveis)
            );
            const snapshot = await getDocs(q);
            setAvailableTurmas(snapshot.docs.map(doc => ({id: doc.id, ...doc.data()})));
        } else {
            setAvailableTurmas([]);
        }
    };
    fetchTurmas();
    setCurrentTurmaId(''); // Reseta ao mudar de nível
  }, [currentEscolaId, currentNiveis]);

  // ======================= INÍCIO DA CORREÇÃO =======================
  // 1. LÓGICA DOS COMPONENTES AGORA DEPENDE DA TURMA E BUSCA DINAMICAMENTE
  useEffect(() => {
    if (currentTurmaId) {
        const turma = availableTurmas.find(t => t.id === currentTurmaId);
        if (turma) {
            const anoSerie = turma.anoSerie; // Ex: "1º ANO"

            // Lógica para encontrar a chave correta no objeto de componentes curriculares
            const seriesGroupKey = Object.keys(componentesCurricularesData).find(key => {
                const parts = key.split(' ao ');
                if (parts.length === 2) { // Intervalo, ex: "1º ao 5º Ano"
                    const start = parseInt(parts[0], 10);
                    const end = parseInt(parts[1], 10);
                    const current = parseInt(anoSerie, 10);
                    return current >= start && current <= end;
                }
                return key.toUpperCase() === anoSerie; // Chave exata, ex: "6º Ano"
            });
            
            const componentes = componentesCurricularesData[seriesGroupKey] || [];
            
            // Adiciona "Todos" no início da lista de componentes
            setAvailableComponentes(['Todos', ...componentes.map(c => c.nome)]);
        }
    } else {
        setAvailableComponentes([]);
    }
    setCurrentComponentes([]); // Reseta ao mudar de turma
  }, [currentTurmaId, availableTurmas]);
  // ======================== FIM DA CORREÇÃO =========================

  const handleSelectPerson = (person) => {
    setSelectedPerson(person);
    setPersonSearchTerm(person.nomeCompleto);
    setPersonSuggestions([]);
  };

  const handleAddFuncao = () => {
    if (!currentFuncao) {
      setError("A Função é obrigatória.");
      return;
    }
    const newFuncao = {
      funcao: currentFuncao,
      niveisEnsino: currentFuncao === 'Professor(a)' ? currentNiveis : [],
      turmaId: currentFuncao === 'Professor(a)' ? currentTurmaId : null,
      turmaNome: currentFuncao === 'Professor(a)' ? availableTurmas.find(t => t.id === currentTurmaId)?.nomeTurma : null,
      componentesCurriculares: currentFuncao === 'Professor(a)' ? currentComponentes : []
    };
    setCurrentFuncoes([...currentFuncoes, newFuncao]);
    setCurrentFuncao('');
    setCurrentNiveis([]);
    setCurrentTurmaId('');
    setCurrentComponentes([]);
    setError('');
  };

  const handleAddAlocacao = () => {
      if(!currentEscolaId || !currentAnoLetivo || currentFuncoes.length === 0) {
          setError("Para adicionar uma alocação, preencha Escola, Ano Letivo e adicione pelo menos uma função.");
          return;
      }
      const newAlocacao = {
          schoolId: currentEscolaId,
          escolaNome: availableSchools.find(s => s.id === currentEscolaId)?.nomeEscola,
          anoLetivo: currentAnoLetivo,
          funcoes: currentFuncoes
      };
      setAlocacoes([...alocacoes, newAlocacao]);
      setCurrentEscolaId('');
      setCurrentAnoLetivo(new Date().getFullYear().toString());
      setCurrentFuncoes([]);
      setError('');
  };

  const handleSave = async () => {
    if (!selectedPerson || alocacoes.length === 0) {
      setError("Selecione uma Pessoa e adicione ao menos uma Alocação para salvar.");
      return;
    }
    setIsSubmitting(true);
    try {
      const servidorData = {
        pessoaId: selectedPerson.id,
        ativo: true,
        alocacoes: alocacoes.map(({escolaNome, ...rest}) => rest),
        dataCriacao: new Date()
      };
      await addDoc(collection(db, 'servidores'), servidorData);
      setSuccess("Servidor cadastrado com sucesso!");
      setSelectedPerson(null);
      setPersonSearchTerm('');
      setAlocacoes([]);
    } catch (err) {
      console.error(err);
      setError("Erro ao salvar o servidor.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Cadastro de Servidor</h2>
        
        <div className="mb-4 relative">
            <label className="block text-sm font-medium text-gray-700">Pessoa *</label>
            <input 
                type="text"
                value={personSearchTerm}
                onChange={(e) => setPersonSearchTerm(e.target.value)}
                placeholder="Digite o nome para procurar a pessoa a ser vinculada..."
                className="mt-1 block w-full p-2 border rounded-md"
            />
            {personSuggestions.length > 0 && (
                <ul className="absolute z-10 w-full bg-white border rounded-md shadow-lg">
                    {personSuggestions.map(p => (
                        <li key={p.id} onClick={() => handleSelectPerson(p)} className="p-2 cursor-pointer hover:bg-gray-100">
                            {p.nomeCompleto} - CPF: {p.cpf}
                        </li>
                    ))}
                </ul>
            )}
        </div>

        <div className="p-4 border-2 border-dashed rounded-md bg-gray-50 mb-6">
            <h3 className="text-xl font-semibold mb-4">Adicionar Alocação</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                <div>
                    <label className="block text-sm font-medium text-gray-700">Escola *</label>
                    <select value={currentEscolaId} onChange={(e) => setCurrentEscolaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md">
                        <option value="">Selecione uma escola</option>
                        {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Ano Letivo *</label>
                    <input type="text" value={currentAnoLetivo} onChange={(e) => setCurrentAnoLetivo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
                </div>
            </div>

            <div className="p-4 border rounded-md bg-white mb-4">
                <h4 className="text-lg font-semibold mb-2">Adicionar Funções</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Função *</label>
                        <select value={currentFuncao} onChange={(e) => setCurrentFuncao(e.target.value)} className="mt-1 block w-full p-2 border rounded-md">
                            <option value="">Selecione a função</option>
                            <option value="Professor(a)">Professor(a)</option>
                            <option value="Coordenador(a)">Coordenador(a)</option>
                            <option value="Diretor(a)">Diretor(a)</option>
                            <option value="Secretário(a)">Secretário(a)</option>
                        </select>
                    </div>
                </div>

                {currentFuncao === 'Professor(a)' && (
                    <>
                        <div className="mt-4">
                            <label className="block text-sm font-medium text-gray-700">Níveis de Ensino (segure Ctrl para selecionar vários)</label>
                            <select multiple value={currentNiveis} onChange={(e) => setCurrentNiveis(Array.from(e.target.selectedOptions, option => option.value))} className="mt-1 block w-full p-2 border rounded-md h-24" disabled={!currentEscolaId}>
                                {availableNiveis.map(n => <option key={n} value={n}>{n}</option>)}
                            </select>
                        </div>
                        <div className="mt-4">
                            <label className="block text-sm font-medium text-gray-700">Turma</label>
                            <select value={currentTurmaId} onChange={(e) => setCurrentTurmaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" disabled={availableTurmas.length === 0}>
                                <option value="">Selecione uma turma</option>
                                {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma} ({t.anoSerie})</option>)}
                            </select>
                        </div>
                        <div className="mt-4">
                            <label className="block text-sm font-medium text-gray-700">Componentes Curriculares (segure Ctrl para selecionar vários)</label>
                            <select multiple value={currentComponentes} onChange={(e) => setCurrentComponentes(Array.from(e.target.selectedOptions, option => option.value))} className="mt-1 block w-full p-2 border rounded-md h-24" disabled={availableComponentes.length === 0}>
                               {availableComponentes.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                    </>
                )}
                <button onClick={handleAddFuncao} className="mt-4 bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600">+ Adicionar Função</button>
                {currentFuncoes.length > 0 && (
                    <div className="mt-4">
                        {currentFuncoes.map((f,i) => <p key={i} className="text-sm p-1 bg-blue-100 rounded">- {f.funcao}</p>)}
                    </div>
                )}
            </div>
            <button onClick={handleAddAlocacao} className="bg-green-500 text-white font-bold py-2 px-4 rounded w-full">Adicionar Alocação Completa</button>
        </div>

        {/* ======================= INÍCIO DA CORREÇÃO ======================= */}
        {/* 2. RESUMO DO CADASTRO AGORA MOSTRA MAIS DETALHES */}
        <div>
            <h3 className="text-xl font-semibold mb-2">Resumo do Cadastro:</h3>
            {alocacoes.map((aloc, i) => (
                <div key={i} className="p-3 border rounded-md mb-2 bg-gray-100">
                    <p className="font-bold">{aloc.escolaNome} - {aloc.anoLetivo}</p>
                    <ul className="list-disc list-inside ml-4 text-sm">
                        {aloc.funcoes.map((f, j) => 
                            <li key={j}>
                                {f.funcao}
                                {f.turmaNome && ` na turma ${f.turmaNome}`}
                                {f.componentesCurriculares?.length > 0 && ` - Componentes: ${f.componentesCurriculares.join(', ')}`}
                            </li>
                        )}
                    </ul>
                </div>
            ))}
        </div>
        {/* ======================== FIM DA CORREÇÃO ========================= */}

        {error && <p className="text-red-500 mt-4">{error}</p>}
        {success && <p className="text-green-500 mt-4">{success}</p>}

        <div className="flex justify-end space-x-4 mt-6">
            <button onClick={() => navigate('/dashboard')} className="bg-gray-300 text-gray-800 py-2 px-4 rounded">Cancelar</button>
            <button onClick={handleSave} disabled={isSubmitting} className="bg-green-600 text-white font-bold py-2 px-4 rounded">{isSubmitting ? 'Salvando...' : 'Salvar Servidor'}</button>
        </div>
      </div>
    </div>
  );
}

export default CadastroServidorPage;