/**
 * Tenant Admin — /admin/tenant
 *
 * Super_admin: Audit + Backfill + Onboard wizard + Branding Live Preview (G4).
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ChevronLeft, ShieldCheck, Plus, AlertTriangle, RefreshCw, Palette,
} from 'lucide-react';
import BrandingPanel from '@/components/branding/BrandingPanel';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TenantAdmin() {
  const [tab, setTab] = useState('audit');
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showOnboard, setShowOnboard] = useState(false);
  const [form, setForm] = useState({
    nome: '', cnpj: '', municipio: '', estado: '',
    secretaria: '', admin_email: '', admin_nome: '',
    primary_color: '#7c3aed', logotipo_url: '',
    escola_inicial_nome: '',
  });
  const [onboarding, setOnboarding] = useState(false);

  const loadAudit = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/tenant/audit`);
      setAudit(r.data);
    } catch {
      toast.error('Falha ao auditar');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'audit') loadAudit();
  }, [tab]);

  const runBackfill = async () => {
    if (!window.confirm('Rodar backfill REAL (escreve no banco)? Modo seguro: deriva mantenedora_id apenas a partir do parent já vinculado.')) return;
    setLoading(true);
    try {
      const r = await axios.post(`${API}/tenant/audit/backfill?dry_run=false`);
      const tot = r.data.results.reduce((s, x) => s + (x.updated || 0), 0);
      toast.success(`Backfill: ${tot} registros corrigidos`, { duration: 6000 });
      loadAudit();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no backfill');
    } finally {
      setLoading(false);
    }
  };

  const onboard = async () => {
    if (!form.nome || !form.admin_email || !form.admin_nome) {
      toast.error('Preencha nome, e-mail e nome do administrador');
      return;
    }
    setOnboarding(true);
    try {
      const r = await axios.post(`${API}/tenant/onboard`, form);
      toast.success(
        `Mantenedora criada! Senha temporária: ${r.data.admin_temp_password}`,
        { duration: 12000 },
      );
      setShowOnboard(false);
      loadAudit();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no onboarding');
    } finally {
      setOnboarding(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="tenant-admin-page">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ShieldCheck className="h-6 w-6 text-emerald-600" />
            Multi-Tenant — Auditoria, Onboarding & Branding
          </h1>
          <p className="text-sm text-gray-500 max-w-3xl">
            Garanta isolamento de dados entre mantenedoras. Adicione novas redes em &lt; 5 minutos.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 mb-4" role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'audit'}
          onClick={() => setTab('audit')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === 'audit'
              ? 'border-purple-600 text-purple-700'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
          data-testid="tab-audit"
        >
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="h-4 w-4" /> Auditoria & Onboarding
          </span>
        </button>
        <button
          role="tab"
          aria-selected={tab === 'branding'}
          onClick={() => setTab('branding')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === 'branding'
              ? 'border-purple-600 text-purple-700'
              : 'border-transparent text-gray-600 hover:text-gray-900'
          }`}
          data-testid="tab-branding"
        >
          <span className="inline-flex items-center gap-1.5">
            <Palette className="h-4 w-4" /> Branding & Live Preview
          </span>
        </button>
      </div>

      {tab === 'audit' && (
        <>
          <div className="flex gap-2 mb-4 flex-wrap">
            <button
              onClick={loadAudit}
              disabled={loading}
              className="px-3 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 inline-flex items-center gap-1 disabled:opacity-50"
              data-testid="btn-refresh-audit"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Atualizar
            </button>
            <button
              onClick={runBackfill}
              disabled={loading}
              className="px-3 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50"
              data-testid="btn-backfill"
            >
              Rodar backfill
            </button>
            <button
              onClick={() => setShowOnboard(true)}
              className="px-3 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 inline-flex items-center gap-1"
              data-testid="btn-onboard"
            >
              <Plus className="h-4 w-4" /> Nova Mantenedora
            </button>
          </div>

          {audit && (
            <>
              <div className={`rounded-lg p-4 mb-4 border ${
                audit.total_orphans > 0
                  ? 'bg-amber-50 border-amber-200'
                  : 'bg-emerald-50 border-emerald-200'
              }`} data-testid="audit-summary">
                {audit.total_orphans > 0 ? (
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-6 w-6 text-amber-600" />
                    <div>
                      <div className="font-semibold text-amber-800">
                        {audit.total_orphans} registro(s) sem `mantenedora_id`
                      </div>
                      <div className="text-xs text-amber-700">
                        Use "Rodar backfill" para corrigir registros que têm parent vinculado.
                        Lacunas remanescentes (ex.: BNCC nacional) são intencionalmente cross-tenant.
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <ShieldCheck className="h-6 w-6 text-emerald-600" />
                    <div className="font-semibold text-emerald-800">
                      Isolamento 100% — todas as coleções escopadas estão íntegras
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto" data-testid="audit-table">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
                    <tr>
                      <th className="px-3 py-2">Coleção</th>
                      <th className="px-3 py-2">Total</th>
                      <th className="px-3 py-2">Com tenant</th>
                      <th className="px-3 py-2">Órfãos</th>
                      <th className="px-3 py-2">Cobertura</th>
                      <th className="px-3 py-2">Parent backfill</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.rows.map(r => (
                      <tr key={r.collection} className="border-t border-gray-100">
                        <td className="px-3 py-2 font-mono text-xs">{r.collection}</td>
                        <td className="px-3 py-2 text-xs">{r.total}</td>
                        <td className="px-3 py-2 text-xs text-emerald-700">{r.with_tenant}</td>
                        <td className={`px-3 py-2 text-xs ${r.without_tenant > 0 ? 'text-amber-700 font-semibold' : 'text-gray-400'}`}>
                          {r.without_tenant}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-2 bg-gray-100 rounded overflow-hidden">
                              <div
                                className={`h-full ${r.coverage_pct >= 90 ? 'bg-emerald-500' : r.coverage_pct >= 70 ? 'bg-amber-500' : 'bg-red-500'}`}
                                style={{ width: `${r.coverage_pct}%` }}
                              />
                            </div>
                            <span className="text-xs">{r.coverage_pct}%</span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-500">{r.parent_for_backfill || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {tab === 'branding' && <BrandingPanel />}

      {/* Modal Onboard */}
      {showOnboard && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold text-lg">Nova Mantenedora — Wizard</h3>
              <button onClick={() => setShowOnboard(false)} className="text-gray-500">×</button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">Nome da mantenedora *</label>
                <input className="w-full border rounded px-2 py-1 text-sm"
                  placeholder="Prefeitura Municipal de Floresta do Araguaia"
                  value={form.nome}
                  onChange={e => setForm(f => ({ ...f, nome: e.target.value }))}
                  data-testid="onb-nome" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">CNPJ</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    value={form.cnpj}
                    onChange={e => setForm(f => ({ ...f, cnpj: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Cor primária</label>
                  <input type="color" className="w-full h-9 border rounded"
                    value={form.primary_color}
                    onChange={e => setForm(f => ({ ...f, primary_color: e.target.value }))}
                    data-testid="onb-color" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Município</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    value={form.municipio}
                    onChange={e => setForm(f => ({ ...f, municipio: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Estado</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    maxLength="2" placeholder="PA"
                    value={form.estado}
                    onChange={e => setForm(f => ({ ...f, estado: e.target.value.toUpperCase() }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">URL do logotipo</label>
                <input className="w-full border rounded px-2 py-1 text-sm"
                  placeholder="https://..."
                  value={form.logotipo_url}
                  onChange={e => setForm(f => ({ ...f, logotipo_url: e.target.value }))} />
              </div>
              <hr />
              <div className="text-xs text-gray-500 font-semibold">Administrador local</div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Nome *</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    value={form.admin_nome}
                    onChange={e => setForm(f => ({ ...f, admin_nome: e.target.value }))}
                    data-testid="onb-admin-nome" />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">E-mail *</label>
                  <input type="email" className="w-full border rounded px-2 py-1 text-sm"
                    value={form.admin_email}
                    onChange={e => setForm(f => ({ ...f, admin_email: e.target.value }))}
                    data-testid="onb-admin-email" />
                </div>
              </div>
              <hr />
              <div>
                <label className="block text-xs text-gray-600 mb-1">Escola inicial (opcional)</label>
                <input className="w-full border rounded px-2 py-1 text-sm"
                  placeholder="Escola Municipal Centro"
                  value={form.escola_inicial_nome}
                  onChange={e => setForm(f => ({ ...f, escola_inicial_nome: e.target.value }))} />
              </div>
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                A senha temporária do admin local será <strong>Mudar@2026</strong> — ele será obrigado a trocar no primeiro login.
              </div>
            </div>
            <div className="flex justify-end gap-2 p-4 border-t bg-gray-50">
              <button onClick={() => setShowOnboard(false)} className="px-3 py-1 border rounded text-sm">Cancelar</button>
              <button
                onClick={onboard}
                disabled={onboarding}
                className="px-3 py-1 bg-purple-600 text-white rounded text-sm disabled:opacity-60"
                data-testid="onb-submit"
              >
                {onboarding ? 'Criando...' : 'Criar mantenedora'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
