import {
  DIFFERENTIATED_LOCATION_OPTIONS,
  GEOGRAPHIC_LOCATION_OPTIONS,
  normalizeLocationValue,
} from './studentLocation';

describe('studentLocation', () => {
  test('oferece apenas urbana e rural como localização geográfica', () => {
    expect(GEOGRAPHIC_LOCATION_OPTIONS.map(item => item.value)).toEqual(['urbana', 'rural']);
  });

  test('distingue não informado de não estar em localização diferenciada', () => {
    expect(normalizeLocationValue(null)).toBe('');
    expect(DIFFERENTIATED_LOCATION_OPTIONS.some(item => item.value === 'nao_se_aplica')).toBe(true);
  });

  test('mantém os quatro grupos diferenciados canônicos internos', () => {
    const values = DIFFERENTIATED_LOCATION_OPTIONS.map(item => item.value);
    expect(values).toEqual(expect.arrayContaining([
      'area_assentamento',
      'terra_indigena',
      'comunidade_quilombola',
      'povos_comunidades_tradicionais',
    ]));
  });
});
