import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { schoolsAPI, classesAPI, schoolAssignmentAPI, staffAPI, uploadAPI, calendarAPI } from '@/services/api';
import { formatPhone, formatCEP } from '@/utils/formatters';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { Plus, AlertCircle, CheckCircle, Home, Users, Phone, Clock } from 'lucide-react';

export function SchoolsComplete() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { getDefaultLocation } = useMantenedora();
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchool, setEditingSchool] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const [schoolStaff, setSchoolStaff] = useState([]);
  const [loadingStaff, setLoadingStaff] = useState(false);
  const [calendarioLetivo, setCalendarioLetivo] = useState(null);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [novoAnoLetivo, setNovoAnoLetivo] = useState('');

  // Permissões baseadas no papel do usuário
  // Admin: pode tudo
  // Secretário: pode visualizar e editar escolas onde tem vínculo, mas não criar/excluir
  // SEMED: pode visualizar tudo, mas não pode editar/excluir
  const isAdmin = user?.role === 'admin';
  const isSecretario = user?.role === 'secretario';
  const isSemed = user?.role === 'semed';
  
  const canEdit = isAdmin || isSecretario; // Admin e secretário podem editar
  const canDelete = isAdmin; // Só admin pode excluir escolas
  const canCreate = isAdmin; // Só admin pode criar escolas
  
  // IDs das escolas que o usuário tem vínculo (para secretário) - usando useMemo para evitar recriação
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user?.school_ids, user?.school_links]);
  
  // Dados padrão da mantenedora
  const defaultLocation = getDefaultLocation();
  
  // Ano letivo atual
  const currentYear = new Date().getFullYear();
  
  // Anos disponíveis para seleção (2025 a 2030)
  const anosDisponiveis = [2025, 2026, 2027, 2028, 2029, 2030];

  // Estado do formulário com valores padrão
  const [formData, setFormData] = useState({
    // Dados Gerais - Identificação
    name: '',
    inep_code: '',
    tipo_unidade: 'sede', // 'sede' ou 'anexa'
    anexa_a: '', // ID da escola sede (quando for anexa)
    caracteristica_escolar: '',
    zona_localizacao: 'urbana',
    cnpj: '',
    situacao_funcionamento: 'Ativa',
    
    // Dados Gerais - Localização
    cep: '',
    logradouro: '',
    numero: '',
    complemento: '',
    bairro: '',
    municipio: defaultLocation.municipio,
    distrito: '',
    estado: defaultLocation.estado,
    ddd_telefone: '',
    telefone: '',
    celular: '',
    
    // Dados Gerais - Contatos
    email: '',
    site: '',
    
    // Dados Gerais - Georreferenciamento
    latitude: '',
    longitude: '',
    
    // Dados Gerais - Regras
    bloquear_lancamento_anos_encerrados: false,
    usar_regra_alternativa: false,
    
    // Dados Gerais - Vinculação
    dependencia_administrativa: 'Municipal',
    orgao_responsavel: '',
    regulamentacao: '',
    esfera_administrativa: '',
    
    // Dados Gerais - Equipe
    secretario_escolar: '',
    gestor_principal: '',
    cargo_gestor: '',
    
    // Dados Gerais - Oferta
    niveis_ensino_oferecidos: [],
    anos_letivos_ativos: [new Date().getFullYear()],
    
    // Infraestrutura
    abastecimento_agua: '',
    energia_eletrica: '',
    saneamento: '',
    coleta_lixo: '',
    possui_rampas: false,
    possui_corrimao: false,
    banheiros_adaptados: false,
    sinalizacao_tatil: false,
    saidas_emergencia: 0,
    extintores: 0,
    brigada_incendio: false,
    plano_evacuacao: false,
    possui_internet: false,
    tipo_conexao: '',
    cobertura_rede: '',
    estado_conservacao: '',
    possui_cercamento: false,
    
    // Dependências
    numero_salas_aula: 0,
    capacidade_total_alunos: 0,
    salas_recursos_multifuncionais: 0,
    sala_direcao: false,
    sala_secretaria: false,
    sala_coordenacao: false,
    sala_professores: false,
    numero_banheiros: 0,
    banheiros_acessiveis: 0,
    possui_cozinha: false,
    possui_refeitorio: false,
    possui_almoxarifado: false,
    possui_biblioteca: false,
    possui_lab_ciencias: false,
    possui_lab_informatica: false,
    possui_quadra: false,
    
    // Equipamentos
    qtd_computadores: 0,
    qtd_tablets: 0,
    qtd_projetores: 0,
    qtd_impressoras: 0,
    qtd_televisores: 0,
    qtd_projetores_multimidia: 0,
    qtd_aparelhos_som: 0,
    qtd_lousas_digitais: 0,
    possui_kits_cientificos: false,
    possui_instrumentos_musicais: false,
    qtd_extintores: 0,
    qtd_cameras: 0,
    
    // Recursos
    possui_material_didatico: false,
    tamanho_acervo: 0,
    participa_programas_governamentais: [],
    
    // Dados do Ensino
    educacao_infantil: false,
    fundamental_anos_iniciais: false,
    fundamental_anos_finais: false,
    ensino_medio: false,
    eja: false,
    eja_final: false,
    aee: false,
    atendimento_integral: false,
    reforco_escolar: false,
    aulas_complementares: false,
    turnos_funcionamento: [],
    organizacao_turmas: '',
    tipo_avaliacao: '',
    
    // Sub-níveis Educação Infantil
    educacao_infantil_bercario_i: false,
    educacao_infantil_bercario_ii: false,
    educacao_infantil_maternal_i: false,
    educacao_infantil_maternal_ii: false,
    educacao_infantil_pre_i: false,
    educacao_infantil_pre_ii: false,
    // Retrocompatibilidade
    educacao_infantil_bercario: false,
    
    // Sub-níveis Fundamental Inicial
    fundamental_inicial_1ano: false,
    fundamental_inicial_2ano: false,
    fundamental_inicial_3ano: false,
    fundamental_inicial_4ano: false,
    fundamental_inicial_5ano: false,
    
    // Sub-níveis Fundamental Final
    fundamental_final_6ano: false,
    fundamental_final_7ano: false,
    fundamental_final_8ano: false,
    fundamental_final_9ano: false,
    
    // Sub-níveis EJA
    eja_inicial_1etapa: false,
    eja_inicial_2etapa: false,
    eja_final_3etapa: false,
    eja_final_4etapa: false,
    
    // Espaços Escolares
    possui_quadra_esportiva: false,
    possui_patio: false,
    possui_parque: false,
    possui_brinquedoteca: false,
    possui_auditorio: false,
    possui_horta: false,
    possui_estacionamento: false,
    
    // Permissão - Data Limite de Lançamento por Bimestre (por ano)
    bimestre_1_limite_lancamento: '',
    bimestre_2_limite_lancamento: '',
    bimestre_3_limite_lancamento: '',
    bimestre_4_limite_lancamento: '',
    
    // Permissão - Pré-Matrícula Online
    pre_matricula_ativa: false,
    
    // Anos Letivos da escola e seus status
    // Formato: { 2025: { status: 'aberto' }, 2026: { status: 'aberto' }, ... }
    anos_letivos: {},
    
    status: 'active'
  });

  // Carrega dados quando o componente monta ou reloadTrigger muda
  useEffect(() => {
    let isMounted = true;
    
    const fetchData = async () => {
      try {
        setLoading(true);
        const [schoolsData, classesData, calendarioData] = await Promise.all([
          schoolsAPI.getAll(),
          classesAPI.getAll(),
          calendarAPI.getCalendarioLetivo(currentYear).catch(() => null)
        ]);
        if (isMounted) {
          // Filtrar escolas para secretário (apenas escolas vinculadas)
          let filteredSchools = schoolsData;
          
          // Debug: verificar school_ids do usuário
          console.log('[SchoolsComplete] user:', user);
          console.log('[SchoolsComplete] userSchoolIds:', userSchoolIds);
          console.log('[SchoolsComplete] isSecretario:', isSecretario);
          
          if (isSecretario) {
            if (userSchoolIds.length > 0) {
              filteredSchools = schoolsData.filter(school => 
                userSchoolIds.includes(school.id)
              );
            }
            // Se secretário não tem school_ids, mostra mensagem
            if (filteredSchools.length === 0) {
              console.log('[SchoolsComplete] Nenhuma escola encontrada para o secretário');
            }
          }
          setSchools(filteredSchools);
          setClasses(classesData);
          setCalendarioLetivo(calendarioData);
        }
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
        if (isMounted) {
          setAlert({ type: 'error', message: 'Erro ao carregar dados' });
          setTimeout(() => setAlert(null), 5000);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      isMounted = false;
    };
  }, [reloadTrigger, isSecretario, userSchoolIds]);

  // Função para recarregar os dados
  const reloadData = () => {
    setReloadTrigger(prev => prev + 1);
  };

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };

  const handleCreate = () => {
    setEditingSchool(null);
    setViewMode(false);
    setSchoolStaff([]); // Limpa lista de servidores
    // Reset form with default values (usando dados da mantenedora)
    setFormData({
      name: '',
      inep_code: '',
      tipo_unidade: 'sede',
      anexa_a: '',
      zona_localizacao: 'urbana',
      situacao_funcionamento: 'Ativa',
      dependencia_administrativa: 'Municipal',
      anos_letivos_ativos: [new Date().getFullYear()],
      niveis_ensino_oferecidos: [],
      turnos_funcionamento: [],
      participa_programas_governamentais: [],
      status: 'active',
      municipio: defaultLocation.municipio,
      estado: defaultLocation.estado
    });
    setIsModalOpen(true);
  }

  // Função para carregar servidores lotados na escola
  async function loadSchoolStaff(schoolId, year = null) {
    if (!schoolId) {
      setSchoolStaff([]);
      return;
    }
    setLoadingStaff(true);
    try {
      // Busca as lotações ativas da escola, filtradas pelo ano letivo se especificado
      const params = { school_id: schoolId, status: 'ativo' };
      if (year) {
        params.academic_year = year;
      }
      const assignments = await schoolAssignmentAPI.list(params);
      
      // Busca os dados completos de cada servidor
      const staffDetails = await Promise.all(
        assignments.map(async (assignment) => {
          try {
            const staff = await staffAPI.get(assignment.staff_id);
            return {
              ...staff,
              lotacao: assignment
            };
          } catch (error) {
            console.error(`Erro ao buscar servidor ${assignment.staff_id}:`, error);
            return null;
          }
        })
      );
      
      // Filtra nulos e ordena por nome
      setSchoolStaff(staffDetails.filter(s => s !== null).sort((a, b) => a.nome.localeCompare(b.nome)));
    } catch (error) {
      console.error('Erro ao carregar servidores da escola:', error);
      setSchoolStaff([]);
    } finally {
      setLoadingStaff(false);
    }
  }

  // Recarrega servidores quando o ano letivo é alterado (e o modal está aberto)
  useEffect(() => {
    if (isModalOpen && (editingSchool?.id || formData?.id)) {
      const schoolId = editingSchool?.id || formData?.id;
      loadSchoolStaff(schoolId, selectedYear);
    }
  }, [selectedYear, isModalOpen, editingSchool?.id, formData?.id]);

  // Funções para gerenciar anos letivos
  function adicionarAnoLetivo(ano) {
    if (!ano) return;
    const anoNum = parseInt(ano);
    if (formData.anos_letivos && formData.anos_letivos[anoNum]) {
      showAlert('error', `Ano ${anoNum} já foi adicionado`);
      return;
    }
    
    const novosAnos = {
      ...formData.anos_letivos,
      [anoNum]: { status: 'aberto' }
    };
    updateFormData('anos_letivos', novosAnos);
    setNovoAnoLetivo('');
  }

  function alterarStatusAnoLetivo(ano, novoStatus) {
    if (!isAdmin) {
      showAlert('error', 'Apenas administradores podem alterar o status do ano letivo');
      return;
    }
    
    const novosAnos = {
      ...formData.anos_letivos,
      [ano]: { ...formData.anos_letivos[ano], status: novoStatus }
    };
    updateFormData('anos_letivos', novosAnos);
  }

  function removerAnoLetivo(ano) {
    if (!isAdmin) {
      showAlert('error', 'Apenas administradores podem remover anos letivos');
      return;
    }
    
    const novosAnos = { ...formData.anos_letivos };
    delete novosAnos[ano];
    updateFormData('anos_letivos', novosAnos);
  }

  // Verifica se o ano selecionado está fechado (bloqueia edição)
  const isYearClosed = formData.anos_letivos && 
    formData.anos_letivos[selectedYear] && 
    formData.anos_letivos[selectedYear].status === 'fechado';

  function handleView(school) {
    setEditingSchool(school);
    setViewMode(true);
    setFormData({
      ...school,
      anos_letivos: school.anos_letivos || {}
    });
    setIsModalOpen(true);
    loadSchoolStaff(school.id, selectedYear);
  }

  function handleEdit(school) {
    setEditingSchool(school);
    setViewMode(false);
    setFormData({
      ...school,
      anos_letivos: school.anos_letivos || {}
    });
    setIsModalOpen(true);
    loadSchoolStaff(school.id, selectedYear);
  }

  async function handleDelete(school) {
    if (window.confirm(`Tem certeza que deseja excluir a escola "${school.name}"?`)) {
      try {
        await schoolsAPI.delete(school.id);
        showAlert('success', 'Escola excluída com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir escola');
        console.error(error);
      }
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);

    try {
      if (editingSchool) {
        await schoolsAPI.update(editingSchool.id, formData);
        showAlert('success', 'Escola atualizada com sucesso');
      } else {
        await schoolsAPI.create(formData);
        showAlert('success', 'Escola criada com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      // Trata erros de validação Pydantic (array de objetos)
      const detail = error.response?.data?.detail;
      let errorMessage = 'Erro ao salvar escola';
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        errorMessage = detail[0]?.msg || 'Erro de validação';
      }
      showAlert('error', errorMessage);
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  }

  function updateFormData(field, value) {
    setFormData(prev => ({ ...prev, [field]: value }));
  }

  const columns = [
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Alunos',
      accessor: 'student_count',
      render: (row) => (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
          {row.student_count !== undefined ? row.student_count : '-'}
        </span>
      )
    },
    {
      header: 'Zona',
      accessor: 'zona_localizacao',
      render: (row) => row.zona_localizacao ? (row.zona_localizacao === 'urbana' ? 'Urbana' : 'Rural') : '-'
    },
    {
      header: 'Status',
      accessor: 'situacao_funcionamento',
      render: (row) => {
        const isAtiva = row.situacao_funcionamento === 'Ativa' || row.situacao_funcionamento === 'Em atividade' || (!row.situacao_funcionamento && row.status === 'active');
        return (
          <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
              isAtiva
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}>
            {isAtiva ? 'Ativa' : 'Inativa'}
          </span>
        );
      }
    }
  ];

  // Renderização das abas do formulário
  const renderDadosGerais = () => (
    <div className="space-y-6">
      {/* Identificação Institucional */}
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Identificação Institucional</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Nome da Escola *</label>
            <input
              type="text"
              value={formData.name || ''}
              onChange={(e) => updateFormData('name', e.target.value)}
              required
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Nome oficial da escola"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Código INEP</label>
            <input
              type="text"
              value={formData.inep_code || ''}
              onChange={(e) => updateFormData('inep_code', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Ex: 15175600"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Tipo de Unidade</label>
            <div className="flex gap-4 mt-2">
              <label className={`flex items-center gap-2 px-4 py-2 rounded-lg border-2 cursor-pointer transition-colors ${
                formData.tipo_unidade === 'sede' 
                  ? 'border-blue-500 bg-blue-50 text-blue-700' 
                  : 'border-gray-300 hover:border-gray-400'
              } ${viewMode ? 'cursor-not-allowed opacity-60' : ''}`}>
                <input
                  type="radio"
                  name="tipo_unidade"
                  value="sede"
                  checked={formData.tipo_unidade === 'sede'}
                  onChange={(e) => {
                    updateFormData('tipo_unidade', e.target.value);
                    updateFormData('anexa_a', '');
                  }}
                  disabled={viewMode}
                  className="text-blue-600"
                />
                <span className="font-medium">Sede</span>
              </label>
              <label className={`flex items-center gap-2 px-4 py-2 rounded-lg border-2 cursor-pointer transition-colors ${
                formData.tipo_unidade === 'anexa' 
                  ? 'border-orange-500 bg-orange-50 text-orange-700' 
                  : 'border-gray-300 hover:border-gray-400'
              } ${viewMode ? 'cursor-not-allowed opacity-60' : ''}`}>
                <input
                  type="radio"
                  name="tipo_unidade"
                  value="anexa"
                  checked={formData.tipo_unidade === 'anexa'}
                  onChange={(e) => updateFormData('tipo_unidade', e.target.value)}
                  disabled={viewMode}
                  className="text-orange-600"
                />
                <span className="font-medium">Anexa</span>
              </label>
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Característica Escolar</label>
            <input
              type="text"
              value={formData.caracteristica_escolar || ''}
              onChange={(e) => updateFormData('caracteristica_escolar', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Zona de Localização</label>
            <select
              value={formData.zona_localizacao || 'urbana'}
              onChange={(e) => updateFormData('zona_localizacao', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="urbana">Urbana</option>
              <option value="rural">Rural</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">CNPJ</label>
            <input
              type="text"
              value={formData.cnpj || ''}
              onChange={(e) => updateFormData('cnpj', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="00.000.000/0000-00"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Situação de Funcionamento</label>
            <select
              value={formData.situacao_funcionamento || 'Ativa'}
              onChange={(e) => updateFormData('situacao_funcionamento', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="Ativa">Ativa</option>
              <option value="Inativa">Inativa</option>
            </select>
          </div>
          
          {/* Campo Anexa a: - aparece apenas quando tipo_unidade é 'anexa' */}
          {formData.tipo_unidade === 'anexa' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Anexa a: <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.anexa_a || ''}
                onChange={(e) => updateFormData('anexa_a', e.target.value)}
                disabled={viewMode}
                required={formData.tipo_unidade === 'anexa'}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                <option value="">Selecione a escola sede</option>
                {schools
                  .filter(s => s.id !== editingSchool?.id && s.tipo_unidade !== 'anexa')
                  .map(school => (
                    <option key={school.id} value={school.id}>{school.name}</option>
                  ))
                }
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Localização */}
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Localização</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">CEP</label>
            <input
              type="text"
              value={formatCEP(formData.cep || '')}
              onChange={(e) => updateFormData('cep', e.target.value.replace(/\D/g, '').slice(0, 8))}
              disabled={viewMode}
              maxLength={9}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="00000-000"
            />
          </div>
          
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">Logradouro</label>
            <input
              type="text"
              value={formData.logradouro || ''}
              onChange={(e) => updateFormData('logradouro', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Rua, Avenida, etc."
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Número</label>
            <input
              type="text"
              value={formData.numero || ''}
              onChange={(e) => updateFormData('numero', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">Complemento</label>
            <input
              type="text"
              value={formData.complemento || ''}
              onChange={(e) => updateFormData('complemento', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Bairro</label>
            <input
              type="text"
              value={formData.bairro || ''}
              onChange={(e) => updateFormData('bairro', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Município</label>
            <input
              type="text"
              value={formData.municipio || ''}
              onChange={(e) => updateFormData('municipio', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Estado</label>
            <input
              type="text"
              value={formData.estado || ''}
              onChange={(e) => updateFormData('estado', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Ex: PA, SP, RJ"
            />
          </div>
        </div>
      </div>

      {/* Contatos */}
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Contatos</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Telefone</label>
            <input
              type="text"
              value={formatPhone(formData.telefone || '')}
              onChange={(e) => updateFormData('telefone', e.target.value.replace(/\D/g, '').slice(0, 11))}
              disabled={viewMode}
              maxLength={14}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="(00)00000-0000"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Celular</label>
            <input
              type="text"
              value={formatPhone(formData.celular || '')}
              onChange={(e) => updateFormData('celular', e.target.value.replace(/\D/g, '').slice(0, 11))}
              disabled={viewMode}
              maxLength={14}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="(00)00000-0000"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">E-mail</label>
            <input
              type="email"
              value={formData.email || ''}
              onChange={(e) => updateFormData('email', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Site</label>
            <input
              type="url"
              value={formData.site || ''}
              onChange={(e) => updateFormData('site', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* Status - Somente no modo edição */}
      {editingSchool && (
        <div>
          <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Status da Escola</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
              <select
                value={formData.status || 'active'}
                onChange={(e) => updateFormData('status', e.target.value)}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                <option value="active">Ativa</option>
                <option value="inactive">Inativa</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Autorização ou Reconhecimento</label>
              <input
                type="text"
                value={formData.regulamentacao || ''}
                onChange={(e) => updateFormData('regulamentacao', e.target.value)}
                disabled={viewMode}
                placeholder="Ex: Resolução n° 272 de 21 de maio de 2020 - CEE/PA"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              />
              <p className="text-xs text-gray-500 mt-1">
                Será exibido no Certificado de Conclusão
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderInfraestrutura = () => (
    <div className="space-y-6">
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Serviços Básicos</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Abastecimento de Água</label>
            <select
              value={formData.abastecimento_agua || ''}
              onChange={(e) => updateFormData('abastecimento_agua', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">Selecione</option>
              <option value="Rede pública">Rede pública</option>
              <option value="Poço artesiano">Poço artesiano</option>
              <option value="Cisterna">Cisterna</option>
              <option value="Outros">Outros</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Energia Elétrica</label>
            <select
              value={formData.energia_eletrica || ''}
              onChange={(e) => updateFormData('energia_eletrica', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">Selecione</option>
              <option value="Rede pública">Rede pública</option>
              <option value="Gerador">Gerador</option>
              <option value="Energia solar">Energia solar</option>
              <option value="Não há">Não há</option>
            </select>
          </div>
        </div>
      </div>

      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Acessibilidade</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_rampas || false}
              onChange={(e) => updateFormData('possui_rampas', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Possui Rampas</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_corrimao || false}
              onChange={(e) => updateFormData('possui_corrimao', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Possui Corrimão</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.banheiros_adaptados || false}
              onChange={(e) => updateFormData('banheiros_adaptados', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Banheiros Adaptados</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.sinalizacao_tatil || false}
              onChange={(e) => updateFormData('sinalizacao_tatil', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Sinalização Tátil</span>
          </label>
        </div>
      </div>

      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Conectividade</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_internet || false}
              onChange={(e) => updateFormData('possui_internet', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Possui Internet</span>
          </label>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Tipo de Conexão</label>
            <select
              value={formData.tipo_conexao || ''}
              onChange={(e) => updateFormData('tipo_conexao', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            >
              <option value="">Selecione</option>
              <option value="Fibra óptica">Fibra óptica</option>
              <option value="Cabo">Cabo</option>
              <option value="Rádio">Rádio</option>
              <option value="Satélite">Satélite</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );

  const renderDependencias = () => (
    <div className="space-y-6">
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Salas e Capacidade</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Número de Salas de Aula</label>
            <input
              type="number"
              value={formData.numero_salas_aula || 0}
              onChange={(e) => updateFormData('numero_salas_aula', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Capacidade Total de Alunos</label>
            <input
              type="number"
              value={formData.capacidade_total_alunos || 0}
              onChange={(e) => updateFormData('capacidade_total_alunos', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Número de Banheiros</label>
            <input
              type="number"
              value={formData.numero_banheiros || 0}
              onChange={(e) => updateFormData('numero_banheiros', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Espaços Disponíveis</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_biblioteca || false}
              onChange={(e) => updateFormData('possui_biblioteca', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Biblioteca</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_lab_ciencias || false}
              onChange={(e) => updateFormData('possui_lab_ciencias', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Laboratório de Ciências</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_lab_informatica || false}
              onChange={(e) => updateFormData('possui_lab_informatica', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Laboratório de Informática</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_quadra || false}
              onChange={(e) => updateFormData('possui_quadra', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Quadra Esportiva</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_cozinha || false}
              onChange={(e) => updateFormData('possui_cozinha', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Cozinha</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.possui_refeitorio || false}
              onChange={(e) => updateFormData('possui_refeitorio', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Refeitório</span>
          </label>
        </div>
      </div>
    </div>
  );

  const renderEquipamentos = () => (
    <div className="space-y-6">
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Tecnologia</h4>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Computadores</label>
            <input
              type="number"
              value={formData.qtd_computadores || 0}
              onChange={(e) => updateFormData('qtd_computadores', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Tablets</label>
            <input
              type="number"
              value={formData.qtd_tablets || 0}
              onChange={(e) => updateFormData('qtd_tablets', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Projetores</label>
            <input
              type="number"
              value={formData.qtd_projetores || 0}
              onChange={(e) => updateFormData('qtd_projetores', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Impressoras</label>
            <input
              type="number"
              value={formData.qtd_impressoras || 0}
              onChange={(e) => updateFormData('qtd_impressoras', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Aparelho de Televisão</label>
            <input
              type="number"
              value={formData.qtd_televisores || 0}
              onChange={(e) => updateFormData('qtd_televisores', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Projetor Multimídia (Data show)</label>
            <input
              type="number"
              value={formData.qtd_projetores_multimidia || 0}
              onChange={(e) => updateFormData('qtd_projetores_multimidia', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Aparelho de som</label>
            <input
              type="number"
              value={formData.qtd_aparelhos_som || 0}
              onChange={(e) => updateFormData('qtd_aparelhos_som', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Lousa digital</label>
            <input
              type="number"
              value={formData.qtd_lousas_digitais || 0}
              onChange={(e) => updateFormData('qtd_lousas_digitais', parseInt(e.target.value) || 0)}
              min="0"
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
            />
          </div>
        </div>
      </div>
    </div>
  );

  const renderDadosEnsino = () => {
    // Modo de visualização - mostra apenas os itens selecionados
    if (viewMode) {
      const niveisAtivos = [];
      
      // Educação Infantil
      if (formData.educacao_infantil) {
        const subniveis = [];
        if (formData.educacao_infantil_bercario_i) subniveis.push('Berçário I');
        if (formData.educacao_infantil_bercario_ii) subniveis.push('Berçário II');
        if (formData.educacao_infantil_bercario_iii) subniveis.push('Berçário III');
        if (formData.educacao_infantil_bercario) subniveis.push('Berçário'); // Retrocompatibilidade
        if (formData.educacao_infantil_maternal_i) subniveis.push('Maternal I');
        if (formData.educacao_infantil_maternal_ii) subniveis.push('Maternal II');
        if (formData.educacao_infantil_pre_i) subniveis.push('Pré I');
        if (formData.educacao_infantil_pre_ii) subniveis.push('Pré II');
        niveisAtivos.push({
          nome: 'Educação Infantil',
          subniveis,
          cor: 'blue'
        });
      }
      
      // Fundamental Anos Iniciais
      if (formData.fundamental_anos_iniciais) {
        const subniveis = [];
        if (formData.fundamental_inicial_1ano) subniveis.push('1º Ano');
        if (formData.fundamental_inicial_2ano) subniveis.push('2º Ano');
        if (formData.fundamental_inicial_3ano) subniveis.push('3º Ano');
        if (formData.fundamental_inicial_4ano) subniveis.push('4º Ano');
        if (formData.fundamental_inicial_5ano) subniveis.push('5º Ano');
        niveisAtivos.push({
          nome: 'Ensino Fundamental - Anos Iniciais',
          subniveis,
          cor: 'green'
        });
      }
      
      // Fundamental Anos Finais
      if (formData.fundamental_anos_finais) {
        const subniveis = [];
        if (formData.fundamental_final_6ano) subniveis.push('6º Ano');
        if (formData.fundamental_final_7ano) subniveis.push('7º Ano');
        if (formData.fundamental_final_8ano) subniveis.push('8º Ano');
        if (formData.fundamental_final_9ano) subniveis.push('9º Ano');
        niveisAtivos.push({
          nome: 'Ensino Fundamental - Anos Finais',
          subniveis,
          cor: 'purple'
        });
      }
      
      // Ensino Médio
      if (formData.ensino_medio) {
        niveisAtivos.push({
          nome: 'Ensino Médio',
          subniveis: [],
          cor: 'red'
        });
      }
      
      // EJA Anos Iniciais
      if (formData.eja) {
        const subniveis = [];
        if (formData.eja_inicial_1etapa) subniveis.push('1ª Etapa');
        if (formData.eja_inicial_2etapa) subniveis.push('2ª Etapa');
        niveisAtivos.push({
          nome: 'EJA - Anos Iniciais',
          subniveis,
          cor: 'yellow'
        });
      }
      
      // EJA Anos Finais
      if (formData.eja_final) {
        const subniveis = [];
        if (formData.eja_final_3etapa) subniveis.push('3ª Etapa');
        if (formData.eja_final_4etapa) subniveis.push('4ª Etapa');
        niveisAtivos.push({
          nome: 'EJA - Anos Finais',
          subniveis,
          cor: 'orange'
        });
      }
      
      // Atendimentos ativos
      const atendimentosAtivos = [];
      if (formData.aee) atendimentosAtivos.push('Atendimento Educacional Especializado - AEE');
      if (formData.atendimento_integral) atendimentosAtivos.push('Escola Integral');
      if (formData.reforco_escolar) atendimentosAtivos.push('Reforço Escolar');
      if (formData.aulas_complementares) atendimentosAtivos.push('Aulas Complementares');
      
      const corClasses = {
        blue: 'bg-blue-100 text-blue-800 border-blue-200',
        green: 'bg-green-100 text-green-800 border-green-200',
        purple: 'bg-purple-100 text-purple-800 border-purple-200',
        red: 'bg-red-100 text-red-800 border-red-200',
        yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200',
        orange: 'bg-orange-100 text-orange-800 border-orange-200'
      };
      
      return (
        <div className="space-y-6">
          <div>
            <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Níveis de Ensino Oferecidos</h4>
            {niveisAtivos.length > 0 ? (
              <div className="space-y-4">
                {niveisAtivos.map((nivel, idx) => (
                  <div key={idx} className={`p-4 rounded-lg border ${corClasses[nivel.cor]}`}>
                    <h5 className="font-semibold mb-2">{nivel.nome}</h5>
                    {nivel.subniveis.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {nivel.subniveis.map((sub, subIdx) => (
                          <span key={subIdx} className="px-2 py-1 bg-white/50 rounded text-sm">
                            {sub}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 italic">Nenhum nível de ensino cadastrado</p>
            )}
          </div>
          
          <div>
            <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Atendimentos e Programas</h4>
            {atendimentosAtivos.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {atendimentosAtivos.map((atend, idx) => (
                  <span key={idx} className="px-3 py-1 bg-teal-100 text-teal-800 rounded-full text-sm">
                    ✓ {atend}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 italic">Nenhum atendimento especial cadastrado</p>
            )}
          </div>
        </div>
      );
    }
    
    // Modo de edição - formulário completo
    return (
    <div className="space-y-6">
      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Níveis de Ensino Oferecidos</h4>
        
        {/* Educação Infantil */}
        <div className="mb-6">
          <label className="flex items-center space-x-2 mb-3">
            <input
              type="checkbox"
              checked={formData.educacao_infantil || false}
              onChange={(e) => updateFormData('educacao_infantil', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">Educação Infantil</span>
          </label>
          
          {formData.educacao_infantil && (
            <div className="ml-6 grid grid-cols-2 md:grid-cols-3 gap-3 p-4 bg-blue-50 rounded-lg">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_bercario_i || false}
                  onChange={(e) => updateFormData('educacao_infantil_bercario_i', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Berçário I <span className="text-xs text-gray-500">(3-11m)</span></span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_bercario_ii || false}
                  onChange={(e) => updateFormData('educacao_infantil_bercario_ii', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Berçário II <span className="text-xs text-gray-500">(1a-1a11m)</span></span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_maternal_i || false}
                  onChange={(e) => updateFormData('educacao_infantil_maternal_i', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Maternal I <span className="text-xs text-gray-500">(2a-2a11m)</span></span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_maternal_ii || false}
                  onChange={(e) => updateFormData('educacao_infantil_maternal_ii', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Maternal II <span className="text-xs text-gray-500">(3a-3a11m)</span></span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_pre_i || false}
                  onChange={(e) => updateFormData('educacao_infantil_pre_i', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Pré I <span className="text-xs text-gray-500">(4 anos)</span></span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_pre_ii || false}
                  onChange={(e) => updateFormData('educacao_infantil_pre_ii', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Pré II <span className="text-xs text-gray-500">(5 anos)</span></span>
              </label>
            </div>
          )}
        </div>

        {/* Fundamental Anos Iniciais */}
        <div className="mb-6">
          <label className="flex items-center space-x-2 mb-3">
            <input
              type="checkbox"
              checked={formData.fundamental_anos_iniciais || false}
              onChange={(e) => updateFormData('fundamental_anos_iniciais', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">Ensino Fundamental - Anos Iniciais</span>
          </label>
          
          {formData.fundamental_anos_iniciais && (
            <div className="ml-6 grid grid-cols-2 md:grid-cols-5 gap-3 p-4 bg-green-50 rounded-lg">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_inicial_1ano || false}
                  onChange={(e) => updateFormData('fundamental_inicial_1ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">1º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_inicial_2ano || false}
                  onChange={(e) => updateFormData('fundamental_inicial_2ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">2º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_inicial_3ano || false}
                  onChange={(e) => updateFormData('fundamental_inicial_3ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">3º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_inicial_4ano || false}
                  onChange={(e) => updateFormData('fundamental_inicial_4ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">4º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_inicial_5ano || false}
                  onChange={(e) => updateFormData('fundamental_inicial_5ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">5º Ano</span>
              </label>
            </div>
          )}
        </div>

        {/* Fundamental Anos Finais */}
        <div className="mb-6">
          <label className="flex items-center space-x-2 mb-3">
            <input
              type="checkbox"
              checked={formData.fundamental_anos_finais || false}
              onChange={(e) => updateFormData('fundamental_anos_finais', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">Ensino Fundamental - Anos Finais</span>
          </label>
          
          {formData.fundamental_anos_finais && (
            <div className="ml-6 grid grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-purple-50 rounded-lg">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_final_6ano || false}
                  onChange={(e) => updateFormData('fundamental_final_6ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">6º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_final_7ano || false}
                  onChange={(e) => updateFormData('fundamental_final_7ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">7º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_final_8ano || false}
                  onChange={(e) => updateFormData('fundamental_final_8ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">8º Ano</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.fundamental_final_9ano || false}
                  onChange={(e) => updateFormData('fundamental_final_9ano', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">9º Ano</span>
              </label>
            </div>
          )}
        </div>

        {/* Ensino Médio */}
        <div className="mb-6">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.ensino_medio || false}
              onChange={(e) => updateFormData('ensino_medio', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">Ensino Médio</span>
          </label>
        </div>

        {/* EJA Anos Iniciais */}
        <div className="mb-6">
          <label className="flex items-center space-x-2 mb-3">
            <input
              type="checkbox"
              checked={formData.eja || false}
              onChange={(e) => updateFormData('eja', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">EJA - Educação de Jovens e Adultos - Anos Iniciais</span>
          </label>
          
          {formData.eja && (
            <div className="ml-6 grid grid-cols-2 gap-3 p-4 bg-yellow-50 rounded-lg">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.eja_inicial_1etapa || false}
                  onChange={(e) => updateFormData('eja_inicial_1etapa', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">1ª Etapa</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.eja_inicial_2etapa || false}
                  onChange={(e) => updateFormData('eja_inicial_2etapa', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">2ª Etapa</span>
              </label>
            </div>
          )}
        </div>

        {/* EJA Anos Finais */}
        <div className="mb-6">
          <label className="flex items-center space-x-2 mb-3">
            <input
              type="checkbox"
              checked={formData.eja_final || false}
              onChange={(e) => updateFormData('eja_final', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm font-semibold text-gray-900">EJA - Educação de Jovens e Adultos - Anos Finais</span>
          </label>
          
          {formData.eja_final && (
            <div className="ml-6 grid grid-cols-2 gap-3 p-4 bg-orange-50 rounded-lg">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.eja_final_3etapa || false}
                  onChange={(e) => updateFormData('eja_final_3etapa', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">3ª Etapa</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.eja_final_4etapa || false}
                  onChange={(e) => updateFormData('eja_final_4etapa', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">4ª Etapa</span>
              </label>
            </div>
          )}
        </div>
      </div>

      <div>
        <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b">Atendimentos e Programas</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.aee || false}
              onChange={(e) => updateFormData('aee', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Atendimento Educacional Especializado - AEE</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.atendimento_integral || false}
              onChange={(e) => updateFormData('atendimento_integral', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Escola Integral</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.reforco_escolar || false}
              onChange={(e) => updateFormData('reforco_escolar', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Reforço Escolar</span>
          </label>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={formData.aulas_complementares || false}
              onChange={(e) => updateFormData('aulas_complementares', e.target.checked)}
              disabled={viewMode}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <span className="text-sm text-gray-700">Aulas Complementares</span>
          </label>
        </div>
      </div>
    </div>
    );
  };

  const renderTurmas = () => {
    // Filtra turmas da escola atual
    const schoolClasses = classes.filter(c => c.school_id === (editingSchool?.id || formData.school_id));

    return (
      <div className="space-y-4">
        <div className="flex justify-between items-center mb-4">
          <h4 className="text-md font-semibold text-gray-900">Turmas Cadastradas</h4>
          <button
            type="button"
            onClick={() => navigate('/admin/classes')}
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            Gerenciar Turmas
          </button>
        </div>

        {schoolClasses.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <p className="text-gray-500">Nenhuma turma cadastrada para esta escola</p>
            <button
              type="button"
              onClick={() => navigate('/admin/classes')}
              className="mt-3 text-sm text-blue-600 hover:text-blue-800 underline"
            >
              Cadastrar primeira turma
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 border rounded-lg">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ano Letivo</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {schoolClasses.map((classItem, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">{classItem.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{classItem.academic_year}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  // Função para renderizar o Quadro de Servidores
  const renderQuadroServidores = () => {
    const formatCargo = (cargo) => {
      const cargos = {
        'professor': 'Professor(a)',
        'diretor': 'Diretor(a)',
        'coordenador': 'Coordenador(a)',
        'secretario': 'Secretário(a)',
        'auxiliar_secretaria': 'Aux. Secretaria',
        'auxiliar': 'Auxiliar',
        'merendeira': 'Merendeira',
        'zelador': 'Zelador(a)',
        'vigia': 'Vigia',
        'outro': 'Outro'
      };
      return cargos[cargo] || cargo;
    };

    const formatVinculo = (vinculo) => {
      const vinculos = {
        'efetivo': 'Efetivo',
        'contratado': 'Contratado',
        'temporario': 'Temporário',
        'comissionado': 'Comissionado'
      };
      return vinculos[vinculo] || vinculo;
    };

    // Calcula CH Mensal (CH semanal * 4)
    const calcularCHMensal = (staff) => {
      // Prioriza a CH da lotação, se não tiver usa a CH do servidor
      const chSemanal = staff.lotacao?.carga_horaria || staff.carga_horaria_semanal || 0;
      return chSemanal * 4; // 4 semanas por mês
    };

    return (
      <div className="space-y-4">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <Users className="text-blue-600" size={20} />
            <h4 className="text-md font-semibold text-gray-900">
              Quadro de Servidores
              <span className="ml-2 text-sm font-normal text-gray-500">({selectedYear})</span>
            </h4>
          </div>
          <button
            type="button"
            onClick={() => navigate('/admin/staff')}
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            Gestão de Servidores
          </button>
        </div>

        {loadingStaff ? (
          <div className="flex justify-center items-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-3 text-gray-500">Carregando servidores...</span>
          </div>
        ) : schoolStaff.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <Users className="mx-auto text-gray-400 mb-2" size={40} />
            <p className="text-gray-500">Nenhum servidor lotado nesta escola em {selectedYear}</p>
            <button
              type="button"
              onClick={() => navigate('/admin/staff')}
              className="mt-3 text-sm text-blue-600 hover:text-blue-800 underline"
            >
              Cadastrar lotação
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 border rounded-lg">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Foto</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cargo</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Vínculo</th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">CH Men</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Celular</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {schoolStaff.map((staff, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    {/* Foto */}
                    <td className="px-4 py-3">
                      {staff.foto_url ? (
                        <img
                          src={uploadAPI.getUrl(staff.foto_url)}
                          alt={staff.nome}
                          className="w-10 h-10 rounded-full object-cover border-2 border-gray-200"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center border-2 border-gray-200">
                          <span className="text-blue-600 font-semibold text-sm">
                            {staff.nome?.charAt(0)?.toUpperCase()}
                          </span>
                        </div>
                      )}
                    </td>
                    {/* Nome */}
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">{staff.nome}</td>
                    {/* Cargo */}
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {formatCargo(staff.cargo)}
                      {staff.cargo_especifico && (
                        <span className="block text-xs text-gray-500">{staff.cargo_especifico}</span>
                      )}
                    </td>
                    {/* Vínculo */}
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                        staff.tipo_vinculo === 'efetivo' 
                          ? 'bg-green-100 text-green-800' 
                          : staff.tipo_vinculo === 'contratado'
                          ? 'bg-blue-100 text-blue-800'
                          : staff.tipo_vinculo === 'temporario'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-purple-100 text-purple-800'
                      }`}>
                        {formatVinculo(staff.tipo_vinculo)}
                      </span>
                    </td>
                    {/* CH Mensal */}
                    <td className="px-4 py-3 text-center">
                      <span className="text-sm font-semibold text-gray-900">
                        {calcularCHMensal(staff)}h
                      </span>
                    </td>
                    {/* Celular */}
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {staff.celular ? (
                        <a 
                          href={`https://wa.me/55${staff.celular.replace(/\D/g, '')}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-green-600 hover:text-green-800"
                        >
                          <Phone size={14} />
                          {staff.celular}
                        </a>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {/* Resumo */}
            <div className="mt-4 flex justify-between items-center bg-blue-50 rounded-lg p-3 border border-blue-200">
              <span className="text-sm font-medium text-blue-700">
                Total de servidores: {schoolStaff.length}
              </span>
              <span className="text-sm text-blue-600">
                CH Total: {schoolStaff.reduce((sum, s) => sum + (s.lotacao?.carga_horaria || s.carga_horaria_semanal || 0) * 4, 0)}h/mês
              </span>
            </div>
          </div>
        )}
      </div>
    );
  };

  // Renderização da aba de Permissões
  const renderPermissoes = () => {
    // Formata data para exibição
    const formatDateDisplay = (dateStr) => {
      if (!dateStr) return 'Não definida';
      const date = new Date(dateStr + 'T12:00:00');
      return date.toLocaleDateString('pt-BR');
    };
    
    // Verifica se há períodos configurados no calendário
    const hasCalendarioConfig = calendarioLetivo && calendarioLetivo.bimestre_1_inicio;
    
    return (
      <div className="space-y-6">
        <div>
          <h4 className="text-md font-semibold text-gray-900 mb-4 pb-2 border-b flex items-center gap-2">
            <Clock size={20} className="text-blue-600" />
            Períodos Bimestrais e Permissões de Lançamento
          </h4>
          
          {!hasCalendarioConfig ? (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="text-amber-600 flex-shrink-0 mt-0.5" size={20} />
                <div>
                  <h6 className="font-medium text-amber-800">Períodos não configurados</h6>
                  <p className="text-sm text-amber-700 mt-1">
                    Os períodos bimestrais ainda não foram configurados no Calendário Letivo. 
                    Configure os períodos no menu &quot;Calendário&quot; &gt; &quot;Períodos Bimestrais&quot; para definir as datas de início e fim de cada bimestre.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-600 mb-6">
              As datas de início e fim de cada bimestre são definidas no <strong>Calendário Letivo</strong>. 
              Aqui você pode configurar a <strong>data limite para lançamentos</strong> desta escola.
            </p>
          )}
          
          {/* 1º Bimestre */}
          <div className="border rounded-lg p-4 mb-4 bg-blue-50">
            <h5 className="font-medium text-blue-800 mb-4">1º Bimestre</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Início</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_1_inicio)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Fim</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_1_fim)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Limite para Lançamento</label>
                <input
                  type="date"
                  value={formData.bimestre_1_limite_lancamento || ''}
                  onChange={(e) => updateFormData('bimestre_1_limite_lancamento', e.target.value)}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 disabled:bg-gray-100"
                />
                <p className="text-xs text-orange-600 mt-1">Após esta data, professores não poderão mais fazer lançamentos do 1º bimestre</p>
              </div>
            </div>
          </div>

          {/* 2º Bimestre */}
          <div className="border rounded-lg p-4 mb-4 bg-green-50">
            <h5 className="font-medium text-green-800 mb-4">2º Bimestre</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Início</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_2_inicio)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Fim</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_2_fim)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Limite para Lançamento</label>
                <input
                  type="date"
                  value={formData.bimestre_2_limite_lancamento || ''}
                  onChange={(e) => updateFormData('bimestre_2_limite_lancamento', e.target.value)}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 disabled:bg-gray-100"
                />
                <p className="text-xs text-orange-600 mt-1">Após esta data, professores não poderão mais fazer lançamentos do 2º bimestre</p>
              </div>
            </div>
          </div>

          {/* 3º Bimestre */}
          <div className="border rounded-lg p-4 mb-4 bg-yellow-50">
            <h5 className="font-medium text-yellow-800 mb-4">3º Bimestre</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Início</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_3_inicio)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Fim</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_3_fim)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Limite para Lançamento</label>
                <input
                  type="date"
                  value={formData.bimestre_3_limite_lancamento || ''}
                  onChange={(e) => updateFormData('bimestre_3_limite_lancamento', e.target.value)}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 disabled:bg-gray-100"
                />
                <p className="text-xs text-orange-600 mt-1">Após esta data, professores não poderão mais fazer lançamentos do 3º bimestre</p>
              </div>
            </div>
          </div>

          {/* 4º Bimestre */}
          <div className="border rounded-lg p-4 mb-4 bg-purple-50">
            <h5 className="font-medium text-purple-800 mb-4">4º Bimestre</h5>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Início</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_4_inicio)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Fim</label>
                <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-100 text-gray-700">
                  {formatDateDisplay(calendarioLetivo?.bimestre_4_fim)}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data Limite para Lançamento</label>
                <input
                  type="date"
                  value={formData.bimestre_4_limite_lancamento || ''}
                  onChange={(e) => updateFormData('bimestre_4_limite_lancamento', e.target.value)}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 disabled:bg-gray-100"
                />
                <p className="text-xs text-orange-600 mt-1">Após esta data, professores não poderão mais fazer lançamentos do 4º bimestre</p>
              </div>
            </div>
          </div>

          {/* Informativo */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="text-amber-600 flex-shrink-0 mt-0.5" size={20} />
              <div>
                <h6 className="font-medium text-amber-800">Importante</h6>
                <p className="text-sm text-amber-700 mt-1">
                  A data limite de lançamento determina até quando os professores podem registrar notas, frequências e objetos de conhecimento. 
                  Após essa data, apenas administradores e secretários poderão fazer alterações nos registros do período.
                </p>
              </div>
            </div>
          </div>

          {/* Gerenciamento de Anos Letivos */}
          <div className="mt-8 pt-6 border-t">
            <h4 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <CheckCircle size={20} className="text-green-600" />
              Gerenciamento de Anos Letivos
            </h4>
            <p className="text-sm text-gray-600 mb-4">
              Adicione os anos letivos da escola e defina se estão <strong>Aberto</strong> (permite edição) ou <strong>Fechado</strong> (bloqueia todas as edições).
            </p>
            
            {/* Adicionar Ano */}
            {!viewMode && (
              <div className="flex items-center gap-3 mb-4">
                <select
                  value={novoAnoLetivo}
                  onChange={(e) => setNovoAnoLetivo(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione o ano...</option>
                  {anosDisponiveis
                    .filter(ano => !formData.anos_letivos || !formData.anos_letivos[ano])
                    .map(ano => (
                      <option key={ano} value={ano}>{ano}</option>
                    ))
                  }
                </select>
                <button
                  type="button"
                  onClick={() => adicionarAnoLetivo(novoAnoLetivo)}
                  disabled={!novoAnoLetivo}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                >
                  <Plus size={16} />
                  Adicionar
                </button>
              </div>
            )}
            
            {/* Lista de Anos */}
            <div className="space-y-2">
              {formData.anos_letivos && Object.keys(formData.anos_letivos).length > 0 ? (
                Object.keys(formData.anos_letivos)
                  .sort((a, b) => parseInt(b) - parseInt(a))
                  .map(ano => (
                    <div key={ano} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                      <span className="font-medium text-gray-800 text-lg">{ano}</span>
                      <div className="flex items-center gap-4">
                        {/* Toggle Aberto/Fechado */}
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name={`status-${ano}`}
                              checked={formData.anos_letivos[ano]?.status === 'aberto'}
                              onChange={() => alterarStatusAnoLetivo(ano, 'aberto')}
                              disabled={viewMode || !isAdmin}
                              className="w-4 h-4 text-green-600 focus:ring-green-500"
                            />
                            <span className={`text-sm ${formData.anos_letivos[ano]?.status === 'aberto' ? 'text-green-700 font-medium' : 'text-gray-500'}`}>
                              Aberto
                            </span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="radio"
                              name={`status-${ano}`}
                              checked={formData.anos_letivos[ano]?.status === 'fechado'}
                              onChange={() => alterarStatusAnoLetivo(ano, 'fechado')}
                              disabled={viewMode || !isAdmin}
                              className="w-4 h-4 text-red-600 focus:ring-red-500"
                            />
                            <span className={`text-sm ${formData.anos_letivos[ano]?.status === 'fechado' ? 'text-red-700 font-medium' : 'text-gray-500'}`}>
                              Fechado
                            </span>
                          </label>
                        </div>
                        
                        {/* Botão Remover (apenas admin) */}
                        {isAdmin && !viewMode && (
                          <button
                            type="button"
                            onClick={() => removerAnoLetivo(ano)}
                            className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                            title="Remover ano"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  ))
              ) : (
                <div className="text-center py-6 text-gray-500 bg-gray-50 rounded-lg border border-dashed">
                  <p>Nenhum ano letivo adicionado.</p>
                  <p className="text-sm">Adicione um ano letivo para configurar as permissões.</p>
                </div>
              )}
            </div>
            
            {/* Informativo sobre Ano Fechado */}
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mt-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
                <div>
                  <h6 className="font-medium text-red-800">Ano Letivo Fechado</h6>
                  <p className="text-sm text-red-700 mt-1">
                    Ao marcar um ano como <strong>&quot;Fechado&quot;</strong>, todas as informações referentes àquele ano (notas, frequências, matrículas, etc.) 
                    ficam bloqueadas para edição por <strong>qualquer usuário</strong>. Apenas administradores podem alterar o status do ano.
                  </p>
                </div>
              </div>
            </div>
          </div>
          
          {/* Pré-Matrícula Online */}
          <div className="mt-8 pt-6 border-t">
            <h4 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <Users size={20} className="text-purple-600" />
              Pré-Matrícula Online
            </h4>
            <p className="text-sm text-gray-600 mb-4">
              Quando ativada, esta escola aparecerá na página pública de <strong>Pré-Matrícula</strong>, 
              permitindo que responsáveis realizem o cadastro prévio de novos alunos.
            </p>
            
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-12 h-6 rounded-full relative cursor-pointer transition-colors ${
                    formData.pre_matricula_ativa ? 'bg-purple-600' : 'bg-gray-300'
                  } ${viewMode ? 'opacity-60 cursor-not-allowed' : ''}`}
                    onClick={() => !viewMode && updateFormData('pre_matricula_ativa', !formData.pre_matricula_ativa)}
                  >
                    <div className={`w-5 h-5 bg-white rounded-full absolute top-0.5 shadow-md transition-transform ${
                      formData.pre_matricula_ativa ? 'translate-x-6' : 'translate-x-0.5'
                    }`} />
                  </div>
                  <span className={`font-medium ${formData.pre_matricula_ativa ? 'text-purple-700' : 'text-gray-600'}`}>
                    {formData.pre_matricula_ativa ? 'Pré-Matrícula Ativada' : 'Pré-Matrícula Desativada'}
                  </span>
                </div>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                  formData.pre_matricula_ativa 
                    ? 'bg-green-100 text-green-700' 
                    : 'bg-gray-100 text-gray-600'
                }`}>
                  {formData.pre_matricula_ativa ? 'Visível ao público' : 'Não visível'}
                </span>
              </div>
              
              {formData.pre_matricula_ativa && (
                <p className="text-sm text-purple-700 mt-3">
                  Esta escola está aceitando pré-matrículas através do link público de pré-matrícula.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const tabLabels = [
    'Geral',
    'Infraestrutura',
    'Dependências',
    'Equipamentos',
    'Ensino',
    'Turmas',
    'Servidores',
    'Permissão'
  ];

  const tabContents = [
    renderDadosGerais(),
    renderInfraestrutura(),
    renderDependencias(),
    renderEquipamentos(),
    renderDadosEnsino(),
    renderTurmas(),
    renderQuadroServidores(),
    renderPermissoes()
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
              data-testid="back-to-dashboard-button"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900" data-testid="schools-title">Escolas</h1>
              <p className="text-gray-600 text-sm">Cadastro completo de escolas com todas as informações</p>
            </div>
          </div>
          {canCreate && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
              data-testid="create-school-button"
            >
              <Plus size={20} />
              <span>Nova Escola</span>
            </button>
          )}
        </div>

        {alert && (
          <div
            className={`p-4 rounded-lg flex items-start ${
              alert.type === 'success'
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
            }`}
            data-testid="alert-message"
          >
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
          data={schools}
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
          title={viewMode ? 'Visualizar Escola' : (editingSchool ? 'Editar Escola' : 'Nova Escola')}
          size="xl"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Seletor de Ano Letivo */}
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg border">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                  className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 font-medium"
                >
                  {anosDisponiveis.map(ano => (
                    <option key={ano} value={ano}>{ano}</option>
                  ))}
                </select>
              </div>
              {formData.anos_letivos && formData.anos_letivos[selectedYear] && (
                <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                  formData.anos_letivos[selectedYear].status === 'fechado' 
                    ? 'bg-red-100 text-red-700' 
                    : 'bg-green-100 text-green-700'
                }`}>
                  {formData.anos_letivos[selectedYear].status === 'fechado' ? '🔒 Ano Fechado' : '🔓 Ano Aberto'}
                </div>
              )}
            </div>
            
            {/* Aviso se ano está fechado */}
            {isYearClosed && !isAdmin && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-sm text-red-700 flex items-center gap-2">
                  <AlertCircle size={16} />
                  <span>O ano letivo {selectedYear} está <strong>fechado</strong>. Os dados não podem ser editados.</span>
                </p>
              </div>
            )}
            
            <Tabs tabs={tabLabels}>
              {tabContents}
            </Tabs>

            <div className="flex justify-end space-x-3 pt-4 border-t">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
                data-testid="cancel-button"
              >
                {viewMode ? 'Fechar' : 'Cancelar'}
              </button>
              {!viewMode && (
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                  data-testid="submit-button"
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
};
