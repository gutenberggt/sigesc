/**
 * Calendário Operacional do Diário — Fase 5 (Mai/2026)
 *
 * Ferramenta de governança visual. Renderizador SEMÂNTICO PURO:
 *   - NÃO calcula nada localmente.
 *   - Apenas mapeia status do backend para a paleta definida
 *     em /app/design_guidelines.json.
 *
 * Endpoint consumido:
 *   GET /api/calendar/diary-state/{class_id}?from=YYYY-MM-DD&to=YYYY-MM-DD
 *
 * Diretrizes obrigatórias:
 *   - Default: escola do usuário + ano corrente + mês corrente.
 *   - Lazy loading por navegação (1 mês por vez).
 *   - `not_expected` quase invisível.
 *   - `inconsistent` impossível de ignorar.
 *   - Cores NUNCA são o único veículo semântico (ícone + label + tooltip).
 */
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import usePermissions from '@/hooks/usePermissions';
import { schoolsAPI, classesAPI } from '@/services/api';
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
import {
  AlertTriangle,
  CircleSlash,
  CheckCircle2,
  CircleHelp,
  RefreshCcw,
  ShieldCheck,
  CircleDot,
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Filter,
  ArrowLeft,
  EyeOff,
  Loader2,
  FileSignature,
} from 'lucide-react';
import { toast } from 'sonner';
import SnapshotsDrawer from '@/components/diary/SnapshotsDrawer';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${API_URL}/api`;

// ============================================================================
// Paleta SEMÂNTICA (espelha /app/design_guidelines.json).
// Cada estado carrega: cor (bg/border/text/indicator), ícone, label, peso.
// O frontend NUNCA decide qual estado um dia tem. Apenas mapeia.
// ============================================================================
const STATUS_META = {
  inconsistent: {
    label: 'Inconsistente',
    weight: 7,
    bg: 'bg-red-50',
    border: 'border-red-600',
    text: 'text-red-900',
    indicator: 'bg-red-600',
    icon: AlertTriangle,
    description: 'Foram encontrados registros fora do horário esperado.',
  },
  empty: {
    label: 'Vazio (pendente)',
    weight: 6,
    bg: 'bg-amber-50',
    border: 'border-amber-600',
    text: 'text-amber-900',
    indicator: 'bg-amber-600',
    icon: CircleSlash,
    description: 'Havia aula esperada e nada foi lançado.',
  },
  validated: {
    label: 'Validado',
    weight: 5,
    bg: 'bg-emerald-50',
    border: 'border-emerald-700',
    text: 'text-emerald-900',
    indicator: 'bg-emerald-700',
    icon: ShieldCheck,
    description: 'Frequência conferida pela coordenação.',
  },
  corrected: {
    label: 'Corrigido',
    weight: 4,
    bg: 'bg-blue-50',
    border: 'border-blue-500',
    text: 'text-blue-900',
    indicator: 'bg-blue-500',
    icon: RefreshCcw,
    description: 'Conteúdo retificado com trilha de auditoria.',
  },
  partial: {
    label: 'Parcial',
    weight: 3,
    bg: 'bg-amber-50/40',
    border: 'border-gray-400 border-dashed',
    text: 'text-gray-800',
    indicator: 'bg-gradient-to-r from-amber-400 to-gray-400',
    icon: CircleDot,
    description: 'Alguns slots cumpridos, outros pendentes.',
  },
  complete: {
    label: 'Completo',
    weight: 2,
    bg: 'bg-white',
    border: 'border-emerald-400',
    text: 'text-emerald-800',
    indicator: 'bg-emerald-400',
    icon: CheckCircle2,
    description: 'Todos os slots do dia foram cumpridos.',
  },
  not_expected: {
    label: 'Sem aula',
    weight: 1,
    bg: 'bg-transparent',
    border: 'border-gray-200',
    text: 'text-gray-400',
    indicator: '',
    icon: EyeOff,
    description: 'Sem expectativa de aula (fim de semana ou sem grade).',
  },
  non_school: {
    label: 'Não-letivo',
    weight: 0,
    bg: 'bg-gray-100',
    border: 'border-gray-300',
    text: 'text-gray-500',
    indicator: '',
    icon: EyeOff,
    description: 'Feriado ou recesso (calendário institucional).',
  },
};

// Tradução PT-BR dos valores brutos vindos do backend (frequência e conteúdo).
// Frontend só mapeia — nunca decide o estado.
const ATTENDANCE_STATUS_LABEL = {
  missing: 'Pendente',
  completed: 'Lançada',
  validated: 'Validada',
  corrected: 'Corrigida',
};

const CONTENT_STATUS_LABEL = {
  missing: 'Pendente',
  published: 'Publicado',
  corrected: 'Corrigido',
};

const STATUS_ORDER_SEVERITY = [  'inconsistent',
  'empty',
  'validated',
  'corrected',
  'partial',
  'complete',
  'not_expected',
  'non_school',
];

const WEEK_LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function isoToParts(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m, d };
}

function monthFirstISO(year, month1) {
  const m = String(month1).padStart(2, '0');
  return `${year}-${m}-01`;
}

function monthLastISO(year, month1) {
  // month1: 1-12. Last day = new Date(year, month1, 0).getDate()
  const last = new Date(year, month1, 0).getDate();
  return `${year}-${String(month1).padStart(2, '0')}-${String(last).padStart(2, '0')}`;
}

function monthLabel(year, month1) {
  const names = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
  ];
  return `${names[month1 - 1]} ${year}`;
}

// Constroi grid 7 colunas. Segunda = primeira coluna (ISO weekday=1).
function buildMonthGrid(year, month1, days) {
  const firstISO = monthFirstISO(year, month1);
  const lastISO = monthLastISO(year, month1);
  const firstDate = new Date(`${firstISO}T00:00:00`);
  // ISO weekday: Mon=1..Sun=7. JS: Sun=0..Sat=6 → converter.
  const firstWeekday = ((firstDate.getDay() + 6) % 7) + 1; // 1..7
  const padBefore = firstWeekday - 1;
  const dayByISO = new Map(days.map((d) => [d.date, d]));
  const cells = [];
  for (let i = 0; i < padBefore; i++) cells.push(null);
  for (let day = 1; day <= isoToParts(lastISO).d; day++) {
    const iso = `${year}-${String(month1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    cells.push(dayByISO.get(iso) || {
      date: iso,
      weekday: ((new Date(`${iso}T00:00:00`).getDay() + 6) % 7) + 1,
      status: 'not_expected',
      expected_slots: 0,
      entries: [],
      has_orphan_evidence: false,
    });
  }
  // pad tail para fechar última semana
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

// ============================================================================
// COMPONENTES INTERNOS
// ============================================================================

function Legend() {
  return (
    <div
      className="flex flex-wrap items-center gap-3 text-xs"
      data-testid="calendar-legend"
    >
      <span className="text-gray-500 font-medium uppercase tracking-wide mr-1">
        Legenda:
      </span>
      {STATUS_ORDER_SEVERITY.map((s) => {
        const meta = STATUS_META[s];
        const Icon = meta.icon;
        return (
          <span
            key={s}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border bg-white"
            data-testid={`legend-${s}`}
          >
            <span
              className={`inline-block w-2 h-2 rounded-sm ${meta.indicator}`}
              aria-hidden="true"
            />
            <Icon size={12} className={meta.text} />
            <span className={`${meta.text} font-medium`}>{meta.label}</span>
          </span>
        );
      })}
    </div>
  );
}

function SummaryChips({ summary, severityFilter, onSeverityChange }) {
  const dsc = summary?.day_status_counts || {};
  const total =
    (dsc.complete || 0) +
    (dsc.partial || 0) +
    (dsc.empty || 0) +
    (dsc.corrected || 0) +
    (dsc.inconsistent || 0) +
    (dsc.validated || 0) +
    (dsc.not_expected || 0);
  const pendentes = dsc.empty || 0;
  const inconsistencias = dsc.inconsistent || 0;
  const completos = (dsc.complete || 0) + (dsc.corrected || 0);
  const validados = dsc.validated || 0;

  const chips = [
    {
      key: 'all',
      label: 'Todos os dias',
      value: total - (dsc.not_expected || 0),
      sub: 'com aula esperada',
      cls: 'bg-gray-100 text-gray-900 border-gray-300',
      icon: CalendarRange,
    },
    {
      key: 'validated',
      label: 'Validados',
      value: validados,
      sub: 'homologados pela coordenação',
      cls: 'bg-emerald-100 text-emerald-900 border-emerald-700 font-semibold',
      icon: ShieldCheck,
    },
    {
      key: 'complete',
      label: 'Completos',
      value: completos,
      sub: 'aguardando validação',
      cls: 'bg-emerald-50 text-emerald-900 border-emerald-300',
      icon: CheckCircle2,
    },
    {
      key: 'empty',
      label: 'Pendentes',
      value: pendentes,
      sub: 'dia sem lançamento',
      cls: 'bg-amber-50 text-amber-900 border-amber-400',
      icon: CircleSlash,
    },
    {
      key: 'inconsistent',
      label: 'Inconsistências',
      value: inconsistencias,
      sub: 'registro fora do horário esperado',
      cls: 'bg-red-50 text-red-900 border-red-500',
      icon: AlertTriangle,
    },
  ];

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-5 gap-3"
      data-testid="summary-bar"
    >
      {chips.map((chip) => {
        const Icon = chip.icon;
        const isActive = severityFilter === chip.key;
        return (
          <button
            key={chip.key}
            onClick={() =>
              onSeverityChange(isActive ? 'all' : chip.key)
            }
            className={`text-left px-4 py-3 rounded border-2 transition-all hover:shadow-sm ${
              isActive ? 'ring-2 ring-offset-1 ring-gray-900' : ''
            } ${chip.cls}`}
            data-testid={`summary-metric-${chip.key}`}
          >
            <div className="flex items-center justify-between">
              <Icon size={16} />
              <span className="text-2xl font-bold tabular-nums leading-none">
                {chip.value}
              </span>
            </div>
            <div className="mt-1 text-sm font-semibold">{chip.label}</div>
            <div className="text-[11px] opacity-70">{chip.sub}</div>
          </button>
        );
      })}
    </div>
  );
}

function StatusIndicators({ entries }) {
  // Compacto: max 3 indicadores (badges com aula_numero + status)
  if (!entries || entries.length === 0) return null;
  const limited = entries.slice(0, 3);
  return (
    <div className="flex items-center gap-0.5 flex-wrap mt-1">
      {limited.map((e, idx) => {
        // Cor do indicador depende do par (attendance_status, content_status)
        let bg = 'bg-gray-300';
        if (
          (e.attendance_status === 'completed' ||
            e.attendance_status === 'validated') &&
          (e.content_status === 'published' || e.content_status === 'corrected')
        ) {
          bg = 'bg-emerald-500';
        } else if (
          e.attendance_status === 'missing' &&
          e.content_status === 'missing'
        ) {
          bg = 'bg-amber-500';
        } else {
          bg = 'bg-amber-300';
        }
        return (
          <span
            key={idx}
            className={`inline-block h-1.5 rounded-sm ${bg}`}
            style={{ width: 14 }}
            aria-hidden="true"
          />
        );
      })}
      {entries.length > 3 && (
        <span className="text-[10px] text-gray-500 ml-1">
          +{entries.length - 3}
        </span>
      )}
    </div>
  );
}

function DayCell({ day, onClick }) {
  if (!day) return <div className="border-r border-b border-gray-200 bg-gray-50/40" />;
  const meta = STATUS_META[day.status] || STATUS_META.not_expected;
  const Icon = meta.icon;
  const dayNum = parseInt(day.date.split('-')[2], 10);
  const isNotExpected = day.status === 'not_expected';
  const isInconsistent = day.status === 'inconsistent';

  return (
    <button
      type="button"
      onClick={() => onClick(day)}
      className={`relative text-left border-r border-b border-gray-200 min-h-[120px] p-2 transition-all
        ${meta.bg} ${meta.border}
        ${isNotExpected ? 'opacity-50' : ''}
        ${isInconsistent ? 'ring-2 ring-red-600 ring-inset z-10' : ''}
        hover:shadow-md hover:z-20 hover:scale-[1.01]
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:z-20`}
      data-testid={`calendar-day-${day.date}`}
      data-status={day.status}
      aria-label={`${day.date} — ${meta.label}. ${meta.description}`}
      title={`${meta.label}: ${meta.description}`}
    >
      <div className="flex items-start justify-between">
        <span className={`text-sm font-semibold tabular-nums ${meta.text}`}>
          {dayNum}
        </span>
        <Icon size={14} className={`${meta.text} flex-shrink-0`} />
      </div>
      {!isNotExpected && (
        <div className={`mt-1 text-[10px] uppercase tracking-wide font-medium ${meta.text}`}>
          {meta.label}
        </div>
      )}
      {day.expected_slots > 0 && (
        <div className="text-[10px] text-gray-600 mt-0.5 tabular-nums">
          {day.expected_slots} {day.expected_slots === 1 ? 'aula' : 'aulas'}
        </div>
      )}
      <StatusIndicators entries={day.entries} />
      {day.has_orphan_evidence && (
        <span
          className="absolute bottom-1 right-1 text-red-600"
          title="Registros fora do horário esperado"
        >
          <AlertTriangle size={12} />
        </span>
      )}
    </button>
  );
}

function MobileDayRow({ day, onClick }) {
  if (day.status === 'not_expected') return null;
  const meta = STATUS_META[day.status];
  const Icon = meta.icon;
  const dt = new Date(`${day.date}T00:00:00`);
  const wd = WEEK_LABELS[((dt.getDay() + 6) % 7)];
  const dayNum = parseInt(day.date.split('-')[2], 10);
  return (
    <button
      onClick={() => onClick(day)}
      className={`w-full text-left p-3 rounded border-2 ${meta.bg} ${meta.border} ${meta.text}
        flex items-center gap-3 active:scale-[0.99] transition`}
      data-testid={`mobile-day-${day.date}`}
    >
      <div className="flex flex-col items-center w-12 flex-shrink-0">
        <span className="text-[10px] uppercase">{wd}</span>
        <span className="text-xl font-bold tabular-nums leading-none">
          {dayNum}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Icon size={14} />
          <span className="text-sm font-semibold">{meta.label}</span>
        </div>
        <div className="text-[11px] opacity-80 mt-0.5">
          {day.expected_slots} {day.expected_slots === 1 ? 'aula' : 'aulas'} esperada{day.expected_slots === 1 ? '' : 's'}
          {day.has_orphan_evidence && ' · evidência órfã'}
        </div>
      </div>
      <ChevronRight size={16} className="opacity-50" />
    </button>
  );
}

function DayDrillDown({ day, onClose, onValidate, onUnvalidate, busyIds }) {
  if (!day) return null;
  const meta = STATUS_META[day.status];
  const Icon = meta.icon;
  return (
    <Sheet open={!!day} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        className="w-full sm:max-w-lg overflow-y-auto"
        data-testid={`day-modal-${day.date}`}
      >
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Icon size={20} className={meta.text} />
            <span>{day.date}</span>
            <Badge variant="outline" className={`${meta.text}`}>
              {meta.label}
            </Badge>
          </SheetTitle>
          <SheetDescription>{meta.description}</SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4">
          <Card>
            <CardContent className="p-4">
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                Resumo
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-gray-500">Aulas esperadas</div>
                  <div className="text-2xl font-bold tabular-nums">
                    {day.expected_slots}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500">Evidência órfã</div>
                  <div className="text-2xl font-bold tabular-nums">
                    {day.has_orphan_evidence ? 'Sim' : 'Não'}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {day.entries && day.entries.length > 0 ? (
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                Slots do dia ({day.entries.length})
              </div>
              <div className="space-y-2" data-testid="day-entries-list">
                {day.entries.map((e, idx) => {
                  const ok =
                    (e.attendance_status === 'completed' ||
                      e.attendance_status === 'validated') &&
                    (e.content_status === 'published' ||
                      e.content_status === 'corrected');
                  return (
                    <div
                      key={idx}
                      className={`p-3 rounded border ${
                        ok
                          ? 'border-emerald-300 bg-emerald-50/40'
                          : 'border-amber-300 bg-amber-50/40'
                      }`}
                      data-testid={`day-entry-${idx}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm">
                          Aula {e.aula_numero}
                        </span>
                        <div className="flex items-center gap-1">
                          {e.matched_by === 'flexible' && (
                            <Badge
                              variant="outline"
                              className="text-[10px] border-blue-400 text-blue-800 bg-blue-50/60"
                              title={
                                e.flexible_match_reason === 'same_teacher_same_day'
                                  ? 'Registro validado semanticamente: mesmo professor, mesma data.'
                                  : e.flexible_match_reason === 'same_component_same_day'
                                  ? 'Registro validado semanticamente: mesmo componente, mesma data.'
                                  : 'Registro validado semanticamente para a etapa pedagógica desta turma.'
                              }
                              data-testid="flexible-match-badge"
                            >
                              Correspondência flexível
                            </Badge>
                          )}
                          {e.is_substitute && (
                            <Badge variant="outline" className="text-[10px]">
                              Substituto
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-gray-700 mt-1">
                        Professor:{' '}
                        <span className="font-medium">
                          {e.teacher_name || e.teacher_id || '—'}
                        </span>
                      </div>
                      {e.component_name && (
                        <div className="text-xs text-gray-600">
                          Componente:{' '}
                          <span className="font-medium">
                            {e.component_name}
                          </span>
                        </div>
                      )}
                      {(e.slot_start || e.slot_end) && (
                        <div className="text-xs text-gray-500 tabular-nums">
                          {e.slot_start} — {e.slot_end}
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-2 mt-2 text-[11px]">
                        <div className="flex items-center gap-1">
                          <span className="text-gray-500">Frequência:</span>
                          <Badge
                            variant="outline"
                            className={
                              e.attendance_status === 'missing'
                                ? 'text-amber-700 border-amber-300'
                                : e.attendance_status === 'validated'
                                ? 'text-emerald-800 border-emerald-500 font-semibold'
                                : 'text-emerald-700 border-emerald-300'
                            }
                          >
                            {ATTENDANCE_STATUS_LABEL[e.attendance_status] || e.attendance_status}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-gray-500">Conteúdo:</span>
                          <Badge
                            variant="outline"
                            className={
                              e.content_status === 'missing'
                                ? 'text-amber-700 border-amber-300'
                                : e.content_status === 'corrected'
                                ? 'text-blue-700 border-blue-300'
                                : 'text-emerald-700 border-emerald-300'
                            }
                          >
                            {CONTENT_STATUS_LABEL[e.content_status] || e.content_status}
                          </Badge>
                        </div>
                      </div>

                      {/* Fase 7 — Painel de Validação Institucional */}
                      {e.attendance_id && (
                        <div
                          className="mt-3 pt-3 border-t border-gray-200"
                          data-testid={`validation-panel-${e.attendance_id}`}
                        >
                          {e.attendance_status === 'validated' ? (
                            <div className="space-y-1">
                              <div className="flex items-center gap-1.5 text-[11px] text-emerald-800">
                                <ShieldCheck size={12} />
                                <span className="font-medium">
                                  Validado por {e.validated_by_name || '—'}
                                </span>
                              </div>
                              {e.validated_at && (
                                <div className="text-[10px] text-gray-500 ml-4">
                                  em{' '}
                                  {new Date(e.validated_at).toLocaleString(
                                    'pt-BR',
                                    {
                                      day: '2-digit',
                                      month: '2-digit',
                                      year: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    },
                                  )}
                                </div>
                              )}
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-[10px] h-6 px-2 mt-1 text-gray-500 hover:text-red-700"
                                disabled={busyIds.has(e.attendance_id)}
                                onClick={() => onUnvalidate(e.attendance_id)}
                                data-testid={`unvalidate-button-${e.attendance_id}`}
                              >
                                {busyIds.has(e.attendance_id) ? (
                                  <Loader2 size={10} className="animate-spin" />
                                ) : (
                                  'Reverter validação'
                                )}
                              </Button>
                            </div>
                          ) : (
                            e.attendance_status === 'completed' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="w-full text-[11px] h-7 border-emerald-300 text-emerald-800 hover:bg-emerald-50"
                                disabled={busyIds.has(e.attendance_id)}
                                onClick={() => onValidate(e.attendance_id)}
                                data-testid={`validate-button-${e.attendance_id}`}
                              >
                                {busyIds.has(e.attendance_id) ? (
                                  <Loader2 size={12} className="animate-spin mr-1" />
                                ) : (
                                  <ShieldCheck size={12} className="mr-1" />
                                )}
                                Validar institucionalmente
                              </Button>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="text-sm text-gray-500 italic text-center py-4">
              Nenhum slot esperado pela grade nesta data.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function OrphanEvidenceList({ summary }) {
  const orphAtt = summary?.orphan_attendance_dates || [];
  const orphCon = summary?.orphan_content_dates || [];
  if (orphAtt.length === 0 && orphCon.length === 0) return null;
  return (
    <Card
      className="border-red-300 bg-red-50/50"
      data-testid="orphan-evidence-list"
    >
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle size={16} className="text-red-700" />
          <h3 className="text-sm font-semibold text-red-900">
            Registros fora do horário esperado
          </h3>
        </div>
        <p className="text-xs text-red-800 mb-3">
          Lançamentos detectados em datas SEM expectativa pela grade. Indica
          erro de grade ou lançamento equivocado.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {orphAtt.length > 0 && (
            <div>
              <div className="font-medium text-red-900 mb-1">
                Frequência ({orphAtt.length})
              </div>
              <ul className="space-y-0.5 max-h-32 overflow-y-auto">
                {orphAtt.map((d) => (
                  <li key={d} className="tabular-nums text-red-800">
                    · {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {orphCon.length > 0 && (
            <div>
              <div className="font-medium text-red-900 mb-1">
                Conteúdo ({orphCon.length})
              </div>
              <ul className="space-y-0.5 max-h-32 overflow-y-auto">
                {orphCon.map((d) => (
                  <li key={d} className="tabular-nums text-red-800">
                    · {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// PÁGINA PRINCIPAL
// ============================================================================
export default function DiaryCalendar() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const perms = usePermissions();

  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1); // 1..12

  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [drillDown, setDrillDown] = useState(null);
  const [severityFilter, setSeverityFilter] = useState('all');
  const [busyValidationIds, setBusyValidationIds] = useState(() => new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  const [snapshotsDrawerOpen, setSnapshotsDrawerOpen] = useState(false);

  const abortRef = useRef(null);
  const defaultedRef = useRef(false);

  // ---------- Carrega escolas (role-aware) ----------
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const all = await schoolsAPI.getAll();
        const active = all.filter((s) => !s.status || s.status === 'active');
        // Professor: limita às escolas vinculadas
        let visible = active;
        if (perms.isProfessor || (!perms.isAdmin && !perms.isSemed)) {
          const linked = new Set(perms.userSchoolIds || []);
          if (linked.size > 0) {
            visible = active.filter((s) => linked.has(s.id));
          }
        }
        if (!mounted) return;
        setSchools(visible);
        // Default: 1a escola visível (one-shot)
        if (!defaultedRef.current && visible.length > 0) {
          defaultedRef.current = true;
          setSelectedSchool(visible[0].id);
        }
      } catch (e) {
        console.error('Erro carregando escolas', e);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [perms.isProfessor, perms.isAdmin, perms.isSemed, perms.userSchoolIds]);

  // ---------- Carrega turmas quando escola muda ----------
  useEffect(() => {
    let mounted = true;
    if (!selectedSchool) {
      setClasses([]);
      setSelectedClass('');
      return;
    }
    (async () => {
      try {
        const all = await classesAPI.getAll(selectedSchool);
        const filtered = all.filter(
          (c) => c.academic_year === year || !c.academic_year
        );
        if (!mounted) return;
        setClasses(filtered);
        if (filtered.length > 0) {
          setSelectedClass((cur) =>
            filtered.find((c) => c.id === cur) ? cur : filtered[0].id
          );
        } else {
          setSelectedClass('');
        }
      } catch (e) {
        console.error('Erro carregando turmas', e);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [selectedSchool, year]);

  // ---------- Carrega estado do diário ----------
  const fetchState = useCallback(async () => {
    if (!selectedClass) {
      setData(null);
      return;
    }
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const from = monthFirstISO(year, month);
      const to = monthLastISO(year, month);
      const res = await axios.get(
        `${API}/calendar/diary-state/${selectedClass}`,
        { params: { from, to }, signal: controller.signal }
      );
      setData(res.data);
    } catch (e) {
      if (axios.isCancel(e) || e.name === 'CanceledError') return;
      console.error('Erro carregando calendário', e);
      setError(
        e.response?.data?.detail ||
          'Não foi possível carregar o calendário operacional.'
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedClass, year, month]);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  // ---------- Fase 7 — Validação Institucional ----------
  const markBusy = (id, busy) => {
    setBusyValidationIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const handleValidate = useCallback(
    async (attendanceId) => {
      markBusy(attendanceId, true);
      try {
        await axios.post(`${API}/attendance/${attendanceId}/validate`);
        toast.success('Frequência validada institucionalmente.');
        await fetchState();
        // Atualiza drilldown ativo, se houver
        setDrillDown((cur) => {
          if (!cur) return cur;
          return { ...cur, _refresh: Date.now() };
        });
      } catch (e) {
        const d = e.response?.data?.detail;
        const msg =
          typeof d === 'object'
            ? d?.message || JSON.stringify(d)
            : d || 'Falha ao validar.';
        toast.error(msg);
      } finally {
        markBusy(attendanceId, false);
      }
    },
    [fetchState],
  );

  const handleUnvalidate = useCallback(
    async (attendanceId) => {
      const rationale = window.prompt(
        'Justifique a reversão (mínimo 30 caracteres):',
      );
      if (!rationale) return;
      if (rationale.trim().length < 30) {
        toast.error('Justificativa deve ter ao menos 30 caracteres.');
        return;
      }
      markBusy(attendanceId, true);
      try {
        await axios.post(`${API}/attendance/${attendanceId}/unvalidate`, {
          rationale,
        });
        toast.success('Validação revertida com auditoria registrada.');
        await fetchState();
      } catch (e) {
        const d = e.response?.data?.detail;
        const msg =
          typeof d === 'object'
            ? d?.message || JSON.stringify(d)
            : d || 'Falha ao reverter validação.';
        toast.error(msg);
      } finally {
        markBusy(attendanceId, false);
      }
    },
    [fetchState],
  );

  const handleBatchValidate = useCallback(async () => {
    if (!selectedClass || !data?.days) return;
    // Coleta dias `complete` (não validados ainda)
    const eligibleDates = data.days
      .filter((d) => d.status === 'complete' || d.status === 'corrected')
      .map((d) => d.date);
    if (eligibleDates.length === 0) {
      toast.info('Nenhum dia elegível para validação em lote.');
      return;
    }
    if (
      !window.confirm(
        `Validar institucionalmente ${eligibleDates.length} dia(s)? ` +
          'Cada validação será registrada individualmente em auditoria.',
      )
    ) {
      return;
    }
    setBatchBusy(true);
    try {
      const res = await axios.post(`${API}/attendance/validate-batch`, {
        class_id: selectedClass,
        dates: eligibleDates,
      });
      const { total_validated, total_skipped } = res.data;
      toast.success(
        `${total_validated} validações institucionais registradas` +
          (total_skipped > 0 ? ` (${total_skipped} ignoradas)` : ''),
      );
      await fetchState();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg =
        typeof d === 'object'
          ? d?.message || JSON.stringify(d)
          : d || 'Falha na validação em lote.';
      toast.error(msg);
    } finally {
      setBatchBusy(false);
    }
  }, [selectedClass, data, fetchState]);

  // ---------- Navegação de mês ----------
  const goPrev = () => {
    if (month === 1) {
      setMonth(12);
      setYear(year - 1);
    } else setMonth(month - 1);
  };
  const goNext = () => {
    if (month === 12) {
      setMonth(1);
      setYear(year + 1);
    } else setMonth(month + 1);
  };
  const goToday = () => {
    setYear(today.getFullYear());
    setMonth(today.getMonth() + 1);
  };

  // ---------- Filtra dias para visualização (severity filter) ----------
  const filteredDays = useMemo(() => {
    if (!data?.days) return [];
    if (severityFilter === 'all') return data.days;
    if (severityFilter === 'complete') {
      return data.days.map((d) => ({
        ...d,
        _dimmed: !(d.status === 'complete' || d.status === 'corrected'),
      }));
    }
    return data.days.map((d) => ({
      ...d,
      _dimmed: d.status !== severityFilter,
    }));
  }, [data, severityFilter]);

  const grid = useMemo(
    () => buildMonthGrid(year, month, filteredDays),
    [year, month, filteredDays]
  );

  const mobileSorted = useMemo(() => {
    if (!data?.days) return [];
    return [...data.days].sort((a, b) => {
      const wa = STATUS_META[a.status]?.weight ?? 0;
      const wb = STATUS_META[b.status]?.weight ?? 0;
      if (wb !== wa) return wb - wa;
      return a.date.localeCompare(b.date);
    });
  }, [data]);

  // ---------- Render ----------
  return (
    <Layout>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/dashboard')}
                data-testid="back-button"
              >
                <ArrowLeft size={16} />
              </Button>
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                Calendário Operacional do Diário
              </h1>
            </div>
            <p className="text-sm text-gray-600 mt-1 ml-9">
              Onde agir hoje? Painel de pendências, inconsistências e
              evidências de cumprimento institucional.
            </p>
          </div>
          {/* Fase 7 — Botão de validação em lote */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Fase 8 — Botão de Snapshot/Documento Institucional */}
            {selectedClass && (perms.isAdmin || perms.isSecretario || perms.isDiretor || perms.isCoordenador || perms.isGerente || perms.isSuperAdmin) && (
              <Button
                variant="outline"
                onClick={() => setSnapshotsDrawerOpen(true)}
                className="border-emerald-700 text-emerald-800 hover:bg-emerald-50"
                data-testid="open-snapshots-drawer-button"
              >
                <FileSignature size={16} className="mr-2" />
                Documento do período
              </Button>
            )}
            {data?.summary?.day_status_counts?.complete > 0 && (
              <Button
                onClick={handleBatchValidate}
                disabled={batchBusy || !selectedClass}
                className="bg-emerald-700 hover:bg-emerald-800 text-white"
                data-testid="batch-validate-button"
              >
                {batchBusy ? (
                  <Loader2 size={16} className="animate-spin mr-2" />
                ) : (
                  <ShieldCheck size={16} className="mr-2" />
                )}
                Validar período (
                {(data.summary.day_status_counts.complete || 0) +
                  (data.summary.day_status_counts.corrected || 0)}
                )
              </Button>
            )}
          </div>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Filter size={14} className="text-gray-500" />
              <span className="text-xs uppercase tracking-wide text-gray-500 font-medium">
                Filtros
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Escola
                </label>
                <Select
                  value={selectedSchool}
                  onValueChange={setSelectedSchool}
                >
                  <SelectTrigger data-testid="filter-school">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
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
                  Turma
                </label>
                <Select
                  value={selectedClass}
                  onValueChange={setSelectedClass}
                  disabled={!selectedSchool || classes.length === 0}
                >
                  <SelectTrigger data-testid="filter-class">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {classes.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Ano letivo
                </label>
                <Select
                  value={String(year)}
                  onValueChange={(v) => setYear(parseInt(v, 10))}
                >
                  <SelectTrigger data-testid="filter-year">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[year - 1, year, year + 1].map((y) => (
                      <SelectItem key={y} value={String(y)}>
                        {y}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-600 mb-1 block">
                  Período (1 mês)
                </label>
                <div
                  className="flex items-center gap-1"
                  data-testid="month-navigator"
                >
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={goPrev}
                    title="Mês anterior"
                    data-testid="prev-month-button"
                  >
                    <ChevronLeft size={16} />
                  </Button>
                  <div className="flex-1 text-center text-sm font-semibold py-2 px-2 bg-gray-50 rounded border tabular-nums">
                    {monthLabel(year, month)}
                  </div>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={goNext}
                    title="Próximo mês"
                    data-testid="next-month-button"
                  >
                    <ChevronRight size={16} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={goToday}
                    title="Mês atual"
                    data-testid="today-button"
                  >
                    Hoje
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Summary chips */}
        {data && !loading && (
          <SummaryChips
            summary={data.summary}
            severityFilter={severityFilter}
            onSeverityChange={setSeverityFilter}
          />
        )}

        {/* Legend */}
        {data && !loading && <Legend />}

        {/* Erros */}
        {error && (
          <Card
            className="border-red-300 bg-red-50"
            data-testid="error-card"
          >
            <CardContent className="p-4 text-sm text-red-900">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle size={16} />
                Erro
              </div>
              <div className="mt-1">{error}</div>
            </CardContent>
          </Card>
        )}

        {/* Estado vazio (sem turma) */}
        {!selectedClass && !loading && !error && (
          <Card>
            <CardContent className="p-8 text-center text-sm text-gray-500">
              <CircleHelp className="mx-auto mb-2 text-gray-400" size={28} />
              Selecione uma escola e uma turma para iniciar.
            </CardContent>
          </Card>
        )}

        {/* Loading skeleton */}
        {loading && (
          <Card>
            <CardContent className="p-4">
              <div className="grid grid-cols-7 gap-0">
                {Array.from({ length: 35 }).map((_, i) => (
                  <Skeleton key={i} className="h-[120px] rounded-none" />
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Calendário desktop */}
        {data && !loading && (
          <Card data-testid="calendar-card">
            <CardContent className="p-0">
              {/* Cabeçalho dias da semana - desktop */}
              <div className="hidden md:grid grid-cols-7 border-b border-gray-300 bg-gray-50">
                {WEEK_LABELS.map((wl, idx) => (
                  <div
                    key={wl}
                    className={`text-xs font-semibold uppercase tracking-wide text-gray-700 px-2 py-2 text-center ${
                      idx >= 5 ? 'text-gray-400' : ''
                    }`}
                  >
                    {wl}
                  </div>
                ))}
              </div>

              {/* Grid desktop */}
              <div
                className="hidden md:grid grid-cols-7 border-l border-t border-gray-200"
                data-testid="calendar-grid"
              >
                {grid.map((cell, idx) => (
                  <DayCell
                    key={idx}
                    day={cell}
                    onClick={(d) => setDrillDown(d)}
                  />
                ))}
              </div>

              {/* Lista mobile (ordenada por severidade) */}
              <div
                className="md:hidden p-3 space-y-2"
                data-testid="calendar-mobile-list"
              >
                {mobileSorted
                  .filter((d) => d.status !== 'not_expected')
                  .map((d) => (
                    <MobileDayRow
                      key={d.date}
                      day={d}
                      onClick={(x) => setDrillDown(x)}
                    />
                  ))}
                {mobileSorted.filter((d) => d.status !== 'not_expected')
                  .length === 0 && (
                  <div className="text-center text-sm text-gray-500 py-4">
                    Nenhum dia com aula esperada neste mês.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Orphan list */}
        {data && !loading && <OrphanEvidenceList summary={data.summary} />}

        {/* Drill-down */}
        {/* Drill-down — Sheet lateral com slots e ações de validação institucional */}
        <DayDrillDown
          day={
            drillDown && data?.days
              ? data.days.find((d) => d.date === drillDown.date) || drillDown
              : drillDown
          }
          onClose={() => setDrillDown(null)}
          onValidate={handleValidate}
          onUnvalidate={handleUnvalidate}
          busyIds={busyValidationIds}
        />

        {/* Fase 8 — Snapshots Drawer (UI Snapshot Management) */}
        <SnapshotsDrawer
          open={snapshotsDrawerOpen}
          onOpenChange={setSnapshotsDrawerOpen}
          classId={selectedClass}
          className={
            classes.find((c) => c.id === selectedClass)?.name || ''
          }
          periodFrom={monthFirstISO(year, month)}
          periodTo={monthLastISO(year, month)}
          periodLabel={monthLabel(year, month)}
        />
      </div>
    </Layout>
  );
}
