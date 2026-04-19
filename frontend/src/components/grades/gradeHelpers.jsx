import { useState, useEffect } from 'react';

// ===== SISTEMA DE AVALIAÇÃO CONCEITUAL - EDUCAÇÃO INFANTIL =====
export const CONCEITOS_EDUCACAO_INFANTIL = {
  OD: { valor: 10.0, descricao: 'Objetivo Desenvolvido', cor: 'text-green-600' },
  DP: { valor: 7.5, descricao: 'Desenvolvido Parcialmente', cor: 'text-blue-600' },
  ND: { valor: 5.0, descricao: 'Não Desenvolvido', cor: 'text-yellow-600' },
  NT: { valor: 0.0, descricao: 'Não Trabalhado', cor: 'text-gray-500' },
};

// ===== SISTEMA DE AVALIAÇÃO CONCEITUAL - 1º E 2º ANO =====
export const CONCEITOS_ANOS_INICIAIS = {
  C: { valor: 10.0, descricao: 'Consolidado', cor: 'text-green-600' },
  ED: { valor: 7.5, descricao: 'Em Desenvolvimento', cor: 'text-blue-600' },
  ND: { valor: 5.0, descricao: 'Não Desenvolvido', cor: 'text-yellow-600' },
};

export const VALOR_PARA_CONCEITO = {
  10.0: 'OD',
  7.5: 'DP',
  5.0: 'ND',
  0.0: 'NT',
};

export const VALOR_PARA_CONCEITO_ANOS_INICIAIS = {
  10.0: 'C',
  7.5: 'ED',
  5.0: 'ND',
};

// Lista de séries/anos da Educação Infantil
export const SERIES_EDUCACAO_INFANTIL = [
  'Berçário', 'Berçário I', 'Berçário II',
  'Maternal', 'Maternal I', 'Maternal II',
  'Pré', 'Pré I', 'Pré II', 'Pré-Escola',
];

// Lista de séries/anos iniciais que usam avaliação conceitual (1º e 2º ano)
export const SERIES_ANOS_INICIAIS_CONCEITUAL = ['1º Ano', '2º Ano', '1º ano', '2º ano', '1 Ano', '2 Ano'];

// Verifica se é série de Educação Infantil
export const isEducacaoInfantil = (gradeLevel, nivelEnsino) => {
  if (nivelEnsino === 'educacao_infantil') return true;
  if (!gradeLevel) return false;
  return SERIES_EDUCACAO_INFANTIL.some(serie =>
    gradeLevel.toLowerCase().includes(serie.toLowerCase())
  );
};

// Verifica se é 1º ou 2º ano (usa conceitos específicos)
export const isAnosIniciaisConceitual = (gradeLevel) => {
  if (!gradeLevel) return false;
  const gradeLower = gradeLevel.toLowerCase();
  return SERIES_ANOS_INICIAIS_CONCEITUAL.some(serie =>
    gradeLower.includes(serie.toLowerCase())
  );
};

// Verifica se a série usa avaliação conceitual
export const usaAvaliacaoConceitual = (gradeLevel, nivelEnsino) => {
  return isEducacaoInfantil(gradeLevel, nivelEnsino) || isAnosIniciaisConceitual(gradeLevel);
};

// Converte valor para conceito
export const valorParaConceito = (valor, gradeLevel = null) => {
  if (valor === null || valor === undefined || valor === '') return '-';
  const num = Number(valor);

  // Se for 1º ou 2º ano, usar conceitos específicos
  if (gradeLevel && isAnosIniciaisConceitual(gradeLevel)) {
    if (num >= 10) return 'C';
    if (num >= 7.5) return 'ED';
    return 'ND';
  }

  // Educação Infantil
  if (num >= 10) return 'OD';
  if (num >= 7.5) return 'DP';
  if (num >= 5) return 'ND';
  return 'NT';
};

// Converte conceito para valor
export const conceitoParaValor = (conceito) => {
  if (CONCEITOS_EDUCACAO_INFANTIL[conceito]) {
    return CONCEITOS_EDUCACAO_INFANTIL[conceito].valor;
  }
  if (CONCEITOS_ANOS_INICIAIS[conceito]) {
    return CONCEITOS_ANOS_INICIAIS[conceito].valor;
  }
  return null;
};

// Calcula o maior conceito (para Educação Infantil e 1º/2º ano)
export const calcularMaiorConceito = (b1, b2, b3, b4) => {
  const valores = [b1, b2, b3, b4].filter(v => v !== null && v !== undefined && v !== '');
  if (valores.length === 0) return null;
  return Math.max(...valores.map(Number));
};

// Formata número com vírgula
export const formatGrade = (value) => {
  if (value === null || value === undefined || value === '') return '';
  return Number(value).toFixed(1).replace('.', ',');
};

// Converte string com vírgula para número
export const parseGrade = (value) => {
  if (!value || value === '') return null;
  const num = parseFloat(value.replace(',', '.'));
  return isNaN(num) ? null : Math.min(10, Math.max(0, num));
};

// Calcula média ponderada com recuperações por semestre
// Campos vazios são tratados como 0 para exibir média desde a 1ª nota
export const calculateAverage = (b1, b2, b3, b4, rec_s1, rec_s2) => {
  const grades = {
    b1: b1 ?? 0,
    b2: b2 ?? 0,
    b3: b3 ?? 0,
    b4: b4 ?? 0,
  };

  let finalGrades = { ...grades };

  if (rec_s1 !== null && rec_s1 !== undefined) {
    const keyS1 = grades.b1 <= grades.b2 ? 'b1' : 'b2';
    if (rec_s1 > finalGrades[keyS1]) {
      finalGrades[keyS1] = rec_s1;
    }
  }

  if (rec_s2 !== null && rec_s2 !== undefined) {
    const keyS2 = grades.b3 <= grades.b4 ? 'b3' : 'b4';
    if (rec_s2 > finalGrades[keyS2]) {
      finalGrades[keyS2] = rec_s2;
    }
  }

  const weights = { b1: 2, b2: 3, b3: 2, b4: 3 };
  const total = Object.keys(finalGrades).reduce((sum, k) => sum + (finalGrades[k] * weights[k]), 0);
  return Math.round(total / 10 * 10) / 10;
};

// Componente de input de nota
export const GradeInput = ({ value, onChange, disabled, placeholder = '0,0' }) => {
  const [localValue, setLocalValue] = useState(formatGrade(value));

  useEffect(() => {
    setLocalValue(formatGrade(value));
  }, [value]);

  const handleBlur = () => {
    const parsed = parseGrade(localValue);
    onChange(parsed);
    setLocalValue(formatGrade(parsed));
  };

  return (
    <input
      type="text"
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={handleBlur}
      disabled={disabled}
      className="w-16 px-2 py-1 text-center border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
      placeholder={placeholder}
    />
  );
};

// Componente de seleção de conceito (para Educação Infantil e 1º/2º Ano)
export const ConceitoSelect = ({ value, onChange, disabled, gradeLevel }) => {  const isAnosIniciais = gradeLevel && isAnosIniciaisConceitual(gradeLevel);
  const conceitosDisponiveis = isAnosIniciais ? CONCEITOS_ANOS_INICIAIS : CONCEITOS_EDUCACAO_INFANTIL;

  const conceito = valorParaConceito(value, gradeLevel);
  const corClasse = conceitosDisponiveis[conceito]?.cor || 'text-gray-500';

  return (
    <select
      value={conceito === '-' ? '' : conceito}
      onChange={(e) => {
        const novoConceito = e.target.value;
        const novoValor = novoConceito ? conceitoParaValor(novoConceito) : null;
        onChange(novoValor);
      }}
      disabled={disabled}
      className={`w-20 px-2 py-1 text-center border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 font-bold ${corClasse}`}
    >
      <option value="">-</option>
      {Object.entries(conceitosDisponiveis).map(([key, { descricao }]) => (
        <option key={key} value={key} title={descricao}>{key}</option>
      ))}
    </select>
  );
};

// Badge de status do aluno (com nota final colorida)
const STATUS_CONFIG = {
  cursando: { label: 'Cursando', class: 'bg-gray-100 text-gray-800' },
  aprovado: { label: 'Aprovado', class: 'bg-green-100 text-green-800' },
  reprovado_nota: { label: 'Reprovado', class: 'bg-red-100 text-red-800' },
  reprovado_frequencia: { label: 'Rep. Freq.', class: 'bg-orange-100 text-orange-800' },
};

export const StatusBadge = ({ status }) => {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.cursando;
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${c.class}`}>
      {c.label}
    </span>
  );
};
