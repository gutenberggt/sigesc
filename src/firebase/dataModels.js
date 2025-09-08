// src/firebase/dataModels.js

/**
 * @file Define os modelos de dados para as coleções do Firestore,
 * baseados nas informações da planilha "Dados" do Excel e nas necessidades do sistema.
 * Estes modelos servem como um guia para a estrutura dos documentos
 * que serão armazenados no banco de dados.
 */

/**
 * Modelo de dados para informações gerais da Escola.
 * Será armazenado na coleção 'escola'.
 * @typedef {Object} EscolaData
 * @property {string} nomeDaEscola - Nome completo da instituição de ensino.
 * @property {string} endereco - Endereço da escola.
 * @property {string} cidade - Cidade onde a escola está localizada.
 * @property {string} estado - Sigla do estado (ex: 'PA').
 * @property {string} censo - Data ou identificador do censo escolar.
 * @property {string} anoLetivo - Ano letivo corrente (identificador).
 * @property {number} diasLetivos - Total de dias letivos previstos para o ano.
 * @property {number} somaFaltasGeral - Soma total de faltas registradas no sistema (resumo).
 * @property {number} somaPresencasGeral - Soma total de presenças registradas no sistema (resumo).
 * @property {number} somaFaltasJustificadasGeral - Soma total de faltas justificadas (resumo).
 * @property {number} somaAtestadosGeral - Soma total de atestados (resumo).
 * @property {number} aulasMinistradasGeral - Total de aulas ministradas (resumo).
 */
export const escolaModel = {
  nomeDaEscola: "",
  endereco: "",
  cidade: "",
  estado: "",
  censo: "",
  anoLetivo: "",
  diasLetivos: 0,
  somaFaltasGeral: 0,
  somaPresencasGeral: 0,
  somaFaltasJustificadasGeral: 0,
  somaAtestadosGeral: 0,
  aulasMinistradasGeral: 0,
};

/**
 * Modelo de dados para um Aluno individual.
 * Será armazenado na coleção 'alunos'.
 * @typedef {Object} AlunoData
 * @property {string} nome - Nome completo do aluno (em maiúsculas).
 * @property {string} sexo - Sexo do aluno ('M' ou 'F').
 * @property {string} dataNascimento - Data de nascimento do aluno (formato 'DD/MM/AAAA').
 * @property {string} matricula - Número de matrícula do aluno.
 * @property {string} serie - Série/Ano em que o aluno está matriculado (ex: 'MATERNAL', '3º ANO').
 * @property {string} turno - Turno em que o aluno estuda ('MANHÃ', 'TARDE', 'NOITE').
 * @property {string} [evento] - Tipo de evento relacionado ao aluno (ex: 'TRANSFERIDO', 'DESISTENTE'). Opcional.
 * @property {string} [dataEvento] - Data do evento, se aplicável (formato 'DD/MM/AAAA'). Opcional.
 * @property {string} situacao - Situação atual do aluno (ex: 'ATIVO', 'APROVADO', 'TRANSFERIDO').
 * @property {string} userId - UID do usuário Firebase associado a este aluno (se houver).
 * @property {boolean} ativo - Indica se o cadastro do aluno está ativo no sistema.
 */
export const alunoModel = {
  nome: "",
  sexo: "",
  dataNascimento: "",
  matricula: "",
  serie: "",
  turno: "Manhã",
  evento: "",
  dataEvento: "",
  situacao: "ATIVO",
  userId: "",
  ativo: false,
};

/**
 * Modelo de dados para uma Disciplina.
 * Será armazenado na coleção 'disciplinas'.
 * @typedef {Object} DisciplinaData
 * @property {string} nome - Nome da disciplina (ex: 'LÍNGUA PORTUGUESA').
 * @property {number} cargaHoraria - Carga horária total da disciplina em aulas/horas.
 * @property {string} [professorResponsavel] - Nome do professor principal responsável pela disciplina. Opcional.
 */
export const disciplinaModel = {
  nome: "",
  cargaHoraria: 0,
  professorResponsavel: "",
};

/**
 * Modelo de dados para uma Turma.
 * Será armazenado na coleção 'turmas'.
 * @typedef {Object} TurmaData
 * @property {string} nomeTurma - Nome ou identificador da turma (ex: '3º Ano A', 'Jardim I').
 * @property {string} nivelEnsino - Nível de ensino associado à turma (ex: 'Ensino Fundamental - Anos Iniciais').
 * @property {string} anoSerie - Ano/Série/Etapa da turma (ex: '3º Ano', 'Maternal').
 * @property {string} turno - Turno da turma ('Manhã', 'Tarde', 'Noite', 'Integral').
 * @property {string} anoLetivo - Ano letivo da turma (ex: '2025').
 * @property {string} schoolId - ID do documento da escola à qual esta turma pertence.
 * @property {string[]} [professoresIds] - Array de UIDs de professores associados a esta turma. Opcional.
 * @property {number} [limiteVagas] - Limite de vagas para a turma. Opcional.
 * @property {string} [salaAula] - Nome ou número da sala de aula. Opcional.
 * @property {Date} dataCriacao - Timestamp da criação da turma.
 * @property {Date} ultimaAtualizacao - Timestamp da última atualização da turma.
 */
export const turmaModel = {
  nomeTurma: "",
  nivelEnsino: "",
  anoSerie: "",
  turno: "Manhã",
  anoLetivo: new Date().getFullYear().toString(),
  schoolId: "",
  professoresIds: [],
  limiteVagas: null,
  salaAula: "",
  dataCriacao: null,
  ultimaAtualizacao: null,
};

/**
 * Modelo de dados para uma Matrícula de Aluno.
 * Será armazenado na coleção 'matriculas'.
 * @typedef {Object} MatriculaData
 * @property {string} pessoaId - ID do documento da pessoa na coleção 'pessoas' vinculada a esta matrícula.
 * @property {string} codigoAluno - Código interno de identificação do aluno (gerado automaticamente).
 * @property {string} [codigoINEP] - Código INEP do aluno, se aplicável.
 * @property {string} [codigoSistemaEstadual] - Código do sistema/rede estadual, se aplicável.
 * @property {string} [fotoURL] - URL da foto do aluno (após upload para Storage).
 * @property {string} anoLetivo - Ano letivo da matrícula (ex: '2025').
 * @property {string} [turmaId] - ID da turma à qual o aluno está matriculado. Opcional (vinculação posterior).
 * @property {string} [situacaoMatricula] - Status da matrícula (ex: 'ATIVA', 'TRANCADA', 'CONCLUIDA').
 * @property {Object[]} [pessoasAutorizadasBuscar] - Array de objetos { nome: string, parentesco: string }.
 * @property {boolean} [utilizaTransporte] - Indica se o aluno utiliza transporte escolar.
 * @property {string} [veiculoTransporte] - Tipo de veículo utilizado.
 * @property {string} [rotaTransporte] - Rota do transporte.
 * @property {string} [responsavelLegalNome] - Nome do responsável legal (vindo de Pessoa ou digitado).
 * @property {string} [responsavelLegalParentesco] - Parentesco do responsável legal.
 * @property {string} [religiao] - Religião do aluno (copiado de Pessoa ou digitado).
 * @property {string} [beneficiosSociais] - Benefícios sociais do aluno.
 * @property {string} [deficienciasTranstornos] - Descrição de deficiências/transtornos.
 * @property {boolean} [alfabetizado] - Se o aluno é alfabetizado.
 * @property {boolean} [emancipado] - Se o aluno é emancipado.
 * @property {Object[]} [documentosDiversosURLs] - URLs de documentos diversos (após upload).
 * @property {string} [laudoMedicoURL] - URL do laudo médico (após upload).
 * @property {string} [observacoes] - Campo livre para observações (limite 255 caracteres).
 * @property {Date} dataMatricula - Timestamp da matrícula.
 * @property {Date} ultimaAtualizacao - Timestamp da última atualização.
 */
export const matriculaModel = {
  pessoaId: "",
  codigoAluno: "",
  codigoINEP: "",
  codigoSistemaEstadual: "",
  fotoURL: "",
  anoLetivo: new Date().getFullYear().toString(),
  turmaId: null,
  situacaoMatricula: "ATIVA",
  pessoasAutorizadasBuscar: [],
  utilizaTransporte: false,
  veiculoTransporte: "",
  rotaTransporte: "",
  responsavelLegalNome: "",
  responsavelLegalParentesco: "",
  religiao: "",
  beneficiosSociais: "",
  deficienciasTranstornos: "",
  alfabetizado: false,
  emancipado: false,
  documentosDiversosURLs: [],
  laudoMedicoURL: "",
  observacoes: "",
  dataMatricula: null,
  ultimaAtualizacao: null,
};
