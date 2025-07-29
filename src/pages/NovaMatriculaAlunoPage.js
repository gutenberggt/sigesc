import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { db } from '../firebase/config';
import { doc, getDoc, collection, getDocs, addDoc, query, where, orderBy } from 'firebase/firestore';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';

// ========================= INÍCIO DA CORREÇÃO =========================
// 1. IMPORTAR OS DADOS REAIS DOS COMPONENTES
import { componentesCurricularesData } from './ComponentesCurricularesPage';
// ========================== FIM DA CORREÇÃO ===========================


function NovaMatriculaAlunoPage() {
  const { alunoId } = useParams();
  const navigate = useNavigate();

  // Estados do Aluno e Formulário
  const [alunoNome, setAlunoNome] = useState('');
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [escolaId, setEscolaId] = useState('');
  const [nivelEnsino, setNivelEnsino] = useState('');
  const [anoSerie, setAnoSerie] = useState('');
  const [turmaId, setTurmaId] = useState('');
  const [dataMatricula, setDataMatricula] = useState(new Date().toISOString().split('T')[0]);
  const [observacoes, setObservacoes] = useState('');
  const [isDependencia, setIsDependencia] = useState(false);
  const [componentesDependencia, setComponentesDependencia] = useState([]);

  // Estados para Dropdowns
  const [availableSchools, setAvailableSchools] = useState([]);
  const [availableNiveis, setAvailableNiveis] = useState([]);
  const [availableSeries, setAvailableSeries] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  
  // ========================= INÍCIO DA CORREÇÃO =========================
  // 2. NOVO ESTADO PARA A LISTA DINÂMICA DE COMPONENTES
  const [availableComponentes, setAvailableComponentes] = useState([]);
  // ========================== FIM DA CORREÇÃO ===========================

  // Estados de Controle
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Busca inicial do nome do aluno e das escolas (sem alterações)
  useEffect(() => {
    const fetchData = async () => {
        try {
            const alunoDocRef = doc(db, 'pessoas', alunoId);
            const alunoDocSnap = await getDoc(alunoDocRef);
            if (alunoDocSnap.exists()) {
                setAlunoNome(alunoDocSnap.data().nomeCompleto);
            } else {
                setError('Aluno não encontrado.');
            }

            const schoolsSnapshot = await getDocs(collection(db, 'schools'));
            const schoolsList = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
            setAvailableSchools(schoolsList);
        } catch (err) {
            console.error(err);
            setError('Falha ao carregar dados iniciais.');
        } finally {
            setLoading(false);
        }
    };
    fetchData();
  }, [alunoId]);

  // Lógica encadeada para os dropdowns (sem alterações)
  useEffect(() => {
    if (escolaId) {
      const selectedSchool = availableSchools.find(s => s.id === escolaId);
      setAvailableNiveis(selectedSchool ? selectedSchool.niveisEnsino : []);
    } else {
      setAvailableNiveis([]);
    }
    setNivelEnsino('');
    setAnoSerie('');
    setTurmaId('');
  }, [escolaId, availableSchools]);

  useEffect(() => {
    if (nivelEnsino) {
        const school = availableSchools.find(s => s.id === escolaId);
        const schoolSeries = school ? school.anosSeriesAtendidas : [];
        const seriesForLevel = seriesAnosEtapasData[nivelEnsino] || [];
        setAvailableSeries(seriesForLevel.filter(serie => schoolSeries.includes(serie)));
    } else {
        setAvailableSeries([]);
    }
    setAnoSerie('');
    setTurmaId('');
  }, [nivelEnsino, escolaId, availableSchools]);

  useEffect(() => {
    if (anoSerie) {
        const fetchTurmas = async () => {
            const turmasQuery = query(
                collection(db, 'turmas'),
                where('schoolId', '==', escolaId),
                where('nivelEnsino', '==', nivelEnsino),
                where('anoSerie', '==', anoSerie)
            );
            const turmasSnapshot = await getDocs(turmasQuery);
            setAvailableTurmas(turmasSnapshot.docs.map(doc => ({id: doc.id, ...doc.data()})));
        };
        fetchTurmas();
    } else {
        setAvailableTurmas([]);
    }
    setTurmaId('');
  }, [anoSerie, nivelEnsino, escolaId]);

  // ========================= INÍCIO DA CORREÇÃO =========================
  // 3. NOVA LÓGICA PARA ATUALIZAR OS COMPONENTES DISPONÍVEIS
  useEffect(() => {
    if (anoSerie) {
      // Converte o ano/série (ex: "1º ANO") para o formato da chave no arquivo de dados (ex: "1º Ano")
      // Esta função simples assume que apenas a palavra "ANO" precisa ser ajustada.
      // Pode ser necessário ajustar se houver outros formatos como "ETAPA".
      const formatKey = (key) => {
        return key.replace(/(\d+º?)\s(ANO|ETAPA)/, (match, p1, p2) => {
          return `${p1} ${p2.charAt(0).toUpperCase() + p2.slice(1).toLowerCase()}`;
        });
      };
      
      const formattedAnoSerie = formatKey(anoSerie);
      
      const componentes = componentesCurricularesData[formattedAnoSerie] || [];
      setAvailableComponentes(componentes.map(c => c.nome)); // Pegamos apenas os nomes
    } else {
      setAvailableComponentes([]);
    }
    // Limpa a seleção de dependência se a série mudar
    setComponentesDependencia([]);
  }, [anoSerie]);
  // ========================== FIM DA CORREÇÃO ===========================

  const handleSalvar = async (e) => {
    e.preventDefault();
    if (!escolaId || !nivelEnsino || !anoSerie || !turmaId) {
        setError('Todos os campos de seleção são obrigatórios.');
        return;
    }
    if (isDependencia && componentesDependencia.length === 0) {
        setError('Se a matrícula é de dependência, ao menos um componente curricular deve ser selecionado.');
        return;
    }

    setIsSubmitting(true);
    setError('');

    try {
        const novaMatriculaData = {
            pessoaId: alunoId,
            anoLetivo,
            escolaId,
            nivelEnsino,
            anoSerie,
            turmaId,
            dataMatricula,
            observacoes,
            matriculaDependencia: isDependencia,
            componentesDependencia: isDependencia ? componentesDependencia : [],
            situacaoMatricula: 'ATIVA',
            ultimaAtualizacao: new Date()
        };

        await addDoc(collection(db, 'matriculas'), novaMatriculaData);
        alert('Nova matrícula cadastrada com sucesso!');
        navigate(`/dashboard/escola/aluno/ficha/${alunoId}`);
    } catch (err) {
        console.error(err);
        setError('Falha ao salvar a nova matrícula.');
    } finally {
        setIsSubmitting(false);
    }
  };

  const handleComponentesChange = (e) => {
    const selectedOptions = Array.from(e.target.selectedOptions, option => option.value);
    setComponentesDependencia(selectedOptions);
  };
  
  const resetForm = () => {
    // ...outros resets
    setIsDependencia(false);
    setComponentesDependencia([]);
  };

  if (loading) return <div className="p-6 text-center">Carregando...</div>;

  return (
    <div className="p-6">
        <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold mb-6 text-gray-800">Nova Matrícula</h2>

            <div className="mb-6 bg-gray-100 p-4 rounded-md">
                <span className="font-semibold text-gray-700">Aluno:</span>
                <span className="ml-2 text-lg text-blue-800">{alunoNome}</span>
            </div>

            <form onSubmit={handleSalvar} className="space-y-4">
                {/* Campos do formulário permanecem os mesmos até a checkbox */}
                <div>
                    <label className="block text-sm font-medium text-gray-700">Ano Letivo *</label>
                    <input type="text" value={anoLetivo} onChange={(e) => setAnoLetivo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Escola *</label>
                    <select value={escolaId} onChange={(e) => setEscolaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required>
                        <option value="">Selecione uma escola</option>
                        {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
                    </select>
                </div>
                 <div>
                    <label className="block text-sm font-medium text-gray-700">Curso (Nível de Ensino) *</label>
                    <select value={nivelEnsino} onChange={(e) => setNivelEnsino(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required disabled={!escolaId}>
                        <option value="">Selecione um curso</option>
                        {availableNiveis.map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Série *</label>
                    <select value={anoSerie} onChange={(e) => setAnoSerie(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required disabled={!nivelEnsino}>
                        <option value="">Selecione uma série</option>
                        {availableSeries.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Turma *</label>
                    <select value={turmaId} onChange={(e) => setTurmaId(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required disabled={!anoSerie}>
                        <option value="">Selecione uma turma</option>
                        {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Data da Matrícula *</label>
                    <input type="date" value={dataMatricula} onChange={(e) => setDataMatricula(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" required />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700">Observações</label>
                    <textarea value={observacoes} onChange={(e) => setObservacoes(e.target.value)} className="mt-1 block w-full p-2 border rounded-md"></textarea>
                </div>
                <div className="flex items-center">
                    <input type="checkbox" id="dependencia" checked={isDependencia} onChange={(e) => setIsDependencia(e.target.checked)} className="h-4 w-4 text-blue-600 border-gray-300 rounded" />
                    <label htmlFor="dependencia" className="ml-2 block text-sm text-gray-900">Matrícula de dependência?</label>
                </div>

                {/* ========================= INÍCIO DA CORREÇÃO ========================= */}
                {/* 4. CAMPO CONDICIONAL AGORA USA A LISTA DINÂMICA */}
                {isDependencia && (
                    <div className="p-4 bg-yellow-50 border-l-4 border-yellow-400">
                        <label htmlFor="componentesDependencia" className="block text-sm font-medium text-gray-700 mb-1">
                            Componentes Curriculares em Dependência *
                        </label>
                        <p className="text-xs text-gray-500 mb-2">Segure Ctrl (ou Cmd em Mac) para selecionar mais de um.</p>
                        <select
                            id="componentesDependencia"
                            multiple={true}
                            value={componentesDependencia}
                            onChange={handleComponentesChange}
                            className="block w-full p-2 border rounded-md h-32"
                            required
                            disabled={availableComponentes.length === 0}
                        >
                            {availableComponentes.length > 0 ? (
                                availableComponentes.map(comp => (
                                    <option key={comp} value={comp}>{comp}</option>
                                ))
                            ) : (
                                <option disabled>Selecione uma Série/Ano para ver os componentes</option>
                            )}
                        </select>
                    </div>
                )}
                {/* ========================== FIM DA CORREÇÃO =========================== */}

                {error && <p className="text-red-600 text-sm text-center">{error}</p>}

                <div className="flex justify-end space-x-4 pt-4">
                    <button type="button" onClick={() => navigate(`/dashboard/escola/aluno/ficha/${alunoId}`)} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">Cancelar</button>
                    <button type="submit" disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition disabled:bg-blue-300">
                        {isSubmitting ? 'Salvando...' : 'Salvar'}
                    </button>
                </div>
            </form>
        </div>
    </div>
  );
}

export default NovaMatriculaAlunoPage;