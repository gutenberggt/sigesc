const digitsOnly = (value) => String(value ?? '').replace(/\D/g, '');

export const EMPTY_STUDENT_ADDRESS = Object.freeze({
  zip_code: '',
  state: '',
  state_ibge_code: '',
  city: '',
  city_ibge_code: '',
  neighborhood: '',
  street: '',
  number: '',
  complement: '',
  geographic_location: '',
  differentiated_location: '',
});

export const normalizeStateIbgeCode = (value) => {
  const digits = digitsOnly(value).slice(0, 2);
  return digits.length === 2 ? digits : '';
};

export const normalizeCityIbgeCode = (value) => {
  const digits = digitsOnly(value).slice(0, 7);
  return digits.length === 7 ? digits : '';
};

export const ibgeCodesFromViaCep = (viaCep = {}) => {
  const cityIbgeCode = normalizeCityIbgeCode(viaCep.ibge);
  return {
    cityIbgeCode,
    stateIbgeCode: cityIbgeCode ? cityIbgeCode.slice(0, 2) : '',
  };
};

export const buildStudentAddressDefaultsFromMantenedora = (mantenedora = {}) => {
  const cityIbgeCode = normalizeCityIbgeCode(mantenedora.codigo_ibge_municipio);
  const explicitStateCode = normalizeStateIbgeCode(mantenedora.codigo_ibge_uf);

  return {
    ...EMPTY_STUDENT_ADDRESS,
    zip_code: digitsOnly(mantenedora.cep).slice(0, 8),
    state: String(mantenedora.estado || '').trim().toUpperCase(),
    state_ibge_code: explicitStateCode || (cityIbgeCode ? cityIbgeCode.slice(0, 2) : ''),
    city: String(mantenedora.municipio || '').trim(),
    city_ibge_code: cityIbgeCode,
  };
};

export const updateStudentAddressField = (address = {}, field, value) => {
  const next = { ...EMPTY_STUDENT_ADDRESS, ...(address || {}), [field]: value };

  if (field === 'state') {
    next.state = String(value || '').trim().toUpperCase();
    next.state_ibge_code = '';
    next.city_ibge_code = '';
  } else if (field === 'city') {
    next.city_ibge_code = '';
  } else if (field === 'state_ibge_code') {
    next.state_ibge_code = digitsOnly(value).slice(0, 2);
  } else if (field === 'city_ibge_code') {
    next.city_ibge_code = digitsOnly(value).slice(0, 7);
  } else if (field === 'zip_code') {
    next.zip_code = digitsOnly(value).slice(0, 8);
  }

  return next;
};
