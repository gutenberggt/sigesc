import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, CheckSquare, ClipboardList, School, Users, AlertTriangle, GraduationCap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { teacherDiariesAPI } from '../../services/teacherDiaries';
import { buildDiaryActionUrl } from '../../utils/diaryPrefill';

const PROFILE_LABELS = {
  regular: 'Regular',
  integrator: 'Componente integrador',
  shared: 'Compartilhado',
};

const legacyStudentsRoute = (classId) => `/professor/turma/${classId}/alunos`; // nomenclature-allow: rota técnica legada

const sortByComponent = (left, right) => (
  (left?.component_name || '').localeCompare(right?.component_name || '', 'pt-BR')
);

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
  const diaryGroups = useMemo(() => {
    const groups = new Map();
    diaries.forEach((diary) => {
      const key = [diary.class_id || 'sem-turma', diary.school_id || 'sem-escola', diary.profile || 'regular'].join('|');
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          class_id: diary.class_id,
          class_name: diary.class_name,
          school_id: diary.school_id,
          school_name: diary.school_name,
          profile: diary.profile,
          diaries: [],
        });
      }
      groups.get(key).diaries.push(diary);
    });
    return Array.from(groups.values())
      .map((group) => ({ ...group, diaries: [...group.diaries].sort(sortByComponent) }))
      .sort((left, right) => {
        const schoolCompare = (left.school_name || '').localeCompare(right.school_name || '', 'pt-BR');
        if (schoolCompare !== 0) return schoolCompare;
        return (left.class_name || '').localeCompare(right.class_name || '', 'pt-BR');
      });
  }, [diaries]);

  const diaryClassIds = useMemo(
    () => new Set(diaries.map((diary) => diary.class_id).filter(Boolean)),
    [diaries]
  );
  const legacyFallbackClasses = useMemo(
    () => (legacyClasses || []).filter((turma) => !diaryClassIds.has(turma.id)),
    [legacyClasses, diaryClassIds]
  );
  const visibleTotal = diaryGroups.length + legacyFallbackClasses.length;

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
          <CardContent className="p-6 text-sm text-slate-500">Carregando seus diários...</CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="p-4 flex items-start gap-2 text-amber-900">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <span>
              {typeof error === 'string' ? error : 'Não foi possível carregar seus diários por vínculo.'}
              {' '}Suas turmas continuam disponíveis abaixo no fluxo atual.
            </span>
          </CardContent>
        </Card>
      )}

      {!loading && !error && data.blocked_total > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex items-start gap-2">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span>
            Há {data.blocked_total} vínculo(s) que precisam ser revisado(s) pela coordenação. A turma correspondente permanece disponível no fluxo atual quando aplicável.
          </span>
        </div>
      )}

      {!loading && !error && diaries.length === 0 && legacyFallbackClasses.length === 0 && (
        <Card>
          <CardContent className="p-6 text-center text-slate-500">
            <BookOpen size={42} className="mx-auto mb-2 text-slate-300" />
            <p className="font-medium text-slate-700">Nenhuma turma ou Diário por Vínculo disponível para {academicYear}.</p>
            <p className="mt-1 text-sm">Entre em contato com a coordenação para revisar sua lotação.</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && diaryGroups.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4" data-testid="diarios-compactos">
          {diaryGroups.map((group) => (
            <Card
              key={group.key}
              className="border-l-4 border-l-indigo-500"
              data-testid={`diario-group-${group.class_id}-${group.profile || 'regular'}`}
            >
              <CardHeader className="pt-4 pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="text-lg">{group.class_name || 'Turma sem nome'}</CardTitle>
                    <CardDescription className="mt-1 flex items-center gap-1 text-xs sm:text-sm">
                      <School size={14} className="shrink-0" />
                      <span className="truncate">{group.school_name || 'Escola não informada'}</span>
                    </CardDescription>
                  </div>
                  <span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                    {PROFILE_LABELS[group.profile] || group.profile}
                  </span>
                </div>
              </CardHeader>

              <CardContent className="pt-0 pb-3 space-y-3">
                <div className="divide-y divide-slate-100">
                  {group.diaries.map((diary) => {
                    const caps = diary.capabilities || {};
                    const unresolvedGroup = diary.profile === 'shared' && diary.student_scope === 'group';
                    const sharedGradeOwner = diary.profile !== 'shared' || diary.grades_official_owner === true;
                    const gradesOperational = !!caps.grades_enabled && !unresolvedGroup && sharedGradeOwner;
                    const actionContext = {
                      academicYear: diary.academic_year || academicYear,
                      schoolId: diary.school_id,
                      classId: diary.class_id,
                      courseId: diary.component_id,
                      assignmentId: diary.assignment_id,
                    };
                    return (
                      <div key={diary.assignment_id} className="py-3 first:pt-1 last:pb-1" data-testid={`diario-card-${diary.assignment_id}`}>
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                          <div className="min-w-0 lg:max-w-[42%]">
                            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Componente</span>
                            <p className="text-sm font-semibold text-slate-800 truncate" title={diary.component_name || ''}>
                              {diary.component_name || 'Regência / vínculo da turma'}
                            </p>
                            {(unresolvedGroup || !sharedGradeOwner) && (
                              <p className="mt-1 text-[11px] leading-4 text-amber-700">
                                {unresolvedGroup
                                  ? 'Aguardando definição auditável do grupo de estudantes.'
                                  : 'Avaliação aguardando responsável oficial do vínculo compartilhado.'}
                              </p>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-2 lg:justify-end">
                            {caps.attendance_enabled && (
                              <Button
                                type="button"
                                size="sm"
                                variant={caps.attendance_purpose === 'pdf_only' ? 'outline' : 'default'}
                                disabled={unresolvedGroup}
                                onClick={() => navigate(buildDiaryActionUrl('/professor/frequencia', actionContext))}
                                className="h-8 px-2.5 text-xs"
                                data-testid={`open-attendance-${diary.assignment_id}`}
                              >
                                <CheckSquare size={14} className="mr-1.5" />
                                {unresolvedGroup
                                  ? 'Frequência aguardando grupo'
                                  : caps.attendance_purpose === 'pdf_only'
                                    ? 'Registro documental'
                                    : 'Frequência'}
                              </Button>
                            )}
                            {caps.grades_enabled && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                disabled={!gradesOperational}
                                onClick={() => navigate(buildDiaryActionUrl('/professor/notas', actionContext))}
                                className="h-8 px-2.5 text-xs"
                                data-testid={`open-grades-${diary.assignment_id}`}
                              >
                                <ClipboardList size={14} className="mr-1.5" />
                                {unresolvedGroup
                                  ? 'Avaliação aguardando grupo'
                                  : !sharedGradeOwner
                                    ? 'Avaliação aguardando responsável'
                                    : 'Notas / Conceitos'}
                              </Button>
                            )}
                            {caps.content_enabled && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() => navigate(buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext))}
                                className="h-8 px-2.5 text-xs"
                                data-testid={`open-content-${diary.assignment_id}`}
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

                <div className="flex flex-col gap-2 border-t border-slate-100 pt-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-[11px] leading-4 text-slate-500">
                    Frequência, Notas/Conceitos e Conteúdos abrem com o vínculo, a turma e o componente já definidos.
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(legacyStudentsRoute(group.class_id))}
                    className="h-8 shrink-0 px-2.5 text-xs"
                    data-testid={`open-students-${group.class_id}`}
                  >
                    <Users size={14} className="mr-1.5" />
                    Estudantes
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!loading && legacyFallbackClasses.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4" data-testid="turmas-fluxo-atual">
          {legacyFallbackClasses.map((turma) => (
            <Card key={turma.id} className="border-l-4 border-l-slate-300">
              <CardHeader className="pt-4 pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <GraduationCap className="text-blue-600 shrink-0" size={18} />
                      <span className="truncate">{turma.name}</span>
                    </CardTitle>
                    <CardDescription className="mt-1 flex items-center gap-1 text-xs sm:text-sm">
                      <School size={14} className="shrink-0" />
                      <span className="truncate">{turma.school_name}</span>
                    </CardDescription>
                  </div>
                  <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                    Fluxo atual
                  </span>
                </div>
              </CardHeader>
              <CardContent className="pt-0 pb-3 space-y-3">
                <div className="divide-y divide-slate-100">
                  {(turma.componentes || []).map((comp) => {
                    const actionContext = {
                      academicYear: turma.academic_year || academicYear,
                      schoolId: turma.school_id,
                      classId: turma.id,
                      courseId: comp.id,
                    };
                    return (
                      <div key={comp.id} className="py-3 first:pt-1 last:pb-1">
                        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                          <div className="min-w-0 lg:max-w-[42%]">
                            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Componente</span>
                            <p className="text-sm font-semibold text-slate-800 truncate" title={comp.name || ''}>{comp.name}</p>
                          </div>
                          <div className="flex flex-wrap gap-2 lg:justify-end">
                            <Button variant="outline" size="sm" onClick={() => navigate(buildDiaryActionUrl('/professor/frequencia', actionContext))} className="h-8 px-2.5 text-xs" data-testid={`legacy-attendance-${turma.id}-${comp.id}`}>
                              <CheckSquare size={14} className="mr-1.5" />
                              Frequência
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => navigate(buildDiaryActionUrl('/professor/notas', actionContext))} className="h-8 px-2.5 text-xs" data-testid={`legacy-grades-${turma.id}-${comp.id}`}>
                              <ClipboardList size={14} className="mr-1.5" />
                              Notas / Conceitos
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => navigate(buildDiaryActionUrl('/professor/objetos-conhecimento', actionContext))} className="h-8 px-2.5 text-xs" data-testid={`legacy-content-${turma.id}-${comp.id}`}>
                              <BookOpen size={14} className="mr-1.5" />
                              Conteúdos
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {(!turma.componentes || turma.componentes.length === 0) && (
                    <span className="block py-2 text-xs text-slate-500">Nenhum componente informado para criar atalhos diretos.</span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
                  <Button variant="outline" size="sm" onClick={() => navigate(`/professor/turma/${turma.id}/diario`)} className="h-8 px-2.5 text-xs">
                    <ClipboardList size={14} className="mr-1.5" />
                    Diário
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => navigate(legacyStudentsRoute(turma.id))} className="h-8 px-2.5 text-xs">
                    <Users size={14} className="mr-1.5" />
                    Estudantes
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!loading && visibleTotal > 0 && (
        <p className="text-xs text-slate-500">
          “Fluxo atual” identifica turmas que ainda não possuem um Diário por Vínculo ativo ou que permanecem fora do escopo atual do DVD. Os atalhos usam somente filtros já autorizados ao professor.
        </p>
      )}
    </section>
  );
}
