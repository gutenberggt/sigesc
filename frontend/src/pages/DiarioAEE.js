import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, FileText, Calendar, Clock, Plus, Edit2, Trash2, Eye, Download,
  ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Search, Filter,
  BookOpen, Target, Activity, UserCheck, ClipboardList, MessageSquare, Home
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Labels para campos
const PUBLICO_ALVO_LABELS = {
  'deficiencia_fisica': 'Deficiência Física',
  'deficiencia_intelectual': 'Deficiência Intelectual',
  'deficiencia_visual': 'Deficiência Visual',
  'deficiencia_auditiva': 'Deficiência Auditiva',
  'surdocegueira': 'Surdocegueira',
  'transtorno_espectro_autista': 'Transtorno do Espectro Autista (TEA)',
  'altas_habilidades': 'Altas Habilidades/Superdotação',
  'deficiencia_multipla': 'Deficiência Múltipla'
};

const MODALIDADE_LABELS = {
  'individual': 'Individual',
  'pequeno_grupo': 'Pequeno Grupo',
  'coensino': 'Coensino',
  'mista': 'Mista'
};

const NIVEL_APOIO_LABELS = {
  'independente': 'Independente',
  'apoio_minimo': 'Apoio Mínimo',
  'apoio_moderado': 'Apoio Moderado',
  'apoio_total': 'Apoio Total'
};

const DIAS_SEMANA = {
  'segunda': 'Segunda',
  'terca': 'Terça',
  'quarta': 'Quarta',
  'quinta': 'Quinta',
  'sexta': 'Sexta'
};

const DiarioAEE = () => {
  const { user, accessToken } = useAuth();
  const token = accessToken;  // Alias para compatibilidade
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const navigate = useNavigate();
  
  // Estados principais
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('estudantes'); // estudantes, planos, atendimentos, diario
  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  
  // Dados
  const [estudantes, setEstudantes] = useState([]);
  const [planos, setPlanos] = useState([]);
  const [atendimentos, setAtendimentos] = useState([]);
  const [diarioData, setDiarioData] = useState(null);
  
  // Modais
  const [showPlanoModal, setShowPlanoModal] = useState(false);
  const [showAtendimentoModal, setShowAtendimentoModal] = useState(false);
  const [editingPlano, setEditingPlano] = useState(null);
  const [editingAtendimento, setEditingAtendimento] = useState(null);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [selectedPlano, setSelectedPlano] = useState(null);
  
  // Formulários
  const [planoForm, setPlanoForm] = useState({
    student_id: '',
    publico_alvo: '',
    criterio_elegibilidade: '',
    turma_origem_id: '',
    turma_origem_nome: '',
    professor_regente_id: '',
    professor_regente_nome: '',
    dias_atendimento: [],
    horario_inicio: '',
    horario_fim: '',
    modalidade: 'individual',
    carga_horaria_semanal: '',
    local_atendimento: 'Sala de Recursos Multifuncionais',
    barreiras: [],
    objetivos: [],
    recursos_acessibilidade: [],
    orientacoes_sala_comum: '',
    adequacoes_curriculares: '',
    data_inicio: '',
    data_revisao: '',
    status: 'rascunho',
    // Novos campos
    data_elaboracao: '',
    periodo_vigencia: '',
    linha_base_situacao_atual: '',
    linha_base_potencialidades: '',
    linha_base_dificuldades: '',
    linha_base_comunicacao: '',
    indicadores_progresso: '',
    frequencia_revisao: 'bimestral',
    criterios_ajuste: '',
    combinados_professor_regente: '',
    adaptacoes_por_componente: ''
  });
  
  const [atendimentoForm, setAtendimentoForm] = useState({
    plano_aee_id: '',
    student_id: '',
    data: '',
    horario_inicio: '',
    horario_fim: '',
    presente: true,
    motivo_ausencia: '',
    objetivo_trabalhado: '',
    atividade_realizada: '',
    recursos_utilizados: [],
    nivel_apoio: '',
    resposta_estudante: '',
    evidencias: '',
    encaminhamento_proximo: '',
    orientacao_sala_comum: '',
    observacoes: ''
  });
  
  const [alert, setAlert] = useState({ show: false, type: '', message: '' });
  const [students, setStudents] = useState([]);
  const [turmas, setTurmas] = useState([]);

  // Headers para requisições
  const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };

  // Busca escolas
  useEffect(() => {
    const fetchSchools = async () => {
      try {
        const response = await fetch(`${API_URL}/api/schools`, { headers: { 'Authorization': `Bearer ${tokenRef.current}` } });
        const data = await response.json();
        // Filtra escolas com AEE (se nenhuma tiver AEE, mostra todas para seleção)
        const allSchools = data.items || data || [];
        const schoolsWithAEE = allSchools.filter(s => s.aee);
        const schoolsToUse = schoolsWithAEE.length > 0 ? schoolsWithAEE : allSchools;
        
        setSchools(schoolsToUse);
        if (schoolsToUse.length > 0) {
          setSelectedSchool(schoolsToUse[0].id);
        } else {
          setLoading(false);
        }
      } catch (error) {
        console.error('Erro ao buscar escolas:', error);
        setLoading(false);
      }
    };
    if (token) fetchSchools();
  }, [token]);

  // Busca dados quando escola é selecionada
  const fetchData = useCallback(async () => {
    if (!selectedSchool || !token) return;
    
    setLoading(true);
    try {
      // Busca estudantes AEE
      const estudantesRes = await fetch(
        `${API_URL}/api/aee/estudantes?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const estudantesData = await estudantesRes.json();
      setEstudantes(estudantesData || []);
      
      // Busca planos
      const planosRes = await fetch(
        `${API_URL}/api/aee/planos?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const planosData = await planosRes.json();
      setPlanos(planosData.items || []);
      
      // Busca atendimentos
      const atendRes = await fetch(
        `${API_URL}/api/aee/atendimentos?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const atendData = await atendRes.json();
      setAtendimentos(atendData.items || []);
      
      // Busca diário consolidado
      const diarioRes = await fetch(
        `${API_URL}/api/aee/diario?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const diarioDataRes = await diarioRes.json();
      setDiarioData(diarioDataRes);
      
      // Busca alunos da escola para o modal
      const studentsRes = await fetch(
        `${API_URL}/api/students?school_id=${selectedSchool}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const studentsData = await studentsRes.json();
      setStudents(studentsData.items || studentsData || []);
      
      // Busca turmas da escola
      const turmasRes = await fetch(
        `${API_URL}/api/classes?school_id=${selectedSchool}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const turmasData = await turmasRes.json();
      setTurmas(turmasData.items || turmasData || []);
      
    } catch (error) {
      console.error('Erro ao buscar dados:', error);
      showAlert('error', 'Erro ao carregar dados do AEE');
    } finally {
      setLoading(false);
    }
  }, [selectedSchool, academicYear, token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const showAlert = (type, message) => {
    setAlert({ show: true, type, message });
    setTimeout(() => setAlert({ show: false, type: '', message: '' }), 5000);
  };

  // === HANDLERS DE PLANO ===
  const handleSavePlano = async () => {
    if (!planoForm.student_id || !planoForm.publico_alvo) {
      showAlert('error', 'Selecione o aluno e o público-alvo');
      return;
    }
    
    try {
      const payload = {
        ...planoForm,
        school_id: selectedSchool,
        academic_year: academicYear,
        professor_aee_id: user.id,
        professor_aee_nome: user.full_name
      };
      
      const url = editingPlano 
        ? `${API_URL}/api/aee/planos/${editingPlano.id}`
        : `${API_URL}/api/aee/planos`;
      
      const response = await fetch(url, {
        method: editingPlano ? 'PUT' : 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Erro ao salvar plano');
      }
      
      showAlert('success', editingPlano ? 'Plano atualizado com sucesso!' : 'Plano criado com sucesso!');
      setShowPlanoModal(false);
      setEditingPlano(null);
      resetPlanoForm();
      fetchData();
    } catch (error) {
      showAlert('error', error.message);
    }
  };

  const resetPlanoForm = () => {
    setPlanoForm({
      student_id: '',
      publico_alvo: '',
      criterio_elegibilidade: '',
      turma_origem_id: '',
      turma_origem_nome: '',
      professor_regente_id: '',
      professor_regente_nome: '',
      dias_atendimento: [],
      horario_inicio: '',
      horario_fim: '',
      modalidade: 'individual',
      carga_horaria_semanal: '',
      local_atendimento: 'Sala de Recursos Multifuncionais',
      barreiras: [],
      objetivos: [],
      recursos_acessibilidade: [],
      orientacoes_sala_comum: '',
      adequacoes_curriculares: '',
      data_inicio: '',
      data_revisao: '',
      status: 'rascunho',
      data_elaboracao: '',
      periodo_vigencia: '',
      linha_base_situacao_atual: '',
      linha_base_potencialidades: '',
      linha_base_dificuldades: '',
      linha_base_comunicacao: '',
      indicadores_progresso: '',
      frequencia_revisao: 'bimestral',
      criterios_ajuste: '',
      combinados_professor_regente: '',
      adaptacoes_por_componente: ''
    });
  };

  const handleEditPlano = (plano) => {
    setEditingPlano(plano);
    setPlanoForm({
      ...plano,
      dias_atendimento: plano.dias_atendimento || [],
      barreiras: plano.barreiras || [],
      objetivos: plano.objetivos || [],
      recursos_acessibilidade: plano.recursos_acessibilidade || []
    });
    setShowPlanoModal(true);
  };

  // === HANDLERS DE ATENDIMENTO ===
  const handleSaveAtendimento = async () => {
    if (!atendimentoForm.plano_aee_id || !atendimentoForm.data || !atendimentoForm.atividade_realizada) {
      showAlert('error', 'Preencha os campos obrigatórios');
      return;
    }
    
    try {
      const plano = planos.find(p => p.id === atendimentoForm.plano_aee_id);
      const payload = {
        ...atendimentoForm,
        school_id: selectedSchool,
        academic_year: academicYear,
        student_id: plano?.student_id || atendimentoForm.student_id,
        professor_aee_id: user.id,
        professor_aee_nome: user.full_name
      };
      
      const url = editingAtendimento
        ? `${API_URL}/api/aee/atendimentos/${editingAtendimento.id}`
        : `${API_URL}/api/aee/atendimentos`;
      
      const response = await fetch(url, {
        method: editingAtendimento ? 'PUT' : 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Erro ao salvar atendimento');
      }
      
      showAlert('success', editingAtendimento ? 'Atendimento atualizado!' : 'Atendimento registrado!');
      setShowAtendimentoModal(false);
      setEditingAtendimento(null);
      resetAtendimentoForm();
      fetchData();
    } catch (error) {
      showAlert('error', error.message);
    }
  };

  const resetAtendimentoForm = () => {
    setAtendimentoForm({
      plano_aee_id: '',
      student_id: '',
      data: new Date().toISOString().split('T')[0].split('-').reverse().join('/'),
      horario_inicio: '',
      horario_fim: '',
      presente: true,
      motivo_ausencia: '',
      objetivo_trabalhado: '',
      atividade_realizada: '',
      recursos_utilizados: [],
      nivel_apoio: '',
      resposta_estudante: '',
      evidencias: '',
      encaminhamento_proximo: '',
      orientacao_sala_comum: '',
      observacoes: ''
    });
  };

  const handleNovoAtendimento = (plano = null) => {
    resetAtendimentoForm();
    if (plano) {
      setAtendimentoForm(prev => ({
        ...prev,
        plano_aee_id: plano.id,
        student_id: plano.student_id,
        horario_inicio: plano.horario_inicio || '',
        horario_fim: plano.horario_fim || ''
      }));
    }
    setShowAtendimentoModal(true);
  };

  // === DOWNLOAD PDF ===
  const handleDownloadPDF = async (studentId = null) => {
    try {
      let url = `${API_URL}/api/aee/diario/pdf?school_id=${selectedSchool}&academic_year=${academicYear}`;
      if (studentId) url += `&student_id=${studentId}`;
      
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (!response.ok) throw new Error('Erro ao gerar PDF');
      
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `diario_aee_${academicYear}.pdf`;
      link.click();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      showAlert('error', 'Erro ao gerar PDF');
    }
  };

  // === COMPONENTES DE TABS ===
  const TabEstudantes = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-800">Estudantes Atendidos no AEE</h3>
        <button
          onClick={() => { resetPlanoForm(); setShowPlanoModal(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus size={18} />
          Novo Plano de AEE
        </button>
      </div>
      
      {estudantes.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <Users size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Nenhum estudante com Plano de AEE ativo</p>
          <p className="text-sm text-gray-400 mt-2">Clique em "Novo Plano de AEE" para cadastrar</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {estudantes.map((est) => (
            <div key={est.student_id} className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="font-semibold text-gray-900">{est.full_name}</h4>
                  <p className="text-sm text-gray-500">Matrícula: {est.enrollment_number || 'N/D'}</p>
                  <p className="text-sm text-gray-500">Turma Origem: {est.turma_origem || 'N/D'}</p>
                  <div className="flex gap-2 mt-2">
                    <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs">
                      {PUBLICO_ALVO_LABELS[est.publico_alvo] || est.publico_alvo}
                    </span>
                    <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs">
                      {MODALIDADE_LABELS[est.modalidade] || est.modalidade}
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleNovoAtendimento(planos.find(p => p.student_id === est.student_id))}
                    className="p-2 text-green-600 hover:bg-green-50 rounded"
                    title="Registrar Atendimento"
                  >
                    <Plus size={18} />
                  </button>
                  <button
                    onClick={() => handleDownloadPDF(est.student_id)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded"
                    title="Baixar Ficha PDF"
                  >
                    <Download size={18} />
                  </button>
                </div>
              </div>
              <div className="mt-3 text-xs text-gray-500">
                Atendimentos: {est.dias_atendimento?.map(d => DIAS_SEMANA[d]).join(', ') || 'N/D'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const TabPlanos = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-800">Planos de AEE</h3>
        <button
          onClick={() => { resetPlanoForm(); setShowPlanoModal(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus size={18} />
          Novo Plano
        </button>
      </div>
      
      {planos.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <FileText size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Nenhum plano cadastrado</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border rounded-lg">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Público-Alvo</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Modalidade</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Dias</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {planos.map((plano) => (
                <tr key={plano.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{plano.student_name}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{PUBLICO_ALVO_LABELS[plano.publico_alvo]}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{MODALIDADE_LABELS[plano.modalidade]}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {plano.dias_atendimento?.map(d => DIAS_SEMANA[d]?.charAt(0)).join(', ')}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs ${
                      plano.status === 'ativo' ? 'bg-green-100 text-green-700' :
                      plano.status === 'rascunho' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {plano.status === 'ativo' ? 'Ativo' : plano.status === 'rascunho' ? 'Rascunho' : plano.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center gap-2">
                      <button
                        onClick={() => handleEditPlano(plano)}
                        className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                        title="Editar"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => handleNovoAtendimento(plano)}
                        className="p-1 text-green-600 hover:bg-green-50 rounded"
                        title="Novo Atendimento"
                      >
                        <Plus size={16} />
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
  );

  const TabAtendimentos = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-800">Registro de Atendimentos</h3>
        <button
          onClick={() => handleNovoAtendimento()}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          disabled={planos.length === 0}
        >
          <Plus size={18} />
          Novo Atendimento
        </button>
      </div>
      
      {atendimentos.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <ClipboardList size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Nenhum atendimento registrado</p>
        </div>
      ) : (
        <div className="space-y-3">
          {atendimentos.slice(0, 20).map((atend) => (
            <div key={atend.id} className="bg-white border rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3">
                    <span className={`w-3 h-3 rounded-full ${atend.presente ? 'bg-green-500' : 'bg-red-500'}`}></span>
                    <span className="font-medium text-gray-900">{atend.student_name}</span>
                    <span className="text-sm text-gray-500">{atend.data}</span>
                    <span className="text-sm text-gray-400">{atend.horario_inicio} - {atend.horario_fim}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-2"><strong>Objetivo:</strong> {atend.objetivo_trabalhado}</p>
                  <p className="text-sm text-gray-600"><strong>Atividade:</strong> {atend.atividade_realizada}</p>
                  {atend.nivel_apoio && (
                    <span className="inline-block mt-2 px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">
                      {NIVEL_APOIO_LABELS[atend.nivel_apoio]}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => {
                    setEditingAtendimento(atend);
                    setAtendimentoForm(atend);
                    setShowAtendimentoModal(true);
                  }}
                  className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                >
                  <Edit2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const TabDiario = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-800">Diário AEE - Visão Consolidada</h3>
        <button
          onClick={() => handleDownloadPDF()}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          <Download size={18} />
          Baixar PDF Completo
        </button>
      </div>
      
      {diarioData && (
        <div className="space-y-6">
          {/* Resumo */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <Users size={24} className="mx-auto text-blue-600 mb-2" />
              <p className="text-2xl font-bold text-blue-700">{diarioData.total_estudantes}</p>
              <p className="text-sm text-blue-600">Estudantes</p>
            </div>
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <ClipboardList size={24} className="mx-auto text-green-600 mb-2" />
              <p className="text-2xl font-bold text-green-700">{atendimentos.length}</p>
              <p className="text-sm text-green-600">Atendimentos</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <FileText size={24} className="mx-auto text-purple-600 mb-2" />
              <p className="text-2xl font-bold text-purple-700">{planos.length}</p>
              <p className="text-sm text-purple-600">Planos Ativos</p>
            </div>
            <div className="bg-orange-50 rounded-lg p-4 text-center">
              <Clock size={24} className="mx-auto text-orange-600 mb-2" />
              <p className="text-2xl font-bold text-orange-700">
                {Math.round(atendimentos.reduce((acc, a) => acc + (a.duracao_minutos || 0), 0) / 60)}h
              </p>
              <p className="text-sm text-orange-600">Carga Horária</p>
            </div>
          </div>
          
          {/* Grade de Horários */}
          <div className="bg-white border rounded-lg p-4">
            <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Calendar size={18} />
              Grade de Atendimentos
            </h4>
            <div className="grid grid-cols-5 gap-2">
              {Object.entries(DIAS_SEMANA).map(([key, label]) => (
                <div key={key} className="border rounded p-2">
                  <h5 className="font-medium text-sm text-gray-700 border-b pb-1 mb-2">{label}</h5>
                  {diarioData.grade_horarios?.[key]?.map((item, idx) => (
                    <div key={idx} className="text-xs bg-blue-50 rounded p-1 mb-1">
                      <p className="font-medium truncate">{item.student_name}</p>
                      <p className="text-gray-500">{item.horario_inicio} - {item.horario_fim}</p>
                    </div>
                  )) || <p className="text-xs text-gray-400">-</p>}
                </div>
              ))}
            </div>
          </div>
          
          {/* Fichas Resumidas */}
          <div className="bg-white border rounded-lg p-4">
            <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Users size={18} />
              Fichas Individuais
            </h4>
            <div className="space-y-3">
              {diarioData.fichas?.map((ficha) => (
                <div key={ficha.student.id} className="border rounded-lg p-3 hover:bg-gray-50">
                  <div className="flex justify-between items-start">
                    <div>
                      <h5 className="font-medium text-gray-900">{ficha.student.full_name}</h5>
                      <p className="text-sm text-gray-500">
                        {PUBLICO_ALVO_LABELS[ficha.plano.publico_alvo]} | {MODALIDADE_LABELS[ficha.plano.modalidade]}
                      </p>
                    </div>
                    <div className="text-right text-sm">
                      <p className="text-green-600">{ficha.estatisticas.presencas} presenças</p>
                      <p className="text-gray-500">{ficha.estatisticas.carga_horaria_realizada_horas}h realizadas</p>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-4">
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-green-500 h-2 rounded-full"
                        style={{ width: `${ficha.estatisticas.frequencia_percentual}%` }}
                      ></div>
                    </div>
                    <span className="text-sm font-medium text-gray-600">
                      {ficha.estatisticas.frequencia_percentual}%
                    </span>
                    <button
                      onClick={() => handleDownloadPDF(ficha.student.id)}
                      className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                      title="Baixar PDF Individual"
                    >
                      <Download size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // === MODAL DE PLANO ===
  const PlanoModal = () => (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingPlano ? 'Editar Plano de AEE' : 'Novo Plano de AEE'}
          </h2>
          <button onClick={() => { setShowPlanoModal(false); setEditingPlano(null); }} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>
        
        <div className="p-6 space-y-6">
          {/* Identificação do Estudante */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Users size={18} />
              Identificacao do Estudante
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Aluno *</label>
                <select
                  value={planoForm.student_id}
                  onChange={(e) => {
                    const student = students.find(s => s.id === e.target.value);
                    const turma = turmas.find(t => t.id === student?.class_id);
                    setPlanoForm({
                      ...planoForm,
                      student_id: e.target.value,
                      turma_origem_id: student?.class_id || '',
                      turma_origem_nome: turma?.name || ''
                    });
                  }}
                  className="w-full border rounded-lg px-3 py-2"
                  disabled={!!editingPlano}
                >
                  <option value="">Selecione o aluno</option>
                  {students.map(s => (
                    <option key={s.id} value={s.id}>{s.full_name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Publico-Alvo da Educacao Especial (PAEE) *</label>
                <select
                  value={planoForm.publico_alvo}
                  onChange={(e) => setPlanoForm({ ...planoForm, publico_alvo: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                >
                  <option value="">Selecione</option>
                  {Object.entries(PUBLICO_ALVO_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">Caracterizacao das necessidades educacionais especificas</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma de Origem</label>
                <input
                  type="text"
                  value={planoForm.turma_origem_nome}
                  onChange={(e) => setPlanoForm({ ...planoForm, turma_origem_nome: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 bg-gray-50"
                  placeholder="Turma do aluno na sala regular"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Professor Regente</label>
                <input
                  type="text"
                  value={planoForm.professor_regente_nome}
                  onChange={(e) => setPlanoForm({ ...planoForm, professor_regente_nome: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  placeholder="Nome do professor da sala regular"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Justificativa Pedagogica para o AEE</label>
                <input
                  type="text"
                  value={planoForm.criterio_elegibilidade}
                  onChange={(e) => setPlanoForm({ ...planoForm, criterio_elegibilidade: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  placeholder="Descreva as barreiras e necessidades de apoio (sem mencionar CID ou laudo)"
                />
                <p className="text-xs text-gray-500 mt-1">Foco nas barreiras identificadas e nos apoios necessarios, nao no diagnostico</p>
              </div>
            </div>
          </div>

          {/* Vigencia do Plano */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Calendar size={18} />
              Vigencia do Plano
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Elaboracao</label>
                <input
                  type="date"
                  value={planoForm.data_elaboracao}
                  onChange={(e) => setPlanoForm({ ...planoForm, data_elaboracao: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Periodo de Vigencia</label>
                <select
                  value={planoForm.periodo_vigencia}
                  onChange={(e) => setPlanoForm({ ...planoForm, periodo_vigencia: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                >
                  <option value="">Selecione</option>
                  <option value="1_bimestre">1o Bimestre</option>
                  <option value="2_bimestre">2o Bimestre</option>
                  <option value="3_bimestre">3o Bimestre</option>
                  <option value="4_bimestre">4o Bimestre</option>
                  <option value="1_semestre">1o Semestre</option>
                  <option value="2_semestre">2o Semestre</option>
                  <option value="ano_letivo">Ano Letivo Completo</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Proxima Revisao</label>
                <input
                  type="date"
                  value={planoForm.data_revisao}
                  onChange={(e) => setPlanoForm({ ...planoForm, data_revisao: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
            </div>
          </div>

          {/* Linha de Base - Situacao Inicial */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <ClipboardList size={18} />
              Linha de Base (Situacao Inicial do Estudante)
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Situacao Atual</label>
                <textarea
                  value={planoForm.linha_base_situacao_atual}
                  onChange={(e) => setPlanoForm({ ...planoForm, linha_base_situacao_atual: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Como o estudante esta hoje em relacao a aprendizagem e participacao..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Potencialidades</label>
                <textarea
                  value={planoForm.linha_base_potencialidades}
                  onChange={(e) => setPlanoForm({ ...planoForm, linha_base_potencialidades: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Pontos fortes, habilidades e interesses do estudante..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dificuldades Observadas</label>
                <textarea
                  value={planoForm.linha_base_dificuldades}
                  onChange={(e) => setPlanoForm({ ...planoForm, linha_base_dificuldades: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Principais dificuldades e barreiras enfrentadas..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Formas de Comunicacao e Participacao</label>
                <textarea
                  value={planoForm.linha_base_comunicacao}
                  onChange={(e) => setPlanoForm({ ...planoForm, linha_base_comunicacao: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Como o estudante se comunica e participa das atividades..."
                />
              </div>
            </div>
          </div>
          
          {/* Cronograma */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Calendar size={18} />
              Cronograma de Atendimento
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Dias de Atendimento</label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(DIAS_SEMANA).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={planoForm.dias_atendimento.includes(key)}
                        onChange={(e) => {
                          const dias = e.target.checked
                            ? [...planoForm.dias_atendimento, key]
                            : planoForm.dias_atendimento.filter(d => d !== key);
                          setPlanoForm({ ...planoForm, dias_atendimento: dias });
                        }}
                        className="rounded"
                      />
                      <span className="text-sm">{label}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Modalidade</label>
                <select
                  value={planoForm.modalidade}
                  onChange={(e) => setPlanoForm({ ...planoForm, modalidade: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                >
                  {Object.entries(MODALIDADE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Horario Inicio</label>
                <input
                  type="time"
                  value={planoForm.horario_inicio}
                  onChange={(e) => setPlanoForm({ ...planoForm, horario_inicio: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Horario Fim</label>
                <input
                  type="time"
                  value={planoForm.horario_fim}
                  onChange={(e) => setPlanoForm({ ...planoForm, horario_fim: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horaria Semanal</label>
                <input
                  type="text"
                  value={planoForm.carga_horaria_semanal}
                  onChange={(e) => setPlanoForm({ ...planoForm, carga_horaria_semanal: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  placeholder="Ex: 4 horas"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Local de Atendimento</label>
                <input
                  type="text"
                  value={planoForm.local_atendimento}
                  onChange={(e) => setPlanoForm({ ...planoForm, local_atendimento: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
            </div>
          </div>

          {/* Objetivos e Barreiras */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Target size={18} />
              Objetivos e Barreiras
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Barreiras Identificadas</label>
                <textarea
                  value={Array.isArray(planoForm.barreiras) ? planoForm.barreiras.join('\n') : planoForm.barreiras}
                  onChange={(e) => setPlanoForm({ ...planoForm, barreiras: e.target.value.split('\n').filter(b => b.trim()) })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={3}
                  placeholder="Uma barreira por linha (ex: Comunicacao, Mobilidade, Aprendizagem...)"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Objetivos do Atendimento</label>
                <textarea
                  value={Array.isArray(planoForm.objetivos) ? planoForm.objetivos.join('\n') : planoForm.objetivos}
                  onChange={(e) => setPlanoForm({ ...planoForm, objetivos: e.target.value.split('\n').filter(o => o.trim()) })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={3}
                  placeholder="Um objetivo por linha"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Recursos de Acessibilidade</label>
                <textarea
                  value={Array.isArray(planoForm.recursos_acessibilidade) ? planoForm.recursos_acessibilidade.join('\n') : planoForm.recursos_acessibilidade}
                  onChange={(e) => setPlanoForm({ ...planoForm, recursos_acessibilidade: e.target.value.split('\n').filter(r => r.trim()) })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={3}
                  placeholder="Um recurso por linha (ex: Software de leitura, Prancha de comunicacao...)"
                />
              </div>
            </div>
          </div>

          {/* Estrategias de Acompanhamento */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Activity size={18} />
              Estrategias de Acompanhamento
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Indicadores de Progresso</label>
                <textarea
                  value={planoForm.indicadores_progresso}
                  onChange={(e) => setPlanoForm({ ...planoForm, indicadores_progresso: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Como sera avaliado o progresso do estudante (indicadores simples e observaveis)..."
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Frequencia de Revisao</label>
                  <select
                    value={planoForm.frequencia_revisao}
                    onChange={(e) => setPlanoForm({ ...planoForm, frequencia_revisao: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2"
                  >
                    <option value="mensal">Mensal</option>
                    <option value="bimestral">Bimestral</option>
                    <option value="trimestral">Trimestral</option>
                    <option value="semestral">Semestral</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Criterios para Ajustar Estrategias</label>
                  <input
                    type="text"
                    value={planoForm.criterios_ajuste}
                    onChange={(e) => setPlanoForm({ ...planoForm, criterios_ajuste: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2"
                    placeholder="Quando e como as estrategias serao revisadas..."
                  />
                </div>
              </div>
            </div>
          </div>
          
          {/* Articulacao com Sala Comum */}
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <MessageSquare size={18} />
              Articulacao com Sala Comum
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Orientacoes para Sala Comum</label>
                <textarea
                  value={planoForm.orientacoes_sala_comum}
                  onChange={(e) => setPlanoForm({ ...planoForm, orientacoes_sala_comum: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Orientacoes gerais para o professor regente..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Combinados com Professor Regente</label>
                <textarea
                  value={planoForm.combinados_professor_regente}
                  onChange={(e) => setPlanoForm({ ...planoForm, combinados_professor_regente: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Acordos especificos entre AEE e professor da sala regular..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Adaptacoes por Componente Curricular</label>
                <textarea
                  value={planoForm.adaptacoes_por_componente}
                  onChange={(e) => setPlanoForm({ ...planoForm, adaptacoes_por_componente: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Ex: Portugues - ampliacao de fonte; Matematica - uso de material concreto..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Adequacoes Curriculares</label>
                <textarea
                  value={planoForm.adequacoes_curriculares}
                  onChange={(e) => setPlanoForm({ ...planoForm, adequacoes_curriculares: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2"
                  rows={2}
                  placeholder="Adequacoes de acesso ao curriculo..."
                />
              </div>
            </div>
          </div>
          
          {/* Status */}
          <div className="flex items-center gap-4">
            <label className="block text-sm font-medium text-gray-700">Status do Plano:</label>
            <select
              value={planoForm.status}
              onChange={(e) => setPlanoForm({ ...planoForm, status: e.target.value })}
              className="border rounded-lg px-3 py-2"
            >
              <option value="rascunho">Rascunho</option>
              <option value="ativo">Ativo</option>
              <option value="revisao">Em Revisão</option>
              <option value="encerrado">Encerrado</option>
            </select>
          </div>
        </div>
        
        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-3">
          <button
            onClick={() => { setShowPlanoModal(false); setEditingPlano(null); }}
            className="px-4 py-2 border rounded-lg hover:bg-gray-100"
          >
            Cancelar
          </button>
          <button
            onClick={handleSavePlano}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            {editingPlano ? 'Atualizar' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );

  // === MODAL DE ATENDIMENTO ===
  const AtendimentoModal = () => (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-gray-900">
            {editingAtendimento ? 'Editar Atendimento' : 'Registrar Atendimento'}
          </h2>
          <button onClick={() => { setShowAtendimentoModal(false); setEditingAtendimento(null); }} className="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>
        
        <div className="p-6 space-y-6">
          {/* Identificação */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Plano/Estudante *</label>
              <select
                value={atendimentoForm.plano_aee_id}
                onChange={(e) => {
                  const plano = planos.find(p => p.id === e.target.value);
                  setAtendimentoForm({
                    ...atendimentoForm,
                    plano_aee_id: e.target.value,
                    student_id: plano?.student_id || '',
                    horario_inicio: plano?.horario_inicio || atendimentoForm.horario_inicio,
                    horario_fim: plano?.horario_fim || atendimentoForm.horario_fim
                  });
                }}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="">Selecione</option>
                {planos.map(p => (
                  <option key={p.id} value={p.id}>{p.student_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Data *</label>
              <input
                type="date"
                value={atendimentoForm.data?.split('/').reverse().join('-') || ''}
                onChange={(e) => {
                  const date = e.target.value.split('-').reverse().join('/');
                  setAtendimentoForm({ ...atendimentoForm, data: date });
                }}
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Horário Início</label>
              <input
                type="time"
                value={atendimentoForm.horario_inicio}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, horario_inicio: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Horário Fim</label>
              <input
                type="time"
                value={atendimentoForm.horario_fim}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, horario_fim: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
          </div>
          
          {/* Presença */}
          <div className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={atendimentoForm.presente}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, presente: e.target.checked })}
                className="rounded"
              />
              <span className="font-medium">Presente</span>
            </label>
            {!atendimentoForm.presente && (
              <input
                type="text"
                value={atendimentoForm.motivo_ausencia}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, motivo_ausencia: e.target.value })}
                className="flex-1 border rounded-lg px-3 py-2"
                placeholder="Motivo da ausência"
              />
            )}
          </div>
          
          {/* Registro Pedagógico */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Objetivo Trabalhado *</label>
              <input
                type="text"
                value={atendimentoForm.objetivo_trabalhado}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, objetivo_trabalhado: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
                placeholder="Objetivo do Plano de AEE trabalhado neste atendimento"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Atividade/Estratégia Realizada *</label>
              <textarea
                value={atendimentoForm.atividade_realizada}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, atividade_realizada: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
                rows={3}
                placeholder="Descreva a atividade realizada..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nível de Apoio</label>
              <select
                value={atendimentoForm.nivel_apoio}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, nivel_apoio: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="">Selecione</option>
                {Object.entries(NIVEL_APOIO_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Resposta do Estudante</label>
              <textarea
                value={atendimentoForm.resposta_estudante}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, resposta_estudante: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
                rows={2}
                placeholder="Descreva a resposta/comportamento do estudante..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Encaminhamento Próximo Encontro</label>
              <textarea
                value={atendimentoForm.encaminhamento_proximo}
                onChange={(e) => setAtendimentoForm({ ...atendimentoForm, encaminhamento_proximo: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
                rows={2}
                placeholder="O que será trabalhado no próximo encontro..."
              />
            </div>
          </div>
        </div>
        
        <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end gap-3">
          <button
            onClick={() => { setShowAtendimentoModal(false); setEditingAtendimento(null); }}
            className="px-4 py-2 border rounded-lg hover:bg-gray-100"
          >
            Cancelar
          </button>
          <button
            onClick={handleSaveAtendimento}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            {editingAtendimento ? 'Atualizar' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="p-6">
      {/* Alert */}
      {alert.show && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 ${
          alert.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
        }`}>
          {alert.type === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
          {alert.message}
        </div>
      )}
      
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <button 
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 text-gray-500 hover:text-blue-600 transition-colors"
          >
            <Home size={20} />
            <span>Início</span>
          </button>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BookOpen className="text-blue-600" />
            Diário AEE
          </h1>
        </div>
        <p className="text-gray-500">Atendimento Educacional Especializado</p>
      </div>
      
      {/* Filtros */}
      <div className="bg-white border rounded-lg p-4 mb-6 flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Escola/Polo AEE</label>
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            className="border rounded-lg px-3 py-2 min-w-[250px]"
          >
            {schools.length === 0 ? (
              <option value="">Carregando escolas...</option>
            ) : (
              schools.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))
            )}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label>
          <select
            value={academicYear}
            onChange={(e) => setAcademicYear(parseInt(e.target.value))}
            className="border rounded-lg px-3 py-2"
          >
            {[2024, 2025, 2026].map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="bg-white border rounded-lg">
        <div className="border-b flex">
          {[
            { id: 'estudantes', label: 'Estudantes', icon: Users },
            { id: 'planos', label: 'Planos de AEE', icon: FileText },
            { id: 'atendimentos', label: 'Atendimentos', icon: ClipboardList },
            { id: 'diario', label: 'Diário Consolidado', icon: BookOpen }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-4 font-medium transition-colors ${
                activeTab === tab.id
                  ? 'text-blue-600 border-b-2 border-blue-600'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon size={18} />
              {tab.label}
            </button>
          ))}
        </div>
        
        <div className="p-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent mx-auto"></div>
              <p className="text-gray-500 mt-4">Carregando...</p>
            </div>
          ) : schools.length === 0 ? (
            <div className="text-center py-12 bg-yellow-50 rounded-lg">
              <AlertCircle size={48} className="mx-auto text-yellow-500 mb-4" />
              <p className="text-yellow-700 font-medium">Nenhuma escola com AEE habilitado</p>
              <p className="text-sm text-yellow-600 mt-2">
                Para utilizar o Diário AEE, é necessário habilitar o AEE em pelo menos uma escola.
              </p>
              <p className="text-sm text-yellow-600 mt-1">
                Acesse o cadastro de escolas e marque a opção "AEE" nas escolas que oferecem este serviço.
              </p>
            </div>
          ) : (
            <>
              {activeTab === 'estudantes' && <TabEstudantes />}
              {activeTab === 'planos' && <TabPlanos />}
              {activeTab === 'atendimentos' && <TabAtendimentos />}
              {activeTab === 'diario' && <TabDiario />}
            </>
          )}
        </div>
      </div>
      
      {/* Modais */}
      {showPlanoModal && <PlanoModal />}
      {showAtendimentoModal && <AtendimentoModal />}
    </div>
  );
};

export default DiarioAEE;
