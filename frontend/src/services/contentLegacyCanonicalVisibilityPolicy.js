// R2.0g.4/R2.0g.5 — política pura para composição canônica no fluxo legado.
//
// Este módulo não registra interceptors nem executa I/O. Ele existe para que a
// regra de escopo possa ser provada por testes comportamentais independentes da
// infraestrutura Axios/React.

const componentOf = (record = {}) => record.component_id || record.course_id || null;
const dayOf = (value) => String(value || '').slice(0, 10);

export const normalizeCanonicalVisibilityRecord = (record = {}) => ({
  ...record,
  course_id: record.course_id || record.component_id || null,
  component_id: record.component_id || record.course_id || null,
  source: 'content_entries',
  legacy: false,
  read_only: false,
});

export const matchesLegacyCanonicalScope = (record = {}, meta = {}) => {
  if (!meta.classId || !meta.componentId) return false;
  if (record.assignment_id && !meta.includeAssignedCanonical) return false;
  if (record.class_id !== meta.classId) return false;
  if (componentOf(record) !== meta.componentId) return false;

  const recordDate = dayOf(record.date);
  if (!recordDate) return false;
  if (meta.date && recordDate !== dayOf(meta.date)) return false;

  if (meta.academicYear) {
    const recordYear = Number(record.academic_year || recordDate.slice(0, 4));
    if (recordYear !== Number(meta.academicYear)) return false;
  }

  if (meta.month) {
    const recordMonth = Number(recordDate.slice(5, 7));
    if (recordMonth !== Number(meta.month)) return false;
  }

  return true;
};

export const selectCanonicalVisibilityRecords = (records = [], meta = {}) => (
  records
    .filter((record) => matchesLegacyCanonicalScope(record, meta))
    .map(normalizeCanonicalVisibilityRecord)
);

export const semanticVisibilityKey = (record = {}) => [
  record.class_id || '',
  componentOf(record) || '',
  dayOf(record.date),
  record.aula_numero ?? '',
  record.teacher_id || record.recorded_by || '',
].join('|');

export const mergeLegacyAndCanonicalVisibility = (legacy = [], canonical = []) => {
  const canonicalKeys = new Set(canonical.map(semanticVisibilityKey));
  const canonicalLegacyIds = new Set(canonical.map((item) => item.legacy_id).filter(Boolean));
  const legacyFiltered = legacy.filter((item) => (
    !canonicalLegacyIds.has(item.id) && !canonicalKeys.has(semanticVisibilityKey(item))
  ));

  return [...canonical, ...legacyFiltered]
    .sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
};

export const shouldComposeLegacyCanonicalFallback = (finalUrl = '') => {
  const url = String(finalUrl || '');
  return url.includes('/learning-objects') && !url.includes('/content-entries');
};
