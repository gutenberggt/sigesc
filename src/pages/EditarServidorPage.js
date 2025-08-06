import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { collection, getDocs, query, where, doc, getDoc, updateDoc, deleteDoc } from 'firebase/firestore';
import { useNavigate, useParams } from 'react-router-dom';
import { niveisDeEnsinoList } from './NiveisDeEnsinoPage';
import { seriesAnosEtapasData } from './SeriesAnosEtapasPage';
import { componentesCurricularesData } from './ComponentesCurricularesPage';
import axios from 'axios'; // ADIÇÃO: Importa a biblioteca axios

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
  
  const [alocacoes, setAlocacoes] = useState([]);
  const [editingAlocacaoIndex, setEditingAlocacaoIndex] = useState(null);
  const [currentEscolaId, setCurrentEscolaId] = useState('');
  const [currentAnoLetivo, setCurrentAnoLetivo] = useState(new Date().getFullYear().toString());
  const [currentFuncoes, setCurrentFuncoes] = useState([]);
  
  const [currentFuncao, setCurrentFuncao] = useState('');
  const [currentNiveis, setCurrentNiveis] = useState([]);
  const [currentTurmaId, setCurrentTurmaId] = useState('');
  const [currentComponentes, setCurrentComponentes] = useState([]);
  
  const [availableNiveis, setAvailableNiveis] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [availableComponentes, setAvailableComponentes] = useState([]);

  // ======================= INÍCIO DA CORREÇÃO =======================
  // ALTERAÇÃO: A função agora usa AXIOS para buscar os dados da sua API
  const fetchInitialData = useCallback(async () => {
    try {
      // Busca escolas primeiro para os dropdowns
      const schoolsResponse = await axios.get('/api/escolas');
      const schoolsList = schoolsResponse.data;
      setAvailableSchools(schoolsList);

      // Busca os dados do servidor específico
      const servidorResponse = await axios.get(`/api/servidores/${servidorId}`);
      const servidorData = servidorResponse.data;
      
      // Assume que a API já retorna os dados da pessoa e os nomes da escola/turma
      setSelectedPerson(servidorData.pessoa); 
      setAlocacoes(servidorData.alocacoes);

    } catch (err) {
      console.error("Erro ao carregar dados:", err);
      setError("Falha ao carregar dados para edição.");
    } finally {
      setLoading(false);
    }
  }, [servidorId]);
  // ======================== FIM DA CORREÇÃO =========================

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);
  
  useEffect(() => { /* Lógica de níveis (mantida) */ }, [currentEscolaId, availableSchools]);
  useEffect(() => { /* Lógica de turmas (mantida) */ }, [currentEscolaId, currentNiveis]);
  useEffect(() => { /* Lógica de componentes (mantida) */ }, [currentTurmaId, availableTurmas]);

  const handleAddFuncao = () => { /* ... (código original mantido) ... */ };
  const handleAddAlocacao = () => { /* ... (código original mantido) ... */ };
  const handleEditAlocacao = (index) => { /* ... (código original mantido) ... */ };
  const handleRemoveAlocacao = (index) => { /* ... (código original mantido) ... */ };
  const handleSave = async () => { /* ... (código original mantido) ... */ };
  const handleDelete = async () => { /* ... (código original mantido) ... */ };

  if (loading) return <div className="p-6 text-center">Carregando...</div>;

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">Editar Servidor</h2>
        
        <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700">Pessoa</label>
            <input 
                type="text"
                value={selectedPerson ? `${selectedPerson.nomeCompleto} - CPF: ${selectedPerson.cpf}` : ''}
                readOnly
                className="mt-1 block w-full p-2 border rounded-md bg-gray-100"
            />
        </div>
        
        <div className="p-4 border-2 border-dashed rounded-md bg-gray-50 mb-6">
            {/* ... (formulário de adicionar alocação mantido) ... */}
        </div>

        <div>
            <h3 className="text-xl font-semibold mb-2">Resumo das Alocações:</h3>
            {alocacoes.map((aloc, i) => (
                <div key={i} className="p-3 border rounded-md mb-2 bg-gray-100 flex justify-between items-center">
                    <div>
                        <p className="font-bold">{aloc.escolaNome} - {aloc.anoLetivo}</p>
                        <ul className="list-disc list-inside ml-4 text-sm">
                            {aloc.funcoes.map((f, j) => <li key={j}>{f.funcao}</li>)}
                        </ul>
                    </div>
                    <div className="space-x-2">
                        <button onClick={() => handleEditAlocacao(i)} className="text-blue-600 hover:text-blue-800 text-sm">Editar</button>
                        <button onClick={() => handleRemoveAlocacao(i)} className="text-red-600 hover:text-red-800 text-sm">Remover</button>
                    </div>
                </div>
            ))}
        </div>

        {error && <p className="text-red-500 mt-4">{error}</p>}
        {success && <p className="text-green-500 mt-4">{success}</p>}

        <div className="flex justify-end space-x-4 mt-6">
            <button onClick={() => navigate(-1)} className="bg-gray-300 text-gray-800 py-2 px-4 rounded">Cancelar</button>
            <button onClick={handleDelete} disabled={isSubmitting} className="bg-red-600 text-white py-2 px-4 rounded">Excluir Servidor</button>
            <button onClick={handleSave} disabled={isSubmitting} className="bg-green-600 text-white py-2 px-4 rounded">{isSubmitting ? 'Salvando...' : 'Salvar Alterações'}</button>
        </div>
      </div>
    </div>
  );
}

export default EditarServidorPage;