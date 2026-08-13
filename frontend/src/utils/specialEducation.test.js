import {
  SPECIAL_EDUCATION_TARGET_OPTIONS,
  LEARNING_DISORDER_OPTIONS,
  hasAeeTargetCondition,
  isAeeTargetCondition,
  normalizeSpecialCondition,
  toggleCondition,
} from './specialEducation';

describe('classificação de Educação Especial / AEE', () => {
  test('TEA caracteriza público da Educação Especial', () => {
    expect(isAeeTargetCondition('Transtorno do Espectro Autista (TEA)')).toBe(true);
  });

  test('baixa visão caracteriza público da Educação Especial', () => {
    expect(isAeeTargetCondition('Baixa Visão')).toBe(true);
  });

  test('TDAH isolado não caracteriza público do AEE', () => {
    expect(hasAeeTargetCondition([
      'Transtorno do Déficit de Atenção e Hiperatividade (TDAH)',
    ])).toBe(false);
  });

  test('dislexia isolada não caracteriza público do AEE', () => {
    expect(hasAeeTargetCondition(['Dislexia'])).toBe(false);
  });

  test('dupla excepcionalidade mantém elegibilidade quando há condição-alvo', () => {
    expect(hasAeeTargetCondition([
      'Dislexia',
      'Transtorno do Espectro Autista (TEA)',
    ])).toBe(true);
  });

  test('valor legado Deficiência Visual é preservado como alvo até revisão', () => {
    expect(isAeeTargetCondition('Deficiência Visual')).toBe(true);
  });

  test('valor legado Deficiência Múltipla é preservado como alvo até revisão', () => {
    expect(isAeeTargetCondition('Deficiência Múltipla')).toBe(true);
  });

  test('normaliza grafia legada do TDAH sem duplicar o cadastro', () => {
    const legacy = 'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)';
    const canonical = 'Transtorno do Déficit de Atenção e Hiperatividade (TDAH)';
    expect(normalizeSpecialCondition(legacy)).toBe(canonical);
    expect(toggleCondition([legacy], canonical, true)).toEqual([legacy]);
  });

  test('lista oficial separa categorias de Educação Especial de transtornos de aprendizagem', () => {
    expect(SPECIAL_EDUCATION_TARGET_OPTIONS).toContain('Visão Monocular');
    expect(SPECIAL_EDUCATION_TARGET_OPTIONS).toContain('Altas Habilidades/Superdotação');
    expect(LEARNING_DISORDER_OPTIONS).toContain('Disgrafia');
    expect(LEARNING_DISORDER_OPTIONS).toContain('Dislalia');
    expect(LEARNING_DISORDER_OPTIONS).toContain('Disortografia');
    expect(LEARNING_DISORDER_OPTIONS).toContain('Transtorno do Processamento Auditivo Central (TPAC)');
    expect(SPECIAL_EDUCATION_TARGET_OPTIONS).not.toContain('Dislexia');
  });
});
