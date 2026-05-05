/**
 * Fila de Revisão de Conteúdo — /admin/content-review (Mai/2026)
 *
 * Tela administrativa para revisar sugestões de normalização textual
 * (CAPS LOCK → sentence case) geradas pelo script
 * `backend/scripts/normalize_content.py`.
 *
 * Cada item mostra original × sugestão lado a lado. Admin pode:
 *   - Aprovar (grava no doc original)
 *   - Rejeitar (descarta a sugestão)
 *   - Editar e Aprovar (admin refina a sugestão antes)
 *   - Aprovar em lote (até 200 itens)
 *
 * Acesso: super_admin, admin, admin_teste.
 */
import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  CheckCircle2, XCircle, Pencil, ChevronLeft, RefreshCw, Filter,
  Loader2, AlertCircle, Inbox, ClipboardCheck, Trash2, Square, CheckSquare,
  Eye,
} from 'lucide-react';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const COLLECTION_LABELS = {
  students: 'Alunos',
  student_history: 'Histórico do Aluno',
  enrollments: 'Matrículas',
  staff: 'Servidores',
  learning_objects: 'Objetos de Aprendizagem',
};

const FIELD_LABELS = {
  observations: 'Observações',
  observacoes: 'Observações',
  descricao: 'Descrição',
  content: 'Conteúdo/Objeto de Conhecimento',
  methodology: 'Práticas Pedagógicas',
  pratica_pedagogica: 'Práticas Pedagógicas (legado)',
};

const STATUS_BADGES = {
  pending: { label: 'Pendente', className: 'bg-amber-100 text-amber-800 border-amber-200' },
  approved: { label: 'Aprovado', className: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
  rejected: { label: 'Rejeitado', className: 'bg-rose-100 text-rose-800 border-rose-200' },
  edited: { label: 'Editado', className: 'bg-blue-100 text-blue-800 border-blue-200' },
};

function authHeaders() {
  const token = localStorage.getItem('sigesc_token');
  const csrf = sessionStorage.getItem('sigesc_csrf_token');
  return {
    Authorization: `Bearer ${token}`,
    ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
  };
}

export default function ContentReview() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({ totals: {}, per_collection: {} });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('pending');
  const [collectionFilter, setCollectionFilter] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [editing, setEditing] = useState(null);
  const [editedText, setEditedText] = useState('');
  const [contextItem, setContextItem] = useState(null);
  const [contextData, setContextData] = useState(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: statusFilter, limit: 100 };
      if (collectionFilter) params.collection = collectionFilter;
      const [listRes, statsRes] = await Promise.all([
        axios.get(`${API}/admin/content-review`, { params, headers: authHeaders() }),
        axios.get(`${API}/admin/content-review/stats`, { headers: authHeaders() }),
      ]);
      setItems(listRes.data.items || []);
      setStats(statsRes.data || { totals: {}, per_collection: {} });
      setSelected(new Set());
    } catch (err) {
      toast.error('Falha ao carregar fila de revisão');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, collectionFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleApprove = async (id) => {
    setActionLoading(true);
    try {
      await axios.post(`${API}/admin/content-review/${id}/approve`, {}, { headers: authHeaders() });
      toast.success('Sugestão aplicada no documento original');
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha ao aprovar');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (id) => {
    setActionLoading(true);
    try {
      await axios.post(`${API}/admin/content-review/${id}/reject`, {}, { headers: authHeaders() });
      toast.success('Sugestão rejeitada');
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha ao rejeitar');
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditAndApprove = async () => {
    if (!editing || !editedText.trim()) return;
    setActionLoading(true);
    try {
      await axios.post(
        `${API}/admin/content-review/${editing.id}/edit-and-approve`,
        { edited_text: editedText },
        { headers: authHeaders() }
      );
      toast.success('Texto editado e aplicado');
      setEditing(null);
      setEditedText('');
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha ao salvar edição');
    } finally {
      setActionLoading(false);
    }
  };

  const handleBulkApprove = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Aprovar ${selected.size} sugestões? Esta ação aplicará as mudanças nos documentos originais.`)) return;
    setActionLoading(true);
    try {
      const res = await axios.post(
        `${API}/admin/content-review/bulk-approve`,
        { ids: Array.from(selected) },
        { headers: authHeaders() }
      );
      toast.success(`${res.data.approved} aprovados • ${res.data.skipped} pulados • ${res.data.errors?.length || 0} erros`);
      await fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha em lote');
    } finally {
      setActionLoading(false);
    }
  };

  const handleViewContext = async (item) => {
    setContextItem(item);
    setContextData(null);
    setContextLoading(true);
    try {
      const res = await axios.get(`${API}/admin/content-review/${item.id}/context`, { headers: authHeaders() });
      setContextData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha ao carregar contexto');
      setContextItem(null);
    } finally {
      setContextLoading(false);
    }
  };

  const toggleSelected = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const toggleSelectAll = () => {
    if (selected.size === items.length) setSelected(new Set());
    else setSelected(new Set(items.map(i => i.id)));
  };

  const totals = stats.totals || {};

  return (
    <Layout>
      <div className="p-6 max-w-7xl mx-auto" data-testid="content-review-page">
        {/* Header */}
        <div className="mb-6">
          <Link to="/dashboard" className="inline-flex items-center text-sm text-slate-600 hover:text-slate-900 mb-3" data-testid="back-link">
            <ChevronLeft className="w-4 h-4 mr-1" /> Voltar ao Dashboard
          </Link>
          <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
            <ClipboardCheck className="w-8 h-8 text-blue-600" />
            Revisão de Conteúdo
          </h1>
          <p className="text-slate-600 mt-2">
            Sugestões de normalização textual (CAPS&nbsp;LOCK&nbsp;→&nbsp;sentence&nbsp;case) aguardando aprovação manual.
            Nenhum dado é alterado sem sua confirmação.
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard label="Pendentes" value={totals.pending || 0} color="amber" testId="stat-pending" />
          <StatCard label="Aprovadas" value={totals.approved || 0} color="emerald" testId="stat-approved" />
          <StatCard label="Rejeitadas" value={totals.rejected || 0} color="rose" testId="stat-rejected" />
          <StatCard label="Editadas" value={totals.edited || 0} color="blue" testId="stat-edited" />
        </div>

        {/* Filters bar */}
        <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4 flex flex-wrap gap-3 items-center">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
            data-testid="filter-status"
          >
            <option value="pending">Pendentes</option>
            <option value="approved">Aprovadas</option>
            <option value="rejected">Rejeitadas</option>
            <option value="edited">Editadas</option>
            <option value="all">Todas</option>
          </select>
          <select
            value={collectionFilter}
            onChange={e => setCollectionFilter(e.target.value)}
            className="border border-slate-300 rounded-md px-3 py-1.5 text-sm"
            data-testid="filter-collection"
          >
            <option value="">Todas as coleções</option>
            {Object.entries(COLLECTION_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} data-testid="refresh-btn">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <div className="ml-auto flex gap-2">
            {statusFilter === 'pending' && items.length > 0 && (
              <>
                <Button variant="outline" size="sm" onClick={toggleSelectAll} data-testid="toggle-select-all">
                  {selected.size === items.length ? <CheckSquare className="w-4 h-4 mr-1" /> : <Square className="w-4 h-4 mr-1" />}
                  {selected.size === items.length ? 'Desmarcar' : 'Selecionar'} todos
                </Button>
                <Button
                  size="sm"
                  onClick={handleBulkApprove}
                  disabled={selected.size === 0 || actionLoading}
                  className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid="bulk-approve-btn"
                >
                  <CheckCircle2 className="w-4 h-4 mr-1" />
                  Aprovar selecionados ({selected.size})
                </Button>
              </>
            )}
          </div>
        </div>

        {/* List */}
        {loading ? (
          <div className="flex items-center justify-center p-12 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Carregando...
          </div>
        ) : items.length === 0 ? (
          <EmptyState statusFilter={statusFilter} />
        ) : (
          <div className="space-y-3">
            {items.map(item => (
              <ReviewCard
                key={item.id}
                item={item}
                selected={selected.has(item.id)}
                onToggleSelect={() => toggleSelected(item.id)}
                onApprove={() => handleApprove(item.id)}
                onReject={() => handleReject(item.id)}
                onEdit={() => { setEditing(item); setEditedText(item.sugestao); }}
                onViewContext={() => handleViewContext(item)}
                actionLoading={actionLoading}
                showCheckbox={statusFilter === 'pending'}
              />
            ))}
          </div>
        )}

        {/* Edit Dialog */}
        <Dialog open={!!editing} onOpenChange={open => { if (!open) { setEditing(null); setEditedText(''); } }}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Editar sugestão antes de aprovar</DialogTitle>
            </DialogHeader>
            {editing && (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Original</label>
                  <div className="mt-1 p-3 bg-rose-50 border border-rose-200 rounded text-sm text-rose-900 whitespace-pre-wrap">
                    {editing.original}
                  </div>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Texto final</label>
                  <Textarea
                    value={editedText}
                    onChange={e => setEditedText(e.target.value)}
                    rows={5}
                    className="mt-1"
                    data-testid="edit-textarea"
                  />
                </div>
              </div>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => { setEditing(null); setEditedText(''); }}>Cancelar</Button>
              <Button
                onClick={handleEditAndApprove}
                disabled={!editedText.trim() || actionLoading}
                className="bg-emerald-600 hover:bg-emerald-700"
                data-testid="save-edit-btn"
              >
                {actionLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                Salvar e aplicar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Context Dialog */}
        <Dialog open={!!contextItem} onOpenChange={open => { if (!open) { setContextItem(null); setContextData(null); } }}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Contexto do registro</DialogTitle>
            </DialogHeader>
            {contextLoading ? (
              <div className="flex items-center justify-center py-8 text-slate-500">
                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Carregando...
              </div>
            ) : contextData ? (
              <ContextView data={contextData} sugestao={contextItem?.sugestao} />
            ) : null}
            <DialogFooter>
              <Button variant="outline" onClick={() => { setContextItem(null); setContextData(null); }} data-testid="close-context-btn">
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}

function ContextView({ data, sugestao }) {
  const collectionLabel = COLLECTION_LABELS[data.collection] || data.collection;
  const allFields = data.fields || {};
  // Separa campos de identificação dos textuais
  const idKeys = ['id', 'full_name', 'nome', 'name', 'email', 'enrollment_number',
                  'date', 'academic_year', 'class_id', 'course_id', 'school_id'];
  const identification = idKeys
    .map(k => [k, allFields[k]])
    .filter(([, v]) => v != null && v !== '');
  const textualKeys = Object.keys(allFields).filter(k => !idKeys.includes(k) &&
    !['mantenedora_id', 'content_migrated', 'content_migrated_at'].includes(k));

  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center gap-2 text-slate-700">
        <Badge variant="outline">{collectionLabel}</Badge>
        <span className="text-slate-500">·</span>
        <span className="font-mono text-xs text-slate-500">{data.source_id}</span>
        {allFields.content_migrated && (
          <span className="ml-auto px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
            Já migrado
          </span>
        )}
      </div>
      {identification.length > 0 && (
        <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded border border-slate-200">
          {identification.map(([k, v]) => (
            <div key={k} className="text-xs">
              <span className="text-slate-500 uppercase tracking-wider">{k}: </span>
              <span className="text-slate-800 font-medium">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="space-y-3">
        {textualKeys.map(k => {
          const isHighlighted = k === data.highlight_field;
          return (
            <div
              key={k}
              className={`p-3 rounded border ${
                isHighlighted ? 'bg-amber-50 border-amber-300 ring-2 ring-amber-200' : 'bg-white border-slate-200'
              }`}
              data-testid={`context-field-${k}`}
            >
              <div className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-1 flex items-center justify-between">
                <span>{FIELD_LABELS[k] || k}</span>
                {isHighlighted && <span className="text-amber-700 normal-case">📍 campo da sugestão</span>}
              </div>
              <div className="text-sm text-slate-800 whitespace-pre-wrap">{String(allFields[k] || '—')}</div>
              {isHighlighted && sugestao && (
                <div className="mt-2 pt-2 border-t border-amber-200">
                  <div className="text-xs font-semibold text-emerald-700 uppercase tracking-wider mb-1">Sugestão pendente</div>
                  <div className="text-sm text-emerald-900">{sugestao}</div>
                </div>
              )}
            </div>
          );
        })}
        {textualKeys.length === 0 && (
          <div className="text-slate-500 italic text-center py-4">Sem campos textuais adicionais.</div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color, testId }) {
  const palette = {
    amber: 'bg-amber-50 border-amber-200 text-amber-900',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    rose: 'bg-rose-50 border-rose-200 text-rose-900',
    blue: 'bg-blue-50 border-blue-200 text-blue-900',
  }[color];
  return (
    <div className={`border rounded-lg p-4 ${palette}`} data-testid={testId}>
      <div className="text-xs uppercase tracking-wider opacity-70">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}

function ReviewCard({ item, selected, onToggleSelect, onApprove, onReject, onEdit, onViewContext, actionLoading, showCheckbox }) {
  const collectionLabel = COLLECTION_LABELS[item.source_collection] || item.source_collection;
  const fieldLabel = FIELD_LABELS[item.source_field] || item.source_field;
  const statusBadge = STATUS_BADGES[item.status] || STATUS_BADGES.pending;
  const isPending = item.status === 'pending';
  const contextName = item.context?.full_name || item.context?.nome || item.context?.name || '—';

  return (
    <div
      className={`bg-white border rounded-lg overflow-hidden transition-all ${
        selected ? 'border-blue-400 ring-2 ring-blue-100' : 'border-slate-200'
      }`}
      data-testid={`review-card-${item.id}`}
    >
      <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center gap-3 text-sm">
        {showCheckbox && (
          <button onClick={onToggleSelect} className="text-slate-500 hover:text-slate-900" data-testid={`select-${item.id}`}>
            {selected ? <CheckSquare className="w-5 h-5 text-blue-600" /> : <Square className="w-5 h-5" />}
          </button>
        )}
        <Badge variant="outline">{collectionLabel}</Badge>
        <span className="text-slate-500">›</span>
        <span className="font-medium text-slate-700">{fieldLabel}</span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-600 italic truncate max-w-xs">{contextName}</span>
        <span className={`ml-auto px-2 py-0.5 rounded text-xs font-medium border ${statusBadge.className}`}>
          {statusBadge.label}
        </span>
      </div>

      <div className="grid md:grid-cols-2 divide-x divide-slate-200">
        <div className="p-4">
          <div className="text-xs font-semibold text-rose-700 uppercase tracking-wider mb-2 flex items-center gap-1">
            <XCircle className="w-3 h-3" /> Original (CAPS)
          </div>
          <div className="text-sm text-slate-800 whitespace-pre-wrap break-words">{item.original}</div>
        </div>
        <div className="p-4 bg-emerald-50/40">
          <div className="text-xs font-semibold text-emerald-700 uppercase tracking-wider mb-2 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Sugestão (sentence case)
          </div>
          <div className="text-sm text-slate-800 whitespace-pre-wrap break-words">
            {item.edited_text || item.sugestao}
          </div>
        </div>
      </div>

      {isPending && (
        <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 flex flex-wrap gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={onViewContext} disabled={actionLoading} data-testid={`view-context-${item.id}`}
                  className="text-slate-600 hover:text-slate-900">
            <Eye className="w-3.5 h-3.5 mr-1" /> Ver contexto
          </Button>
          <Button variant="outline" size="sm" onClick={onEdit} disabled={actionLoading} data-testid={`edit-${item.id}`}>
            <Pencil className="w-3.5 h-3.5 mr-1" /> Editar
          </Button>
          <Button variant="outline" size="sm" onClick={onReject} disabled={actionLoading} data-testid={`reject-${item.id}`}
                  className="text-rose-700 border-rose-300 hover:bg-rose-50 hover:text-rose-900">
            <XCircle className="w-3.5 h-3.5 mr-1" /> Rejeitar
          </Button>
          <Button size="sm" onClick={onApprove} disabled={actionLoading} className="bg-emerald-600 hover:bg-emerald-700"
                  data-testid={`approve-${item.id}`}>
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Aprovar
          </Button>
        </div>
      )}
    </div>
  );
}

function EmptyState({ statusFilter }) {
  const messages = {
    pending: { title: 'Nenhuma sugestão pendente', sub: 'Rode o script normalize_content.py --scan para gerar sugestões.' },
    approved: { title: 'Nenhum item aprovado ainda', sub: 'Itens aprovados aparecerão aqui.' },
    rejected: { title: 'Nenhum item rejeitado', sub: 'Itens descartados aparecerão aqui.' },
    edited: { title: 'Nenhum item editado', sub: 'Sugestões editadas pelo admin aparecerão aqui.' },
    all: { title: 'Fila vazia', sub: 'Nenhum item nesta fila.' },
  };
  const m = messages[statusFilter] || messages.all;
  return (
    <div className="bg-white border-2 border-dashed border-slate-200 rounded-lg p-12 text-center" data-testid="empty-state">
      <Inbox className="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <div className="text-lg font-semibold text-slate-700">{m.title}</div>
      <div className="text-sm text-slate-500 mt-1">{m.sub}</div>
    </div>
  );
}
