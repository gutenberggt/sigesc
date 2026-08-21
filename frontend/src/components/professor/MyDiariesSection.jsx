import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, CheckSquare, ClipboardList, School, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { teacherDiariesAPI } from '../../services/teacherDiaries';
import { buildDiaryActionUrl } from '../../utils/diaryPrefill';
import { inferEducationLevel } from '../../utils/educationLevel';

const PROFILE_LABELS = {
  regular: 'Regular',
  integrator: 'Componente integrador',
  shared: 'Compartilhado',
};

const ATTENDANCE_BY_COMPONENT_LEVELS = new Set([
  'fundamental_anos_finais',
  'eja_final',
  'ensino_medio',
]);

const sortByComponentName = (left, right) => (
  (left?.name || '').localeCompare(right?.name || '', 'pt-BR')
);

const usesAttendanceByComponent = (classInfo) => (
  ATTENDANCE_BY_COMPONENT_LEVELS.has(inferEducationLevel(classInfo))
);

const getComponentOperationalState = (component) => {
  if (!component?.diary) {
    return {
      canAttendance: true,
      canGrades: true,
      canContent: true,
      attendancePurpose: null,
      unresolvedGroup: false,
      sharedGradeOwner: true,
    };
  }

  const diary = component.diary;
  const caps = diary.capabilities || {};
  const unresolvedGroup = diary.profile === 'shared' && diary.student_scope === 'group';
  const sharedGradeOwner = diary.profile !== 'shared' || diary.grades_official_owner === true;

  return {
    canAttendance: !!caps.attendance_enabled && !unresolvedGroup,
    canGrades: !!caps.grades_enabled && !unresolvedGroup && sharedGradeOwner,
    canContent: !!caps.content_enabled,
    attendancePurpose: caps.attendance_purpose || null,
    unresolvedGroup,
    sharedGradeOwner,
  };
};

const buildComponentContext = (component, module, academicYear) => {
  const diary = component.diary;
  const baseContext = {
    academicYear: component.academicYear || module.classInfo?.academic_year || academicYear,
    schoolId: component.schoolId || module.school_id,
    classId: module.class_id,
    courseId: component.id || '',
  };

  if (diary) {
    return {
      ...baseContext,
      assignmentId: diary.assignment_id,
    };
  }

  return {
    ...baseContext,
    assignmentId: '',
  };
};

export default function MyDiariesSection({ legacyClasses = [] }) {
  const navigate = useNavigate();
  const academicYear = new Date().getFullYear();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ items: [], total: 0, blocked_total: 0 });
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        setLoading(true);
        const result = await teacherDiariesAPI.listMine(academicYear);
        if (active) {
          setData(result || { items: [], total: 0, blocked_total: 0 });
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err.response?.data?.detail || 'Não foi possível carregar seus diários por vínculo.');
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    return () => { active = false; };
  }, [academicYear]);

  const diaries = useMemo(() => data?.items || [], [data]);

  // Um único módulo por turma. Os componentes do fluxo legado são a base da
  // lotação do professor; quando existe DVD para o mesmo turma/componente, o
  // vínculo DVD sobrepõe apenas as capacidades/assignment daquele componente.
  const classModules = useMemo(() => {
    const modules = new Map();

    const ensureModule = (classId, seed = {}) => {
      if (!classId) return null;
      if (!modules.has(classId)) {
        modules.set(classId, {
          class_id: classId,
          class_name: seed.class_name || seed.name || 'Turma sem nome',
          school_id: seed.school_id || '',
          school_name: seed.school_name || 'Escola não informada',
          classInfo: { ...seed },
          components: new Map(),
          profiles: new Set(),
        });
      }

      const module = modules.get(classId);
      module.class_name = module.class_name || seed.class_name || seed.name || 'Turma sem nome';
      module.school_id = module.school_id || seed.school_id || '';
      module.school_name = module.school_name || seed.school_name || 'Escola não informada';
      module.classInfo = { ...seed, ...module.classInfo };
      return module;
    };

    legacyClasses.forEach((turma) => {
      const module = ensureModule(turma.id, turma);
      if (!module) return;

      (turma.componentes || []).forEach((component) => {
        if (!component?.id) return;
        const key = String(component.id);
        module.components.set(key, {
          id: component.id,
          name: component.name || 'Componente sem nome',
          academicYear: turma.academic_year || academicYear,
          schoolId: turma.school_id,
          legacyAssignmentId: component.assignment_id || '',
          diary: null,
        });
      });
    });

    diaries.forEach((diary) => {
      const module = ensureModule(diary.class_id, {
        id: diary.class_id,
        name: diary.class_name,
        class_name: diary.class_name,
        school_id: diary.school_id,
        school_name: diary.school_name,
        academic_year: diary.academic_year,
        education_level: diary.education_level,
        grade_level: diary.grade_level,
        shift: diary.shift,
      });
      if (!module) return;

      if (diary.profile) module.profiles.add(diary.profile);

      const key = diary.component_id
        ? String(diary.component_id)
        : `assignment:${diary.assignment_id}`;
      const existing = module.components.get(key);

      module.components.set(key, {
        id: diary.component_id || existing?.id || '',
        name: diary.component_name || existing?.name || 'Regência / vínculo da turma',
        academicYear: diary.academic_year || existing?.academicYear || academicYear,
        schoolId: diary.school_id || existing?.schoolId || module.school_id,
        legacyAssignmentId: existing?.legacyAssignmentId || '',
        diary,
      });
    });

    return Array.from(modules.values())
      .map((module) => ({
        ...module,
        components: Array.from(module.components.values()).sort(sortByComponentName),
        profiles: Array.from(module.profiles),
      }))
      .sort((left, right) => {
        const schoolCompare = (left.school_name || '').localeCompare(right.school_name || '', 'pt-BR');
        return schoolCompare !== 0
          ? schoolCompare
          : (left.class_name || '').localeCompare(right.class_name || '', 'pt-BR');
      });
  }, [academicYear, diaries, legacyClasses]);

  const visibleTotal = classModules.length;

  return (
    <section data-testid="meus-diarios-section" className="space-y-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BookOpen className="text-indigo-600" size={22} />
            Meus Diários
          </h2>
          <p className="text-sm text-slate-500">
            Turmas, componentes e ações do diário organizados em um só lugar — {academicYear}.
          </p>
        </div>
        {!loading && visibleTotal > 0 && (
          <span className="text-sm text-slate-500" data-testid="meus-diarios-total">
            {visibleTotal} turma(s)
          </span>
        )}
      </div>

      {loading && (
        <Card>
          <CardContent className="p-6 text-sm text-slate-500">
            Carregando seus diários...
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="p-4 flex items-start gap-2 text-amber-900">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <span>
              {typeof error === 'string' ? error : 'Não foi possível carregar seus diários por vínculo.'}
              {' '}Suas turmas continuam disponíveis no fluxo autorizado.
            </span>
          </CardContent>
        </Card>
      )}

      {!loading && !error && data.blocked_total > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex items-start gap-2">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span>
            Há {data.blocked_total} vínculo(s) que precisam ser revisado(s) pela coordenação.
          </span>
        </div>
      )}

      {!loading && !error && classModules.length === 0 && (
        <Card>
          <CardContent className="p-6 text-center text-slate-500">
            <BookOpen size={42} className="mx-auto mb-2 text-slate-300" />
            <p className="font-medium text-slate-700">
              Nenhuma turma disponível para {academicYear}.
            </p>
            <p className="mt-1 text-sm">Entre em contato com a coordenação para revisar sua lotação.</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && classModules.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4" data-testid="diarios-compactos">
          {classModules.map((module) => {
            const attendancePerComponent = usesAttendanceByComponent(module.classInfo);
            const topAttendanceComponent = !attendancePerComponent
              ? (
                module.components.find((component) => (
                  component.diary && getComponentOperationalState(component).canAttendance
                ))
                || module.components.find((component) => getComponentOperationalState(component).canAttendance)
              )
              : null;

            const topAttendanceContext = topAttendanceComponent
              ? buildComponentContext(topAttendanceComponent, module, academicYear)
              : null;
            const topAttendanceState = topAttendanceComponent
              ? getComponentOperationalState(topAttendanceComponent)
              : null;

            const profileLabels = module.profiles
              .map((profile) => PROFILE_LABELS[profile] || profile)
              .filter(Boolean);

            return (
              <Card
                key={module.class_id}
                className="border-l-4 border-l-indigo-500"
                data-testid={`diario-group-${module.class_id}`}
              >
                <CardHeader className="px-3 pt-3 pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="text-base sm:text-lg leading-tight">
                        {module.class_name || 'Turma sem nome'}
                      </CardTitle>
                      <CardDescription className="mt-1 flex items-start gap-1 text-xs sm:text-sm">
                        <School size={14} className="mt-0.5 shrink-0" />
                        <span className="whitespace-normal break-words">
                          {module.school_name || 'Escola não informada'}
                        </span>
                      </CardDescription>
                    </div>

                    <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                      {topAttendanceContext && (
                        <Button
                          type="button"
                          size="sm"
                          variant={topAttendanceState?.attendancePurpose === 'pdf_only' ? 'outline' : 'default'}
                          onClick={() => navigate(buildDiaryActionUrl('/professor/frequencia', topAttendanceContext))}
                          className="h-8 px-2.5 text-xs"
                          data-testid={`class-attendance-${module.class_id}`}
                        >
                          <CheckSquare size={14} className="mr-1.5" />
                          Frequência
                        </Button>
                      )}

                      {profileLabels.length === 0 ? (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                          Fluxo atual
                        </span>
                      ) : profileLabels.length === 1 ? (
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                          {profileLabels[0]}
                        </span>
                      ) : (
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                          Misto
                        </span>
                      )}
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="px-3 pt-0 pb-2">
                  <div className="divide-y divide-slate-100">
                    {module.components.map((component) => {
                      const diary = component.diary;
                      const ops = getComponentOperationalState(component);
                      const actionContext = buildComponentContext(component, module, academicYear);

                      return (
                        <div
                          key={diary?.assignment_id || component.id || component.name}
                          className="py-2 first:pt-1 last:pb-1"
                          data-testid={diary?.assignment_id
                            ? `diario-card-${diary.assignment_id}`
                            : `legacy-component-${module.class_id}-${component.id}`}
                        >
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0 flex-1">
                              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                                Componente
                              </span>
                              <p className="whitespace-normal break-words text-sm font-semibold leading-4 text-slate-800">
                                {component.name}
                              </p>
                              {(ops.unresolvedGroup || !ops.sharedGradeOwner) && (
                                <p className="mt-1 text-[11px] leading-4 text-amber-700">
                                  {ops.unresolvedGroup
                                    ? 'Aguardando definição auditável do grupo de estudantes.'
                                    : 'Avaliação aguardando responsável oficial do vínculo compartilhado.'}
                                </p>
                              )}
                            </div>

                            <div className="flex shrink-0 flex-wrap gap-1.5 sm:justify-end">
                              {attendancePerComponent && ops.canAttendance && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={ops.attendancePurpose === 'pdf_only' ? 'outline' : 'default'}
                                  onClick={() => navigate(buildDiaryActionUrl('/professor/frequencia', actionContext))}
                                  className="h-8 px-2 text-xs"
                                  data-testid={`component-attendance-${module.class_id}-${component.id}`}
                                >
                                  <CheckSquare size={14} className="mr-1.5" />
                                  Frequência
                                </Button>
                              )}

                              {(diary?.capabilities?.grades_enabled !== false || !diary) && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  disabled={!ops.canGrades}
                                  onClick={() => navigate(buildDiaryActionUrl('/professor/notas', actionContext))}
                                  className="h-8 px-2 text-xs"
                                  data-testid={diary
                                    ? `open-grades-${diary.assignment_id}`
                                    : `legacy-grades-${module.class_id}-${component.id}`}
                                >
                                  <ClipboardList size={14} className="mr-1.5" />
                                  Notas / Conceitos
                                </Button>
                              )}

                              {ops.canContent && diary && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  onClick={() => navigate(buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext))}
                                  className="h-8 px-2 text-xs"
                                  data-testid={`open-content-${diary.assignment_id}`}
                                >
                                  <BookOpen size={14} className="mr-1.5" />
                                  Conteúdos
                                </Button>
                              )}

                              {ops.canContent && !diary && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  onClick={() => navigate(buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext))}
                                  className="h-8 px-2 text-xs"
                                  data-testid={`legacy-content-${module.class_id}-${component.id}`}
                                >
                                  <BookOpen size={14} className="mr-1.5" />
                                  Conteúdos
                                </Button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}
