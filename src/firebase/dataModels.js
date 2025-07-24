// ... (outros modelos: escolaModel, alunoModel, disciplinaModel)

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
  turno: "Manhã", // Valor padrão
  anoLetivo: new Date().getFullYear().toString(), // Ano atual como padrão
  schoolId: "",
  professoresIds: [],
  limiteVagas: null,
  salaAula: "",
  dataCriacao: null,
  ultimaAtualizacao: null,
};