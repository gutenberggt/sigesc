import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, CheckSquare, ClipboardList, School, Users, AlertTriangle, GraduationCap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Button } from '../ui/button';
import { teacherDiariesAPI } from '../../services/teacherDiaries';

const PROFILE_LABELS = {
  regular: 'Regular',
  integrator: 'Componente integrador',
  shared: 'Compartilhado',
};

const legacyStudentsRoute = (classId) => `/professor/turma/${classId}/alunos`; // nomenclature-allow: rota técnica legada

function Capability({ icon: Icon, label, enabled, detail }) {
  return (
    <div className={`rounded-lg border p-3 ${enabled ? 'bg-white' : 'bg-gray-50 opacity-70'}`}>
      <div className="flex items-center gap-2">
        <Icon size={17} className={enabled ? 'text-slate-700' : 'text-slate-400'} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}

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
  const diaryClassIds = useMemo(
    () => new Set(diaries.map((diary) => diary.class_id).filter(Boolean)),
    [diaries]
  );
  const legacyFallbackClasses = useMemo(
    () => (legacyClasses || []).filter((turma) => !diaryClassIds.has(turma.id)),
    [legacyClasses, diaryClassIds]
  );
  const visibleTotal = diaries.length + legacyFallbackClasses.length;

  return (
    <section data-testid="meus-diarios-section" className="space-y-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BookOpen className="text-indigo-600" size={22} />
            Meus Diários
          </h2>
          <p className="text-sm text-slate-500">
            Turmas e vínculos docentes organizados em um só lugar — {academicYear}.
          </p>
        </div>
        {!loading && visibleTotal > 0 && (
          <span className="text-sm text-slate-500" data-testid="meus-diarios-total">
            {visibleTotal} turma(s) / diário(s)
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

      {!loading && !error && diaries.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {diaries.map((diary) => {
            const caps = diary.capabilities || {};
            const unresolvedGroup = diary.profile === 'shared' && diary.student_scope === 'group';
            const sharedGradeOwner = diary.profile !== 'shared' || diary.grades_official_owner === true;
            const gradesOperational = !!caps.grades_enabled && !unresolvedGroup && sharedGradeOwner;
            const attendanceDetail = !caps.attendance_enabled
              ? 'Não se aplica a este vínculo.'
              : unresolvedGroup
                ? 'Aguarda a definição auditável dos estudantes do grupo antes do lançamento.'
                : caps.attendance_purpose === 'pdf_only'
                  ? 'Operacional: registro opcional, documental e exclusivo deste diário; não produz efeitos oficiais.'
                  : 'Operacional por vínculo docente.';
            const gradesDetail = !caps.grades_enabled
              ? 'Não se aplica a este vínculo.'
              : unresolvedGroup
                ? 'Aguarda a definição auditável dos estudantes do grupo antes do lançamento.'
                : !sharedGradeOwner
                  ? 'A coordenação deve definir qual vínculo shared é o responsável oficial pela avaliação.'
                  : diary.profile === 'shared'
                    ? 'Este vínculo é o responsável oficial pela avaliação compartilhada.'
                    : 'Operacional com autoria por vínculo e por período avaliativo.';

            return (
              <Card key={diary.assignment_id} className="border-l-4 border-l-indigo-500" data-testid={`diario-card-${diary.assignment_id}`}>
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-lg">{diary.class_name || 'Turma sem nome'}</CardTitle>
                      <CardDescription className="mt-1 flex items-center gap-1">
                        <School size={14} />
                        {diary.school_name || 'Escola não informada'}
                      </CardDescription>
                    </div>
                    <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                      {PROFILE_LABELS[diary.profile] || diary.profile}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-slate-500">Componente</span>
                      <p className="font-medium">{diary.component_name || 'Regência / vínculo da turma'}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Vigência</span>
                      <p className="font-medium">{diary.valid_from} a {diary.valid_until || 'sem data final'}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <Capability
                      icon={BookOpen}
                      label="Conteúdos"
                      enabled={!!caps.content_enabled}
                      detail={caps.content_enabled
                        ? 'Disponível neste perfil; a abertura pela nova organização será habilitada quando a tela atual estiver harmonizada.'
                        : 'Não se aplica a este vínculo.'}
                    />
                    <Capability
                      icon={CheckSquare}
                      label="Frequência"
                      enabled={!!caps.attendance_enabled && !unresolvedGroup}
                      detail={attendanceDetail}
                    />
                    <Capability
                      icon={ClipboardList}
                      label="Avaliação"
                      enabled={gradesOperational}
                      detail={gradesDetail}
                    />
                  </div>

                  {diary.student_scope === 'group' && (
                    <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600 flex items-center gap-2">
                      <Users size={15} />
                      {unresolvedGroup
                        ? 'Vínculo compartilhado por grupo: lançamento bloqueado até existir uma lista canônica e auditável de membros.'
                        : 'Vínculo compartilhado com grupo específico de estudantes.'}
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {caps.attendance_enabled && (
                      <Button
                        type="button"
                        size="sm"
                        variant={caps.attendance_purpose === 'pdf_only' ? 'outline' : 'default'}
                        disabled={unresolvedGroup}
                        onClick={() => navigate(`/professor/frequencia?assignment_id=${encodeURIComponent(diary.assignment_id)}`)}
                        data-testid={`open-attendance-${diary.assignment_id}`}
                      >
                        <CheckSquare size={16} className="mr-2" />
                        {unresolvedGroup
                          ? 'Frequência aguardando grupo'
                          : caps.attendance_purpose === 'pdf_only'
                            ? 'Abrir registro documental'
                            : 'Abrir Frequência'}
                      </Button>
                    )}
                    {caps.grades_enabled && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={!gradesOperational}
                        onClick={() => navigate(`/professor/notas?assignment_id=${encodeURIComponent(diary.assignment_id)}`)}
                        data-testid={`open-grades-${diary.assignment_id}`}
                      >
                        <ClipboardList size={16} className="mr-2" />
                        {unresolvedGroup
                          ? 'Avaliação aguardando grupo'
                          : !sharedGradeOwner
                            ? 'Avaliação aguardando responsável'
                            : 'Abrir Avaliação'}
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(legacyStudentsRoute(diary.class_id))}
                      data-testid={`open-students-${diary.assignment_id}`}
                    >
                      <Users size={16} className="mr-2" />
                      Estudantes
                    </Button>
                  </div>

                  <div className="rounded-md border border-dashed px-3 py-2 text-xs text-slate-500">
                    Frequência e Avaliação usam autoria por vínculo docente. Conteúdos será habilitado quando a tela atual estiver harmonizada com o backend canônico.
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {!loading && legacyFallbackClasses.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="turmas-fluxo-atual">
          {legacyFallbackClasses.map((turma) => (
            <Card key={turma.id} className="hover:shadow-lg transition-shadow border-l-4 border-l-slate-300">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <GraduationCap className="text-blue-600" size={20} />
                      {turma.name}
                    </CardTitle>
                    <CardDescription className="mt-1 flex items-center gap-1">
                      <School size={14} />
                      {turma.school_name}
                    </CardDescription>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 whitespace-nowrap">
                    Fluxo atual
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 mb-4">
                  <p className="text-sm font-medium text-gray-700">Componentes:</p>
                  <div className="flex flex-wrap gap-1">
                    {(turma.componentes || []).map((comp) => (
                      <span
                        key={comp.id}
                        className="bg-purple-100 text-purple-700 text-xs px-2 py-1 rounded-full"
                      >
                        {comp.name}
                      </span>
                    ))}
                    {(!turma.componentes || turma.componentes.length === 0) && (
                      <span className="text-xs text-slate-500">Nenhum componente informado</span>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/professor/turma/${turma.id}/diario`)}
                    className="flex items-center gap-1"
                  >
                    <ClipboardList size={14} />
                    Diário
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(legacyStudentsRoute(turma.id))}
                    className="flex items-center gap-1"
                  >
                    <Users size={14} />
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
          “Fluxo atual” identifica turmas que ainda não possuem um Diário por Vínculo ativo ou que permanecem fora do escopo atual do DVD.
        </p>
      )}
    </section>
  );
}
