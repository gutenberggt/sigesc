import { useEffect, useMemo, useState, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  Loader2, Plus, Trash2, Pencil, Home, ClipboardList, CheckCircle2, Clock,
  AlertTriangle, Save, X
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import { actionPlansAPI, schoolsAPI } from '@/services/api';
import SpellCheckTextarea from '@/components/SpellCheckTextarea';

const PRIORITY_LABELS = { low: 'Baixa', medium: 'Média', high: 'Alta', critical: 'Crítica' };
const STATUS_LABELS = {
  draft: 'Rascunho', active: 'Ativo', in_progress: 'Em Andamento',
  completed: 'Concluído', cancelled: 'Cancelado'
};
const PRIORITY_COLORS = {
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700'
};
const STATUS_COLORS = {
  draft: 'bg-gray-100 text-gray-700',
  active: 'bg-blue-100 text-blue-700',
  in_progress: 'bg-indigo-100 text-indigo-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700'
};

const emptyPlan = () => ({
  school_id: '',
  title: '',
  description: '',
  priority: 'medium',
  status: 'active',
  due_date: '',
  responsible_user_id: '',
  linked_kpi: '',
  actions: []
});

export default function ActionPlans() {
  const [searchParams, setSearchParams] = useSearchParams();
  const schoolFilterFromUrl = searchParams.get('school_id') || '';

  const [plans, setPlans] = useState([]);
  const [schools, setSchools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyPlan());
  const [filters, setFilters] = useState({ school_id: schoolFilterFromUrl, status: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [p, s] = await Promise.all([
        actionPlansAPI.list({
          ...(filters.school_id ? { school_id: filters.school_id } : {}),
          ...(filters.status ? { status: filters.status } : {})
        }),
        schoolsAPI.list()
      ]);
      setPlans(p.items || []);
      setSchools(s.items || s || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Erro ao carregar');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyPlan(), school_id: filters.school_id || '' });
    setDialogOpen(true);
  };

  const openEdit = (plan) => {
    setEditingId(plan.id);
    setForm({
      school_id: plan.school_id,
      title: plan.title,
      description: plan.description || '',
      priority: plan.priority,
      status: plan.status,
      due_date: plan.due_date || '',
      responsible_user_id: plan.responsible_user_id || '',
      linked_kpi: plan.linked_kpi || '',
      actions: plan.actions || []
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.school_id || !form.title.trim()) {
      setError('Escola e título são obrigatórios.');
      return;
    }
    try {
      setSaving(true);
      setError(null);
      if (editingId) {
        await actionPlansAPI.update(editingId, form);
      } else {
        await actionPlansAPI.create(form);
      }
      setDialogOpen(false);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (plan) => {
    if (!window.confirm(`Excluir o plano "${plan.title}"?`)) return;
    try {
      await actionPlansAPI.delete(plan.id);
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Erro ao excluir');
    }
  };

  const addActionItem = () => {
    setForm(f => ({ ...f, actions: [...(f.actions || []), { text: '', done: false }] }));
  };
  const updateActionItem = (i, patch) => {
    setForm(f => {
      const next = [...f.actions];
      next[i] = { ...next[i], ...patch };
      return { ...f, actions: next };
    });
  };
  const removeActionItem = (i) => {
    setForm(f => ({ ...f, actions: f.actions.filter((_, idx) => idx !== i) }));
  };

  const stats = useMemo(() => {
    const s = { active: 0, in_progress: 0, completed: 0, critical: 0 };
    plans.forEach(p => {
      if (p.status === 'active' || p.status === 'draft') s.active++;
      if (p.status === 'in_progress') s.in_progress++;
      if (p.status === 'completed') s.completed++;
      if (p.priority === 'critical' && p.status !== 'completed' && p.status !== 'cancelled') s.critical++;
    });
    return s;
  }, [plans]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <Link to="/dashboard" className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors">
            <Home size={18} />
            <span>Início</span>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="action-plans-title">
              <ClipboardList className="w-7 h-7 text-blue-600" />
              Planos de Ação
            </h1>
            <p className="text-gray-600 text-sm">Intervenções estruturadas por escola — PMPI-GE</p>
          </div>
        </div>
        <Button onClick={openCreate} data-testid="new-plan-btn">
          <Plus className="w-4 h-4 mr-2" />
          Novo Plano
        </Button>
      </div>

      {/* Estatísticas resumidas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="p-3 flex items-center gap-2">
            <Clock className="w-6 h-6 text-blue-500" />
            <div>
              <div className="text-[10px] text-gray-500 uppercase">Ativos</div>
              <div className="text-xl font-bold">{stats.active}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-indigo-500">
          <CardContent className="p-3 flex items-center gap-2">
            <Clock className="w-6 h-6 text-indigo-500" />
            <div>
              <div className="text-[10px] text-gray-500 uppercase">Em Andamento</div>
              <div className="text-xl font-bold">{stats.in_progress}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-500">
          <CardContent className="p-3 flex items-center gap-2">
            <CheckCircle2 className="w-6 h-6 text-green-500" />
            <div>
              <div className="text-[10px] text-gray-500 uppercase">Concluídos</div>
              <div className="text-xl font-bold">{stats.completed}</div>
            </div>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="p-3 flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-red-500" />
            <div>
              <div className="text-[10px] text-gray-500 uppercase">Críticos</div>
              <div className="text-xl font-bold">{stats.critical}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="p-4 flex flex-wrap gap-3 items-end">
          <div>
            <Label htmlFor="f-school" className="text-xs">Escola</Label>
            <select
              id="f-school"
              className="border border-gray-300 rounded-md px-3 py-2 text-sm min-w-[220px]"
              value={filters.school_id}
              onChange={(e) => {
                setFilters(f => ({ ...f, school_id: e.target.value }));
                if (e.target.value) setSearchParams({ school_id: e.target.value });
                else setSearchParams({});
              }}
              data-testid="filter-school"
            >
              <option value="">Todas as escolas</option>
              {schools.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="f-status" className="text-xs">Status</Label>
            <select
              id="f-status"
              className="border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={filters.status}
              onChange={(e) => setFilters(f => ({ ...f, status: e.target.value }))}
              data-testid="filter-status"
            >
              <option value="">Todos</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg p-4" data-testid="plans-error">
          {error}
        </div>
      )}

      {/* Lista de planos */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[200px]">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      ) : plans.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center text-gray-500">
            <ClipboardList className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p>Nenhum plano de ação cadastrado para esses filtros.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="plans-list">
          {plans.map(p => (
            <Card key={p.id} className="hover:shadow-md transition-shadow" data-testid={`plan-row-${p.id}`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex-1 min-w-[250px]">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[p.priority]}`}>
                        {PRIORITY_LABELS[p.priority]}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[p.status]}`}>
                        {STATUS_LABELS[p.status]}
                      </span>
                      {p.linked_kpi && (
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-purple-100 text-purple-700">
                          KPI: {p.linked_kpi}
                        </span>
                      )}
                    </div>
                    <h3 className="font-semibold text-gray-900 leading-tight">{p.title}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {p.school_name}
                      {p.due_date && <> · Prazo: {new Date(p.due_date).toLocaleDateString('pt-BR')}</>}
                    </p>
                    {p.description && (
                      <p className="text-sm text-gray-700 mt-2 line-clamp-2">{p.description}</p>
                    )}
                    {(p.actions || []).length > 0 && (
                      <div className="text-xs text-gray-500 mt-2">
                        {(p.actions || []).filter(a => a.done).length}/{p.actions.length} itens concluídos
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => openEdit(p)} data-testid={`edit-plan-${p.id}`}>
                      <Pencil className="w-4 h-4" />
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => remove(p)} data-testid={`delete-plan-${p.id}`}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog Create/Edit */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Editar Plano de Ação' : 'Novo Plano de Ação'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Escola *</Label>
              <select
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                value={form.school_id}
                onChange={(e) => setForm(f => ({ ...f, school_id: e.target.value }))}
                data-testid="plan-school-select"
                disabled={!!editingId}
              >
                <option value="">Selecione...</option>
                {schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <Label>Título *</Label>
              <Input
                value={form.title}
                onChange={(e) => setForm(f => ({ ...f, title: e.target.value }))}
                placeholder="Ex.: Recuperar frequência na turma 5ºA"
                data-testid="plan-title-input"
              />
            </div>
            <div>
              <Label>Descrição</Label>
              <SpellCheckTextarea
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm min-h-[80px]"
                value={form.description}
                onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Contexto, objetivo e responsabilidades..."
                data-testid="plan-description-input"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Prioridade</Label>
                <select
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                  value={form.priority}
                  onChange={(e) => setForm(f => ({ ...f, priority: e.target.value }))}
                  data-testid="plan-priority-select"
                >
                  {Object.entries(PRIORITY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Status</Label>
                <select
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                  value={form.status}
                  onChange={(e) => setForm(f => ({ ...f, status: e.target.value }))}
                  data-testid="plan-status-select"
                >
                  {Object.entries(STATUS_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Prazo</Label>
                <Input
                  type="date"
                  value={form.due_date ? form.due_date.slice(0, 10) : ''}
                  onChange={(e) => setForm(f => ({ ...f, due_date: e.target.value }))}
                  data-testid="plan-due-date-input"
                />
              </div>
              <div>
                <Label>KPI vinculado</Label>
                <select
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
                  value={form.linked_kpi}
                  onChange={(e) => setForm(f => ({ ...f, linked_kpi: e.target.value }))}
                  data-testid="plan-linked-kpi-select"
                >
                  <option value="">—</option>
                  <option value="frequencia">Frequência</option>
                  <option value="aulas_lancadas">Aulas Lançadas</option>
                  <option value="notas_lancadas">Notas Lançadas</option>
                  <option value="atrasos_dias">Atrasos</option>
                  <option value="carga_horaria">Carga Horária</option>
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Checklist de ações</Label>
                <Button type="button" variant="outline" size="sm" onClick={addActionItem} data-testid="add-action-item-btn">
                  <Plus className="w-3 h-3 mr-1" /> Adicionar item
                </Button>
              </div>
              <div className="space-y-2">
                {(form.actions || []).map((a, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`action-item-${i}`}>
                    <input
                      type="checkbox"
                      checked={a.done || false}
                      onChange={(e) => updateActionItem(i, { done: e.target.checked, done_at: e.target.checked ? new Date().toISOString() : null })}
                    />
                    <Input
                      value={a.text}
                      onChange={(e) => updateActionItem(i, { text: e.target.value })}
                      placeholder="Descrição da ação..."
                      className="flex-1"
                    />
                    <Button type="button" variant="ghost" size="sm" onClick={() => removeActionItem(i)}>
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
                {(!form.actions || form.actions.length === 0) && (
                  <p className="text-xs text-gray-400 text-center py-2">Nenhum item adicionado</p>
                )}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button onClick={save} disabled={saving} data-testid="save-plan-btn">
              {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Salvando...</> : <><Save className="w-4 h-4 mr-2" />Salvar</>}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
