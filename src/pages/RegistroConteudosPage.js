import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, documentId, doc, getDoc, orderBy, writeBatch } from 'firebase/firestore';
import { useUser } from '../context/UserContext';

function RegistroConteudosPage() {
  const { userData } = useUser();

  // Estados dos Filtros
  const [availableSchools, setAvailableSchools] = useState([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState('');
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [selectedTurmaId, setSelectedTurmaId] = useState('');
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [selectedComponente, setSelectedComponente] = useState('');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [availablePeriods, setAvailablePeriods] = useState([]);
  const [selectedPeriod, setSelectedPeriod] = useState(null);
  
  // Estados da Página
  const [diasLetivos, setDiasLetivos] = useState([]);
  const [conteudosData, setConteudosData] = useState({});
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isProfessor = userData?.funcao?.toLowerCase() === 'professor';

  // Lógica para carregar os filtros (reutilizada da frequenciaPage)
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
      } else { setAvailableSchools(allSchools); }
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
          if (turmasIds.length > 0) { turmasQuery = query(turmasQuery, where(documentId(), 'in', [...new Set(turmasIds)])); }
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

  const loadConteudoData = useCallback(async () => {
    if (!selectedTurmaId || !selectedPeriod || (showComponenteFilter && !selectedComponente)) {
        setDiasLetivos([]); setConteudosData({}); return;
    };
    setLoading(true); setError('');
    try {
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
            if (feriados.has(dataFormatada)) continue;
            const diaDaSemana = d.getDay();
            if (diaDaSemana === 0 || diaDaSemana === 6) continue;
            const weekDayName = ["domingo", "segunda", "terca", "quarta", "quinta", "sexta", "sabado"][diaDaSemana];
            if (horarioData[weekDayName] && horarioData[weekDayName].length > 0) {
                const aulasDoDia = horarioData[weekDayName].filter(aula => aula).filter(aula => !showComponenteFilter || aula.startsWith(selectedComponente));
                if (aulasDoDia.length > 0) { dias.push({ data: dataFormatada }); }
            }
        }
        setDiasLetivos(dias);

        // Carregar conteúdos já salvos
        const conteudosQuery = query(collection(db, 'conteudos'), where('turmaId', '==', selectedTurmaId), where('componente', '==', selectedComponente));
        const conteudosSnap = await getDocs(conteudosQuery);
        const conteudosGravados = {};
        conteudosSnap.forEach(d => {
            const data = d.data();
            conteudosGravados[data.data] = {
                objetos: data.objetosDeConhecimento,
                atividades: data.atividadesRealizadas
            };
        });
        setConteudosData(conteudosGravados);

    } catch(err) { console.error("Erro ao carregar dados:", err); setError("Não foi possível carregar os dados."); }
    finally { setLoading(false); }
  }, [selectedTurmaId, selectedPeriod, selectedYear, selectedComponente, showComponenteFilter]);

  useEffect(() => { loadConteudoData(); }, [loadConteudoData]);
  
  const handleConteudoChange = (data, field, value) => {
    setConteudosData(prev => ({
        ...prev,
        [data]: {
            ...prev[data],
            [field]: value
        }
    }));
  };
  
  const handleSaveConteudos = async () => {
    setIsSubmitting(true);
    setError('');
    setSuccess('');
    try {
        const batch = writeBatch(db);
        for (const data in conteudosData) {
            const conteudoDoDia = conteudosData[data];
            // Salva apenas se houver algum conteúdo
            if (conteudoDoDia.objetos || conteudoDoDia.atividades) {
                const docId = `${selectedTurmaId}_${data}_${selectedComponente || 'GERAL'}`;
                const docRef = doc(db, "conteudos", docId);
                batch.set(docRef, {
                    turmaId: selectedTurmaId,
                    schoolId: selectedSchoolId,
                    anoLetivo: selectedYear.toString(),
                    data: data,
                    componente: selectedComponente || 'GERAL',
                    objetosDeConhecimento: conteudoDoDia.objetos || '',
                    atividadesRealizadas: conteudoDoDia.atividades || '',
                    lancadoPor: userData.uid,
                    ultimaAtualizacao: new Date()
                });
            }
        }
        await batch.commit();
        setSuccess('Conteúdos salvos com sucesso!');
        setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
        console.error("Erro ao salvar conteúdos:", err);
        setError("Ocorreu um erro ao salvar os conteúdos.");
    } finally {
        setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Objetos de Conhecimento</h2>
        <div className="grid grid-cols-1 md:grid-cols-10 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <div className="md:col-span-5"><label className="block text-sm font-medium text-gray-700 mb-1">Escola</label><select value={selectedSchoolId} onChange={(e) => setSelectedSchoolId(e.target.value)} className="p-2 border rounded-md w-full"><option value="">Selecione a Escola</option>{availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}</select></div>
          <div className="md:col-span-3"><label className="block text-sm font-medium text-gray-700 mb-1">Turma</label><select value={selectedTurmaId} onChange={(e) => setSelectedTurmaId(e.target.value)} className="p-2 border rounded-md w-full" disabled={!selectedSchoolId}><option value="">Selecione a Turma</option>{availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}</select></div>
		  <div className="md:col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label><input type="number" value={selectedYear} onChange={(e) => setSelectedYear(parseInt(e.target.value))} className="p-2 border rounded-md w-full" /></div>
		  <div className="md:col-span-3"><label className="block text-sm font-medium text-gray-700 mb-1">Período</label><select value={selectedPeriod ? selectedPeriod.value : ''} onChange={(e) => { const v = e.target.value; setSelectedPeriod(availablePeriods.find(p => p.value.toString() === v)); }} className="p-2 border rounded-md w-full" disabled={!selectedYear || availablePeriods.length === 0}><option value="">Selecione o Período</option>{availablePeriods.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}</select></div>
          {showComponenteFilter && (<div className="md:col-span-7"><label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular</label><select value={selectedComponente} onChange={(e) => setSelectedComponente(e.target.value)} className="p-2 border rounded-md w-full" disabled={!selectedTurmaId}><option value="">Selecione o Componente</option>{availableComponentes.map(c => <option key={c} value={c}>{c}</option>)}</select></div>)}
        </div>
        
        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}
        
        {loading ? <p className="text-center p-4">Carregando...</p> : (
            <div className="space-y-6">
                {diasLetivos.map(({ data }) => (
                    <div key={data} className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start border-b pb-4">
                        <div className="md:col-span-1 text-center">
                            <p className="font-bold text-lg text-blue-600">{data.substring(8, 10)}</p>
                            <p className="text-sm text-gray-500">{data.substring(5, 7)}</p>
                        </div>
                        <div className="md:col-span-5">
                            <label className="block text-sm font-semibold text-gray-700 mb-1">Objetos de Conhecimento</label>
                            <textarea
                                value={conteudosData[data]?.objetos || ''}
                                onChange={(e) => handleConteudoChange(data, 'objetos', e.target.value)}
                                rows="4"
                                className="w-full p-2 border rounded-md"
                            />
                        </div>
                        <div className="md:col-span-6">
                            <label className="block text-sm font-semibold text-gray-700 mb-1">Atividades Realizadas</label>
                            <textarea
                                value={conteudosData[data]?.atividades || ''}
                                onChange={(e) => handleConteudoChange(data, 'atividades', e.target.value)}
                                rows="4"
                                className="w-full p-2 border rounded-md"
                            />
                        </div>
                    </div>
                ))}

                {diasLetivos.length > 0 && (
                    <div className="flex justify-end mt-6">
                        <button onClick={handleSaveConteudos} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded transition">
                            {isSubmitting ? 'Salvando...' : 'Salvar Conteúdos'}
                        </button>
                    </div>
                )}
                {!loading && diasLetivos.length === 0 && selectedTurmaId && selectedPeriod && (
                    <p className="text-center p-4 text-gray-500">Nenhum dia letivo encontrado para o período e horário desta turma.</p>
                )}
            </div>
        )}
      </div>
    </div>
  );
}

export default RegistroConteudosPage;