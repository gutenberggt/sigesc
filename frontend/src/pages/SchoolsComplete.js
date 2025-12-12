import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { schoolsAPI, classesAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';

export function SchoolsComplete() {
  const navigate = useNavigate();
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchool, setEditingSchool] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Estado do formulário com valores padrão
  const [formData, setFormData] = useState({
    // Dados Gerais - Identificação
    name: '',
    inep_code: '',
    sigla: '',
    caracteristica_escolar: '',
    zona_localizacao: 'urbana',
    cnpj: '',
    situacao_funcionamento: 'Em atividade',
    
    // Dados Gerais - Localização
    cep: '',
    logradouro: '',
    numero: '',
    complemento: '',
    bairro: '',
    municipio: '',
    distrito: '',
    estado: '',
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
    educacao_infantil_bercario: false,
    educacao_infantil_maternal_i: false,
    educacao_infantil_maternal_ii: false,
    educacao_infantil_pre_i: false,
    educacao_infantil_pre_ii: false,
    
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
    
    status: 'active'
  });

  // Funções de carregamento de dados
  async function loadSchools() {
    try {
      setLoading(true);
      const data = await schoolsAPI.getAll();
      setSchools(data);
    } catch (error) {
      setAlert({ type: 'error', message: 'Erro ao carregar escolas' });
      setTimeout(() => setAlert(null), 5000);
      console.error(error);
    } finally {
      setLoading(false);
    }
  }

  async function loadClasses() {
    try {
      const data = await classesAPI.getAll();
      setClasses(data);
    } catch (error) {
      console.error('Erro ao carregar turmas:', error);
      setClasses([]);
    }
  }

  function showAlert(type, message) {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  }

  useEffect(() => {
    loadSchools();
    loadClasses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = () => {
    setEditingSchool(null);
    setViewMode(false);
    // Reset form with default values
    setFormData({
      name: '',
      inep_code: '',
      zona_localizacao: 'urbana',
      situacao_funcionamento: 'Em atividade',
      dependencia_administrativa: 'Municipal',
      anos_letivos_ativos: [new Date().getFullYear()],
      niveis_ensino_oferecidos: [],
      turnos_funcionamento: [],
      participa_programas_governamentais: [],
      status: 'active'
    });
    setIsModalOpen(true);
  };

  const handleView = (school) => {
    setEditingSchool(school);
    setViewMode(true);
    setFormData(school);
    setIsModalOpen(true);
  };

  const handleEdit = (school) => {
    setEditingSchool(school);
    setViewMode(false);
    setFormData(school);
    setIsModalOpen(true);
  };

  const handleDelete = async (school) => {
    if (window.confirm(`Tem certeza que deseja excluir a escola "${school.name}"?`)) {
      try {
        await schoolsAPI.delete(school.id);
        showAlert('success', 'Escola excluída com sucesso');
        loadSchools();
      } catch (error) {
        showAlert('error', 'Erro ao excluir escola');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
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
      loadSchools();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar escola');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const columns = [
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Código INEP',
      accessor: 'inep_code',
      render: (row) => row.inep_code || '-'
    },
    {
      header: 'Município',
      accessor: 'municipio',
      render: (row) => row.municipio || '-'
    },
    {
      header: 'Zona',
      accessor: 'zona_localizacao',
      render: (row) => row.zona_localizacao ? (row.zona_localizacao === 'urbana' ? 'Urbana' : 'Rural') : '-'
    },
    {
      header: 'Status',
      accessor: 'status',
      render: (row) => (
        <span
          className={`px-2 py-1 text-xs font-medium rounded-full ${
            row.status === 'active'
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {row.status === 'active' ? 'Ativa' : 'Inativa'}
        </span>
      )
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
            <label className="block text-sm font-medium text-gray-700 mb-2">Sigla</label>
            <input
              type="text"
              value={formData.sigla || ''}
              onChange={(e) => updateFormData('sigla', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Ex: CMEI"
            />
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
            <input
              type="text"
              value={formData.situacao_funcionamento || ''}
              onChange={(e) => updateFormData('situacao_funcionamento', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="Ex: Em atividade"
            />
          </div>
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
              value={formData.cep || ''}
              onChange={(e) => updateFormData('cep', e.target.value)}
              disabled={viewMode}
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
              value={formData.telefone || ''}
              onChange={(e) => updateFormData('telefone', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="(00) 0000-0000"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Celular</label>
            <input
              type="text"
              value={formData.celular || ''}
              onChange={(e) => updateFormData('celular', e.target.value)}
              disabled={viewMode}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              placeholder="(00) 00000-0000"
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

  const renderDadosEnsino = () => (
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
                  checked={formData.educacao_infantil_bercario || false}
                  onChange={(e) => updateFormData('educacao_infantil_bercario', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Berçário</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_maternal_i || false}
                  onChange={(e) => updateFormData('educacao_infantil_maternal_i', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Maternal I</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_maternal_ii || false}
                  onChange={(e) => updateFormData('educacao_infantil_maternal_ii', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Maternal II</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_pre_i || false}
                  onChange={(e) => updateFormData('educacao_infantil_pre_i', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Pré I</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={formData.educacao_infantil_pre_ii || false}
                  onChange={(e) => updateFormData('educacao_infantil_pre_ii', e.target.checked)}
                  disabled={viewMode}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Pré II</span>
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
            <span className="text-sm text-gray-700">Atendimento Integral</span>
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
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ano Letivo</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Série/Etapa</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turno</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {schoolClasses.map((classItem, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">{classItem.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{classItem.academic_year}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{classItem.grade_level}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {classItem.shift === 'morning' ? 'Manhã' :
                       classItem.shift === 'afternoon' ? 'Tarde' :
                       classItem.shift === 'evening' ? 'Noite' : 'Integral'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  const tabLabels = [
    'Dados Gerais',
    'Infraestrutura',
    'Dependências',
    'Equipamentos',
    'Dados do Ensino',
    'Turmas'
  ];

  const tabContents = [
    renderDadosGerais(),
    renderInfraestrutura(),
    renderDependencias(),
    renderEquipamentos(),
    renderDadosEnsino(),
    renderTurmas()
  ];

  return (
    <Layout>
      <div className="space-y-6">
        {/* Botão Voltar */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
          data-testid="back-to-dashboard-button"
        >
          <ArrowLeft size={20} />
          <span>Voltar ao Dashboard</span>
        </button>

        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900" data-testid="schools-title">Escolas</h1>
            <p className="text-gray-600 mt-1">Cadastro completo de escolas com todas as informações</p>
          </div>
          <button
            onClick={handleCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            data-testid="create-school-button"
          >
            <Plus size={20} />
            <span>Nova Escola</span>
          </button>
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
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={viewMode ? 'Visualizar Escola' : (editingSchool ? 'Editar Escola' : 'Nova Escola')}
          size="xl"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
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
