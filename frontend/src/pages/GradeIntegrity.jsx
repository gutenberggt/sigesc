/**
 * Integrity Report da Grade Horária — Fase 6b (Mai/2026)
 *
 * UI operacional de saneamento institucional. Cards humanizados (NÃO JSON),
 * severidade colorida, drill-down com assignments, workflow state
 * (open/in_analysis/resolved/wont_fix), notes append-only.
 *
 * Diretriz do owner:
 *   "O sistema NÃO deve parecer um log técnico."
 *   "Transformar inconsistências em fila de trabalho."
 *   "Tudo vem do backend. Frontend apenas representa."
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { schoolsAPI } from '@/services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  AlertTriangle,
  ShieldAlert,
  ShieldQuestion,
  AlertCircle,
  ArrowLeft,
  Filter,
  RefreshCw,
  ExternalLink,
  ClipboardCheck,
  UserCheck,
  CheckCircle2,
  XCircle,
  RotateCcw,
  MessageSquarePlus,
  Loader2,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${API_URL}/api`;

// ============================================================================
// Mapas de severidade e status — paleta SEMÂNTICA fixa.
// ============================================================================
const SEVERITY_META = {
  high: {
    label: 'Crítico',
    bg: 'bg-red-50',
    border: 'border-red-600',
    text: 'text-red-900',
    chip: 'bg-red-600 text-white',
    icon: AlertTriangle,
  },
  medium: {
    label: 'Médio',
    bg: 'bg-amber-50',
    border: 'border-amber-500',
    text: 'text-amber-900',
    chip: 'bg-amber-500 text-white',
    icon: ShieldAlert,
  },
  low: {
    label: 'Baixo',
    bg: 'bg-blue-50',
    border: 'border-blue-400',
    text: 'text-blue-900',
    chip: 'bg-blue-500 text-white',
    icon: ShieldQuestion,
  },
};

const STATUS_META = {
  open: { label: 'Aberto', cls: 'bg-gray-200 text-gray-900', icon: AlertCircle },
  in_analysis: {
    label: 'Em análise',
    cls: 'bg-yellow-200 text-yellow-900',
    icon: ClipboardCheck,
  },
  resolved: {
    label: 'Resolvido',
    cls: 'bg-emerald-200 text-emerald-900',
    icon: CheckCircle2,
  },
  wont_fix: {
    label: 'Não corrigir',
    cls: 'bg-gray-300 text-gray-800',
    icon: XCircle,
  },
};

const KIND_LABEL_PT = {
  TEACHER_DOUBLE_BOOKING: 'Conflito de professor',
  OVERLAP: 'Sobreposição na grade',
  TEMPORAL_GAP: 'Lacuna na cobertura',
  CLASS_WITHOUT_ASSIGNMENT: 'Turma sem grade',
  EXPIRED_NO_SUCCESSOR: 'Vínculo expirado sem substituto',
  ORPHAN_TEACHER: 'Professor inexistente',
  DUPLICATE_SLOT: 'Slots duplicados',
  INVERTED_VALIDITY: 'Validade invertida',
};

const WEEKDAY_PT = ['', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

// ============================================================================
// COMPONENTES
// ============================================================================
function ExecutiveHeader({ summary }) {
  if (!summary) return null;
  const high = summary.by_severity?.high || 0;
  const medium = summary.by_severity?.medium || 0;
  const low = summary.by_severity?.low || 0;
  const resolved = summary.by_status?.resolved || 0;
  const in_analysis = summary.by_status?.in_analysis || 0;
  const open_count = summary.by_status?.open || 0;
  const cards = [
    {
      label: 'Inconsistências',
      value: summary.total_issues,
      sub: `${open_count} abertas · ${in_analysis} em análise · ${resolved} resolvidas`,
      cls: 'bg-gray-100 border-gray-400 text-gray-900',
      icon: Wrench,
    },
    {
      label: 'Críticas',
      value: high,
      sub: 'bloqueiam governança',
      cls: 'bg-red-50 border-red-600 text-red-900',
      icon: AlertTriangle,
    },
    {
      label: 'Médias',
      value: medium,
      sub: 'inviabilizam validação',
      cls: 'bg-amber-50 border-amber-500 text-amber-900',
      icon: ShieldAlert,
    },
    {
      label: 'Baixas',
      value: low,
      sub: 'higiene de dados',
      cls: 'bg-blue-50 border-blue-400 text-blue-900',
      icon: ShieldQuestion,
    },
  ];
  const meta = [
    { label: 'Escolas afetadas', value: summary.affected_schools || 0 },
    { label: 'Professores afetados', value: summary.affected_teachers || 0 },
    { label: 'Turmas afetadas', value: summary.affected_classes || 0 },
  ];
  return (
    <div className="space-y-3" data-testid="executive-header">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.label}
              className={`p-4 rounded border-2 ${c.cls}`}
              data-testid={`header-card-${c.label.toLowerCase()}`}
            >
              <div className="flex items-center justify-between">
                <Icon size={16} />
                <span className="text-3xl font-bold tabular-nums leading-none">
                  {c.value}
                </span>
              </div>
              <div className="mt-1 text-sm font-semibold">{c.label}</div>
              <div className="text-[11px] opacity-70">{c.sub}</div>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-gray-600">
        {meta.map((m) => (
          <span
            key={m.label}
            className="px-3 py-1 bg-gray-100 rounded border border-gray-300"
            data-testid={`meta-${m.label.replaceAll(' ', '-').toLowerCase()}`}
          >
            <span className="font-semibold tabular-nums">{m.value}</span>{' '}
            <span className="text-gray-500">{m.label.toLowerCase()}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function IssueCard({ issue, onOpen }) {
  const sev = SEVERITY_META[issue.severity] || SEVERITY_META.low;
  const SeverityIcon = sev.icon;
  const status = issue.state?.status || 'open';
  const statusMeta = STATUS_META[status] || STATUS_META.open;
  const StatusIcon = statusMeta.icon;

  return (
    <button
      onClick={() => onOpen(issue)}
      className={`text-left w-full p-4 rounded border-2 ${sev.bg} ${sev.border} hover:shadow-md transition-all`}
      data-testid={`issue-card-${issue.fingerprint}`}
      data-severity={issue.severity}
      data-status={status}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${sev.chip}`}>
              {sev.label}
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${statusMeta.cls} inline-flex items-center gap-1`}>
              <StatusIcon size={10} />
              {statusMeta.label}
            </span>
            <span className="text-[10px] text-gray-500 uppercase">
              {KIND_LABEL_PT[issue.kind] || issue.kind}
            </span>
          </div>
          <h3 className={`text-base font-semibold ${sev.text}`}>
            <SeverityIcon size={14} className="inline mr-1.5 -mt-0.5" />
            {issue.human_title}
          </h3>
          <p className="text-sm text-gray-700 mt-1">{issue.human_summary}</p>
          {issue.impact && (
            <p className="text-xs text-gray-500 mt-2 italic">
              Impacto: {issue.impact}
            </p>
          )}
          {issue.class_name && (
            <p className="text-[11px] text-gray-500 mt-2">
              Turma:{' '}
              <span className="font-medium text-gray-700">
                {issue.class_name}
              </span>
              {issue.teacher_name && (
                <>
                  {' · '}Professor(a):{' '}
                  <span className="font-medium text-gray-700">
                    {issue.teacher_name}
                  </span>
                </>
              )}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}

function IssueDrillDown({ issue, onClose, onUpdate, busy }) {
  const [noteText, setNoteText] = useState('');
  if (!issue) return null;
  const sev = SEVERITY_META[issue.severity] || SEVERITY_META.low;
  const SeverityIcon = sev.icon;
  const state = issue.state || {};
  const status = state.status || 'open';
  const notes = state.notes || [];

  const transition = async (newStatus) => {
    await onUpdate(issue.fingerprint, { status: newStatus });
  };

  const submitNote = async () => {
    const txt = noteText.trim();
    if (!txt) return;
    await onUpdate(issue.fingerprint, { note_text: txt });
    setNoteText('');
  };

  return (
    <Sheet open={!!issue} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        className="w-full sm:max-w-2xl overflow-y-auto"
        data-testid={`issue-modal-${issue.fingerprint}`}
      >
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <SeverityIcon size={20} className={sev.text} />
            <span>{issue.human_title}</span>
          </SheetTitle>
          <SheetDescription>
            {KIND_LABEL_PT[issue.kind] || issue.kind} · severidade {sev.label}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          {/* Resumo humanizado */}
          <Card>
            <CardContent className="p-4 space-y-3">
              <p className="text-sm text-gray-800 leading-relaxed">
                {issue.human_summary}
              </p>
              {issue.impact && (
                <div className="p-3 bg-red-50 border-l-4 border-red-500 text-xs text-red-900">
                  <span className="font-semibold">Impacto:</span> {issue.impact}
                </div>
              )}
              {issue.recommendation && (
                <div className="p-3 bg-emerald-50 border-l-4 border-emerald-500 text-xs text-emerald-900">
                  <span className="font-semibold">Ação sugerida:</span>{' '}
                  {issue.recommendation}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Workflow state + ações */}
          <Card>
            <CardContent className="p-4">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-3">
                Workflow institucional
              </div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm">
                  Status atual:{' '}
                  <Badge
                    variant="outline"
                    className={STATUS_META[status]?.cls}
                  >
                    {STATUS_META[status]?.label}
                  </Badge>
                </span>
                {state.assigned_to_name && (
                  <span className="text-xs text-gray-600">
                    <UserCheck size={11} className="inline mr-1" />
                    {state.assigned_to_name}
                  </span>
                )}
              </div>
              <div
                className="flex flex-wrap gap-2"
                data-testid="workflow-actions"
              >
                {status === 'open' && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => transition('in_analysis')}
                    data-testid="action-mark-in-analysis"
                  >
                    <ClipboardCheck size={14} className="mr-1" />
                    Marcar como em análise
                  </Button>
                )}
                {(status === 'open' || status === 'in_analysis') && (
                  <>
                    <Button
                      size="sm"
                      className="bg-emerald-700 hover:bg-emerald-800 text-white"
                      disabled={busy}
                      onClick={() => transition('resolved')}
                      data-testid="action-resolve"
                    >
                      <CheckCircle2 size={14} className="mr-1" />
                      Marcar como resolvido
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => transition('wont_fix')}
                      data-testid="action-wont-fix"
                    >
                      <XCircle size={14} className="mr-1" />
                      Não corrigir
                    </Button>
                  </>
                )}
                {(status === 'resolved' || status === 'wont_fix') && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => transition('open')}
                    data-testid="action-reopen"
                  >
                    <RotateCcw size={14} className="mr-1" />
                    Reabrir
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Assignments envolvidos + links diretos */}
          {issue.assignment_ids && issue.assignment_ids.length > 0 && (
            <Card>
              <CardContent className="p-4">
                <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                  Vínculos envolvidos ({issue.assignment_ids.length})
                </div>
                <ul className="space-y-1" data-testid="assignment-list">
                  {issue.assignment_ids.map((aid) => (
                    <li
                      key={aid}
                      className="flex items-center justify-between text-xs"
                    >
                      <code className="text-gray-600">{aid.slice(0, 16)}…</code>
                      <a
                        href={`/admin/teacher-assignments?focus=${aid}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline inline-flex items-center gap-1"
                      >
                        Abrir vínculo
                        <ExternalLink size={11} />
                      </a>
                    </li>
                  ))}
                </ul>
                {(issue.weekday || issue.aula_numero) && (
                  <div className="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-700">
                    <span className="font-semibold">Slot conflitante:</span>{' '}
                    {WEEKDAY_PT[issue.weekday]} · aula {issue.aula_numero}
                  </div>
                )}
                {issue.gap_from && (
                  <div className="mt-2 text-xs text-gray-700">
                    <span className="font-semibold">Lacuna:</span>{' '}
                    {issue.gap_from} a {issue.gap_to}
                  </div>
                )}
                {issue.class_ids && issue.class_ids.length > 1 && (
                  <div className="mt-2 text-xs text-gray-700">
                    <span className="font-semibold">Turmas afetadas:</span>{' '}
                    {(issue.class_names || []).join(' · ')}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Notas append-only */}
          <Card>
            <CardContent className="p-4">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                Observações ({notes.length})
              </div>
              {notes.length > 0 && (
                <ul
                  className="space-y-2 mb-3 max-h-48 overflow-y-auto"
                  data-testid="notes-list"
                >
                  {notes.map((n, i) => (
                    <li
                      key={i}
                      className="p-2 bg-gray-50 border border-gray-200 rounded text-xs"
                    >
                      <div className="text-gray-800">{n.text}</div>
                      <div className="text-[10px] text-gray-500 mt-1">
                        {n.by_user_name || n.by_user_id} ·{' '}
                        {n.at ? new Date(n.at).toLocaleString('pt-BR') : '—'}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <Textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Adicione uma observação institucional…"
                className="text-sm"
                rows={2}
                data-testid="note-input"
              />
              <Button
                size="sm"
                className="mt-2"
                disabled={busy || !noteText.trim()}
                onClick={submitNote}
                data-testid="add-note-button"
              >
                <MessageSquarePlus size={14} className="mr-1" />
                Adicionar observação
              </Button>
            </CardContent>
          </Card>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ============================================================================
// PÁGINA PRINCIPAL
// ============================================================================
export default function GradeIntegrity() {
  const navigate = useNavigate();
  const today = new Date();

  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('all');
  const [selectedKind, setSelectedKind] = useState('all');
  const [selectedSeverity, setSelectedSeverity] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('open');
  const [academicYear, setAcademicYear] = useState(today.getFullYear());

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drillDown, setDrillDown] = useState(null);
  const [busy, setBusy] = useState(false);

  // Schools
  useEffect(() => {
    (async () => {
      try {
        const all = await schoolsAPI.getAll();
        setSchools(all.filter((s) => !s.status || s.status === 'active'));
      } catch (e) {
        console.error('Erro carregando escolas', e);
      }
    })();
  }, []);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    try {
      const params = { academic_year: academicYear };
      if (selectedSchool !== 'all') params.school_id = selectedSchool;
      const res = await axios.get(
        `${API}/teacher-class-assignments/integrity-report`,
        { params },
      );
      setData(res.data);
    } catch (e) {
      console.error('Erro carregando integrity-report', e);
      toast.error('Falha ao carregar relatório de integridade.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [academicYear, selectedSchool]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  // Update state local após mudança
  const updateIssueState = useCallback(
    async (fingerprint, patch) => {
      setBusy(true);
      try {
        const res = await axios.post(
          `${API}/teacher-class-assignments/integrity-report/issues/${fingerprint}/state`,
          patch,
        );
        // Atualiza state local da issue
        setData((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            issues: prev.issues.map((it) =>
              it.fingerprint === fingerprint ? { ...it, state: res.data } : it,
            ),
          };
        });
        setDrillDown((cur) =>
          cur && cur.fingerprint === fingerprint
            ? { ...cur, state: res.data }
            : cur,
        );
        toast.success('Workflow atualizado.');
      } catch (e) {
        console.error(e);
        const msg =
          e.response?.data?.detail || 'Falha ao atualizar o estado da issue.';
        toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  // Filtros locais (frontend não recalcula, só filtra a apresentação)
  const filteredIssues = useMemo(() => {
    if (!data?.issues) return [];
    let r = data.issues;
    if (selectedKind !== 'all') r = r.filter((it) => it.kind === selectedKind);
    if (selectedSeverity !== 'all')
      r = r.filter((it) => it.severity === selectedSeverity);
    if (selectedStatus !== 'all')
      r = r.filter((it) => (it.state?.status || 'open') === selectedStatus);
    // Ordenar por severidade (high > medium > low) e depois por kind
    const sevOrder = { high: 0, medium: 1, low: 2 };
    return [...r].sort((a, b) => {
      const sa = sevOrder[a.severity] ?? 9;
      const sb = sevOrder[b.severity] ?? 9;
      if (sa !== sb) return sa - sb;
      return (a.kind || '').localeCompare(b.kind || '');
    });
  }, [data, selectedKind, selectedSeverity, selectedStatus]);

  return (
    <Layout>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/dashboard')}
              data-testid="back-button"
            >
              <ArrowLeft size={16} />
            </Button>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                Integridade da Grade Horária
              </h1>
              <p className="text-sm text-gray-600 mt-0.5">
                Painel de saneamento institucional. Cada card é tarefa
                executável.
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchReport}
            disabled={loading}
            data-testid="refresh-button"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin mr-1" />
            ) : (
              <RefreshCw size={14} className="mr-1" />
            )}
            Atualizar
          </Button>
        </div>

        {/* Executive header */}
        {!loading && data && <ExecutiveHeader summary={data.summary} />}
        {loading && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        )}

        {/* Filtros */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Filter size={14} className="text-gray-500" />
              <span className="text-xs uppercase tracking-wide text-gray-500 font-medium">
                Filtros
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Escola
                </label>
                <Select
                  value={selectedSchool}
                  onValueChange={setSelectedSchool}
                >
                  <SelectTrigger data-testid="filter-school">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    {schools.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Tipo de problema
                </label>
                <Select value={selectedKind} onValueChange={setSelectedKind}>
                  <SelectTrigger data-testid="filter-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    {Object.entries(KIND_LABEL_PT).map(([k, lbl]) => (
                      <SelectItem key={k} value={k}>
                        {lbl}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Severidade
                </label>
                <Select
                  value={selectedSeverity}
                  onValueChange={setSelectedSeverity}
                >
                  <SelectTrigger data-testid="filter-severity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="high">Crítico</SelectItem>
                    <SelectItem value="medium">Médio</SelectItem>
                    <SelectItem value="low">Baixo</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Situação
                </label>
                <Select
                  value={selectedStatus}
                  onValueChange={setSelectedStatus}
                >
                  <SelectTrigger data-testid="filter-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="open">Abertas</SelectItem>
                    <SelectItem value="in_analysis">Em análise</SelectItem>
                    <SelectItem value="resolved">Resolvidas</SelectItem>
                    <SelectItem value="wont_fix">Não corrigir</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Ano letivo
                </label>
                <Select
                  value={String(academicYear)}
                  onValueChange={(v) => setAcademicYear(parseInt(v, 10))}
                >
                  <SelectTrigger data-testid="filter-year">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[today.getFullYear() - 1, today.getFullYear(), today.getFullYear() + 1].map(
                      (y) => (
                        <SelectItem key={y} value={String(y)}>
                          {y}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="mt-3 text-xs text-gray-500">
              <span className="font-semibold tabular-nums">
                {filteredIssues.length}
              </span>{' '}
              issue(s) exibida(s) após filtros.
            </div>
          </CardContent>
        </Card>

        {/* Lista de issues */}
        {!loading && (
          <div className="space-y-2" data-testid="issues-list">
            {filteredIssues.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center text-sm text-gray-500">
                  <CheckCircle2
                    className="mx-auto mb-2 text-emerald-500"
                    size={32}
                  />
                  Nenhuma inconsistência encontrada com os filtros aplicados.
                </CardContent>
              </Card>
            ) : (
              filteredIssues.map((it) => (
                <IssueCard
                  key={it.fingerprint}
                  issue={it}
                  onOpen={setDrillDown}
                />
              ))
            )}
          </div>
        )}

        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        )}

        {/* Drill-down */}
        <IssueDrillDown
          issue={drillDown}
          onClose={() => setDrillDown(null)}
          onUpdate={updateIssueState}
          busy={busy}
        />
      </div>
    </Layout>
  );
}
