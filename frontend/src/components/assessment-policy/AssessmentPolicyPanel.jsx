import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { extractErrorMessage } from '@/utils/errorHandler';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ADMIN_API = `${API}/assessment-policy-admin`;

const emptyDraft = () => ({
  id: '',
  policyKey: '',
  name: '',
  version: '1',
  academicYear: String(new Date().getFullYear()),
  effectiveFrom: `${new Date().getFullYear()}-01-01`,
  effectiveUntil: `${new Date().getFullYear()}-12-31`,
  series: '',
  schoolIds: '',
  classIds: '',
  componentIds: '',
  educationStages: '',
  modalities: '',
  assessmentMode: '',
  numericMinimum: '',
  numericMaximum: '',
  numericDecimals: '1',
  conceptualScale: '',
  periods: '',
  calculationStrategy: 'weighted_average',
  partialDivisor: 'sum_available_weights',
  calculationDecimals: '1',
  recoveryDecision: '',
  recoveryGroups: '',
  minimumAverage: '',
  attendancePercentage: '',
  attendanceBasis: '',
  normativeType: '',
  normativeTitle: '',
  normativeReference: '',
  periodMapping: '',
  recoveryMapping: '',
  pilotReferenceDate: `${new Date().getFullYear()}-12-31`,
  pilotClassIds: '',
  pilotLimit: '100',
});

const parseList = (value) => {
  const items = String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length ? [...new Set(items)] : null;
};

const parseLines = (value) => String(value || '')
  .split('\n')
  .map((line) => line.trim())
  .filter(Boolean);

const parseConceptScale = (value) => parseLines(value).map((line) => {
  const [code, label, numericValue] = line.split('|').map((item) => item?.trim());
  return { code, label, numeric_value: Number(numericValue) };
});

const parsePeriods = (value) => parseLines(value).map((line) => {
  const [code, label, weight, required] = line.split('|').map((item) => item?.trim());
  return {
    code,
    label,
    weight: Number(weight),
    required_for_final: required === undefined || required === '' ? true : required !== 'false',
  };
});

const parseBoolean = (value) => {
  if (value === 'true') return true;
  if (value === 'false') return false;
  return null;
};

const parseRecoveryGroups = (value) => parseLines(value).map((line) => {
  const [code, label, inputCode, periodCodes, tieBreak, onlyIfImproves] = line
    .split('|')
    .map((item) => item?.trim());
  return {
    code,
    label,
    input_code: inputCode,
    period_codes: String(periodCodes || '').split(',').map((item) => item.trim()).filter(Boolean),
    strategy: 'replace_lowest',
    tie_break: tieBreak || 'highest_weight',
    only_if_improves: parseBoolean(onlyIfImproves),
  };
});

const parseMapping = (value) => {
  const result = {};
  parseLines(value).forEach((line) => {
    const [source, target] = line.split('=').map((item) => item?.trim());
    if (source && target) result[source] = target;
  });
  return result;
};

const formatList = (value) => (Array.isArray(value) ? value.join(', ') : '');

const formatConceptScale = (value) => (Array.isArray(value) ? value : [])
  .map((item) => `${item.code}|${item.label}|${item.numeric_value}`)
  .join('\n');

const formatPeriods = (value) => (Array.isArray(value) ? value : [])
  .map((item) => `${item.code}|${item.label}|${item.weight}|${item.required_for_final !== false}`)
  .join('\n');

const formatRecoveryGroups = (value) => (Array.isArray(value) ? value : [])
  .map((item) => [
    item.code,
    item.label,
    item.input_code,
    Array.isArray(item.period_codes) ? item.period_codes.join(',') : '',
    item.tie_break || '',
    item.only_if_improves == null ? '' : String(item.only_if_improves),
  ].join('|'))
  .join('\n');

const hydrateDraftFromPolicy = (policy) => {
  const assessment = policy?.assessment || {};
  const calculation = assessment.calculation || {};
  const outcome = policy?.academic_outcome || {};
  const scope = policy?.scope || {};
  const normative = Array.isArray(policy?.normative_sources) && policy.normative_sources.length
    ? policy.normative_sources[0]
    : {};
  const academicYear = policy?.academic_year == null ? '' : String(policy.academic_year);

  return {
    ...emptyDraft(),
    id: policy?.id || '',
    policyKey: policy?.policy_key || '',
    name: policy?.name || '',
    version: policy?.version == null ? '' : String(policy.version),
    academicYear,
    effectiveFrom: policy?.effective_from || '',
    effectiveUntil: policy?.effective_until || '',
    series: formatList(scope.series),
    schoolIds: formatList(scope.school_ids),
    classIds: formatList(scope.class_ids),
    componentIds: formatList(scope.component_ids),
    educationStages: formatList(scope.education_stages),
    modalities: formatList(scope.modalities),
    assessmentMode: assessment.mode || '',
    numericMinimum: assessment.numeric_scale?.minimum == null ? '' : String(assessment.numeric_scale.minimum),
    numericMaximum: assessment.numeric_scale?.maximum == null ? '' : String(assessment.numeric_scale.maximum),
    numericDecimals: assessment.numeric_scale?.decimal_places == null ? '1' : String(assessment.numeric_scale.decimal_places),
    conceptualScale: formatConceptScale(assessment.conceptual_scale),
    periods: formatPeriods(assessment.periods),
    calculationStrategy: calculation.strategy || 'weighted_average',
    partialDivisor: calculation.partial_divisor || 'sum_available_weights',
    calculationDecimals: calculation.decimal_places == null ? '1' : String(calculation.decimal_places),
    recoveryDecision: policy?.recovery?.enabled === true ? 'yes' : policy?.recovery?.enabled === false ? 'no' : '',
    recoveryGroups: formatRecoveryGroups(policy?.recovery?.groups),
    minimumAverage: outcome.minimum_component_average == null ? '' : String(outcome.minimum_component_average),
    attendancePercentage: outcome.minimum_attendance_percentage == null ? '' : String(outcome.minimum_attendance_percentage),
    attendanceBasis: outcome.attendance_basis || '',
    normativeType: normative.type || '',
    normativeTitle: normative.title || '',
    normativeReference: normative.reference || '',
    // Mapping legado não pertence à AssessmentPolicy persistida. Na retomada,
    // deve ser fornecido de novo de forma explícita; nunca reconstruído/inferido.
    periodMapping: '',
    recoveryMapping: '',
    pilotReferenceDate: policy?.effective_until || (academicYear ? `${academicYear}-12-31` : ''),
    pilotClassIds: '',
    pilotLimit: '100',
  };
};

const statusLabel = {
  draft: 'Rascunho',
  validated: 'Validada',
  published: 'Publicada',
  superseded: 'Substituída',
  retired: 'Retirada',
};

function TechnicalTextarea({ label, help, value, onChange, placeholder, rows = 4, testId }) {
  return (
    <div>
      <Label>{label}</Label>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={rows}
        data-testid={testId}
        className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
      />
      {help && <p className="mt-1 text-xs text-gray-500">{help}</p>}
    </div>
  );
}

export default function AssessmentPolicyPanel() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [persistedPolicy, setPersistedPolicy] = useState(null);
  const [preview, setPreview] = useState(null);
  const [pilotReport, setPilotReport] = useState(null);

  const setField = (field, value) => setDraft((current) => ({ ...current, [field]: value }));

  const loadOverview = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${ADMIN_API}/overview`);
      setOverview(response.data);
    } catch (error) {
      setMessage({ type: 'error', text: extractErrorMessage(error, 'Não foi possível carregar as políticas avaliativas.') });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const legacy = overview?.legacy_reference || {};
  const policyEditable = !persistedPolicy || persistedPolicy.status === 'draft';

  const mappingPayload = useMemo(() => ({
    period_field_map: parseMapping(draft.periodMapping),
    recovery_field_map: parseMapping(draft.recoveryMapping),
  }), [draft.periodMapping, draft.recoveryMapping]);

  const buildPolicy = useCallback(() => {
    const assessmentMode = draft.assessmentMode;
    const year = Number(draft.academicYear);
    const recoveryEnabled = draft.recoveryDecision === 'yes';
    const existingCalculation = persistedPolicy?.assessment?.calculation || {};
    const existingOutcome = persistedPolicy?.academic_outcome || {};
    const existingSources = Array.isArray(persistedPolicy?.normative_sources)
      ? persistedPolicy.normative_sources
      : [];
    const primarySource = draft.normativeType.trim() && draft.normativeTitle.trim() ? {
      type: draft.normativeType.trim(),
      title: draft.normativeTitle.trim(),
      reference: draft.normativeReference.trim() || null,
    } : null;

    const policy = {
      id: persistedPolicy?.id || draft.id || (globalThis.crypto?.randomUUID?.() || `policy-${Date.now()}`),
      policy_key: draft.policyKey.trim(),
      version: Number(draft.version),
      revision: persistedPolicy?.revision || 1,
      mantenedora_id: overview?.mantenedora?.id,
      name: draft.name.trim(),
      status: 'draft',
      academic_year: year,
      effective_from: draft.effectiveFrom,
      effective_until: draft.effectiveUntil,
      scope: {
        school_ids: parseList(draft.schoolIds),
        class_ids: parseList(draft.classIds),
        series: parseList(draft.series),
        component_ids: parseList(draft.componentIds),
        education_stages: parseList(draft.educationStages),
        modalities: parseList(draft.modalities),
      },
      assessment: {
        mode: assessmentMode,
        conceptual_scale: assessmentMode === 'conceptual' ? parseConceptScale(draft.conceptualScale) : null,
        numeric_scale: assessmentMode === 'numeric' ? {
          minimum: Number(draft.numericMinimum),
          maximum: Number(draft.numericMaximum),
          decimal_places: Number(draft.numericDecimals),
        } : null,
        periods: parsePeriods(draft.periods),
        calculation: {
          strategy: draft.calculationStrategy,
          partial_divisor: draft.partialDivisor,
          final_divisor: existingCalculation.final_divisor || 'sum_all_weights',
          rounding_mode: existingCalculation.rounding_mode || 'half_up',
          decimal_places: Number(draft.calculationDecimals),
        },
      },
      recovery: {
        enabled: recoveryEnabled,
        groups: recoveryEnabled ? parseRecoveryGroups(draft.recoveryGroups) : [],
      },
      academic_outcome: {
        minimum_component_average: draft.minimumAverage === '' ? null : Number(draft.minimumAverage),
        require_all_components: existingOutcome.require_all_components ?? true,
        component_strategy: existingOutcome.component_strategy || 'all_required_components',
        minimum_attendance_percentage: draft.attendancePercentage === '' ? null : Number(draft.attendancePercentage),
        attendance_basis: draft.attendanceBasis || null,
        dependency: existingOutcome.dependency || { enabled: false, outcomes: [] },
        council: existingOutcome.council || {
          enabled: false,
          can_override_academic_result: false,
          requires_reason: true,
          requires_audit_event: true,
        },
      },
      normative_sources: primarySource
        ? [primarySource, ...existingSources.slice(1)]
        : existingSources.slice(1),
      parent_policy: persistedPolicy?.parent_policy || null,
      rule_hash: null,
      created_by: persistedPolicy?.created_by || null,
      created_at: persistedPolicy?.created_at || null,
      validated_by: null,
      validated_at: null,
      published_by: null,
      published_at: null,
    };
    return policy;
  }, [draft, overview, persistedPolicy]);

  const configurationPayload = useCallback(() => ({
    policy: buildPolicy(),
    legacy_mapping: mappingPayload,
    tolerance: '0.01',
  }), [buildPolicy, mappingPayload]);

  const requireExplicitBasics = () => {
    const missing = [];
    if (!draft.policyKey.trim()) missing.push('chave da policy');
    if (!draft.name.trim()) missing.push('nome');
    if (!draft.assessmentMode) missing.push('modo de avaliação');
    if (!draft.periods.trim()) missing.push('períodos');
    if (!draft.recoveryDecision) missing.push('decisão explícita sobre recuperação');
    if (missing.length) {
      setMessage({ type: 'error', text: `Preencha antes de continuar: ${missing.join(', ')}.` });
      return false;
    }
    return true;
  };

  const handlePreview = async () => {
    if (!policyEditable) {
      setMessage({ type: 'warning', text: 'Policy validada é somente leitura. O piloto usa a versão persistida.' });
      return;
    }
    if (!requireExplicitBasics()) return;
    try {
      setBusy(true);
      setPilotReport(null);
      const response = await axios.post(`${ADMIN_API}/preview`, configurationPayload());
      setPreview(response.data);
      setMessage({
        type: response.data.can_dry_run ? 'success' : 'warning',
        text: response.data.can_dry_run
          ? 'Configuração semanticamente completa para dry-run piloto.'
          : 'Pré-validação concluída. Existem pendências antes do piloto.',
      });
    } catch (error) {
      setMessage({ type: 'error', text: extractErrorMessage(error, 'Falha ao pré-validar a política.') });
    } finally {
      setBusy(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!policyEditable) {
      setMessage({ type: 'warning', text: 'Policy validada não pode ser editada como rascunho nesta sprint.' });
      return;
    }
    if (!requireExplicitBasics()) return;
    try {
      setBusy(true);
      const payload = configurationPayload();
      const response = persistedPolicy
        ? await axios.put(`${ADMIN_API}/drafts/${persistedPolicy.id}`, payload)
        : await axios.post(`${ADMIN_API}/drafts`, payload);
      setPersistedPolicy(response.data);
      setDraft((current) => ({ ...current, id: response.data.id }));
      setMessage({ type: 'success', text: 'Rascunho salvo. A regra ainda NÃO está publicada nem ativa no SIGESC.' });
      await loadOverview();
    } catch (error) {
      setMessage({ type: 'error', text: extractErrorMessage(error, 'Não foi possível salvar o rascunho.') });
    } finally {
      setBusy(false);
    }
  };

  const handleValidate = async () => {
    if (!persistedPolicy?.id || persistedPolicy.status !== 'draft') return;
    try {
      setBusy(true);
      const response = await axios.post(`${ADMIN_API}/drafts/${persistedPolicy.id}/validate`);
      setPersistedPolicy(response.data.policy);
      setMessage({ type: 'success', text: 'Policy validada formalmente. Ela continua NÃO publicada e NÃO ativa.' });
      await loadOverview();
    } catch (error) {
      setMessage({ type: 'error', text: extractErrorMessage(error, 'A policy possui pendências e não pôde ser validada.') });
    } finally {
      setBusy(false);
    }
  };

  const handlePilot = async () => {
    if (!persistedPolicy?.id) {
      setMessage({ type: 'error', text: 'Salve o rascunho antes de executar o piloto.' });
      return;
    }
    try {
      setBusy(true);
      const response = await axios.post(`${ADMIN_API}/pilot`, {
        policy_id: persistedPolicy.id,
        legacy_mapping: mappingPayload,
        reference_date: draft.pilotReferenceDate,
        class_ids: parseList(draft.pilotClassIds),
        tolerance: '0.01',
        limit: draft.pilotLimit ? Number(draft.pilotLimit) : null,
      });
      setPilotReport(response.data);
      setMessage({ type: 'success', text: 'Dry-run piloto concluído em modo somente leitura.' });
    } catch (error) {
      setMessage({ type: 'error', text: extractErrorMessage(error, 'Não foi possível executar o dry-run piloto.') });
    } finally {
      setBusy(false);
    }
  };

  const startNewDraft = () => {
    setDraft(emptyDraft());
    setPersistedPolicy(null);
    setPreview(null);
    setPilotReport(null);
    setMessage(null);
    setEditorOpen(true);
  };

  const resumeDraft = (policy) => {
    if (policy?.status !== 'draft') {
      setMessage({ type: 'warning', text: 'Somente policies em status rascunho podem ser retomadas para edição.' });
      return;
    }
    setDraft(hydrateDraftFromPolicy(policy));
    setPersistedPolicy(policy);
    setPreview(null);
    setPilotReport(null);
    setMessage({
      type: 'warning',
      text: 'Rascunho retomado sem inferências. O mapping legado não é persistido e deve ser informado novamente antes do piloto.',
    });
    setEditorOpen(true);
  };

  if (loading) {
    return (
      <Card data-testid="assessment-policy-panel">
        <CardContent className="flex items-center gap-2 py-8 text-sm text-gray-600">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando políticas avaliativas...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="assessment-policy-panel" className="border-blue-200 lg:col-span-2">
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ShieldCheck className="h-5 w-5 text-blue-700" />
              Política de Avaliação
            </CardTitle>
            <p className="mt-1 text-sm text-gray-600">
              Regras versionadas por mantenedora, ano, escola, turma, série e componente.
            </p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={loadOverview}>
              <RefreshCw className="mr-2 h-4 w-4" /> Atualizar
            </Button>
            <Button type="button" size="sm" onClick={startNewDraft} data-testid="assessment-policy-new-draft">
              <Plus className="mr-2 h-4 w-4" /> Novo rascunho
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <p className="font-semibold">Atenção à fonte da regra</p>
              <p className="mt-1">
                Os campos antigos abaixo são apenas referência histórica. Eles não geram nem alteram automaticamente uma policy.
                A fonte única das novas regras é <code>assessment_policies</code>.
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border bg-gray-50 p-3">
            <p className="text-xs uppercase tracking-wide text-gray-500">Média legada</p>
            <p className="mt-1 text-lg font-semibold">{legacy.media_aprovacao ?? 'Não informada'}</p>
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-xs"
              onClick={() => setField('minimumAverage', legacy.media_aprovacao == null ? '' : String(legacy.media_aprovacao))}
              disabled={legacy.media_aprovacao == null || !policyEditable}
            >
              Usar explicitamente no rascunho
            </Button>
          </div>
          <div className="rounded-lg border bg-gray-50 p-3">
            <p className="text-xs uppercase tracking-wide text-gray-500">Frequência legada</p>
            <p className="mt-1 text-lg font-semibold">{legacy.frequencia_minima == null ? 'Não informada' : `${legacy.frequencia_minima}%`}</p>
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-xs"
              onClick={() => setField('attendancePercentage', legacy.frequencia_minima == null ? '' : String(legacy.frequencia_minima))}
              disabled={legacy.frequencia_minima == null || !policyEditable}
            >
              Usar explicitamente no rascunho
            </Button>
          </div>
          <div className="rounded-lg border bg-gray-50 p-3">
            <p className="text-xs uppercase tracking-wide text-gray-500">Ativação</p>
            <p className="mt-1 font-semibold text-red-700">Publicação indisponível</p>
            <p className="text-xs text-gray-600">Sprint 007: rascunho, validação e piloto somente.</p>
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Policies cadastradas</h3>
            <span className="text-xs text-gray-500">{overview?.policies?.length || 0} versão(ões)</span>
          </div>
          <div className="space-y-2">
            {(overview?.policies || []).length === 0 && (
              <div className="rounded-lg border border-dashed p-4 text-sm text-gray-500">
                Nenhuma policy versionada cadastrada para esta mantenedora.
              </div>
            )}
            {(overview?.policies || []).map((policy) => (
              <div key={policy.id} className="flex flex-col gap-2 rounded-lg border p-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="font-medium">{policy.name}</p>
                  <p className="text-xs text-gray-500">
                    {policy.policy_key} · v{policy.version} · rev.{policy.revision} · {policy.academic_year} · {statusLabel[policy.status] || policy.status}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`w-fit rounded-full px-2 py-1 text-xs font-medium ${
                    policy.status === 'published'
                      ? 'bg-green-100 text-green-800'
                      : policy.status === 'validated'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-gray-100 text-gray-700'
                  }`}>
                    {statusLabel[policy.status] || policy.status}
                  </span>
                  {policy.status === 'draft' && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => resumeDraft(policy)}
                      data-testid="assessment-policy-resume-draft"
                    >
                      Retomar rascunho
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {message && (
          <div className={`rounded-lg border p-3 text-sm ${
            message.type === 'success'
              ? 'border-green-200 bg-green-50 text-green-800'
              : message.type === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-900'
                : 'border-red-200 bg-red-50 text-red-800'
          }`}>
            {message.text}
          </div>
        )}

        {editorOpen && (
          <div className="space-y-6 rounded-xl border border-blue-200 bg-blue-50/30 p-4" data-testid="assessment-policy-editor">
            <div>
              <h3 className="font-semibold text-gray-900">
                {persistedPolicy ? 'Assistente de configuração — rascunho retomado' : 'Assistente de configuração — novo rascunho'}
              </h3>
              <p className="text-xs text-gray-600">
                Nada neste formulário publica a regra. Campos vazios permanecem pendências; não são completados por inferência.
              </p>
            </div>

            {persistedPolicy?.status === 'validated' && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900">
                Esta policy está validada e os campos normativos abaixo ficam somente leitura. O mapping legado e os parâmetros do piloto continuam editáveis porque não alteram a policy persistida.
              </div>
            )}

            {persistedPolicy?.status === 'draft' && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                Retomada segura: identidade e revisão foram preservadas. O mapping legado foi deixado vazio deliberadamente e precisa ser informado novamente para preview/piloto.
              </div>
            )}

            <fieldset disabled={!policyEditable} className="space-y-6">
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <Label>Chave da policy *</Label>
                  <Input
                    value={draft.policyKey}
                    onChange={(event) => setField('policyKey', event.target.value)}
                    placeholder="Ex: EF_1_2_CONCEITUAL_2026"
                    disabled={Boolean(persistedPolicy)}
                  />
                </div>
                <div className="md:col-span-2">
                  <Label>Nome *</Label>
                  <Input value={draft.name} onChange={(event) => setField('name', event.target.value)} placeholder="Nome institucional da regra" />
                </div>
                <div>
                  <Label>Versão</Label>
                  <Input
                    type="number"
                    min="1"
                    value={draft.version}
                    onChange={(event) => setField('version', event.target.value)}
                    disabled={Boolean(persistedPolicy)}
                  />
                </div>
                <div>
                  <Label>Ano letivo</Label>
                  <Input type="number" value={draft.academicYear} onChange={(event) => {
                    const year = event.target.value;
                    setDraft((current) => ({ ...current, academicYear: year, effectiveFrom: `${year}-01-01`, effectiveUntil: `${year}-12-31`, pilotReferenceDate: `${year}-12-31` }));
                  }} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Vigência inicial</Label>
                    <Input type="date" value={draft.effectiveFrom} onChange={(event) => setField('effectiveFrom', event.target.value)} />
                  </div>
                  <div>
                    <Label>Vigência final</Label>
                    <Input type="date" value={draft.effectiveUntil} onChange={(event) => setField('effectiveUntil', event.target.value)} />
                  </div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>Séries/anos</Label>
                  <Input value={draft.series} onChange={(event) => setField('series', event.target.value)} placeholder="Ex: 1º Ano, 2º Ano" />
                </div>
                <div>
                  <Label>Etapas de ensino</Label>
                  <Input value={draft.educationStages} onChange={(event) => setField('educationStages', event.target.value)} placeholder="Opcional, separados por vírgula" />
                </div>
                <div>
                  <Label>IDs de escolas</Label>
                  <Input value={draft.schoolIds} onChange={(event) => setField('schoolIds', event.target.value)} placeholder="Opcional; vazio = sem restrição" />
                </div>
                <div>
                  <Label>IDs de turmas</Label>
                  <Input value={draft.classIds} onChange={(event) => setField('classIds', event.target.value)} placeholder="Opcional; vazio = sem restrição" />
                </div>
                <div>
                  <Label>IDs de componentes</Label>
                  <Input value={draft.componentIds} onChange={(event) => setField('componentIds', event.target.value)} placeholder="Opcional; vazio = sem restrição" />
                </div>
                <div>
                  <Label>Modalidades</Label>
                  <Input value={draft.modalities} onChange={(event) => setField('modalities', event.target.value)} placeholder="Opcional, separados por vírgula" />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <Label>Modo de avaliação *</Label>
                  <select
                    value={draft.assessmentMode}
                    onChange={(event) => setField('assessmentMode', event.target.value)}
                    className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                  >
                    <option value="">Selecione explicitamente</option>
                    <option value="numeric">Numérica</option>
                    <option value="conceptual">Conceitual</option>
                  </select>
                </div>
                <div>
                  <Label>Estratégia de cálculo</Label>
                  <select value={draft.calculationStrategy} onChange={(event) => setField('calculationStrategy', event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                    <option value="weighted_average">Média ponderada</option>
                    <option value="simple_average">Média simples</option>
                  </select>
                </div>
                <div>
                  <Label>Divisor durante o ano</Label>
                  <select value={draft.partialDivisor} onChange={(event) => setField('partialDivisor', event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                    <option value="sum_available_weights">Somente períodos lançados</option>
                    <option value="sum_all_weights">Todos os períodos previstos</option>
                  </select>
                </div>
              </div>

              {draft.assessmentMode === 'numeric' && (
                <div className="grid gap-4 md:grid-cols-3">
                  <div><Label>Escala mínima</Label><Input type="number" step="0.1" value={draft.numericMinimum} onChange={(event) => setField('numericMinimum', event.target.value)} /></div>
                  <div><Label>Escala máxima</Label><Input type="number" step="0.1" value={draft.numericMaximum} onChange={(event) => setField('numericMaximum', event.target.value)} /></div>
                  <div><Label>Casas decimais</Label><Input type="number" min="0" max="4" value={draft.numericDecimals} onChange={(event) => setField('numericDecimals', event.target.value)} /></div>
                </div>
              )}

              {draft.assessmentMode === 'conceptual' && (
                <TechnicalTextarea
                  label="Escala conceitual"
                  value={draft.conceptualScale}
                  onChange={(value) => setField('conceptualScale', value)}
                  placeholder={'CODIGO|Descrição|valor numérico\nCODIGO2|Descrição|valor'}
                  help="Uma linha por conceito. O valor numérico pertence à policy e não é padronizado pelo SIGESC."
                  testId="assessment-policy-concept-scale"
                />
              )}

              <TechnicalTextarea
                label="Períodos avaliativos *"
                value={draft.periods}
                onChange={(value) => setField('periods', value)}
                placeholder={'b1|1º Bimestre|2|true\nb2|2º Bimestre|3|true'}
                help="Formato: código|rótulo|peso|required_for_final. Nenhum peso é preenchido automaticamente."
                testId="assessment-policy-periods"
              />

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label>Recuperação existe nesta policy? *</Label>
                  <select value={draft.recoveryDecision} onChange={(event) => setField('recoveryDecision', event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                    <option value="">Confirme explicitamente</option>
                    <option value="no">Não</option>
                    <option value="yes">Sim</option>
                  </select>
                </div>
                <div>
                  <Label>Casas decimais do cálculo</Label>
                  <Input type="number" min="0" max="4" value={draft.calculationDecimals} onChange={(event) => setField('calculationDecimals', event.target.value)} />
                </div>
              </div>

              {draft.recoveryDecision === 'yes' && (
                <TechnicalTextarea
                  label="Grupos de recuperação"
                  value={draft.recoveryGroups}
                  onChange={(value) => setField('recoveryGroups', value)}
                  placeholder={'rec1|Recuperação|rec_s1|b1,b2|highest_weight|true'}
                  help="Formato: código|rótulo|entrada|períodos|desempate|only_if_improves. Use true/false explicitamente."
                  testId="assessment-policy-recovery-groups"
                />
              )}

              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <Label>Média mínima por componente</Label>
                  <Input type="number" step="0.1" value={draft.minimumAverage} onChange={(event) => setField('minimumAverage', event.target.value)} placeholder="Sem inferência" />
                </div>
                <div>
                  <Label>Frequência mínima (%)</Label>
                  <Input type="number" step="0.1" min="0" max="100" value={draft.attendancePercentage} onChange={(event) => setField('attendancePercentage', event.target.value)} placeholder="Sem inferência" />
                </div>
                <div>
                  <Label>Base da frequência</Label>
                  <select value={draft.attendanceBasis} onChange={(event) => setField('attendanceBasis', event.target.value)} className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                    <option value="">Não definida</option>
                    <option value="global">Global</option>
                    <option value="stage">Etapa</option>
                    <option value="component">Componente</option>
                  </select>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div><Label>Tipo da fonte normativa</Label><Input value={draft.normativeType} onChange={(event) => setField('normativeType', event.target.value)} placeholder="Ex: resolução, documento_semed" /></div>
                <div><Label>Título da fonte normativa</Label><Input value={draft.normativeTitle} onChange={(event) => setField('normativeTitle', event.target.value)} placeholder="Documento/ato oficial" /></div>
                <div><Label>Referência</Label><Input value={draft.normativeReference} onChange={(event) => setField('normativeReference', event.target.value)} placeholder="Número, data, processo ou observação" /></div>
              </div>
            </fieldset>

            <div className="grid gap-4 md:grid-cols-2">
              <TechnicalTextarea
                label="Mapping legado dos períodos"
                value={draft.periodMapping}
                onChange={(value) => setField('periodMapping', value)}
                placeholder={'campo_legado=codigo_periodo\nb1=b1'}
                help="Necessário para o dry-run. Não integra a norma; documenta como os campos atuais alimentam a policy. Na retomada, permanece vazio até preenchimento explícito."
                testId="assessment-policy-period-mapping"
              />
              <TechnicalTextarea
                label="Mapping legado da recuperação"
                value={draft.recoveryMapping}
                onChange={(value) => setField('recoveryMapping', value)}
                placeholder={'campo_recuperacao=codigo_entrada'}
                help="Obrigatório quando a policy possui recuperação. O SIGESC não presume rec_s1, rec_s2 ou recovery."
                testId="assessment-policy-recovery-mapping"
              />
            </div>

            {preview && (
              <div className="rounded-lg border bg-white p-4" data-testid="assessment-policy-preview-result">
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className={`rounded-full px-2 py-1 ${preview.can_save_draft ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>Salvar draft: {preview.can_save_draft ? 'sim' : 'não'}</span>
                  <span className={`rounded-full px-2 py-1 ${preview.can_validate ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>Validar: {preview.can_validate ? 'sim' : 'não'}</span>
                  <span className={`rounded-full px-2 py-1 ${preview.can_dry_run ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>Piloto: {preview.can_dry_run ? 'sim' : 'não'}</span>
                </div>
                {preview.issues?.length > 0 && (
                  <div className="mt-3 space-y-1 text-xs">
                    {preview.issues.map((issue, index) => (
                      <div key={`${issue.code}-${index}`} className={issue.severity === 'error' ? 'text-red-700' : 'text-amber-700'}>
                        <strong>{issue.code}</strong> — {issue.message}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {policyEditable && (
              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="button" variant="outline" onClick={handlePreview} disabled={busy}>
                  <ClipboardCheck className="mr-2 h-4 w-4" /> Pré-validar
                </Button>
                <Button type="button" onClick={handleSaveDraft} disabled={busy} data-testid="assessment-policy-save-draft">
                  {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  {persistedPolicy ? 'Salvar nova revisão do rascunho' : 'Salvar rascunho'}
                </Button>
                {persistedPolicy?.status === 'draft' && (
                  <Button type="button" variant="outline" onClick={handleValidate} disabled={busy}>
                    <CheckCircle2 className="mr-2 h-4 w-4" /> Validar formalmente
                  </Button>
                )}
              </div>
            )}

            {persistedPolicy && (
              <div className="space-y-4 rounded-lg border border-purple-200 bg-purple-50/40 p-4">
                <div>
                  <h4 className="flex items-center gap-2 font-semibold text-purple-900"><Beaker className="h-4 w-4" /> Dry-run piloto</h4>
                  <p className="text-xs text-purple-800">Somente leitura. Não altera notas, médias, status, frequência ou matrícula.</p>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <div><Label>Data de referência</Label><Input type="date" value={draft.pilotReferenceDate} onChange={(event) => setField('pilotReferenceDate', event.target.value)} /></div>
                  <div><Label>IDs de turmas do piloto</Label><Input value={draft.pilotClassIds} onChange={(event) => setField('pilotClassIds', event.target.value)} placeholder="Opcional; vírgulas" /></div>
                  <div><Label>Limite de registros</Label><Input type="number" min="1" max="5000" value={draft.pilotLimit} onChange={(event) => setField('pilotLimit', event.target.value)} /></div>
                </div>
                <Button type="button" variant="outline" onClick={handlePilot} disabled={busy} data-testid="assessment-policy-run-pilot">
                  <Beaker className="mr-2 h-4 w-4" /> Executar piloto read-only
                </Button>
                {pilotReport && (
                  <div className="grid gap-2 text-sm md:grid-cols-4" data-testid="assessment-policy-pilot-report">
                    <div className="rounded border bg-white p-2"><span className="text-xs text-gray-500">Lidos</span><div className="font-semibold">{pilotReport.scanned}</div></div>
                    <div className="rounded border bg-white p-2"><span className="text-xs text-gray-500">No escopo</span><div className="font-semibold">{pilotReport.in_scope}</div></div>
                    <div className="rounded border bg-white p-2"><span className="text-xs text-gray-500">Divergências</span><div className="font-semibold">{pilotReport.differences}</div></div>
                    <div className="rounded border bg-white p-2"><span className="text-xs text-gray-500">Compatibilidade</span><div className="font-semibold">{pilotReport.match_rate == null ? '—' : `${(pilotReport.match_rate * 100).toFixed(1)}%`}</div></div>
                    <div className="md:col-span-4 text-xs text-gray-600">Fora do escopo da policy: {pilotReport.skipped_out_of_scope} · Issues: {pilotReport.unresolved}</div>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-start gap-2 rounded-lg border border-gray-200 bg-white p-3 text-xs text-gray-600">
              <FileText className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Validação não equivale a publicação. Esta sprint não possui comando de publicação ou cutover.</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
