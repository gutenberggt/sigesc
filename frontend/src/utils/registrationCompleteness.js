// Cálculo de "completude do cadastro" do aluno.
// IMPORTANTE: estes critérios devem permanecer ESPELHADOS com o backend
// (routers/students.py -> _compute_student_completeness) para que a % da LISTA
// (calculada no backend) bata com a % da BARRA do formulário (calculada aqui).

const isFilled = (v) => v !== undefined && v !== null && String(v).trim() !== '';
const anyFilled = (...vals) => vals.some(isFilled);

// Critérios de completude (cada um vale 1 ponto). Conjunto AMPLIADO:
// obrigatórios + documento + telefone do responsável + turma + matrícula.
export const COMPLETENESS_CRITERIA = [
  { key: 'full_name', label: 'Nome Completo', test: (d) => isFilled(d.full_name) },
  { key: 'birth_date', label: 'Data de Nascimento', test: (d) => isFilled(d.birth_date) },
  { key: 'sex', label: 'Sexo', test: (d) => isFilled(d.sex) },
  { key: 'nationality', label: 'Nacionalidade', test: (d) => isFilled(d.nationality) },
  { key: 'color_race', label: 'Cor/Raça', test: (d) => isFilled(d.color_race) },
  { key: 'comunidade_tradicional', label: 'Comunidade Tradicional', test: (d) => isFilled(d.comunidade_tradicional) },
  { key: 'birth_city', label: 'Naturalidade (Cidade)', test: (d) => isFilled(d.birth_city) },
  { key: 'birth_state', label: 'Estado', test: (d) => isFilled(d.birth_state) },
  { key: 'mother_name', label: 'Mãe', test: (d) => isFilled(d.mother_name) },
  { key: 'legal_guardian_type', label: 'Responsável Legal', test: (d) => isFilled(d.legal_guardian_type) },
  { key: 'documento', label: 'Documento (CPF, NIS ou Certidão)', test: (d) => anyFilled(d.cpf, d.nis, d.civil_certificate_number) },
  { key: 'telefone_responsavel', label: 'Telefone do Responsável', test: (d) => anyFilled(d.mother_phone, d.father_phone, d.guardian_phone) },
  { key: 'class_id', label: 'Turma', test: (d) => isFilled(d.class_id) },
  { key: 'enrollment_number', label: 'Matrícula', test: (d) => isFilled(d.enrollment_number) },
];

// Retorna { percent, filled, total, missing: [{key, label}] }
export const computeCompleteness = (data) => {
  const d = data || {};
  const total = COMPLETENESS_CRITERIA.length;
  const missing = [];
  let filled = 0;
  COMPLETENESS_CRITERIA.forEach((c) => {
    if (c.test(d)) filled += 1;
    else missing.push({ key: c.key, label: c.label });
  });
  const percent = total > 0 ? Math.round((filled / total) * 100) : 0;
  return { percent, filled, total, missing };
};

// Faixas de cor: verde >=80, amarelo 50-79, vermelho <50.
export const completenessColor = (percent) => {
  if (percent >= 80) return { text: 'text-green-700', bg: 'bg-green-100', bar: 'bg-green-500', ring: 'border-green-300' };
  if (percent >= 50) return { text: 'text-yellow-700', bg: 'bg-yellow-100', bar: 'bg-yellow-500', ring: 'border-yellow-300' };
  return { text: 'text-red-700', bg: 'bg-red-100', bar: 'bg-red-500', ring: 'border-red-300' };
};
