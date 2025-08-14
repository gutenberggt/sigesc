import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, addDoc } from 'firebase/firestore';
import { useNavigate } from 'react-router-dom';

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

  // Estados para a lista de alocações do servidor
  const [alocacoes, setAlocacoes] = useState([]);

  // Estados para o formulário de UMA alocação que está sendo criada
  const [currentEscolaId, setCurrentEscolaId] = useState('');
  const [currentAnoLetivo, setCurrentAnoLetivo] = useState(new Date().getFullYear().toString());
  const [currentFuncoes, setCurrentFuncoes] = useState([]);

  // Estados para o formulário de UMA função que está sendo criada
  const [currentFuncao, setCurrentFuncao] = useState('');
  const [currentTurmaId, setCurrentTurmaId] = useState('');

  const [selectedComponentes, setSelectedComponentes] = useState([]);
  const [allComponentes, setAllComponentes] = useState([]);
  const [componentesParaAdicionar, setComponentesParaAdicionar] = useState([]);
  const [componentesParaRemover, setComponentesParaRemover] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);

  // Busca escolas e todos os componentes curriculares uma vez
  useEffect(() => {
    const fetchInitialData = async () => {
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      setAvailableSchools(schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
      
      const componentesSnapshot = await getDocs(collection(db, 'componentes'));
      setAllComponentes(componentesSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    fetchInitialData();
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
  
  // Atualiza Turmas disponíveis com base na escola
  useEffect(() => {
    const fetchTurmas = async () => {
        if (currentEscolaId) {
            const q = query(collection(db, 'turmas'), where('schoolId', '==', currentEscolaId));
            const snapshot = await getDocs(q);
            setAvailableTurmas(snapshot.docs.map(doc => ({id: doc.id, ...doc.data()})));
        } else {
            setAvailableTurmas([]);
        }
    };
    fetchTurmas();
    setCurrentTurmaId('');
  }, [currentEscolaId]);

  // ======================= INÍCIO DAS MUDANÇAS =======================
  // Filtra os componentes disponíveis com base na série/ano da turma e na condição de escola integral
  const availableComponentesParaTurma = allComponentes.filter(comp => {
    const turma = availableTurmas.find(t => t.id === currentTurmaId);
    if (!turma) return false; // Se não há turma, não mostra componentes

    const isCorrectSerie = comp.serieAno === turma.anoSerie;
    if (!isCorrectSerie) return false;

    // Condição da escola integral
    const escolaSelecionada = availableSchools.find(s => s.id === currentEscolaId);
    const isIntegral = escolaSelecionada?.integral === 'Sim';
    
    const componentesIntegrais = [
      "Recreação, Esporte e Lazer",
      "Arte e Cultura",
      "Tecnologia e Informática",
      "Acompanhamento Pedagógico de Língua Portuguesa",
      "Acompanhamento Pedagógico de Matemática"
    ];

    // Se o componente for de tempo integral, só mostra se a escola for integral
    if (componentesIntegrais.includes(comp.nome) && !isIntegral) {
      return false;
    }
    
    return true; // Se passou em todas as verificações, mostra o componente
  }).sort((a, b) => a.nome.localeCompare(b.nome)); // Melhoria: Ordena alfabeticamente
  // ======================== FIM DAS MUDANÇAS =========================

  const componentesNaoSelecionados = availableComponentesParaTurma.filter(
    comp => !selectedComponentes.some(sel => sel.id === comp.id)
  );

  const componentesSelecionadosInfo = selectedComponentes.map(sel => 
    allComponentes.find(comp => comp.id === sel.id)
  ).filter(Boolean);

  const handleSelectPerson = (person) => {
    setSelectedPerson(person);
    setPersonSearchTerm(person.nomeCompleto);
    setPersonSuggestions([]);
  };

  const handleAdicionarComponentes = () => {
    const novosComponentes = [...selectedComponentes];
    componentesParaAdicionar.forEach(idToAdd => {
        if(!novosComponentes.some(c => c.id === idToAdd)) {
            const comp = allComponentes.find(c => c.id === idToAdd);
            if(comp) novosComponentes.push({id: comp.id, nome: comp.nome});
        }
    });
    setSelectedComponentes(novosComponentes.sort((a,b) => a.nome.localeCompare(b.nome))); // Ordena a lista de selecionados também
    setComponentesParaAdicionar([]);
  };

  const handleRemoverComponentes = () => {
    const componentesSelecionadosAtualizados = selectedComponentes.filter(c => !componentesParaRemover.includes(c.id));
    setSelectedComponentes(componentesSelecionadosAtualizados);
    setComponentesParaRemover([]);
  };

  const handleAddFuncao = () => {
    if (!currentFuncao) {
      setError("A Função é obrigatória.");
      return;
    }
    const newFuncao = {
      funcao: currentFuncao,
      turmaId: currentFuncao === 'Professor(a)' ? currentTurmaId : null,
      turmaNome: currentFuncao === 'Professor(a)' ? availableTurmas.find(t => t.id === currentTurmaId)?.nomeTurma : null,
      componentesCurriculares: currentFuncao === 'Professor(a)' ? componentesSelecionadosInfo.map(c => c.nome) : []
    };
    setCurrentFuncoes([...currentFuncoes, newFuncao]);
    setCurrentFuncao('');
    setCurrentTurmaId('');
    setSelectedComponentes([]);
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
      setError("Selecione uma Pessoa e adicione ao menos uma Alocação completa para salvar.");
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
                placeholder="Digite o nome para procurar..."
                className="mt-1 block w-full p-2 border rounded-md"
                disabled={!!selectedPerson}
            />
            {personSuggestions.length > 0 && !selectedPerson && (
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
                    <select value={currentEscolaId} onChange={(e) => setCurrentEscolaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md bg-white">
                        <option value="">Selecione uma escola</option>
                        {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Ano Letivo *</label>
                    <input type="text" value={currentAnoLetivo} onChange={(e) => setCurrentAnoLetivo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md bg-white" />
                </div>
            </div>

            <div className="p-4 border rounded-md bg-white mb-4">
                <h4 className="text-lg font-semibold mb-2 text-gray-600">Adicionar Funções à Alocação</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Função *</label>
                        <select value={currentFuncao} onChange={(e) => setCurrentFuncao(e.target.value)} className="mt-1 block w-full p-2 border rounded-md bg-white">
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
                            <label className="block text-sm font-medium text-gray-700">Turma</label>
                            <select value={currentTurmaId} onChange={(e) => setCurrentTurmaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md bg-white" disabled={availableTurmas.length === 0}>
                                <option value="">Selecione uma turma</option>
                                {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma} ({t.anoSerie})</option>)}
                            </select>
                        </div>
                        <div className="mt-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">Componentes Curriculares</label>
                            <div className="flex items-center space-x-2">
                                <select multiple value={componentesParaAdicionar} onChange={(e) => setComponentesParaAdicionar(Array.from(e.target.selectedOptions, option => option.value))} className="w-full p-2 border rounded-md h-32 bg-white" disabled={!currentTurmaId}>
                                   {componentesNaoSelecionados.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
                                </select>
                                <div className="flex flex-col space-y-2">
                                    <button type="button" onClick={handleAdicionarComponentes} className="p-2 bg-gray-200 rounded hover:bg-gray-300">Adicionar &gt;&gt;</button>
                                    <button type="button" onClick={handleRemoverComponentes} className="p-2 bg-gray-200 rounded hover:bg-gray-300">&lt;&lt; Remover</button>
                                </div>
                                <select multiple value={componentesParaRemover} onChange={(e) => setComponentesParaRemover(Array.from(e.target.selectedOptions, option => option.value))} className="w-full p-2 border rounded-md h-32 bg-gray-100 overflow-y-auto">
                                   {componentesSelecionadosInfo.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
                                </select>
                            </div>
                        </div>
                    </>
                )}
                <div className="text-right">
                  <button type="button" onClick={handleAddFuncao} className="mt-4 bg-blue-500 text-white py-2 px-4 rounded hover:bg-blue-600">+ Adicionar Função</button>
                </div>
                {currentFuncoes.length > 0 && (
                    <div className="mt-4">
                        <h4 className="text-md font-semibold text-gray-600">Funções adicionadas nesta alocação:</h4>
                        {currentFuncoes.map((f,i) => <p key={i} className="text-sm p-1 bg-blue-100 rounded">- {f.funcao} {f.turmaNome ? `(${f.turmaNome})` : ''}</p>)}
                    </div>
                )}
            </div>
            <button type="button" onClick={handleAddAlocacao} className="bg-green-500 text-white font-bold py-2 px-4 rounded w-full">Confirmar e Adicionar Alocação</button>
        </div>

        <div>
            <h3 className="text-xl font-semibold mb-2">Resumo das Alocações do Servidor:</h3>
            {selectedPerson && <p className="mb-2 font-bold text-lg text-blue-700">{selectedPerson.nomeCompleto}</p>}
            {alocacoes.map((aloc, i) => (
                <div key={i} className="p-3 border rounded-md mb-2 bg-gray-100">
                    <p className="font-bold">{aloc.escolaNome} - {aloc.anoLetivo}</p>
                    <ul className="list-disc list-inside ml-4 text-sm">
                        {aloc.funcoes.map((f, j) => 
                            <li key={j}>
                                <span className="font-semibold">{f.funcao}</span>
                                {f.turmaNome && ` na turma ${f.turmaNome}`}
                                {f.componentesCurriculares?.length > 0 && ` - Comp: ${f.componentesCurriculares.join(', ')}`}
                            </li>
                        )}
                    </ul>
                </div>
            ))}
        </div>
        
        {error && <p className="text-red-500 text-center font-semibold">{error}</p>}
        {success && <p className="text-green-500 text-center font-semibold">{success}</p>}

        <div className="flex justify-end space-x-4 mt-6">
            <button type="button" onClick={() => navigate('/dashboard')} className="bg-gray-300 text-gray-800 py-2 px-4 rounded">Cancelar</button>
            <button type="button" onClick={handleSave} disabled={isSubmitting} className="bg-green-600 text-white font-bold py-2 px-4 rounded">{isSubmitting ? 'Salvando...' : 'Salvar Servidor'}</button>
        </div>
      </div>
    </div>
  );
}

export default CadastroServidorPage;