import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Loader2,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import {
  manualContentCopyAPI,
  manualCopyErrorMessage,
} from '@/services/manualContentCopyApi';

const EMPTY_FILTERS = {
  month: '',
  sourceSchoolId: '',
  sourceClassId: '',
  targetSchoolId: '',
  targetClassId: '',
  componentId: '',
};

const UNAVAILABLE_LABELS = {
  TARGET_ALREADY_HAS_CONTENT: 'Já possui conteúdo',
  MULTIPLE_DVD_ASSIGNMENTS: 'Vínculo docente ambíguo',
  MULTIPLE_HISTORICAL_DVD_ASSIGNMENTS: 'Vínculo histórico ambíguo',
  MULTIPLE_LEGACY_TEACHERS: 'Mais de um professor legado',
  MULTIPLE_ATTENDANCE_TEACHERS: 'Mais de um professor na frequência',
  LEGACY_TEACHER_USER_ID_UNRESOLVED: 'Professor legado não resolvido',
  ATTENDANCE_TEACHER_USER_ID_UNRESOLVED: 'Professor da frequência não resolvido',
  TARGET_TEACHER_NOT_RESOLVED: 'Professor do destino não resolvido',
  TARGET_BINDING_UNRESOLVED: 'Vínculo do destino não resolvido',
};

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function newRequestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `manual-copy-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDate(date) {
  if (!date) return '—';
  const [year, month, day] = String(date).slice(0, 10).split('-');
  return year && month && day ? `${day}/${month}/${year}` : date;
}

function sourceKindLabel(kind) {
  return kind === 'content_entries' ? 'Canônico' : 'Legado';
}

function unavailableLabel(reason) {
  return UNAVAILABLE_LABELS[reason] || reason || 'Indisponível';
}

function buildPayload(filters, sourceRows, mappings, requestId) {
  return {
    request_id: requestId,
    month: filters.month,
    source_class_id: filters.sourceClassId,
    source_component_id: filters.componentId,
    target_class_id: filters.targetClassId,
    target_component_id: filters.componentId,
    mappings: sourceRows.map((row) => ({
      source_id: row.id,
      target_date: mappings[row.id] || null,
    })),
  };
}

function planErrorsToText(errors) {
  if (!Array.isArray(errors) || errors.length === 0) return 'O preflight não autorizou a cópia.';
  return errors
    .map((item) => {
      const code = item?.code || 'ERRO';
      const message = item?.message || unavailableLabel(code);
      const target = item?.target_date ? ` (${formatDate(item.target_date)})` : '';
      return `${message}${target}`;
    })
    .join(' • ');
}

function BlockingResultModal({ result, onOk }) {
  useEffect(() => {
    if (!result) return undefined;
    const blockEscape = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener('keydown', blockEscape, true);
    return () => window.removeEventListener('keydown', blockEscape, true);
  }, [result]);

  if (!result) return null;
  const success = result.type === 'success';

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="manual-copy-result-title"
      data-testid="manual-copy-result-modal"
    >
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl border border-gray-200 p-6">
        <div className="flex items-start gap-3">
          {success ? (
            <CheckCircle2 className="h-8 w-8 text-emerald-600 shrink-0" />
          ) : (
            <AlertTriangle className="h-8 w-8 text-red-600 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <h2 id="manual-copy-result-title" className="text-xl font-bold text-gray-900">
              {success ? 'Cópia concluída' : 'Cópia não concluída'}
            </h2>
            <p className="mt-2 text-sm text-gray-700 whitespace-pre-wrap">{result.message}</p>

            {success && (
              <div className="mt-4 rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-950 space-y-1">
                <p><strong>Copiados:</strong> {result.copiedCount ?? 0}</p>
                <p><strong>Ignorados por destino vazio:</strong> {result.skipped ?? 0}</p>
                <p className="break-all"><strong>Lote:</strong> {result.batchId || '—'}</p>
              </div>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onOk}
          autoFocus
          className={`mt-6 w-full rounded-xl px-4 py-3 font-semibold text-white transition-colors ${
            success ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-red-600 hover:bg-red-700'
          }`}
          data-testid="manual-copy-result-ok"
        >
          OK
        </button>
      </div>
    </div>
  );
}

function ConfirmApplyModal({ plan, busy, onCancel, onConfirm }) {
  if (!plan) return null;
  return (
    <div
      className="fixed inset-0 z-[90] bg-black/50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="manual-copy-confirm-title"
      data-testid="manual-copy-confirm-modal"
    >
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl border border-gray-200 p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck className="h-8 w-8 text-blue-600 shrink-0" />
          <div>
            <h2 id="manual-copy-confirm-title" className="text-xl font-bold text-gray-900">
              Confirmar cópia
            </h2>
            <p className="mt-2 text-sm text-gray-700">
              O preflight validou o mapa. Confirme a criação dos registros canônicos no destino.
            </p>
          </div>
        </div>

        <div className="mt-4 rounded-xl bg-blue-50 border border-blue-200 p-4 text-sm text-blue-950 space-y-1">
          <p><strong>Registros selecionados:</strong> {plan.selected_count ?? 0}</p>
          <p><strong>Sem destino:</strong> {plan.skipped_without_target ?? 0}</p>
          <p className="break-all text-xs"><strong>Manifesto:</strong> {plan.manifest_hash}</p>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-xl border border-gray-300 px-4 py-3 font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
            data-testid="manual-copy-confirm-apply"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            Confirmar cópia
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ManualContentCopyLauncher() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState({ ...EMPTY_FILTERS, month: currentMonth() });
  const [options, setOptions] = useState({ schools: [], classes: [], courses: [] });
  const [sourceRows, setSourceRows] = useState([]);
  const [destinationRows, setDestinationRows] = useState([]);
  const [mappings, setMappings] = useState({});
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [loadingRows, setLoadingRows] = useState(false);
  const [inlineError, setInlineError] = useState('');
  const [requestId, setRequestId] = useState(newRequestId());
  const [pendingPayload, setPendingPayload] = useState(null);
  const [preflightPlan, setPreflightPlan] = useState(null);
  const [applying, setApplying] = useState(false);
  const [preflighting, setPreflighting] = useState(false);
  const [finalResult, setFinalResult] = useState(null);

  const isSuperAdmin = user?.role === 'super_admin';

  const sourceClasses = useMemo(
    () => options.classes.filter((item) => item.school_id === filters.sourceSchoolId),
    [options.classes, filters.sourceSchoolId]
  );
  const targetClasses = useMemo(
    () => options.classes.filter((item) => item.school_id === filters.targetSchoolId),
    [options.classes, filters.targetSchoolId]
  );

  const selectedDates = useMemo(() => {
    const map = new Map();
    Object.entries(mappings).forEach(([sourceId, date]) => {
      if (date) map.set(date, sourceId);
    });
    return map;
  }, [mappings]);

  const selectedCount = useMemo(
    () => Object.values(mappings).filter(Boolean).length,
    [mappings]
  );

  const filtersReady = Boolean(
    filters.month &&
    filters.sourceSchoolId &&
    filters.sourceClassId &&
    filters.targetSchoolId &&
    filters.targetClassId &&
    filters.componentId
  );

  const busy = loadingOptions || loadingRows || preflighting || applying;

  useEffect(() => {
    if (!open || !isSuperAdmin) return;
    let active = true;
    setLoadingOptions(true);
    setInlineError('');
    manualContentCopyAPI.options()
      .then((data) => {
        if (!active) return;
        setOptions({
          schools: data?.schools || [],
          classes: data?.classes || [],
          courses: data?.courses || [],
        });
      })
      .catch((error) => {
        if (!active) return;
        setInlineError(manualCopyErrorMessage(error));
      })
      .finally(() => {
        if (active) setLoadingOptions(false);
      });
    return () => { active = false; };
  }, [open, isSuperAdmin]);

  useEffect(() => {
    if (!open || !isSuperAdmin || !filtersReady) {
      setSourceRows([]);
      setDestinationRows([]);
      setMappings({});
      return;
    }

    let active = true;
    setLoadingRows(true);
    setInlineError('');
    setMappings({});
    setPendingPayload(null);
    setPreflightPlan(null);
    setRequestId(newRequestId());

    Promise.all([
      manualContentCopyAPI.source({
        classId: filters.sourceClassId,
        componentId: filters.componentId,
        month: filters.month,
      }),
      manualContentCopyAPI.destinations({
        classId: filters.targetClassId,
        componentId: filters.componentId,
        month: filters.month,
      }),
    ])
      .then(([source, destinations]) => {
        if (!active) return;
        setSourceRows(source?.items || []);
        setDestinationRows(destinations?.items || []);
      })
      .catch((error) => {
        if (!active) return;
        setSourceRows([]);
        setDestinationRows([]);
        setInlineError(manualCopyErrorMessage(error));
      })
      .finally(() => {
        if (active) setLoadingRows(false);
      });

    return () => { active = false; };
  }, [
    open,
    isSuperAdmin,
    filtersReady,
    filters.month,
    filters.sourceClassId,
    filters.targetClassId,
    filters.componentId,
  ]);

  if (!isSuperAdmin) return null;

  const changeFilter = (key, value) => {
    setInlineError('');
    setPendingPayload(null);
    setPreflightPlan(null);
    setFilters((previous) => {
      const next = { ...previous, [key]: value };
      if (key === 'sourceSchoolId') next.sourceClassId = '';
      if (key === 'targetSchoolId') next.targetClassId = '';
      return next;
    });
  };

  const closeWorkspace = () => {
    if (busy || preflightPlan) return;
    if (selectedCount > 0 && !window.confirm('Há mapeamentos selecionados. Deseja fechar sem copiar?')) {
      return;
    }
    setOpen(false);
  };

  const chooseTarget = (sourceId, targetDate) => {
    if (targetDate) {
      const owner = selectedDates.get(targetDate);
      if (owner && owner !== sourceId) return;
    }
    setMappings((previous) => ({ ...previous, [sourceId]: targetDate }));
    setPendingPayload(null);
    setPreflightPlan(null);
  };

  const runPreflight = async () => {
    if (busy || selectedCount === 0) return;

    const values = Object.values(mappings).filter(Boolean);
    if (new Set(values).size !== values.length) {
      setFinalResult({
        type: 'error',
        message: 'Uma data de destino foi selecionada mais de uma vez. Revise o mapa antes de copiar.',
      });
      return;
    }

    const payload = buildPayload(filters, sourceRows, mappings, requestId);
    setPreflighting(true);
    setInlineError('');
    try {
      const plan = await manualContentCopyAPI.preflight(payload);
      if (!plan?.valid) {
        setFinalResult({ type: 'error', message: planErrorsToText(plan?.errors) });
        return;
      }
      setPendingPayload(payload);
      setPreflightPlan(plan);
    } catch (error) {
      setFinalResult({ type: 'error', message: manualCopyErrorMessage(error) });
    } finally {
      setPreflighting(false);
    }
  };

  const applyCopy = async () => {
    if (!pendingPayload || !preflightPlan?.manifest_hash || applying) return;
    setApplying(true);
    try {
      const result = await manualContentCopyAPI.apply({
        ...pendingPayload,
        manifest_hash: preflightPlan.manifest_hash,
      });
      setPreflightPlan(null);
      setPendingPayload(null);
      setFinalResult({
        type: 'success',
        message: result?.message || 'Os registros selecionados foram copiados com sucesso.',
        copiedCount: result?.copied_count ?? 0,
        skipped: result?.skipped_without_target ?? 0,
        batchId: result?.batch_id,
      });
    } catch (error) {
      setPreflightPlan(null);
      setPendingPayload(null);
      setFinalResult({ type: 'error', message: manualCopyErrorMessage(error) });
    } finally {
      setApplying(false);
    }
  };

  const acknowledgeResult = () => {
    const wasSuccess = finalResult?.type === 'success';
    setFinalResult(null);
    if (wasSuccess) {
      setMappings({});
      setRequestId(newRequestId());
      setLoadingRows(true);
      Promise.all([
        manualContentCopyAPI.source({
          classId: filters.sourceClassId,
          componentId: filters.componentId,
          month: filters.month,
        }),
        manualContentCopyAPI.destinations({
          classId: filters.targetClassId,
          componentId: filters.componentId,
          month: filters.month,
        }),
      ])
        .then(([source, destinations]) => {
          setSourceRows(source?.items || []);
          setDestinationRows(destinations?.items || []);
        })
        .catch((error) => setInlineError(manualCopyErrorMessage(error)))
        .finally(() => setLoadingRows(false));
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition-colors"
        title="Assistente de cópia manual de conteúdo — exclusivo do Super Administrador"
        data-testid="manual-content-copy-launcher"
      >
        <Copy className="h-4 w-4" />
        Cópia de Conteúdo
      </button>

      {open && (
        <div className="fixed inset-0 z-[80] bg-slate-950/55 p-2 sm:p-4">
          <div className="h-full w-full rounded-2xl bg-gray-50 shadow-2xl border border-gray-200 overflow-hidden flex flex-col">
            <div className="bg-white border-b border-gray-200 px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-blue-600" />
                  <h1 className="text-xl font-bold text-gray-900">Cópia Manual de Conteúdo</h1>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Origem → Destino • acesso exclusivo do Super Administrador • nenhuma data é inferida automaticamente
                </p>
              </div>
              <button
                type="button"
                onClick={closeWorkspace}
                disabled={busy || Boolean(preflightPlan)}
                className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 disabled:opacity-40"
                aria-label="Fechar"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
              <section className="rounded-2xl bg-white border border-gray-200 shadow-sm p-4">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3">
                  <label className="text-xs font-medium text-gray-700">
                    Mês/ano
                    <input
                      type="month"
                      value={filters.month}
                      onChange={(event) => changeFilter('month', event.target.value)}
                      disabled={busy}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-month"
                    />
                  </label>

                  <label className="text-xs font-medium text-gray-700">
                    Escola de origem
                    <select
                      value={filters.sourceSchoolId}
                      onChange={(event) => changeFilter('sourceSchoolId', event.target.value)}
                      disabled={busy || loadingOptions}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-source-school"
                    >
                      <option value="">Selecione...</option>
                      {options.schools.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label className="text-xs font-medium text-gray-700">
                    Turma de origem
                    <select
                      value={filters.sourceClassId}
                      onChange={(event) => changeFilter('sourceClassId', event.target.value)}
                      disabled={busy || !filters.sourceSchoolId}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-source-class"
                    >
                      <option value="">Selecione...</option>
                      {sourceClasses.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label className="text-xs font-medium text-gray-700">
                    Escola de destino
                    <select
                      value={filters.targetSchoolId}
                      onChange={(event) => changeFilter('targetSchoolId', event.target.value)}
                      disabled={busy || loadingOptions}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-target-school"
                    >
                      <option value="">Selecione...</option>
                      {options.schools.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label className="text-xs font-medium text-gray-700">
                    Turma de destino
                    <select
                      value={filters.targetClassId}
                      onChange={(event) => changeFilter('targetClassId', event.target.value)}
                      disabled={busy || !filters.targetSchoolId}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-target-class"
                    >
                      <option value="">Selecione...</option>
                      {targetClasses.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label className="text-xs font-medium text-gray-700">
                    Componente curricular
                    <select
                      value={filters.componentId}
                      onChange={(event) => changeFilter('componentId', event.target.value)}
                      disabled={busy || loadingOptions}
                      className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                      data-testid="manual-copy-component"
                    >
                      <option value="">Selecione...</option>
                      {options.courses.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                </div>

                {inlineError && (
                  <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 flex gap-2">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>{inlineError}</span>
                  </div>
                )}
              </section>

              {!filtersReady && (
                <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500">
                  Selecione mês, escolas, turmas e componente curricular para carregar origem e destino.
                </div>
              )}

              {filtersReady && loadingRows && (
                <div className="rounded-2xl border border-gray-200 bg-white p-10 flex items-center justify-center gap-3 text-gray-600">
                  <Loader2 className="h-5 w-5 animate-spin" /> Carregando conteúdos e datas elegíveis...
                </div>
              )}

              {filtersReady && !loadingRows && (
                <section className="rounded-2xl bg-white border border-gray-200 shadow-sm overflow-hidden">
                  <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)] bg-gray-100 border-b border-gray-200">
                    <div className="px-4 py-3 font-semibold text-gray-800">Origem — {sourceRows.length} registro(s)</div>
                    <div className="px-4 py-3 font-semibold text-gray-800 lg:border-l lg:border-gray-200">Destino — {destinationRows.length} data(s)</div>
                  </div>

                  {sourceRows.length === 0 ? (
                    <div className="p-10 text-center text-gray-500">Nenhum conteúdo encontrado na origem para os filtros selecionados.</div>
                  ) : (
                    sourceRows.map((row) => {
                      const selectedDate = mappings[row.id] || '';
                      const selectedDestination = destinationRows.find((item) => item.date === selectedDate);
                      return (
                        <div
                          key={row.id}
                          className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)] border-b border-gray-200 last:border-b-0"
                          data-testid={`manual-copy-row-${row.id}`}
                        >
                          <div className="p-4 min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-2">
                              <span className="font-bold text-gray-900">{formatDate(row.date)}</span>
                              <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                                {row.number_of_classes || 1} aula(s)
                              </span>
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                row.source_kind === 'content_entries'
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : 'bg-amber-50 text-amber-700'
                              }`}>
                                {sourceKindLabel(row.source_kind)}
                              </span>
                            </div>
                            <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">{row.content}</p>
                            {row.methodology && (
                              <p className="mt-2 text-xs text-gray-600"><strong>Metodologia:</strong> {row.methodology}</p>
                            )}
                            {row.observations && (
                              <p className="mt-1 text-xs text-gray-600"><strong>Observações:</strong> {row.observations}</p>
                            )}
                          </div>

                          <div className="p-4 bg-slate-50 lg:border-l lg:border-gray-200">
                            <label className="text-xs font-semibold text-gray-700">
                              Data de destino
                              <select
                                value={selectedDate}
                                onChange={(event) => chooseTarget(row.id, event.target.value)}
                                disabled={busy}
                                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm"
                                data-testid={`manual-copy-target-${row.id}`}
                              >
                                <option value="">NÃO COPIAR</option>
                                {destinationRows.map((destination) => {
                                  const selectedByOther = selectedDates.has(destination.date) && selectedDates.get(destination.date) !== row.id;
                                  const disabled = !destination.available || selectedByOther;
                                  const suffix = !destination.available
                                    ? unavailableLabel(destination.unavailable_reason)
                                    : selectedByOther
                                      ? 'Já selecionada em outra linha'
                                      : `${destination.session_count || 0} sessão(ões)`;
                                  return (
                                    <option key={destination.date} value={destination.date} disabled={disabled}>
                                      {formatDate(destination.date)} — {suffix}
                                    </option>
                                  );
                                })}
                              </select>
                            </label>

                            {selectedDestination && (
                              <div className="mt-3 rounded-lg border border-blue-100 bg-white p-3 text-xs text-gray-700 space-y-1">
                                <p><strong>Sessões:</strong> {selectedDestination.session_count ?? 0}</p>
                                <p><strong>Carga declarada:</strong> {selectedDestination.declared_load ?? 0}</p>
                                <p><strong>Professor:</strong> {selectedDestination.teacher_name || '—'}</p>
                                <p><strong>Vínculo:</strong> {selectedDestination.binding_mode || '—'}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </section>
              )}
            </div>

            <div className="bg-white border-t border-gray-200 px-4 sm:px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="text-sm text-gray-600">
                <strong>{selectedCount}</strong> selecionado(s) para copiar •{' '}
                <strong>{Math.max(sourceRows.length - selectedCount, 0)}</strong> como NÃO COPIAR
              </div>
              <button
                type="button"
                onClick={runPreflight}
                disabled={!filtersReady || selectedCount === 0 || busy || sourceRows.length === 0}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="manual-copy-run-preflight"
              >
                {preflighting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
                Copiar
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmApplyModal
        plan={preflightPlan}
        busy={applying}
        onCancel={() => {
          if (!applying) {
            setPreflightPlan(null);
            setPendingPayload(null);
            setRequestId(newRequestId());
          }
        }}
        onConfirm={applyCopy}
      />

      <BlockingResultModal result={finalResult} onOk={acknowledgeResult} />
    </>
  );
}
