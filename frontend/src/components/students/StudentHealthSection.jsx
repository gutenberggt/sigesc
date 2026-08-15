import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, Save, ShieldCheck, Stethoscope } from 'lucide-react';

import { studentHealthAPI } from '@/services/api';
import {
  BLOOD_TYPES,
  EMPTY_HEALTH_PROFILE,
  inputToTriState,
  normalizeHealthPayloadForSave,
  normalizeHealthProfile,
  triStateToInput,
} from '@/utils/studentHealth';

const TriStateSelect = ({ label, value, onChange, disabled }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    <select
      value={triStateToInput(value)}
      onChange={event => onChange(inputToTriState(event.target.value))}
      disabled={disabled}
      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
    >
      <option value="">Não informado</option>
      <option value="false">Não</option>
      <option value="true">Sim</option>
    </select>
  </div>
);

export function StudentHealthSection({ studentId, studentName, viewMode = false }) {
  const [profile, setProfile] = useState({ ...EMPTY_HEALTH_PROFILE });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const [restricted, setRestricted] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setMessage(null);
      setRestricted(false);
      setCanWrite(false);
      if (!studentId) {
        setProfile({ ...EMPTY_HEALTH_PROFILE });
        return;
      }

      setLoading(true);
      try {
        const result = await studentHealthAPI.getByStudent(studentId);
        if (!active) return;
        setProfile(normalizeHealthProfile(result?.profile));
        setCanWrite(result?.can_write === true);
      } catch (error) {
        if (!active) return;
        if (error?.response?.status === 403) {
          setRestricted(true);
        } else {
          setMessage({ type: 'error', text: 'Não foi possível carregar a ficha de saúde.' });
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    return () => { active = false; };
  }, [studentId]);

  const updateField = (field, value) => {
    setProfile(prev => ({ ...prev, [field]: value }));
    setMessage(null);
  };

  const save = async () => {
    if (!studentId || !canWrite || viewMode) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload = normalizeHealthPayloadForSave(profile);
      const result = await studentHealthAPI.save(studentId, payload);
      setProfile(normalizeHealthProfile(result?.profile));
      setMessage({ type: 'success', text: 'Ficha de saúde salva com sucesso.' });
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setMessage({
        type: 'error',
        text: typeof detail === 'string' ? detail : 'Não foi possível salvar a ficha de saúde.',
      });
    } finally {
      setSaving(false);
    }
  };

  if (restricted) {
    return (
      <section className="mt-8 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="text-amber-700 mt-0.5" size={20} />
          <div>
            <h3 className="font-semibold text-amber-900">Saúde e Necessidades Alimentares</h3>
            <p className="text-sm text-amber-800 mt-1">
              Dados de saúde possuem acesso restrito. Seu perfil não tem autorização para visualizar esta ficha.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const disabled = viewMode || !canWrite || saving;

  return (
    <section className="mt-8 rounded-xl border border-red-100 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Stethoscope className="text-red-600" size={20} />
            Saúde e Necessidades Alimentares
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            Informações sensíveis, com acesso restrito e auditado{studentName ? ` — ${studentName}` : ''}.
          </p>
        </div>
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <ShieldCheck size={15} />
          Não incluído em listagens gerais
        </div>
      </div>

      {!studentId && (
        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
          Salve o cadastro do estudante antes de registrar informações de saúde.
        </div>
      )}

      {studentId && loading && (
        <div className="py-8 flex items-center justify-center gap-2 text-gray-500">
          <Loader2 className="animate-spin" size={18} /> Carregando ficha de saúde...
        </div>
      )}

      {studentId && !loading && (
        <div className="mt-5 space-y-5">
          {message && (
            <div className={`rounded-lg border p-3 text-sm ${
              message.type === 'success'
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}>
              {message.type === 'error' && <AlertTriangle className="inline mr-1" size={16} />}
              {message.text}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tipo sanguíneo</label>
              <select
                value={profile.blood_type || ''}
                onChange={event => updateField('blood_type', event.target.value || null)}
                disabled={disabled}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Não informado</option>
                {BLOOD_TYPES.map(type => <option key={type} value={type}>{type}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TriStateSelect label="Alergias" value={profile.has_allergies} onChange={value => updateField('has_allergies', value)} disabled={disabled} />
            {profile.has_allergies === true && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Descrição das alergias</label>
                <textarea rows={3} value={profile.allergies_description || ''} onChange={event => updateField('allergies_description', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TriStateSelect label="Comorbidades" value={profile.has_comorbidities} onChange={value => updateField('has_comorbidities', value)} disabled={disabled} />
            {profile.has_comorbidities === true && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Descrição das comorbidades</label>
                <textarea rows={3} value={profile.comorbidities_description || ''} onChange={event => updateField('comorbidities_description', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TriStateSelect label="Medicação de uso contínuo" value={profile.uses_continuous_medication} onChange={value => updateField('uses_continuous_medication', value)} disabled={disabled} />
            {profile.uses_continuous_medication === true && (
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Medicamento(s)</label>
                  <textarea rows={2} value={profile.continuous_medication_description || ''} onChange={event => updateField('continuous_medication_description', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Orientações relevantes</label>
                  <textarea rows={2} value={profile.continuous_medication_instructions || ''} onChange={event => updateField('continuous_medication_instructions', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <TriStateSelect label="Necessidade nutricional individualizada" value={profile.individualized_nutritional_need} onChange={value => updateField('individualized_nutritional_need', value)} disabled={disabled} />
            {profile.individualized_nutritional_need === true && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Descrição da necessidade nutricional</label>
                <textarea rows={3} value={profile.nutritional_need_details || ''} onChange={event => updateField('nutritional_need_details', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Observações de saúde</label>
            <textarea rows={3} value={profile.health_notes || ''} onChange={event => updateField('health_notes', event.target.value)} disabled={disabled} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" />
          </div>

          {!viewMode && canWrite && (
            <div className="flex justify-end">
              <button type="button" onClick={save} disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60">
                {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                Salvar ficha de saúde
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
