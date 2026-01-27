/**
 * Utilitário para extração de mensagens de erro
 * Lida com diferentes formatos de erro do backend (Pydantic, strings, objetos)
 */

/**
 * Extrai mensagem de erro de uma resposta de erro do axios/fetch
 * @param {Error} error - Objeto de erro
 * @param {string} defaultMessage - Mensagem padrão caso não consiga extrair
 * @returns {string} Mensagem de erro formatada
 */
export const extractErrorMessage = (error, defaultMessage = 'Erro ao processar requisição') => {
  const detail = error.response?.data?.detail;
  
  // String simples
  if (typeof detail === 'string') {
    return detail;
  }
  
  // Array de erros de validação Pydantic
  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || detail[0]?.message || 'Erro de validação';
  }
  
  // Objeto com mensagem
  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || defaultMessage;
  }
  
  // Fallback para mensagem do erro
  if (error.message) {
    return error.message;
  }
  
  return defaultMessage;
};

export default extractErrorMessage;
