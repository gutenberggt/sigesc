import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  X, RefreshCw, Save, CheckCircle2, AlertTriangle, History,
  ClipboardList, BookOpen, Target, CalendarDays, Users, MessageSquare,
  Activity, ShieldCheck, FileClock
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TAB_ITEMS = [
  { id: 'overview', label: 'Visão Geral', icon: ShieldCheck },
  { id: 'study_case', label: 'Estudo de Caso', icon: BookOpen },
  { id: 'paee', label: 'PAEE', icon: Target },
  { id: 'pei', label: 'PEI', icon: ClipboardList },
  { id: 'schedule', label: 'Agenda', icon: CalendarDays },
  { id: 'lifecycle', label: 'Vigência e Revisão', icon: FileClock },
  { id: 'attendances', label: 'Atendimentos', icon: Users },
  { id: 'articulations', label: 'Articulação', icon: MessageSquare },
  { id: 'evolutions', label: 'Evolução', icon: Activity },
  { id: 'history', label: 'Histórico', icon: History },
];

const SECTION_LABELS = {
  study_case: 'Estudo de Caso',
  paee: 'PAEE',
  pei: 'PEI',
  schedule: 'Agenda / Cronograma',
  lifecycle: 'Vigência e Revisão',
};

const SECTION_PATHS = {
  study_case: 'study-case',
  paee: 'paee',
  pei: 'pei',
  schedule: 'schedule',
  lifecycle: 'lifecycle',
};

const SUPPORT_STATUS = {
  not_assessed: 'Não avaliado',
  not_needed: 'Não necessário',
  needed: 'Necessário',
  provided: 'Disponibilizado',
  unavailable: 'Indisponível',
};

const STATE_LABELS = {
  legacy_projected: 'Projetado do Plano anterior — revisar',
  in_progress: 'Em elaboração',
  complete: 'Concluído',
  not_applicable: 'Não aplicável',
};

function readCsrfToken() {
  try {
    const ls = localStorage.getItem('sigesc_csrf_token');
    if (ls) return ls;
  } catch (_) { /* noop */ }
  try {
    const ss = sessionStorage.getItem('sigesc_csrf_token');
    if (ss) return ss;
  } catch (_) { /* noop */ }
  const match = typeof document !== 'undefined'
    ? document.cookie.match(/(?:^|;\s*)sigesc_csrf=([^;]+)/)
    : null;
  return match ? decodeURIComponent(match[1]) : null;
}

function asLines(value) {
  return Array.isArray(value) ? value.filter(Boolean).join('\n') : '';
}

function lines(value) {
  return String(value || '')
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean);
}

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function formatDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('pt-BR');
}

function Field({ label, value, onChange, rows = 3, disabled = false, help = null }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-gray-700 mb-1">{label}</span>
      <textarea
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        disabled={disabled}
        className="w-full border rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
      />
      {help && <span className="block text-[11px] text-gray-500 mt-1">{help}</span>}
    </label>
  );
}

function InputField({ label, value, onChange, type = 'text', disabled = false, help = null }) {
  const displayValue = type === 'date' && value ? String(value).slice(0, 10) : (value || '');
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-gray-700 mb-1">{label}</span>
      <input
        type={type}
        value={displayValue}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="w-full border rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
      />
      {help && <span className="block text-[11px] text-gray-500 mt-1">{help}</span>}
    </label>
  );
}

function SelectField({ label, value, onChange, options, disabled = false, help = null }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-gray-700 mb-1">{label}</span>
      <select
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="w-full border rounded-lg px-3 py-2 text-sm disabled:bg-gray-50"
      >
        {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
      </select>
      {help && <span className="block text-[11px] text-gray-500 mt-1">{help}</span>}
    </label>
  );
}

function SectionState({ section, onChange, disabled }) {
  return (
    <div className="flex justify-end mb-3">
      <label className="text-xs text-gray-600 flex items-center gap-2">
        Situação da seção
        <select
          value={section?.state || 'in_progress'}
          onChange={(event) => onChange({ ...section, state: event.target.value })}
          disabled={disabled}
          className="border rounded px-2 py-1 bg-white"
        >
          <option value="legacy_projected">Projetado do legado</option>
          <option value="in_progress">Em elaboração</option>
          <option value="complete">Concluído</option>
          <option value="not_applicable">Não aplicável</option>
        </select>
      </label>
    </div>
  );
}

function SupportAssessment({ title, value, onChange, disabled, showCapacity = false }) {
  const current = value || { status: 'not_assessed' };
  return (
    <div className="border rounded-lg p-3 bg-gray-50">
      <p className="text-sm font-semibold text-gray-800 mb-2">{title}</p>
      <div className={`grid gap-3 ${showCapacity ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        <SelectField
          label="Avaliação da necessidade"
          value={current.status || 'not_assessed'}
          onChange={(status) => onChange({ ...current, status })}
          disabled={disabled}
          options={Object.entries(SUPPORT_STATUS)}
          help="Não avaliado é diferente de não necessário."
        />
        <Field
          label="Justificativa pedagógica"
          value={current.justificativa}
          onChange={(justificativa) => onChange({ ...current, justificativa })}
          rows={2}
          disabled={disabled}
        />
        {showCapacity && (
          <Field
            label="Capacidade de disponibilização"
            value={current.capacidade_disponibilizacao}
            onChange={(capacidade_disponibilizacao) => onChange({ ...current, capacidade_disponibilizacao })}
            rows={2}
            disabled={disabled}
            help="Quando houver necessidade, registre como o recurso poderá ser disponibilizado ou a limitação existente."
          />
        )}
      </div>
    </div>
  );
}

function blockerText(item) {
  if (!item) return 'Pendência de adequação.';
  if (item.code === 'AEE_V2_SECTION_NOT_COMPLETE') {
    return `${SECTION_LABELS[item.section] || 'Seção'}: marque a situação da seção como “Concluído” após revisar os dados.`;
  }
  return item.description || item.message || 'Há uma pendência que precisa ser revisada.';
}

function blockerTab(item) {
  return ['study_case', 'paee', 'pei', 'schedule', 'lifecycle'].includes(item?.section)
    ? item.section
    : null;
}

function SnapshotBadge({ snapshot, kind }) {
  if (!snapshot) return null;
  const isActive = kind === 'active';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${isActive ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
      {isActive ? <CheckCircle2 size={12} /> : <FileClock size={12} />}
      v{snapshot.document_version}.r{snapshot.revision} · {isActive ? 'Vigente' : 'Em trabalho'}
    </span>
  );
}

export default function DossieAEEV2Modal({ show, onClose, plano, token, canEdit }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [activation, setActivation] = useState(null);
  const [related, setRelated] = useState({ attendances: [], articulations: [], evolutions: [] });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const baseUrl = plano?.id ? `${API_URL}/api/aee/planos/${plano.id}/dossie-v2` : null;
  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const writeHeaders = useMemo(() => ({
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...(readCsrfToken() ? { 'X-CSRF-Token': readCsrfToken() } : {}),
  }), [token]);

  const requestJson = useCallback(async (url, options = {}) => {
    const response = await fetch(url, options);
    let body = null;
    try { body = await response.json(); } catch (_) { body = null; }
    if (!response.ok) {
      const detail = body?.detail;
      const text = typeof detail === 'string'
        ? detail
        : detail?.message || body?.message || `Erro HTTP ${response.status}`;
      const error = new Error(text);
      error.payload = body;
      error.status = response.status;
      throw error;
    }
    return body;
  }, []);

  const applyState = useCallback((nextState) => {
    setState(nextState);
    const source = nextState?.working_snapshot?.dossier || nextState?.active_snapshot?.dossier || null;
    setDraft(source ? clone(source) : null);
  }, []);

  const loadState = useCallback(async () => {
    if (!show || !baseUrl) return;
    setLoading(true);
    setMessage(null);
    try {
      const [stateData, snapshotData, atendData, articulacaoData, evolucaoData] = await Promise.all([
        requestJson(`${baseUrl}/state`, { headers: authHeaders }),
        requestJson(`${baseUrl}/snapshots`, { headers: authHeaders }).catch(() => ({ items: [] })),
        requestJson(`${API_URL}/api/aee/atendimentos?plano_aee_id=${encodeURIComponent(plano.id)}`, { headers: authHeaders }).catch(() => []),
        requestJson(`${API_URL}/api/aee/articulacoes?plano_aee_id=${encodeURIComponent(plano.id)}`, { headers: authHeaders }).catch(() => []),
        requestJson(`${API_URL}/api/aee/evolucoes?plano_aee_id=${encodeURIComponent(plano.id)}`, { headers: authHeaders }).catch(() => []),
      ]);
      applyState(stateData);
      setSnapshots(snapshotData?.items || []);
      setRelated({
        attendances: Array.isArray(atendData) ? atendData : (atendData?.items || []),
        articulations: Array.isArray(articulacaoData) ? articulacaoData : [],
        evolutions: Array.isArray(evolucaoData) ? evolucaoData : [],
      });
      if (stateData?.head?.working_snapshot_id) {
        try {
          setActivation(await requestJson(`${baseUrl}/activation-validation`, { headers: authHeaders }));
        } catch (_) {
          setActivation(null);
        }
      } else {
        setActivation(null);
      }
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setLoading(false);
    }
  }, [show, baseUrl, authHeaders, plano?.id, requestJson, applyState]);

  useEffect(() => {
    if (show) {
      setActiveTab('overview');
      loadState();
    }
  }, [show, loadState]);

  if (!show || !plano) return null;

  const hasHead = Boolean(state?.head);
  const hasWorking = Boolean(state?.working_snapshot);
  const hasActive = Boolean(state?.active_snapshot);
  const editable = Boolean(canEdit && hasWorking && draft);

  const mutateSection = (sectionName, updater) => {
    setDraft(current => {
      if (!current) return current;
      const next = clone(current);
      next[sectionName] = typeof updater === 'function'
        ? updater(next[sectionName] || {})
        : updater;
      return next;
    });
  };

  const refreshAfterWrite = async (nextState, successText) => {
    applyState(nextState);
    setMessage({ type: 'success', text: successText });
    const history = await requestJson(`${baseUrl}/snapshots`, { headers: authHeaders }).catch(() => ({ items: [] }));
    setSnapshots(history?.items || []);
    if (nextState?.head?.working_snapshot_id) {
      const validation = await requestJson(`${baseUrl}/activation-validation`, { headers: authHeaders }).catch(() => null);
      setActivation(validation);
    } else {
      setActivation(null);
    }
  };

  const bootstrap = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const next = await requestJson(`${baseUrl}/bootstrap`, { method: 'POST', headers: writeHeaders });
      await refreshAfterWrite(next, 'Dossiê AEE V2 inicializado a partir do Plano existente.');
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setSaving(false);
    }
  };

  const saveSection = async (sectionName) => {
    if (!editable || !state?.head || !state?.working_snapshot || !draft?.[sectionName]) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        expected_head_revision: state.head.head_revision,
        expected_working_snapshot_id: state.working_snapshot.id,
        section: draft[sectionName],
      };
      const next = await requestJson(`${baseUrl}/sections/${SECTION_PATHS[sectionName]}`, {
        method: 'PATCH',
        headers: writeHeaders,
        body: JSON.stringify(payload),
      });
      await refreshAfterWrite(next, `${SECTION_LABELS[sectionName]} salvo em nova revisão imutável.`);
    } catch (error) {
      if (error.status === 409) await loadState();
      setMessage({ type: 'error', text: error.status === 409 ? `${error.message} O Dossiê foi recarregado.` : error.message });
    } finally {
      setSaving(false);
    }
  };

  const startRevision = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const next = await requestJson(`${baseUrl}/revisions`, {
        method: 'POST',
        headers: writeHeaders,
        body: JSON.stringify({ expected_head_revision: state.head.head_revision }),
      });
      await refreshAfterWrite(next, `Nova versão v${next.working_snapshot?.document_version} aberta para revisão.`);
    } catch (error) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setSaving(false);
    }
  };

  const activate = async () => {
    if (!state?.head || !state?.working_snapshot) return;
    setSaving(true);
    setMessage(null);
    try {
      const next = await requestJson(`${baseUrl}/activate`, {
        method: 'POST',
        headers: writeHeaders,
        body: JSON.stringify({
          expected_head_revision: state.head.head_revision,
          expected_working_snapshot_id: state.working_snapshot.id,
        }),
      });
      await refreshAfterWrite(next, `Versão v${next.active_snapshot?.document_version} do Dossiê AEE V2 tornou-se vigente.`);
    } catch (error) {
      const blockers = error.payload?.detail?.blockers;
      setMessage({
        type: 'error',
        text: blockers?.length
          ? `Ativação bloqueada: ${blockers.map(blockerText).join(' · ')}`
          : error.message,
      });
    } finally {
      setSaving(false);
    }
  };

  const renderSectionBlockers = (sectionName) => {
    const items = (activation?.blockers || []).filter(item => item.section === sectionName);
    if (!items.length) return null;
    return (
      <div className="mb-4 border border-amber-200 bg-amber-50 rounded-lg p-3">
        <p className="text-sm font-semibold text-amber-900">Pendências desta seção</p>
        <ul className="mt-2 space-y-1 text-sm text-amber-900 list-disc list-inside">
          {items.map((item, index) => <li key={`${item.code}-${index}`}>{blockerText(item)}</li>)}
        </ul>
      </div>
    );
  };

  const saveButton = (sectionName) => (
    <div className="flex justify-end pt-4 border-t mt-5">
      <button
        type="button"
        onClick={() => saveSection(sectionName)}
        disabled={!editable || saving}
        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50"
      >
        <Save size={16} /> Salvar {SECTION_LABELS[sectionName]}
      </button>
    </div>
  );

  const study = draft?.study_case || {};
  const paee = draft?.paee || {};
  const pei = draft?.pei || {};
  const schedule = draft?.schedule || {};
  const lifecycle = draft?.lifecycle || {};

  const renderOverview = () => (
    <div className="space-y-5">
      <div className="grid md:grid-cols-3 gap-3">
        <div className="border rounded-xl p-4 bg-slate-50">
          <p className="text-xs text-gray-500">Fonte efetiva</p>
          <p className="font-semibold mt-1">{state?.effective_source === 'sidecar_active' ? 'Dossiê AEE V2 vigente' : 'Plano AEE legado'}</p>
        </div>
        <div className="border rounded-xl p-4 bg-green-50">
          <p className="text-xs text-gray-500">Versão vigente</p>
          <div className="mt-2"><SnapshotBadge snapshot={state?.active_snapshot} kind="active" /></div>
          {!hasActive && <p className="text-sm text-gray-500 mt-1">Ainda não há versão V2 vigente.</p>}
        </div>
        <div className="border rounded-xl p-4 bg-amber-50">
          <p className="text-xs text-gray-500">Versão em elaboração/revisão</p>
          <div className="mt-2"><SnapshotBadge snapshot={state?.working_snapshot} kind="working" /></div>
          {!hasWorking && <p className="text-sm text-gray-500 mt-1">Nenhuma versão em trabalho.</p>}
        </div>
      </div>

      {!hasHead && (
        <div className="border border-blue-200 bg-blue-50 rounded-xl p-5">
          <h3 className="font-semibold text-blue-900">Inicialização controlada do Dossiê V2</h3>
          <p className="text-sm text-blue-800 mt-2">
            O Plano AEE atual será projetado para o Dossiê V2. O Plano original não será alterado nem excluído.
          </p>
          {canEdit && (
            <button onClick={bootstrap} disabled={saving} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50">
              Inicializar Dossiê V2
            </button>
          )}
        </div>
      )}

      {hasHead && (
        <div className="grid md:grid-cols-3 gap-3">
          {['study_case', 'paee', 'pei'].map(name => {
            const section = draft?.[name];
            return (
              <div key={name} className="border rounded-xl p-4">
                <p className="font-semibold text-gray-800">{SECTION_LABELS[name]}</p>
                <p className="text-sm text-gray-500 mt-1">{STATE_LABELS[section?.state] || section?.state || 'Não informado'}</p>
              </div>
            );
          })}
        </div>
      )}

      {hasWorking && (
        <div className={`rounded-xl p-4 border ${activation?.ready ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'}`}>
          <div className="flex items-start gap-3">
            {activation?.ready ? <CheckCircle2 className="text-green-600 mt-0.5" size={20} /> : <AlertTriangle className="text-amber-600 mt-0.5" size={20} />}
            <div className="flex-1">
              <p className="font-semibold">{activation?.ready ? 'Versão pronta para vigência' : 'Versão ainda possui pendências'}</p>
              {!activation?.ready && activation?.blockers?.length > 0 && (
                <div className="mt-3 space-y-2">
                  {activation.blockers.map((item, index) => {
                    const targetTab = blockerTab(item);
                    return (
                      <div key={`${item.code}-${index}`} className="flex items-start justify-between gap-3 rounded-lg bg-white/70 border border-amber-200 px-3 py-2">
                        <span className="text-sm text-amber-950">{blockerText(item)}</span>
                        {targetTab && (
                          <button
                            type="button"
                            onClick={() => setActiveTab(targetTab)}
                            className="shrink-0 text-xs font-semibold text-blue-700 hover:underline"
                          >
                            Corrigir →
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {canEdit && activation?.ready && (
                <button onClick={activate} disabled={saving} className="mt-3 px-4 py-2 bg-green-600 text-white rounded-lg disabled:opacity-50">
                  Tornar esta versão Vigente
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {hasActive && !hasWorking && canEdit && (
        <button onClick={startRevision} disabled={saving} className="px-4 py-2 bg-amber-600 text-white rounded-lg disabled:opacity-50">
          Abrir nova versão para revisão
        </button>
      )}
    </div>
  );

  const renderStudyCase = () => (
    <div>
      {!draft ? <p className="text-sm text-gray-500">Inicialize o Dossiê V2 para acessar esta seção.</p> : (
        <>
          <SectionState section={study} onChange={(next) => mutateSection('study_case', next)} disabled={!editable} />
          {renderSectionBlockers('study_case')}
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Fundamentação pedagógica da identificação para o AEE" value={study.fundamentacao_pedagogica_identificacao} onChange={(value) => mutateSection('study_case', s => ({ ...s, fundamentacao_pedagogica_identificacao: value }))} disabled={!editable} />
            <Field label="Demanda inicial e contexto escolar" value={study.demanda_inicial_contexto} onChange={(value) => mutateSection('study_case', s => ({ ...s, demanda_inicial_contexto: value }))} disabled={!editable} />
            <Field label="Barreiras identificadas" value={asLines(study.barreiras_contexto)} onChange={(value) => mutateSection('study_case', s => ({ ...s, barreiras_contexto: lines(value) }))} disabled={!editable} help="Uma barreira por linha." />
            <Field label="Potencialidades" value={study.potencialidades} onChange={(value) => mutateSection('study_case', s => ({ ...s, potencialidades: value }))} disabled={!editable} />
            <Field label="Demandas de apoio" value={study.demandas_apoio} onChange={(value) => mutateSection('study_case', s => ({ ...s, demandas_apoio: value }))} disabled={!editable} />
            <Field label="Comunicação e participação" value={study.comunicacao_participacao} onChange={(value) => mutateSection('study_case', s => ({ ...s, comunicacao_participacao: value }))} disabled={!editable} />
            <Field label="Participação do estudante" value={study.participacao_estudante} onChange={(value) => mutateSection('study_case', s => ({ ...s, participacao_estudante: value }))} disabled={!editable} />
            <Field label="Contribuições do estudante" value={study.contribuicoes_estudante} onChange={(value) => mutateSection('study_case', s => ({ ...s, contribuicoes_estudante: value }))} disabled={!editable} />
            <Field label="Contribuições da família" value={study.contribuicoes_familia} onChange={(value) => mutateSection('study_case', s => ({ ...s, contribuicoes_familia: value }))} disabled={!editable} />
            <Field label="Estratégias e recursos de acessibilidade" value={asLines(study.estrategias_recursos_acessibilidade)} onChange={(value) => mutateSection('study_case', s => ({ ...s, estrategias_recursos_acessibilidade: lines(value) }))} disabled={!editable} help="Uma estratégia/recurso por linha." />
            <Field label="Articulação com a rede de proteção, quando necessária" value={asLines(study.articulacao_rede_protecao)} onChange={(value) => mutateSection('study_case', s => ({ ...s, articulacao_rede_protecao: lines(value) }))} disabled={!editable} />
          </div>
          {saveButton('study_case')}
        </>
      )}
    </div>
  );

  const updateDescriptions = (current, text, factory = (descricao) => ({ descricao })) => {
    const items = lines(text);
    return items.map((descricao, index) => ({ ...(current?.[index] || factory(descricao)), descricao }));
  };

  const renderPaee = () => (
    <div>
      {!draft ? <p className="text-sm text-gray-500">Inicialize o Dossiê V2 para acessar esta seção.</p> : (
        <>
          <SectionState section={paee} onChange={(next) => mutateSection('paee', next)} disabled={!editable} />
          {renderSectionBlockers('paee')}
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Barreiras prioritárias" value={asLines(paee.barreiras_prioritarias)} onChange={(value) => mutateSection('paee', s => ({ ...s, barreiras_prioritarias: lines(value) }))} disabled={!editable} />
            <Field label="Objetivos do PAEE" value={asLines((paee.objetivos || []).map(item => item.descricao))} onChange={(value) => mutateSection('paee', s => ({ ...s, objetivos: updateDescriptions(s.objetivos, value) }))} disabled={!editable} help="Um objetivo por linha; metadados existentes são preservados por posição." />
            <Field label="Materiais e recursos" value={asLines((paee.materiais_recursos || []).map(item => item.descricao))} onChange={(value) => mutateSection('paee', s => ({ ...s, materiais_recursos: updateDescriptions(s.materiais_recursos, value) }))} disabled={!editable} />
            <Field label="Indicadores de progresso" value={paee.indicadores_progresso} onChange={(value) => mutateSection('paee', s => ({ ...s, indicadores_progresso: value }))} disabled={!editable} />
            <Field label="Frequência de revisão" value={paee.frequencia_revisao} onChange={(value) => mutateSection('paee', s => ({ ...s, frequencia_revisao: value }))} disabled={!editable} />
            <Field label="Critérios de ajuste" value={paee.criterios_ajuste} onChange={(value) => mutateSection('paee', s => ({ ...s, criterios_ajuste: value }))} disabled={!editable} />
            <Field label="Avaliação de demandas de formação em Educação Especial Inclusiva" value={asLines(paee.demandas_formacao_educacao_especial_inclusiva)} onChange={(value) => mutateSection('paee', s => ({ ...s, demandas_formacao_educacao_especial_inclusiva: lines(value) }))} disabled={!editable} help="Registre a demanda identificada ou declare explicitamente que nenhuma demanda adicional foi identificada neste momento." />
            <Field label="Avaliação sobre acionamento da rede de proteção" value={asLines(paee.acionamentos_rede_protecao)} onChange={(value) => mutateSection('paee', s => ({ ...s, acionamentos_rede_protecao: lines(value) }))} disabled={!editable} help="Registre o acionamento necessário ou declare explicitamente que não há acionamento indicado neste momento." />
          </div>
          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <SupportAssessment title="Tecnologia Assistiva" value={paee.tecnologia_assistiva} onChange={(value) => mutateSection('paee', s => ({ ...s, tecnologia_assistiva: value }))} disabled={!editable} showCapacity />
            <SupportAssessment title="Comunicação Aumentativa e Alternativa (CAA)" value={paee.comunicacao_aumentativa_alternativa} onChange={(value) => mutateSection('paee', s => ({ ...s, comunicacao_aumentativa_alternativa: value }))} disabled={!editable} showCapacity />
            <SupportAssessment title="Profissional de Apoio Escolar" value={paee.profissional_apoio_escolar} onChange={(value) => mutateSection('paee', s => ({ ...s, profissional_apoio_escolar: value }))} disabled={!editable} />
            <SupportAssessment title="Tradutor/Intérprete de Libras" value={paee.tradutor_interprete_libras} onChange={(value) => mutateSection('paee', s => ({ ...s, tradutor_interprete_libras: value }))} disabled={!editable} />
            <SupportAssessment title="Guia-intérprete" value={paee.guia_interprete} onChange={(value) => mutateSection('paee', s => ({ ...s, guia_interprete: value }))} disabled={!editable} />
          </div>
          {saveButton('paee')}
        </>
      )}
    </div>
  );

  const renderPei = () => (
    <div>
      {!draft ? <p className="text-sm text-gray-500">Inicialize o Dossiê V2 para acessar esta seção.</p> : (
        <>
          <SectionState section={pei} onChange={(next) => mutateSection('pei', next)} disabled={!editable} />
          {renderSectionBlockers('pei')}
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Atividades do AEE" value={asLines(pei.atividades_aee)} onChange={(value) => mutateSection('pei', s => ({ ...s, atividades_aee: lines(value) }))} disabled={!editable} help="Registre as atividades previstas no AEE para este estudante." />
            <Field label="Articulação com a Sala Comum" value={pei.articulacao_sala_comum} onChange={(value) => mutateSection('pei', s => ({ ...s, articulacao_sala_comum: value }))} disabled={!editable} help="Descreva a articulação com o professor regente e, quando pertinente, com outros profissionais da escola." />
            <Field label="Combinados com o Professor Regente" value={pei.combinados_professor_regente} onChange={(value) => mutateSection('pei', s => ({ ...s, combinados_professor_regente: value }))} disabled={!editable} />
            <Field label="Acessibilidade Curricular" value={pei.acessibilidade_curricular} onChange={(value) => mutateSection('pei', s => ({ ...s, acessibilidade_curricular: value }))} disabled={!editable} />
            <Field label="Acessibilidade Didático-Pedagógica" value={pei.acessibilidade_didatico_pedagogica} onChange={(value) => mutateSection('pei', s => ({ ...s, acessibilidade_didatico_pedagogica: value }))} disabled={!editable} />
            <Field label="Acessibilidade Avaliativa" value={pei.acessibilidade_avaliativa} onChange={(value) => mutateSection('pei', s => ({ ...s, acessibilidade_avaliativa: value }))} disabled={!editable} />
            <Field label="Adaptações por Componente Curricular/Campos de Experiência" value={pei.adaptacoes_por_componente} onChange={(value) => mutateSection('pei', s => ({ ...s, adaptacoes_por_componente: value }))} disabled={!editable} rows={4} />
            <Field label="Estratégias de acompanhamento e monitoramento" value={pei.estrategias_acompanhamento_monitoramento} onChange={(value) => mutateSection('pei', s => ({ ...s, estrategias_acompanhamento_monitoramento: value }))} disabled={!editable} />
            <Field label="Devolutivas à família" value={asLines(pei.devolutivas_familia)} onChange={(value) => mutateSection('pei', s => ({ ...s, devolutivas_familia: lines(value) }))} disabled={!editable} />
          </div>
          {saveButton('pei')}
        </>
      )}
    </div>
  );

  const renderLifecycle = () => (
    <div>
      {!draft ? <p className="text-sm text-gray-500">Inicialize o Dossiê V2 para acessar esta seção.</p> : (
        <>
          {renderSectionBlockers('lifecycle')}
          <div className="grid md:grid-cols-2 gap-4">
            <InputField label="Início da vigência" type="date" value={lifecycle.effective_from} onChange={(value) => mutateSection('lifecycle', s => ({ ...s, effective_from: value }))} disabled={!editable} />
            <InputField label="Fim da vigência (quando aplicável)" type="date" value={lifecycle.effective_to} onChange={(value) => mutateSection('lifecycle', s => ({ ...s, effective_to: value }))} disabled={!editable} />
            <InputField label="Data programada para revisão anual" type="date" value={lifecycle.review_at} onChange={(value) => mutateSection('lifecycle', s => ({ ...s, review_at: value }))} disabled={!editable} help="A revisão anual não impede atualizações anteriores sempre que necessárias." />
            <Field label="Período de vigência / observação legada" value={lifecycle.periodo_vigencia_legacy} onChange={(value) => mutateSection('lifecycle', s => ({ ...s, periodo_vigencia_legacy: value }))} disabled={!editable} rows={2} />
          </div>
          {saveButton('lifecycle')}
        </>
      )}
    </div>
  );

  const scheduleText = (schedule.sessions || []).map(item => [
    item.weekday || '', item.start || '', item.end || '', item.local || '', item.modalidade || ''
  ].join(' | ')).join('\n');

  const renderSchedule = () => (
    <div>
      {!draft ? <p className="text-sm text-gray-500">Inicialize o Dossiê V2 para acessar esta seção.</p> : (
        <>
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Carga horária semanal" value={schedule.carga_horaria_semanal} onChange={(value) => mutateSection('schedule', s => ({ ...s, carga_horaria_semanal: value }))} disabled={!editable} rows={2} />
            <Field
              label="Sessões"
              value={scheduleText}
              onChange={(value) => mutateSection('schedule', s => ({
                ...s,
                sessions: lines(value).map((row, index) => {
                  const [weekday, start, end, local, modalidade] = row.split('|').map(item => item.trim());
                  return { ...(s.sessions?.[index] || {}), weekday, start, end, local, modalidade };
                }),
              }))}
              disabled={!editable}
              rows={6}
              help="Uma sessão por linha: dia | início | fim | local | modalidade."
            />
          </div>
          {saveButton('schedule')}
        </>
      )}
    </div>
  );

  const renderReadOnlyList = (items, emptyText, renderer) => (
    items.length === 0
      ? <p className="text-sm text-gray-500 py-6 text-center">{emptyText}</p>
      : <div className="space-y-3">{items.map((item, index) => renderer(item, index))}</div>
  );

  const renderAttendances = () => renderReadOnlyList(
    related.attendances,
    'Nenhum atendimento vinculado a este Plano.',
    (item, index) => (
      <div key={item.id || index} className="border rounded-lg p-3">
        <div className="flex justify-between gap-3"><strong>{item.data || 'Data não informada'}</strong><span className="text-xs text-gray-500">{item.presente === false ? 'Ausente' : 'Presente'}</span></div>
        <p className="text-sm mt-2"><b>Objetivo:</b> {item.objetivo_trabalhado || '-'}</p>
        <p className="text-sm"><b>Atividade:</b> {item.atividade_realizada || '-'}</p>
      </div>
    )
  );

  const renderArticulations = () => renderReadOnlyList(
    related.articulations,
    'Nenhuma articulação com Sala Comum vinculada a este Plano.',
    (item, index) => (
      <div key={item.id || index} className="border rounded-lg p-3">
        <strong>{item.data || item.created_at || 'Registro de articulação'}</strong>
        <p className="text-sm mt-2 whitespace-pre-wrap">{item.descricao || item.registro || item.orientacao || item.observacoes || '-'}</p>
      </div>
    )
  );

  const renderEvolutions = () => renderReadOnlyList(
    related.evolutions,
    'Nenhuma evolução vinculada a este Plano.',
    (item, index) => (
      <div key={item.id || index} className="border rounded-lg p-3">
        <strong>{item.data || item.created_at || 'Registro de evolução'}</strong>
        <p className="text-sm mt-2 whitespace-pre-wrap">{item.descricao || item.evolucao || item.observacoes || item.registro || '-'}</p>
      </div>
    )
  );

  const renderHistory = () => renderReadOnlyList(
    snapshots,
    'O histórico versionado será criado após a inicialização do Dossiê V2.',
    (item, index) => (
      <div key={item.id || index} className="border rounded-lg p-3 flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold">v{item.document_version}.r{item.revision} · {item.operation}</p>
          <p className="text-xs text-gray-500 mt-1">{formatDate(item.created_at)} · {item.created_by || 'autor não informado'}</p>
          <p className="text-[11px] text-gray-400 mt-1 font-mono break-all">{item.snapshot_hash}</p>
        </div>
        {state?.active_snapshot?.id === item.id && <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">Vigente</span>}
      </div>
    )
  );

  const content = {
    overview: renderOverview,
    study_case: renderStudyCase,
    paee: renderPaee,
    pei: renderPei,
    schedule: renderSchedule,
    lifecycle: renderLifecycle,
    attendances: renderAttendances,
    articulations: renderArticulations,
    evolutions: renderEvolutions,
    history: renderHistory,
  }[activeTab];

  return (
    <div className="fixed inset-0 bg-black/55 z-[70] flex items-center justify-center p-3" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-7xl h-[94vh] flex flex-col overflow-hidden" onClick={(event) => event.stopPropagation()} data-testid="dossie-aee-v2-modal">
        <div className="px-5 py-4 border-b flex items-start justify-between gap-4 bg-white">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-bold text-gray-900">Dossiê Individual AEE V2</h2>
              <SnapshotBadge snapshot={state?.active_snapshot} kind="active" />
              <SnapshotBadge snapshot={state?.working_snapshot} kind="working" />
            </div>
            <p className="text-sm text-gray-500 mt-1">{plano.student_name || 'Estudante'} · Ano letivo {plano.academic_year}</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadState} disabled={loading || saving} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500" title="Recarregar"><RefreshCw size={18} /></button>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500" title="Fechar"><X size={20} /></button>
          </div>
        </div>

        {message && (
          <div className={`mx-5 mt-3 rounded-lg px-4 py-3 text-sm ${message.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
            {message.text}
          </div>
        )}

        <div className="flex flex-1 min-h-0">
          <aside className="w-56 border-r bg-gray-50 overflow-y-auto p-2 hidden md:block">
            {TAB_ITEMS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm mb-1 ${activeTab === tab.id ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-100'}`}
                >
                  <Icon size={16} /> {tab.label}
                </button>
              );
            })}
          </aside>

          <main className="flex-1 min-w-0 overflow-y-auto">
            <div className="md:hidden border-b p-2 overflow-x-auto flex gap-2">
              {TAB_ITEMS.map(tab => <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`shrink-0 px-3 py-2 rounded-lg text-xs ${activeTab === tab.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}`}>{tab.label}</button>)}
            </div>
            <div className="p-5">
              {loading ? (
                <div className="py-20 text-center text-gray-500">Carregando Dossiê AEE V2...</div>
              ) : content ? content() : null}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
