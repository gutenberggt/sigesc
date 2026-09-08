import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { BookOpen, CheckCircle2, FileText, Loader2, Plus, RefreshCw, Upload, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { coursesAPI } from '@/services/api';

const API = process.env.REACT_APP_BACKEND_URL;

const SOURCE_TYPES = [
  ['DCM', 'Documento Curricular Municipal (DCM)'],
  ['REFERENCIAL_MUNICIPAL', 'Referencial Municipal'],
  ['BNCC', 'BNCC'],
  ['BNCC_COMPUTACAO', 'BNCC / Referencial de Computação'],
  ['OUTRO_OFICIAL', 'Outro documento oficial'],
];

function versionScopeLabel(version) {
  const grade = (version.grade_scope || [])[0] || '—';
  return `${version.component_name || 'Componente'} · ${grade}º ano · ${version.bimestre}º bimestre · ${version.academic_year}`;
}

function StatusBadge({ status }) {
  const cls = status === 'published'
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : status === 'superseded'
      ? 'bg-gray-100 text-gray-600 border-gray-200'
      : 'bg-amber-50 text-amber-700 border-amber-200';
  const label = status === 'published' ? 'Publicada' : status === 'superseded' ? 'Substituída' : 'Rascunho';
  return <span className={`inline-flex px-2 py-0.5 rounded-full border text-xs font-medium ${cls}`}>{label}</span>;
}

function SkillList({ title, items = [], tone = 'blue' }) {
  if (!items.length) return null;
  const cls = tone === 'green' ? 'border-emerald-200 bg-emerald-50/50' : tone === 'violet' ? 'border-violet-200 bg-violet-50/50' : 'border-blue-200 bg-blue-50/50';
  return (
    <div className={`border rounded-lg p-3 ${cls}`}>
      <h4 className="font-semibold text-sm mb-2">{title}</h4>
      <div className="space-y-2">
        {items.map((item, idx) => (
          <div key={`${item.code || item.practice_or_axis}-${idx}`} className="text-sm">
            {item.code && <span className="font-mono font-semibold mr-2">{item.code}</span>}
            <span>{item.focus || item.purpose || item.practice_or_axis || item.usage || ''}</span>
            {!!item.knowledge_objects?.length && (
              <div className="mt-1 text-xs text-gray-600">Objetos: {item.knowledge_objects.join(' · ')}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ScopedCurriculumVersions({ onOpenSkillImport }) {
  const currentYear = new Date().getFullYear();
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [sources, setSources] = useState([]);
  const [courses, setCourses] = useState([]);
  const [versions, setVersions] = useState([]);
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [plan, setPlan] = useState(null);
  const [sourceFormOpen, setSourceFormOpen] = useState(false);
  const [sourceForm, setSourceForm] = useState({ title: '', source_type: 'DCM', scope: 'tenant', description: '' });
  const [form, setForm] = useState({
    academic_year: currentYear,
    component_id: '',
    grade: 6,
    bimestre: 3,
    source_ids: [],
    name: '',
    notes: '',
    file: null,
  });

  const loadPlan = useCallback(async (version) => {
    if (!version) { setPlan(null); return; }
    try {
      const r = await axios.get(`${API}/api/curriculum/teaching-plans`, {
        params: {
          academic_year: version.academic_year,
          component_id: version.component_id,
          bimestre: version.bimestre,
        },
      });
      const grade = String((version.grade_scope || [])[0] || '');
      const found = (r.data?.items || []).find((item) => (
        item.curriculum_version_id === version.id
        && (item.grade_scope || []).map(String).includes(grade)
      ));
      setPlan(found || null);
    } catch {
      setPlan(null);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [sourcesR, coursesR, versionsR] = await Promise.all([
        axios.get(`${API}/api/curriculum/sources`),
        coursesAPI.list(),
        axios.get(`${API}/api/curriculum/import/scoped-versions`, { params: { academic_year: form.academic_year } }),
      ]);
      setSources(sourcesR.data?.items || []);
      const courseItems = Array.isArray(coursesR) ? coursesR : (coursesR?.items || coursesR?.data || []);
      setCourses(courseItems.filter((item) => item?.id && item?.name));
      setVersions(versionsR.data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Falha ao carregar versões curriculares.');
    } finally {
      setLoading(false);
    }
  }, [form.academic_year]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const selectedSourceSet = useMemo(() => new Set(form.source_ids), [form.source_ids]);
  const unresolved = selectedVersion?.skill_resolution?.filter((item) => !item.resolved) || [];

  const selectVersion = async (version) => {
    setSelectedVersion(version);
    await loadPlan(version);
  };

  const toggleSource = (id) => {
    setForm((prev) => ({
      ...prev,
      source_ids: prev.source_ids.includes(id)
        ? prev.source_ids.filter((value) => value !== id)
        : [...prev.source_ids, id],
    }));
  };

  const createSource = async () => {
    if (!sourceForm.title.trim()) return toast.info('Informe o título da fonte curricular.');
    try {
      const payload = { ...sourceForm, title: sourceForm.title.trim(), description: sourceForm.description.trim() || null };
      const r = await axios.post(`${API}/api/curriculum/sources`, payload);
      setSources((prev) => [...prev, r.data]);
      setForm((prev) => ({ ...prev, source_ids: [...prev.source_ids, r.data.id] }));
      setSourceForm({ title: '', source_type: 'DCM', scope: 'tenant', description: '' });
      setSourceFormOpen(false);
      toast.success('Fonte curricular registrada.');
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Falha ao registrar fonte curricular.');
    }
  };

  const uploadVersion = async () => {
    if (!form.file) return toast.info('Selecione o PDF da Versão Curricular Estruturada.');
    if (!form.component_id) return toast.info('Selecione o componente curricular.');
    if (!form.source_ids.length) return toast.info('Selecione pelo menos uma fonte curricular oficial.');
    setUploading(true);
    try {
      const data = new FormData();
      data.append('file', form.file);
      data.append('academic_year', String(form.academic_year));
      data.append('component_id', form.component_id);
      data.append('grade', String(form.grade));
      data.append('bimestre', String(form.bimestre));
      data.append('source_ids', form.source_ids.join(','));
      if (form.name.trim()) data.append('name', form.name.trim());
      if (form.notes.trim()) data.append('notes', form.notes.trim());
      const r = await axios.post(`${API}/api/curriculum/import/scoped-versions/upload`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success('Versão curricular extraída em rascunho para revisão.');
      setSelectedVersion(r.data);
      setPlan(null);
      setForm((prev) => ({ ...prev, file: null, name: '', notes: '' }));
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(detail?.message || (typeof detail === 'string' ? detail : 'Falha ao processar a Versão Curricular.'));
    } finally {
      setUploading(false);
    }
  };

  const refreshResolution = async () => {
    if (!selectedVersion) return;
    try {
      const r = await axios.post(`${API}/api/curriculum/import/scoped-versions/${selectedVersion.id}/refresh-skill-resolution`);
      setSelectedVersion(r.data);
      toast.success('Vínculos de habilidades atualizados.');
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || 'Falha ao atualizar habilidades.');
    }
  };

  const publishVersion = async () => {
    if (!selectedVersion) return;
    if (unresolved.length) return toast.info('Resolva as habilidades DCM obrigatórias antes de publicar.');
    if (!window.confirm(`Publicar a versão “${versionScopeLabel(selectedVersion)}”?`)) return;
    try {
      const r = await axios.post(`${API}/api/curriculum/import/scoped-versions/${selectedVersion.id}/publish`);
      setSelectedVersion(r.data);
      toast.success('Versão Curricular publicada.');
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || 'Falha ao publicar a versão.');
    }
  };

  const createPlan = async () => {
    if (!selectedVersion) return;
    try {
      const r = await axios.post(`${API}/api/curriculum/import/scoped-versions/${selectedVersion.id}/create-teaching-plan`);
      setPlan(r.data);
      toast.success('Plano de Ensino Bimestral criado em rascunho.');
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Falha ao criar Plano de Ensino.');
    }
  };

  const publishPlan = async () => {
    if (!plan) return;
    if (!window.confirm('Publicar este Plano de Ensino Bimestral?')) return;
    try {
      const r = await axios.post(`${API}/api/curriculum/teaching-plans/${plan.id}/publish`);
      setPlan(r.data);
      toast.success('Plano de Ensino Bimestral publicado.');
    } catch (error) {
      toast.error(error?.response?.data?.detail?.message || error?.response?.data?.detail || 'Falha ao publicar o Plano de Ensino.');
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-purple-600" /></div>;
  }

  return (
    <div className="space-y-6" data-testid="scoped-curriculum-versions">
      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-start justify-between gap-4 mb-5">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Versões Curriculares</h2>
            <p className="text-sm text-gray-500">Uma versão por componente, ano/série e bimestre, vinculada às fontes oficiais.</p>
          </div>
          <button type="button" onClick={() => setSourceFormOpen((v) => !v)} className="inline-flex items-center gap-1.5 px-3 py-2 border rounded-lg text-sm hover:bg-gray-50">
            <Plus className="h-4 w-4" /> Fonte oficial
          </button>
        </div>

        {sourceFormOpen && (
          <div className="border rounded-lg p-4 bg-gray-50 mb-5 grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="md:col-span-2">
              <label className="text-xs text-gray-600">Título da fonte oficial</label>
              <input value={sourceForm.title} onChange={(e) => setSourceForm((p) => ({ ...p, title: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm" placeholder="Ex.: Documento Curricular do Município de Floresta do Araguaia" />
            </div>
            <div>
              <label className="text-xs text-gray-600">Tipo</label>
              <select value={sourceForm.source_type} onChange={(e) => setSourceForm((p) => ({ ...p, source_type: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm">
                {SOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-600">Escopo</label>
              <select value={sourceForm.scope} onChange={(e) => setSourceForm((p) => ({ ...p, scope: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm">
                <option value="tenant">Rede municipal</option>
                <option value="national">Nacional</option>
              </select>
            </div>
            <div className="md:col-span-4">
              <label className="text-xs text-gray-600">Descrição (opcional)</label>
              <input value={sourceForm.description} onChange={(e) => setSourceForm((p) => ({ ...p, description: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm" />
            </div>
            <div className="md:col-span-4 flex justify-end">
              <button type="button" onClick={createSource} className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm">Registrar fonte</button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div><label className="text-xs text-gray-600">Ano letivo</label><input type="number" value={form.academic_year} onChange={(e) => setForm((p) => ({ ...p, academic_year: Number(e.target.value) }))} className="w-full mt-1 border rounded px-3 py-2 text-sm" /></div>
          <div><label className="text-xs text-gray-600">Ano/série</label><select value={form.grade} onChange={(e) => setForm((p) => ({ ...p, grade: Number(e.target.value) }))} className="w-full mt-1 border rounded px-3 py-2 text-sm">{[1,2,3,4,5,6,7,8,9].map((n) => <option key={n} value={n}>{n}º ano</option>)}</select></div>
          <div><label className="text-xs text-gray-600">Bimestre</label><select value={form.bimestre} onChange={(e) => setForm((p) => ({ ...p, bimestre: Number(e.target.value) }))} className="w-full mt-1 border rounded px-3 py-2 text-sm">{[1,2,3,4].map((n) => <option key={n} value={n}>{n}º bimestre</option>)}</select></div>
          <div><label className="text-xs text-gray-600">Componente curricular</label><select value={form.component_id} onChange={(e) => setForm((p) => ({ ...p, component_id: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm"><option value="">Selecione...</option>{courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
        </div>

        <div className="mt-4">
          <label className="text-xs text-gray-600">Fontes oficiais utilizadas no documento</label>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
            {sources.map((source) => (
              <label key={source.id} className="flex items-start gap-2 border rounded-lg p-2.5 text-sm cursor-pointer hover:bg-gray-50">
                <input type="checkbox" className="mt-1" checked={selectedSourceSet.has(source.id)} onChange={() => toggleSource(source.id)} />
                <span><span className="font-medium">{source.title}</span><span className="block text-xs text-gray-500">{source.source_type} · {source.scope === 'national' ? 'Nacional' : 'Rede'}</span></span>
              </label>
            ))}
            {!sources.length && <p className="text-sm text-amber-700">Nenhuma fonte cadastrada. Registre ao menos uma fonte oficial.</p>}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label className="text-xs text-gray-600">PDF da Versão Curricular Estruturada</label><input type="file" accept="application/pdf" onChange={(e) => setForm((p) => ({ ...p, file: e.target.files?.[0] || null }))} className="w-full mt-1 border rounded px-3 py-2 text-sm" /></div>
          <div><label className="text-xs text-gray-600">Nome da versão (opcional)</label><input value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm" placeholder="Gerado automaticamente se vazio" /></div>
        </div>
        <div className="mt-3"><label className="text-xs text-gray-600">Notas (opcional)</label><textarea value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} className="w-full mt-1 border rounded px-3 py-2 text-sm min-h-20" /></div>
        <div className="mt-4 flex justify-end">
          <button type="button" onClick={uploadVersion} disabled={uploading} className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}{uploading ? 'Analisando PDF...' : 'Enviar e analisar versão'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-5">
        <div className="bg-white border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3"><h3 className="font-semibold">Versões cadastradas</h3><button type="button" onClick={loadAll} className="p-1.5 hover:bg-gray-100 rounded"><RefreshCw className="h-4 w-4" /></button></div>
          <div className="space-y-2 max-h-[620px] overflow-auto">
            {versions.map((version) => (
              <button key={version.id} type="button" onClick={() => selectVersion(version)} className={`w-full text-left border rounded-lg p-3 hover:border-purple-300 ${selectedVersion?.id === version.id ? 'border-purple-500 ring-1 ring-purple-200' : ''}`}>
                <div className="flex items-start justify-between gap-2"><span className="font-medium text-sm">{versionScopeLabel(version)}</span><StatusBadge status={version.status} /></div>
                <div className="mt-2 text-xs text-gray-500">Rev. {version.revision} · obrigatórias {version.summary?.mandatory_resolved || 0}/{version.summary?.mandatory_skills || 0}</div>
              </button>
            ))}
            {!versions.length && <p className="text-sm text-gray-500 py-4 text-center">Nenhuma versão escopada para {form.academic_year}.</p>}
          </div>
        </div>

        <div className="bg-white border rounded-xl p-5 min-h-[420px]">
          {!selectedVersion ? (
            <div className="h-full flex flex-col items-center justify-center text-gray-500 py-16"><FileText className="h-10 w-10 mb-3 text-gray-300" /><p>Selecione ou envie uma versão para revisar.</p></div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><div className="flex items-center gap-2"><h3 className="text-lg font-bold">{selectedVersion.name}</h3><StatusBadge status={selectedVersion.status} /></div><p className="text-sm text-gray-500 mt-1">{versionScopeLabel(selectedVersion)} · revisão {selectedVersion.revision}</p></div>
                <div className="flex gap-2 flex-wrap">
                  <button type="button" onClick={refreshResolution} className="inline-flex items-center gap-1.5 border px-3 py-2 rounded-lg text-sm"><RefreshCw className="h-4 w-4" /> Resolver habilidades</button>
                  {selectedVersion.status === 'draft' && <button type="button" onClick={publishVersion} disabled={unresolved.length > 0} className="inline-flex items-center gap-1.5 bg-emerald-600 text-white px-3 py-2 rounded-lg text-sm disabled:bg-gray-300"><CheckCircle2 className="h-4 w-4" /> Publicar versão</button>}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
                <div className="border rounded-lg p-3"><div className="text-xl font-bold">{selectedVersion.summary?.mandatory_skills || 0}</div><div className="text-xs text-gray-500">Obrigatórias</div></div>
                <div className="border rounded-lg p-3"><div className="text-xl font-bold text-emerald-600">{selectedVersion.summary?.mandatory_resolved || 0}</div><div className="text-xs text-gray-500">Resolvidas</div></div>
                <div className="border rounded-lg p-3"><div className="text-xl font-bold text-red-600">{selectedVersion.summary?.mandatory_unresolved || 0}</div><div className="text-xs text-gray-500">Pendentes</div></div>
                <div className="border rounded-lg p-3"><div className="text-xl font-bold">{selectedVersion.summary?.complementary_skills || 0}</div><div className="text-xs text-gray-500">Complementares</div></div>
                <div className="border rounded-lg p-3"><div className="text-xl font-bold">{selectedVersion.summary?.transversal_skills || 0}</div><div className="text-xs text-gray-500">Transversais</div></div>
              </div>

              {!!unresolved.length && (
                <div className="border border-amber-300 bg-amber-50 rounded-lg p-4 flex items-start gap-3"><AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" /><div><p className="font-semibold text-amber-800">Habilidades obrigatórias ainda não resolvidas</p><p className="text-sm text-amber-700 mt-1">{unresolved.map((item) => item.code).join(', ')}</p>{onOpenSkillImport && <button type="button" onClick={onOpenSkillImport} className="mt-2 text-sm underline font-medium text-amber-800">Abrir importador de habilidades</button>}</div></div>
              )}

              {selectedVersion.document_url && <a href={selectedVersion.document_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm text-purple-700 underline"><FileText className="h-4 w-4" /> Abrir PDF original · SHA-256 {String(selectedVersion.document_sha256 || '').slice(0, 12)}…</a>}

              <SkillList title="Habilidades DCM obrigatórias" items={selectedVersion.structured_payload?.mandatory_skills || []} />
              <SkillList title="Habilidades BNCC complementares" items={selectedVersion.structured_payload?.complementary_skills || []} tone="green" />
              <SkillList title="Integrações transversais" items={selectedVersion.structured_payload?.transversal_skills || []} tone="violet" />
              <SkillList title="Objetos de Conhecimento por prática/eixo" items={selectedVersion.structured_payload?.knowledge_object_groups || []} />

              <div className="border-t pt-5">
                <div className="flex items-center justify-between gap-3 flex-wrap"><div><h4 className="font-semibold">Plano de Ensino Bimestral</h4><p className="text-sm text-gray-500">Criado somente a partir das habilidades DCM obrigatórias desta versão.</p></div>{selectedVersion.status === 'published' && !plan && <button type="button" onClick={createPlan} className="inline-flex items-center gap-1.5 bg-gray-900 text-white px-3 py-2 rounded-lg text-sm"><BookOpen className="h-4 w-4" /> Criar Plano de Ensino</button>}</div>
                {plan && <div className="mt-3 border rounded-lg p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{plan.title}</p><p className="text-xs text-gray-500 mt-1">{(plan.items || []).length} itens · {plan.status === 'published' ? 'publicado' : 'rascunho'}</p></div>{plan.status === 'draft' && <button type="button" onClick={publishPlan} className="bg-emerald-600 text-white px-3 py-2 rounded-lg text-sm">Publicar Plano</button>}</div><div className="mt-3 space-y-2">{(plan.items || []).map((item) => <div key={item.id} className="text-sm border-t first:border-t-0 pt-2 first:pt-0"><span className="font-mono font-semibold">{item.skill_code_snapshot}</span><span className="ml-2">{item.learning_objective || item.skill_description_snapshot}</span>{!!item.knowledge_objects?.length && <div className="text-xs text-gray-500 mt-1">Objeto(s): {item.knowledge_objects.map((o) => o.label).join(' · ')}</div>}</div>)}</div></div>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
