import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc, query, where, getDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate, useParams } from 'react-router-dom';

// ======================= INÍCIO DA CORREÇÃO =======================
import { niveisDeEnsinoList, seriesAnosEtapasData } from '../data/ensinoConstants';
// ======================== FIM DA CORREÇÃO =========================
import { turmaModel } from '../firebase/dataModels';

function TurmasPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const { schoolId } = useParams();

  const [turmas, setTurmas] = useState([]);
  const [editingTurma, setEditingTurma] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  const [schoolName, setSchoolName] = useState('');
  const [schoolNiveisEnsino, setSchoolNiveisEnsino] = useState([]);
  const [schoolAnosSeries, setSchoolAnosSeries] = useState([]);

  // Estados do Formulário de Turma
  const [nomeTurma, setNomeTurma] = useState('');
  const [nivelEnsino, setNivelEnsino] = useState('');
  const [anoSerie, setAnoSerie] = useState('');
  const [turno, setTurno] = useState('Manhã');
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [professoresIds, setProfessoresIds] = useState([]);
  const [limiteVagas, setLimiteVagas] = useState('');
  const [salaAula, setSalaAula] = useState('');

  const [availableAnosSeries, setAvailableAnosSeries] = useState([]);

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    const newAvailableAnosSeries = new Set();
    if (nivelEnsino) {
      if (seriesAnosEtapasData[nivelEnsino]) {
        seriesAnosEtapasData[nivelEnsino].forEach(item => {
          if (schoolAnosSeries.includes(item)) {
              newAvailableAnosSeries.add(item);
          }
        });
      }
    }
    setAvailableAnosSeries(Array.from(newAvailableAnosSeries));
    if (anoSerie && !Array.from(newAvailableAnosSeries).includes(anoSerie)) {
      setAnoSerie('');
    }
  }, [nivelEnsino, anoSerie, schoolAnosSeries]);


  const resetForm = () => {
    setNomeTurma('');
    setNivelEnsino('');
    setAnoSerie('');
    setTurno('Manhã');
    setAnoLetivo(new Date().getFullYear().toString());
    setProfessoresIds([]);
    setLimiteVagas('');
    setSalaAula('');
    setErrorMessage('');
    setSuccessMessage('');
    setEditingTurma(null);
  };

  const filteredTurmas = turmas.filter(turma =>
    (turma.nomeTurma && turma.nomeTurma.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (turma.anoSerie && turma.anoSerie.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (turma.nivelEnsino && turma.nivelEnsino.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  useEffect(() => {
    if (!loading && schoolId) {
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }
      if (userData.funcao.toLowerCase() === 'secretario') {
         const userSchools = userData.escolasIds || (userData.escolaId ? [userData.escolaId] : []);
         if (!userSchools.includes(schoolId)) {
           setErrorMessage("Acesso negado: Você não está associado a esta escola.");
           setTurmas([]);
           return;
         }
      }

      const fetchData = async () => {
        try {
          const schoolDocRef = doc(db, 'schools', schoolId);
          const schoolDocSnap = await getDoc(schoolDocRef);
          if (schoolDocSnap.exists()) {
            setSchoolName(schoolDocSnap.data().nomeEscola);
            setSchoolNiveisEnsino(schoolDocSnap.data().niveisEnsino || []);
            setSchoolAnosSeries(schoolDocSnap.data().anosSeriesAtendidas || []);
          } else {
            setErrorMessage("Erro: Escola não encontrada.");
            setSchoolName('Escola Desconhecida');
            setSchoolNiveisEnsino([]);
            setSchoolAnosSeries([]);
          }

          const turmasColRef = collection(db, 'turmas');
          const q = query(turmasColRef, where('schoolId', '==', schoolId));
          const turmaSnapshot = await getDocs(q);
          const turmaList = turmaSnapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data()
          }));
          setTurmas(turmaList);
        } catch (error) {
          console.error("Erro ao buscar dados da página de turmas:", error);
          setErrorMessage("Erro ao carregar dados da página de turmas.");
        }
      };
      fetchData();
    }
  }, [loading, userData, navigate, schoolId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    if (!nomeTurma || !nivelEnsino || !anoSerie || !turno || !anoLetivo) {
      setErrorMessage('Todos os campos obrigatórios devem ser preenchidos.');
      return;
    }
    if (!schoolId) {
      setErrorMessage('ID da escola não fornecido. Não é possível cadastrar a turma.');
      return;
    }

    const turmaData = {
      ...turmaModel,
      nomeTurma: nomeTurma.toUpperCase(),
      nivelEnsino: nivelEnsino, // Mantém o case original do constant
      anoSerie: anoSerie, // Mantém o case original do constant
      turno,
      anoLetivo,
      professoresIds: professoresIds || [],
      limiteVagas: limiteVagas ? parseInt(limiteVagas, 10) : null,
      salaAula: salaAula.toUpperCase(),
      schoolId,
    };

    try {
      if (editingTurma) {
        const turmaDocRef = doc(db, 'turmas', editingTurma.id);
        await updateDoc(turmaDocRef, {
          ...turmaData,
          ultimaAtualizacao: new Date(),
        });
        setSuccessMessage('Turma atualizada com sucesso!');
        setTurmas(turmas.map(t => t.id === editingTurma.id ? { ...t, ...turmaData } : t));
      } else {
        const newTurmaData = {
          ...turmaData,
          dataCriacao: new Date(),
          ultimaAtualizacao: new Date(),
        };
        const docRef = await addDoc(collection(db, 'turmas'), newTurmaData);
        setSuccessMessage('Turma cadastrada com sucesso!');
        setTurmas([...turmas, { id: docRef.id, ...newTurmaData }]);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar turma:", error);
      setErrorMessage("Erro ao salvar dados da turma: " + error.message);
    }
  };

  const handleEdit = (turmaToEdit) => {
    setEditingTurma(turmaToEdit);
    setNomeTurma(turmaToEdit.nomeTurma || '');
    setNivelEnsino(turmaToEdit.nivelEnsino || '');
    setAnoSerie(turmaToEdit.anoSerie || '');
    setTurno(turmaToEdit.turno || 'Manhã');
    setAnoLetivo(turmaToEdit.anoLetivo || new Date().getFullYear().toString());
    setProfessoresIds(turmaToEdit.professoresIds || []);
    setLimiteVagas(turmaToEdit.limiteVagas || '');
    setSalaAula(turmaToEdit.salaAula || '');
    setErrorMessage('');
    setSuccessMessage('');
  };

  const handleDelete = async (turmaId) => {
    if (window.confirm('Tem certeza que deseja excluir esta turma? Esta ação não pode ser desfeita!')) {
      try {
        await deleteDoc(doc(db, 'turmas', turmaId));
        setSuccessMessage('Turma excluída com sucesso!');
        setTurmas(turmas.filter(turma => turma.id !== turmaId));
      } catch (error) {
        console.error("Erro ao excluir turma:", error);
        setErrorMessage("Erro ao excluir turma: " + error.message);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando...
      </div>
    );
  }

  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingTurma ? 'EDITAR TURMA' : 'CADASTRAR NOVA TURMA'} {schoolName && `NA ESCOLA ${schoolName.toUpperCase()}`}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="nomeTurma" className="block text-sm font-medium text-gray-700">Nome da Turma <span className="text-red-500">*</span></label>
            <input type="text" id="nomeTurma" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeTurma} onChange={(e) => setNomeTurma(e.target.value.toUpperCase())} required autoComplete="off" />
          </div>

          <div>
            <label htmlFor="anoLetivo" className="block text-sm font-medium text-gray-700">Ano Letivo <span className="text-red-500">*</span></label>
            <input type="text" id="anoLetivo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={anoLetivo} onChange={(e) => setAnoLetivo(e.target.value)} required autoComplete="off" />
          </div>

          <div>
            <label htmlFor="nivelEnsino" className="block text-sm font-medium text-gray-700">Nível de Ensino <span className="text-red-500">*</span></label>
            <select id="nivelEnsino" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={nivelEnsino} onChange={(e) => setNivelEnsino(e.target.value)} required autoComplete="off">
              <option value="">Selecione um Nível</option>
              {schoolNiveisEnsino.map((nivel, index) => (
                <option key={index} value={nivel}>{nivel}</option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="anoSerie" className="block text-sm font-medium text-gray-700">Ano/Série/Etapa <span className="text-red-500">*</span></label>
            <select id="anoSerie" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={anoSerie} onChange={(e) => setAnoSerie(e.target.value)} required disabled={!nivelEnsino} autoComplete="off">
              <option value="">Selecione um Ano/Série</option>
              {availableAnosSeries.length > 0 ? (
                availableAnosSeries.map((item, index) => (
                  <option key={index} value={item}>{item}</option>
                ))
              ) : (
                <option value="" disabled>Selecione um Nível de Ensino primeiro</option>
              )}
            </select>
          </div>

          <div>
            <label htmlFor="turno" className="block text-sm font-medium text-gray-700">Turno <span className="text-red-500">*</span></label>
            <select id="turno" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={turno} onChange={(e) => setTurno(e.target.value)} required autoComplete="off">
              <option value="Manhã">Manhã</option>
              <option value="Tarde">Tarde</option>
              <option value="Noite">Noite</option>
              <option value="Integral">Integral</option>
            </select>
          </div>

          <div>
            <label htmlFor="limiteVagas" className="block text-sm font-medium text-gray-700">Limite de Vagas</label>
            <input type="number" id="limiteVagas" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={limiteVagas} onChange={(e) => setLimiteVagas(e.target.value)} min="1" autoComplete="off" />
          </div>

          <div className="md:col-span-2">
            <label htmlFor="salaAula" className="block text-sm font-medium text-gray-700">Sala de Aula</label>
            <input type="text" id="salaAula" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={salaAula} onChange={(e) => setSalaAula(e.target.value.toUpperCase())} autoComplete="off" />
          </div>

          <div className="md:col-span-2 flex justify-end space-x-3 mt-4">
            {editingTurma && (
              <button
                type="button"
                onClick={resetForm}
                className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded"
              >
                Cancelar Edição
              </button>
            )}
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
            >
              {editingTurma ? 'Salvar Alterações' : 'Cadastrar Turma'}
            </button>
          </div>
        </form>

        <hr className="my-8" />

        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Turmas</h3>
        <div className="overflow-x-auto">
            <table className="min-w-full bg-white border border-gray-300 rounded-md">
              <thead>
                <tr className="bg-gray-200 text-gray-700 uppercase text-sm leading-normal">
                  <th className="py-3 px-6 text-left">Nome da Turma</th>
                  <th className="py-3 px-6 text-left">Nível de Ensino</th>
                  <th className="py-3 px-6 text-left">Ano/Série</th>
                  <th className="py-3 px-6 text-left">Turno</th>
                  <th className="py-3 px-6 text-left">Ano Letivo</th>
                  <th className="py-3 px-6 text-center">Ações</th>
                </tr>
              </thead>
              <tbody className="text-gray-600 text-sm font-light">
                {filteredTurmas.map((turma) => (
                  <tr key={turma.id} className="border-b border-gray-200 hover:bg-gray-100">
                    <td className="py-3 px-6 text-left whitespace-nowrap">{turma.nomeTurma}</td>
                    <td className="py-3 px-6 text-left">{turma.nivelEnsino}</td>
                    <td className="py-3 px-6 text-left">{turma.anoSerie}</td>
                    <td className="py-3 px-6 text-left">{turma.turno}</td>
                    <td className="py-3 px-6 text-left">{turma.anoLetivo}</td>
                    <td className="py-3 px-6 text-center">
                      <div className="flex item-center justify-center space-x-2">
                        <button onClick={() => handleEdit(turma)} className="bg-blue-500 hover:bg-blue-600 text-white p-2 rounded-full text-xs">
                          Editar
                        </button>
                        <button onClick={() => handleDelete(turma.id)} className="bg-red-500 hover:bg-red-600 text-white p-2 rounded-full text-xs">
                          Excluir
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
        </div>
      </div>
    </div>
  );
}

export default TurmasPage;