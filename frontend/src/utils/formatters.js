/**
 * Funções de formatação de campos
 */

/**
 * Formata telefone no padrão (00)00000-0000
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatPhone = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '');
  if (numbers.length <= 2) return `(${numbers}`;
  if (numbers.length <= 7) return `(${numbers.slice(0, 2)})${numbers.slice(2)}`;
  return `(${numbers.slice(0, 2)})${numbers.slice(2, 7)}-${numbers.slice(7, 11)}`;
};

/**
 * Formata CEP no padrão 00000-000
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatCEP = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '');
  if (numbers.length <= 5) return numbers;
  return `${numbers.slice(0, 5)}-${numbers.slice(5, 8)}`;
};

/**
 * Formata CPF no padrão 000.000.000-00
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatCPF = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '');
  if (numbers.length <= 3) return numbers;
  if (numbers.length <= 6) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
  if (numbers.length <= 9) return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6)}`;
  return `${numbers.slice(0, 3)}.${numbers.slice(3, 6)}.${numbers.slice(6, 9)}-${numbers.slice(9, 11)}`;
};

/**
 * Formata CNPJ no padrão 00.000.000/0000-00
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatCNPJ = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '');
  if (numbers.length <= 2) return numbers;
  if (numbers.length <= 5) return `${numbers.slice(0, 2)}.${numbers.slice(2)}`;
  if (numbers.length <= 8) return `${numbers.slice(0, 2)}.${numbers.slice(2, 5)}.${numbers.slice(5)}`;
  if (numbers.length <= 12) return `${numbers.slice(0, 2)}.${numbers.slice(2, 5)}.${numbers.slice(5, 8)}/${numbers.slice(8)}`;
  return `${numbers.slice(0, 2)}.${numbers.slice(2, 5)}.${numbers.slice(5, 8)}/${numbers.slice(8, 12)}-${numbers.slice(12, 14)}`;
};

/**
 * Remove formatação de um valor (retorna apenas números)
 * @param {string} value - Valor a ter formatação removida
 * @returns {string} Apenas números
 */
export const unformat = (value) => {
  if (!value) return '';
  return value.replace(/\D/g, '');
};

/**
 * Formata NIS/PIS/PASEP no padrão 000.00000.00-0
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatNIS = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '').slice(0, 11);
  if (numbers.length <= 3) return numbers;
  if (numbers.length <= 8) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
  if (numbers.length <= 10) return `${numbers.slice(0, 3)}.${numbers.slice(3, 8)}.${numbers.slice(8)}`;
  return `${numbers.slice(0, 3)}.${numbers.slice(3, 8)}.${numbers.slice(8, 10)}-${numbers.slice(10, 11)}`;
};

/**
 * Formata Número SUS no padrão 000.0000.0000.0000
 * @param {string} value - Valor a ser formatado
 * @returns {string} Valor formatado
 */
export const formatSUS = (value) => {
  if (!value) return '';
  const numbers = value.replace(/\D/g, '').slice(0, 15);
  if (numbers.length <= 3) return numbers;
  if (numbers.length <= 7) return `${numbers.slice(0, 3)}.${numbers.slice(3)}`;
  if (numbers.length <= 11) return `${numbers.slice(0, 3)}.${numbers.slice(3, 7)}.${numbers.slice(7)}`;
  return `${numbers.slice(0, 3)}.${numbers.slice(3, 7)}.${numbers.slice(7, 11)}.${numbers.slice(11, 15)}`;
};

/**
 * Valida formato de e-mail
 * @param {string} email - E-mail a ser validado
 * @returns {boolean} True se válido
 */
export const isValidEmail = (email) => {
  if (!email) return true; // Vazio é válido (não obrigatório)
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};
