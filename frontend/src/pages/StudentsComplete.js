import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { studentsAPI, schoolsAPI, classesAPI, uploadAPI, documentsAPI, medicalCertificatesAPI, cpfAPI } from '@/services/api';
import { formatPhone, formatCEP, formatCPF, formatNIS, formatSUS, isValidEmail, isValidCPF } from '@/utils/formatters';
import { extractErrorMessage } from '@/utils/errorHandler';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { useOffline } from '@/contexts/OfflineContext';
import { offlineStudentsService } from '@/services/offlineStudentsService';
import { Plus, AlertCircle, CheckCircle, Home, User, Trash2, Upload, FileText, Image, Search, X, Printer, Building2, Users, ExternalLink, Calendar, CloudOff, Cloud, RefreshCw, Stethoscope, Filter, ChevronLeft, ChevronRight, Mail, Phone } from 'lucide-react';
import { DocumentGeneratorModal } from '@/components/documents';
import { CityAutocomplete } from '@/components/CityAutocomplete';

// Estados brasileiros
const STATES = [
  'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
  'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
];

// Opções de deficiências/transtornos
const DISABILITIES_OPTIONS = [
  'Deficiência Física',
  'Deficiência Intelectual',
  'Deficiência Visual',
  'Deficiência Auditiva',
  'Deficiência Múltipla',
  'Transtorno do Espectro Autista (TEA)',
  'Altas Habilidades/Superdotação',
  'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)',
  'Dislexia',
  'Discalculia',
  'Síndrome de Down'
];

// Opções de benefícios
const BENEFITS_OPTIONS = [
  'Bolsa Família',
  'BPC - Benefício de Prestação Continuada',
  'Auxílio Brasil',
  'Programa de Erradicação do Trabalho Infantil (PETI)',
  'Outros'
];

const initialFormData = {
  // Identificação
  school_id: '',
  enrollment_number: '',
  inep_code: '',
  
  // Dados Pessoais
  full_name: '',
  phone: '',
  email: '',
  birth_date: '',
  sex: '',
  nationality: 'Brasileira',
  birth_city: '',
  birth_state: '',
  color_race: '',
  comunidade_tradicional: '',
  
  // Documentos
  cpf: '',
  rg: '',
  rg_issue_date: '',
  rg_issuer: '',
  rg_state: '',
  nis: '',
  sus_number: '',
  civil_certificate_type: '',
  civil_certificate_number: '',
  civil_certificate_book: '',
  civil_certificate_page: '',
  civil_certificate_registry: '',
  civil_certificate_city: '',
  civil_certificate_state: '',
  civil_certificate_date: '',
  passport_number: '',
  passport_country: '',
  passport_expiry: '',
  no_documents_justification: '',
  
  // Responsáveis
  father_name: '',
  father_cpf: '',
  father_rg: '',
  father_phone: '',
  father_email: '',
  mother_name: '',
  mother_cpf: '',
  mother_rg: '',
  mother_phone: '',
  mother_email: '',
  legal_guardian_type: '',  // 'mother', 'father', 'both', 'other'
  guardian_name: '',
  guardian_cpf: '',
  guardian_rg: '',
  guardian_phone: '',
  guardian_email: '',
  guardian_relationship: '',
  authorized_persons: [],
  
  // Informações Complementares
  uses_school_transport: false,
  transport_type: '',
  transport_route: '',
  religion: '',
  benefits: [],
  has_disability: false,
  disabilities: [],
  disability_details: '',
  is_literate: null,
  is_emancipated: false,
  
  // Anexos
  photo_url: '',
  documents_urls: [],
  medical_report_url: '',
  
  // Vínculo escolar
  class_id: '',
  user_id: null,
  guardian_ids: [],
  
  // Observações
  observations: '',
  status: 'active'
};

// Função para calcular a idade a partir da data de nascimento
const calculateAge = (birthDate) => {
  if (!birthDate) return null;
  const today = new Date();
  const birth = new Date(birthDate);
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  return age;
};

// Função para calcular a série ideal baseada na idade
// Data de corte: 31 de março do ano letivo (conforme MEC)
// A criança deve completar a idade mínima ATÉ 31/03 do ano da matrícula
const calculateIdealGrade = (birthDate) => {
  if (!birthDate) return null;
  
  const birth = new Date(birthDate);
  const currentYear = new Date().getFullYear();
  
  // Data de corte: 31 de março do ano letivo atual
  const cutoffDate = new Date(currentYear, 2, 31); // Março = 2 (0-indexed)
  
  // Calcular a idade que a criança terá/teve em 31 de março do ano atual
  let ageAtCutoff = currentYear - birth.getFullYear();
  
  // Se o aniversário é DEPOIS de 31 de março, a criança ainda não completou anos
  // Então reduzimos 1 ano da idade na data de corte
  if (birth.getMonth() > 2 || (birth.getMonth() === 2 && birth.getDate() > 31)) {
    ageAtCutoff--;
  }
  
  // Calcular idade em meses na data de corte (para berçário)
  let ageInMonths = ageAtCutoff * 12;
  if (ageAtCutoff === 0) {
    // Para bebês, calcular meses mais precisamente
    ageInMonths = (2 - birth.getMonth()) + 12; // Meses desde nascimento até março
    if (birth.getFullYear() === currentYear) {
      ageInMonths = 2 - birth.getMonth(); // Nasceu este ano
    } else {
      ageInMonths = (12 - birth.getMonth()) + 3; // Meses até março do próximo ano
    }
  } else if (ageAtCutoff === 1) {
    // Para crianças de 1 ano, calcular meses mais precisamente
    const monthsFromBirth = ((currentYear - birth.getFullYear()) * 12) + (2 - birth.getMonth());
    ageInMonths = monthsFromBirth;
  }
  
  // Educação Infantil - Creche (faixas específicas)
  // Berçário I: 3 a 11 meses
  // Berçário II: 1 ano a 1 ano e 11 meses (12 a 23 meses)
  // Maternal I: 2 anos a 2 anos e 11 meses
  // Maternal II: 3 anos a 3 anos e 11 meses
  
  if (ageAtCutoff < 0) return 'Idade insuficiente';
  
  // Berçário I: 3 a 11 meses
  if (ageInMonths >= 3 && ageInMonths <= 11) return 'Berçário I';
  
  // Berçário II: 1 ano a 1 ano e 11 meses (12 a 23 meses)
  if (ageInMonths >= 12 && ageInMonths <= 23) return 'Berçário II';
  
  // Maternal I: 2 anos a 2 anos e 11 meses
  if (ageAtCutoff === 2) return 'Maternal I';
  
  // Maternal II: 3 anos a 3 anos e 11 meses
  if (ageAtCutoff === 3) return 'Maternal II';
  
  // Pré I: a partir de 4 anos (completos até 31/03)
  if (ageAtCutoff === 4) return 'Pré I';
  
  // Pré II: a partir de 5 anos (completos até 31/03)
  if (ageAtCutoff === 5) return 'Pré II';
  
  // Ensino Fundamental - Anos Iniciais
  if (ageAtCutoff === 6) return '1º Ano';
  if (ageAtCutoff === 7) return '2º Ano';
  if (ageAtCutoff === 8) return '3º Ano';
  if (ageAtCutoff === 9) return '4º Ano';
  if (ageAtCutoff === 10) return '5º Ano';
  
  // Ensino Fundamental - Anos Finais
  if (ageAtCutoff === 11) return '6º Ano';
  if (ageAtCutoff === 12) return '7º Ano';
  if (ageAtCutoff === 13) return '8º Ano';
  if (ageAtCutoff === 14) return '9º Ano';
  
  // Ensino Médio
  if (ageAtCutoff === 15) return '1ª Série EM';
  if (ageAtCutoff === 16) return '2ª Série EM';
  if (ageAtCutoff === 17) return '3ª Série EM';
  
  if (ageAtCutoff >= 18) return 'Ensino Superior/EJA';
  
  return null;
};

export function StudentsComplete() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { isOnline, pendingSyncCount, triggerSync, updatePendingCount } = useOffline();
  const [students, setStudents] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const [formData, setFormData] = useState(initialFormData);
  const [dataSource, setDataSource] = useState('server'); // 'server' ou 'local'
  
  // Estado para modal de documentos
  const [showDocumentsModal, setShowDocumentsModal] = useState(false);
  const [documentStudent, setDocumentStudent] = useState(null);
  
  // Estados para busca avançada
  const [searchName, setSearchName] = useState('');
  const [searchCpf, setSearchCpf] = useState('');
  const [showNameSuggestions, setShowNameSuggestions] = useState(false);
  const [showCpfSuggestions, setShowCpfSuggestions] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  
  // Filtros por Escola, Turma e Status
  const [filterSchoolId, setFilterSchoolId] = useState('');
  const [filterClassId, setFilterClassId] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [showBatchPrintModal, setShowBatchPrintModal] = useState(false);
  
  // Paginação
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;
  
  // Ações em Lote
  const [batchMode, setBatchMode] = useState(false);
  const [selectedStudentIds, setSelectedStudentIds] = useState([]);
  const [batchSchoolId, setBatchSchoolId] = useState('');
  const [batchClassId, setBatchClassId] = useState('');
  const [batchStatus, setBatchStatus] = useState('');
  const [savingBatch, setSavingBatch] = useState(false);
  
  // Histórico do aluno
  const [studentHistory, setStudentHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [batchPrinting, setBatchPrinting] = useState(false);
  const nameInputRef = useRef(null);
  const cpfInputRef = useRef(null);
  
  // Estados para validação de CPF
  const [cpfValidation, setCpfValidation] = useState({
    cpf: { isValid: true, isDuplicate: false, message: '' },
    father_cpf: { isValid: true, isDuplicate: false, message: '' },
    mother_cpf: { isValid: true, isDuplicate: false, message: '' },
    guardian_cpf: { isValid: true, isDuplicate: false, message: '' }
  });
  
  // Estados para Atestados Médicos
  const [medicalCertificates, setMedicalCertificates] = useState([]);
  const [loadingCertificates, setLoadingCertificates] = useState(false);
  const [showCertificateModal, setShowCertificateModal] = useState(false);
  const [certificateForm, setCertificateForm] = useState({
    start_date: '',
    end_date: '',
    reason: 'Atestado Médico',
    document_url: '',
    notes: ''
  });
  const [savingCertificate, setSavingCertificate] = useState(false);
  
  // Estado para filtro de ano no vínculo de turma (novo aluno)
  const [vinculoAnoLetivo, setVinculoAnoLetivo] = useState(new Date().getFullYear());
  
  // Estados para Ações de Vínculo (Matricular, Transferir, Remanejar, Progredir)
  const [showActionModal, setShowActionModal] = useState(false);
  const [selectedAction, setSelectedAction] = useState('');
  const [actionData, setActionData] = useState({
    targetSchoolId: '',
    targetClassId: '',
    academicYear: new Date().getFullYear(),
    reason: '',
    notes: '',
    emitirHistorico: false,
    studentSeries: '' // Série do aluno para turmas multisseriadas
  });
  const [executingAction, setExecutingAction] = useState(false);
  
  // Permissões de edição/exclusão de alunos:
  // - Admin: pode editar/excluir qualquer aluno
  // - Secretário: pode editar apenas alunos ATIVOS da(s) escola(s) onde tem vínculo
  // - SEMED: apenas visualização (não pode editar/excluir)
  // - Coordenador: apenas visualização de alunos (não pode editar/excluir)
  
  const isAdmin = user?.role === 'admin' || user?.role === 'admin_teste';
  const isSecretario = user?.role === 'secretario';
  const isSemed = user?.role === 'semed';
  const isCoordenador = user?.role === 'coordenador';
  
  // IDs das escolas que o usuário (secretário) tem vínculo
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user?.school_ids, user?.school_links]);
  
  // Função para verificar se o secretário pode editar um aluno específico
  const canEditStudent = useCallback((student) => {
    if (isAdmin) return true;
    if (isSemed || isCoordenador) return false;
    if (isSecretario) {
      const isAtivo = student.status === 'active' || student.status === 'Ativo';
      const isFromUserSchool = userSchoolIds.includes(student.school_id);
      
      // Secretário pode editar:
      // 1. Alunos ATIVOS da sua escola
      // 2. Alunos NÃO ATIVOS de qualquer escola
      if (isAtivo) {
        return isFromUserSchool; // Só pode editar ativos da sua escola
      } else {
        return true; // Pode editar não-ativos de qualquer escola
      }
    }
    return true; // Outros roles podem editar
  }, [isAdmin, isSecretario, isSemed, isCoordenador, userSchoolIds]);
  
  // Permissão geral para mostrar botões de edição (será refinada por aluno)
  const canEditStudents = !isSemed && !isCoordenador;
  const canDeleteStudents = isAdmin; // Apenas admin pode excluir alunos
  
  // Permissão para registrar atestados (secretário e admin)
  const canRegisterCertificates = user?.role === 'admin' || user?.role === 'admin_teste' || user?.role === 'secretario';
  // Permissão para excluir atestados (apenas admin)
  const canDeleteCertificates = user?.role === 'admin' || user?.role === 'admin_teste';
  
  // Mantém variáveis originais para compatibilidade
  const canEdit = canEditStudents;
  const canDelete = canDeleteStudents;

  // Carrega dados com suporte offline
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        
        // Busca alunos usando serviço offline
        const studentsResult = await offlineStudentsService.getStudents();
        setStudents(studentsResult.data || []);
        setDataSource(studentsResult.source || 'server');
        
        // Busca escolas e turmas (ainda precisam de conexão)
        if (isOnline) {
          const [schoolsData, classesData] = await Promise.all([
            schoolsAPI.getAll(),
            classesAPI.getAll()
          ]);
          setSchools(schoolsData || []);
          setClasses(classesData?.items || classesData || []);
        }
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
        showAlert('error', 'Erro ao carregar dados');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [reloadTrigger, isOnline]);

  // Fechar dropdowns ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (nameInputRef.current && !nameInputRef.current.contains(event.target)) {
        setShowNameSuggestions(false);
      }
      if (cpfInputRef.current && !cpfInputRef.current.contains(event.target)) {
        setShowCpfSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const reloadData = () => setReloadTrigger(prev => prev + 1);
  
  // Força recarregar dados do servidor, limpando cache
  const forceRefreshFromServer = async () => {
    try {
      setLoading(true);
      // Limpa cache local
      await offlineStudentsService.clearCache();
      // Recarrega dados
      setReloadTrigger(prev => prev + 1);
      showAlert('success', 'Dados atualizados do servidor');
    } catch (error) {
      console.error('Erro ao forçar atualização:', error);
      showAlert('error', 'Erro ao atualizar dados');
    }
  };
  
  // Descarta alterações pendentes com problema
  const discardPendingChanges = async () => {
    if (!window.confirm('Tem certeza que deseja descartar todas as alterações pendentes? Esta ação não pode ser desfeita.')) {
      return;
    }
    try {
      setLoading(true);
      await offlineStudentsService.discardPendingChanges();
      // Atualiza contador do contexto offline
      if (typeof updatePendingCount === 'function') {
        await updatePendingCount();
      }
      // Recarrega dados do servidor
      setReloadTrigger(prev => prev + 1);
      showAlert('success', 'Alterações pendentes descartadas. Dados recarregados do servidor.');
    } catch (error) {
      console.error('Erro ao descartar alterações:', error);
      showAlert('error', 'Erro ao descartar alterações');
    } finally {
      setLoading(false);
    }
  };

  // Sistema de alertas com confirmação obrigatória
  const showAlert = (type, message, requireConfirmation = false) => {
    setAlert({ type, message, requireConfirmation });
    // Se não requer confirmação, fecha automaticamente após 5 segundos
    if (!requireConfirmation) {
      setTimeout(() => setAlert(null), 5000);
    }
  };

  // Função para fechar o alerta manualmente
  const dismissAlert = () => {
    setAlert(null);
  };

  // Função específica para erros que requerem confirmação
  const showErrorAlert = (message) => {
    showAlert('error', message, true);
  };

  const generateEnrollmentNumber = () => {
    const year = new Date().getFullYear();
    const random = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
    return `${year}${random}`;
  };

  const handleCreate = () => {
    setEditingStudent(null);
    setViewMode(false);
    setFormData({
      ...initialFormData,
      school_id: schools.length > 0 ? schools[0].id : '',
      enrollment_number: generateEnrollmentNumber()
    });
    setIsModalOpen(true);
  };

  const handleView = async (student) => {
    setEditingStudent(student);
    setViewMode(true);
    setFormData({ ...initialFormData, ...student });
    setIsModalOpen(true);
    
    // Define o ano letivo com base na turma atual do aluno
    if (student.class_id) {
      const studentClass = classes.find(c => c.id === student.class_id);
      if (studentClass?.academic_year) {
        setVinculoAnoLetivo(studentClass.academic_year);
      }
    }
    
    // Carrega histórico do aluno
    loadStudentHistory(student.id);
  };

  const handleEdit = async (student) => {
    setEditingStudent(student);
    setViewMode(false);
    setFormData({ ...initialFormData, ...student });
    setIsModalOpen(true);
    
    // Define o ano letivo com base na turma atual do aluno
    if (student.class_id) {
      const studentClass = classes.find(c => c.id === student.class_id);
      if (studentClass?.academic_year) {
        setVinculoAnoLetivo(studentClass.academic_year);
      }
    }
    
    // Carrega histórico do aluno
    loadStudentHistory(student.id);
    // Carrega atestados médicos do aluno
    loadMedicalCertificates(student.id);
  };
  
  const loadStudentHistory = async (studentId) => {
    setLoadingHistory(true);
    try {
      const history = await studentsAPI.getHistory(studentId);
      setStudentHistory(history);
    } catch (error) {
      console.error('Erro ao carregar histórico:', error);
      setStudentHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Carrega atestados médicos do aluno
  const loadMedicalCertificates = async (studentId) => {
    setLoadingCertificates(true);
    try {
      const certificates = await medicalCertificatesAPI.getByStudent(studentId);
      setMedicalCertificates(certificates);
    } catch (error) {
      console.error('Erro ao carregar atestados médicos:', error);
      setMedicalCertificates([]);
    } finally {
      setLoadingCertificates(false);
    }
  };

  // Salvar atestado médico
  const handleSaveCertificate = async () => {
    if (!certificateForm.start_date || !certificateForm.end_date) {
      showAlert('error', 'Informe as datas de início e fim do afastamento');
      return;
    }
    
    setSavingCertificate(true);
    try {
      await medicalCertificatesAPI.create({
        student_id: editingStudent.id,
        ...certificateForm
      });
      showAlert('success', 'Atestado médico registrado com sucesso');
      setShowCertificateModal(false);
      setCertificateForm({
        start_date: '',
        end_date: '',
        reason: 'Atestado Médico',
        document_url: '',
        notes: ''
      });
      // Recarrega a lista de atestados
      loadMedicalCertificates(editingStudent.id);
    } catch (error) {
      showAlert('error', extractErrorMessage(error, 'Erro ao registrar atestado'));
    } finally {
      setSavingCertificate(false);
    }
  };

  // Excluir atestado médico (apenas admin)
  const handleDeleteCertificate = async (certificateId) => {
    if (!window.confirm('Tem certeza que deseja excluir este atestado médico?')) {
      return;
    }
    
    try {
      await medicalCertificatesAPI.delete(certificateId);
      showAlert('success', 'Atestado médico excluído com sucesso');
      loadMedicalCertificates(editingStudent.id);
    } catch (error) {
      showAlert('error', extractErrorMessage(error, 'Erro ao excluir atestado'));
    }
  };

  // Abrir modal de documentos
  const handleOpenDocuments = (student) => {
    setDocumentStudent(student);
    setShowDocumentsModal(true);
  };

  // Função para impressão em lote de documentos da turma
  const handleBatchPrint = async (documentType) => {
    if (!filterClassId || displayedStudents.length === 0) return;
    
    setBatchPrinting(true);
    
    try {
      // Usar o ano letivo das matrículas (geralmente o ano atual ou configurado)
      const academicYear = 2025; // Ano letivo fixo por enquanto
      
      // Obter o blob do PDF consolidado
      const blob = await documentsAPI.getBatchDocuments(filterClassId, documentType, academicYear);
      
      // Criar URL do blob e abrir em nova aba
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      
      // Limpar URL do blob após um tempo
      setTimeout(() => window.URL.revokeObjectURL(url), 10000);
      
      showAlert('success', `PDF com ${displayedStudents.length} documento(s) gerado com sucesso!`);
    } catch (error) {
      console.error('Erro ao gerar documentos em lote:', error);
      showAlert('error', extractErrorMessage(error, 'Erro ao gerar PDF em lote'));
    } finally {
      setBatchPrinting(false);
      setShowBatchPrintModal(false);
    }
  };

  const handleDelete = async (student) => {
    if (window.confirm(`Tem certeza que deseja excluir o aluno "${student.full_name || student.enrollment_number}"?`)) {
      try {
        await studentsAPI.delete(student.id);
        showAlert('success', 'Aluno excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir aluno');
        console.error(error);
      }
    }
  };

  // ===== FUNÇÕES DE AÇÕES DE VÍNCULO =====
  
  // Verifica se a ação é permitida para o status atual do aluno
  const canExecuteAction = (action, studentStatus) => {
    const status = studentStatus?.toLowerCase()?.trim();
    
    switch (action) {
      case 'matricular':
        // Matricular: só se transferido, desistente, inativo ou sem status
        return status === 'transferred' || status === 'transferido' || 
               status === 'dropout' || status === 'desistente' ||
               status === 'inactive' || status === 'inativo' ||
               !status || status === '' || status === 'null' || status === 'undefined';
      case 'transferir':
        // Transferir: só se ativo
        return status === 'active' || status === 'ativo';
      case 'remanejar':
        // Remanejar: só se ativo
        return status === 'active' || status === 'ativo';
      case 'progredir':
        // Progredir: só se ativo
        return status === 'active' || status === 'ativo';
      default:
        return false;
    }
  };

  // Abre o modal de ação
  const handleOpenActionModal = (action) => {
    if (!editingStudent) {
      showAlert('error', 'Nenhum aluno selecionado');
      return;
    }
    
    if (!canExecuteAction(action, editingStudent.status)) {
      const statusLabels = {
        'active': 'Ativo', 'ativo': 'Ativo',
        'transferred': 'Transferido', 'transferido': 'Transferido',
        'dropout': 'Desistente', 'desistente': 'Desistente',
        'inactive': 'Inativo'
      };
      const currentStatus = statusLabels[editingStudent.status?.toLowerCase()] || editingStudent.status;
      
      const actionMessages = {
        'matricular': 'A ação "Matricular" só é permitida para alunos com status "Transferido", "Desistente", "Inativo" ou sem status definido.',
        'transferir': 'A ação "Transferir" só é permitida para alunos com status "Ativo".',
        'remanejar': 'A ação "Remanejar" só é permitida para alunos com status "Ativo".',
        'progredir': 'A ação "Progredir" só é permitida para alunos com status "Ativo".'
      };
      
      showAlert('error', `${actionMessages[action]} Status atual: ${currentStatus}`);
      return;
    }
    
    setSelectedAction(action);
    setActionData({
      targetSchoolId: action === 'remanejar' ? formData.school_id : '',
      targetClassId: '',
      academicYear: new Date().getFullYear(),
      reason: '',
      notes: '',
      emitirHistorico: false,
      studentSeries: '' // Limpa série ao abrir modal
    });
    setShowActionModal(true);
  };

  // Executa a ação selecionada
  const executeVinculoAction = async () => {
    if (!editingStudent || !selectedAction) return;
    
    setExecutingAction(true);
    
    try {
      const currentYear = new Date().getFullYear();
      let updateData = {};
      let historyEntry = {
        action_type: selectedAction,
        previous_status: editingStudent.status,
        observations: actionData.notes,
        user_name: user?.full_name || user?.email
      };
      
      switch (selectedAction) {
        case 'matricular':
          // Validações
          if (!actionData.targetSchoolId || !actionData.targetClassId) {
            showAlert('error', 'Selecione a escola e a turma para matrícula');
            setExecutingAction(false);
            return;
          }
          
          // Verifica se é turma multisseriada e se a série foi selecionada
          const targetClassForMatricula = classes.find(c => c.id === actionData.targetClassId);
          if (targetClassForMatricula?.is_multi_grade && targetClassForMatricula?.series?.length > 0) {
            if (!actionData.studentSeries) {
              showAlert('error', 'Selecione a série do aluno para esta turma multisseriada');
              setExecutingAction(false);
              return;
            }
          }
          
          updateData = {
            school_id: actionData.targetSchoolId,
            class_id: actionData.targetClassId,
            status: 'active',
            academic_year: actionData.academicYear
          };
          
          // Adiciona informação da série na observação se for turma multisseriada
          const seriesNote = actionData.studentSeries ? ` (Série: ${actionData.studentSeries})` : '';
          
          historyEntry = {
            ...historyEntry,
            action_type: 'matricula',
            new_status: 'active',
            school_id: actionData.targetSchoolId,
            class_id: actionData.targetClassId,
            academic_year: actionData.academicYear,
            observations: (actionData.notes || `Matrícula realizada para o ano letivo ${actionData.academicYear}`) + seriesNote
          };
          break;
          
        case 'transferir':
          updateData = {
            status: 'transferred'
          };
          
          historyEntry = {
            ...historyEntry,
            action_type: 'transferencia_saida',
            new_status: 'transferred',
            school_id: formData.school_id,
            class_id: formData.class_id,
            observations: actionData.reason || 'Transferência solicitada'
          };
          break;
          
        case 'remanejar':
          // Validações
          if (!actionData.targetClassId) {
            showAlert('error', 'Selecione a turma de destino para remanejamento');
            setExecutingAction(false);
            return;
          }
          
          if (actionData.targetClassId === formData.class_id) {
            showAlert('error', 'A turma de destino deve ser diferente da turma atual');
            setExecutingAction(false);
            return;
          }
          
          const turmaOrigem = classes.find(c => c.id === formData.class_id);
          const turmaDestino = classes.find(c => c.id === actionData.targetClassId);
          
          updateData = {
            class_id: actionData.targetClassId
          };
          
          historyEntry = {
            ...historyEntry,
            action_type: 'remanejamento',
            new_status: 'active',
            school_id: formData.school_id,
            class_id: actionData.targetClassId,
            observations: `Remanejado de ${turmaOrigem?.name || 'turma anterior'} para ${turmaDestino?.name || 'nova turma'}. ${actionData.notes || ''}`
          };
          break;
          
        case 'progredir':
          // Se emitir histórico, apenas muda o status para transferido
          if (actionData.emitirHistorico) {
            updateData = {
              status: 'transferred'
            };
            
            historyEntry = {
              ...historyEntry,
              action_type: 'progressao',
              new_status: 'transferred',
              school_id: formData.school_id,
              class_id: formData.class_id,
              observations: `Progressão com emissão de histórico escolar. ${actionData.notes || ''}`
            };
          } else {
            // Se não emitir histórico, seleciona nova turma
            if (!actionData.targetClassId) {
              showAlert('error', 'Selecione a turma de destino ou marque "Emitir Histórico Escolar"');
              setExecutingAction(false);
              return;
            }
            
            const turmaProgressao = classes.find(c => c.id === actionData.targetClassId);
            
            updateData = {
              class_id: actionData.targetClassId
            };
            
            historyEntry = {
              ...historyEntry,
              action_type: 'progressao',
              new_status: 'active',
              school_id: formData.school_id,
              class_id: actionData.targetClassId,
              observations: `Progressão para ${turmaProgressao?.name || 'nova turma'}. Base legal aplicada. ${actionData.notes || ''}`
            };
          }
          break;
          
        default:
          showAlert('error', 'Ação inválida');
          setExecutingAction(false);
          return;
      }
      
      // Executa a atualização
      await studentsAPI.update(editingStudent.id, updateData);
      
      // Se for remanejamento ou progressão (sem emitir histórico), copia dados para a nova turma
      if ((selectedAction === 'remanejar' || (selectedAction === 'progredir' && !actionData.emitirHistorico)) && formData.class_id && actionData.targetClassId) {
        try {
          const copyType = selectedAction === 'remanejar' ? 'remanejamento' : 'progressao';
          const API_URL = process.env.REACT_APP_BACKEND_URL;
          const token = localStorage.getItem('accessToken') || sessionStorage.getItem('accessToken');
          
          await fetch(`${API_URL}/api/students/${editingStudent.id}/copy-data`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              source_class_id: formData.class_id,
              target_class_id: actionData.targetClassId,
              copy_type: copyType,
              academic_year: new Date().getFullYear()
            })
          });
          console.log(`Dados copiados (${copyType}) da turma ${formData.class_id} para ${actionData.targetClassId}`);
        } catch (copyError) {
          console.error('Erro ao copiar dados:', copyError);
          // Não interrompe o fluxo - a ação principal já foi concluída
        }
      }
      
      // Atualiza o formData local
      setFormData(prev => ({ ...prev, ...updateData }));
      setEditingStudent(prev => ({ ...prev, ...updateData }));
      
      // Recarrega o histórico
      if (editingStudent.id) {
        const historyResponse = await studentsAPI.getHistory(editingStudent.id);
        setStudentHistory(historyResponse.data || []);
      }
      
      const actionLabels = {
        'matricular': 'Matrícula',
        'transferir': 'Transferência',
        'remanejar': 'Remanejamento',
        'progredir': 'Progressão'
      };
      
      showAlert('success', `${actionLabels[selectedAction]} realizada com sucesso!`);
      setShowActionModal(false);
      reloadData();
      
    } catch (error) {
      console.error('Erro ao executar ação:', error);
      showAlert('error', extractErrorMessage(error, 'Erro ao executar ação'));
    } finally {
      setExecutingAction(false);
    }
  };

  // Turmas filtradas para a escola de destino (usado nas ações)
  const actionTargetClasses = useMemo(() => {
    if (!actionData.targetSchoolId) return [];
    return classes.filter(c => c.school_id === actionData.targetSchoolId);
  }, [classes, actionData.targetSchoolId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validação: pelo menos um documento
    if (!formData.cpf && !formData.nis && !formData.civil_certificate_number) {
      if (!formData.no_documents_justification) {
        showErrorAlert('Informe pelo menos um documento (CPF, NIS ou Certidão) ou justifique a ausência.');
        return;
      }
    }
    
    // Validação de CPF inválido
    if (formData.cpf && !cpfValidation.cpf.isValid) {
      showErrorAlert('O CPF informado é inválido. Por favor, verifique.');
      return;
    }
    
    // Aviso de CPF duplicado (não bloqueia, mas avisa)
    if (formData.cpf && cpfValidation.cpf.isDuplicate) {
      showErrorAlert(`Atenção: ${cpfValidation.cpf.message}`);
      // Não retorna, permite continuar mas com aviso
    }
    
    setSubmitting(true);

    // Limpa dados antes de enviar (converte strings vazias para null em campos Literal)
    const cleanData = { ...formData };
    const literalFields = ['sex', 'color_race', 'civil_certificate_type', 'legal_guardian_type'];
    literalFields.forEach(field => {
      if (cleanData[field] === '') {
        cleanData[field] = null;
      }
    });

    try {
      let result;
      if (editingStudent) {
        // Atualização - usa serviço offline
        result = await offlineStudentsService.updateStudent(editingStudent.id, cleanData);
        if (result.success) {
          if (result.pendingSync) {
            showAlert('success', 'Aluno atualizado localmente. Será sincronizado quando a conexão for restaurada.');
          } else {
            showAlert('success', 'Aluno atualizado com sucesso');
          }
        } else {
          throw new Error(result.error || 'Erro ao atualizar aluno');
        }
      } else {
        // Criação - usa serviço offline
        result = await offlineStudentsService.createStudent(cleanData);
        if (result.success) {
          if (result.pendingSync) {
            showAlert('success', 'Aluno cadastrado localmente. Será sincronizado quando a conexão for restaurada.');
          } else {
            showAlert('success', 'Aluno cadastrado com sucesso');
          }
        } else {
          throw new Error(result.error || 'Erro ao cadastrar aluno');
        }
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      // Trata erro de validação do Pydantic (pode ser array de objetos)
      let errorMessage = 'Erro ao salvar aluno';
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail;
        if (Array.isArray(detail)) {
          // Pydantic validation errors
          errorMessage = detail.map(err => {
            const field = err.loc?.join('.') || 'Campo';
            return `${field}: ${err.msg}`;
          }).join('; ');
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        } else if (typeof detail === 'object' && detail.msg) {
          errorMessage = detail.msg;
        }
      } else if (error.message) {
        errorMessage = error.message;
      }
      showAlert('error', errorMessage);
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Função para validar CPF e verificar duplicidade
  const validateCpfField = useCallback(async (field, cpfValue) => {
    if (!cpfValue || cpfValue.length < 11) {
      setCpfValidation(prev => ({
        ...prev,
        [field]: { isValid: true, isDuplicate: false, message: '' }
      }));
      return;
    }

    const cpfNumbers = cpfValue.replace(/\D/g, '');
    
    // Validar formato do CPF
    const isValid = isValidCPF(cpfNumbers);
    
    if (!isValid) {
      setCpfValidation(prev => ({
        ...prev,
        [field]: { isValid: false, isDuplicate: false, message: 'CPF inválido' }
      }));
      return;
    }

    // Verificar duplicidade apenas para o CPF do aluno
    if (field === 'cpf') {
      try {
        const result = await cpfAPI.checkDuplicate(cpfNumbers, 'student', editingStudent?.id);
        setCpfValidation(prev => ({
          ...prev,
          [field]: { 
            isValid: true, 
            isDuplicate: result.is_duplicate, 
            message: result.is_duplicate ? result.message : ''
          }
        }));
      } catch (error) {
        console.error('Erro ao verificar CPF:', error);
      }
    } else {
      setCpfValidation(prev => ({
        ...prev,
        [field]: { isValid: true, isDuplicate: false, message: '' }
      }));
    }
  }, [editingStudent?.id]);

  // Efeito para validar CPF quando o valor muda
  useEffect(() => {
    const cpfFields = ['cpf', 'father_cpf', 'mother_cpf', 'guardian_cpf'];
    cpfFields.forEach(field => {
      const value = formData[field];
      if (value && value.replace(/\D/g, '').length === 11) {
        const timer = setTimeout(() => validateCpfField(field, value), 500);
        return () => clearTimeout(timer);
      }
    });
  }, [formData.cpf, formData.father_cpf, formData.mother_cpf, formData.guardian_cpf, validateCpfField]);

  const handleCheckboxChange = (field, value, checked) => {
    setFormData(prev => {
      const currentValues = prev[field] || [];
      if (checked) {
        return { ...prev, [field]: [...currentValues, value] };
      } else {
        return { ...prev, [field]: currentValues.filter(v => v !== value) };
      }
    });
  };

  const addAuthorizedPerson = () => {
    if (formData.authorized_persons.length >= 5) {
      showAlert('error', 'Máximo de 5 pessoas autorizadas');
      return;
    }
    setFormData(prev => ({
      ...prev,
      authorized_persons: [...prev.authorized_persons, { name: '', relationship: '', phone: '', document: '' }]
    }));
  };

  const updateAuthorizedPerson = (index, field, value) => {
    setFormData(prev => {
      const updated = [...prev.authorized_persons];
      updated[index] = { ...updated[index], [field]: value };
      return { ...prev, authorized_persons: updated };
    });
  };

  const removeAuthorizedPerson = (index) => {
    setFormData(prev => ({
      ...prev,
      authorized_persons: prev.authorized_persons.filter((_, i) => i !== index)
    }));
  };

  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || '-';
  };

  const getClassName = (classId) => {
    const classItem = classes.find(c => c.id === classId);
    return classItem ? classItem.name : '-';
  };

  // Turmas filtradas por escola e ano letivo selecionado (para vínculo de novo aluno)
  const filteredClasses = classes.filter(c => 
    c.school_id === formData.school_id && 
    c.academic_year === vinculoAnoLetivo
  );
  
  // Turmas filtradas para o filtro de busca
  const filterClassOptions = classes.filter(c => c.school_id === filterSchoolId);

  // Lógica de sugestões de busca
  const nameSuggestions = searchName.length >= 3 
    ? students.filter(s => 
        s.full_name?.toLowerCase().startsWith(searchName.toLowerCase())
      ).slice(0, 10)
    : [];

  const cpfSuggestions = searchCpf.length >= 3
    ? students.filter(s => 
        s.cpf?.replace(/\D/g, '').startsWith(searchCpf.replace(/\D/g, ''))
      ).slice(0, 10)
    : [];

  // Dados exibidos na tabela (filtrado por seleção, escola, turma ou todos)
  const displayedStudents = (() => {
    if (selectedStudent) return [selectedStudent];
    
    let result = students;
    
    // Filtrar por escola
    if (filterSchoolId) {
      result = result.filter(s => s.school_id === filterSchoolId);
    }
    
    // Filtrar por turma
    if (filterClassId) {
      result = result.filter(s => s.class_id === filterClassId);
    }
    
    // Filtrar por status
    if (filterStatus) {
      result = result.filter(s => s.status === filterStatus);
    }
    
    return result;
  })();

  // Paginação
  const totalPages = Math.ceil(displayedStudents.length / itemsPerPage);
  const paginatedStudents = displayedStudents.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reset página quando filtros mudam
  useEffect(() => {
    setCurrentPage(1);
  }, [filterSchoolId, filterClassId, filterStatus, selectedStudent]);

  // Turmas filtradas para ação em lote (baseado na escola selecionada para lote)
  const batchClassOptions = classes.filter(c => c.school_id === batchSchoolId);

  // Funções para Ações em Lote
  const handleToggleBatchMode = () => {
    setBatchMode(!batchMode);
    if (batchMode) {
      // Ao desativar, limpa seleções
      setSelectedStudentIds([]);
      setBatchSchoolId('');
      setBatchClassId('');
      setBatchStatus('');
    }
  };

  const handleSelectAllStudents = (checked) => {
    if (checked) {
      // Seleciona apenas os alunos da página atual
      setSelectedStudentIds(paginatedStudents.map(s => s.id));
    } else {
      setSelectedStudentIds([]);
    }
  };

  const handleSelectStudent_Batch = (studentId, checked) => {
    if (checked) {
      setSelectedStudentIds(prev => [...prev, studentId]);
    } else {
      setSelectedStudentIds(prev => prev.filter(id => id !== studentId));
    }
  };

  const handleSaveBatchActions = async () => {
    if (selectedStudentIds.length === 0) {
      showAlert('error', 'Selecione pelo menos um aluno');
      return;
    }

    if (!batchSchoolId && !batchClassId && !batchStatus) {
      showAlert('error', 'Selecione pelo menos uma ação (escola, turma ou status)');
      return;
    }

    const confirmMessage = `Você está prestes a atualizar ${selectedStudentIds.length} aluno(s). Esta ação não pode ser desfeita. Deseja continuar?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }

    setSavingBatch(true);
    let successCount = 0;
    let errorCount = 0;

    try {
      for (const studentId of selectedStudentIds) {
        const student = students.find(s => s.id === studentId);
        if (!student) continue;

        const updateData = {};
        
        if (batchSchoolId) {
          updateData.school_id = batchSchoolId;
          // Se mudar de escola, limpa a turma (a menos que uma nova turma seja selecionada)
          if (!batchClassId) {
            updateData.class_id = '';
          }
        }
        
        if (batchClassId) {
          updateData.class_id = batchClassId;
        }
        
        if (batchStatus) {
          updateData.status = batchStatus;
        }

        try {
          // Envia apenas os campos que queremos atualizar, não o objeto completo
          await studentsAPI.update(studentId, updateData);
          successCount++;
        } catch (err) {
          console.error(`Erro ao atualizar aluno ${studentId}:`, err);
          errorCount++;
        }
      }

      if (successCount > 0) {
        showAlert('success', `${successCount} aluno(s) atualizado(s) com sucesso${errorCount > 0 ? ` (${errorCount} erro(s))` : ''}`);
        // Recarrega a lista
        setReloadTrigger(prev => prev + 1);
      } else {
        showAlert('error', 'Nenhum aluno foi atualizado');
      }

      // Limpa seleções após salvar
      setSelectedStudentIds([]);
      setBatchSchoolId('');
      setBatchClassId('');
      setBatchStatus('');
      setBatchMode(false);

    } catch (error) {
      console.error('Erro ao salvar ações em lote:', error);
      showAlert('error', 'Erro ao salvar ações em lote');
    } finally {
      setSavingBatch(false);
    }
  };

  // Verifica se a turma selecionada é elegível para certificado (9º Ano ou EJA 4ª Etapa)
  const isClassEligibleForCertificate = (() => {
    if (!filterClassId) return false;
    const selectedClass = classes.find(c => c.id === filterClassId);
    if (!selectedClass) return false;
    
    const gradeLevel = (selectedClass.grade_level || '').toLowerCase();
    const educationLevel = (selectedClass.education_level || '').toLowerCase();
    
    const is9ano = gradeLevel.includes('9') && gradeLevel.includes('ano');
    const isEja4etapa = (educationLevel.includes('eja') || gradeLevel.includes('eja')) && 
                        (gradeLevel.includes('4') || gradeLevel.includes('etapa'));
    
    return is9ano || isEja4etapa;
  })();

  const handleSelectStudent = (student) => {
    setSelectedStudent(student);
    setSearchName(student.full_name || '');
    setSearchCpf(student.cpf || '');
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
  };

  const handleClearSearch = () => {
    setSearchName('');
    setSearchCpf('');
    setSelectedStudent(null);
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
    setFilterSchoolId('');
    setFilterClassId('');
  };

  const columns = [
    { header: 'Nome', accessor: 'full_name', render: (row) => row.full_name || '-' },
    { header: 'Escola', accessor: 'school_id', render: (row) => getSchoolName(row.school_id) },
    { header: 'Turma', accessor: 'class_id', render: (row) => getClassName(row.class_id) },
    { 
      header: 'Status', 
      accessor: 'status',
      render: (row) => {
        const statusConfig = {
          'active': { label: 'Ativo', class: 'bg-green-100 text-green-800' },
          'Ativo': { label: 'Ativo', class: 'bg-green-100 text-green-800' },
          'inactive': { label: 'Inativo', class: 'bg-gray-100 text-gray-800' },
          'Inativo': { label: 'Inativo', class: 'bg-gray-100 text-gray-800' },
          'dropout': { label: 'Desistente', class: 'bg-orange-100 text-orange-800' },
          'Desistente': { label: 'Desistente', class: 'bg-orange-100 text-orange-800' },
          'transferred': { label: 'Transferido', class: 'bg-yellow-100 text-yellow-800' },
          'Transferido': { label: 'Transferido', class: 'bg-yellow-100 text-yellow-800' },
          'deceased': { label: 'Falecido', class: 'bg-red-100 text-red-800' },
          'Falecido': { label: 'Falecido', class: 'bg-red-100 text-red-800' }
        };
        const config = statusConfig[row.status] || statusConfig['active'];
        return (
          <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.class}`}>
            {config.label}
          </span>
        );
      }
    },
    {
      header: 'Documentos',
      accessor: 'documents',
      render: (row) => {
        // Secretário só pode gerar documentos de alunos da sua escola
        const canGenerateDocuments = isAdmin || isSemed || 
          (isSecretario && userSchoolIds.includes(row.school_id)) ||
          (!isSecretario && !isSemed);
        
        if (!canGenerateDocuments) {
          return (
            <span className="text-gray-400 text-sm" title="Sem permissão para gerar documentos deste aluno">
              -
            </span>
          );
        }
        
        return (
          <button
            onClick={() => handleOpenDocuments(row)}
            className="flex items-center gap-1 px-2 py-1 text-sm text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors"
            title="Gerar documentos"
          >
            <Printer size={16} />
            <span className="hidden sm:inline">PDF</span>
          </button>
        );
      }
    }
  ];

  // ========== TABS CONTENT ==========
  
  const tabIdentificacao = (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Identificação do Aluno</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Código/Matrícula *</label>
          <input
            type="text"
            value={formData.enrollment_number}
            readOnly
            disabled
            className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-100 text-gray-600 cursor-not-allowed"
            placeholder="Gerado automaticamente"
          />
          <p className="text-xs text-gray-500 mt-1">Gerado automaticamente pelo sistema</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Código INEP</label>
          <input
            type="text"
            value={formData.inep_code}
            onChange={(e) => updateFormData('inep_code', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="Código INEP do aluno"
          />
        </div>
      </div>
      
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Dados Pessoais</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo *</label>
            <input
              type="text"
              value={formData.full_name}
              onChange={(e) => updateFormData('full_name', e.target.value)}
              required
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Phone size={14} className="inline mr-1" />
              Telefone
            </label>
            <input
              type="text"
              value={formatPhone(formData.phone || '')}
              onChange={(e) => updateFormData('phone', e.target.value.replace(/\D/g, '').slice(0, 11))}
              disabled={viewMode}
              maxLength={14}
              placeholder="(00)00000-0000"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Mail size={14} className="inline mr-1" />
              E-mail
            </label>
            <input
              type="email"
              value={formData.email || ''}
              onChange={(e) => updateFormData('email', e.target.value)}
              disabled={viewMode}
              placeholder="aluno@email.com"
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
                formData.email && !isValidEmail(formData.email) ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {formData.email && !isValidEmail(formData.email) && (
              <p className="text-xs text-red-500 mt-1">E-mail inválido</p>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data de Nascimento</label>
            <input
              type="date"
              value={formData.birth_date}
              onChange={(e) => updateFormData('birth_date', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Idade</label>
            <input
              type="text"
              value={formData.birth_date ? `${calculateAge(formData.birth_date)} anos` : ''}
              disabled
              className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-600 cursor-not-allowed"
              placeholder="Automático"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Série Ideal</label>
            <input
              type="text"
              value={calculateIdealGrade(formData.birth_date) || ''}
              disabled
              className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-600 cursor-not-allowed"
              placeholder="Automático"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Sexo</label>
          <select
            value={formData.sex}
            onChange={(e) => updateFormData('sex', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            <option value="masculino">Masculino</option>
            <option value="feminino">Feminino</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Nacionalidade</label>
          <input
            type="text"
            value={formData.nationality}
            onChange={(e) => updateFormData('nationality', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Cor/Raça</label>
          <select
            value={formData.color_race}
            onChange={(e) => updateFormData('color_race', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            <option value="branca">Branca</option>
            <option value="preta">Preta</option>
            <option value="parda">Parda</option>
            <option value="amarela">Amarela</option>
            <option value="indigena">Indígena</option>
            <option value="nao_declarada">Não Declarada</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Comunidade Tradicional</label>
          <select
            value={formData.comunidade_tradicional || ''}
            onChange={(e) => updateFormData('comunidade_tradicional', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            <option value="nao_pertence">Não Pertence</option>
            <option value="quilombola">Quilombola</option>
            <option value="cigano">Cigano</option>
            <option value="ribeirinho">Ribeirinho</option>
            <option value="extrativista">Extrativista</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Naturalidade (Cidade)</label>
          <CityAutocomplete
            value={formData.birth_city}
            onChange={(value) => updateFormData('birth_city', value)}
            disabled={viewMode}
            placeholder="Digite pelo menos 3 letras..."
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Estado</label>
          <select
            value={formData.birth_state}
            onChange={(e) => updateFormData('birth_state', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            {STATES.map(state => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );

  const tabDocumentos = (
    <div className="space-y-4">
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
        <p className="text-sm text-yellow-800">
          <strong>⚠️ Importante:</strong> Pelo menos um dos documentos (CPF, NIS ou Certidão de Nascimento) deve ser informado. 
          Caso não possua, justifique a ausência.
        </p>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Documentos Básicos</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
          <input
            type="text"
            value={formatCPF(formData.cpf || '')}
            onChange={(e) => updateFormData('cpf', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
              !cpfValidation.cpf.isValid ? 'border-red-500 bg-red-50' : 
              cpfValidation.cpf.isDuplicate ? 'border-yellow-500 bg-yellow-50' : 'border-gray-300'
            }`}
            placeholder="000.000.000-00"
          />
          {!cpfValidation.cpf.isValid && (
            <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
              <AlertCircle size={12} /> CPF inválido
            </p>
          )}
          {cpfValidation.cpf.isDuplicate && (
            <p className="text-xs text-yellow-600 mt-1 flex items-center gap-1">
              <AlertCircle size={12} /> {cpfValidation.cpf.message}
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">NIS (PIS/PASEP)</label>
          <input
            type="text"
            value={formatNIS(formData.nis || '')}
            onChange={(e) => updateFormData('nis', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="000.00000.00-0"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número SUS</label>
          <input
            type="text"
            value={formatSUS(formData.sus_number || '')}
            onChange={(e) => updateFormData('sus_number', e.target.value.replace(/\D/g, '').slice(0, 15))}
            disabled={viewMode}
            maxLength={19}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="000.0000.0000.0000"
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">RG</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número RG</label>
          <input
            type="text"
            value={formData.rg}
            onChange={(e) => updateFormData('rg', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Data Emissão</label>
          <input
            type="date"
            value={formData.rg_issue_date}
            onChange={(e) => updateFormData('rg_issue_date', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Órgão Emissor</label>
          <input
            type="text"
            value={formData.rg_issuer}
            onChange={(e) => updateFormData('rg_issuer', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="SSP"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Estado</label>
          <select
            value={formData.rg_state}
            onChange={(e) => updateFormData('rg_state', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">UF</option>
            {STATES.map(state => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Certidão Civil</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tipo</label>
          <select
            value={formData.civil_certificate_type}
            onChange={(e) => updateFormData('civil_certificate_type', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            <option value="nascimento">Nascimento</option>
            <option value="casamento">Casamento</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número/Matrícula</label>
          <input
            type="text"
            value={formData.civil_certificate_number}
            onChange={(e) => updateFormData('civil_certificate_number', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Livro</label>
          <input
            type="text"
            value={formData.civil_certificate_book}
            onChange={(e) => updateFormData('civil_certificate_book', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Folha</label>
          <input
            type="text"
            value={formData.civil_certificate_page}
            onChange={(e) => updateFormData('civil_certificate_page', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Cartório</label>
          <input
            type="text"
            value={formData.civil_certificate_registry}
            onChange={(e) => updateFormData('civil_certificate_registry', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Cidade</label>
          <CityAutocomplete
            value={formData.civil_certificate_city}
            onChange={(value) => updateFormData('civil_certificate_city', value)}
            disabled={viewMode}
            placeholder="Digite pelo menos 3 letras..."
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Estado</label>
          <select
            value={formData.civil_certificate_state}
            onChange={(e) => updateFormData('civil_certificate_state', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">UF</option>
            {STATES.map(state => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Passaporte (Opcional)</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número</label>
          <input
            type="text"
            value={formData.passport_number}
            onChange={(e) => updateFormData('passport_number', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">País</label>
          <input
            type="text"
            value={formData.passport_country}
            onChange={(e) => updateFormData('passport_country', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Validade</label>
          <input
            type="date"
            value={formData.passport_expiry}
            onChange={(e) => updateFormData('passport_expiry', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Justificativa de Ausência de Documentos</h3>
      <textarea
        value={formData.no_documents_justification}
        onChange={(e) => updateFormData('no_documents_justification', e.target.value)}
        disabled={viewMode}
        rows={3}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        placeholder="Caso não possua CPF, NIS ou Certidão, justifique aqui..."
      />
    </div>
  );

  const tabResponsaveis = (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Pai</h3>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo</label>
          <input
            type="text"
            value={formData.father_name}
            onChange={(e) => updateFormData('father_name', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
          <input
            type="text"
            value={formatCPF(formData.father_cpf || '')}
            onChange={(e) => updateFormData('father_cpf', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            placeholder="000.000.000-00"
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
              !cpfValidation.father_cpf.isValid ? 'border-red-500 bg-red-50' : 'border-gray-300'
            }`}
          />
          {!cpfValidation.father_cpf.isValid && (
            <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
              <AlertCircle size={12} /> CPF inválido
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
          <input
            type="text"
            value={formatPhone(formData.father_phone || '')}
            onChange={(e) => updateFormData('father_phone', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            placeholder="(00)00000-0000"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
          <input
            type="email"
            value={formData.father_email || ''}
            onChange={(e) => updateFormData('father_email', e.target.value)}
            disabled={viewMode}
            placeholder="email@exemplo.com"
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
              formData.father_email && !isValidEmail(formData.father_email) ? 'border-red-500' : 'border-gray-300'
            }`}
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Mãe</h3>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo</label>
          <input
            type="text"
            value={formData.mother_name}
            onChange={(e) => updateFormData('mother_name', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
          <input
            type="text"
            value={formatCPF(formData.mother_cpf || '')}
            onChange={(e) => updateFormData('mother_cpf', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            placeholder="000.000.000-00"
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
              !cpfValidation.mother_cpf.isValid ? 'border-red-500 bg-red-50' : 'border-gray-300'
            }`}
          />
          {!cpfValidation.mother_cpf.isValid && (
            <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
              <AlertCircle size={12} /> CPF inválido
            </p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
          <input
            type="text"
            value={formatPhone(formData.mother_phone || '')}
            onChange={(e) => updateFormData('mother_phone', e.target.value.replace(/\D/g, '').slice(0, 11))}
            disabled={viewMode}
            maxLength={14}
            placeholder="(00)00000-0000"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
          <input
            type="email"
            value={formData.mother_email || ''}
            onChange={(e) => updateFormData('mother_email', e.target.value)}
            disabled={viewMode}
            placeholder="email@exemplo.com"
            className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
              formData.mother_email && !isValidEmail(formData.mother_email) ? 'border-red-500' : 'border-gray-300'
            }`}
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Responsável Legal *</h3>
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
        <p className="text-sm text-blue-800 mb-3">
          <strong>Selecione quem é o responsável legal do aluno:</strong>
        </p>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="legal_guardian_type"
              value="mother"
              checked={formData.legal_guardian_type === 'mother'}
              onChange={(e) => updateFormData('legal_guardian_type', e.target.value)}
              disabled={viewMode}
              className="h-4 w-4 text-blue-600"
            />
            <span className="text-sm text-gray-700">Mãe</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="legal_guardian_type"
              value="father"
              checked={formData.legal_guardian_type === 'father'}
              onChange={(e) => updateFormData('legal_guardian_type', e.target.value)}
              disabled={viewMode}
              className="h-4 w-4 text-blue-600"
            />
            <span className="text-sm text-gray-700">Pai</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="legal_guardian_type"
              value="both"
              checked={formData.legal_guardian_type === 'both'}
              onChange={(e) => updateFormData('legal_guardian_type', e.target.value)}
              disabled={viewMode}
              className="h-4 w-4 text-blue-600"
            />
            <span className="text-sm text-gray-700">Mãe e Pai</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="legal_guardian_type"
              value="other"
              checked={formData.legal_guardian_type === 'other'}
              onChange={(e) => updateFormData('legal_guardian_type', e.target.value)}
              disabled={viewMode}
              className="h-4 w-4 text-blue-600"
            />
            <span className="text-sm text-gray-700">Outro Responsável</span>
          </label>
        </div>
      </div>

      {/* Mostrar campos de outro responsável apenas se "Outro" estiver selecionado */}
      {formData.legal_guardian_type === 'other' && (
        <div className="grid grid-cols-1 md:grid-cols-6 gap-4 p-4 bg-gray-50 rounded-lg">
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo *</label>
            <input
              type="text"
              value={formData.guardian_name}
              onChange={(e) => updateFormData('guardian_name', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Parentesco *</label>
            <select
              value={formData.guardian_relationship}
              onChange={(e) => updateFormData('guardian_relationship', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            >
              <option value="">Selecione</option>
              <option value="avo">Avô/Avó</option>
              <option value="tio">Tio/Tia</option>
              <option value="irmao">Irmão/Irmã</option>
              <option value="padrasto">Padrasto</option>
              <option value="madrasta">Madrasta</option>
              <option value="tutor">Tutor Legal</option>
              <option value="outro">Outro</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
            <input
              type="text"
              value={formatCPF(formData.guardian_cpf || '')}
              onChange={(e) => updateFormData('guardian_cpf', e.target.value.replace(/\D/g, '').slice(0, 11))}
              disabled={viewMode}
              maxLength={14}
              placeholder="000.000.000-00"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
            <input
              type="text"
              value={formatPhone(formData.guardian_phone || '')}
              onChange={(e) => updateFormData('guardian_phone', e.target.value.replace(/\D/g, '').slice(0, 11))}
              disabled={viewMode}
              maxLength={14}
              placeholder="(00)00000-0000"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
            <input
              type="email"
              value={formData.guardian_email || ''}
              onChange={(e) => updateFormData('guardian_email', e.target.value)}
              disabled={viewMode}
              placeholder="email@exemplo.com"
              className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${
                formData.guardian_email && !isValidEmail(formData.guardian_email) ? 'border-red-500' : 'border-gray-300'
              }`}
            />
          </div>
        </div>
      )}

      <div className="border-t pt-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Autorizados a Buscar (Máx. 5)</h3>
          {!viewMode && (
            <button
              type="button"
              onClick={addAuthorizedPerson}
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 text-sm"
            >
              <Plus size={16} /> Adicionar
            </button>
          )}
        </div>

        {formData.authorized_persons.map((person, index) => (
          <div key={index} className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4 p-4 bg-gray-50 rounded-lg">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome</label>
              <input
                type="text"
                value={person.name}
                onChange={(e) => updateAuthorizedPerson(index, 'name', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Parentesco</label>
              <input
                type="text"
                value={person.relationship}
                onChange={(e) => updateAuthorizedPerson(index, 'relationship', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
              <input
                type="text"
                value={person.phone}
                onChange={(e) => updateAuthorizedPerson(index, 'phone', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <label className="block text-sm font-medium text-gray-700 mb-1">Doc.</label>
                <input
                  type="text"
                  value={person.document}
                  onChange={(e) => updateAuthorizedPerson(index, 'document', e.target.value)}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  placeholder="CPF/RG"
                />
              </div>
              {!viewMode && (
                <button
                  type="button"
                  onClick={() => removeAuthorizedPerson(index)}
                  className="p-2 text-red-600 hover:bg-red-100 rounded-lg"
                >
                  <Trash2 size={18} />
                </button>
              )}
            </div>
          </div>
        ))}

        {formData.authorized_persons.length === 0 && (
          <p className="text-gray-500 text-sm text-center py-4">Nenhuma pessoa autorizada cadastrada</p>
        )}
      </div>
    </div>
  );

  const tabComplementares = (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Transporte Escolar</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="uses_transport"
            checked={formData.uses_school_transport}
            onChange={(e) => updateFormData('uses_school_transport', e.target.checked)}
            disabled={viewMode}
            className="h-4 w-4 text-blue-600 rounded"
          />
          <label htmlFor="uses_transport" className="text-sm text-gray-700">Utiliza transporte escolar público</label>
        </div>
        {formData.uses_school_transport && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Veículo</label>
              <input
                type="text"
                value={formData.transport_type}
                onChange={(e) => updateFormData('transport_type', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                placeholder="Ex: Ônibus escolar"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Rota</label>
              <input
                type="text"
                value={formData.transport_route}
                onChange={(e) => updateFormData('transport_route', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>
          </>
        )}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Outras Informações</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Religião</label>
          <input
            type="text"
            value={formData.religion}
            onChange={(e) => updateFormData('religion', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div className="flex items-center gap-4">
          <label className="text-sm font-medium text-gray-700">Alfabetizado:</label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="is_literate"
              checked={formData.is_literate === true}
              onChange={() => updateFormData('is_literate', true)}
              disabled={viewMode}
            />
            <span className="text-sm">Sim</span>
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="is_literate"
              checked={formData.is_literate === false}
              onChange={() => updateFormData('is_literate', false)}
              disabled={viewMode}
            />
            <span className="text-sm">Não</span>
          </label>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is_emancipated"
            checked={formData.is_emancipated}
            onChange={(e) => updateFormData('is_emancipated', e.target.checked)}
            disabled={viewMode}
            className="h-4 w-4 text-blue-600 rounded"
          />
          <label htmlFor="is_emancipated" className="text-sm text-gray-700">Emancipado</label>
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Benefícios</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {BENEFITS_OPTIONS.map(benefit => (
          <label key={benefit} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={formData.benefits.includes(benefit)}
              onChange={(e) => handleCheckboxChange('benefits', benefit, e.target.checked)}
              disabled={viewMode}
              className="h-4 w-4 text-blue-600 rounded"
            />
            <span className="text-sm text-gray-700">{benefit}</span>
          </label>
        ))}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Deficiências / Transtornos</h3>
      <div className="flex items-center gap-2 mb-4">
        <input
          type="checkbox"
          id="has_disability"
          checked={formData.has_disability}
          onChange={(e) => updateFormData('has_disability', e.target.checked)}
          disabled={viewMode}
          className="h-4 w-4 text-blue-600 rounded"
        />
        <label htmlFor="has_disability" className="text-sm text-gray-700">Possui deficiência ou transtorno</label>
      </div>
      
      {formData.has_disability && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            {DISABILITIES_OPTIONS.map(disability => (
              <label key={disability} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.disabilities.includes(disability)}
                  onChange={(e) => handleCheckboxChange('disabilities', disability, e.target.checked)}
                  disabled={viewMode}
                  className="h-4 w-4 text-blue-600 rounded"
                />
                <span className="text-sm text-gray-700">{disability}</span>
              </label>
            ))}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Detalhes / Necessidades Especiais</label>
            <textarea
              value={formData.disability_details}
              onChange={(e) => updateFormData('disability_details', e.target.value)}
              disabled={viewMode}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              placeholder="Descreva detalhes sobre as necessidades especiais do aluno..."
            />
          </div>
        </>
      )}
    </div>
  );

  const tabAnexos = (
    <div className="space-y-6">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
        <p className="text-sm text-blue-800">
          <strong>ℹ️ Formatos aceitos:</strong> JPG, PNG, PDF, GIF, DOC, DOCX (máx. 5MB por arquivo)
        </p>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Foto do Aluno</h3>
      <div className="flex items-center gap-4">
        {formData.photo_url ? (
          <div className="relative">
            <img 
              src={uploadAPI.getUrl(formData.photo_url)} 
              alt="Foto do aluno" 
              className="w-32 h-32 object-cover rounded-lg border"
            />
            {!viewMode && (
              <button
                type="button"
                onClick={() => updateFormData('photo_url', '')}
                className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ) : (
          <div className="w-32 h-32 bg-gray-100 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center">
            <User className="text-gray-400" size={48} />
          </div>
        )}
        {!viewMode && (
          <div>
            <label className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer transition-colors">
              <Upload size={18} />
              <span>Selecionar Foto</span>
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (file) {
                    try {
                      const result = await uploadAPI.upload(file, 'student');
                      updateFormData('photo_url', result.url);
                      showAlert('success', 'Foto enviada com sucesso');
                    } catch (error) {
                      showAlert('error', 'Erro ao enviar foto');
                    }
                  }
                }}
              />
            </label>
            <p className="text-xs text-gray-500 mt-1">JPG, PNG ou GIF</p>
          </div>
        )}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Laudo Médico</h3>
      <div className="flex items-center gap-4">
        {formData.medical_report_url ? (
          <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg">
            <FileText className="text-green-600" size={24} />
            <div>
              <p className="text-sm font-medium text-green-800">Laudo anexado</p>
              <a 
                href={uploadAPI.getUrl(formData.medical_report_url)} 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-600 text-sm hover:underline"
              >
                Visualizar arquivo
              </a>
            </div>
            {!viewMode && (
              <button
                type="button"
                onClick={() => updateFormData('medical_report_url', '')}
                className="ml-auto p-1 text-red-600 hover:bg-red-100 rounded"
              >
                <Trash2 size={18} />
              </button>
            )}
          </div>
        ) : (
          !viewMode && (
            <label className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 cursor-pointer transition-colors border border-gray-300">
              <Upload size={18} />
              <span>Anexar Laudo</span>
              <input
                type="file"
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files[0];
                  if (file) {
                    try {
                      const result = await uploadAPI.upload(file, 'laudo');
                      updateFormData('medical_report_url', result.url);
                      showAlert('success', 'Laudo enviado com sucesso');
                    } catch (error) {
                      showAlert('error', 'Erro ao enviar laudo');
                    }
                  }
                }}
              />
            </label>
          )
        )}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Documentos Gerais</h3>
      <p className="text-sm text-gray-500 mb-2">Certidões, comprovantes, declarações, etc.</p>
      
      <div className="space-y-2">
        {formData.documents_urls.map((url, index) => (
          <div key={index} className="flex items-center gap-3 p-3 bg-gray-50 border border-gray-200 rounded-lg">
            <FileText className="text-gray-600" size={20} />
            <span className="flex-1 text-sm text-gray-700 truncate">
              {url.split('/').pop() || `Documento ${index + 1}`}
            </span>
            <a 
              href={uploadAPI.getUrl(url)} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-600 text-sm hover:underline"
            >
              Visualizar
            </a>
            {!viewMode && (
              <button
                type="button"
                onClick={() => {
                  const newUrls = formData.documents_urls.filter((_, i) => i !== index);
                  updateFormData('documents_urls', newUrls);
                }}
                className="p-1 text-red-600 hover:bg-red-100 rounded"
              >
                <Trash2 size={18} />
              </button>
            )}
          </div>
        ))}
        
        {!viewMode && (
          <label className="flex items-center justify-center gap-2 px-4 py-3 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 hover:bg-blue-50 cursor-pointer transition-colors">
            <Plus size={18} className="text-gray-500" />
            <span className="text-gray-600">Adicionar documento</span>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files[0];
                if (file) {
                  try {
                    const result = await uploadAPI.upload(file, 'document');
                    updateFormData('documents_urls', [...formData.documents_urls, result.url]);
                    showAlert('success', 'Documento enviado com sucesso');
                  } catch (error) {
                    showAlert('error', 'Erro ao enviar documento');
                  }
                }
              }}
            />
          </label>
        )}
      </div>

      {/* Seção de Atestados Médicos */}
      {editingStudent && (
        <>
          <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 flex items-center gap-2 mt-8">
            <Stethoscope className="text-red-600" size={20} />
            Atestados Médicos
          </h3>
          <p className="text-sm text-gray-500 mb-2">
            Registre atestados médicos para justificar ausências. Os dias cobertos pelo atestado aparecerão como "AM" na frequência.
          </p>
          
          {loadingCertificates ? (
            <div className="text-center py-4 text-gray-500">Carregando atestados...</div>
          ) : (
            <>
              {/* Lista de Atestados */}
              {medicalCertificates.length > 0 ? (
                <div className="space-y-2">
                  {medicalCertificates.map((cert) => (
                    <div key={cert.id} className="flex items-center gap-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                      <Stethoscope className="text-red-600 flex-shrink-0" size={20} />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-red-800">
                          {cert.reason || 'Atestado Médico'}
                        </p>
                        <p className="text-xs text-red-600">
                          Período: {new Date(cert.start_date + 'T12:00:00').toLocaleDateString('pt-BR')} a {new Date(cert.end_date + 'T12:00:00').toLocaleDateString('pt-BR')}
                        </p>
                        {cert.notes && (
                          <p className="text-xs text-gray-600 mt-1">{cert.notes}</p>
                        )}
                        <p className="text-xs text-gray-400 mt-1">
                          Registrado por: {cert.created_by_name || 'Sistema'}
                        </p>
                      </div>
                      {cert.document_url && (
                        <a 
                          href={uploadAPI.getUrl(cert.document_url)} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-600 text-xs hover:underline"
                        >
                          Ver documento
                        </a>
                      )}
                      {canDeleteCertificates && (
                        <button
                          type="button"
                          onClick={() => handleDeleteCertificate(cert.id)}
                          className="p-1 text-red-600 hover:bg-red-100 rounded"
                          title="Excluir atestado (apenas admin)"
                        >
                          <Trash2 size={18} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 italic">Nenhum atestado médico registrado.</p>
              )}
              
              {/* Botão para Registrar Atestado */}
              {canRegisterCertificates && !viewMode && (
                <button
                  type="button"
                  onClick={() => setShowCertificateModal(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors mt-4"
                >
                  <Plus size={18} />
                  Registrar Atestado Médico
                </button>
              )}
            </>
          )}
        </>
      )}
    </div>
  );

  const tabTurma = (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Vínculo com Turma</h3>
      
      {/* Exibição do vínculo atual (aluno existente) */}
      {editingStudent ? (
        <div className="space-y-4">
          {/* Linha com seletor de ano para filtro de turmas */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Selecione o ano e a turma para vincular o aluno</span>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
              <select
                value={vinculoAnoLetivo}
                onChange={(e) => {
                  setVinculoAnoLetivo(parseInt(e.target.value));
                }}
                disabled={viewMode}
                className="px-3 py-1.5 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-blue-50 text-blue-700 font-medium"
              >
                {[2025, 2026, 2027, 2028, 2029, 2030].map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
              <select
                value={formData.school_id || ''}
                onChange={(e) => {
                  updateFormData('school_id', e.target.value);
                  updateFormData('class_id', '');
                }}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Selecione uma escola</option>
                {schools.map(school => (
                  <option key={school.id} value={school.id}>{school.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Turma ({vinculoAnoLetivo})</label>
              <select
                value={formData.class_id || ''}
                onChange={(e) => updateFormData('class_id', e.target.value)}
                disabled={viewMode || !formData.school_id}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">{formData.school_id ? 'Selecione uma turma' : 'Selecione a escola primeiro'}</option>
                {filteredClasses.map(classItem => (
                  <option key={classItem.id} value={classItem.id}>
                    {classItem.name}
                  </option>
                ))}
              </select>
              {filteredClasses.length === 0 && formData.school_id && (
                <p className="text-sm text-yellow-600 mt-1">Nenhuma turma cadastrada para esta escola em {vinculoAnoLetivo}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={formData.status}
                onChange={(e) => updateFormData('status', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
                <option value="dropout">Desistente</option>
                <option value="transferred">Transferido</option>
                <option value="deceased">Falecido</option>
              </select>
            </div>
          
            {/* Campo de Ação */}
            {!viewMode && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ação</label>
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      handleOpenActionModal(e.target.value);
                      e.target.value = '';
                    }
                  }}
                  className="w-full px-3 py-2 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-blue-50 text-blue-700 font-medium cursor-pointer"
                >
                  <option value="">Selecione uma ação...</option>
                  <option value="matricular" disabled={!canExecuteAction('matricular', editingStudent?.status)}>
                    📋 Matricular {!canExecuteAction('matricular', editingStudent?.status) ? '(indisponível)' : ''}
                  </option>
                  <option value="transferir" disabled={!canExecuteAction('transferir', editingStudent?.status)}>
                    🔄 Transferir {!canExecuteAction('transferir', editingStudent?.status) ? '(indisponível)' : ''}
                  </option>
                  <option value="remanejar" disabled={!canExecuteAction('remanejar', editingStudent?.status)}>
                    ↔️ Remanejar {!canExecuteAction('remanejar', editingStudent?.status) ? '(indisponível)' : ''}
                  </option>
                  <option value="progredir" disabled={!canExecuteAction('progredir', editingStudent?.status)}>
                    ⬆️ Progredir {!canExecuteAction('progredir', editingStudent?.status) ? '(indisponível)' : ''}
                  </option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {formData.status === 'active' || formData.status === 'ativo' 
                    ? 'Disponível: Transferir, Remanejar, Progredir'
                    : 'Disponível: Matricular'}
                </p>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Novo aluno - campos editáveis */
        <div className="space-y-4">
          {/* Linha com título e seletor de ano */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Selecione o ano e a escola para vincular o aluno</span>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
              <select
                value={vinculoAnoLetivo}
                onChange={(e) => {
                  setVinculoAnoLetivo(parseInt(e.target.value));
                  // Limpar turma selecionada ao trocar o ano
                  updateFormData('class_id', '');
                }}
                disabled={viewMode}
                className="px-3 py-1.5 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-blue-50 text-blue-700 font-medium"
              >
                {[2025, 2026, 2027, 2028, 2029, 2030].map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
              <select
                value={formData.school_id}
                onChange={(e) => {
                  updateFormData('school_id', e.target.value);
                  // Limpar turma ao trocar de escola
                  updateFormData('class_id', '');
                }}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Selecione (opcional)</option>
                {schools.map(school => (
                  <option key={school.id} value={school.id}>{school.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Turma ({vinculoAnoLetivo})</label>
              <select
                value={formData.class_id}
                onChange={(e) => updateFormData('class_id', e.target.value)}
                disabled={viewMode || !formData.school_id}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">{formData.school_id ? 'Selecione uma turma (opcional)' : 'Selecione a escola primeiro'}</option>
                {filteredClasses.map(classItem => (
                  <option key={classItem.id} value={classItem.id}>
                    {classItem.name}
                  </option>
                ))}
              </select>
              {filteredClasses.length === 0 && formData.school_id && (
                <p className="text-sm text-yellow-600 mt-1">Nenhuma turma cadastrada para esta escola em {vinculoAnoLetivo}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={formData.status}
                onChange={(e) => updateFormData('status', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
                <option value="dropout">Desistente</option>
                <option value="transferred">Transferido</option>
              <option value="deceased">Falecido</option>
            </select>
          </div>
        </div>
        </div>
      )}

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-8">Observações</h3>
      <textarea
        value={formData.observations}
        onChange={(e) => updateFormData('observations', e.target.value)}
        disabled={viewMode}
        rows={5}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        placeholder="Anotações adicionais sobre o aluno..."
      />

      {/* Histórico do Aluno */}
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-8 flex items-center gap-2">
        <Calendar size={18} />
        Histórico do Aluno
      </h3>
      {loadingHistory ? (
        <div className="flex items-center justify-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-500">Carregando histórico...</span>
        </div>
      ) : studentHistory.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-100">
                <th className="px-3 py-2 text-left font-medium">Data/Hora</th>
                <th className="px-3 py-2 text-left font-medium">Ação</th>
                <th className="px-3 py-2 text-left font-medium">Escola</th>
                <th className="px-3 py-2 text-left font-medium">Turma</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Responsável</th>
              </tr>
            </thead>
            <tbody>
              {studentHistory.map((item, idx) => (
                <tr key={item.id || idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {new Date(item.action_date).toLocaleString('pt-BR', { 
                      day: '2-digit', 
                      month: '2-digit', 
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      item.action_type === 'matricula' ? 'bg-green-100 text-green-700' :
                      item.action_type === 'remanejamento' ? 'bg-blue-100 text-blue-700' :
                      item.action_type === 'transferencia_saida' ? 'bg-orange-100 text-orange-700' :
                      item.action_type === 'transferencia_entrada' ? 'bg-purple-100 text-purple-700' :
                      item.action_type === 'progressao' ? 'bg-purple-100 text-purple-700' :
                      item.action_type === 'mudanca_status' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {item.action_type === 'matricula' ? 'Matrícula' :
                       item.action_type === 'remanejamento' ? 'Remanejamento' :
                       item.action_type === 'transferencia_saida' ? 'Transf. Saída' :
                       item.action_type === 'transferencia_entrada' ? 'Transf. Entrada' :
                       item.action_type === 'progressao' ? 'Progressão' :
                       item.action_type === 'mudanca_status' ? 'Mudança Status' :
                       'Edição'}
                    </span>
                  </td>
                  <td className="px-3 py-2">{item.school_name || '-'}</td>
                  <td className="px-3 py-2">{item.class_name || '-'}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-1 rounded text-xs ${
                      item.new_status === 'active' ? 'bg-green-100 text-green-700' :
                      item.new_status === 'transferred' ? 'bg-orange-100 text-orange-700' :
                      item.new_status === 'inactive' ? 'bg-gray-100 text-gray-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {item.new_status === 'active' ? 'Ativo' :
                       item.new_status === 'transferred' ? 'Transferido' :
                       item.new_status === 'inactive' ? 'Inativo' :
                       item.new_status === 'dropout' ? 'Desistente' :
                       item.new_status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{item.user_name || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-gray-500 text-sm py-4">Nenhum histórico registrado para este aluno.</p>
      )}
    </div>
  );

  const tabs = [
    { id: 'identificacao', label: 'Identificação', content: tabIdentificacao },
    { id: 'documentos', label: 'Documentos', content: tabDocumentos },
    { id: 'responsaveis', label: 'Responsáveis', content: tabResponsaveis },
    { id: 'complementares', label: 'Info. Complementares', content: tabComplementares },
    { id: 'anexos', label: 'Anexos', content: tabAnexos },
    { id: 'turma', label: 'Turma/Observações', content: tabTurma }
  ];

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                Alunos(as)
                {!isOnline && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-amber-100 text-amber-700 text-xs font-medium rounded-full">
                    <CloudOff size={12} />
                    Modo Offline
                  </span>
                )}
                {dataSource === 'local' && isOnline && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded-full">
                    <Cloud size={12} />
                    Cache Local
                  </span>
                )}
              </h1>
              <p className="text-gray-600 text-sm">
                Gerencie o cadastro completo de alunos(as)
                {pendingSyncCount > 0 && (
                  <span className="ml-2 text-amber-600">
                    ({pendingSyncCount} alteração(ões) pendente(s) de sincronização)
                  </span>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Botão para forçar atualização do servidor */}
            <button
              onClick={forceRefreshFromServer}
              className="bg-gray-100 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-200 transition-colors flex items-center space-x-2"
              title="Forçar atualização do servidor"
            >
              <RefreshCw size={18} />
              <span className="hidden sm:inline">Atualizar</span>
            </button>
            {pendingSyncCount > 0 && isOnline && (
              <>
                <button
                  onClick={triggerSync}
                  className="bg-amber-500 text-white px-3 py-2 rounded-lg hover:bg-amber-600 transition-colors flex items-center space-x-2"
                  title="Sincronizar alterações pendentes"
                >
                  <RefreshCw size={18} />
                  <span>Sincronizar</span>
                </button>
                <button
                  onClick={discardPendingChanges}
                  className="bg-red-100 text-red-700 px-3 py-2 rounded-lg hover:bg-red-200 transition-colors flex items-center space-x-2"
                  title="Descartar alterações pendentes com problema"
                >
                  <Trash2 size={18} />
                  <span className="hidden sm:inline">Descartar</span>
                </button>
              </>
            )}
            {canEdit && (
              <button
                onClick={handleCreate}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
              >
                <Plus size={20} />
                <span>Novo(a) Aluno(a)</span>
              </button>
            )}
          </div>
        </div>

        {/* Banner de Alerta Fixo no Topo */}
        {alert && (
          <div className={`fixed top-0 left-0 right-0 z-50 shadow-lg ${
            alert.type === 'success' ? 'bg-green-500' : 'bg-red-500'
          }`}>
            <div className="max-w-7xl mx-auto px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  {alert.type === 'success' ? (
                    <CheckCircle className="text-white mr-3 flex-shrink-0" size={24} />
                  ) : (
                    <AlertCircle className="text-white mr-3 flex-shrink-0" size={24} />
                  )}
                  <p className="text-white font-medium text-base">
                    {alert.message}
                  </p>
                </div>
                <button
                  onClick={dismissAlert}
                  className={`ml-4 px-6 py-2 rounded-lg font-semibold transition-colors ${
                    alert.type === 'success' 
                      ? 'bg-green-600 hover:bg-green-700 text-white border-2 border-white' 
                      : 'bg-red-600 hover:bg-red-700 text-white border-2 border-white'
                  }`}
                >
                  OK
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Campos de Busca Avançada */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div className="flex flex-wrap items-end gap-4">
            {/* Busca por Nome */}
            <div className="relative flex-1 min-w-[250px]" ref={nameInputRef}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Search size={14} className="inline mr-1" />
                Buscar por Nome
              </label>
              <input
                type="text"
                value={searchName}
                onChange={(e) => {
                  setSearchName(e.target.value);
                  setShowNameSuggestions(e.target.value.length >= 3);
                  if (e.target.value.length < 3) {
                    setSelectedStudent(null);
                  }
                }}
                onFocus={() => setShowNameSuggestions(searchName.length >= 3)}
                placeholder="Digite pelo menos 3 letras..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              {/* Dropdown de sugestões por nome */}
              {showNameSuggestions && nameSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                  {nameSuggestions.map((student) => (
                    <button
                      key={student.id}
                      type="button"
                      onClick={() => handleSelectStudent(student)}
                      className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                    >
                      <div className="font-medium text-gray-900">{student.full_name}</div>
                      <div className="text-xs text-gray-500">
                        Matrícula: {student.enrollment_number} | CPF: {student.cpf || '-'}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {showNameSuggestions && searchName.length >= 3 && nameSuggestions.length === 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg p-3 text-gray-500 text-sm">
                  Nenhum aluno encontrado
                </div>
              )}
            </div>

            {/* Busca por CPF */}
            <div className="relative flex-1 min-w-[250px]" ref={cpfInputRef}>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Search size={14} className="inline mr-1" />
                Buscar por CPF
              </label>
              <input
                type="text"
                value={searchCpf}
                onChange={(e) => {
                  setSearchCpf(e.target.value);
                  setShowCpfSuggestions(e.target.value.length >= 3);
                  if (e.target.value.length < 3) {
                    setSelectedStudent(null);
                  }
                }}
                onFocus={() => setShowCpfSuggestions(searchCpf.length >= 3)}
                placeholder="Digite pelo menos 3 dígitos..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              {/* Dropdown de sugestões por CPF */}
              {showCpfSuggestions && cpfSuggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                  {cpfSuggestions.map((student) => (
                    <button
                      key={student.id}
                      type="button"
                      onClick={() => handleSelectStudent(student)}
                      className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                    >
                      <div className="font-medium text-gray-900">{student.cpf}</div>
                      <div className="text-xs text-gray-500">
                        {student.full_name} | Matrícula: {student.enrollment_number}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {showCpfSuggestions && searchCpf.length >= 3 && cpfSuggestions.length === 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg p-3 text-gray-500 text-sm">
                  Nenhum aluno encontrado
                </div>
              )}
            </div>

            {/* Botão Limpar Consulta */}
            {(searchName || searchCpf || selectedStudent || filterSchoolId || filterClassId) && (
              <button
                onClick={handleClearSearch}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors border border-gray-300"
              >
                <X size={18} />
                <span>Limpar Filtros</span>
              </button>
            )}
          </div>

          {/* Filtros por Escola e Turma */}
          <div className="flex flex-wrap items-end gap-4 mt-4 pt-4 border-t border-gray-200">
            {/* Filtro por Escola */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Building2 size={14} className="inline mr-1" />
                Filtrar por Escola
              </label>
              <select
                value={filterSchoolId}
                onChange={(e) => {
                  setFilterSchoolId(e.target.value);
                  setFilterClassId(''); // Limpa turma ao mudar escola
                  setSelectedStudent(null);
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Todas as escolas</option>
                {schools.map(school => (
                  <option key={school.id} value={school.id}>{school.name}</option>
                ))}
              </select>
            </div>

            {/* Filtro por Turma */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Users size={14} className="inline mr-1" />
                Filtrar por Turma
              </label>
              <select
                value={filterClassId}
                onChange={(e) => {
                  setFilterClassId(e.target.value);
                  setSelectedStudent(null);
                }}
                disabled={!filterSchoolId}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                <option value="">Todas as turmas</option>
                {filterClassOptions.map(classItem => (
                  <option key={classItem.id} value={classItem.id}>
                    {classItem.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Filtro por Status */}
            <div className="flex-1 min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <Filter size={14} className="inline mr-1" />
                Filtrar por Status
              </label>
              <select
                value={filterStatus}
                onChange={(e) => {
                  setFilterStatus(e.target.value);
                  setSelectedStudent(null);
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Todos os status</option>
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
                <option value="dropout">Desistente</option>
                <option value="transferred">Transferido</option>
                <option value="deceased">Falecido</option>
              </select>
            </div>

            {/* Botão Impressão em Lote (aparece quando uma turma é selecionada) */}
            {filterClassId && displayedStudents.length > 0 && (
              <button
                onClick={() => setShowBatchPrintModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <Printer size={18} />
                <span>Imprimir Turma ({displayedStudents.length} alunos)</span>
              </button>
            )}
          </div>

          {/* Indicador de filtro ativo */}
          {selectedStudent && (
            <div className="mt-3 flex items-center gap-2 text-sm text-blue-600 bg-blue-50 px-3 py-2 rounded-lg">
              <span>Exibindo resultado para:</span>
              <strong>{selectedStudent.full_name}</strong>
              <span className="text-gray-400">|</span>
              <span>CPF: {selectedStudent.cpf || '-'}</span>
            </div>
          )}
          
          {/* Indicador de filtro por escola/turma/status */}
          {!selectedStudent && (filterSchoolId || filterClassId || filterStatus) && (
            <div className="mt-3 flex items-center gap-2 text-sm text-green-600 bg-green-50 px-3 py-2 rounded-lg">
              <span>Filtro ativo:</span>
              {filterSchoolId && <strong>{getSchoolName(filterSchoolId)}</strong>}
              {filterClassId && (
                <>
                  <span className="text-gray-400">→</span>
                  <strong>{getClassName(filterClassId)}</strong>
                </>
              )}
              {filterStatus && (
                <>
                  <span className="text-gray-400">→</span>
                  <strong>{filterStatus === 'active' ? 'Ativo' : filterStatus === 'inactive' ? 'Inativo' : filterStatus === 'dropout' ? 'Desistente' : filterStatus === 'transferred' ? 'Transferido' : filterStatus === 'deceased' ? 'Falecido' : filterStatus}</strong>
                </>
              )}
              <span className="text-gray-400">|</span>
              <span>{displayedStudents.length} aluno(s)</span>
            </div>
          )}
        </div>

        {/* Linha de Total e Toggle de Ações em Lote */}
        <div className="flex items-center justify-between bg-gray-50 px-4 py-3 rounded-lg mb-4">
          <div className="text-sm text-gray-600">
            <span className="font-medium">Total: {displayedStudents.length} registros</span>
            {batchMode && selectedStudentIds.length > 0 && (
              <span className="ml-2 text-blue-600">({selectedStudentIds.length} selecionado(s))</span>
            )}
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={batchMode}
              onChange={handleToggleBatchMode}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700">Ações em Lote</span>
          </label>
        </div>

        {/* Tabela com suporte a Ações em Lote */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              {/* Linha de Ações em Lote (aparece apenas quando batchMode está ativo) */}
              {batchMode && (
                <thead className="bg-blue-50">
                  <tr>
                    <th className="px-4 py-3 text-left">
                      <input
                        type="checkbox"
                        checked={paginatedStudents.length > 0 && paginatedStudents.every(s => selectedStudentIds.includes(s.id))}
                        onChange={(e) => handleSelectAllStudents(e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                        title="Selecionar todos desta página"
                      />
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-blue-800">
                      {/* Vazio - coluna Nome */}
                    </th>
                    <th className="px-4 py-3 text-left">
                      <div className="space-y-1">
                        <span className="text-xs font-medium text-blue-800">Transferir para:</span>
                        <select
                          value={batchSchoolId}
                          onChange={(e) => {
                            setBatchSchoolId(e.target.value);
                            setBatchClassId(''); // Limpa turma ao mudar escola
                          }}
                          className="w-full px-2 py-1 text-xs border border-blue-300 rounded focus:ring-blue-500 focus:border-blue-500"
                        >
                          <option value="">Manter atual</option>
                          {schools.map(school => (
                            <option key={school.id} value={school.id}>{school.name}</option>
                          ))}
                        </select>
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left">
                      <div className="space-y-1">
                        <span className="text-xs font-medium text-blue-800">Turma:</span>
                        <select
                          value={batchClassId}
                          onChange={(e) => setBatchClassId(e.target.value)}
                          disabled={!batchSchoolId}
                          className="w-full px-2 py-1 text-xs border border-blue-300 rounded focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
                        >
                          <option value="">Manter atual</option>
                          {batchClassOptions.map(classItem => (
                            <option key={classItem.id} value={classItem.id}>{classItem.name}</option>
                          ))}
                        </select>
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left">
                      <div className="space-y-1">
                        <span className="text-xs font-medium text-blue-800">Status:</span>
                        <select
                          value={batchStatus}
                          onChange={(e) => setBatchStatus(e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-blue-300 rounded focus:ring-blue-500 focus:border-blue-500"
                        >
                          <option value="">Manter atual</option>
                          <option value="active">Ativo</option>
                          <option value="inactive">Inativo</option>
                          <option value="dropout">Desistente</option>
                          <option value="transferred">Transferido</option>
                          <option value="deceased">Falecido</option>
                        </select>
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left">
                      <button
                        onClick={handleSaveBatchActions}
                        disabled={savingBatch || selectedStudentIds.length === 0}
                        className="px-4 py-2 bg-green-600 text-white text-xs font-medium rounded hover:bg-green-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-1"
                      >
                        {savingBatch ? (
                          <>
                            <RefreshCw size={14} className="animate-spin" />
                            Salvando...
                          </>
                        ) : (
                          <>
                            <CheckCircle size={14} />
                            Salvar
                          </>
                        )}
                      </button>
                    </th>
                    <th className="px-4 py-3">
                      {/* Coluna Ações */}
                    </th>
                  </tr>
                </thead>
              )}
              
              {/* Cabeçalho normal da tabela */}
              <thead className="bg-gray-50">
                <tr>
                  {batchMode && (
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      
                    </th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Nome</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Escola</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Turma</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Documentos</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Ações</th>
                </tr>
              </thead>
              
              <tbody className="bg-white divide-y divide-gray-200">
                {loading ? (
                  <tr>
                    <td colSpan={batchMode ? 7 : 6} className="px-4 py-8 text-center">
                      <div className="flex items-center justify-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        <span className="ml-2 text-gray-500">Carregando...</span>
                      </div>
                    </td>
                  </tr>
                ) : displayedStudents.length === 0 ? (
                  <tr>
                    <td colSpan={batchMode ? 7 : 6} className="px-4 py-8 text-center text-gray-500">
                      Nenhum aluno encontrado
                    </td>
                  </tr>
                ) : (
                  paginatedStudents.map((row) => {
                    const canEditThisStudent = canEditStudent(row);
                    const canGenerateDocuments = isAdmin || isSemed || 
                      (isSecretario && userSchoolIds.includes(row.school_id)) ||
                      (!isSecretario && !isSemed);
                    
                    return (
                      <tr key={row.id} className={`hover:bg-gray-50 ${selectedStudentIds.includes(row.id) ? 'bg-blue-50' : ''}`}>
                        {batchMode && (
                          <td className="px-4 py-3">
                            <input
                              type="checkbox"
                              checked={selectedStudentIds.includes(row.id)}
                              onChange={(e) => handleSelectStudent_Batch(row.id, e.target.checked)}
                              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            />
                          </td>
                        )}
                        <td className="px-4 py-3 text-sm text-gray-900">{row.full_name}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">{getSchoolName(row.school_id)}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">{getClassName(row.class_id)}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            row.status === 'active' ? 'bg-green-100 text-green-800' :
                            row.status === 'inactive' ? 'bg-gray-100 text-gray-800' :
                            row.status === 'dropout' ? 'bg-red-100 text-red-800' :
                            (row.status === 'transferred' || row.status === 'Transferido') ? 'bg-orange-100 text-orange-800' :
                            row.status === 'deceased' ? 'bg-purple-100 text-purple-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {row.status === 'active' ? 'Ativo' :
                             row.status === 'inactive' ? 'Inativo' :
                             row.status === 'dropout' ? 'Desistente' :
                             (row.status === 'transferred' || row.status === 'Transferido') ? 'Transferido' :
                             row.status === 'deceased' ? 'Falecido' :
                             row.status || '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {canGenerateDocuments && (
                            <button
                              onClick={() => {
                                setDocumentStudent(row);
                                setShowDocumentsModal(true);
                              }}
                              className="text-blue-600 hover:text-blue-800 text-sm flex items-center gap-1"
                            >
                              <FileText size={16} />
                              Documentos
                            </button>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleView(row)}
                              className="text-gray-600 hover:text-gray-800"
                              title="Visualizar"
                            >
                              <Search size={16} />
                            </button>
                            {canEdit && canEditThisStudent && (
                              <button
                                onClick={() => handleEdit(row)}
                                className="text-blue-600 hover:text-blue-800"
                                title="Editar"
                              >
                                <FileText size={16} />
                              </button>
                            )}
                            {canDelete && (
                              <button
                                onClick={() => handleDelete(row.id)}
                                className="text-red-600 hover:text-red-800"
                                title="Excluir"
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          
          {/* Paginação */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-t">
              <div className="text-sm text-gray-600">
                Mostrando {((currentPage - 1) * itemsPerPage) + 1} a {Math.min(currentPage * itemsPerPage, displayedStudents.length)} de {displayedStudents.length} registros
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Primeira
                </button>
                <button
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                  className="p-1 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={18} />
                </button>
                <span className="px-3 py-1 text-sm">
                  Página <strong>{currentPage}</strong> de <strong>{totalPages}</strong>
                </span>
                <button
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronRight size={18} />
                </button>
                <button
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Última
                </button>
              </div>
            </div>
          )}
        </div>

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={
            viewMode 
              ? `Visualizar Aluno(a)${editingStudent ? `: ${editingStudent.full_name}` : ''}` 
              : (editingStudent 
                  ? `Editar Aluno(a): ${editingStudent.full_name}` 
                  : 'Novo(a) Aluno(a)')
          }
          size="xl"
        >
          <form onSubmit={handleSubmit}>
            <Tabs tabs={tabs} />
            
            <div className="flex justify-end space-x-3 pt-4 border-t mt-6">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {viewMode ? 'Fechar' : 'Cancelar'}
              </button>
              {!viewMode && (
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                >
                  {submitting ? 'Salvando...' : 'Salvar'}
                </button>
              )}
            </div>
          </form>
        </Modal>
        
        {/* Modal de Documentos */}
        <DocumentGeneratorModal
          isOpen={showDocumentsModal}
          onClose={() => {
            setShowDocumentsModal(false);
            setDocumentStudent(null);
          }}
          student={documentStudent}
          academicYear="2025"
          classInfo={classes.find(c => c.id === filterClassId) || null}
        />
        
        {/* Modal de Impressão em Lote */}
        <Modal
          isOpen={showBatchPrintModal}
          onClose={() => setShowBatchPrintModal(false)}
          title={`Impressão em Lote - ${getClassName(filterClassId)}`}
          size="md"
        >
          <div className="space-y-4">
            <p className="text-gray-600">
              Selecione o tipo de documento para gerar para todos os <strong>{displayedStudents.length} alunos</strong> da turma:
            </p>
            
            <div className="space-y-3">
              {/* Boletim */}
              <button
                onClick={() => handleBatchPrint('boletim')}
                disabled={batchPrinting}
                className="w-full flex items-center justify-between p-4 border-2 border-blue-200 rounded-lg hover:bg-blue-50 hover:border-blue-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                    <FileText className="text-blue-600" size={20} />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-gray-900">Boletim Escolar</p>
                    <p className="text-sm text-gray-500">Notas e frequência do aluno</p>
                  </div>
                </div>
                <ExternalLink size={20} className="text-blue-600" />
              </button>
              
              {/* Ficha Individual */}
              <button
                onClick={() => handleBatchPrint('ficha_individual')}
                disabled={batchPrinting}
                className="w-full flex items-center justify-between p-4 border-2 border-green-200 rounded-lg hover:bg-green-50 hover:border-green-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                    <User className="text-green-600" size={20} />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-gray-900">Ficha Individual</p>
                    <p className="text-sm text-gray-500">Notas, frequência e dados completos</p>
                  </div>
                </div>
                <ExternalLink size={20} className="text-green-600" />
              </button>
              
              {/* Certificado - Apenas para 9º Ano e EJA 4ª Etapa */}
              {isClassEligibleForCertificate && (
                <button
                  onClick={() => handleBatchPrint('certificado')}
                  disabled={batchPrinting}
                  className="w-full flex items-center justify-between p-4 border-2 border-purple-200 rounded-lg hover:bg-purple-50 hover:border-purple-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                      <FileText className="text-purple-600" size={20} />
                    </div>
                    <div className="text-left">
                      <p className="font-medium text-gray-900">Certificado</p>
                      <p className="text-sm text-gray-500">Certificado de conclusão (9º Ano / EJA 4ª Etapa)</p>
                    </div>
                  </div>
                  <ExternalLink size={20} className="text-purple-600" />
                </button>
              )}
            </div>
            
            {batchPrinting && (
              <div className="flex items-center justify-center gap-3 p-4 bg-blue-50 rounded-lg">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>
                <span className="text-blue-600">Gerando documentos...</span>
              </div>
            )}
            
            <div className="flex justify-end pt-4 border-t">
              <button
                onClick={() => setShowBatchPrintModal(false)}
                disabled={batchPrinting}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Fechar
              </button>
            </div>
          </div>
        </Modal>

        {/* Modal de Registro de Atestado Médico */}
        <Modal 
          isOpen={showCertificateModal} 
          onClose={() => setShowCertificateModal(false)} 
          title="Registrar Atestado Médico"
          size="md"
        >
          <div className="space-y-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-800">
                <strong>⚠️ Atenção:</strong> O atestado médico bloqueará o lançamento de frequência pelo professor nos dias cobertos. 
                O período aparecerá como "AM" (Atestado Médico) na lista de presença.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Data Inicial <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  value={certificateForm.start_date}
                  onChange={(e) => setCertificateForm(prev => ({ ...prev, start_date: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Data Final <span className="text-red-500">*</span>
                </label>
                <input
                  type="date"
                  value={certificateForm.end_date}
                  onChange={(e) => setCertificateForm(prev => ({ ...prev, end_date: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Motivo</label>
              <select
                value={certificateForm.reason}
                onChange={(e) => setCertificateForm(prev => ({ ...prev, reason: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500"
              >
                <option value="Atestado Médico">Atestado Médico</option>
                <option value="Atestado Médico - Consulta">Atestado Médico - Consulta</option>
                <option value="Atestado Médico - Cirurgia">Atestado Médico - Cirurgia</option>
                <option value="Atestado Médico - Internação">Atestado Médico - Internação</option>
                <option value="Atestado Médico - Tratamento">Atestado Médico - Tratamento</option>
                <option value="Atestado Odontológico">Atestado Odontológico</option>
                <option value="Licença Maternidade">Licença Maternidade</option>
                <option value="Outro">Outro</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Observações</label>
              <textarea
                value={certificateForm.notes}
                onChange={(e) => setCertificateForm(prev => ({ ...prev, notes: e.target.value }))}
                placeholder="Informações adicionais sobre o atestado..."
                rows={2}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Documento Digitalizado</label>
              {certificateForm.document_url ? (
                <div className="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg">
                  <FileText className="text-green-600" size={20} />
                  <span className="text-sm text-green-800">Documento anexado</span>
                  <button
                    type="button"
                    onClick={() => setCertificateForm(prev => ({ ...prev, document_url: '' }))}
                    className="ml-auto text-red-600 hover:bg-red-100 p-1 rounded"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ) : (
                <label className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 cursor-pointer transition-colors border border-gray-300">
                  <Upload size={18} />
                  <span>Anexar Atestado (PDF/Imagem)</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files[0];
                      if (file) {
                        try {
                          const result = await uploadAPI.upload(file, 'atestado');
                          setCertificateForm(prev => ({ ...prev, document_url: result.url }));
                          showAlert('success', 'Documento anexado');
                        } catch (error) {
                          showAlert('error', 'Erro ao anexar documento');
                        }
                      }
                    }}
                  />
                </label>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t">
              <button
                type="button"
                onClick={() => setShowCertificateModal(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSaveCertificate}
                disabled={savingCertificate || !certificateForm.start_date || !certificateForm.end_date}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {savingCertificate ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                    Salvando...
                  </>
                ) : (
                  <>
                    <Stethoscope size={18} />
                    Registrar Atestado
                  </>
                )}
              </button>
            </div>
          </div>
        </Modal>

        {/* Modal de Ação de Vínculo (Matricular, Transferir, Remanejar, Progredir) */}
        <Modal 
          isOpen={showActionModal} 
          onClose={() => setShowActionModal(false)} 
          title={
            selectedAction === 'matricular' ? '📋 Matricular Aluno' :
            selectedAction === 'transferir' ? '🔄 Transferir Aluno' :
            selectedAction === 'remanejar' ? '↔️ Remanejar Aluno' :
            selectedAction === 'progredir' ? '⬆️ Progredir Aluno' :
            'Ação do Aluno'
          }
          size="md"
        >
          <div className="space-y-4">
            {/* Info do Aluno */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
              <p className="text-sm text-gray-700">
                <strong>Aluno:</strong> {editingStudent?.full_name}
              </p>
              <p className="text-sm text-gray-500">
                <strong>Status atual:</strong>{' '}
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  editingStudent?.status === 'active' || editingStudent?.status === 'ativo' 
                    ? 'bg-green-100 text-green-700' 
                    : editingStudent?.status === 'transferred' || editingStudent?.status === 'transferido'
                    ? 'bg-orange-100 text-orange-700'
                    : 'bg-gray-100 text-gray-700'
                }`}>
                  {editingStudent?.status === 'active' ? 'Ativo' : 
                   editingStudent?.status === 'transferred' ? 'Transferido' :
                   editingStudent?.status === 'dropout' ? 'Desistente' :
                   editingStudent?.status || 'N/A'}
                </span>
              </p>
            </div>

            {/* Campos específicos por ação */}
            
            {/* MATRICULAR - Seleciona escola e turma */}
            {selectedAction === 'matricular' && (
              <div className="space-y-4">
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                  <p className="text-sm text-green-800">
                    <strong>ℹ️ Matricular:</strong> O aluno será reativado e matriculado na escola/turma selecionada.
                  </p>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Ano Letivo <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={actionData.academicYear}
                      onChange={(e) => setActionData(prev => ({ ...prev, academicYear: parseInt(e.target.value) }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                    >
                      <option value={2025}>2025</option>
                      <option value={2026}>2026</option>
                      <option value={2027}>2027</option>
                      <option value={2028}>2028</option>
                      <option value={2029}>2029</option>
                      <option value={2030}>2030</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Escola de Destino <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={actionData.targetSchoolId}
                      onChange={(e) => setActionData(prev => ({ 
                        ...prev, 
                        targetSchoolId: e.target.value,
                        targetClassId: '' // Limpa turma ao mudar escola
                      }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                    >
                      <option value="">Selecione a escola...</option>
                      {schools.map(school => (
                        <option key={school.id} value={school.id}>{school.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Turma de Destino <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={actionData.targetClassId}
                    onChange={(e) => setActionData(prev => ({ 
                      ...prev, 
                      targetClassId: e.target.value,
                      studentSeries: '' // Limpa série ao mudar turma
                    }))}
                    disabled={!actionData.targetSchoolId}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
                  >
                    <option value="">
                      {actionData.targetSchoolId ? 'Selecione a turma...' : 'Selecione a escola primeiro'}
                    </option>
                    {actionTargetClasses.map(cls => (
                      <option key={cls.id} value={cls.id}>
                        {cls.name}
                        {cls.is_multi_grade && ' (Multisseriada)'}
                      </option>
                    ))}
                  </select>
                </div>
                
                {/* Seleção de Série para Turmas Multisseriadas */}
                {(() => {
                  const selectedClass = classes.find(c => c.id === actionData.targetClassId);
                  if (selectedClass?.is_multi_grade && selectedClass?.series?.length > 0) {
                    return (
                      <div className="mt-3">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Série do Aluno <span className="text-red-500">*</span>
                          <span className="text-xs text-indigo-600 font-normal ml-2">
                            (turma multisseriada)
                          </span>
                        </label>
                        <select
                          value={actionData.studentSeries}
                          onChange={(e) => setActionData(prev => ({ ...prev, studentSeries: e.target.value }))}
                          className="w-full px-3 py-2 border border-indigo-300 rounded-lg focus:ring-2 focus:ring-indigo-500 bg-indigo-50"
                        >
                          <option value="">Selecione a série do aluno...</option>
                          {selectedClass.series.map(serie => (
                            <option key={serie} value={serie}>{serie}</option>
                          ))}
                        </select>
                        <p className="text-xs text-indigo-600 mt-1">
                          Esta turma atende às séries: {selectedClass.series.join(', ')}
                        </p>
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>
            )}

            {/* TRANSFERIR - Motivo da transferência */}
            {selectedAction === 'transferir' && (
              <div className="space-y-4">
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                  <p className="text-sm text-orange-800">
                    <strong>⚠️ Transferir:</strong> O aluno será marcado como "Transferido" e não aparecerá mais nas listas de alunos ativos.
                  </p>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Motivo da Transferência
                  </label>
                  <select
                    value={actionData.reason}
                    onChange={(e) => setActionData(prev => ({ ...prev, reason: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500"
                  >
                    <option value="">Selecione o motivo...</option>
                    <option value="Mudança de cidade">Mudança de cidade</option>
                    <option value="Mudança de bairro">Mudança de bairro</option>
                    <option value="Transferência para escola particular">Transferência para escola particular</option>
                    <option value="Transferência para outra rede">Transferência para outra rede (estadual/federal)</option>
                    <option value="Solicitação da família">Solicitação da família</option>
                    <option value="Outro motivo">Outro motivo</option>
                  </select>
                </div>
              </div>
            )}

            {/* REMANEJAR - Seleciona turma na mesma escola */}
            {selectedAction === 'remanejar' && (
              <div className="space-y-4">
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-sm text-blue-800">
                    <strong>ℹ️ Remanejar:</strong> O aluno será movido para outra turma na mesma escola.
                  </p>
                </div>
                
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Turma atual:</span>
                    <p className="font-medium">{classes.find(c => c.id === formData.class_id)?.name || 'N/A'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Escola:</span>
                    <p className="font-medium">{schools.find(s => s.id === formData.school_id)?.name || 'N/A'}</p>
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Nova Turma <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={actionData.targetClassId}
                    onChange={(e) => setActionData(prev => ({ ...prev, targetClassId: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Selecione a nova turma...</option>
                    {classes
                      .filter(c => c.school_id === formData.school_id && c.id !== formData.class_id)
                      .map(cls => (
                        <option key={cls.id} value={cls.id}>{cls.name}</option>
                      ))
                    }
                  </select>
                </div>
              </div>
            )}

            {/* PROGREDIR - Com ou sem histórico */}
            {selectedAction === 'progredir' && (
              <div className="space-y-4">
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                  <p className="text-sm text-purple-800">
                    <strong>ℹ️ Progredir:</strong> O aluno avançará para a próxima série/turma ou será concluído com emissão de histórico.
                  </p>
                </div>
                
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="emitirHistorico"
                    checked={actionData.emitirHistorico}
                    onChange={(e) => setActionData(prev => ({ 
                      ...prev, 
                      emitirHistorico: e.target.checked,
                      targetClassId: e.target.checked ? '' : prev.targetClassId
                    }))}
                    className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                  />
                  <label htmlFor="emitirHistorico" className="text-sm font-medium text-gray-700">
                    Emitir Histórico Escolar (conclusão do ciclo)
                  </label>
                </div>
                
                {actionData.emitirHistorico ? (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                    <p className="text-sm text-yellow-800">
                      <strong>📄 Conclusão:</strong> O aluno será marcado como "Transferido" (concluído) e o histórico escolar deverá ser gerado manualmente.
                    </p>
                  </div>
                ) : (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Nova Turma (próxima série) <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={actionData.targetClassId}
                      onChange={(e) => setActionData(prev => ({ ...prev, targetClassId: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500"
                    >
                      <option value="">Selecione a próxima turma...</option>
                      {classes
                        .filter(c => c.school_id === formData.school_id && c.id !== formData.class_id)
                        .map(cls => (
                          <option key={cls.id} value={cls.id}>{cls.name}</option>
                        ))
                      }
                    </select>
                  </div>
                )}
              </div>
            )}

            {/* Observações (comum a todas as ações) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Observações
              </label>
              <textarea
                value={actionData.notes}
                onChange={(e) => setActionData(prev => ({ ...prev, notes: e.target.value }))}
                rows={2}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Anotações adicionais sobre esta ação..."
              />
            </div>

            {/* Botões de Ação */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <button
                type="button"
                onClick={() => setShowActionModal(false)}
                disabled={executingAction}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={executeVinculoAction}
                disabled={executingAction || (() => {
                  if (selectedAction === 'matricular') {
                    if (!actionData.targetSchoolId || !actionData.targetClassId) return true;
                    // Verifica se é turma multisseriada e se a série foi selecionada
                    const targetClass = classes.find(c => c.id === actionData.targetClassId);
                    if (targetClass?.is_multi_grade && targetClass?.series?.length > 0 && !actionData.studentSeries) {
                      return true;
                    }
                    return false;
                  }
                  if (selectedAction === 'remanejar' && !actionData.targetClassId) return true;
                  if (selectedAction === 'progredir' && !actionData.emitirHistorico && !actionData.targetClassId) return true;
                  return false;
                })()}
                className={`px-4 py-2 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 ${
                  selectedAction === 'matricular' ? 'bg-green-600 hover:bg-green-700' :
                  selectedAction === 'transferir' ? 'bg-orange-600 hover:bg-orange-700' :
                  selectedAction === 'remanejar' ? 'bg-blue-600 hover:bg-blue-700' :
                  selectedAction === 'progredir' ? 'bg-purple-600 hover:bg-purple-700' :
                  'bg-gray-600 hover:bg-gray-700'
                }`}
              >
                {executingAction ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                    Processando...
                  </>
                ) : (
                  <>
                    {selectedAction === 'matricular' && '📋 Confirmar Matrícula'}
                    {selectedAction === 'transferir' && '🔄 Confirmar Transferência'}
                    {selectedAction === 'remanejar' && '↔️ Confirmar Remanejamento'}
                    {selectedAction === 'progredir' && '⬆️ Confirmar Progressão'}
                  </>
                )}
              </button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
}
