/**
 * Utilitários de nível de ensino — centralizados para evitar duplicação.
 */

export const EDUCATION_LEVEL_LABELS = {
  'fundamental_anos_iniciais': 'Fundamental - Anos Iniciais',
  'fundamental_anos_finais': 'Fundamental - Anos Finais',
  'eja': 'EJA - Anos Iniciais',
  'eja_final': 'EJA - Anos Finais',
  'educacao_infantil': 'Educação Infantil',
  'ensino_medio': 'Ensino Médio',
  'global': 'Global'
};

/**
 * Infere o nível de ensino da turma a partir de education_level, grade_level ou name.
 */
export const inferEducationLevel = (classInfo) => {
  if (!classInfo) return '';
  const explicit = (classInfo.education_level || classInfo.nivel_ensino || classInfo.level || '').toLowerCase();
  if (explicit && explicit !== '') return explicit;
  const ref = (classInfo.grade_level || classInfo.name || '').toUpperCase();
  if (/PRÉ[- ]?ESCOLA|BERÇÁRIO|MATERNAL|CRECHE|INFANTIL/.test(ref)) return 'educacao_infantil';
  if (/\bEJA\b/.test(ref)) {
    if (/FINAL|ANOS?\s*FINAI|[6-9]/.test(ref)) return 'eja_final';
    return 'eja_inicial';
  }
  const match = ref.match(/(\d+)[ºª°]?\s*(ANO|SÉRIE)/i);
  if (match) {
    const num = parseInt(match[1]);
    if (num >= 1 && num <= 5) return 'fundamental_anos_iniciais';
    if (num >= 6 && num <= 9) return 'fundamental_anos_finais';
  }
  if (classInfo.series && classInfo.series.length > 0) {
    const m = (classInfo.series[0] || '').match(/(\d+)/);
    if (m) {
      const num = parseInt(m[1]);
      if (num >= 1 && num <= 5) return 'fundamental_anos_iniciais';
      if (num >= 6 && num <= 9) return 'fundamental_anos_finais';
    }
  }
  return '';
};

/**
 * Retorna o tipo de frequência por nível de ensino e período.
 */
export const getAttendanceType = (educationLevel, period) => {
  if (period === 'integral' || period === 'complementar') {
    return 'by_component';
  }
  if (['fundamental_anos_iniciais', 'eja', 'eja_inicial', 'educacao_infantil'].includes(educationLevel)) {
    return 'daily';
  }
  return 'by_component';
};
