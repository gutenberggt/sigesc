import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Search } from 'lucide-react';

import { studentsAPI } from '@/services/api';

const AUDIT_ROLES = new Set([
  'super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3',
]);

const ISSUE_LABELS = {
  traditional_value_in_color_race: 'Comunidade tradicional registrada em Cor/Raça',
  traditional_dimensions_conflict: 'Conflito entre Cor/Raça e Comunidade Tradicional',
  traditional_community_needs_confirmation: 'Comunidade tradicional precisa ser confirmada',
  unsupported_color_race: 'Valor de Cor/Raça fora do domínio canônico',
  unsupported_traditional_community: 'Comunidade Tradicional fora do domínio canônico',
};

const humanize = value => {
  if (!value) return 'Não informado';
  return String(value).replaceAll('_', ' ');
};

export function StudentDemographicAuditPanel({ user, onReviewStudent }) {
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);

  const canAudit = useMemo(() => {
    const roles = [user?.role, ...(Array.isArray(user?.roles) ? user.roles : [])].filter(Boolean);
    return roles.some(role => AUDIT_ROLES.has(role));
  }, [user]);

  if (!canAudit) return null;

  const loadAudit = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await studentsAPI.getRaceCommunityAudit();
      setAudit(result);
      setExpanded(true);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Não foi possível executar a auditoria demográfica.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="mt-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-700" />
            <h3 className="text-sm font-semibold text-gray-900">Auditoria Raça/Cor × Comunidade Tradicional</h3>
          </div>
          <p className="mt-1 text-xs text-gray-600">
            Revisão assistida de registros legados. O SIGESC não infere raça/cor a partir da comunidade tradicional.
          </p>
        </div>
        <button
          type="button"
          onClick={loadAudit}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          {audit ? 'Atualizar auditoria' : 'Executar auditoria'}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

      {audit && (
        <div className="mt-4">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-white px-3 py-1.5 text-gray-700 border border-gray-200">
              Analisados: {audit.total_scanned || 0}
            </span>
            <span className={`rounded-full px-3 py-1.5 border ${audit.needs_review_total > 0 ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-green-50 text-green-700 border-green-200'}`}>
              Pendentes de revisão: {audit.needs_review_total || 0}
            </span>
            {audit.migration_ready && (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-3 py-1.5 text-green-700 border border-green-200">
                <CheckCircle2 size={14} /> Domínio legado regularizado
              </span>
            )}
          </div>

          {(audit.samples || []).length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setExpanded(value => !value)}
                className="mt-3 text-xs font-medium text-amber-800 underline"
              >
                {expanded ? 'Ocultar registros pendentes' : 'Exibir registros pendentes'}
              </button>

              {expanded && (
                <div className="mt-3 overflow-x-auto rounded-xl border border-amber-200 bg-white">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Estudante</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Cor/Raça atual</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Comunidade atual</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-600">Pendência</th>
                        <th className="px-3 py-2 text-right font-medium text-gray-600">Ação</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {(audit.samples || []).map(sample => (
                        <tr key={sample.id}>
                          <td className="px-3 py-2 font-medium text-gray-900">{sample.full_name || sample.id}</td>
                          <td className="px-3 py-2 text-gray-700 capitalize">{humanize(sample.color_race)}</td>
                          <td className="px-3 py-2 text-gray-700 capitalize">{humanize(sample.comunidade_tradicional)}</td>
                          <td className="px-3 py-2 text-gray-600">
                            {(sample.issues || []).map(issue => ISSUE_LABELS[issue] || issue).join('; ')}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <button
                              type="button"
                              onClick={() => onReviewStudent?.({ id: sample.id })}
                              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50"
                            >
                              <Search size={14} /> Revisar cadastro
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {(audit.needs_review_total || 0) > (audit.samples || []).length && (
                <p className="mt-2 text-xs text-gray-500">
                  A amostra exibe até {audit.sample_limit || 100} registros por execução. Corrija os exibidos e execute a auditoria novamente para continuar.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
