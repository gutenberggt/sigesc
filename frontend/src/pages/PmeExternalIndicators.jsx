import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { pmeAnosFinaisAPI } from '@/services/api';
import {
  Home, Save, Loader2, Plus, Trash2, ClipboardList, BarChart3,
} from 'lucide-react';

const YEARS = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i);

const numOrNull = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));

const Field = ({ label, children, hint }) => (
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
    {children}
    {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
  </div>
);

const Section = ({ icon: Icon, title, children }) => (
  <Card>
    <CardContent className="p-6 space-y-4">
      <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
        {Icon && <Icon size={18} className="text-indigo-600" />}{title}
      </h2>
      {children}
    </CardContent>
  </Card>
);

const inputCls = "w-full px-3 py-2 border rounded-lg";

export default function PmeExternalIndicators() {
  const navigate = useNavigate();
  const [year, setYear] = useState(new Date().getFullYear());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = useCallback(async (yr) => {
    setLoading(true);
    try {
      const data = await pmeAnosFinaisAPI.getExternal(yr);
      setForm({
        evolucao: [], bncc_descritores: [],
        ...data,
        academic_year: yr,
      });
    } catch (e) {
      toast.error('Falha ao carregar indicadores.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(year); }, [year, load]);

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        academic_year: year,
        ideb_atual: numOrNull(form.ideb_atual),
        ideb_meta: numOrNull(form.ideb_meta),
        saeb_lp_9: numOrNull(form.saeb_lp_9),
        saeb_mat_9: numOrNull(form.saeb_mat_9),
        evolucao: (form.evolucao || []).map((e) => ({
          year: parseInt(e.year, 10) || null, ideb: numOrNull(e.ideb), lp: numOrNull(e.lp), mat: numOrNull(e.mat),
        })),
        pop_11_14_pct: numOrNull(form.pop_11_14_pct),
        pop_16_pct: numOrNull(form.pop_16_pct),
        bncc_descritores: (form.bncc_descritores || []).map((d) => ({
          descritor: d.descritor || '', nivel_defasagem_pct: numOrNull(d.nivel_defasagem_pct),
        })),
        escolas_total: numOrNull(form.escolas_total),
        escolas_lab_informatica: numOrNull(form.escolas_lab_informatica),
        escolas_lab_ciencias: numOrNull(form.escolas_lab_ciencias),
        escolas_biblioteca: numOrNull(form.escolas_biblioteca),
        escolas_internet: numOrNull(form.escolas_internet),
        infraestrutura_obs: form.infraestrutura_obs || null,
        transporte_cobertura_pct: numOrNull(form.transporte_cobertura_pct),
        transporte_impacto_evasao: form.transporte_impacto_evasao || null,
        formacao_continuada_ativa: form.formacao_continuada_ativa ?? null,
        formacao_continuada_obs: form.formacao_continuada_obs || null,
        plano_carreira_atualizado: form.plano_carreira_atualizado ?? null,
        plano_carreira_obs: form.plano_carreira_obs || null,
        observacoes_gerais: form.observacoes_gerais || null,
      };
      await pmeAnosFinaisAPI.saveExternal(payload);
      toast.success(`Indicadores de ${year} salvos.`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Falha ao salvar.');
    } finally {
      setSaving(false);
    }
  };

  const addRow = (key, row) => set(key, [...(form[key] || []), row]);
  const updRow = (key, i, patch) => set(key, (form[key] || []).map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const delRow = (key, i) => set(key, (form[key] || []).filter((_, idx) => idx !== i));

  return (
    <Layout>
      <div className="space-y-6 max-w-5xl" data-testid="pme-external-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-gray-500 hover:text-indigo-600" data-testid="pme-ext-home">
              <Home size={20} /><span>Início</span>
            </button>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <ClipboardList className="text-indigo-600" /> Indicadores Externos (PME) — Anos Finais
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => navigate('/pme/anos-finais')} data-testid="pme-ext-go-dashboard">
              <BarChart3 size={16} className="mr-2" /> Ver Painel
            </Button>
            <select value={year} onChange={(e) => setYear(parseInt(e.target.value, 10))} className="px-3 py-2 border rounded-lg bg-white" data-testid="pme-ext-year">
              {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <Button onClick={save} disabled={saving || loading} className="bg-indigo-600 hover:bg-indigo-700" data-testid="pme-ext-save">
              {saving ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Save size={16} className="mr-2" />} Salvar
            </Button>
          </div>
        </div>

        <p className="text-sm text-gray-500">
          Informe aqui os dados que o SIGESC não possui (IDEB/SAEB, IBGE, infraestrutura, transporte e políticas).
          Eles aparecem automaticamente no Painel dos Anos Finais.
        </p>

        {loading ? (
          <div className="flex items-center gap-2 text-gray-500"><Loader2 className="animate-spin" size={18} /> Carregando…</div>
        ) : (
          <>
            <Section icon={BarChart3} title="IDEB / SAEB — 9º ano">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Field label="IDEB atual"><input type="number" step="0.1" className={inputCls} value={form.ideb_atual ?? ''} onChange={(e) => set('ideb_atual', e.target.value)} data-testid="pme-ideb-atual" /></Field>
                <Field label="IDEB meta projetada"><input type="number" step="0.1" className={inputCls} value={form.ideb_meta ?? ''} onChange={(e) => set('ideb_meta', e.target.value)} data-testid="pme-ideb-meta" /></Field>
                <Field label="SAEB Língua Portuguesa (9º)"><input type="number" step="0.1" className={inputCls} value={form.saeb_lp_9 ?? ''} onChange={(e) => set('saeb_lp_9', e.target.value)} /></Field>
                <Field label="SAEB Matemática (9º)"><input type="number" step="0.1" className={inputCls} value={form.saeb_mat_9 ?? ''} onChange={(e) => set('saeb_mat_9', e.target.value)} /></Field>
              </div>

              <div className="pt-2">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-gray-700">Evolução histórica</p>
                  <Button size="sm" variant="outline" onClick={() => addRow('evolucao', { year: '', ideb: '', lp: '', mat: '' })} data-testid="pme-add-evolucao"><Plus size={14} className="mr-1" /> Linha</Button>
                </div>
                {(form.evolucao || []).map((row, i) => (
                  <div key={i} className="grid grid-cols-5 gap-2 mb-2 items-center">
                    <input type="number" placeholder="Ano" className={inputCls} value={row.year ?? ''} onChange={(e) => updRow('evolucao', i, { year: e.target.value })} />
                    <input type="number" step="0.1" placeholder="IDEB" className={inputCls} value={row.ideb ?? ''} onChange={(e) => updRow('evolucao', i, { ideb: e.target.value })} />
                    <input type="number" step="0.1" placeholder="LP" className={inputCls} value={row.lp ?? ''} onChange={(e) => updRow('evolucao', i, { lp: e.target.value })} />
                    <input type="number" step="0.1" placeholder="Mat" className={inputCls} value={row.mat ?? ''} onChange={(e) => updRow('evolucao', i, { mat: e.target.value })} />
                    <Button size="icon" variant="ghost" onClick={() => delRow('evolucao', i)}><Trash2 size={16} className="text-red-500" /></Button>
                  </div>
                ))}
              </div>
            </Section>

            <Section icon={ClipboardList} title="Atendimento Populacional (IBGE)">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="% população 11–14 anos na escola"><input type="number" step="0.1" className={inputCls} value={form.pop_11_14_pct ?? ''} onChange={(e) => set('pop_11_14_pct', e.target.value)} data-testid="pme-pop-11-14" /></Field>
                <Field label="% população 16 anos na escola"><input type="number" step="0.1" className={inputCls} value={form.pop_16_pct ?? ''} onChange={(e) => set('pop_16_pct', e.target.value)} /></Field>
              </div>
            </Section>

            <Section icon={BarChart3} title="Defasagem por Descritores BNCC / SAEB">
              <div className="flex justify-end mb-2">
                <Button size="sm" variant="outline" onClick={() => addRow('bncc_descritores', { descritor: '', nivel_defasagem_pct: '' })} data-testid="pme-add-bncc"><Plus size={14} className="mr-1" /> Descritor</Button>
              </div>
              {(form.bncc_descritores || []).map((row, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 mb-2 items-center">
                  <input placeholder="Descritor (ex.: D12 - LP)" className={`${inputCls} col-span-7`} value={row.descritor ?? ''} onChange={(e) => updRow('bncc_descritores', i, { descritor: e.target.value })} />
                  <input type="number" step="0.1" placeholder="% defasagem" className={`${inputCls} col-span-4`} value={row.nivel_defasagem_pct ?? ''} onChange={(e) => updRow('bncc_descritores', i, { nivel_defasagem_pct: e.target.value })} />
                  <Button size="icon" variant="ghost" onClick={() => delRow('bncc_descritores', i)}><Trash2 size={16} className="text-red-500" /></Button>
                </div>
              ))}
            </Section>

            <Section icon={ClipboardList} title="Infraestrutura e Recursos">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <Field label="Total de escolas"><input type="number" className={inputCls} value={form.escolas_total ?? ''} onChange={(e) => set('escolas_total', e.target.value)} /></Field>
                <Field label="Lab. Informática"><input type="number" className={inputCls} value={form.escolas_lab_informatica ?? ''} onChange={(e) => set('escolas_lab_informatica', e.target.value)} /></Field>
                <Field label="Lab. Ciências"><input type="number" className={inputCls} value={form.escolas_lab_ciencias ?? ''} onChange={(e) => set('escolas_lab_ciencias', e.target.value)} /></Field>
                <Field label="Biblioteca"><input type="number" className={inputCls} value={form.escolas_biblioteca ?? ''} onChange={(e) => set('escolas_biblioteca', e.target.value)} /></Field>
                <Field label="Internet/Recursos digitais"><input type="number" className={inputCls} value={form.escolas_internet ?? ''} onChange={(e) => set('escolas_internet', e.target.value)} /></Field>
              </div>
              <Field label="Observações de infraestrutura"><textarea rows={2} className={inputCls} value={form.infraestrutura_obs ?? ''} onChange={(e) => set('infraestrutura_obs', e.target.value)} /></Field>
            </Section>

            <Section icon={ClipboardList} title="Transporte Escolar">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="% cobertura do transporte"><input type="number" step="0.1" className={inputCls} value={form.transporte_cobertura_pct ?? ''} onChange={(e) => set('transporte_cobertura_pct', e.target.value)} /></Field>
                <Field label="Impacto na evasão/faltas"><input className={inputCls} value={form.transporte_impacto_evasao ?? ''} onChange={(e) => set('transporte_impacto_evasao', e.target.value)} placeholder="Ex.: faltas por falta de transporte na zona rural" /></Field>
              </div>
            </Section>

            <Section icon={ClipboardList} title="Políticas Docentes">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="Política ativa de formação continuada?">
                  <select className={inputCls} value={form.formacao_continuada_ativa === true ? 'sim' : form.formacao_continuada_ativa === false ? 'nao' : ''} onChange={(e) => set('formacao_continuada_ativa', e.target.value === '' ? null : e.target.value === 'sim')}>
                    <option value="">—</option><option value="sim">Sim</option><option value="nao">Não</option>
                  </select>
                </Field>
                <Field label="Plano de carreira atualizado e implementado?">
                  <select className={inputCls} value={form.plano_carreira_atualizado === true ? 'sim' : form.plano_carreira_atualizado === false ? 'nao' : ''} onChange={(e) => set('plano_carreira_atualizado', e.target.value === '' ? null : e.target.value === 'sim')}>
                    <option value="">—</option><option value="sim">Sim</option><option value="nao">Não</option>
                  </select>
                </Field>
                <Field label="Obs. formação continuada"><textarea rows={2} className={inputCls} value={form.formacao_continuada_obs ?? ''} onChange={(e) => set('formacao_continuada_obs', e.target.value)} /></Field>
                <Field label="Obs. plano de carreira"><textarea rows={2} className={inputCls} value={form.plano_carreira_obs ?? ''} onChange={(e) => set('plano_carreira_obs', e.target.value)} /></Field>
              </div>
            </Section>

            <Section icon={ClipboardList} title="Observações Gerais">
              <textarea rows={3} className={inputCls} value={form.observacoes_gerais ?? ''} onChange={(e) => set('observacoes_gerais', e.target.value)} data-testid="pme-obs-gerais" />
            </Section>

            <div className="flex justify-end pb-8">
              <Button onClick={save} disabled={saving} className="bg-indigo-600 hover:bg-indigo-700" data-testid="pme-ext-save-bottom">
                {saving ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Save size={16} className="mr-2" />} Salvar indicadores de {year}
              </Button>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
