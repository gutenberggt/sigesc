import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { studentsAPI, schoolsAPI, classesAPI, uploadAPI, documentsAPI, medicalCertificatesAPI } from '@/services/api';
import { formatPhone, formatCEP } from '@/utils/formatters';
import { extractErrorMessage } from '@/utils/errorHandler';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { useOffline } from '@/contexts/OfflineContext';
import { offlineStudentsService } from '@/services/offlineStudentsService';
import { Plus, AlertCircle, CheckCircle, Home, User, Trash2, Upload, FileText, Image, Search, X, Printer, Building2, Users, ExternalLink, Calendar, CloudOff, Cloud, RefreshCw, Stethoscope } from 'lucide-react';
import { DocumentGeneratorModal } from '@/components/documents';

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
  birth_date: '',
  sex: '',
  nationality: 'Brasileira',
  birth_city: '',
  birth_state: '',
  color_race: '',
  
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
  mother_name: '',
  mother_cpf: '',
  mother_rg: '',
  mother_phone: '',
  legal_guardian_type: '',  // 'mother', 'father', 'both', 'other'
  guardian_name: '',
  guardian_cpf: '',
  guardian_rg: '',
  guardian_phone: '',
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
  }
  
  // Educação Infantil - Creche (faixas específicas conforme MEC)
  // Berçário: 4 meses até 1 ano e 11 meses
  if (ageAtCutoff < 0) return 'Idade insuficiente';
  if (ageAtCutoff === 0) return 'Berçário';
  if (ageAtCutoff === 1) return 'Berçário';
  
  // Maternal I: a partir de 2 anos (completos até 31/03)
  if (ageAtCutoff === 2) return 'Maternal I';
  
  // Maternal II: a partir de 3 anos (completos até 31/03)
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
  const { isOnline, pendingSyncCount, triggerSync } = useOffline();
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
  
  // Filtros por Escola e Turma
  const [filterSchoolId, setFilterSchoolId] = useState('');
  const [filterClassId, setFilterClassId] = useState('');
  const [showBatchPrintModal, setShowBatchPrintModal] = useState(false);
  
  // Histórico do aluno
  const [studentHistory, setStudentHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [batchPrinting, setBatchPrinting] = useState(false);
  const nameInputRef = useRef(null);
  const cpfInputRef = useRef(null);
  
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
  
  // Permissões de edição/exclusão de alunos:
  // - Admin: pode editar/excluir qualquer aluno
  // - Secretário: pode editar apenas alunos ATIVOS da(s) escola(s) onde tem vínculo
  // - SEMED: apenas visualização (não pode editar/excluir)
  // - Coordenador: apenas visualização de alunos (não pode editar/excluir)
  
  const isAdmin = user?.role === 'admin';
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
  const canRegisterCertificates = user?.role === 'admin' || user?.role === 'secretario';
  // Permissão para excluir atestados (apenas admin)
  const canDeleteCertificates = user?.role === 'admin';
  
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

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
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
    
    // Carrega histórico do aluno
    loadStudentHistory(student.id);
  };

  const handleEdit = async (student) => {
    setEditingStudent(student);
    setViewMode(false);
    setFormData({ ...initialFormData, ...student });
    setIsModalOpen(true);
    
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validação: pelo menos um documento
    if (!formData.cpf && !formData.nis && !formData.civil_certificate_number) {
      if (!formData.no_documents_justification) {
        showAlert('error', 'Informe pelo menos um documento (CPF, NIS ou Certidão) ou justifique a ausência.');
        return;
      }
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

  const filteredClasses = classes.filter(c => c.school_id === formData.school_id);
  
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
    
    return result;
  })();

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
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Escola *</label>
          <select
            value={formData.school_id}
            onChange={(e) => updateFormData('school_id', e.target.value)}
            required
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            {schools.map(school => (
              <option key={school.id} value={school.id}>{school.name}</option>
            ))}
          </select>
        </div>
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
          <label className="block text-sm font-medium text-gray-700 mb-1">Naturalidade (Cidade)</label>
          <input
            type="text"
            value={formData.birth_city}
            onChange={(e) => updateFormData('birth_city', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
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
            value={formData.cpf}
            onChange={(e) => updateFormData('cpf', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="000.000.000-00"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">NIS (PIS/PASEP)</label>
          <input
            type="text"
            value={formData.nis}
            onChange={(e) => updateFormData('nis', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número SUS</label>
          <input
            type="text"
            value={formData.sus_number}
            onChange={(e) => updateFormData('sus_number', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="000 0000 0000 0000"
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
          <input
            type="text"
            value={formData.civil_certificate_city}
            onChange={(e) => updateFormData('civil_certificate_city', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
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
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
            value={formData.father_cpf}
            onChange={(e) => updateFormData('father_cpf', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
          <input
            type="text"
            value={formData.father_phone}
            onChange={(e) => updateFormData('father_phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Mãe</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
            value={formData.mother_cpf}
            onChange={(e) => updateFormData('mother_cpf', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
          <input
            type="text"
            value={formData.mother_phone}
            onChange={(e) => updateFormData('mother_phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
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
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
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
              value={formData.guardian_cpf}
              onChange={(e) => updateFormData('guardian_cpf', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">RG</label>
            <input
              type="text"
              value={formData.guardian_rg}
              onChange={(e) => updateFormData('guardian_rg', e.target.value)}
              disabled={viewMode}
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
          <select
            value={formData.class_id}
            onChange={(e) => updateFormData('class_id', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione uma turma</option>
            {filteredClasses.map(classItem => (
              <option key={classItem.id} value={classItem.id}>
                {classItem.name}
              </option>
            ))}
          </select>
          {filteredClasses.length === 0 && formData.school_id && (
            <p className="text-sm text-yellow-600 mt-1">Nenhuma turma cadastrada para esta escola</p>
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
                      item.action_type === 'mudanca_status' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {item.action_type === 'matricula' ? 'Matrícula' :
                       item.action_type === 'remanejamento' ? 'Remanejamento' :
                       item.action_type === 'transferencia_saida' ? 'Transf. Saída' :
                       item.action_type === 'transferencia_entrada' ? 'Transf. Entrada' :
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
                Alunos
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
                Gerencie o cadastro completo de alunos
                {pendingSyncCount > 0 && (
                  <span className="ml-2 text-amber-600">
                    ({pendingSyncCount} alteração(ões) pendente(s) de sincronização)
                  </span>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pendingSyncCount > 0 && isOnline && (
              <button
                onClick={triggerSync}
                className="bg-amber-500 text-white px-3 py-2 rounded-lg hover:bg-amber-600 transition-colors flex items-center space-x-2"
                title="Sincronizar alterações pendentes"
              >
                <RefreshCw size={18} />
                <span>Sincronizar</span>
              </button>
            )}
            {canEdit && (
              <button
                onClick={handleCreate}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
              >
                <Plus size={20} />
                <span>Novo Aluno</span>
              </button>
            )}
          </div>
        </div>

        {alert && (
          <div className={`p-4 rounded-lg flex items-start ${
            alert.type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
          }`}>
            {alert.type === 'success' ? (
              <CheckCircle className="text-green-600 mr-2 flex-shrink-0" size={20} />
            ) : (
              <AlertCircle className="text-red-600 mr-2 flex-shrink-0" size={20} />
            )}
            <p className={`text-sm ${alert.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
              {alert.message}
            </p>
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
          
          {/* Indicador de filtro por escola/turma */}
          {!selectedStudent && (filterSchoolId || filterClassId) && (
            <div className="mt-3 flex items-center gap-2 text-sm text-green-600 bg-green-50 px-3 py-2 rounded-lg">
              <span>Filtro ativo:</span>
              {filterSchoolId && <strong>{getSchoolName(filterSchoolId)}</strong>}
              {filterClassId && (
                <>
                  <span className="text-gray-400">→</span>
                  <strong>{getClassName(filterClassId)}</strong>
                </>
              )}
              <span className="text-gray-400">|</span>
              <span>{displayedStudents.length} aluno(s)</span>
            </div>
          )}
        </div>

        <DataTable
          columns={columns}
          data={displayedStudents}
          loading={loading}
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
          canEditRow={canEditStudent}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={viewMode ? 'Visualizar Aluno' : (editingStudent ? 'Editar Aluno' : 'Novo Aluno')}
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
      </div>
    </Layout>
  );
}
