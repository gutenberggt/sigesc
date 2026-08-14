import { mergeMissingIbgeCodesFromMantenedora } from './studentIbgeBackfill';

const mantenedora = {
  estado: 'PA',
  codigo_ibge_uf: '15',
  municipio: 'Floresta do Araguaia',
  codigo_ibge_municipio: '1502939',
};

describe('mergeMissingIbgeCodesFromMantenedora', () => {
  test('completa códigos ausentes em cadastro legado compatível', () => {
    expect(mergeMissingIbgeCodesFromMantenedora({
      state: 'PA',
      city: 'Floresta do Araguaia',
      street: 'Av. Brasil',
    }, mantenedora)).toMatchObject({
      state: 'PA',
      state_ibge_code: '15',
      city: 'Floresta do Araguaia',
      city_ibge_code: '1502939',
      street: 'Av. Brasil',
    });
  });

  test('não sobrescreve códigos já informados', () => {
    expect(mergeMissingIbgeCodesFromMantenedora({
      state: 'PA',
      state_ibge_code: '17',
      city: 'Floresta do Araguaia',
      city_ibge_code: '1700000',
    }, mantenedora)).toMatchObject({
      state_ibge_code: '17',
      city_ibge_code: '1700000',
    });
  });

  test('não injeta código municipal da mantenedora quando o município diverge', () => {
    expect(mergeMissingIbgeCodesFromMantenedora({
      state: 'PA',
      city: 'Conceição do Araguaia',
    }, mantenedora)).toMatchObject({
      state_ibge_code: '15',
      city_ibge_code: '',
    });
  });

  test('compara município ignorando acentos e diferenças de caixa', () => {
    expect(mergeMissingIbgeCodesFromMantenedora({
      state: 'pa',
      city: 'FLORESTA DO ARAGUAIA',
    }, mantenedora)).toMatchObject({
      state_ibge_code: '15',
      city_ibge_code: '1502939',
    });
  });
});
