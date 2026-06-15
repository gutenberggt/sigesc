import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import {
  ClipboardCheck,
  RefreshCw,
  AlertTriangle,
  Copy,
  FileWarning,
  ShieldCheck,
  ShieldAlert,
  Home,
  Users,
  BookOpen,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { studentsAPI } from '@/services/api';
import { toast } from 'sonner';

const API = process.env.REACT_APP_BACKEND_URL;

const StatCard = ({ icon: Icon, label, value, tone, testId }) => {
  const tones = {
    danger: 'border-red-200 bg-red-50 text-red-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
    neutral: 'border-slate-200 bg-white text-slate-700',
  };
  return (
    <Card className={`border ${tones[tone] || tones.neutral}`} data-testid={testId}>
      <CardContent className="p-5 flex items-center gap-4">
        <div className="p-3 rounded-xl bg-white/70 border border-current/10">
          <Icon className="w-6 h-6" />
        </div>
        <div>
          <p className="text-3xl font-bold leading-none" data-testid={`${testId}-value`}>{value}</p>
          <p className="text-sm font-medium mt-1 opacity-80">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
};

export const EnrollmentAudit = () => {
  const navigate = useNavigate();
  const { accessToken: token } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [repairing, setRepairing] = useState(false);
  const [seriesData, setSeriesData] = useState(null);
  const [seriesRepairing, setSeriesRepairing] = useState(false);

  const fetchSeriesAudit = useCallback(async () => {
    try {
      const res = await studentsAPI.auditSeriesSync();
      setSeriesData(res);
    } catch {
      setSeriesData(null);
    }
  }, []);

  const fetchAudit = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API}/api/students/enrollment-audit`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        throw new Error(`Falha ao carregar auditoria (HTTP ${res.status})`);
      }
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchAudit();
    fetchSeriesAudit();
  }, [fetchAudit, fetchSeriesAudit]);

  const runRepair = useCallback(async () => {
    try {
      setRepairing(true);
      const res = await studentsAPI.repairEnrollment();
      const total = (res.fixed_students || 0) + (res.fixed_enrollments || 0);
      if (total === 0) {
        toast.success('Tudo certo! Nenhuma matrícula sem número encontrada.');
      } else {
        toast.success(
          `Correção concluída: ${res.fixed_students} aluno(s) e ${res.fixed_enrollments} matrícula(s) numerados` +
          (res.created_enrollments ? `, ${res.created_enrollments} matrícula(s) criada(s).` : '.')
        );
      }
      await fetchAudit();
    } catch (e) {
      toast.error(
        e?.response?.data?.detail || 'Não foi possível corrigir as matrículas. Tente novamente.'
      );
    } finally {
      setRepairing(false);
    }
  }, [fetchAudit]);

  const ownerName = (id) => (data?.owner_names && data.owner_names[id]) || id;

  const runSeriesRepair = useCallback(async () => {
    try {
      setSeriesRepairing(true);
      const res = await studentsAPI.repairSeriesSync();
      if ((res.fixed_enrollments || 0) === 0) {
        toast.success('Tudo certo! Nenhuma matrícula precisava de sincronização de série.');
      } else {
        toast.success(`Sincronização concluída: ${res.fixed_enrollments} matrícula(s) tiveram a série preenchida a partir do cadastro.`);
      }
      await fetchSeriesAudit();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Não foi possível sincronizar as séries. Tente novamente.');
    } finally {
      setSeriesRepairing(false);
    }
  }, [fetchSeriesAudit]);

  const renderDuplicates = (collName, label, Icon) => {
    const block = data?.[collName];
    if (!block) return null;
    return (
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden" data-testid={`dup-table-${collName}`}>
        <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
          <Icon className="w-4 h-4 text-slate-500" />
          <h3 className="text-base font-semibold text-slate-800">
            Duplicatas — {label}
          </h3>
          <Badge variant="outline" className="ml-2">{block.duplicate_groups}</Badge>
        </div>
        {block.duplicates.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-500">Nenhuma matrícula duplicada. 🎉</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-5 py-2 font-medium">Matrícula</th>
                  <th className="text-left px-5 py-2 font-medium">Qtd.</th>
                  <th className="text-left px-5 py-2 font-medium">Alunos envolvidos</th>
                </tr>
              </thead>
              <tbody>
                {block.duplicates.map((d) => (
                  <tr key={d.enrollment_number} className="border-t border-slate-100">
                    <td className="px-5 py-2 font-mono font-semibold text-slate-800">{d.enrollment_number}</td>
                    <td className="px-5 py-2">
                      <Badge className="bg-red-100 text-red-700 hover:bg-red-100">{d.count}</Badge>
                    </td>
                    <td className="px-5 py-2 text-slate-600">
                      {d.owners.map((o) => ownerName(o)).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  return (
    <Layout>
      <div className="space-y-6" data-testid="enrollment-audit-page">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
              data-testid="back-dashboard-button"
            >
              <Home className="w-4 h-4" /> Início
            </button>
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-2">
              <ClipboardCheck className="w-7 h-7 text-blue-600" />
              Auditoria de Matrículas
            </h1>
            <p className="text-slate-500 mt-1 text-sm">
              Acompanhe matrículas ausentes e duplicadas em tempo real. Use “Corrigir” para numerar automaticamente alunos sem matrícula.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {seriesData && seriesData.total_to_fix > 0 && (
              <Button
                onClick={runSeriesRepair}
                disabled={seriesRepairing || loading}
                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                data-testid="repair-series-sync-button"
              >
                <Wrench className={`w-4 h-4 mr-2 ${seriesRepairing ? 'animate-spin' : ''}`} />
                {seriesRepairing ? 'Sincronizando...' : `Sincronizar séries (${seriesData.total_to_fix})`}
              </Button>
            )}
            {data && (data.students.empty > 0 || data.enrollments.empty > 0) && (
              <Button
                onClick={runRepair}
                disabled={repairing || loading}
                className="bg-amber-600 hover:bg-amber-700 text-white"
                data-testid="repair-enrollment-button"
              >
                <Wrench className={`w-4 h-4 mr-2 ${repairing ? 'animate-spin' : ''}`} />
                {repairing ? 'Corrigindo...' : 'Corrigir matrículas sem número'}
              </Button>
            )}
            <Button onClick={() => { fetchAudit(); fetchSeriesAudit(); }} disabled={loading} variant="outline" data-testid="refresh-audit-button">
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700" data-testid="audit-error">
            <AlertTriangle className="w-5 h-5" /> {error}
          </div>
        )}

        {loading && !data ? (
          <div className="flex items-center justify-center py-20 text-slate-400" data-testid="audit-loading">
            <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Carregando auditoria...
          </div>
        ) : data ? (
          <>
            {/* Status do índice único */}
            <div
              className={`flex items-center gap-3 p-4 rounded-lg border ${
                data.unique_index.students && data.unique_index.enrollments
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-amber-50 border-amber-200 text-amber-700'
              }`}
              data-testid="unique-index-status"
            >
              {data.unique_index.students && data.unique_index.enrollments ? (
                <ShieldCheck className="w-5 h-5" />
              ) : (
                <ShieldAlert className="w-5 h-5" />
              )}
              <span className="text-sm font-medium">
                Índice único de matrícula:{' '}
                {data.unique_index.students && data.unique_index.enrollments
                  ? 'ATIVO em alunos e matrículas — duplicatas bloqueadas pelo banco.'
                  : 'NÃO aplicado em todas as coleções. Recomenda-se rodar o saneamento.'}
              </span>
            </div>

            {/* Cards resumo */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                icon={FileWarning}
                label="Alunos sem matrícula"
                value={data.students.empty}
                tone={data.students.empty > 0 ? 'danger' : 'neutral'}
                testId="stat-students-empty"
              />
              <StatCard
                icon={Copy}
                label="Matrículas de aluno duplicadas"
                value={data.students.duplicate_groups}
                tone={data.students.duplicate_groups > 0 ? 'danger' : 'neutral'}
                testId="stat-students-dup"
              />
              <StatCard
                icon={FileWarning}
                label="Registros de matrícula sem número"
                value={data.enrollments.empty}
                tone={data.enrollments.empty > 0 ? 'warning' : 'neutral'}
                testId="stat-enrollments-empty"
              />
              <StatCard
                icon={Copy}
                label="Números de matrícula duplicados"
                value={data.enrollments.duplicate_groups}
                tone={data.enrollments.duplicate_groups > 0 ? 'warning' : 'neutral'}
                testId="stat-enrollments-dup"
              />
            </div>

            {/* Duplicatas */}
            <div className="grid grid-cols-1 gap-6">
              {renderDuplicates('enrollments', 'Matrículas (por ano/turma)', BookOpen)}
              {renderDuplicates('students', 'Alunos', Users)}
            </div>

            {/* Alunos sem matrícula */}
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden" data-testid="empty-students-table">
              <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
                <FileWarning className="w-4 h-4 text-slate-500" />
                <h3 className="text-base font-semibold text-slate-800">Alunos sem número de matrícula</h3>
                <Badge variant="outline" className="ml-2">{data.students.empty}</Badge>
              </div>
              {(data.students.empty_sample || []).length === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">Todos os alunos possuem matrícula. 🎉</p>
              ) : (
                <div className="overflow-x-auto max-h-96 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-slate-500 text-xs uppercase sticky top-0">
                      <tr>
                        <th className="text-left px-5 py-2 font-medium">Aluno</th>
                        <th className="text-left px-5 py-2 font-medium">ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.students.empty_sample.map((s) => (
                        <tr key={s.id} className="border-t border-slate-100">
                          <td className="px-5 py-2 text-slate-800">{s.full_name || '—'}</td>
                          <td className="px-5 py-2 font-mono text-xs text-slate-400">{s.id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {data.students.empty > (data.students.empty_sample || []).length && (
                    <p className="px-5 py-3 text-xs text-slate-400">
                      Exibindo {data.students.empty_sample.length} de {data.students.empty}.
                    </p>
                  )}
                </div>
              )}
            </div>
            {/* Sincronização de série matrícula ↔ cadastro (turmas multisseriadas) */}
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden" data-testid="series-sync-table">
              <div className="px-5 py-3 border-b border-slate-100 flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-slate-500" />
                <h3 className="text-base font-semibold text-slate-800">Matrículas sem série (corrigíveis pelo cadastro)</h3>
                <Badge variant="outline" className="ml-2">{seriesData?.total_to_fix || 0}</Badge>
              </div>
              {!seriesData || (seriesData.total_to_fix || 0) === 0 ? (
                <p className="px-5 py-6 text-sm text-slate-500">Todas as matrículas com aluno classificado já têm série. 🎉</p>
              ) : (
                <>
                  <p className="px-5 pt-3 text-xs text-slate-500">
                    Estes alunos têm a série salva no cadastro, mas a matrícula está sem série — por isso somem dos diários/PDFs por etapa. Clique em “Sincronizar séries” para copiar a série do cadastro para a matrícula.
                  </p>
                  <div className="overflow-x-auto max-h-96 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 text-slate-500 text-xs uppercase sticky top-0">
                        <tr>
                          <th className="text-left px-5 py-2 font-medium">Aluno</th>
                          <th className="text-left px-5 py-2 font-medium">Turma</th>
                          <th className="text-left px-5 py-2 font-medium">Série (cadastro)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(seriesData.sample || []).map((s) => (
                          <tr key={s.student_id} className="border-t border-slate-100">
                            <td className="px-5 py-2 text-slate-800">{s.full_name || '—'}</td>
                            <td className="px-5 py-2 text-slate-600">{s.class_name || '—'}</td>
                            <td className="px-5 py-2">
                              <Badge className="bg-indigo-100 text-indigo-700 hover:bg-indigo-100">{s.target_series}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {seriesData.total_to_fix > (seriesData.sample || []).length && (
                      <p className="px-5 py-3 text-xs text-slate-400">
                        Exibindo {seriesData.sample.length} de {seriesData.total_to_fix}.
                      </p>
                    )}
                  </div>
                </>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Layout>
  );
};

export default EnrollmentAudit;
