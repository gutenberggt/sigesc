import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { Layout } from '@/components/Layout';
import { ctueAPI } from '@/services/api';
import { STATE_META } from '@/components/ctue/ConformityPanel';
import {
  Building2, CheckCircle2, XCircle, Gauge, ClipboardList, Clock, Award,
  AlertTriangle, ListChecks, MapPin, BarChart3, TrendingUp, ExternalLink, Loader2
} from 'lucide-react';

const SEV_META = {
  critico: { dot: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', label: 'Crítico' },
  alto: { dot: 'bg-orange-500', text: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200', label: 'Alto' },
  medio: { dot: 'bg-yellow-500', text: 'text-yellow-700', bg: 'bg-yellow-50', border: 'border-yellow-200', label: 'Médio' },
};
const MAP_COLORS = { conforme: '#22c55e', atencao: '#eab308', critico: '#f97316', nao_conforme: '#ef4444', nao_avaliado: '#9ca3af' };
const MATURITY_LABELS = { 1: 'Cadastro Inicial', 2: 'Cadastro Completo', 3: 'Infraestrutura Validada', 4: 'Conformidade Institucional', 5: 'Excelência Operacional' };

function StatCard({ icon: Icon, label, value, sub, color = 'text-gray-700', testid }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3" data-testid={testid}>
      <div className={`p-2 rounded-lg bg-gray-50 ${color}`}><Icon size={22} /></div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-gray-900 leading-tight">{value}</div>
        <div className="text-xs text-gray-500">{label}{sub && <span className="block text-[11px] text-gray-400">{sub}</span>}</div>
      </div>
    </div>
  );
}

function SectionTitle({ icon: Icon, children, hint }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon size={18} className="text-gray-500" />
      <h3 className="text-base font-semibold text-gray-900">{children}</h3>
      {hint && <span className="text-xs text-gray-400">· {hint}</span>}
    </div>
  );
}

export default function NetworkPanel() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState('default');
  const [profiles, setProfiles] = useState([]);
  const [panel, setPanel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [comparTab, setComparTab] = useState('zona');

  useEffect(() => { ctueAPI.getProfiles().then((d) => setProfiles(d.profiles || [])).catch(() => {}); }, []);
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    ctueAPI.getNetworkPanel(profile)
      .then((d) => { if (mounted) setPanel(d); })
      .catch(() => { if (mounted) setPanel(null); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [profile]);

  const e = panel?.executive;
  const points = panel?.map || [];
  const center = points.length ? [points[0].lat, points[0].lng] : [-3.7327, -38.527];

  return (
    <Layout>
      <div className="space-y-6" data-testid="network-panel">
        {/* Cabeçalho */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Centro de Inteligência da Rede</h1>
            <p className="text-sm text-gray-500">O que a Secretaria precisa fazer hoje — dados do CTUE (SSoT)</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500">Perfil:</label>
            <select
              value={profile}
              onChange={(e2) => setProfile(e2.target.value)}
              className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-blue-500"
              data-testid="network-profile-select"
            >
              {profiles.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20 text-gray-400" data-testid="network-loading">
            <Loader2 className="animate-spin mr-2" /> Carregando painel…
          </div>
        )}

        {!loading && panel && (
          <>
            {/* 1. Visão Executiva */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3" data-testid="network-executive">
              <StatCard icon={Building2} label="Escolas" value={e.total} color="text-blue-600" testid="exec-total" />
              <StatCard icon={CheckCircle2} label="Ativas" value={e.ativas} color="text-green-600" testid="exec-ativas" />
              <StatCard icon={XCircle} label="Inativas" value={e.inativas} color="text-gray-500" testid="exec-inativas" />
              <StatCard icon={Gauge} label="Conformidade média" value={`${e.conformidade_media}%`} color="text-emerald-600" testid="exec-conf" />
              <StatCard icon={ClipboardList} label="Completude média" value={`${e.completude_media}%`} color="text-indigo-600" testid="exec-comp" />
              <StatCard icon={Clock} label="Atualização média" value={e.atualizacao_media_dias != null ? `${e.atualizacao_media_dias}d` : '—'} sub={`${e.cadastros_nunca_atualizados} nunca`} color="text-amber-600" testid="exec-atualizacao" />
              <StatCard icon={Award} label="Nível médio" value={`N${e.maturidade_media || 1}`} sub={MATURITY_LABELS[e.maturidade_media] || ''} color="text-violet-600" testid="exec-maturidade" />
            </div>

            {/* Distribuição de maturidade */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <SectionTitle icon={Award}>Distribuição por Maturidade</SectionTitle>
              <div className="flex w-full h-3 rounded-full overflow-hidden bg-gray-100 mb-2">
                {[1, 2, 3, 4, 5].map((n) => {
                  const v = e.maturidade_distribuicao[String(n)] || 0;
                  const pct = e.total ? (v / e.total) * 100 : 0;
                  const colors = ['bg-red-400', 'bg-orange-400', 'bg-yellow-400', 'bg-lime-500', 'bg-green-600'];
                  return pct > 0 ? <div key={n} className={colors[n - 1]} style={{ width: `${pct}%` }} title={`Nível ${n}: ${v}`} /> : null;
                })}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
                {[1, 2, 3, 4, 5].map((n) => (
                  <span key={n} data-testid={`maturity-level-${n}`}>Nível {n} — {MATURITY_LABELS[n]}: <strong>{e.maturidade_distribuicao[String(n)] || 0}</strong></span>
                ))}
              </div>
            </div>

            {/* 2 + 3. Alertas e Fila de Prioridades */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4" data-testid="network-alerts">
                <SectionTitle icon={AlertTriangle} hint={`${panel.alerts.length} alertas`}>Painel de Alertas</SectionTitle>
                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {panel.alerts.length === 0 && <p className="text-sm text-gray-400">Sem alertas 🎉</p>}
                  {panel.alerts.map((a, i) => {
                    const sm = SEV_META[a.severidade] || SEV_META.medio;
                    return (
                      <button key={i} onClick={() => navigate('/admin/schools')}
                        className={`w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg border text-left hover:shadow-sm transition ${sm.bg} ${sm.border}`}
                        data-testid={`alert-item-${i}`}>
                        <span className="flex items-center gap-2 min-w-0">
                          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${sm.dot}`} />
                          <span className="text-sm text-gray-800 truncate"><strong>{a.school_name}</strong> — {a.label}</span>
                        </span>
                        <span className={`text-[10px] font-semibold uppercase ${sm.text}`}>{sm.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4" data-testid="network-priorities">
                <SectionTitle icon={ListChecks} hint="ordenado por criticidade">Ações Prioritárias</SectionTitle>
                <ol className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  {panel.priorities.length === 0 && <p className="text-sm text-gray-400">Nenhuma ação pendente.</p>}
                  {panel.priorities.slice(0, 30).map((p) => (
                    <li key={p.ordem} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-100 hover:bg-gray-50" data-testid={`priority-item-${p.ordem}`}>
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">{p.ordem}</span>
                      <span className="text-sm text-gray-800 flex-1 min-w-0">{p.acao}</span>
                      <span className="text-[11px] text-gray-400 flex-shrink-0">{p.conformidade}%</span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>

            {/* 4. Mapa da Rede */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4" data-testid="network-map">
              <SectionTitle icon={MapPin} hint={`${points.length} escolas georreferenciadas`}>Mapa da Rede</SectionTitle>
              {points.length === 0 ? (
                <div className="py-10 text-center text-sm text-gray-400" data-testid="map-empty">
                  Nenhuma escola possui coordenadas (latitude/longitude) cadastradas no CTUE ainda.
                </div>
              ) : (
                <div className="h-96 rounded-lg overflow-hidden">
                  <MapContainer center={center} zoom={11} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false}>
                    <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                    {points.map((pt) => (
                      <CircleMarker key={pt.school_id} center={[pt.lat, pt.lng]} radius={9}
                        pathOptions={{ color: MAP_COLORS[pt.status] || '#9ca3af', fillColor: MAP_COLORS[pt.status] || '#9ca3af', fillOpacity: 0.85 }}>
                        <Popup>
                          <div className="text-sm">
                            <div className="font-semibold">{pt.name}</div>
                            <div className="text-gray-600">Gestor: {pt.gestor || '—'}</div>
                            <div>Conformidade: <strong>{pt.conformidade}%</strong> · Completude: {pt.completude}%</div>
                            <div className="text-gray-500 text-xs">{pt.atualizacao}</div>
                            <button className="mt-1 text-blue-600 inline-flex items-center gap-1" onClick={() => navigate('/admin/schools')}>
                              Abrir CTUE <ExternalLink size={12} />
                            </button>
                          </div>
                        </Popup>
                      </CircleMarker>
                    ))}
                  </MapContainer>
                </div>
              )}
            </div>

            {/* 5. Comparativos */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4" data-testid="network-comparativos">
              <SectionTitle icon={BarChart3}>Comparativos da Rede</SectionTitle>
              <div className="flex flex-wrap gap-2 mb-3">
                {[['zona', 'Urbana × Rural'], ['distrito', 'Distrito'], ['etapas', 'Etapas de Ensino'], ['porte', 'Porte']].map(([k, lbl]) => (
                  <button key={k} onClick={() => setComparTab(k)}
                    className={`px-3 py-1.5 rounded-full text-sm font-medium border transition ${comparTab === k ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}
                    data-testid={`compar-tab-${k}`}>{lbl}</button>
                ))}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="compar-table">
                  <thead>
                    <tr className="text-left text-gray-500 border-b">
                      <th className="py-2 pr-4">Grupo</th><th className="py-2 pr-4">Escolas</th>
                      <th className="py-2 pr-4">Conformidade média</th><th className="py-2">Completude média</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(panel.comparativos[comparTab] || []).map((row, i) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-2 pr-4 font-medium text-gray-800">{row.grupo}</td>
                        <td className="py-2 pr-4">{row.escolas}</td>
                        <td className="py-2 pr-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden"><div className="h-full bg-emerald-500" style={{ width: `${row.conformidade_media}%` }} /></div>
                            <span>{row.conformidade_media}%</span>
                          </div>
                        </td>
                        <td className="py-2">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden"><div className="h-full bg-indigo-500" style={{ width: `${row.completude_media}%` }} /></div>
                            <span>{row.completude_media}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* 6. Evolução da Rede (arquitetura preparada) */}
            <div className="bg-gray-50 rounded-xl border border-dashed border-gray-300 p-4" data-testid="network-evolucao">
              <SectionTitle icon={TrendingUp} hint="em breve">Evolução da Rede</SectionTitle>
              <p className="text-sm text-gray-500">
                Arquitetura preparada para a visão histórica. Em breve: evolução de conformidade,
                completude, atualização e maturidade ao longo do tempo (via snapshots do CTUE).
              </p>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
