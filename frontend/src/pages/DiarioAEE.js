import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, FileText, Calendar, Clock, Plus, Edit2, Trash2, Eye, Copy, Download, X,
  ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Search, Filter,
  BookOpen, Target, Activity, UserCheck, ClipboardList, MessageSquare, Home
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import PlanoAEEModal from '@/components/PlanoAEEModal';

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
  
  const isProfessor = user?.role === 'professor';

  // Permissão de edição - semed3 é somente leitura
  const canEdit = user?.role !== 'semed3';

  // Feb 2026: Modelos de Plano AEE — disponível para todos os usuários com acesso
  // ao Diário AEE (Professor, Coordenador, Diretor, Apoio, Secretaria, Admins...).
  // Apenas semed3 (somente leitura) fica restrito.
  const isTemplateAdmin = canEdit;
  
  // Estados principais
  const [loading, setLoading] = useState(true);
  const initialLoadDone = useRef(false);
  const [activeTab, setActiveTab] = useState('estudantes'); // estudantes, planos, atendimentos, diario
  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedTurma, setSelectedTurma] = useState('');
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  const [professorTurmaIds, setProfessorTurmaIds] = useState(null);
  
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
  const [turmasAEE, setTurmasAEE] = useState([]);

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
  }, []);

  // Busca dados quando escola é selecionada
  const fetchData = useCallback(async () => {
    if (!selectedSchool || !tokenRef.current) return;
    
    const authHeader = { 'Authorization': `Bearer ${tokenRef.current}` };

    // Helper seguro: garante que o body só é lido uma vez e nunca quebra em status HTTP não-ok
    const safeFetchJson = async (url, options = {}) => {
      try {
        const res = await fetch(url, options);
        let body = null;
        try {
          body = await res.json();
        } catch (_) {
          body = null;
        }
        if (!res.ok) {
          console.error(`[AEE] ${res.status} em ${url}`, body);
          return null;
        }
        return body;
      } catch (err) {
        console.error(`[AEE] Falha de rede em ${url}`, err);
        return null;
      }
    };
    
    // Mostrar loading apenas na primeira carga
    if (!initialLoadDone.current) {
      setLoading(true);
    }
    try {
      // Busca estudantes AEE
      const estudantesData = await safeFetchJson(
        `${API_URL}/api/aee/estudantes?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: authHeader }
      );
      setEstudantes(Array.isArray(estudantesData) ? estudantesData : []);
      
      // Busca planos
      const planosData = await safeFetchJson(
        `${API_URL}/api/aee/planos?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: authHeader }
      );
      setPlanos(planosData?.items || []);
      
      // Busca atendimentos
      const atendData = await safeFetchJson(
        `${API_URL}/api/aee/atendimentos?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: authHeader }
      );
      setAtendimentos(atendData?.items || []);
      
      // Busca diário consolidado
      const diarioDataRes = await safeFetchJson(
        `${API_URL}/api/aee/diario?school_id=${selectedSchool}&academic_year=${academicYear}`,
        { headers: authHeader }
      );
      setDiarioData(diarioDataRes);
      
      // Busca alunos da escola para o modal
      let studentsUrl = `${API_URL}/api/students?school_id=${selectedSchool}&page_size=200`;
      const studentsData = await safeFetchJson(studentsUrl, { headers: authHeader });
      setStudents(studentsData?.items || studentsData || []);
      
      // Busca turmas da escola
      const turmasData = await safeFetchJson(
        `${API_URL}/api/classes?school_id=${selectedSchool}`,
        { headers: authHeader }
      );
      const allTurmas = turmasData?.items || turmasData || [];
      setTurmas(allTurmas);

      // Para professor: buscar suas alocações e filtrar turmas AEE
      let aee = allTurmas.filter(t => (t.atendimento_programa || '').toLowerCase() === 'aee');
      if (isProfessor) {
        const profTurmas = await safeFetchJson(
          `${API_URL}/api/professor/turmas`,
          { headers: authHeader }
        );
        const profIds = new Set((profTurmas || []).map(t => t.id));
        setProfessorTurmaIds(profIds);
        aee = aee.filter(t => profIds.has(t.id));
      }
      setTurmasAEE(aee);
      
      // Para professor: selecionar primeira turma automaticamente
      if (isProfessor && aee.length > 0 && !selectedTurma) {
        setSelectedTurma(aee[0].id);
      }
      
    } catch (error) {
      console.error('Erro ao buscar dados:', error);
      showAlert('error', 'Erro ao carregar dados do AEE');
    } finally {
      setLoading(false);
      initialLoadDone.current = true;
    }
  }, [selectedSchool, academicYear]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Parser robusto de erro de response: lê o body uma única vez como texto,
  // tenta decodificar JSON (FastAPI detail pode vir como string OU array de validações).
  const parseResponseError = async (response, fallback = 'Erro ao processar requisição') => {
    let text = '';
    try { text = await response.text(); } catch { /* body já consumido em algum lugar */ }
    if (!text) return fallback;
    try {
      const obj = JSON.parse(text);
      if (obj?.detail) {
        if (Array.isArray(obj.detail)) {
          return obj.detail.map(d => d?.msg || JSON.stringify(d)).join(' · ');
        }
        return typeof obj.detail === 'string' ? obj.detail : JSON.stringify(obj.detail);
      }
      return obj?.message || fallback;
    } catch {
      return text.slice(0, 200);
    }
  };

  const showAlert = (type, message) => {
    setAlert({ show: true, type, message });
  };

  // === HANDLERS DE PLANO ===
  const handleSavePlano = async (formData) => {
    if (!formData.student_id || !formData.publico_alvo) {
      showAlert('error', 'Selecione o aluno e o público-alvo');
      return;
    }
    
    try {
      const payload = {
        ...formData,
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
        throw new Error(await parseResponseError(response, 'Erro ao salvar plano'));
      }
      
      showAlert('success', editingPlano ? 'Plano atualizado com sucesso!' : 'Plano criado com sucesso!');
      setShowPlanoModal(false);
      setEditingPlano(null);
      fetchData();
    } catch (error) {
      showAlert('error', error.message);
    }
  };

  const handleEditPlano = (plano) => {
    setEditingPlano(plano);
    setShowPlanoModal(true);
  };

  // === HANDLERS DE VISUALIZAÇÃO / EXCLUSÃO (Feb 2026) ===
  const [viewingPlano, setViewingPlano] = useState(null);
  const [deletingPlano, setDeletingPlano] = useState(null);

  const handleVisualizarPlano = (plano) => {
    setViewingPlano(plano);
  };

  const handleDeletePlano = (plano) => {
    setDeletingPlano(plano);
  };

  const confirmDeletePlano = async () => {
    if (!deletingPlano) return;
    try {
      const response = await fetch(
        `${API_URL}/api/aee/planos/${deletingPlano.id}`,
        { method: 'DELETE', headers }
      );
      if (!response.ok) {
        throw new Error(await parseResponseError(response, 'Erro ao excluir plano'));
      }
      showAlert('success', 'Plano AEE excluído com sucesso');
      setDeletingPlano(null);
      await fetchData();
    } catch (error) {
      showAlert('error', error.message);
    }
  };

  const handleGerarPDFPlano = async (plano) => {
    try {
      const response = await fetch(
        `${API_URL}/api/aee/planos/${plano.id}/pdf`,
        { headers }
      );
      if (!response.ok) {
        throw new Error(await parseResponseError(response, 'Erro ao gerar PDF'));
      }
      const blob = await response.blob();
      const pdfBlob = blob.type === 'application/pdf'
        ? blob
        : new Blob([blob], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(pdfBlob);
      const studentName = (estudantes.find(e => e.student_id === plano.student_id)?.full_name || 'aluno')
        .replace(/[^a-zA-Z0-9_-]/g, '_');
      const filename = `plano_aee_${studentName}.pdf`;
      // Força download com extensão .pdf para que o navegador ofereça "PDF" ao salvar
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Revoke URL depois de 1min para liberar memória
      setTimeout(() => window.URL.revokeObjectURL(url), 60000);
    } catch (error) {
      showAlert('error', error.message);
    }
  };

  const [duplicatingPlano, setDuplicatingPlano] = useState(null);
  const [duplicateTargetStudentId, setDuplicateTargetStudentId] = useState('');
  const [duplicateMode, setDuplicateMode] = useState('same'); // 'same' | 'cross'

  const handleDuplicarPlano = (plano) => {
    setDuplicatingPlano(plano);
    setDuplicateMode('same');
    setDuplicateTargetStudentId('');
  };

  const confirmDuplicarPlano = async () => {
    if (!duplicatingPlano) return;
    if (duplicateMode === 'cross' && !duplicateTargetStudentId) {
      showAlert('error', 'Selecione o aluno alvo para a duplicação cruzada');
      return;
    }
    try {
      const body = duplicateMode === 'cross'
        ? { target_student_id: duplicateTargetStudentId }
        : {};
      const response = await fetch(
        `${API_URL}/api/aee/planos/${duplicatingPlano.id}/duplicate`,
        { method: 'POST', headers, body: JSON.stringify(body) }
      );
      if (!response.ok) {
        throw new Error(await parseResponseError(response, 'Erro ao duplicar plano'));
      }
      showAlert('success', duplicateMode === 'cross'
        ? 'Plano AEE duplicado para outro aluno (rascunho)'
        : 'Plano AEE duplicado com sucesso (rascunho)');
      setDuplicatingPlano(null);
      setDuplicateTargetStudentId('');
      setDuplicateMode('same');
      await fetchData();
    } catch (error) {
      showAlert('error', error.message);
    }
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
        throw new Error(await parseResponseError(response, 'Erro ao salvar atendimento'));
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
  const [showPeriodoModal, setShowPeriodoModal] = useState(false);
  const [periodoSelecionado, setPeriodoSelecionado] = useState('ano');
  const [periodoDataInicio, setPeriodoDataInicio] = useState('');
  const [periodoDataFim, setPeriodoDataFim] = useState('');

  // === MODELOS DE PLANO AEE (Feb 2026) ===
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [showTemplateForm, setShowTemplateForm] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [templateForm, setTemplateForm] = useState({
    nome: '', descricao: '', publico_alvo: '',
    modalidade: 'individual', carga_horaria_semanal: '',
    local_atendimento: 'Sala de Recursos Multifuncionais',
    barreiras_text: '', objetivos_text: '', recursos_text: '',
    indicadores_progresso: '', frequencia_revisao: 'bimestral',
    criterios_ajuste: '', orientacoes_sala_comum: '',
    adequacoes_curriculares: '', ativo: true,
  });
  const [showApplyTemplate, setShowApplyTemplate] = useState(false);
  const [applyTemplateId, setApplyTemplateId] = useState('');
  const [applyStudentId, setApplyStudentId] = useState('');
  const [applyFilterPublico, setApplyFilterPublico] = useState('');

  const fetchTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const res = await fetch(`${API_URL}/api/aee/templates`, { headers });
      const d = res.ok ? await res.json() : { items: [] };
      setTemplates(d.items || []);
    } catch (e) {
      setTemplates([]);
    } finally {
      setLoadingTemplates(false);
    }
  };

  useEffect(() => {
    if (token) fetchTemplates();
  }, [token]);

  const openApplyTemplate = () => {
    setApplyTemplateId('');
    setApplyStudentId('');
    setApplyFilterPublico('');
    setShowApplyTemplate(true);
  };

  const handleApplyTemplate = async () => {
    if (!applyTemplateId || !applyStudentId) {
      showAlert('error', 'Selecione o modelo e o aluno');
      return;
    }
    try {
      const res = await fetch(`${API_URL}/api/aee/planos/from-template`, {
        method: 'POST', headers,
        body: JSON.stringify({
          template_id: applyTemplateId,
          student_id: applyStudentId,
          academic_year: academicYear,
        }),
      });
      if (!res.ok) throw new Error(await parseResponseError(res, 'Erro ao aplicar modelo'));
      showAlert('success', 'Plano AEE criado a partir do modelo (rascunho)');
      setShowApplyTemplate(false);
      await fetchData();
    } catch (e) {
      showAlert('error', e.message);
    }
  };

  const openTemplateForm = (tpl = null) => {
    if (tpl) {
      setEditingTemplate(tpl);
      setTemplateForm({
        nome: tpl.nome || '',
        descricao: tpl.descricao || '',
        publico_alvo: tpl.publico_alvo || '',
        modalidade: tpl.modalidade || 'individual',
        carga_horaria_semanal: tpl.carga_horaria_semanal || '',
        local_atendimento: tpl.local_atendimento || '',
        barreiras_text: (tpl.barreiras || []).map(b => b.descricao).join('\n'),
        objetivos_text: (tpl.objetivos || []).map(o => `[${o.prazo || 'medio'}] ${o.descricao}`).join('\n'),
        recursos_text: (tpl.recursos_acessibilidade || []).map(r => r.descricao).join('\n'),
        indicadores_progresso: tpl.indicadores_progresso || '',
        frequencia_revisao: tpl.frequencia_revisao || 'bimestral',
        criterios_ajuste: tpl.criterios_ajuste || '',
        orientacoes_sala_comum: tpl.orientacoes_sala_comum || '',
        adequacoes_curriculares: tpl.adequacoes_curriculares || '',
        ativo: tpl.ativo !== false,
      });
    } else {
      setEditingTemplate(null);
      setTemplateForm({
        nome: '', descricao: '', publico_alvo: '',
        modalidade: 'individual', carga_horaria_semanal: '',
        local_atendimento: 'Sala de Recursos Multifuncionais',
        barreiras_text: '', objetivos_text: '', recursos_text: '',
        indicadores_progresso: '', frequencia_revisao: 'bimestral',
        criterios_ajuste: '', orientacoes_sala_comum: '',
        adequacoes_curriculares: '', ativo: true,
      });
    }
    setShowTemplateForm(true);
  };

  const handleSaveTemplate = async () => {
    if (!templateForm.nome || !templateForm.publico_alvo) {
      showAlert('error', 'Preencha o nome e o público-alvo do modelo');
      return;
    }
    const linesOf = (v) => (v || '').split('\n').map(s => s.trim()).filter(Boolean);
    const parseObjetivos = (txt) => linesOf(txt).map(line => {
      const m = line.match(/^\[(curto|medio|longo)\]\s*(.*)$/i);
      return m
        ? { prazo: m[1].toLowerCase(), descricao: m[2], status: 'nao_iniciado', indicadores: [] }
        : { prazo: 'medio', descricao: line, status: 'nao_iniciado', indicadores: [] };
    });
    const payload = {
      nome: templateForm.nome,
      descricao: templateForm.descricao || null,
      publico_alvo: templateForm.publico_alvo,
      modalidade: templateForm.modalidade,
      carga_horaria_semanal: templateForm.carga_horaria_semanal || null,
      local_atendimento: templateForm.local_atendimento || null,
      barreiras: linesOf(templateForm.barreiras_text)
        .map(d => ({ tipo: 'outra', descricao: d, estrategias: [] })),
      objetivos: parseObjetivos(templateForm.objetivos_text),
      recursos_acessibilidade: linesOf(templateForm.recursos_text)
        .map(d => ({ tipo: 'outro', descricao: d, disponivel: true })),
      indicadores_progresso: templateForm.indicadores_progresso || null,
      frequencia_revisao: templateForm.frequencia_revisao,
      criterios_ajuste: templateForm.criterios_ajuste || null,
      orientacoes_sala_comum: templateForm.orientacoes_sala_comum || null,
      adequacoes_curriculares: templateForm.adequacoes_curriculares || null,
      ativo: templateForm.ativo,
    };
    try {
      const url = editingTemplate
        ? `${API_URL}/api/aee/templates/${editingTemplate.id}`
        : `${API_URL}/api/aee/templates`;
      const res = await fetch(url, {
        method: editingTemplate ? 'PUT' : 'POST',
        headers, body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await parseResponseError(res, 'Erro ao salvar modelo'));
      showAlert('success', editingTemplate ? 'Modelo atualizado' : 'Modelo criado');
      setShowTemplateForm(false);
      setEditingTemplate(null);
      await fetchTemplates();
    } catch (e) {
      showAlert('error', e.message);
    }
  };

  const handleDeleteTemplate = async (tpl) => {
    if (!window.confirm(`Excluir o modelo "${tpl.nome}"? Planos já criados a partir dele serão preservados.`)) return;
    try {
      const res = await fetch(`${API_URL}/api/aee/templates/${tpl.id}`, {
        method: 'DELETE', headers,
      });
      if (!res.ok) throw new Error(await parseResponseError(res, 'Erro ao excluir modelo'));
      showAlert('success', 'Modelo excluído');
      await fetchTemplates();
    } catch (e) {
      showAlert('error', e.message);
    }
  };

  // Calcula intervalo de datas para presets de período
  const getPeriodoRange = (preset, year) => {
    const presets = {
      'bim1': { ini: `${year}-02-01`, fim: `${year}-04-30`, label: '1º Bimestre' },
      'bim2': { ini: `${year}-05-01`, fim: `${year}-07-31`, label: '2º Bimestre' },
      'bim3': { ini: `${year}-08-01`, fim: `${year}-09-30`, label: '3º Bimestre' },
      'bim4': { ini: `${year}-10-01`, fim: `${year}-12-31`, label: '4º Bimestre' },
      'sem1': { ini: `${year}-02-01`, fim: `${year}-07-31`, label: '1º Semestre' },
      'sem2': { ini: `${year}-08-01`, fim: `${year}-12-31`, label: '2º Semestre' },
      'ano': { ini: '', fim: '', label: 'Ano completo' },
      'custom': { ini: periodoDataInicio, fim: periodoDataFim, label: 'Personalizado' },
    };
    return presets[preset] || presets['ano'];
  };

  const handleDownloadPDF = async (studentId = null) => {
    try {
      const range = getPeriodoRange(periodoSelecionado, academicYear);
      let url = `${API_URL}/api/aee/diario/pdf?school_id=${selectedSchool}&academic_year=${academicYear}`;
      if (studentId) url += `&student_id=${studentId}`;
      if (range.ini) url += `&data_inicio=${range.ini}`;
      if (range.fim) url += `&data_fim=${range.fim}`;
      if (range.label) url += `&periodo_label=${encodeURIComponent(range.label)}`;

      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Erro ao gerar PDF');

      const blob = await response.blob();
      const pdfBlob = blob.type === 'application/pdf'
        ? blob
        : new Blob([blob], { type: 'application/pdf' });
      const downloadUrl = window.URL.createObjectURL(pdfBlob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      const periodoSlug = (range.label || 'ano').toLowerCase().replace(/\s+/g, '_').replace(/[º°]/g, '');
      link.download = `diario_aee_${academicYear}_${periodoSlug}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
      setShowPeriodoModal(false);
    } catch (error) {
      showAlert('error', 'Erro ao gerar PDF');
    }
  };

  // === FILTRAGEM POR TURMA AEE ===
  const filteredEstudantes = selectedTurma
    ? estudantes.filter(est => {
        // Primeiro tenta pelo próprio objeto estudante (dados vindos de /api/aee/estudantes)
        if (est.class_id === selectedTurma || est.atendimento_programa_class_id === selectedTurma) return true;
        // Fallback: busca no array geral de students
        const student = students.find(s => s.id === est.student_id);
        return student && (student.class_id === selectedTurma || student.atendimento_programa_class_id === selectedTurma);
      })
    : estudantes;

  const filteredPlanos = selectedTurma
    ? planos.filter(p => {
        const est = estudantes.find(e => e.student_id === p.student_id);
        if (est && (est.class_id === selectedTurma || est.atendimento_programa_class_id === selectedTurma)) return true;
        const student = students.find(s => s.id === p.student_id);
        return student && (student.class_id === selectedTurma || student.atendimento_programa_class_id === selectedTurma);
      })
    : planos;

  const filteredAtendimentos = selectedTurma
    ? atendimentos.filter(a => {
        const est = estudantes.find(e => e.student_id === a.student_id);
        if (est && (est.class_id === selectedTurma || est.atendimento_programa_class_id === selectedTurma)) return true;
        const student = students.find(s => s.id === a.student_id);
        return student && (student.class_id === selectedTurma || student.atendimento_programa_class_id === selectedTurma);
      })
    : atendimentos;

  // === COMPONENTES DE TABS ===
  const TabEstudantes = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-800">Estudantes Atendidos no AEE</h3>
        {canEdit && (
        <button
          onClick={() => { setEditingPlano(null); setShowPlanoModal(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus size={18} />
          Novo Plano de AEE
        </button>
        )}
      </div>
      
      {filteredEstudantes.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <Users size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">{selectedTurma ? 'Nenhum estudante com Plano de AEE nesta turma' : 'Nenhum estudante com Plano de AEE ativo'}</p>
          <p className="text-sm text-gray-400 mt-2">Clique em "Novo Plano de AEE" para cadastrar</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredEstudantes.map((est) => (
            <div key={est.student_id} className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="font-semibold text-gray-900">{est.full_name}</h4>
                  <p className="text-sm text-gray-500">Turma Origem: {est.turma_origem || 'N/D'}</p>
                  <p className="text-sm text-gray-500">Escola Origem: {est.escola_origem || 'N/D'}</p>
                  <p className="text-sm text-gray-500">Professor Regente: {est.professor_regente || 'N/D'}</p>
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
                  {canEdit && (
                  <button
                    onClick={() => handleNovoAtendimento(planos.find(p => p.student_id === est.student_id))}
                    className="p-2 text-green-600 hover:bg-green-50 rounded"
                    title="Registrar Atendimento"
                  >
                    <Plus size={18} />
                  </button>
                  )}
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
        <div className="flex items-center gap-2">
          {canEdit && (
            <button
              onClick={() => openApplyTemplate()}
              data-testid="btn-novo-de-modelo"
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
            >
              <BookOpen size={18} />
              Novo a partir de Modelo
            </button>
          )}
          {canEdit && (
            <button
              onClick={() => { setEditingPlano(null); setShowPlanoModal(true); }}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <Plus size={18} />
              Novo Plano
            </button>
          )}
        </div>
      </div>
      
      {filteredPlanos.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <FileText size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">{selectedTurma ? 'Nenhum plano cadastrado nesta turma' : 'Nenhum plano cadastrado'}</p>
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
              {filteredPlanos.map((plano) => (
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
                    <div className="flex justify-center gap-1">
                      <button
                        onClick={() => handleVisualizarPlano(plano)}
                        className="p-1 text-indigo-600 hover:bg-indigo-50 rounded"
                        title="Visualizar"
                        data-testid={`btn-visualizar-plano-${plano.id}`}
                      >
                        <Eye size={16} />
                      </button>
                      {canEdit && (
                      <>
                      <button
                        onClick={() => handleEditPlano(plano)}
                        className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                        title="Editar"
                        data-testid={`btn-editar-plano-${plano.id}`}
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        onClick={() => handleDuplicarPlano(plano)}
                        className="p-1 text-purple-600 hover:bg-purple-50 rounded"
                        title="Duplicar Plano AEE"
                        data-testid={`btn-duplicar-plano-${plano.id}`}
                      >
                        <Copy size={16} />
                      </button>
                      <button
                        onClick={() => handleNovoAtendimento(plano)}
                        className="p-1 text-green-600 hover:bg-green-50 rounded"
                        title="Novo Atendimento"
                        data-testid={`btn-novo-atendimento-${plano.id}`}
                      >
                        <Plus size={16} />
                      </button>
                      <button
                        onClick={() => handleDeletePlano(plano)}
                        className="p-1 text-red-600 hover:bg-red-50 rounded"
                        title="Excluir"
                        data-testid={`btn-excluir-plano-${plano.id}`}
                      >
                        <Trash2 size={16} />
                      </button>
                      </>
                      )}
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
        {canEdit && (
        <button
          onClick={() => handleNovoAtendimento()}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          disabled={planos.length === 0}
        >
          <Plus size={18} />
          Novo Atendimento
        </button>
        )}
      </div>
      
      {filteredAtendimentos.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <ClipboardList size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">{selectedTurma ? 'Nenhum atendimento registrado nesta turma' : 'Nenhum atendimento registrado'}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredAtendimentos.slice(0, 20).map((atend) => (
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
                {canEdit && (
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
                )}
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
          onClick={() => setShowPeriodoModal(true)}
          data-testid="btn-baixar-pdf-completo"
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
              <p className="text-2xl font-bold text-blue-700">{selectedTurma ? filteredEstudantes.length : diarioData.total_estudantes}</p>
              <p className="text-sm text-blue-600">Estudantes</p>
            </div>
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <ClipboardList size={24} className="mx-auto text-green-600 mb-2" />
              <p className="text-2xl font-bold text-green-700">{filteredAtendimentos.length}</p>
              <p className="text-sm text-green-600">Atendimentos</p>
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <FileText size={24} className="mx-auto text-purple-600 mb-2" />
              <p className="text-2xl font-bold text-purple-700">{filteredPlanos.length}</p>
              <p className="text-sm text-purple-600">Planos Ativos</p>
            </div>
            <div className="bg-orange-50 rounded-lg p-4 text-center">
              <Clock size={24} className="mx-auto text-orange-600 mb-2" />
              <p className="text-2xl font-bold text-orange-700">
                {Math.round(filteredAtendimentos.reduce((acc, a) => acc + (a.duracao_minutos || 0), 0) / 60)}h
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

  // === ABA: MODELOS DE PLANO AEE (apenas admin/super_admin) ===
  const TabModelos = () => (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">Modelos de Plano AEE</h3>
          <p className="text-xs text-gray-500 mt-1">Templates pré-prontos por público-alvo. Apenas administradores podem criar/editar.</p>
        </div>
        <button
          onClick={() => openTemplateForm(null)}
          data-testid="btn-novo-modelo"
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
        >
          <Plus size={18} />
          Novo Modelo
        </button>
      </div>
      {loadingTemplates ? (
        <div className="text-center py-8 text-gray-500">Carregando modelos...</div>
      ) : templates.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <BookOpen size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500">Nenhum modelo cadastrado ainda</p>
          <p className="text-xs text-gray-400 mt-1">Crie um modelo para acelerar o trabalho dos professores AEE.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white border rounded-lg">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Público-Alvo</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Modalidade</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Itens</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {templates.map(tpl => (
                <tr key={tpl.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{tpl.nome}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{PUBLICO_ALVO_LABELS[tpl.publico_alvo] || tpl.publico_alvo}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{MODALIDADE_LABELS[tpl.modalidade] || tpl.modalidade}</td>
                  <td className="px-4 py-3 text-xs text-center text-gray-500">
                    B:{(tpl.barreiras || []).length} · O:{(tpl.objetivos || []).length} · R:{(tpl.recursos_acessibilidade || []).length}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-1 rounded text-xs ${tpl.ativo ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {tpl.ativo ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center gap-1">
                      <button
                        onClick={() => openTemplateForm(tpl)}
                        data-testid={`btn-editar-modelo-${tpl.id}`}
                        className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                        title="Editar"
                      ><Edit2 size={16} /></button>
                      <button
                        onClick={() => handleDeleteTemplate(tpl)}
                        data-testid={`btn-excluir-modelo-${tpl.id}`}
                        className="p-1 text-red-600 hover:bg-red-50 rounded"
                        title="Excluir"
                      ><Trash2 size={16} /></button>
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
  const atendimentoModalContent = (
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
          <button onClick={() => setAlert({ show: false, type: '', message: '' })} className="ml-2 font-bold hover:opacity-80">✕</button>
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
            onChange={(e) => { initialLoadDone.current = false; setSelectedSchool(e.target.value); setSelectedTurma(''); }}
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
        {turmasAEE.length > 0 && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Turma AEE</label>
            <select
              value={selectedTurma}
              onChange={(e) => setSelectedTurma(e.target.value)}
              className="border rounded-lg px-3 py-2 min-w-[200px]"
              data-testid="filter-turma-aee"
            >
              {!isProfessor && <option value="">Todas as turmas</option>}
              {turmasAEE.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>
      
      {/* Tabs */}
      <div className="bg-white border rounded-lg">
        <div className="border-b flex">
          {[
            { id: 'estudantes', label: 'Estudantes', icon: Users },
            { id: 'planos', label: 'Planos de AEE', icon: FileText },
            { id: 'atendimentos', label: 'Atendimentos', icon: ClipboardList },
            { id: 'diario', label: 'Diário Consolidado', icon: BookOpen },
            ...(isTemplateAdmin ? [{ id: 'modelos', label: 'Modelos', icon: BookOpen }] : []),
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              data-testid={`tab-${tab.id}`}
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
              {activeTab === 'modelos' && isTemplateAdmin && <TabModelos />}
            </>
          )}
        </div>
      </div>
      
      {/* Modais */}
      <PlanoAEEModal
        show={showPlanoModal}
        onClose={() => { setShowPlanoModal(false); setEditingPlano(null); }}
        onSave={handleSavePlano}
        editingPlano={editingPlano}
        estudantes={estudantes}
        canEdit={canEdit}
      />
      {showAtendimentoModal && atendimentoModalContent}

      {/* Modal de Visualização do Plano AEE (Feb 2026) */}
      {viewingPlano && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setViewingPlano(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="view-plano-modal">
            <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-gray-900">Visualização do Plano AEE</h3>
              <button onClick={() => setViewingPlano(null)} className="text-gray-400 hover:text-gray-600">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <div><span className="font-semibold text-gray-600">Aluno:</span> {estudantes.find(e => e.student_id === viewingPlano.student_id)?.full_name || '-'}</div>
                <div><span className="font-semibold text-gray-600">Ano Letivo:</span> {viewingPlano.academic_year}</div>
                <div><span className="font-semibold text-gray-600">Público-alvo:</span> {viewingPlano.publico_alvo?.replace(/_/g, ' ')}</div>
                <div><span className="font-semibold text-gray-600">Status:</span> <span className="capitalize">{viewingPlano.status}</span></div>
                <div><span className="font-semibold text-gray-600">Modalidade:</span> <span className="capitalize">{viewingPlano.modalidade || '-'}</span></div>
                <div><span className="font-semibold text-gray-600">Carga Horária:</span> {viewingPlano.carga_horaria_semanal || '-'}</div>
                <div><span className="font-semibold text-gray-600">Data Elaboração:</span> {viewingPlano.data_elaboracao || '-'}</div>
                <div><span className="font-semibold text-gray-600">Período Vigência:</span> {viewingPlano.periodo_vigencia || '-'}</div>
              </div>
              {viewingPlano.linha_base_situacao_atual && (
                <div><span className="font-semibold text-gray-600 block">Linha de Base - Situação Atual:</span> <div className="whitespace-pre-wrap">{viewingPlano.linha_base_situacao_atual}</div></div>
              )}
              {viewingPlano.linha_base_potencialidades && (
                <div><span className="font-semibold text-gray-600 block">Potencialidades:</span> <div className="whitespace-pre-wrap">{viewingPlano.linha_base_potencialidades}</div></div>
              )}
              {Array.isArray(viewingPlano.barreiras) && viewingPlano.barreiras.length > 0 && (
                <div><span className="font-semibold text-gray-600 block mb-1">Barreiras Identificadas:</span>
                  <ul className="list-disc list-inside space-y-1">
                    {viewingPlano.barreiras.map((b, i) => (
                      <li key={b._key || `b-${i}`}>{typeof b === 'string' ? b : `[${(b.tipo || '').toUpperCase()}] ${b.descricao || ''}`}</li>
                    ))}
                  </ul>
                </div>
              )}
              {Array.isArray(viewingPlano.objetivos) && viewingPlano.objetivos.length > 0 && (
                <div><span className="font-semibold text-gray-600 block mb-1">Objetivos:</span>
                  <ul className="list-disc list-inside space-y-1">
                    {viewingPlano.objetivos.map((o, i) => (
                      <li key={o._key || `o-${i}`}>{typeof o === 'string' ? o : `${o.descricao || ''}${o.prazo ? ` (${o.prazo})` : ''}`}</li>
                    ))}
                  </ul>
                </div>
              )}
              {Array.isArray(viewingPlano.recursos_acessibilidade) && viewingPlano.recursos_acessibilidade.length > 0 && (
                <div><span className="font-semibold text-gray-600 block mb-1">Recursos de Acessibilidade:</span>
                  <ul className="list-disc list-inside space-y-1">
                    {viewingPlano.recursos_acessibilidade.map((r, i) => (
                      <li key={r._key || `r-${i}`}>{typeof r === 'string' ? r : `[${(r.tipo || '').toUpperCase()}] ${r.descricao || ''}`}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-3 flex justify-end gap-2">
              <button
                onClick={() => setViewingPlano(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Fechar</button>
              <button
                onClick={() => handleGerarPDFPlano(viewingPlano)}
                data-testid="btn-gerar-pdf-plano"
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 inline-flex items-center gap-2"
              >
                <Download size={14} />
                Gerar PDF (Imprimir / Salvar)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Confirmação de Exclusão (Feb 2026) */}
      {deletingPlano && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setDeletingPlano(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="delete-plano-modal">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-red-100 rounded-lg">
                <Trash2 size={24} className="text-red-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Excluir Plano AEE</h3>
                <p className="text-sm text-gray-500 mt-1">Esta ação não pode ser desfeita.</p>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 mb-4 text-sm">
              <div><b>Aluno:</b> {estudantes.find(e => e.student_id === deletingPlano.student_id)?.full_name || '-'}</div>
              <div><b>Status:</b> <span className="capitalize">{deletingPlano.status}</span></div>
              <div><b>Ano letivo:</b> {deletingPlano.academic_year}</div>
            </div>
            <p className="text-xs text-gray-600 mb-4">
              Os atendimentos AEE vinculados permanecerão no sistema para fins de histórico,
              mas perderão a referência a este plano.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeletingPlano(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Cancelar</button>
              <button
                onClick={confirmDeletePlano}
                data-testid="confirm-delete-plano"
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700"
              >Excluir definitivamente</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Duplicação de Plano AEE (Feb 2026) */}
      {duplicatingPlano && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setDuplicatingPlano(null)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="duplicate-plano-modal">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-purple-100 rounded-lg">
                <Copy size={24} className="text-purple-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Duplicar Plano AEE</h3>
                <p className="text-sm text-gray-500 mt-1">
                  Plano original: <b>{duplicatingPlano.student_name || '-'}</b>
                </p>
              </div>
            </div>

            <div className="space-y-2 mb-4">
              <label className="flex items-start gap-2 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                     style={{ borderColor: duplicateMode === 'same' ? '#9333ea' : '#d1d5db' }}>
                <input
                  type="radio"
                  name="dup-mode"
                  checked={duplicateMode === 'same'}
                  onChange={() => setDuplicateMode('same')}
                  data-testid="duplicate-mode-same"
                  className="mt-1"
                />
                <div className="flex-1">
                  <p className="font-medium text-sm text-gray-800">Para o mesmo aluno</p>
                  <p className="text-xs text-gray-500">Cria uma cópia em rascunho do plano para o mesmo aluno (útil para revisões/novo período).</p>
                </div>
              </label>
              <label className="flex items-start gap-2 p-3 border rounded-lg cursor-pointer hover:bg-gray-50"
                     style={{ borderColor: duplicateMode === 'cross' ? '#9333ea' : '#d1d5db' }}>
                <input
                  type="radio"
                  name="dup-mode"
                  checked={duplicateMode === 'cross'}
                  onChange={() => setDuplicateMode('cross')}
                  data-testid="duplicate-mode-cross"
                  className="mt-1"
                />
                <div className="flex-1">
                  <p className="font-medium text-sm text-gray-800">Para outro aluno (duplicação cruzada)</p>
                  <p className="text-xs text-gray-500">Copia objetivos, recursos e cronograma para outro aluno AEE da mesma escola. Turma e Prof. Regente são ajustados automaticamente.</p>
                </div>
              </label>
            </div>

            {duplicateMode === 'cross' && (
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-700 mb-1">Aluno alvo</label>
                <select
                  value={duplicateTargetStudentId}
                  onChange={(e) => setDuplicateTargetStudentId(e.target.value)}
                  data-testid="duplicate-target-student"
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">Selecione...</option>
                  {estudantes
                    .filter(e => e.student_id !== duplicatingPlano.student_id)
                    .map(e => (
                      <option key={e.student_id} value={e.student_id}>
                        {e.full_name}{e.turma_origem ? ` — ${e.turma_origem}` : ''}
                      </option>
                    ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  São listados apenas alunos AEE da escola atual.
                  Se o aluno já tiver plano no mesmo ano letivo, a duplicação será bloqueada.
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDuplicatingPlano(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Cancelar</button>
              <button
                onClick={confirmDuplicarPlano}
                data-testid="confirm-duplicate-plano"
                disabled={duplicateMode === 'cross' && !duplicateTargetStudentId}
                className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <Copy size={16} />
                Duplicar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Filtro de Período para PDF (Feb 2026) */}
      {showPeriodoModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowPeriodoModal(false)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="periodo-pdf-modal">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-red-100 rounded-lg">
                <Calendar size={24} className="text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Período do PDF</h3>
                <p className="text-sm text-gray-500 mt-1">Escolha o período de atendimentos a incluir no relatório.</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-4">
              {[
                { v: 'ano', label: 'Ano completo' },
                { v: 'sem1', label: '1º Semestre' },
                { v: 'sem2', label: '2º Semestre' },
                { v: 'bim1', label: '1º Bimestre' },
                { v: 'bim2', label: '2º Bimestre' },
                { v: 'bim3', label: '3º Bimestre' },
                { v: 'bim4', label: '4º Bimestre' },
                { v: 'custom', label: 'Personalizado' },
              ].map((opt) => (
                <button
                  key={opt.v}
                  onClick={() => setPeriodoSelecionado(opt.v)}
                  data-testid={`periodo-opt-${opt.v}`}
                  className={`px-3 py-2 text-sm font-medium rounded-lg border transition-colors ${
                    periodoSelecionado === opt.v
                      ? 'bg-red-600 text-white border-red-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            {periodoSelecionado === 'custom' && (
              <div className="grid grid-cols-2 gap-3 mb-4 bg-gray-50 p-3 rounded-lg">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={periodoDataInicio}
                    onChange={(e) => setPeriodoDataInicio(e.target.value)}
                    data-testid="periodo-data-inicio"
                    className="w-full border rounded px-2 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={periodoDataFim}
                    onChange={(e) => setPeriodoDataFim(e.target.value)}
                    data-testid="periodo-data-fim"
                    className="w-full border rounded px-2 py-1.5 text-sm"
                  />
                </div>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowPeriodoModal(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Cancelar</button>
              <button
                onClick={() => handleDownloadPDF()}
                data-testid="confirm-download-pdf"
                disabled={periodoSelecionado === 'custom' && (!periodoDataInicio || !periodoDataFim)}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <Download size={16} />
                Gerar PDF
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Aplicar Modelo a um Aluno (Feb 2026) */}
      {showApplyTemplate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowApplyTemplate(false)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" onClick={(e) => e.stopPropagation()} data-testid="apply-template-modal">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-emerald-100 rounded-lg">
                <BookOpen size={24} className="text-emerald-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Novo Plano a partir de Modelo</h3>
                <p className="text-sm text-gray-500 mt-1">Selecione um modelo validado e o aluno alvo. O plano será criado em rascunho.</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Filtrar por público-alvo</label>
                <select
                  value={applyFilterPublico}
                  onChange={(e) => setApplyFilterPublico(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">Todos</option>
                  {Object.entries(PUBLICO_ALVO_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Modelo</label>
                <select
                  value={applyTemplateId}
                  onChange={(e) => setApplyTemplateId(e.target.value)}
                  data-testid="apply-template-select"
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">Selecione um modelo...</option>
                  {templates
                    .filter(t => t.ativo !== false)
                    .filter(t => !applyFilterPublico || t.publico_alvo === applyFilterPublico)
                    .map(t => (
                      <option key={t.id} value={t.id}>
                        {t.nome} — {PUBLICO_ALVO_LABELS[t.publico_alvo] || t.publico_alvo}
                      </option>
                    ))}
                </select>
                {templates.length === 0 && (
                  <p className="text-xs text-yellow-600 mt-1">Nenhum modelo cadastrado. Peça a um administrador para criar.</p>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Aluno alvo</label>
                <select
                  value={applyStudentId}
                  onChange={(e) => setApplyStudentId(e.target.value)}
                  data-testid="apply-student-select"
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                >
                  <option value="">Selecione um aluno...</option>
                  {estudantes.map(e => (
                    <option key={e.student_id} value={e.student_id}>
                      {e.full_name}{e.turma_origem ? ` — ${e.turma_origem}` : ''}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">Se o aluno já tiver plano no mesmo ano letivo, a criação será bloqueada.</p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowApplyTemplate(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Cancelar</button>
              <button
                onClick={handleApplyTemplate}
                data-testid="confirm-apply-template"
                disabled={!applyTemplateId || !applyStudentId}
                className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >Aplicar e Criar Plano</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Criar/Editar Modelo de Plano AEE (Feb 2026) */}
      {showTemplateForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowTemplateForm(false)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="template-form-modal">
            <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-900">
                {editingTemplate ? 'Editar Modelo' : 'Novo Modelo de Plano AEE'}
              </h2>
              <button onClick={() => setShowTemplateForm(false)} className="text-gray-400 hover:text-gray-600">✕</button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Nome <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    value={templateForm.nome}
                    onChange={(e) => setTemplateForm({ ...templateForm, nome: e.target.value })}
                    data-testid="template-nome"
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                    placeholder="Ex: Modelo TEA - Anos Iniciais"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Público-alvo <span className="text-red-500">*</span></label>
                  <select
                    value={templateForm.publico_alvo}
                    onChange={(e) => setTemplateForm({ ...templateForm, publico_alvo: e.target.value })}
                    data-testid="template-publico-alvo"
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="">Selecione...</option>
                    {Object.entries(PUBLICO_ALVO_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Descrição</label>
                <textarea
                  value={templateForm.descricao}
                  onChange={(e) => setTemplateForm({ ...templateForm, descricao: e.target.value })}
                  rows={2}
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                  placeholder="Contexto/uso recomendado"
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Modalidade</label>
                  <select
                    value={templateForm.modalidade}
                    onChange={(e) => setTemplateForm({ ...templateForm, modalidade: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  >
                    {Object.entries(MODALIDADE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Carga horária</label>
                  <input
                    type="text"
                    value={templateForm.carga_horaria_semanal}
                    onChange={(e) => setTemplateForm({ ...templateForm, carga_horaria_semanal: e.target.value })}
                    placeholder="Ex: 4 horas"
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Frequência de revisão</label>
                  <select
                    value={templateForm.frequencia_revisao}
                    onChange={(e) => setTemplateForm({ ...templateForm, frequencia_revisao: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="mensal">Mensal</option>
                    <option value="bimestral">Bimestral</option>
                    <option value="trimestral">Trimestral</option>
                    <option value="semestral">Semestral</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Local de atendimento</label>
                <input
                  type="text"
                  value={templateForm.local_atendimento}
                  onChange={(e) => setTemplateForm({ ...templateForm, local_atendimento: e.target.value })}
                  className="w-full border rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Barreiras (uma por linha)</label>
                <textarea
                  value={templateForm.barreiras_text}
                  onChange={(e) => setTemplateForm({ ...templateForm, barreiras_text: e.target.value })}
                  rows={3}
                  className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
                  placeholder={'Dificuldade de comunicação verbal\nFalta de interação com pares'}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Objetivos (uma por linha; prefixe [curto], [medio] ou [longo])
                </label>
                <textarea
                  value={templateForm.objetivos_text}
                  onChange={(e) => setTemplateForm({ ...templateForm, objetivos_text: e.target.value })}
                  rows={4}
                  className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
                  placeholder={'[curto] Reconhecer figuras de PECS\n[medio] Comunicar necessidades básicas\n[longo] Engajar em conversa simples'}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Recursos de acessibilidade (um por linha)</label>
                <textarea
                  value={templateForm.recursos_text}
                  onChange={(e) => setTemplateForm({ ...templateForm, recursos_text: e.target.value })}
                  rows={3}
                  className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
                  placeholder={'Pranchas PECS\nTablet com app de comunicação alternativa'}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Indicadores de progresso</label>
                  <textarea
                    value={templateForm.indicadores_progresso}
                    onChange={(e) => setTemplateForm({ ...templateForm, indicadores_progresso: e.target.value })}
                    rows={2}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Critérios de ajuste</label>
                  <textarea
                    value={templateForm.criterios_ajuste}
                    onChange={(e) => setTemplateForm({ ...templateForm, criterios_ajuste: e.target.value })}
                    rows={2}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Orientações à sala comum</label>
                  <textarea
                    value={templateForm.orientacoes_sala_comum}
                    onChange={(e) => setTemplateForm({ ...templateForm, orientacoes_sala_comum: e.target.value })}
                    rows={2}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Adequações curriculares</label>
                  <textarea
                    value={templateForm.adequacoes_curriculares}
                    onChange={(e) => setTemplateForm({ ...templateForm, adequacoes_curriculares: e.target.value })}
                    rows={2}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={templateForm.ativo}
                  onChange={(e) => setTemplateForm({ ...templateForm, ativo: e.target.checked })}
                />
                Modelo ativo (disponível para uso)
              </label>
            </div>
            <div className="sticky bottom-0 bg-white border-t px-6 py-3 flex justify-end gap-2">
              <button
                onClick={() => setShowTemplateForm(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >Cancelar</button>
              <button
                onClick={handleSaveTemplate}
                data-testid="save-template-btn"
                className="px-4 py-2 text-sm font-medium text-white bg-emerald-600 rounded-lg hover:bg-emerald-700"
              >{editingTemplate ? 'Atualizar Modelo' : 'Criar Modelo'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DiarioAEE;
