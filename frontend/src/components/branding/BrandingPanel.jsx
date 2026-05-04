/**
 * BrandingPanel — Live Preview de Branding (Sprint G4 — Mai/2026).
 *
 * Para super_admin selecionar uma mantenedora e configurar:
 *   - Nome exibido / slogan
 *   - URL do logotipo
 *   - Cor primária / secundária
 *
 * Live Preview: ao alterar cores, aplica `--brand-primary` e
 * `--brand-secondary` em `document.documentElement` em tempo real.
 * Em "Cancelar" ou unmount, restaura as CSS vars do branding atual.
 *
 * Submit: PUT /api/tenant/branding com `X-Mantenedora-Id` (override
 * para super_admin escolher tenant alvo). Após sucesso, recarrega o
 * BrandingContext e dispara `tenant-changed` para sincronizar Layouts.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Save, RotateCcw, Palette, Upload, Eye, ImageOff } from 'lucide-react';
import { useBranding } from '@/contexts/BrandingContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;

/** Mistura cor com branco para gerar variante "soft" (consistente com BrandingContext) */
function softColor(hex) {
  if (!HEX_RE.test(hex || '')) return null;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const mix = (c) => Math.round(c * 0.12 + 255 * 0.88);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}

function applyVars({ primary, secondary }) {
  const root = document.documentElement;
  if (HEX_RE.test(primary || '')) {
    root.style.setProperty('--brand-primary', primary);
    const soft = softColor(primary);
    if (soft) root.style.setProperty('--brand-primary-soft', soft);
  }
  if (HEX_RE.test(secondary || '')) {
    root.style.setProperty('--brand-secondary', secondary);
  }
}

export default function BrandingPanel() {
  const { branding, refresh } = useBranding();

  const [tenants, setTenants] = useState([]);
  const [tenantId, setTenantId] = useState('');
  const [loadingTenants, setLoadingTenants] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    name: '',
    slogan: '',
    logo_url: '',
    primary_color: '#7c3aed',
    secondary_color: '#a855f7',
  });
  const [original, setOriginal] = useState(null);
  const [logoError, setLogoError] = useState(false);

  // Snapshot das CSS vars atuais (para restaurar em cleanup/cancel)
  const initialVarsRef = useRef(null);
  useEffect(() => {
    const root = document.documentElement;
    initialVarsRef.current = {
      primary: root.style.getPropertyValue('--brand-primary'),
      secondary: root.style.getPropertyValue('--brand-secondary'),
      soft: root.style.getPropertyValue('--brand-primary-soft'),
    };
    return () => {
      // Restaura ao desmontar (caso usuário saia sem salvar)
      const v = initialVarsRef.current;
      if (!v) return;
      const r = document.documentElement;
      if (v.primary) r.style.setProperty('--brand-primary', v.primary);
      if (v.secondary) r.style.setProperty('--brand-secondary', v.secondary);
      if (v.soft) r.style.setProperty('--brand-primary-soft', v.soft);
    };
  }, []);

  // Carrega lista de mantenedoras
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoadingTenants(true);
      try {
        const r = await axios.get(`${API}/mantenedoras`);
        if (!alive) return;
        const list = Array.isArray(r.data) ? r.data : [];
        setTenants(list);
        setTenantId((cur) => cur || (list[0]?.id || ''));
      } catch {
        if (alive) toast.error('Falha ao listar mantenedoras');
      } finally {
        if (alive) setLoadingTenants(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  // Carrega detalhe da mantenedora selecionada
  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    setLoadingDetail(true);
    setLogoError(false);
    try {
      const r = await axios.get(`${API}/mantenedoras/${id}`);
      const m = r.data || {};
      const next = {
        name: m.nome || '',
        slogan: m.slogan || '',
        logo_url: m.logotipo_url || '',
        primary_color: m.cor_primaria || '#7c3aed',
        secondary_color: m.cor_secundaria || '#a855f7',
      };
      setForm(next);
      setOriginal(next);
      // aplica preview com a cor real do tenant alvo
      applyVars({ primary: next.primary_color, secondary: next.secondary_color });
    } catch {
      toast.error('Falha ao carregar branding da mantenedora');
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (tenantId) loadDetail(tenantId);
  }, [tenantId, loadDetail]);

  // Live Preview — aplica vars enquanto edita
  useEffect(() => {
    applyVars({ primary: form.primary_color, secondary: form.secondary_color });
  }, [form.primary_color, form.secondary_color]);

  const dirty = useMemo(() => {
    if (!original) return false;
    return JSON.stringify(form) !== JSON.stringify(original);
  }, [form, original]);

  const handleReset = () => {
    if (!original) return;
    setForm(original);
    applyVars({ primary: original.primary_color, secondary: original.secondary_color });
    toast('Alterações descartadas');
  };

  const handleSave = async () => {
    if (!tenantId) {
      toast.error('Selecione uma mantenedora');
      return;
    }
    if (!HEX_RE.test(form.primary_color)) {
      toast.error('Cor primária inválida (use #RRGGBB)');
      return;
    }
    if (form.secondary_color && !HEX_RE.test(form.secondary_color)) {
      toast.error('Cor secundária inválida (use #RRGGBB)');
      return;
    }

    setSaving(true);
    try {
      await axios.put(
        `${API}/tenant/branding`,
        {
          name: form.name || null,
          slogan: form.slogan || null,
          logo_url: form.logo_url || null,
          primary_color: form.primary_color,
          secondary_color: form.secondary_color,
        },
        { headers: { 'X-Mantenedora-Id': tenantId } },
      );
      toast.success('Branding atualizado!');
      setOriginal(form);
      // Atualiza snapshot que será restaurado no unmount
      initialVarsRef.current = {
        primary: form.primary_color,
        secondary: form.secondary_color,
        soft: softColor(form.primary_color) || '',
      };
      // Recarrega o BrandingContext (se for o tenant ativo, reflete no Layout)
      try { refresh && refresh(); } catch { /* ignore */ }
      window.dispatchEvent(new Event('tenant-changed'));
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" data-testid="branding-panel">
      {/* Form */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 pb-3 border-b border-gray-100">
          <Palette className="h-5 w-5 text-purple-600" />
          <h2 className="font-semibold text-gray-900">Configuração do Branding</h2>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Mantenedora alvo
          </label>
          <select
            className="w-full border border-gray-300 rounded px-2 py-2 text-sm"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            disabled={loadingTenants}
            data-testid="branding-tenant-select"
          >
            {loadingTenants && <option>Carregando...</option>}
            {!loadingTenants && tenants.length === 0 && <option value="">— nenhuma —</option>}
            {tenants.map(t => (
              <option key={t.id} value={t.id}>{t.nome || t.name || t.id}</option>
            ))}
          </select>
        </div>

        <fieldset disabled={!tenantId || loadingDetail} className="space-y-3 disabled:opacity-50">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Nome exibido</label>
            <input
              className="w-full border border-gray-300 rounded px-2 py-2 text-sm"
              placeholder="Secretaria Municipal de Educação"
              value={form.name}
              onChange={e => set('name', e.target.value)}
              data-testid="branding-name-input"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Slogan</label>
            <input
              className="w-full border border-gray-300 rounded px-2 py-2 text-sm"
              placeholder="Educação que transforma"
              value={form.slogan}
              onChange={e => set('slogan', e.target.value)}
              data-testid="branding-slogan-input"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">URL do logotipo</label>
            <div className="flex gap-2">
              <input
                className="flex-1 border border-gray-300 rounded px-2 py-2 text-sm"
                placeholder="https://exemplo.com/logo.png"
                value={form.logo_url}
                onChange={e => { set('logo_url', e.target.value); setLogoError(false); }}
                data-testid="branding-logo-input"
              />
              <Upload className="h-4 w-4 text-gray-400 self-center" title="Cole o link público do logo" />
            </div>
            <p className="text-[11px] text-gray-500 mt-1">
              Recomendado: PNG/SVG transparente, máx 2MB, proporção 4:1 ou 1:1.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Cor primária</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-10 w-12 border border-gray-300 rounded cursor-pointer"
                  value={form.primary_color}
                  onChange={e => set('primary_color', e.target.value)}
                  data-testid="branding-primary-color"
                />
                <input
                  type="text"
                  className="flex-1 border border-gray-300 rounded px-2 py-2 text-sm font-mono"
                  value={form.primary_color}
                  onChange={e => set('primary_color', e.target.value)}
                  maxLength={7}
                  data-testid="branding-primary-hex"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Cor secundária</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-10 w-12 border border-gray-300 rounded cursor-pointer"
                  value={form.secondary_color}
                  onChange={e => set('secondary_color', e.target.value)}
                  data-testid="branding-secondary-color"
                />
                <input
                  type="text"
                  className="flex-1 border border-gray-300 rounded px-2 py-2 text-sm font-mono"
                  value={form.secondary_color}
                  onChange={e => set('secondary_color', e.target.value)}
                  maxLength={7}
                  data-testid="branding-secondary-hex"
                />
              </div>
            </div>
          </div>
        </fieldset>

        <div className="flex justify-end gap-2 pt-3 border-t border-gray-100">
          <button
            onClick={handleReset}
            disabled={!dirty || saving}
            className="px-3 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 inline-flex items-center gap-1 disabled:opacity-50"
            data-testid="branding-reset-btn"
          >
            <RotateCcw className="h-4 w-4" /> Descartar
          </button>
          <button
            onClick={handleSave}
            disabled={!dirty || saving || !tenantId}
            className="px-4 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 inline-flex items-center gap-1 disabled:opacity-50"
            data-testid="branding-save-btn"
          >
            <Save className="h-4 w-4" /> {saving ? 'Salvando...' : 'Salvar branding'}
          </button>
        </div>
      </div>

      {/* Live Preview */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Eye className="h-4 w-4 text-purple-600" />
          <span className="font-medium">Pré-visualização ao vivo</span>
          <span className="text-xs text-gray-400">(reflete em tempo real)</span>
        </div>

        <PreviewCard form={form} logoError={logoError} setLogoError={setLogoError} />

        <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-800">
          <strong>Dica:</strong> as alterações aqui só ficam visíveis para todos
          os usuários do tenant após clicar em <em>Salvar branding</em>. Se você
          sair sem salvar, as cores reais serão restauradas automaticamente.
        </div>
      </div>
    </div>
  );
}

function PreviewCard({ form, logoError, setLogoError }) {
  const primary = HEX_RE.test(form.primary_color) ? form.primary_color : '#7c3aed';
  const secondary = HEX_RE.test(form.secondary_color) ? form.secondary_color : '#a855f7';

  return (
    <div
      className="rounded-xl border border-gray-200 overflow-hidden shadow-sm"
      data-testid="branding-preview-card"
    >
      {/* Header simulado */}
      <div
        className="px-4 py-3 flex items-center gap-3 text-white"
        style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})` }}
      >
        <div className="h-10 w-10 rounded bg-white/15 flex items-center justify-center overflow-hidden border border-white/20">
          {form.logo_url && !logoError ? (
            <img
              src={form.logo_url}
              alt="logo"
              className="h-full w-full object-contain"
              onError={() => setLogoError(true)}
            />
          ) : (
            <ImageOff className="h-5 w-5 opacity-70" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold truncate" data-testid="preview-name">
            {form.name || 'Nome da mantenedora'}
          </div>
          <div className="text-xs opacity-90 truncate" data-testid="preview-slogan">
            {form.slogan || 'Slogan da rede de ensino'}
          </div>
        </div>
      </div>

      {/* Botões/cards exemplo */}
      <div className="p-4 bg-white space-y-3">
        <button
          className="w-full text-left px-3 py-2 rounded text-sm font-medium text-white"
          style={{ background: primary }}
        >
          Botão de ação principal
        </button>

        <div className="grid grid-cols-3 gap-2">
          {['Alunos', 'Turmas', 'Boletim'].map(label => (
            <div
              key={label}
              className="rounded-lg border border-gray-200 p-3 text-center text-xs"
            >
              <div
                className="h-8 w-8 mx-auto rounded-full mb-1"
                style={{ background: `${primary}22` }}
              />
              <div className="font-medium text-gray-700">{label}</div>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          <span
            className="px-2 py-0.5 text-xs rounded-full"
            style={{ background: `${primary}1a`, color: primary }}
          >
            Tag primária
          </span>
          <span
            className="px-2 py-0.5 text-xs rounded-full"
            style={{ background: `${secondary}1a`, color: secondary }}
          >
            Tag secundária
          </span>
        </div>

        <div className="text-xs text-gray-500 border-t border-gray-100 pt-2 mt-2 font-mono">
          primary: {form.primary_color || '—'} · secondary: {form.secondary_color || '—'}
        </div>
      </div>
    </div>
  );
}
