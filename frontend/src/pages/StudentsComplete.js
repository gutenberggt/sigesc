import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { studentsAPI, schoolsAPI, classesAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, AlertCircle, CheckCircle, ArrowLeft, User, Trash2 } from 'lucide-react';

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

export function StudentsComplete() {
  const navigate = useNavigate();
  const { user } = useAuth();
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
  
  // SEMED pode visualizar tudo, mas não pode editar/excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role !== 'semed';

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [studentsData, schoolsData, classesData] = await Promise.all([
          studentsAPI.getAll(),
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        setStudents(studentsData);
        setSchools(schoolsData);
        setClasses(classesData);
      } catch (error) {
        setAlert({ type: 'error', message: 'Erro ao carregar dados' });
        setTimeout(() => setAlert(null), 5000);
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [reloadTrigger]);

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

  const handleView = (student) => {
    setEditingStudent(student);
    setViewMode(true);
    setFormData({ ...initialFormData, ...student });
    setIsModalOpen(true);
  };

  const handleEdit = (student) => {
    setEditingStudent(student);
    setViewMode(false);
    setFormData({ ...initialFormData, ...student });
    setIsModalOpen(true);
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

    try {
      if (editingStudent) {
        await studentsAPI.update(editingStudent.id, formData);
        showAlert('success', 'Aluno atualizado com sucesso');
      } else {
        await studentsAPI.create(formData);
        showAlert('success', 'Aluno cadastrado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar aluno');
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
    return classItem ? `${classItem.name} - ${classItem.grade_level}` : '-';
  };

  const filteredClasses = classes.filter(c => c.school_id === formData.school_id);

  const columns = [
    { header: 'Matrícula', accessor: 'enrollment_number' },
    { header: 'Nome', accessor: 'full_name', render: (row) => row.full_name || '-' },
    { header: 'Escola', accessor: 'school_id', render: (row) => getSchoolName(row.school_id) },
    { header: 'Turma', accessor: 'class_id', render: (row) => getClassName(row.class_id) },
    { 
      header: 'Status', 
      accessor: 'status',
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
          row.status === 'active' ? 'bg-green-100 text-green-800' :
          row.status === 'transferred' ? 'bg-yellow-100 text-yellow-800' :
          'bg-red-100 text-red-800'
        }`}>
          {row.status === 'active' ? 'Ativo' : row.status === 'transferred' ? 'Transferido' : 'Inativo'}
        </span>
      )
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
            onChange={(e) => updateFormData('enrollment_number', e.target.value)}
            required
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="Ex: 20240001"
          />
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
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
          <label className="block text-sm font-medium text-gray-700 mb-1">Parentesco</label>
          <select
            value={formData.guardian_relationship}
            onChange={(e) => updateFormData('guardian_relationship', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            <option value="pai">Pai</option>
            <option value="mae">Mãe</option>
            <option value="avo">Avô/Avó</option>
            <option value="tio">Tio/Tia</option>
            <option value="irmao">Irmão/Irmã</option>
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
            value={formData.guardian_phone}
            onChange={(e) => updateFormData('guardian_phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
      </div>

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
          <strong>ℹ️ Formatos aceitos:</strong> JPG, PNG, PDF, GIF (máx. 2MB por arquivo)
        </p>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Foto do Aluno</h3>
      <div className="flex items-center gap-4">
        {formData.photo_url ? (
          <div className="relative">
            <img 
              src={formData.photo_url} 
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
            <label className="block text-sm font-medium text-gray-700 mb-1">URL da Foto</label>
            <input
              type="url"
              value={formData.photo_url}
              onChange={(e) => updateFormData('photo_url', e.target.value)}
              className="w-64 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="https://..."
            />
            <p className="text-xs text-gray-500 mt-1">Cole a URL de uma imagem hospedada</p>
          </div>
        )}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Laudo Médico</h3>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">URL do Laudo</label>
        <input
          type="url"
          value={formData.medical_report_url}
          onChange={(e) => updateFormData('medical_report_url', e.target.value)}
          disabled={viewMode}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          placeholder="https://..."
        />
        {formData.medical_report_url && (
          <a 
            href={formData.medical_report_url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-blue-600 text-sm hover:underline mt-1 inline-block"
          >
            Visualizar laudo
          </a>
        )}
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Documentos Gerais</h3>
      <p className="text-sm text-gray-500 mb-2">URLs de documentos digitalizados (certidões, comprovantes, etc.)</p>
      {/* Simplified document list */}
      <div className="space-y-2">
        {formData.documents_urls.map((url, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => {
                const newUrls = [...formData.documents_urls];
                newUrls[index] = e.target.value;
                updateFormData('documents_urls', newUrls);
              }}
              disabled={viewMode}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
            {!viewMode && (
              <button
                type="button"
                onClick={() => {
                  const newUrls = formData.documents_urls.filter((_, i) => i !== index);
                  updateFormData('documents_urls', newUrls);
                }}
                className="p-2 text-red-600 hover:bg-red-100 rounded-lg"
              >
                <Trash2 size={18} />
              </button>
            )}
          </div>
        ))}
        {!viewMode && (
          <button
            type="button"
            onClick={() => updateFormData('documents_urls', [...formData.documents_urls, ''])}
            className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm"
          >
            <Plus size={16} /> Adicionar documento
          </button>
        )}
      </div>
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
                {classItem.name} - {classItem.grade_level} ({classItem.shift === 'morning' ? 'Manhã' : classItem.shift === 'afternoon' ? 'Tarde' : classItem.shift === 'evening' ? 'Noite' : 'Integral'})
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
            <option value="transferred">Transferido</option>
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
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={20} />
          <span>Voltar ao Dashboard</span>
        </button>

        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Alunos</h1>
            <p className="text-gray-600 mt-1">Gerencie o cadastro completo de alunos</p>
          </div>
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

        <DataTable
          columns={columns}
          data={students}
          loading={loading}
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
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
      </div>
    </Layout>
  );
}
