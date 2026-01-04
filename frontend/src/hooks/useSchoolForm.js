/**
 * Hook para gestão do formulário de escola
 * Contém estado inicial e helpers para manipulação do form
 */
import { useState, useCallback } from 'react';

// Estado inicial do formulário de escola
export const getInitialSchoolFormState = (defaultLocation = {}) => ({
  // Dados Gerais - Identificação
  name: '',
  inep_code: '',
  tipo_unidade: 'sede',
  anexa_a: '',
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
  municipio: defaultLocation.municipio || '',
  distrito: '',
  estado: defaultLocation.estado || '',
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
  
  // Permissão - Data Limite de Lançamento por Bimestre
  bimestre_1_limite_lancamento: '',
  bimestre_2_limite_lancamento: '',
  bimestre_3_limite_lancamento: '',
  bimestre_4_limite_lancamento: '',
  
  // Anos Letivos da escola e seus status
  anos_letivos: {},
  
  status: 'active'
});

export function useSchoolForm(defaultLocation = {}) {
  const [formData, setFormData] = useState(() => 
    getInitialSchoolFormState(defaultLocation)
  );
  const [submitting, setSubmitting] = useState(false);

  // Reset form to initial state
  const resetForm = useCallback(() => {
    setFormData(getInitialSchoolFormState(defaultLocation));
  }, [defaultLocation]);

  // Update a single field
  const updateField = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  }, []);

  // Load data from existing school
  const loadSchoolData = useCallback((school) => {
    if (!school) {
      resetForm();
      return;
    }
    setFormData({ ...getInitialSchoolFormState(defaultLocation), ...school });
  }, [defaultLocation, resetForm]);

  // Add academic year
  const adicionarAnoLetivo = useCallback((ano) => {
    const anoNum = parseInt(ano);
    if (isNaN(anoNum) || anoNum < 2020 || anoNum > 2050) {
      throw new Error('Ano inválido');
    }
    
    if (formData.anos_letivos?.[anoNum]) {
      throw new Error('Ano letivo já existe');
    }
    
    setFormData(prev => ({
      ...prev,
      anos_letivos: {
        ...prev.anos_letivos,
        [anoNum]: { status: 'configurando' }
      }
    }));
  }, [formData.anos_letivos]);

  // Change academic year status
  const alterarStatusAnoLetivo = useCallback((ano, novoStatus) => {
    setFormData(prev => ({
      ...prev,
      anos_letivos: {
        ...prev.anos_letivos,
        [ano]: { ...prev.anos_letivos?.[ano], status: novoStatus }
      }
    }));
  }, []);

  // Remove academic year
  const removerAnoLetivo = useCallback((ano) => {
    setFormData(prev => {
      const novosAnos = { ...prev.anos_letivos };
      delete novosAnos[ano];
      return { ...prev, anos_letivos: novosAnos };
    });
  }, []);

  // Check if year is closed
  const isYearClosed = useCallback((year) => {
    return formData.anos_letivos?.[year]?.status === 'fechado';
  }, [formData.anos_letivos]);

  return {
    formData,
    submitting,
    setSubmitting,
    setFormData,
    resetForm,
    updateField,
    loadSchoolData,
    adicionarAnoLetivo,
    alterarStatusAnoLetivo,
    removerAnoLetivo,
    isYearClosed
  };
}

export default useSchoolForm;
