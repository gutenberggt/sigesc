import React, { useEffect, useReducer, useState } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, writeBatch, doc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';

const roundUp1 = (value) => {
  if (value === null || value === undefined || value === '') return '';
  const num = Number(value);
  if (Number.isNaN(num)) return '';
  return Math.ceil(num * 10) / 10;
};

const fmt1 = (value) => {
  if (value === '' || value === null || value === undefined) return '';
  const v = roundUp1(value);
  return v.toFixed(1);
};

const aplicarRecuperacoes = (B1, B2, R1, B3, B4, R2) => {
  let eB1 = B1 ?? 0, eB2 = B2 ?? 0, eB3 = B3 ?? 0, eB4 = B4 ?? 0;
  const r1 = R1 ?? 0, r2 = R2 ?? 0;

  if (r1 > 0) {
    if (eB1 < eB2) { if (r1 > eB1) eB1 = r1; }
    else if (eB2 < eB1) { if (r1 > eB2) eB2 = r1; }
    else { if (r1 > eB2) eB2 = r1; }
  }

  if (r2 > 0) {
    if (eB3 < eB4) { if (r2 > eB3) eB3 = r2; }
    else if (eB4 < eB3) { if (r2 > eB4) eB4 = r2; }
    else { if (r2 > eB4) eB4 = r2; }
  }

  return [eB1, eB2, eB3, eB4];
};

const calcularTotais = (B1, B2, R1, B3, B4, R2) => {
  const [eB1, eB2, eB3, eB4] = aplicarRecuperacoes(
    Number(B1 || 0), Number(B2 || 0), Number(R1 || 0), Number(B3 || 0), Number(B4 || 0), Number(R2 || 0)
  );
  const total = (eB1 * 2) + (eB2 * 3) + (eB3 * 2) + (eB4 * 3);
  const media = total / 10;
  return { total: roundUp1(total), media: roundUp1(media) };
};

const NotaInput = ({ value, onChange, disabled }) => (
  <input
    type="number"
    step="0.1"
    min="0"
    max="10"
    value={value === '' || value === null || value === undefined ? '' : value}
    onChange={(e) => {
      const v = e.target.value;
      if (v === '') return onChange('');
      const n = Number(v);
      if (!Number.isNaN(n)) onChange(n);
    }}
    onBlur={(e) => {
      const v = e.target.value;
      if (v === '') return;
      const n = Number(v);
      if (!Number.isNaN(n)) onChange(roundUp1(n));
    }}
    className={`w-20 p-1 border rounded text-center ${disabled ? 'bg-gray-100 text-gray-500' : ''}`}
    disabled={disabled}
  />
);

function NotasPage() {
  const { userData } = useUser();

  const initialFilters = { selectedSchoolId: '', selectedTurmaId: '', selectedComponente: '', selectedYear: new Date().getFullYear() };
  const [filters, setFilters] = useReducer((s, a) => ({ ...s, ...a }), initialFilters);

  const [availableSchools, setAvailableSchools] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [alunosDaTurma, setAlunosDaTurma] = useState([]);
  const [notas, setNotas] = useState({});
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isProfessor = userData?.funcao?.toLowerCase() === 'professor';
  const canEdit = isProfessor || userData?.funcao?.toLowerCase() === 'gestão';

  const selectedTurmaObject = availableTurmas.find(t => t.id === filters.selectedTurmaId);
  const isAnosFinais = selectedTurmaObject && (
    selectedTurmaObject.nivelEnsino === 'ENSINO FUNDAMENTAL - ANOS FINAIS' ||
    selectedTurmaObject.nivelEnsino === 'EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS'
  );

  const showComponenteFilter = isAnosFinais;

  useEffect(() => {
    const fetchInitialData = async () => {
      const schoolsSnapshot = await getDocs(collection(db, 'schools'));
      setAvailableSchools(schoolsSnapshot.docs.map(docu => ({ id: docu.id, ...docu.data() })));
    };
    fetchInitialData();
  }, []);

  useEffect(() => {
    const fetchTurmas = async () => {
      if (!filters.selectedSchoolId) return;
      const q = query(collection(db, 'turmas'), where('schoolId', '==', filters.selectedSchoolId));
      const snapshot = await getDocs(q);
      setAvailableTurmas(snapshot.docs.map(docu => ({ id: docu.id, ...docu.data() })));
    };
    fetchTurmas();
  }, [filters.selectedSchoolId]);

  useEffect(() => {
    const fetchComponentes = async () => {
      if (!filters.selectedTurmaId || !showComponenteFilter) return;
      const q = query(collection(db, 'componentes'), where('turmaId', '==', filters.selectedTurmaId));
      const snapshot = await getDocs(q);
      setAvailableComponentes(snapshot.docs.map(docu => ({ id: docu.id, ...docu.data() })));
    };
    fetchComponentes();
  }, [filters.selectedTurmaId, showComponenteFilter]);

  useEffect(() => {
    const fetchAlunosENotas = async () => {
      if (!filters.selectedTurmaId) return;
      setLoading(true);
      try {
        const alunosSnap = await getDocs(query(collection(db, 'matriculas'), where('turmaId', '==', filters.selectedTurmaId)));
        const alunosList = alunosSnap.docs.map(docu => ({ id: docu.id, ...docu.data() })).sort((a, b) => (a.numeroChamada || 0) - (b.numeroChamada || 0));
        setAlunosDaTurma(alunosList);

        const notasSnap = await getDocs(query(collection(db, 'notas'), where('turmaId', '==', filters.selectedTurmaId)));
        const notasMap = {};
        notasSnap.docs.forEach(docu => {
          notasMap[docu.data().alunoId] = docu.data();
        });
        setNotas(notasMap);
      } catch (err) {
        setError('Erro ao carregar alunos ou notas');
      } finally {
        setLoading(false);
      }
    };
    fetchAlunosENotas();
  }, [filters.selectedTurmaId]);

  const handleNotaChange = (alunoId, campo, valor) => {
    setNotas(prev => ({
      ...prev,
      [alunoId]: {
        ...prev[alunoId],
        [campo]: valor
      }
    }));
  };

  const handleSaveNotas = async () => {
    if (!filters.selectedTurmaId) return;
    setIsSubmitting(true);
    setError('');
    setSuccess('');
    try {
      const batch = writeBatch(db);
      for (const alunoId of Object.keys(notas)) {
        const ref = doc(db, 'notas', `${filters.selectedTurmaId}_${alunoId}`);
        batch.set(ref, {
          turmaId: filters.selectedTurmaId,
          componenteId: filters.selectedComponente || '',
          alunoId,
          ...notas[alunoId],
          updatedAt: new Date()
        }, { merge: true });
      }
      await batch.commit();
      setSuccess('Notas salvas com sucesso!');
    } catch (err) {
      setError('Erro ao salvar notas.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGenerateReport = () => {
    window.print();
  };

  const anos = [new Date().getFullYear(), new Date().getFullYear() - 1, new Date().getFullYear() - 2];

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-full mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Lançamento de Notas</h2>
        <div className="grid grid-cols-1 md:grid-cols-10 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <div className="md:col-span-3">
            <label htmlFor="escola-select" className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
            <select id="escola-select" value={filters.selectedSchoolId} onChange={(e) => setFilters({ selectedSchoolId: e.target.value, selectedTurmaId: '', selectedComponente: '' })} className="p-2 border rounded-md w-full">
              <option value="">Selecione a Escola</option>
              {availableSchools.map(s => <option key={s.id} value={s.id}>{s.nomeEscola}</option>)}
            </select>
          </div>

          <div className="md:col-span-3">
            <label htmlFor="turma-select" className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
            <select id="turma-select" value={filters.selectedTurmaId} onChange={(e) => setFilters({ selectedTurmaId: e.target.value, selectedComponente: '' })} className="p-2 border rounded-md w-full" disabled={!filters.selectedSchoolId}>
              <option value="">Selecione a Turma</option>
              {availableTurmas.map(t => <option key={t.id} value={t.id}>{t.nomeTurma}</option>)}
            </select>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="ano-select" className="block text-sm font-medium text-gray-700 mb-1">Ano</label>
            <select id="ano-select" value={filters.selectedYear} onChange={(e) => setFilters({ selectedYear: e.target.value })} className="p-2 border rounded-md w-full">
              {anos.map(ano => <option key={ano} value={ano}>{ano}</option>)}
            </select>
          </div>

          {showComponenteFilter && (
            <div className="md:col-span-2">
              <label htmlFor="componente-select" className="block text-sm font-medium text-gray-700 mb-1">Componente</label>
              <select id="componente-select" value={filters.selectedComponente} onChange={(e) => setFilters({ selectedComponente: e.target.value })} className="p-2 border rounded-md w-full">
                <option value="">Selecione o Componente</option>
                {availableComponentes.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
              </select>
            </div>
          )}

        </div>

        {!isAnosFinais && filters.selectedTurmaId && (
          <p className="text-red-500 mb-4">Lançamento de notas disponível apenas para Ensino Fundamental - Anos Finais.</p>
        )}

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}

        {loading && <p className="text-center text-gray-500">Carregando dados...</p>}

        {!loading && alunosDaTurma.length > 0 && (
          <div className="overflow-x-auto max-h-[70vh]">
            <table className="min-w-full bg-white border-collapse">
              <thead>
                <tr className="bg-gray-200 text-gray-600 uppercase text-xs">
                  <th className="py-2 px-2 border">Nº</th>
                  <th className="py-2 px-2 border">Aluno</th>
                  <th className="py-2 px-2 border">1º Bim</th>
                  <th className="py-2 px-2 border">2º Bim</th>
                  <th className="py-2 px-2 border">Recup. 1</th>
                  <th className="py-2 px-2 border">3º Bim</th>
                  <th className="py-2 px-2 border">4º Bim</th>
                  <th className="py-2 px-2 border">Recup. 2</th>
                  <th className="py-2 px-2 border">Total</th>
                  <th className="py-2 px-2 border">Média</th>
                </tr>
              </thead>
              <tbody>
                {alunosDaTurma.map(aluno => {
                  const row = notas[aluno.id] || { b1:'', b2:'', r1:'', b3:'', b4:'', r2:'' };
                  const { total, media } = calcularTotais(row.b1||0, row.b2||0, row.r1||0, row.b3||0, row.b4||0, row.r2||0);
                  return (
                    <tr key={aluno.id}>
                      <td className="border text-center">{aluno.numeroChamada ?? ''}</td>
                      <td className="border">{aluno.nomeCompleto}</td>
                      <td className="border text-center"><NotaInput value={row.b1} onChange={(v) => handleNotaChange(aluno.id, 'b1', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center"><NotaInput value={row.b2} onChange={(v) => handleNotaChange(aluno.id, 'b2', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center"><NotaInput value={row.r1} onChange={(v) => handleNotaChange(aluno.id, 'r1', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center"><NotaInput value={row.b3} onChange={(v) => handleNotaChange(aluno.id, 'b3', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center"><NotaInput value={row.b4} onChange={(v) => handleNotaChange(aluno.id, 'b4', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center"><NotaInput value={row.r2} onChange={(v) => handleNotaChange(aluno.id, 'r2', v)} disabled={!canEdit || isSubmitting} /></td>
                      <td className="border text-center font-semibold">{fmt1(total)}</td>
                      <td className="border text-center font-semibold">{fmt1(media)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {alunosDaTurma.length > 0 && (
          <div className="flex justify-end items-center mt-6 gap-4">
            <button onClick={handleGenerateReport} className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition">Gerar Relatório</button>
            <button onClick={handleSaveNotas} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">{isSubmitting ? 'Salvando...' : 'Salvar Notas'}</button>
          </div>
        )}

      </div>
    </div>
  );
}

export default NotasPage;
