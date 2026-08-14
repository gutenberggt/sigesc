import {
  inputToTriState,
  normalizeHealthPayloadForSave,
  triStateToInput,
} from './studentHealth';

describe('studentHealth', () => {
  test('preserva os três estados lógicos', () => {
    expect(triStateToInput(true)).toBe('true');
    expect(triStateToInput(false)).toBe('false');
    expect(triStateToInput(null)).toBe('');
    expect(inputToTriState('true')).toBe(true);
    expect(inputToTriState('false')).toBe(false);
    expect(inputToTriState('')).toBeNull();
  });

  test('remove detalhes quando o estado não é Sim', () => {
    const result = normalizeHealthPayloadForSave({
      has_allergies: false,
      allergies_description: 'texto antigo',
      individualized_nutritional_need: null,
      nutritional_need_details: 'texto antigo',
    });
    expect(result.allergies_description).toBeNull();
    expect(result.nutritional_need_details).toBeNull();
  });
});
