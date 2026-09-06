import {
  mergeLegacyAndCanonicalVisibility,
  selectCanonicalVisibilityRecords,
  shouldComposeLegacyCanonicalFallback,
} from './contentLegacyCanonicalVisibilityPolicy';

const mathMeta = (overrides = {}) => ({
  classId: '9A',
  componentId: 'math',
  academicYear: 2026,
  month: 2,
  date: null,
  ...overrides,
});

describe('R2.0g.4 — política de visibilidade canônica no fluxo legado', () => {
  test('faz aparecer somente o content_entry administrativo da mesma turma + Matemática', () => {
    const records = [
      {
        id: 'copied-math',
        class_id: '9A',
        component_id: 'math',
        date: '2026-02-09',
        academic_year: 2026,
        assignment_id: null,
        teacher_id: 'luiz',
      },
      {
        id: 'other-component',
        class_id: '9A',
        component_id: 'history',
        date: '2026-02-09',
        academic_year: 2026,
        assignment_id: null,
        teacher_id: 'other',
      },
      {
        id: 'other-class',
        class_id: '8A',
        component_id: 'math',
        date: '2026-02-09',
        academic_year: 2026,
        assignment_id: null,
        teacher_id: 'luiz',
      },
      {
        id: 'dvd-owned',
        class_id: '9A',
        component_id: 'math',
        date: '2026-02-09',
        academic_year: 2026,
        assignment_id: 'dvd-assignment',
        teacher_id: 'luiz',
      },
    ];

    const selected = selectCanonicalVisibilityRecords(records, mathMeta());

    expect(selected.map((item) => item.id)).toEqual(['copied-math']);
    expect(selected[0]).toMatchObject({
      source: 'content_entries',
      legacy: false,
      read_only: false,
      component_id: 'math',
      course_id: 'math',
    });
  });

  test('os 111/98 candidatos históricos de outros componentes não podem virar Matemática por projeção', () => {
    const wrongComponent8A = Array.from({ length: 111 }, (_, index) => ({
      id: `8a-other-${index}`,
      class_id: '8A',
      component_id: index % 2 === 0 ? 'history' : 'portuguese',
      date: `2026-0${2 + (index % 3)}-10`,
      academic_year: 2026,
      assignment_id: null,
    }));
    const wrongComponent9A = Array.from({ length: 98 }, (_, index) => ({
      id: `9a-other-${index}`,
      class_id: '9A',
      component_id: index % 2 === 0 ? 'art' : 'history',
      date: `2026-0${2 + (index % 3)}-11`,
      academic_year: 2026,
      assignment_id: null,
    }));

    const selected8A = selectCanonicalVisibilityRecords(wrongComponent8A, {
      classId: '8A',
      componentId: 'math',
      academicYear: 2026,
    });
    const selected9A = selectCanonicalVisibilityRecords(wrongComponent9A, {
      classId: '9A',
      componentId: 'math',
      academicYear: 2026,
    });

    expect(selected8A).toHaveLength(0);
    expect(selected9A).toHaveLength(0);
  });

  test('um registro legado normal de maio permanece inalterado quando não há fallback canônico elegível', () => {
    const legacyMay = {
      id: 'legacy-may-04',
      class_id: '9A',
      course_id: 'math',
      date: '2026-05-04',
      teacher_id: 'luiz',
      content: 'conteúdo legado já visível',
    };
    const canonicalCandidates = [
      {
        id: 'may-other-component',
        class_id: '9A',
        component_id: 'history',
        date: '2026-05-04',
        academic_year: 2026,
        assignment_id: null,
      },
      {
        id: 'may-dvd-math',
        class_id: '9A',
        component_id: 'math',
        date: '2026-05-04',
        academic_year: 2026,
        assignment_id: 'dvd-assignment',
      },
    ];

    const selected = selectCanonicalVisibilityRecords(
      canonicalCandidates,
      mathMeta({ month: 5 })
    );
    const merged = mergeLegacyAndCanonicalVisibility([legacyMay], selected);

    expect(selected).toHaveLength(0);
    expect(merged).toEqual([legacyMay]);
  });

  test('se um bridge DVD já reescreveu para content_entries, o fallback legado não compõe nem duplica', () => {
    expect(shouldComposeLegacyCanonicalFallback('/api/content-entries?class_id=9A')).toBe(false);
    expect(shouldComposeLegacyCanonicalFallback('/api/learning-objects?class_id=9A')).toBe(true);
  });

  test('check-date canônico só aceita a data exata solicitada', () => {
    const records = [
      {
        id: 'feb-09',
        class_id: '9A',
        component_id: 'math',
        date: '2026-02-09',
        academic_year: 2026,
        assignment_id: null,
      },
      {
        id: 'feb-10',
        class_id: '9A',
        component_id: 'math',
        date: '2026-02-10',
        academic_year: 2026,
        assignment_id: null,
      },
    ];

    const selected = selectCanonicalVisibilityRecords(
      records,
      mathMeta({ date: '2026-02-09' })
    );

    expect(selected.map((item) => item.id)).toEqual(['feb-09']);
  });

  test('legacy_id continua impedindo duplicação de um registro já representado canonicamente', () => {
    const legacy = [{
      id: 'legacy-1',
      class_id: '9A',
      course_id: 'math',
      date: '2026-02-09',
      teacher_id: 'luiz',
    }];
    const canonical = [{
      id: 'canonical-1',
      legacy_id: 'legacy-1',
      class_id: '9A',
      component_id: 'math',
      date: '2026-02-09',
      teacher_id: 'luiz',
    }];

    const merged = mergeLegacyAndCanonicalVisibility(legacy, canonical);

    expect(merged.map((item) => item.id)).toEqual(['canonical-1']);
  });
});
