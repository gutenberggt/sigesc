import {
  buildStudentAddressDefaultsFromMantenedora,
  ibgeCodesFromViaCep,
  updateStudentAddressField,
} from './ibgeAddress';

describe('ibgeAddress', () => {
  test('deriva código da UF a partir do geocódigo municipal do IBGE', () => {
    expect(ibgeCodesFromViaCep({ ibge: '1502939' })).toEqual({
      cityIbgeCode: '1502939',
      stateIbgeCode: '15',
    });
  });

  test('cria defaults do endereço do estudante usando a Unidade Mantenedora', () => {
    const address = buildStudentAddressDefaultsFromMantenedora({
      cep: '68.543-000',
      estado: 'PA',
      codigo_ibge_uf: '15',
      municipio: 'Floresta do Araguaia',
      codigo_ibge_municipio: '1502939',
    });

    expect(address).toMatchObject({
      zip_code: '68543000',
      state: 'PA',
      state_ibge_code: '15',
      city: 'Floresta do Araguaia',
      city_ibge_code: '1502939',
    });
    expect(address.street).toBe('');
    expect(address.number).toBe('');
  });

  test('alterar UF manualmente invalida códigos territoriais dependentes', () => {
    const current = {
      state: 'PA',
      state_ibge_code: '15',
      city: 'Floresta do Araguaia',
      city_ibge_code: '1502939',
    };
    const changed = updateStudentAddressField(current, 'state', 'TO');

    expect(changed.state).toBe('TO');
    expect(changed.state_ibge_code).toBe('');
    expect(changed.city_ibge_code).toBe('');
  });

  test('alterar município manualmente invalida somente o código municipal', () => {
    const current = {
      state: 'PA',
      state_ibge_code: '15',
      city: 'Floresta do Araguaia',
      city_ibge_code: '1502939',
    };
    const changed = updateStudentAddressField(current, 'city', 'Conceição do Araguaia');

    expect(changed.state_ibge_code).toBe('15');
    expect(changed.city_ibge_code).toBe('');
  });
});
