// Classificação normativa para cadastro do estudante.
// Referências funcionais: LDB (Lei 9.394/1996, arts. 58 e 59) e orientações
// vigentes do Inep/Censo Escolar para Educação Especial.
//
// Os valores persistidos continuam no campo legado `disabilities` para manter
// compatibilidade com o backend e com registros já existentes.

export const SPECIAL_EDUCATION_TARGET_OPTIONS = [
  'Deficiência Física',
  'Deficiência Intelectual',
  'Deficiência Auditiva',
  'Surdez',
  'Surdocegueira',
  'Baixa Visão',
  'Cegueira',
  'Visão Monocular',
  'Transtorno do Espectro Autista (TEA)',
  'Altas Habilidades/Superdotação',
];

// Transtornos que impactam o desenvolvimento da aprendizagem coletados pelo
// Censo Escolar desde 2025. Isoladamente, NÃO caracterizam público do AEE.
export const LEARNING_DISORDER_OPTIONS = [
  'Discalculia',
  'Disgrafia',
  'Dislalia',
  'Dislexia',
  'Disortografia',
  'Transtorno do Déficit de Atenção e Hiperatividade (TDAH)',
  'Transtorno do Processamento Auditivo Central (TPAC)',
];

// Condições relevantes ao acompanhamento pedagógico, mas que não são, por si,
// categorias de deficiência/TEA/AH-SD do Censo Escolar.
export const OTHER_CONDITION_OPTIONS = [
  'Transtorno do Desenvolvimento da Linguagem (TDL)',
  'Síndrome de Down',
];

// Valores antigos do SIGESC preservados para não apagar ou reinterpretar
// automaticamente informação histórica. Novos registros devem usar as
// categorias atuais acima.
export const LEGACY_SPECIAL_EDUCATION_OPTIONS = [
  'Deficiência Visual',
  'Deficiência Múltipla',
];

const LEGACY_EQUIVALENTS = {
  'Transtorno de Déficit de Atenção e Hiperatividade (TDAH)':
    'Transtorno do Déficit de Atenção e Hiperatividade (TDAH)',
};

export const normalizeSpecialCondition = (value) =>
  LEGACY_EQUIVALENTS[value] || value;

export const isAeeTargetCondition = (value) => {
  const normalized = normalizeSpecialCondition(value);
  return SPECIAL_EDUCATION_TARGET_OPTIONS.includes(normalized)
    || LEGACY_SPECIAL_EDUCATION_OPTIONS.includes(normalized);
};

export const hasAeeTargetCondition = (values = []) =>
  (values || []).some(isAeeTargetCondition);

export const getLegacySpecialEducationValues = (values = []) =>
  (values || []).filter((value) => LEGACY_SPECIAL_EDUCATION_OPTIONS.includes(value));

export const hasCondition = (values = [], option) => {
  const target = normalizeSpecialCondition(option).toLocaleLowerCase('pt-BR');
  return (values || []).some(
    (value) => normalizeSpecialCondition(value).toLocaleLowerCase('pt-BR') === target,
  );
};

export const toggleCondition = (values = [], option, checked) => {
  const normalizedOption = normalizeSpecialCondition(option);
  const current = values || [];

  if (checked) {
    if (hasCondition(current, normalizedOption)) return current;
    return [...current, normalizedOption];
  }

  return current.filter(
    (value) => normalizeSpecialCondition(value) !== normalizedOption,
  );
};
