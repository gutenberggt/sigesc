import React, { useState, useEffect } from 'react';
import { db } from '../firebase/config';
import { collection, addDoc, getDocs, doc, updateDoc, deleteDoc, query, where, getDoc } from 'firebase/firestore';
import { useUser } from '../context/UserContext';
import { useNavigate, useParams } from 'react-router-dom';

// Importar os dados de níveis de ensino e séries/anos/etapas (ainda necessários para mapeamento de séries)
import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';
import { turmaModel } from '../firebase/dataModels';

function TurmasPage() {
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const { schoolId } = useParams();

  const [turmas, setTurmas] = useState([]);
  const [editingTurma, setEditingTurma] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  const [schoolName, setSchoolName] = useState('');
  // --- NOVOS ESTADOS PARA NÍVEIS E ANOS/SÉRIES DA ESCOLA ---
  const [schoolNiveisEnsino, setSchoolNiveisEnsino] = useState([]); // Níveis da escola específica
  const [schoolAnosSeries, setSchoolAnosSeries] = useState([]); // Anos/Séries da escola específica

  // --- Estados do Formulário de Turma ---
  const [nomeTurma, setNomeTurma] = useState('');
  const [nivelEnsino, setNivelEnsino] = useState('');
  const [anoSerie, setAnoSerie] = useState('');
  const [turno, setTurno] = useState('Manhã');
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [professoresIds, setProfessoresIds] = useState([]);
  const [limiteVagas, setLimiteVagas] = useState('');
  const [salaAula, setSalaAula] = useState('');

  const [availableAnosSeries, setAvailableAnosSeries] = useState([]); // Para opções dinâmicas de ano/série (agora filtradas duplamente)

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // Efeito para atualizar anos/séries disponíveis com base no nível de ensino selecionado E nos anos/séries da escola
  useEffect(() => {
    const newAvailableAnosSeries = new Set();
    if (nivelEnsino) {
      const mappedNivel = {
        "Educação Infantil": "Educação Infantil",
        "Ensino Fundamental - Anos Iniciais": "Ensino Fundamental - Anos Iniciais",
        "Ensino Fundamental - Anos Finais": "Ensino Fundamental - Anos Finais",
        "Educação de Jovens e Adultos - EJA - Anos Iniciais": "Educação de Jovens e Adultos - EJA",
        "Educação de Jovens e Adultos - EJA - Anos Finais": "Educação de Jovens e Adultos - EJA",
      }[nivelEnsino] || nivelEnsino;

      if (seriesAnosEtapasData[mappedNivel]) {
        seriesAnosEtapasData[mappedNivel].forEach(item => {
          // AQUI: Filtra pelos anos/séries que a escola ATENDE
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
  }, [nivelEnsino, anoSerie, schoolAnosSeries]); // Adicionado schoolAnosSeries como dependência


  // Limpa o formulário (mantido)
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

  // Filtra turmas para a busca (mantido)
  const filteredTurmas = turmas.filter(turma =>
    (turma.nomeTurma && turma.nomeTurma.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (turma.anoSerie && turma.anoSerie.toLowerCase().includes(searchTerm.toLowerCase())) ||
    (turma.nivelEnsino && turma.nivelEnsino.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Efeito para carregar turmas existentes da escola, o nome da escola E os níveis/anos da escola
  useEffect(() => {
    if (!loading && schoolId) {
      // Verifica permissões (mantido)
      if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
        navigate('/dashboard');
        return;
      }
      // Se for secretário, verifica associação com a escola (mantido)
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
          // 1. Buscar o nome da escola E seus níveis/anos/séries ofertados
          const schoolDocRef = doc(db, 'schools', schoolId);
          const schoolDocSnap = await getDoc(schoolDocRef);
          if (schoolDocSnap.exists()) {
            setSchoolName(schoolDocSnap.data().nomeEscola);
            setSchoolNiveisEnsino(schoolDocSnap.data().niveisEnsino || []); // Carrega os níveis da escola
            setSchoolAnosSeries(schoolDocSnap.data().anosSeriesAtendidas || []); // Carrega os anos/séries da escola
          } else {
            setErrorMessage("Erro: Escola não encontrada.");
            setSchoolName('Escola Desconhecida');
            setSchoolNiveisEnsino([]);
            setSchoolAnosSeries([]);
          }

          // 2. Buscar as turmas vinculadas ao schoolId (mantido)
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

  // Função para lidar com o cadastro/edição de turma (mantido)
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    // Validações básicas (mantido)
    if (!nomeTurma || !nivelEnsino || !anoSerie || !turno || !anoLetivo) {
      setErrorMessage('Todos os campos obrigatórios devem ser preenchidos.');
      return;
    }
    if (!schoolId) {
      setErrorMessage('ID da escola não fornecido. Não é possível cadastrar a turma.');
      return;
    }

    // Cria o objeto de dados da turma (mantido)
    const turmaData = {
      ...turmaModel,
      nomeTurma: nomeTurma.toUpperCase(),
      nivelEnsino: nivelEnsino.toUpperCase(),
      anoSerie: anoSerie.toUpperCase(),
      turno,
      anoLetivo,
      professoresIds: professoresIds || [],
      limiteVagas: limiteVagas ? parseInt(limiteVagas, 10) : null,
      salaAula: salaAula.toUpperCase(),
      schoolId,
    };

    try {
      if (editingTurma) {
        // MODO EDIÇÃO (mantido)
        const turmaDocRef = doc(db, 'turmas', editingTurma.id);
        await updateDoc(turmaDocRef, {
          ...turmaData,
          ultimaAtualizacao: new Date(),
        });
        setSuccessMessage('Turma atualizada com sucesso!');
        setTurmas(turmas.map(t => t.id === editingTurma.id ? { ...t, ...turmaData } : t));
      } else {
        // MODO CADASTRO DE NOVA TURMA (mantido)
        const newTurmaData = {
          ...turmaData,
          dataCriacao: new Date(),
          ultimaAtualizacao: new Date(),
        };
        await addDoc(collection(db, 'turmas'), newTurmaData);
        setSuccessMessage('Turma cadastrada com sucesso!');
        const turmasColRef = collection(db, 'turmas');
        const q = query(turmasColRef, where('schoolId', '==', schoolId));
        const turmaSnapshot = await getDocs(q);
        const updatedTurmaList = turmaSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        setTurmas(updatedTurmaList);
      }
      resetForm();
    } catch (error) {
      console.error("Erro ao gerenciar turma:", error);
      setErrorMessage("Erro ao salvar dados da turma: " + error.message);
    }
  };

  // Funções para a tabela: handleEdit (mantido)
  const handleEdit = (turmaToEdit) => {
    setEditingTurma(turmaToEdit);
    setNomeTurma(turmaToEdit.nomeTurma || '');
    setNivelEnsino(turmaToEdit.nivelEnsino.toUpperCase() || '');
    setAnoSerie(turmaToEdit.anoSerie.toUpperCase() || '');
    setTurno(turmaToEdit.turno || 'Manhã');
    setAnoLetivo(turmaToEdit.anoLetivo || new Date().getFullYear().toString());
    setProfessoresIds(turmaToEdit.professoresIds || []);
    setLimiteVagas(turmaToEdit.limiteVagas || '');
    setSalaAula(turmaToEdit.salaAula || '');
    setErrorMessage('');
    setSuccessMessage('');
  };

  // Função handleDelete (mantido)
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

  // Verificação de permissão (mantido)
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        Carregando permissões...
      </div>
    );
  }

  if (!userData || !(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario'))) {
    return (
      <div className="flex justify-center items-center h-screen text-red-600 font-bold">
        Acesso Negado: Você não tem permissão para acessar esta página.
      </div>
    );
  }

  if (userData.funcao.toLowerCase() === 'secretario') {
    const userSchools = userData.escolasIds || (userData.escolaId ? [userData.escolaId] : []);
    if (!userSchools.includes(schoolId)) {
        return (
            <div className="flex justify-center items-center h-screen text-red-600 font-bold">
                Acesso Negado: Você não está associado à escola selecionada.
            </div>
        );
    }
  }


  return (
    <div className="flex-grow p-6">
      <div className="bg-white p-8 rounded-lg shadow-md">
        <h2 className="text-2xl font-bold mb-6 text-gray-800 text-center">
          {editingTurma ? 'EDITAR TURMA' : 'CADASTRAR NOVA TURMA'} {schoolName && `NA ${schoolName}`}
        </h2>

        {errorMessage && <p className="text-red-600 text-sm mb-4 text-center">{errorMessage}</p>}
        {successMessage && <p className="text-green-600 text-sm mb-4 text-center">{successMessage}</p>}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Nome da Turma (mantido) */}
          <div>
            <label htmlFor="nomeTurma" className="block text-sm font-medium text-gray-700">Nome da Turma <span className="text-red-500">*</span></label>
            <input type="text" id="nomeTurma" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={nomeTurma} onChange={(e) => setNomeTurma(e.target.value.toUpperCase())} required autoComplete="off" />
          </div>

          {/* Ano Letivo (mantido) */}
          <div>
            <label htmlFor="anoLetivo" className="block text-sm font-medium text-gray-700">Ano Letivo <span className="text-red-500">*</span></label>
            <input type="text" id="anoLetivo" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={anoLetivo} onChange={(e) => setAnoLetivo(e.target.value)} required autoComplete="off" />
          </div>

          {/* Nível de Ensino - AGORA FILTRADO PELOS NÍVEIS DA ESCOLA */}
          <div>
            <label htmlFor="nivelEnsino" className="block text-sm font-medium text-gray-700">Nível de Ensino <span className="text-red-500">*</span></label>
            <select id="nivelEnsino" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={nivelEnsino} onChange={(e) => setNivelEnsino(e.target.value)} required autoComplete="off">
              <option value="">Selecione um Nível</option>
              {schoolNiveisEnsino.map((nivel, index) => ( // Usando schoolNiveisEnsino
                <option key={index} value={nivel}>{nivel}</option>
              ))}
            </select>
          </div>

          {/* Ano/Série/Etapa - AGORA FILTRADO PELOS ANOS/SÉRIES DA ESCOLA E NÍVEL SELECIONADO */}
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

          {/* Turno (mantido) */}
          <div>
            <label htmlFor="turno" className="block text-sm font-medium text-gray-700">Turno <span className="text-red-500">*</span></label>
            <select id="turno" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={turno} onChange={(e) => setTurno(e.target.value)} required autoComplete="off">
              <option value="Manhã">Manhã</option>
              <option value="Tarde">Tarde</option>
              <option value="Noite">Noite</option>
              <option value="Integral">Integral</option>
            </select>
          </div>

          {/* Limite de Vagas (Opcional) (mantido) */}
          <div>
            <label htmlFor="limiteVagas" className="block text-sm font-medium text-gray-700">Limite de Vagas</label>
            <input type="number" id="limiteVagas" className="mt-1 block w-full p-2 border border-gray-300 rounded-md" value={limiteVagas} onChange={(e) => setLimiteVagas(e.target.value)} min="1" autoComplete="off" />
          </div>

          {/* Sala de Aula (Opcional) (mantido) */}
          <div className="md:col-span-2">
            <label htmlFor="salaAula" className="block text-sm font-medium text-gray-700">Sala de Aula</label>
            <input type="text" id="salaAula" className="mt-1 block w-full p-2 border border-gray-300 rounded-md uppercase" value={salaAula} onChange={(e) => setSalaAula(e.target.value.toUpperCase())} autoComplete="off" />
          </div>

          {/* Botões de Ação (mantido) */}
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

        {/* Tabela de Turmas Existentes (mantido) */}
        <h3 className="text-xl font-bold mb-4 text-gray-800 text-center">Lista de Turmas</h3>
        {filteredTurmas.length === 0 ? (
          <p className="text-center text-gray-600">Nenhuma turma cadastrada ou encontrada para esta escola.</p>
        ) : (
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
        )}
      </div>
    </div>
  );
}

export default TurmasPage;