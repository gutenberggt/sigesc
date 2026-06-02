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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';

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
  }, [fetchAudit]);

  const ownerName = (id) => (data?.owner_names && data.owner_names[id]) || id;

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
              Painel somente leitura. Acompanhe matrículas ausentes e duplicadas em tempo real.
            </p>
          </div>
          <Button onClick={fetchAudit} disabled={loading} data-testid="refresh-audit-button">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
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
          </>
        ) : null}
      </div>
    </Layout>
  );
};

export default EnrollmentAudit;
