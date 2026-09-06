import {
  selectCanonicalVisibilityRecords,
  mergeLegacyAndCanonicalVisibility,
} from './contentLegacyCanonicalVisibilityPolicy';

const baseMeta = {
  classId: '9A',
  componentId: 'math',
  academicYear: 2026,
  month: 2,
};

const canonical = [
  {
    id: 'legacy-mode-copy',
    class_id: '9A',
    component_id: 'math',
    date: '2026-02-09',
    academic_year: 2026,
    assignment_id: null,
    teacher_id: 'luiz',
    content: 'Conteúdo administrativo reconstruído',
  },
  {
    id: 'dvd-content',
    class_id: '9A',
    component_id: 'math',
    date: '2026-02-11',
    academic_year: 2026,
    assignment_id: 'dvd-luiz-math',
    teacher_id: 'luiz',
    content: 'Conteúdo DVD',
  },
  {
    id: 'wrong-component',
    class_id: '9A',
    component_id: 'history',
    date: '2026-02-12',
    academic_year: 2026,
    assignment_id: null,
  },
];

describe('R2.0g.5 — paridade institucional de leitura de conteúdos', () => {
  test('fallback do professor preserva somente canônico sem assignment', () => {
    const selected = selectCanonicalVisibilityRecords(canonical, {
      ...baseMeta,
      includeAssignedCanonical: false,
    });

    expect(selected.map((item) => item.id)).toEqual(['legacy-mode-copy']);
  });

  test('gestão inclui canônicos com e sem assignment no mesmo escopo pedagógico', () => {
    const selected = selectCanonicalVisibilityRecords(canonical, {
      ...baseMeta,
      includeAssignedCanonical: true,
    });

    expect(selected.map((item) => item.id)).toEqual([
      'legacy-mode-copy',
      'dvd-content',
    ]);
    expect(selected.some((item) => item.component_id === 'history')).toBe(false);
  });

  test('overlay institucional preserva legado e dá precedência à representação canônica equivalente', () => {
    const legacy = [
      {
        id: 'legacy-original',
        class_id: '9A',
        course_id: 'math',
        date: '2026-02-09',
        teacher_id: 'luiz',
      },
      {
        id: 'legacy-other-day',
        class_id: '9A',
        course_id: 'math',
        date: '2026-02-10',
        teacher_id: 'luiz',
      },
    ];
    const canonicalEquivalent = [{
      id: 'canonical-equivalent',
      legacy_id: 'legacy-original',
      class_id: '9A',
      component_id: 'math',
      date: '2026-02-09',
      teacher_id: 'luiz',
    }];

    const merged = mergeLegacyAndCanonicalVisibility(legacy, canonicalEquivalent);

    expect(merged.map((item) => item.id)).toEqual([
      'legacy-other-day',
      'canonical-equivalent',
    ]);
  });
});
