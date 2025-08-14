import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, doc, getDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useNavigate, useParams } from 'react-router-dom';

function EditarServidorPage() {
  const navigate = useNavigate();
  const { servidorId } = useParams();

  // Estados da Página
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [availableSchools, setAvailableSchools] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(true);

  // Estados para a lista de alocações e edição
  const [alocacoes, setAlocacoes] = useState([]);
  const [editingAlocacaoIndex, setEditingAlocacaoIndex] = useState(null);

  // Estados para o formulário de UMA alocação
  const [currentEscolaId, setCurrentEscolaId] = useState('');
  const [currentAnoLetivo, setCurrentAnoLetivo] = useState(new Date().getFullYear().toString());
  const [currentFuncoes, setCurrentFuncoes] = useState([]);

  // Estados para o formulário de UMA função
  const [currentFuncao, setCurrentFuncao] = useState('');
  const [currentTurmaId, setCurrentTurmaId] = useState('');
  
  const [selectedComponentes, setSelectedComponentes] = useState([]);
  const [allComponentes, setAllComponentes] = useState([]);
  const [componentesParaAdicionar, setComponentesParaAdicionar] = useState([]);
  const [componentesParaRemover, setComponentesParaRemover] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);

  // Carrega dados iniciais
  const fetchInitialData = useCallback(async () => {
    setLoading(true);
    try {
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      const schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setAvailableSchools(schoolsList);
      
      const componentesSnapshot = await getDocs(collection(db, 'componentes'));
      setAllComponentes(componentesSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));

      const servidorDocRef = doc(db, 'servidores', servidorId);
      const servidorDoc = await getDoc(servidorDocRef);

      if (!servidorDoc.exists()) {
        setError("Servidor não encontrado.");
        setLoading(false);
        return;
      }
      const servidorData = servidorDoc.data();
      
      const pessoaDocRef = doc(db, 'pessoas', servidorData.pessoaId);
      const pessoaDoc = await getDoc(pessoaDocRef);
      if(pessoaDoc.exists()) {
        setSelectedPerson({ id: pessoaDoc.id, ...pessoaDoc.data() });
      }
      
      const alocacoesComNomes = servidorData.alocacoes.map(aloc => ({
        ...aloc,
        escolaNome: schoolsList.find(s => s.id === aloc.schoolId)?.nomeEscola || 'Desconhecida'
      }));
      setAlocacoes(alocacoesComNomes);

    } catch (err) {
      console.error("Erro ao carregar dados:", err);
      setError("Falha ao carregar dados para edição.");
    } finally {
      setLoading(false);
    }
  }, [servidorId]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  // Lógica para carregar turmas e filtrar componentes
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
    if (editingAlocacaoIndex === null) {
        setCurrentTurmaId('');
    }
  }, [currentEscolaId, editingAlocacaoIndex]);

  // ======================= INÍCIO DAS MUDANÇAS =======================
  // Filtra os componentes disponíveis com base na série/ano da turma e na condição de escola integral
  const availableComponentesParaTurma = allComponentes.filter(comp => {
    const turma = availableTurmas.find(t => t.id === currentTurmaId);
    if (!turma) return false;

    const isCorrectSerie = comp.serieAno === turma.anoSerie;
    if (!isCorrectSerie) return false;

    const escolaSelecionada = availableSchools.find(s => s.id === currentEscolaId);
    const isIntegral = escolaSelecionada?.integral === 'Sim';
    
    const componentesIntegrais = [
      "Recreação, Esporte e Lazer", "Arte e Cultura", "Tecnologia e Informática",
      "Acompanhamento Pedagógico de Língua Portuguesa", "Acompanhamento Pedagógico de Matemática"
    ];

    if (componentesIntegrais.includes(comp.nome) && !isIntegral) {
      return false;
    }
    
    return true;
  }).sort((a, b) => a.nome.localeCompare(b.nome)); // Melhoria: Ordena alfabeticamente
  // ======================== FIM DAS MUDANÇAS =========================

  const componentesNaoSelecionados = availableComponentesParaTurma.filter(
    comp => !selectedComponentes.some(sel => sel.id === comp.id)
  );

  const componentesSelecionadosInfo = selectedComponentes.map(sel => 
    allComponentes.find(comp => comp.id === sel.id)
  ).filter(Boolean);

  // Funções de manipulação (handlers)
  const handleAddFuncao = () => {
    if (!currentFuncao) { setError("A Função é obrigatória."); return; }
    const newFuncao = {
      funcao: currentFuncao,
      turmaId: currentFuncao === 'Professor(a)' ? currentTurmaId : null,
      turmaNome: currentFuncao === 'Professor(a)' ? availableTurmas.find(t => t.id === currentTurmaId)?.nomeTurma : null,
      componentesCurriculares: currentFuncao === 'Professor(a)' ? selectedComponentes.map(c => c.nome) : []
    };
    setCurrentFuncoes([...currentFuncoes, newFuncao]);
    setCurrentFuncao('');
    setCurrentTurmaId('');
    setSelectedComponentes([]);
  };

  const handleAddOrUpdateAlocacao = () => {
    if(!currentEscolaId || !currentAnoLetivo || currentFuncoes.length === 0) { setError("Preencha Escola, Ano Letivo e adicione pelo menos uma função."); return; }
    const alocacaoData = {
        schoolId: currentEscolaId,
        escolaNome: availableSchools.find(s => s.id === currentEscolaId)?.nomeEscola,
        anoLetivo: currentAnoLetivo,
        funcoes: currentFuncoes
    };
    let updatedAlocacoes = [...alocacoes];
    if (editingAlocacaoIndex !== null) {
        updatedAlocacoes[editingAlocacaoIndex] = alocacaoData;
    } else {
        updatedAlocacoes.push(alocacaoData);
    }
    setAlocacoes(updatedAlocacoes);
    resetFormAlocacao();
  };
  
  const handleEditAlocacao = (index) => {
    setEditingAlocacaoIndex(index);
    const aloc = alocacoes[index];
    setCurrentEscolaId(aloc.schoolId);
    setCurrentAnoLetivo(aloc.anoLetivo);
    setCurrentFuncoes(aloc.funcoes);

    const primeiraFuncaoProfessor = aloc.funcoes.find(f => f.funcao === 'Professor(a)');
    if (primeiraFuncaoProfessor) {
        setCurrentFuncao(primeiraFuncaoProfessor.funcao);
        setCurrentTurmaId(primeiraFuncaoProfessor.turmaId || '');
        
        const componentesSalvos = primeiraFuncaoProfessor.componentesCurriculares || [];
        const componentesObj = allComponentes.filter(comp => componentesSalvos.includes(comp.nome));
        setSelectedComponentes(componentesObj.map(c => ({id: c.id, nome: c.nome})));
    } else {
        setCurrentFuncao('');
        setCurrentTurmaId('');
        setSelectedComponentes([]);
    }
  };

  const handleRemoveAlocacao = (index) => {
    if (window.confirm("Tem certeza que deseja remover esta alocação?")) {
      const updatedAlocacoes = alocacoes.filter((_, i) => i !== index);
      setAlocacoes(updatedAlocacoes);
    }
  };

  const handleSave = async () => {
    if (!selectedPerson) { setError("Nenhuma pessoa selecionada."); return; }
    setIsSubmitting(true);
    try {
      const servidorDocRef = doc(db, 'servidores', servidorId);
      const updateData = {
          alocacoes: alocacoes.map(({escolaNome, ...rest}) => rest),
          dataAtualizacao: new Date()
      };
      await updateDoc(servidorDocRef, updateData);
      setSuccess("Servidor atualizado com sucesso!");
      setTimeout(() => navigate(`/dashboard/escola/servidor/ficha/${servidorId}`), 2000);
    } catch (err) {
      setError("Erro ao salvar as alterações.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (window.confirm("ATENÇÃO: Isso excluirá o registro de servidor. Deseja continuar?")) {
      setIsSubmitting(true);
      try {
        await deleteDoc(doc(db, 'servidores', servidorId));
        setSuccess("Servidor excluído com sucesso!");
        setTimeout(() => navigate('/dashboard/escola/servidores/busca'), 2000);
      } catch (err) {
        setError("Falha ao excluir o servidor.");
        setIsSubmitting(false);
      }
    }
  };

  const resetFormAlocacao = () => {
    setCurrentEscolaId('');
    setCurrentAnoLetivo(new Date().getFullYear().toString());
    setCurrentFuncoes([]);
    setCurrentFuncao('');
    setCurrentTurmaId('');
    setSelectedComponentes([]);
    setEditingAlocacaoIndex(null);
  };
  
  const handleAdicionarComponentes = () => {
    const novosComponentes = [...selectedComponentes];
    componentesParaAdicionar.forEach(idToAdd => {
        if(!novosComponentes.some(c => c.id === idToAdd)) {
            const comp = allComponentes.find(c => c.id === idToAdd);
            if(comp) novosComponentes.push({id: comp.id, nome: comp.nome});
        }
    });
    setSelectedComponentes(novosComponentes.sort((a,b) => a.nome.localeCompare(b.nome))); // Ordena a lista
    setComponentesParaAdicionar([]);
  };

  const handleRemoverComponentes = () => {
    const componentesSelecionadosAtualizados = selectedComponentes.filter(c => !componentesParaRemover.includes(c.id));
    setSelectedComponentes(componentesSelecionadosAtualizados);
    setComponentesParaRemover([]);
  };

  if (loading) return <div className="p-6 text-center">Carregando...</div>;

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Editar Servidor</h2>
        
        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}

        <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700">Pessoa</label>
            <input 
                type="text"
                value={selectedPerson ? `${selectedPerson.nomeCompleto}` : ''}
                readOnly
                className="mt-1 block w-full p-2 border rounded-md bg-gray-100"
            />
        </div>
        
        <div className="p-4 border-2 border-dashed rounded-md bg-gray-50 mb-6">
            <h3 className="text-xl font-semibold mb-4">{editingAlocacaoIndex !== null ? 'Editando Alocação' : 'Adicionar Nova Alocação'}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                <div>
                    <label>Escola *</label>
                    <select value={currentEscolaId} onChange={(e) => setCurrentEscolaId(e.target.value)} className="mt-1 w-full p-2 border rounded-md">
                        <option value="">Selecione</option>
                        {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
                    </select>
                </div>
                <div>
                    <label>Ano Letivo *</label>
                    <input type="text" value={currentAnoLetivo} onChange={(e) => setCurrentAnoLetivo(e.target.value)} className="mt-1 w-full p-2 border rounded-md" />
                </div>
            </div>

            <div className="p-4 border rounded-md bg-white mb-4">
                <h4 className="text-lg font-semibold mb-2">Adicionar Funções</h4>
                <div className="mb-4">
                    <label>Função *</label>
                    <select value={currentFuncao} onChange={(e) => setCurrentFuncao(e.target.value)} className="mt-1 w-full p-2 border rounded-md">
                        <option value="">Selecione</option>
                        <option value="Professor(a)">Professor(a)</option>
                        <option value="Coordenador(a)">Coordenador(a)</option>
                        <option value="Diretor(a)">Diretor(a)</option>
                        <option value="Secretário(a)">Secretário(a)</option>
                    </select>
                </div>

                {currentFuncao === 'Professor(a)' && (
                    <>
                        <div className="mt-4">
                            <label>Turma</label>
                            <select value={currentTurmaId} onChange={(e) => setCurrentTurmaId(e.target.value)} className="mt-1 w-full p-2 border rounded-md" disabled={!currentEscolaId}>
                                <option value="">Selecione</option>
                                {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma} ({t.anoSerie})</option>)}
                            </select>
                        </div>
                        <div className="mt-4">
                            <label className="mb-2 block">Componentes Curriculares</label>
                            <div className="flex items-center space-x-2">
                                <select multiple value={componentesParaAdicionar} onChange={(e) => setComponentesParaAdicionar(Array.from(e.target.selectedOptions, option => option.value))} className="w-full h-32 p-2 border rounded-md" disabled={!currentTurmaId}>
                                   {componentesNaoSelecionados.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
                                </select>
                                <div className="flex flex-col space-y-2">
                                    <button type="button" onClick={handleAdicionarComponentes} className="p-2 bg-gray-200 rounded">Adicionar &gt;&gt;</button>
                                    <button type="button" onClick={handleRemoverComponentes} className="p-2 bg-gray-200 rounded">&lt;&lt; Remover</button>
                                </div>
                                <select multiple value={componentesParaRemover} onChange={(e) => setComponentesParaRemover(Array.from(e.target.selectedOptions, option => option.value))} className="w-full h-32 p-2 border rounded-md bg-gray-100">
                                   {componentesSelecionadosInfo.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
                                </select>
                            </div>
                        </div>
                    </>
                )}
                <div className="text-right">
                  <button type="button" onClick={handleAddFuncao} className="mt-4 bg-blue-500 text-white py-2 px-4 rounded">+ Adicionar Função</button>
                </div>
            </div>
            <div className="flex justify-end space-x-2">
                {editingAlocacaoIndex !== null && <button type="button" onClick={resetFormAlocacao} className="bg-gray-500 text-white py-2 px-4 rounded">Cancelar Edição</button>}
                <button type="button" onClick={handleAddOrUpdateAlocacao} className="bg-green-500 text-white py-2 px-4 rounded w-full">
                    {editingAlocacaoIndex !== null ? 'Salvar Alterações na Alocação' : 'Adicionar Alocação'}
                </button>
            </div>
        </div>

        <div>
            <h3 className="text-xl font-semibold mb-2">Resumo das Alocações</h3>
            {alocacoes.map((aloc, i) => (
                <div key={i} className="p-3 border rounded-md mb-2 bg-gray-100 flex justify-between items-center">
                    <div>
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
                    <div className="space-x-2">
                        <button onClick={() => handleEditAlocacao(i)} className="text-blue-600 text-sm">Editar</button>
                        <button onClick={() => handleRemoveAlocacao(i)} className="text-red-600 text-sm">Remover</button>
                    </div>
                </div>
            ))}
        </div>

        <div className="flex justify-end space-x-4 mt-6">
            <button onClick={() => navigate(-1)} className="bg-gray-300 py-2 px-4 rounded">Cancelar</button>
            <button onClick={handleDelete} disabled={isSubmitting} className="bg-red-600 text-white py-2 px-4 rounded">Excluir Servidor</button>
            <button onClick={handleSave} disabled={isSubmitting} className="bg-green-600 text-white py-2 px-4 rounded">{isSubmitting ? 'Salvando...' : 'Salvar Alterações'}</button>
        </div>
      </div>
    </div>
  );
}

export default EditarServidorPage;