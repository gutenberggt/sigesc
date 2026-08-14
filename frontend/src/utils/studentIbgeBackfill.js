import {
  EMPTY_STUDENT_ADDRESS,
  buildStudentAddressDefaultsFromMantenedora,
  normalizeCityIbgeCode,
  normalizeStateIbgeCode,
} from './ibgeAddress';

const normalizeText = (value) => String(value ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .trim()
  .toLowerCase()
  .replace(/\s+/g, ' ');

const sameOrBlank = (currentValue, expectedValue) => {
  const current = normalizeText(currentValue);
  const expected = normalizeText(expectedValue);
  return !current || (!!expected && current === expected);
};

/**
 * Completa apenas códigos IBGE ausentes usando a Unidade Mantenedora.
 *
 * Regras de segurança:
 * - nunca sobrescreve código já informado;
 * - UF só herda código se estiver vazia ou coincidir com a UF da mantenedora;
 * - Município só herda código se estiver vazio ou coincidir com o município da mantenedora;
 * - os demais campos do endereço são preservados integralmente.
 */
export const mergeMissingIbgeCodesFromMantenedora = (address = {}, mantenedora = {}) => {
  const current = { ...EMPTY_STUDENT_ADDRESS, ...(address || {}) };
  const defaults = buildStudentAddressDefaultsFromMantenedora(mantenedora);

  const currentStateCode = normalizeStateIbgeCode(current.state_ibge_code);
  const currentCityCode = normalizeCityIbgeCode(current.city_ibge_code);
  const stateMatches = sameOrBlank(current.state, defaults.state);
  const cityMatches = sameOrBlank(current.city, defaults.city);

  return {
    ...current,
    state_ibge_code: currentStateCode || (stateMatches ? defaults.state_ibge_code : ''),
    city_ibge_code: currentCityCode || (stateMatches && cityMatches ? defaults.city_ibge_code : ''),
  };
};
