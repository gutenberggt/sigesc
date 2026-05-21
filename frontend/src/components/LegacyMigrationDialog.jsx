/**
 * LegacyMigrationDialog — Modal para preview + apply da migração legacy → MEC
 *
 * Fluxo:
 *   1) GET /migrate-legacy/preview → mostra distribuição + amostras
 *   2) Usuário escolhe confidence_min + include_fallback
 *   3) POST /migrate-legacy/apply → executa, mostra resultado
 *   4) Refresh do dashboard pai
 */
import { useEffect, useState } from 'react';
import { Loader2, X, ListChecks, AlertTriangle, CheckCircle2 } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function LegacyMigrationDialog({ open, onClose, onApplied, academicYear }) {
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);

  const [confidenceMin, setConfidenceMin] = useState(0.85);
  const [includeFallback, setIncludeFallback] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState(null);

  const token = localStorage.getItem('accessToken');
  const headers = { Authorization: `Bearer ${token}` };

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setApplyResult(null);
    axios.get(`${API}/bolsa-familia/migrate-legacy/preview?academic_year=${academicYear}`, { headers })
      .then(r => setPreview(r.data))
      .catch(e => setError(e?.response?.data?.detail || 'Falha ao carregar preview'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line
  }, [open, academicYear]);

  const handleApply = async () => {
    setApplying(true);
    try {
      const params = new URLSearchParams({
        academic_year: String(academicYear),
        confidence_min: String(confidenceMin),
        include_fallback: String(includeFallback),
      });
      const res = await axios.post(
        `${API}/bolsa-familia/migrate-legacy/apply?${params.toString()}`,
        {},
        { headers },
      );
      setApplyResult(res.data);
      onApplied?.();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Falha ao aplicar migração');
    } finally {
      setApplying(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" data-testid="legacy-migration-dialog">
      <div className="bg-white rounded-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="px-5 py-3 border-b flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 flex items-center gap-2">
            <ListChecks size={18} /> Reclassificar Motivos Legados → MEC v4.2
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded" data-testid="legacy-close">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto p-5 space-y-4">
          {loading && (
            <div className="flex items-center justify-center py-10 text-gray-500">
              <Loader2 size={20} className="animate-spin mr-2" /> Analisando registros legados...
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-800 p-3 rounded text-sm">{error}</div>
          )}

          {preview && !loading && (
            <>
              <div className="grid grid-cols-3 gap-2">
                <SmallCard label="Candidatos" value={preview.total_candidates} icon={ListChecks} />
                <SmallCard label="Classificados" value={preview.classified} icon={CheckCircle2} tone="emerald" />
                <SmallCard label="Não classificados" value={preview.unclassified} icon={AlertTriangle} tone="amber" />
              </div>

              {Object.keys(preview.by_subcode || {}).length > 0 && (
                <div>
                  <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">Distribuição por subcódigo MEC sugerido</h3>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(preview.by_subcode).sort((a, b) => b[1] - a[1]).map(([sub, count]) => (
                      <span key={sub} className="text-xs bg-gray-100 border border-gray-200 rounded px-2 py-1">
                        <span className="font-mono text-gray-500">{sub}</span> · {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {preview.samples?.length > 0 && (
                <div>
                  <h3 className="text-xs uppercase tracking-wide text-gray-500 mb-2">Amostras ({preview.samples.length})</h3>
                  <div className="border border-gray-200 rounded max-h-56 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 sticky top-0">
                        <tr className="text-left text-gray-500">
                          <th className="px-2 py-1.5 font-medium">Texto legado</th>
                          <th className="px-2 py-1.5 font-medium">Sugestão MEC</th>
                          <th className="px-2 py-1.5 font-medium text-right">Confiança</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {preview.samples.map((s, i) => (
                          <tr key={i}>
                            <td className="px-2 py-1 max-w-md truncate" title={s.legacy_text}>
                              {s.legacy_text}
                            </td>
                            <td className="px-2 py-1">
                              <span className={`font-mono ${s.fallback_used ? 'text-amber-600' : 'text-gray-700'}`}>
                                {s.suggested_subcode}
                              </span>
                              {' '}{s.suggested_reason_name}
                            </td>
                            <td className="px-2 py-1 text-right font-mono">
                              {(s.confidence * 100).toFixed(0)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Controles de aplicação */}
              <div className="bg-blue-50 border border-blue-200 rounded p-3 space-y-2 text-sm">
                <p className="font-medium text-blue-900">Parâmetros da aplicação</p>
                <label className="flex items-center justify-between gap-3">
                  <span className="text-gray-700">Confiança mínima:</span>
                  <select
                    value={confidenceMin}
                    onChange={e => setConfidenceMin(Number(e.target.value))}
                    className="border border-gray-300 rounded px-2 py-1 text-sm"
                    data-testid="legacy-confidence-min"
                  >
                    <option value={1.0}>100% (apenas exatos)</option>
                    <option value={0.85}>85% (recomendado)</option>
                    <option value={0.7}>70% (mais permissivo)</option>
                  </select>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={includeFallback}
                    onChange={e => setIncludeFallback(e.target.checked)}
                    data-testid="legacy-include-fallback"
                  />
                  <span className="text-gray-700">
                    Marcar não-classificados como <code className="text-xs">24z - Não classificado (legado)</code>
                  </span>
                </label>
              </div>

              {applyResult && (
                <div className="bg-emerald-50 border border-emerald-300 rounded p-3 text-sm" data-testid="legacy-apply-result">
                  <p className="font-medium text-emerald-900 flex items-center gap-1.5">
                    <CheckCircle2 size={14} /> Migração concluída
                  </p>
                  <p className="text-emerald-800 mt-1">
                    <strong>{applyResult.migrated}</strong> registros migrados.
                    {applyResult.skipped_low_confidence > 0 && ` ${applyResult.skipped_low_confidence} pulados por baixa confiança.`}
                    {applyResult.skipped_fallback > 0 && ` ${applyResult.skipped_fallback} ignorados (não classificáveis).`}
                  </p>
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t flex items-center justify-between gap-2">
          <p className="text-xs text-gray-500">
            Engine v{preview?.engine_version || '1.0'} · Determinística · Auditável
          </p>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50" data-testid="legacy-cancel">
              Fechar
            </button>
            <button
              onClick={handleApply}
              disabled={applying || !preview || preview.total_candidates === 0}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
              data-testid="legacy-apply"
            >
              {applying ? <Loader2 size={14} className="animate-spin" /> : null}
              {applying ? 'Aplicando...' : 'Aplicar migração'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SmallCard({ label, value, icon: Icon, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-50 border-slate-200 text-slate-900',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
  };
  return (
    <div className={`border rounded p-2.5 ${tones[tone]}`}>
      <div className="flex items-center gap-1.5 text-xs opacity-70">
        <Icon size={12} /> {label}
      </div>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}

export default LegacyMigrationDialog;
