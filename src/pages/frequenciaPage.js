import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, documentId, setDoc, doc, getDoc, orderBy, writeBatch } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate } from 'react-router-dom';

const FrequenciaCell = ({ status, onClick, isSaving }) => {
  const statusMap = {
    P: { text: 'P', color: 'bg-green-500', title: 'Presente' },
    F: { text: 'F', color: 'bg-red-500', title: 'Falta' },
    J: { text: 'FJ', color: 'bg-yellow-400', title: 'Falta Justificada' },
  };
  const currentStatus = statusMap[status] || { text: '-', color: 'bg-gray-200', title: 'Marcar Presença' };

  return (
    <button
      onClick={onClick}
      title={currentStatus.title}
      className={`w-8 h-8 rounded-full text-white text-xs font-bold flex items-center justify-center transition-all transform hover:scale-110 ${currentStatus.color} ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
      disabled={isSaving}
    >
      {currentStatus.text}
    </button>
  );
};

const formatDate = (dateString) => {
    if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) { return 'Não Informado'; }
    const [year, month, day] = dateString.split('-');
    return `${day}/${month}/${year}`;
};

function FrequenciaPage() {
  const { userData } = useUser();
  const navigate = useNavigate();

  const [availableSchools, setAvailableSchools] = useState([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState('');
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [selectedTurmaId, setSelectedTurmaId] = useState('');
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [selectedComponente, setSelectedComponente] = useState('');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [availablePeriods, setAvailablePeriods] = useState([]);
  const [selectedPeriod, setSelectedPeriod] = useState(null);
  const [alunosDaTurma, setAlunosDaTurma] = useState([]);
  const [diasLetivos, setDiasLetivos] = useState([]);
  const [frequenciaData, setFrequenciaData] = useState({});
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isProfessor = userData?.funcao?.toLowerCase() === 'professor';

  useEffect(() => {
    const fetchInitialData = async () => {
      if (!userData) return;
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      const allSchools = schoolsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      if (isProfessor) {
        const servidorQuery = query(collection(db, 'servidores'), where('userId', '==', userData.uid));
        const servidorSnapshot = await getDocs(servidorQuery);
        if (!servidorSnapshot.empty) {
          const alocacoes = servidorSnapshot.docs[0].data().alocacoes || [];
          const professorSchoolIds = [...new Set(alocacoes.map(a => a.schoolId))];
          setAvailableSchools(allSchools.filter(s => professorSchoolIds.includes(s.id)));
        }
      } else {
        setAvailableSchools(allSchools);
      }
    };
    fetchInitialData();
  }, [userData, isProfessor]);
  
  useEffect(() => {
    const fetchTurmas = async () => {
      if (!selectedSchoolId) { setAvailableTurmas([]); return; }
      let turmasQuery = query(collection(db, 'turmas'), where('schoolId', '==', selectedSchoolId));
      if (isProfessor) {
        const servidorQuery = query(collection(db, 'servidores'), where('userId', '==', userData.uid));
        const servidorSnapshot = await getDocs(servidorQuery);
        if (!servidorSnapshot.empty) {
          const alocacoes = servidorSnapshot.docs[0].data().alocacoes || [];
          const turmasIds = alocacoes.flatMap(a => a.funcoes.map(f => f.turmaId));
          if (turmasIds.length > 0) {
            turmasQuery = query(turmasQuery, where(documentId(), 'in', [...new Set(turmasIds)]));
          }
        }
      }
      const snapshot = await getDocs(turmasQuery);
      setAvailableTurmas(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    };
    fetchTurmas();
    setSelectedTurmaId('');
  }, [selectedSchoolId, isProfessor, userData]);

  useEffect(() => {
    const populateComponentes = async () => {
        if (!selectedTurmaId) { setAvailableComponentes([]); return; }
        const horarioRef = doc(db, 'horarios', selectedTurmaId);
        const horarioSnap = await getDoc(horarioRef);
        if (horarioSnap.exists()) {
            const horarioData = horarioSnap.data().horario;
            let componentes = new Set();
            Object.values(horarioData).forEach(aulasDoDia => { if(Array.isArray(aulasDoDia)) { aulasDoDia.forEach(aula => { if (aula) componentes.add(aula.split(' - ')[0]); }); } });
            if (isProfessor) {
                const servidorQuery = query(collection(db, 'servidores'), where('userId', '==', userData.uid));
                const servidorSnapshot = await getDocs(servidorQuery);
                if(!servidorSnapshot.empty){
                    const alocacoes = servidorSnapshot.docs[0].data().alocacoes || [];
                    const componentesDoProfessor = new Set();
                    alocacoes.forEach(aloc => { aloc.funcoes.forEach(f => { if (f.turmaId === selectedTurmaId) { (f.componentesCurriculares || []).forEach(c => componentesDoProfessor.add(c)); } }); });
                    componentes = new Set([...componentes].filter(c => componentesDoProfessor.has(c)));
                }
            }
            setAvailableComponentes(Array.from(componentes).sort());
        } else { setAvailableComponentes([]); }
    };
    populateComponentes();
    setSelectedComponente('');
  }, [selectedTurmaId, isProfessor, userData]);

  useEffect(() => {
    const fetchPeriods = async () => {
      if (!selectedYear) { setAvailablePeriods([]); return; }
      try {
        const q = query(collection(db, 'bimestres'), where('anoLetivo', '==', selectedYear.toString()), orderBy('dataInicio'));
        const snapshot = await getDocs(q);
        const bimestresList = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        const isBimestral = bimestresList.length > 0 && bimestresList[0].modoLancamento === 'Bimestral';
        if (isBimestral) { setAvailablePeriods(bimestresList.map(b => ({ value: b.id, label: b.nome }))); }
        else { const meses = Array.from({length: 12}, (_, i) => { const month = i + 1; const monthName = new Date(selectedYear, i, 1).toLocaleString('pt-BR', { month: 'long' }); return { value: month, label: monthName.charAt(0).toUpperCase() + monthName.slice(1) }; }); setAvailablePeriods(meses); }
      } catch (error) { console.error("Erro ao buscar períodos:", error); setAvailablePeriods([]); }
      finally { setSelectedPeriod(null); }
    };
    fetchPeriods();
  }, [selectedYear]);
  
  const selectedTurmaObject = selectedTurmaId ? availableTurmas.find(t => t.id === selectedTurmaId) : null;
  const showComponenteFilter = selectedTurmaObject && (selectedTurmaObject.nivelEnsino === "ENSINO FUNDAMENTAL - ANOS FINAIS" || selectedTurmaObject.nivelEnsino === "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS");

  const loadDiarioData = useCallback(async () => {
    if (!selectedTurmaId || !selectedPeriod || (showComponenteFilter && !selectedComponente)) {
        setAlunosDaTurma([]); setDiasLetivos([]); setFrequenciaData({}); return;
    };
    setLoading(true); setError('');
    try {
        const matriculasQuery = query(collection(db, 'matriculas'), where('turmaId', '==', selectedTurmaId), where('anoLetivo', '==', selectedYear.toString()));
        const matriculasSnap = await getDocs(matriculasQuery);
        const studentIds = matriculasSnap.docs.map(d => d.data().pessoaId);
        
        let alunos = [];
        if (studentIds.length > 0) {
            const alunosQuery = query(collection(db, 'pessoas'), where(documentId(), 'in', studentIds));
            const alunosSnap = await getDocs(alunosQuery);
            alunos = alunosSnap.docs.map(doc => ({ id: doc.id, ...doc.data() }));
            alunos.sort((a, b) => a.nomeCompleto.localeCompare(b.nomeCompleto));
        }
        setAlunosDaTurma(alunos);

        let dataInicio, dataFim;
        if (typeof selectedPeriod.value === 'number') {
            dataInicio = new Date(selectedYear, selectedPeriod.value - 1, 1);
            dataFim = new Date(selectedYear, selectedPeriod.value, 0);
        } else {
            const bimestreDoc = await getDoc(doc(db, 'bimestres', selectedPeriod.value));
            if (bimestreDoc.exists()) {
                const bData = bimestreDoc.data();
                const [startYear, startMonth, startDay] = bData.dataInicio.split('-').map(Number);
                dataInicio = new Date(startYear, startMonth - 1, startDay);
                const [endYear, endMonth, endDay] = bData.dataFim.split('-').map(Number);
                dataFim = new Date(endYear, endMonth - 1, endDay);
            }
        }
        
        const eventosQuery = query(collection(db, 'eventos'), where('anoLetivo', '==', selectedYear.toString()));
        const eventosSnap = await getDocs(eventosQuery);
        const feriados = new Set();
        eventosSnap.docs.forEach(d => { const evento = d.data(); if (evento.tipo.toUpperCase().includes('FERIADO')) { feriados.add(evento.data); } });

        const horarioRef = doc(db, 'horarios', selectedTurmaId);
        const horarioSnap = await getDoc(horarioRef);
        const horarioData = horarioSnap.exists() ? horarioSnap.data().horario : {};

        const dias = [];
        for (let d = new Date(dataInicio); d <= dataFim; d.setDate(d.getDate() + 1)) {
            const dataFormatada = d.toISOString().split('T')[0];
            if (feriados.has(dataFormatada)) { continue; }
            const diaDaSemana = d.getDay();
            if (diaDaSemana === 0 || diaDaSemana === 6) continue;
            const weekDayName = ["domingo", "segunda", "terca", "quarta", "quinta", "sexta", "sabado"][diaDaSemana];
            
            if (horarioData[weekDayName] && horarioData[weekDayName].length > 0) {
                const aulasDoDia = horarioData[weekDayName].map((aula, index) => ({ id: `aula${index + 1}`, nome: aula })).filter(aula => aula.nome).filter(aula => !showComponenteFilter || aula.nome.startsWith(selectedComponente));
                if (aulasDoDia.length > 0) { dias.push({ data: dataFormatada, aulas: aulasDoDia, bloqueado: false }); }
            }
        }
        setDiasLetivos(dias);

        const frequenciaQuery = query(collection(db, 'frequencias'), where('turmaId', '==', selectedTurmaId));
        const frequenciaSnap = await getDocs(frequenciaQuery);
        const freqData = {};
        frequenciaSnap.forEach(d => {
            const data = d.data();
            if (!freqData[data.alunoId]) freqData[data.alunoId] = {};
            if (!freqData[data.alunoId][data.data]) freqData[data.alunoId][data.data] = {};
            freqData[data.alunoId][data.data][data.aulaId] = data.status;
        });
        setFrequenciaData(freqData);

    } catch(err) { console.error("Erro detalhado ao carregar diário:", err); setError("Não foi possível carregar os dados do diário."); }
    finally { setLoading(false); }
  }, [selectedTurmaId, selectedPeriod, selectedYear, selectedComponente, showComponenteFilter]);

  useEffect(() => { loadDiarioData(); }, [loadDiarioData]);
  
  const handleFrequenciaChange = (alunoId, data, aulaId) => { setFrequenciaData(prev => { const newState = JSON.parse(JSON.stringify(prev)); if (!newState[alunoId]) newState[alunoId] = {}; if (!newState[alunoId][data]) newState[alunoId][data] = {}; const currentStatus = newState[alunoId][data][aulaId] || 'P'; const nextStatus = { P: 'F', F: 'J', J: 'P' }; newState[alunoId][data][aulaId] = nextStatus[currentStatus]; return newState; }); };
  
  const handleSaveFrequencia = async () => {
    if (!selectedTurmaId || !selectedPeriod) {
        setError("Selecione Escola, Turma e Período antes de salvar.");
        return;
    }

    setIsSubmitting(true);
    setError('');
    setSuccess('');

    try {
        const batch = writeBatch(db);

        for (const alunoId in frequenciaData) {
            for (const dataAula in frequenciaData[alunoId]) {
                for (const aulaId in frequenciaData[alunoId][dataAula]) {
                    const status = frequenciaData[alunoId][dataAula][aulaId];
                    // Criar um ID de documento único para evitar colisões
                    const docId = `${selectedTurmaId}_${alunoId}_${dataAula}_${aulaId}`;
                    const docRef = doc(db, "frequencias", docId);

                    batch.set(docRef, {
                        schoolId: selectedSchoolId,
                        turmaId: selectedTurmaId,
                        alunoId,
                        data: dataAula,
                        aulaId,
                        status,
                        anoLetivo: selectedYear.toString(),
                        componente: showComponenteFilter ? selectedComponente : "GERAL",
                        atualizadoEm: new Date(),
                        atualizadoPor: userData?.uid || null
                    });
                }
            }
        }

        await batch.commit();
        setSuccess("Frequência salva com sucesso!");
        setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
        console.error("Erro ao salvar frequência:", err);
        setError("Ocorreu um erro ao salvar a frequência.");
    } finally {
        setIsSubmitting(false);
    }
  };
  
  const handleGenerateReport = () => { if (!selectedSchoolId || !selectedTurmaId || !selectedPeriod) { alert("Para gerar o relatório, selecione Escola, Turma e Período."); return; } const componenteParam = showComponenteFilter && selectedComponente ? selectedComponente : 'DIARIO'; const periodValue = selectedPeriod.value; const url = `/relatorio/frequencia/${selectedSchoolId}/${selectedTurmaId}/${selectedYear}/${periodValue}/${componenteParam}`; window.open(url, '_blank'); };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Lançamento de Frequência</h2>
        <div className="text-sm text-gray-600 mb-4 p-2 bg-gray-50 rounded-md"><span className="font-bold">Legenda:</span><span className="inline-flex items-center ml-4"><div className="w-4 h-4 rounded-full bg-green-500 mr-1"></div> P = Presente</span><span className="inline-flex items-center ml-4"><div className="w-4 h-4 rounded-full bg-red-500 mr-1"></div> F = Falta</span><span className="inline-flex items-center ml-4"><div className="w-4 h-4 rounded-full bg-yellow-400 mr-1"></div> FJ = Falta Justificada</span></div>
        <div className="grid grid-cols-1 md:grid-cols-10 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <div className="md:col-span-5"><label htmlFor="escola-select" className="block text-sm font-medium text-gray-700 mb-1">Escola</label><select id="escola-select" value={selectedSchoolId} onChange={(e) => setSelectedSchoolId(e.target.value)} className="p-2 border rounded-md w-full"><option value="">Selecione a Escola</option>{availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}</select></div>
          <div className="md:col-span-3"><label htmlFor="turma-select" className="block text-sm font-medium text-gray-700 mb-1">Turma</label><select id="turma-select" value={selectedTurmaId} onChange={(e) => setSelectedTurmaId(e.target.value)} className="p-2 border rounded-md w-full" disabled={!selectedSchoolId}><option value="">Selecione a Turma</option>{availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}</select></div>
		  <div className="md:col-span-2"><label htmlFor="ano-input" className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label><input id="ano-input" type="number" value={selectedYear} onChange={(e) => setSelectedYear(parseInt(e.target.value))} className="p-2 border rounded-md w-full" /></div>
		  <div className="md:col-span-3"><label htmlFor="periodo-select" className="block text-sm font-medium text-gray-700 mb-1">Período</label><select id="periodo-select" value={selectedPeriod ? selectedPeriod.value : ''} onChange={(e) => { const v = e.target.value; setSelectedPeriod(availablePeriods.find(p => p.value.toString() === v)); }} className="p-2 border rounded-md w-full" disabled={!selectedYear || availablePeriods.length === 0}><option value="">Selecione o Período</option>{availablePeriods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}</select></div>
          {showComponenteFilter && (<div className="md:col-span-7"><label htmlFor="componente-select" className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular</label><select id="componente-select" value={selectedComponente} onChange={(e) => setSelectedComponente(e.target.value)} className="p-2 border rounded-md w-full" disabled={!selectedTurmaId}><option value="">Selecione o Componente</option>{availableComponentes.map(c => <option key={c} value={c}>{c}</option>)}</select></div>)}
        </div>
        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}
        <div className="overflow-x-auto"><table className="min-w-full bg-white border-collapse"><thead><tr className="bg-gray-200 text-gray-600 uppercase text-xs"><th className="py-2 px-2 border text-left sticky left-0 bg-gray-200 z-10" style={{minWidth: '250px'}}>Aluno</th>{diasLetivos.map((dia) => (<th key={dia.data} className="py-2 px-1 border text-center relative" colSpan={dia.aulas.length || 1}>{formatDate(dia.data).slice(0, 5)}<div className="absolute top-0 bottom-0 -right-px w-0.5 bg-gray-400"></div></th>))}</tr></thead><tbody className="text-gray-700">{loading ? (<tr><td colSpan={100} className="text-center p-4">Carregando diário...</td></tr>) : alunosDaTurma.length === 0 && selectedTurmaId && selectedPeriod ? (<tr><td colSpan={100} className="text-center p-4 text-gray-500">Nenhum aluno encontrado para esta turma.</td></tr>) : (alunosDaTurma.map((aluno) => (<tr key={aluno.id} className="border-b hover:bg-gray-50"><td className="py-2 px-2 border sticky left-0 bg-white hover:bg-gray-50 z-10">{aluno.nomeCompleto}</td>{diasLetivos.map((dia) => dia.bloqueado ? (<td key={dia.data} colSpan={dia.aulas.length || 1} className="py-2 px-1 border text-center bg-gray-200 text-gray-500 text-xs relative" title={dia.evento}>{dia.evento.split(':')[0]}<div className="absolute top-0 bottom-0 -right-px w-0.5 bg-gray-400"></div></td>) : dia.aulas.length > 0 ? (dia.aulas.map((aula, aulaIndex) => (<td key={`${dia.data}-${aula.id}`} className="py-2 px-1 border text-center relative"><div className="flex justify-center"><FrequenciaCell status={frequenciaData[aluno.id]?.[dia.data]?.[aula.id] || 'P'} onClick={() => handleFrequenciaChange(aluno.id, dia.data, aula.id)} isSaving={isSubmitting} /></div>{aulaIndex < dia.aulas.length - 1 && <div className="absolute top-0 bottom-0 right-0 w-px bg-gray-200"></div>}</td>))) : (<td key={dia.data} className="py-2 px-1 border bg-gray-50 relative"><div className="absolute top-0 bottom-0 -right-px w-0.5 bg-gray-400"></div></td>))}</tr>)))}</tbody></table></div>
        <div className="flex justify-end items-center mt-6 gap-4">{alunosDaTurma.length > 0 && (<><button onClick={handleGenerateReport} className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition" title="Gerar relatório em PDF da visualização atual">Gerar Relatório</button><button onClick={handleSaveFrequencia} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">{isSubmitting ? 'Salvando...' : 'Salvar Frequência'}</button></>)}</div>
      </div>
    </div>
  );
}

export default FrequenciaPage;