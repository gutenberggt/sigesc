// Constantes para o módulo de Gestão de Servidores

export const CARGOS = {
  auxiliar: 'Auxiliar Administrativo(a)',
  auxiliar_secretaria: 'Auxiliar de Secretaria',
  auxiliar_servicos_gerais: 'Auxiliar de Serviços Gerais',
  coordenador: 'Coordenador(a)',
  diretor: 'Diretor(a)',
  mediador: 'Mediador(a)',
  merendeira: 'Merendeira(o)',
  professor: 'Professor(a)',
  secretario: 'Secretário(a)',
  vigia: 'Vigia',
  zelador: 'Zelador(a)',
  outro: 'Outro'
};

export const STATUS_SERVIDOR = {
  ativo: { label: 'Ativo', color: 'bg-green-100 text-green-800' },
  afastado: { label: 'Afastado', color: 'bg-yellow-100 text-yellow-800' },
  licenca: { label: 'Licença', color: 'bg-blue-100 text-blue-800' },
  ferias: { label: 'Férias', color: 'bg-purple-100 text-purple-800' },
  aposentado: { label: 'Aposentado', color: 'bg-gray-100 text-gray-800' },
  exonerado: { label: 'Exonerado', color: 'bg-red-100 text-red-800' }
};

export const TIPOS_VINCULO = {
  efetivo: 'Efetivo',
  contratado: 'Contratado',
  temporario: 'Temporário',
  comissionado: 'Comissionado'
};

export const SEXOS = {
  masculino: 'Masculino',
  feminino: 'Feminino',
  outro: 'Outro'
};

export const COR_RACA = {
  branca: 'Branca',
  preta: 'Preta',
  parda: 'Parda',
  amarela: 'Amarela',
  indigena: 'Indígena',
  nao_declarado: 'Não Declarado'
};

export const FUNCOES = {
  professor: 'Professor(a)',
  diretor: 'Diretor(a)',
  vice_diretor: 'Vice-Diretor(a)',
  coordenador: 'Coordenador(a)',
  secretario: 'Secretário(a)',
  apoio: 'Apoio'
};

export const TURNOS = {
  matutino: 'Matutino',
  vespertino: 'Vespertino',
  noturno: 'Noturno',
  integral: 'Integral'
};

export const TABS = [
  { id: 'servidores', label: 'Servidores', icon: 'Users' },
  { id: 'lotacoes', label: 'Lotações', icon: 'Building2' },
  { id: 'alocacoes', label: 'Alocações de Professores', icon: 'GraduationCap' }
];

export const INITIAL_STAFF_FORM = {
  nome: '',
  cpf: '',
  foto_url: '',
  data_nascimento: '',
  sexo: '',
  cor_raca: '',
  celular: '',
  email: '',
  cargo: 'professor',
  cargo_especifico: '',
  tipo_vinculo: 'efetivo',
  data_admissao: '',
  carga_horaria_semanal: '',
  formacoes: [],
  especializacoes: [],
  status: 'ativo',
  motivo_afastamento: '',
  data_afastamento: '',
  previsao_retorno: '',
  observacoes: ''
};

export const INITIAL_LOTACAO_FORM = {
  staff_id: '',
  funcao: 'professor',
  data_inicio: '',
  turno: '',
  status: 'ativo',
  academic_year: new Date().getFullYear(),
  observacoes: ''
};

export const INITIAL_ALOCACAO_FORM = {
  staff_id: '',
  school_id: '',
  academic_year: new Date().getFullYear(),
  status: 'ativo',
  observacoes: ''
};
