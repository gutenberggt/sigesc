import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Loader2, Home, Siren, Plus, Play, Target, Settings, Check,
  RefreshCw, Trash2, Pencil, AlertTriangle, CheckCircle2, Clock, Save, X,
  Shield, Brain
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEVERITY_LABEL = { low: 'Baixa', medium: 'Média', high: 'Alta', critical: 'Crítica' };
const SEVERITY_COLOR = {
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700'
};
const STATUS_LABEL = { open: 'Aberto', acknowledged: 'Reconhecido', resolved: 'Resolvido' };
const STATUS_COLOR = {
  open: 'bg-red-50 text-red-700 border-red-200',
  acknowledged: 'bg-yellow-50 text-yellow-800 border-yellow-200',
  resolved: 'bg-green-50 text-green-700 border-green-200'
};
const KPI_LABEL = {
  frequencia: 'Frequência', aulas_lancadas: 'Aulas Lançadas',
  notas_lancadas: 'Notas Lançadas', atrasos_dias: 'Atrasos (dias)',
  carga_horaria: 'Carga Horária'
};
const OPERATOR_LABEL = { lt: '<', lte: '≤', gt: '>', gte: '≥' };

const api = {
  listAlerts: (filters = {}) => axios.get(`${API}/pmpi/alerts`, { params: filters }).then(r => r.data),
  updateAlert: (id, data) => axios.put(`${API}/pmpi/alerts/${id}`, data).then(r => r.data),
  runEngine: () => axios.post(`${API}/pmpi/alerts/run`).then(r => r.data),
  listRules: () => axios.get(`${API}/pmpi/alert-rules`).then(r => r.data),
  createRule: (d) => axios.post(`${API}/pmpi/alert-rules`, d).then(r => r.data),
  updateRule: (id, d) => axios.put(`${API}/pmpi/alert-rules/${id}`, d).then(r => r.data),
  deleteRule: (id) => axios.delete(`${API}/pmpi/alert-rules/${id}`).then(r => r.data),
  seedDefaults: () => axios.post(`${API}/pmpi/alert-rules/seed-defaults`).then(r => r.data),
  listGoals: (month) => axios.get(`${API}/pmpi/monthly-goals`, { params: month ? { month } : {} }).then(r => r.data),
  generateGoals: () => axios.post(`${API}/pmpi/monthly-goals/generate`).then(r => r.data),
  // Onda 3
  ranking: () => axios.get(`${API}/pmpi/ranking`).then(r => r.data),
  managerProfile: () => axios.get(`${API}/pmpi/manager-profile`).then(r => r.data),
  intervention: (schoolId) => axios.get(`${API}/pmpi/intervention-level/${schoolId}`).then(r => r.data),
  aiAnalyze: (schoolId) => axios.post(`${API}/pmpi/ai/analyze/${schoolId}`).then(r => r.data),
  aiHistory: (schoolId) => axios.get(`${API}/pmpi/ai/analyses`, { params: schoolId ? { school_id: schoolId } : {} }).then(r => r.data),
  cronStatus: () => axios.get(`${API}/pmpi/cron/status`).then(r => r.data),
  cronTrigger: () => axios.post(`${API}/pmpi/cron/trigger-now`).then(r => r.data),
};

// ======= ALERTS TAB =======
function AlertsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [filters, setFilters] = useState({ status: '', severity: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.listAlerts({
        ...(filters.status ? { status: filters.status } : {}),
        ...(filters.severity ? { severity: filters.severity } : {})
      });
      setData(res);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    try {
      setRunning(true);
      const r = await api.runEngine();
      toast.success(`Motor executado: ${r.alerts_created} novo(s), ${r.alerts_auto_resolved} auto-resolvido(s).`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setRunning(false);
    }
  };

  const update = async (id, status) => {
    try {
      await api.updateAlert(id, { status });
      toast.success('Alerta atualizado');
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const counts = data?.open_by_severity || { low: 0, medium: 0, high: 0, critical: 0 };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-2">
          <select className="border rounded-md px-3 py-2 text-sm" value={filters.status}
            onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))} data-testid="alert-filter-status">
            <option value="">Todos os status</option>
            <option value="open">Aberto</option>
            <option value="acknowledged">Reconhecido</option>
            <option value="resolved">Resolvido</option>
          </select>
          <select className="border rounded-md px-3 py-2 text-sm" value={filters.severity}
            onChange={(e) => setFilters(f => ({ ...f, severity: e.target.value }))} data-testid="alert-filter-severity">
            <option value="">Todas severidades</option>
            {Object.entries(SEVERITY_LABEL).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
          </select>
        </div>
        <Button onClick={run} disabled={running} data-testid="run-engine-btn">
          <Play className={`w-4 h-4 mr-2 ${running ? 'animate-pulse' : ''}`} />
          {running ? 'Executando...' : 'Executar Motor'}
        </Button>
      </div>

      {/* Contadores abertos */}
      <div className="grid grid-cols-4 gap-2">
        {Object.entries(SEVERITY_LABEL).map(([k, v]) => (
          <Card key={k} className={`border-l-4 ${k === 'critical' ? 'border-l-red-500' : k === 'high' ? 'border-l-orange-500' : k === 'medium' ? 'border-l-blue-500' : 'border-l-gray-400'}`}>
            <CardContent className="p-3 flex items-center gap-2">
              <AlertTriangle className={`w-5 h-5 ${k === 'critical' ? 'text-red-500' : k === 'high' ? 'text-orange-500' : k === 'medium' ? 'text-blue-500' : 'text-gray-400'}`} />
              <div>
                <div className="text-[10px] text-gray-500 uppercase">{v}</div>
                <div className="text-lg font-bold" data-testid={`alert-count-${k}`}>{counts[k]}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
      ) : (data?.items || []).length === 0 ? (
        <Card><CardContent className="py-10 text-center text-gray-500">Nenhum alerta encontrado.</CardContent></Card>
      ) : (
        <div className="space-y-2" data-testid="alerts-list">
          {data.items.map(a => (
            <Card key={a.id} className={`border-l-4 ${a.severity === 'critical' ? 'border-l-red-500' : a.severity === 'high' ? 'border-l-orange-500' : a.severity === 'medium' ? 'border-l-blue-500' : 'border-l-gray-400'}`}>
              <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
                <div className="flex-1 min-w-[250px]">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_COLOR[a.severity]}`}>{SEVERITY_LABEL[a.severity]}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${STATUS_COLOR[a.status]}`}>{STATUS_LABEL[a.status]}</span>
                  </div>
                  <h4 className="font-semibold text-sm">{a.rule_name}</h4>
                  <p className="text-xs text-gray-500">
                    {a.school_name} · KPI {KPI_LABEL[a.kpi] || a.kpi}: {a.kpi_value}
                    {a.operator && a.threshold !== undefined && (<> (regra {OPERATOR_LABEL[a.operator]} {a.threshold})</>)}
                  </p>
                  <p className="text-[11px] text-gray-400 mt-0.5">Detectado em: {new Date(a.detected_at).toLocaleString('pt-BR')}</p>
                </div>
                {a.status === 'open' && (
                  <Button variant="outline" size="sm" onClick={() => update(a.id, 'acknowledged')} data-testid={`ack-${a.id}`}>
                    <Clock className="w-3 h-3 mr-1" /> Reconhecer
                  </Button>
                )}
                {a.status !== 'resolved' && (
                  <Button variant="outline" size="sm" onClick={() => update(a.id, 'resolved')} data-testid={`resolve-${a.id}`}>
                    <Check className="w-3 h-3 mr-1" /> Resolver
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ======= RULES TAB =======
function RulesTab() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const emptyForm = { name: '', description: '', kpi: 'frequencia', operator: 'lt', threshold: 70, severity: 'medium', active: true, notify_roles: ['diretor', 'semed'] };
  const [form, setForm] = useState(emptyForm);

  const load = useCallback(async () => {
    try { setLoading(true); const r = await api.listRules(); setRules(r.items || []); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditingId(null); setForm(emptyForm); setOpen(true); };
  const openEdit = (r) => { setEditingId(r.id); setForm({ ...r, notify_roles: r.notify_roles || [] }); setOpen(true); };

  const save = async () => {
    try {
      if (!form.name.trim()) { toast.error('Nome obrigatório'); return; }
      if (editingId) await api.updateRule(editingId, form);
      else await api.createRule(form);
      toast.success('Regra salva');
      setOpen(false); await load();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Excluir a regra "${r.name}"?`)) return;
    try { await api.deleteRule(r.id); toast.success('Removida'); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  };

  const seed = async () => {
    try { const r = await api.seedDefaults(); toast.success(`${r.total_created} regra(s) padrão criada(s)`); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between">
        <Button variant="outline" onClick={seed} data-testid="seed-defaults-btn"><Settings className="w-4 h-4 mr-2" /> Semear padrões</Button>
        <Button onClick={openCreate} data-testid="new-rule-btn"><Plus className="w-4 h-4 mr-2" /> Nova Regra</Button>
      </div>

      {loading ? <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div> :
        rules.length === 0 ? (
          <Card><CardContent className="py-10 text-center text-gray-500">Nenhuma regra. Clique em "Semear padrões" para começar.</CardContent></Card>
        ) : (
          <div className="space-y-2" data-testid="rules-list">
            {rules.map(r => (
              <Card key={r.id}>
                <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex-1 min-w-[250px]">
                    <div className="flex gap-2 flex-wrap mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_COLOR[r.severity]}`}>{SEVERITY_LABEL[r.severity]}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${r.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                        {r.active ? 'Ativa' : 'Inativa'}
                      </span>
                    </div>
                    <h4 className="font-semibold text-sm">{r.name}</h4>
                    <p className="text-xs text-gray-600 mt-0.5">{r.description || '—'}</p>
                    <p className="text-[11px] text-gray-500 mt-0.5">
                      Se <b>{KPI_LABEL[r.kpi]}</b> {OPERATOR_LABEL[r.operator]} {r.threshold} → dispara alerta
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => openEdit(r)}><Pencil className="w-3 h-3" /></Button>
                    <Button variant="outline" size="sm" onClick={() => remove(r)}><Trash2 className="w-3 h-3 text-red-500" /></Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editingId ? 'Editar Regra' : 'Nova Regra'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Nome *</Label><Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} data-testid="rule-name-input" /></div>
            <div><Label>Descrição</Label><Input value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} /></div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>KPI</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.kpi} onChange={e => setForm(f => ({ ...f, kpi: e.target.value }))}>
                  {Object.entries(KPI_LABEL).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
                </select>
              </div>
              <div>
                <Label>Severidade</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                  {Object.entries(SEVERITY_LABEL).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
                </select>
              </div>
              <div>
                <Label>Operador</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={form.operator} onChange={e => setForm(f => ({ ...f, operator: e.target.value }))}>
                  {Object.entries(OPERATOR_LABEL).map(([k, v]) => (<option key={k} value={k}>{v} ({k})</option>))}
                </select>
              </div>
              <div>
                <Label>Threshold</Label>
                <Input type="number" step="0.1" value={form.threshold} onChange={e => setForm(f => ({ ...f, threshold: parseFloat(e.target.value) }))} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="active" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
              <Label htmlFor="active" className="cursor-pointer">Ativa</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button onClick={save} data-testid="save-rule-btn"><Save className="w-4 h-4 mr-2" /> Salvar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ======= GOALS TAB =======
function GoalsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    try { setLoading(true); const r = await api.listGoals(); setData(r); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    try {
      setGenerating(true);
      const r = await api.generateGoals();
      toast.success(`Metas do mês ${r.month}: ${r.goals_created} nova(s), ${r.goals_updated} atualizada(s)`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
    finally { setGenerating(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">Mês de referência: <b>{data?.month || '—'}</b></div>
        <Button onClick={generate} disabled={generating} data-testid="generate-goals-btn">
          <RefreshCw className={`w-4 h-4 mr-2 ${generating ? 'animate-spin' : ''}`} />
          {generating ? 'Gerando...' : 'Gerar/Atualizar Metas'}
        </Button>
      </div>

      {loading ? <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div> :
        (data?.items || []).length === 0 ? (
          <Card><CardContent className="py-10 text-center text-gray-500">Nenhuma meta gerada ainda. Clique em "Gerar Metas".</CardContent></Card>
        ) : (
          <div className="space-y-3" data-testid="goals-list">
            {data.items.map(g => (
              <Card key={g.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{g.school_name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    {Object.entries(g.goals || {}).map(([k, v]) => (
                      <div key={k} className="border rounded-md p-2" data-testid={`goal-${k}-${g.school_id}`}>
                        <div className="text-[10px] uppercase text-gray-500">{KPI_LABEL[k] || k}</div>
                        <div className="flex items-baseline gap-1">
                          <span className="text-lg font-bold text-blue-700">{v}</span>
                          <span className="text-xs text-gray-400">{k === 'atrasos_dias' ? 'dias' : '%'}</span>
                        </div>
                        <div className="text-[10px] text-gray-400">Base: {g.baseline?.[k] ?? '—'}</div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
    </div>
  );
}

// ======= INTELLIGENCE TAB (Onda 3) =======
function IntelligenceTab() {
  const [ranking, setRanking] = useState([]);
  const [managers, setManagers] = useState([]);
  const [cron, setCron] = useState(null);
  const [loading, setLoading] = useState(true);
  const [aiSchool, setAiSchool] = useState('');
  const [aiResult, setAiResult] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [interventionResult, setInterventionResult] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [rk, mp, cr] = await Promise.all([
        api.ranking(), api.managerProfile(), api.cronStatus()
      ]);
      setRanking(rk.items || []);
      setManagers(mp.items || []);
      setCron(cr);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const runAi = async () => {
    if (!aiSchool) { toast.error('Selecione uma escola'); return; }
    try {
      setAiLoading(true);
      setAiResult(null);
      setInterventionResult(null);
      const [ai, iv] = await Promise.all([
        api.aiAnalyze(aiSchool),
        api.intervention(aiSchool),
      ]);
      setAiResult(ai);
      setInterventionResult(iv);
      toast.success('Análise concluída');
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setAiLoading(false);
    }
  };

  const triggerCron = async () => {
    try { await api.cronTrigger(); toast.success('Motor executado manualmente'); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  };

  const rankColor = (score) => {
    if (score == null) return 'text-gray-400';
    if (score >= 85) return 'text-green-600';
    if (score >= 70) return 'text-yellow-600';
    if (score >= 50) return 'text-orange-600';
    return 'text-red-600';
  };
  const profileColor = {
    proativo: 'bg-green-100 text-green-700',
    reativo: 'bg-yellow-100 text-yellow-800',
    critico: 'bg-red-100 text-red-700'
  };
  const riskColor = { baixo: 'bg-green-100 text-green-700', medio: 'bg-yellow-100 text-yellow-800', alto: 'bg-red-100 text-red-700' };
  const interventionColor = [
    'bg-green-100 text-green-700',
    'bg-blue-100 text-blue-700',
    'bg-orange-100 text-orange-700',
    'bg-red-100 text-red-700'
  ];

  return (
    <div className="space-y-5">
      {/* Cron status */}
      <Card>
        <CardContent className="p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${cron?.running ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            <div>
              <div className="text-xs text-gray-500">Agendador</div>
              <div className="text-sm font-medium">
                {cron?.running ? 'Rodando' : 'Parado'}
                {cron?.jobs?.[0]?.next_run_time && (
                  <span className="text-xs text-gray-500 ml-2">
                    · Próxima execução: {new Date(cron.jobs[0].next_run_time).toLocaleString('pt-BR')}
                  </span>
                )}
              </div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={triggerCron} data-testid="trigger-cron-btn">
            <Play className="w-4 h-4 mr-2" /> Disparar agora
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin text-blue-600" /></div>
      ) : (
        <>
          {/* Ranking institucional */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Target className="w-5 h-5 text-blue-600" />Ranking Institucional</CardTitle></CardHeader>
            <CardContent>
              {ranking.length === 0 ? (
                <p className="text-gray-500 text-sm">Nenhuma escola disponível.</p>
              ) : (
                <div className="space-y-2" data-testid="ranking-list">
                  {ranking.map(r => (
                    <div key={r.school_id} className="flex items-center justify-between p-2 border rounded-md hover:bg-gray-50" data-testid={`rank-row-${r.school_id}`}>
                      <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold text-gray-400">#{r.position}</span>
                        <div>
                          <div className="font-medium text-sm">{r.school_name}</div>
                          <div className="text-xs text-gray-500">
                            Freq: {r.kpis?.frequencia?.value ?? '—'} · Aulas: {r.kpis?.aulas_lancadas?.value ?? '—'} · Notas: {r.kpis?.notas_lancadas?.value ?? '—'}
                          </div>
                        </div>
                      </div>
                      <div className={`text-xl font-bold ${rankColor(r.score)}`}>
                        {r.score ?? '—'}
                        <span className="text-xs text-gray-400 ml-1">score</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Perfil dos gestores */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Shield className="w-5 h-5 text-purple-600" />Perfil dos Gestores (60 dias)</CardTitle></CardHeader>
            <CardContent>
              {managers.length === 0 ? (
                <p className="text-gray-500 text-sm">Nenhum gestor identificado. Cadastre diretores/coordenadores com vínculo a escolas.</p>
              ) : (
                <div className="space-y-2" data-testid="managers-list">
                  {managers.map(m => (
                    <div key={m.user_id} className="flex items-center justify-between p-2 border rounded-md">
                      <div>
                        <div className="font-medium text-sm">{m.user_name}</div>
                        <div className="text-xs text-gray-500">
                          ACK médio: {m.tempo_medio_ack_horas ?? '—'}h · Planos no prazo: {m.planos_no_prazo_pct ?? '—'}% · Reincidentes: {m.alertas_reincidentes}
                        </div>
                      </div>
                      <span className={`text-xs px-3 py-1 rounded-full font-medium ${profileColor[m.perfil] || 'bg-gray-100 text-gray-700'}`}>
                        {m.perfil.toUpperCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* IA preditiva */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2">
              <Siren className="w-5 h-5 text-orange-600" /> Análise Preditiva com IA (Claude Sonnet)
            </CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2 items-end flex-wrap">
                <div className="flex-1 min-w-[220px]">
                  <Label className="text-xs">Escola para analisar</Label>
                  <select className="w-full border rounded-md px-3 py-2 text-sm" value={aiSchool}
                    onChange={e => setAiSchool(e.target.value)} data-testid="ai-school-select">
                    <option value="">Selecione...</option>
                    {ranking.map(r => (<option key={r.school_id} value={r.school_id}>{r.school_name}</option>))}
                  </select>
                </div>
                <Button onClick={runAi} disabled={aiLoading || !aiSchool} data-testid="run-ai-btn">
                  {aiLoading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analisando...</> : <><Play className="w-4 h-4 mr-2" /> Analisar</>}
                </Button>
              </div>
              {aiLoading && <p className="text-xs text-gray-500">⏳ Claude está analisando (≈ 15-25s)...</p>}
              {aiResult && (
                <div className="border rounded-md p-3 bg-blue-50/30 space-y-3" data-testid="ai-result">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${riskColor[aiResult.nivel_risco] || 'bg-gray-100 text-gray-700'}`}>
                      Risco: {aiResult.nivel_risco?.toUpperCase()}
                    </span>
                    <span className="text-xs text-gray-500">Modelo: {aiResult.model}</span>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-700 mb-1">Análise</div>
                    <p className="text-sm text-gray-800">{aiResult.analise}</p>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-700 mb-1">Recomendações</div>
                    <ul className="list-disc list-inside text-sm text-gray-800 space-y-1">
                      {(aiResult.recomendacoes || []).map((r, i) => (<li key={i}>{r}</li>))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-700 mb-1">Previsão para o próximo mês</div>
                    <p className="text-sm text-gray-800 italic">{aiResult.previsao_proximo_mes}</p>
                  </div>
                </div>
              )}
              {interventionResult && (
                <div className={`border rounded-md p-3 ${interventionColor[interventionResult.intervention_level] || 'bg-gray-100'}`} data-testid="intervention-result">
                  <div className="text-xs font-semibold uppercase mb-1">
                    Nível de Intervenção Recomendado: {interventionResult.intervention_level}
                  </div>
                  <p className="text-sm">{interventionResult.recommendation}</p>
                  <div className="text-xs mt-1 opacity-80">
                    Alertas abertos: {interventionResult.alerts_open} · Críticos: {interventionResult.alerts_critical} · Score: {interventionResult.score ?? '—'}
                  </div>
                  {interventionResult.notify_roles?.length > 0 && (
                    <div className="text-xs mt-1 opacity-80">Notificar: {interventionResult.notify_roles.join(', ')}</div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

// ======= MAIN PAGE =======
export default function PmpiEngine() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/dashboard" className="flex items-center gap-2 text-gray-600 hover:text-gray-900">
          <Home size={18} /><span>Início</span>
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="pmpi-engine-title">
            <Siren className="w-7 h-7 text-orange-500" />
            Motor PMPI-GE
          </h1>
          <p className="text-gray-600 text-sm">Alertas, regras e metas mensais — Onda 2</p>
        </div>
      </div>

      <Tabs defaultValue="alerts">
        <TabsList>
          <TabsTrigger value="alerts" data-testid="tab-alerts"><Siren className="w-4 h-4 mr-2" />Alertas</TabsTrigger>
          <TabsTrigger value="rules" data-testid="tab-rules"><Settings className="w-4 h-4 mr-2" />Regras</TabsTrigger>
          <TabsTrigger value="goals" data-testid="tab-goals"><Target className="w-4 h-4 mr-2" />Metas Mensais</TabsTrigger>
          <TabsTrigger value="intel" data-testid="tab-intelligence"><Brain className="w-4 h-4 mr-2" />Inteligência</TabsTrigger>
        </TabsList>
        <TabsContent value="alerts" className="mt-4"><AlertsTab /></TabsContent>
        <TabsContent value="rules" className="mt-4"><RulesTab /></TabsContent>
        <TabsContent value="goals" className="mt-4"><GoalsTab /></TabsContent>
        <TabsContent value="intel" className="mt-4"><IntelligenceTab /></TabsContent>
      </Tabs>
    </div>
  );
}
