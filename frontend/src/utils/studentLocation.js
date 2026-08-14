export const GEOGRAPHIC_LOCATION_OPTIONS = [
  { value: 'urbana', label: 'Urbana' },
  { value: 'rural', label: 'Rural' },
];

export const DIFFERENTIATED_LOCATION_OPTIONS = [
  { value: 'nao_se_aplica', label: 'Não está em localização diferenciada' },
  { value: 'area_assentamento', label: 'Área de assentamento' },
  { value: 'terra_indigena', label: 'Terra indígena' },
  { value: 'comunidade_quilombola', label: 'Comunidade quilombola' },
  { value: 'povos_comunidades_tradicionais', label: 'Área de povos e comunidades tradicionais' },
];

export const normalizeLocationValue = value => {
  if (value == null) return '';
  return String(value).trim();
};
