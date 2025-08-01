import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, documentId, setDoc, doc, getDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

function FrequenciaPage() {
  const { userData } = useUser();
  const navigate = useNavigate();

  // Estados para os filtros
  const [availableSchools, setAvailableSchools] = useState([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState('');
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [selectedTurmaId, setSelectedTurmaId] = useState('');
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [selectedComponente, setSelectedComponente] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().slice(0, 10));

  // Estados para os dados
  const [alunosDaTurma, setAlunosDaTurma] = useState([]);
  const [frequenciaData, setFrequenciaData] = useState({}); // { alunoId: isPresent, ... }

  // Estados de controle
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Carrega as escolas que o usuário tem permissão para ver
  useEffect(() => {
    const fetchSchools = async () => {
      if (!userData) return;
      try {
        const schoolsCol = collection(db, 'schools');
        let schoolsQuery;
        if (userData.funcao?.toLowerCase() === 'administrador') {
          schoolsQuery = query(schoolsCol);
        } else {
          const userSchoolsIds = userData.escolasIds || [];
          if (userSchoolsIds.length === 0) {
            setAvailableSchools([]);
            return;
          }
          schoolsQuery = query(schoolsCol, where(documentId(), 'in', userSchoolsIds));
        }
        const schoolsSnapshot = await getDocs(schoolsQuery);
        setAvailableSchools(schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
      } catch (err) {
        setError("Falha ao carregar escolas.");
      }
    };
    fetchSchools();
  }, [userData]);

  // Carrega as turmas da escola selecionada
  useEffect(() => {
    const fetchTurmas = async () => {
      if (!selectedSchoolId) {
        setAvailableTurmas([]);
        return;
      }
      const turmasQuery = query(collection(db, 'turmas'), where('schoolId', '==', selectedSchoolId));
      const snapshot = await getDocs(turmasQuery);
      setAvailableTurmas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    fetchTurmas();
    setSelectedTurmaId(''); // Reseta a turma ao mudar de escola
  }, [selectedSchoolId]);

  // Carrega os alunos e a frequência salva quando a turma e a data mudam
  const loadAlunosEFrequencia = useCallback(async () => {
    if (!selectedTurmaId || !selectedDate || !selectedComponente) {
      setAlunosDaTurma([]);
      setFrequenciaData({});
      return;
    }
    setLoading(true);
    setError('');
    try {
      // 1. Buscar alunos da turma
      const matriculasQuery = query(
        collection(db, 'matriculas'),
        where('turmaId', '==', selectedTurmaId),
        where('situacaoMatricula', '==', 'ATIVA')
      );
      const matriculasSnapshot = await getDocs(matriculasQuery);
      const pessoaIds = matriculasSnapshot.docs.map(doc => doc.data().pessoaId);
      
      if (pessoaIds.length > 0) {
        const pessoasQuery = query(collection(db, 'pessoas'), where(documentId(), 'in', pessoaIds));
        const pessoasSnapshot = await getDocs(pessoasQuery);
        const alunos = pessoasSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })).sort((a,b) => a.nomeCompleto.localeCompare(b.nomeCompleto));
        setAlunosDaTurma(alunos);

        // 2. Buscar frequência já salva para este dia/turma/componente
        const frequenciaId = `${selectedDate}_${selectedTurmaId}_${selectedComponente.replace(/\s+/g, '-')}`;
        const frequenciaDocRef = doc(db, 'frequencias', frequenciaId);
        const frequenciaDocSnap = await getDoc(frequenciaDocRef);
        
        const initialFrequencia = {};
        if (frequenciaDocSnap.exists()) {
          const data = frequenciaDocSnap.data();
          alunos.forEach(aluno => {
            initialFrequencia[aluno.id] = data.alunosPresentes?.includes(aluno.id) || false;
          });
        } else {
          // Se não houver registro, marca todos como presentes por padrão
          alunos.forEach(aluno => { initialFrequencia[aluno.id] = true; });
        }
        setFrequenciaData(initialFrequencia);
      } else {
        setAlunosDaTurma([]);
        setFrequenciaData({});
      }
    } catch (err) {
      setError("Falha ao carregar alunos ou dados de frequência.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [selectedTurmaId, selectedDate, selectedComponente]);

  useEffect(() => {
    loadAlunosEFrequencia();
  }, [loadAlunosEFrequencia]);

  const handleFrequenciaChange = (alunoId) => {
    setFrequenciaData(prev => ({
      ...prev,
      [alunoId]: !prev[alunoId]
    }));
  };

  const handleMarcarTodos = (isPresente) => {
    const newFrequencia = {};
    alunosDaTurma.forEach(aluno => {
      newFrequencia[aluno.id] = isPresente;
    });
    setFrequenciaData(newFrequencia);
  };

  const handleSaveFrequencia = async () => {
    if (!selectedTurmaId || !selectedDate || !selectedComponente) {
      setError("Por favor, selecione todos os filtros antes de salvar.");
      return;
    }
    setIsSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const alunosPresentes = Object.keys(frequenciaData).filter(alunoId => frequenciaData[alunoId]);
      
      const frequenciaId = `${selectedDate}_${selectedTurmaId}_${selectedComponente.replace(/\s+/g, '-')}`;
      const frequenciaDocRef = doc(db, 'frequencias', frequenciaId);

      await setDoc(frequenciaDocRef, {
        schoolId: selectedSchoolId,
        turmaId: selectedTurmaId,
        componenteCurricular: selectedComponente,
        data: selectedDate,
        alunosPresentes: alunosPresentes,
        ultimaAtualizacao: new Date()
      }, { merge: true });

      setSuccess("Frequência salva com sucesso!");
    } catch (err) {
      setError("Erro ao salvar a frequência.");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Lançamento de Frequência</h2>

        {/* FILTROS */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <select value={selectedSchoolId} onChange={(e) => setSelectedSchoolId(e.target.value)} className="p-2 border rounded-md">
            <option value="">Selecione a Escola</option>
            {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
          </select>
          <select value={selectedTurmaId} onChange={(e) => setSelectedTurmaId(e.target.value)} className="p-2 border rounded-md" disabled={!selectedSchoolId}>
            <option value="">Selecione a Turma</option>
            {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}
          </select>
          <select value={selectedComponente} onChange={(e) => setSelectedComponente(e.target.value)} className="p-2 border rounded-md" disabled={!selectedTurmaId}>
            <option value="">Selecione o Componente</option>
            <option value="Língua Portuguesa">Língua Portuguesa</option>
            <option value="Matemática">Matemática</option>
          </select>
          <input type="date" value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} className="p-2 border rounded-md" />
        </div>

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}

        {/* TABELA DE ALUNOS */}
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                <th className="py-3 px-6 text-left">Nº</th>
                <th className="py-3 px-6 text-left">Nome do Aluno</th>
                <th className="py-3 px-6 text-center">
                  <input 
                    type="checkbox"
                    className="h-5 w-5"
                    checked={alunosDaTurma.length > 0 && Object.values(frequenciaData).every(v => v)}
                    onChange={(e) => handleMarcarTodos(e.target.checked)}
                    title="Marcar/Desmarcar Todos"
                  />
                  <span className="ml-2">Presença</span>
                </th>
              </tr>
            </thead>
            <tbody className="text-gray-700">
              {loading ? (
                <tr><td colSpan="3" className="text-center p-4">Carregando alunos...</td></tr>
              ) : (
                alunosDaTurma.map((aluno, index) => (
                  <tr key={aluno.id} className="border-b hover:bg-gray-100">
                    <td className="py-3 px-6">{index + 1}</td>
                    <td className="py-3 px-6">{aluno.nomeCompleto}</td>
                    <td className="py-3 px-6 text-center">
                      <input 
                        type="checkbox"
                        className="h-6 w-6"
                        checked={frequenciaData[aluno.id] || false}
                        onChange={() => handleFrequenciaChange(aluno.id)}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {alunosDaTurma.length > 0 && (
            <div className="flex justify-end mt-6">
                <button 
                    onClick={handleSaveFrequencia} 
                    disabled={isSubmitting}
                    className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition"
                >
                    {isSubmitting ? 'Salvando...' : 'Salvar Frequência'}
                </button>
            </div>
        )}
      </div>
    </div>
  );
}

export default FrequenciaPage;