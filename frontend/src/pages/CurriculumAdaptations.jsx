/**
 * CRUD de Adaptações Curriculares v2 — /admin/curriculo/adaptacoes
 *
 * Gestor ajusta a base curricular (ano/bimestre/descrição local) sem depender
 * de importação. Visualiza origem (BNCC / DCM / MUNICIPAL) para não quebrar
 * o vínculo normalizado.
 */
import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Search, Plus, Edit, Trash2, FileUp, ChevronLeft, Loader2, X,
  AlertCircle, Filter,
} from 'lucide-react';
import { curriculumAPI } from '@/services/api';

const FONTE_STYLE = {
  BNCC_COMPUTACAO: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  DCM_FA: 'bg-amber-50 text-amber-700 border-amber-200',
  MUNICIPAL: 'bg-violet-50 text-violet-700 border-violet-200',
};

const PAGE_SIZE = 30;

export default function CurriculumAdaptations() {
  const [filters, setFilters] = useState({
    componente_codigo: '', ano: '', bimestre: '', q: '',
  });
  const [components, setComponents] = useState([]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);      // item sendo editado
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);

  /* Carrega componentes para o dropdown */
  useEffect(() => {
    curriculumAPI.components().then(d => setComponents(d || [])).catch(() => setComponents([]));
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset: page * PAGE_SIZE };
      if (filters.componente_codigo) params.componente_codigo = filters.componente_codigo;
      if (filters.ano) params.ano = Number(filters.ano);
      if (filters.bimestre) params.bimestre = Number(filters.bimestre);
      if (filters.q) params.q = filters.q;
      const r = await curriculumAPI.adaptations(params);
      setItems(r.items || []);
      setTotal(r.total || 0);
    } catch {
      toast.error('Falha ao carregar adaptações');
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { loadItems(); }, [loadItems]);

  const openNew = () => {
    setEditing(null);
    setFormData({
      component_id: '',
      codigo_local: '',
      descricao_local: '',
      eixo_local: '',
      objeto_conhecimento: '',
      ano: '',
      bimestre: '',
      ordem_sequencia: 0,
      fonte: 'MUNICIPAL',
    });
    setShowForm(true);
  };

  const openEdit = async (row) => {
    try {
      const d = await curriculumAPI.adaptationById(row.adaptation_id);
      const a = d.adaptation;
      setEditing({ ...row, ...a });
      setFormData({
        component_id: a.component_id || '',
        codigo_local: a.codigo_local || '',
        descricao_local: a.descricao_local || '',
        eixo_local: a.eixo_local || '',
        objeto_conhecimento: a.objeto_conhecimento || '',
        ano: a.ano ?? '',
        bimestre: a.bimestre ?? '',
        ordem_sequencia: a.ordem_sequencia ?? 0,
        fonte: a.fonte || 'MUNICIPAL',
      });
      setShowForm(true);
    } catch {
      toast.error('Falha ao carregar detalhes');
    }
  };

  const save = async () => {
    if (!formData.component_id) return toast.error('Selecione o componente');
    if (!formData.ano && formData.ano !== 0) return toast.error('Ano é obrigatório');
    setSaving(true);
    try {
      const payload = {
        ...formData,
        ano: Number(formData.ano),
        bimestre: formData.bimestre === '' || formData.bimestre === null
          ? null : Number(formData.bimestre),
        ordem_sequencia: Number(formData.ordem_sequencia || 0),
      };
      // Descarta vazios para evitar gravar string em bncc_skill_id etc
      Object.keys(payload).forEach(k => {
        if (payload[k] === '') payload[k] = null;
      });
      if (editing) {
        await curriculumAPI.updateAdaptation(editing.adaptation_id, payload);
        toast.success('Adaptação atualizada');
      } else {
        await curriculumAPI.createAdaptation(payload);
        toast.success('Adaptação criada');
      }
      setShowForm(false);
      loadItems();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Excluir adaptação ${row.codigo}? Se estiver vinculada a aulas será apenas desativada.`)) return;
    try {
      const r = await curriculumAPI.deleteAdaptation(row.adaptation_id);
      toast.success(r.soft_deleted ? 'Desativada (estava em uso)' : 'Excluída');
      loadItems();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao excluir');
    }
  };

  const runMigration = async () => {
    try {
      toast.info('Rodando migração v2...');
      const r = await curriculumAPI.runMigration();
      toast.success(
        `Migração OK — BNCC: +${r.bncc_inserted} / Adapt: +${r.adapt_inserted} / LO: ${r.migrated}`,
        { duration: 8000 }
      );
      loadItems();
    } catch (e) {
      toast.error('Falha na migração');
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="curriculum-adaptations-page">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-2">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Adaptações Curriculares (v2)</h1>
          <p className="text-sm text-gray-500">
            Base editável do currículo municipal. Vínculo normalizado com a BNCC canônica.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/admin/curriculo/importar"
            className="inline-flex items-center gap-2 px-3 py-2 bg-amber-50 text-amber-700 border border-amber-200 rounded-lg text-sm hover:bg-amber-100"
            data-testid="btn-import-pdf"
          >
            <FileUp className="h-4 w-4" /> Importar PDF
          </Link>
          <button
            onClick={runMigration}
            className="inline-flex items-center gap-2 px-3 py-2 bg-gray-50 text-gray-700 border border-gray-200 rounded-lg text-sm hover:bg-gray-100"
            data-testid="btn-run-migration"
          >
            Sincronizar BNCC
          </button>
          <button
            onClick={openNew}
            className="inline-flex items-center gap-2 px-3 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700"
            data-testid="btn-new-adaptation"
          >
            <Plus className="h-4 w-4" /> Nova adaptação
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 flex flex-wrap gap-3 items-end" data-testid="curr-filters">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Filter className="h-4 w-4" /> FILTRAR
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Componente</label>
          <select
            className="border border-gray-300 rounded px-2 py-1 text-sm"
            value={filters.componente_codigo}
            onChange={e => { setPage(0); setFilters(f => ({ ...f, componente_codigo: e.target.value })); }}
            data-testid="filter-componente"
          >
            <option value="">— Todos —</option>
            {Array.from(new Set(components.map(c => c.codigo))).sort().map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Ano</label>
          <select
            className="border border-gray-300 rounded px-2 py-1 text-sm w-20"
            value={filters.ano}
            onChange={e => { setPage(0); setFilters(f => ({ ...f, ano: e.target.value })); }}
            data-testid="filter-ano"
          >
            <option value="">—</option>
            {[1,2,3,4,5,6,7,8,9].map(a => <option key={a} value={a}>{a}º</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Bimestre</label>
          <select
            className="border border-gray-300 rounded px-2 py-1 text-sm w-20"
            value={filters.bimestre}
            onChange={e => { setPage(0); setFilters(f => ({ ...f, bimestre: e.target.value })); }}
            data-testid="filter-bimestre"
          >
            <option value="">—</option>
            {[1,2,3,4].map(b => <option key={b} value={b}>{b}º</option>)}
          </select>
        </div>
        <div className="flex-1 min-w-[220px]">
          <label className="block text-xs text-gray-500 mb-1">Busca (código ou descrição)</label>
          <div className="relative">
            <Search className="absolute left-2 top-2 h-4 w-4 text-gray-400" />
            <input
              className="pl-8 pr-2 py-1 border border-gray-300 rounded text-sm w-full"
              placeholder="Ex.: EF03LP02 ou 'fração'"
              value={filters.q}
              onChange={e => { setPage(0); setFilters(f => ({ ...f, q: e.target.value })); }}
              data-testid="filter-q"
            />
          </div>
        </div>
        <div className="text-xs text-gray-500 self-center ml-auto">
          <span className="font-semibold text-gray-800">{total}</span> resultados
        </div>
      </div>

      {/* Tabela */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-x-auto" data-testid="curr-table">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2 w-2/5">Descrição</th>
              <th className="px-3 py-2">Comp.</th>
              <th className="px-3 py-2">Ano</th>
              <th className="px-3 py-2">Bim.</th>
              <th className="px-3 py-2">Origem</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan="7" className="px-3 py-6 text-center text-gray-400">
                <Loader2 className="h-5 w-5 animate-spin inline-block" /> Carregando...
              </td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan="7" className="px-3 py-6 text-center text-gray-400">
                Nenhuma adaptação encontrada com esses filtros.
              </td></tr>
            )}
            {!loading && items.map(it => {
              const fonteClass = FONTE_STYLE[it.fonte] || FONTE_STYLE.MUNICIPAL;
              return (
                <tr key={it.adaptation_id} className="border-t border-gray-100 hover:bg-gray-50" data-testid={`row-${it.codigo}`}>
                  <td className="px-3 py-2 font-mono text-xs font-semibold text-purple-700">{it.codigo}</td>
                  <td className="px-3 py-2 text-gray-800">
                    <div className="line-clamp-2">{it.descricao}</div>
                    {it.has_bncc && it.codigo !== it.codigo_bncc && it.codigo_local && (
                      <div className="text-[10px] text-gray-400">Ref BNCC: {it.codigo_bncc}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600">{it.componente_codigo || '—'}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{it.ano != null ? `${it.ano}º` : '—'}</td>
                  <td className="px-3 py-2 text-xs text-gray-600">{it.bimestre != null ? `${it.bimestre}º` : '—'}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] px-1 rounded border ${fonteClass}`}>{it.fonte}</span>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      onClick={() => openEdit(it)}
                      className="text-gray-500 hover:text-purple-700 mr-2"
                      title="Editar"
                      data-testid={`edit-${it.codigo}`}
                    ><Edit className="h-4 w-4 inline" /></button>
                    <button
                      onClick={() => remove(it)}
                      className="text-gray-500 hover:text-red-600"
                      title="Excluir"
                      data-testid={`delete-${it.codigo}`}
                    ><Trash2 className="h-4 w-4 inline" /></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Paginação */}
      {total > PAGE_SIZE && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <div className="text-gray-500">Página {page + 1} de {totalPages}</div>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-40"
              data-testid="page-prev"
            >‹ Anterior</button>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-40"
              data-testid="page-next"
            >Próximo ›</button>
          </div>
        </div>
      )}

      {/* Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto" data-testid="adaptation-modal">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold text-lg">
                {editing ? `Editar ${editing.codigo || ''}` : 'Nova adaptação'}
              </h3>
              <button onClick={() => setShowForm(false)} className="text-gray-500 hover:text-gray-800">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              {editing?.codigo_bncc && (
                <div className="flex items-center gap-2 text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-1 rounded">
                  <AlertCircle className="h-3 w-3" /> Vinculada a BNCC canônica: <span className="font-mono font-semibold">{editing.codigo_bncc}</span>
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-600 mb-1">Componente *</label>
                <select
                  className="w-full border rounded px-2 py-1 text-sm"
                  value={formData.component_id}
                  onChange={e => setFormData(f => ({ ...f, component_id: e.target.value }))}
                  data-testid="form-component"
                >
                  <option value="">— Selecione —</option>
                  {components.map(c => (
                    <option key={c.id} value={c.id}>
                      {c.codigo} — {c.nome} ({c.etapa})
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Ano *</label>
                  <input type="number" className="w-full border rounded px-2 py-1 text-sm"
                    value={formData.ano}
                    onChange={e => setFormData(f => ({ ...f, ano: e.target.value }))}
                    data-testid="form-ano" />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Bimestre</label>
                  <select className="w-full border rounded px-2 py-1 text-sm"
                    value={formData.bimestre ?? ''}
                    onChange={e => setFormData(f => ({ ...f, bimestre: e.target.value }))}
                    data-testid="form-bimestre">
                    <option value="">—</option>
                    {[1,2,3,4].map(b => <option key={b} value={b}>{b}º</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Ordem</label>
                  <input type="number" className="w-full border rounded px-2 py-1 text-sm"
                    value={formData.ordem_sequencia}
                    onChange={e => setFormData(f => ({ ...f, ordem_sequencia: e.target.value }))} />
                </div>
              </div>
              {!editing?.has_bncc && !editing && (
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Código local (preenchido quando não há BNCC correspondente)
                  </label>
                  <input className="w-full border rounded px-2 py-1 text-sm font-mono"
                    placeholder="Ex.: DCM_EA_03_01"
                    value={formData.codigo_local}
                    onChange={e => setFormData(f => ({ ...f, codigo_local: e.target.value }))}
                    data-testid="form-codigo-local" />
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-600 mb-1">
                  Descrição local {editing?.has_bncc && <span className="text-[10px] text-gray-400">(sobrescreve BNCC quando preenchida)</span>}
                </label>
                <textarea className="w-full border rounded px-2 py-1 text-sm min-h-[80px]"
                  placeholder={editing?.descricao_bncc ? `BNCC: ${editing.descricao_bncc}` : 'Descrição da habilidade'}
                  value={formData.descricao_local}
                  onChange={e => setFormData(f => ({ ...f, descricao_local: e.target.value }))}
                  data-testid="form-descricao-local" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Eixo local</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    value={formData.eixo_local}
                    onChange={e => setFormData(f => ({ ...f, eixo_local: e.target.value }))} />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Objeto de conhecimento</label>
                  <input className="w-full border rounded px-2 py-1 text-sm"
                    value={formData.objeto_conhecimento}
                    onChange={e => setFormData(f => ({ ...f, objeto_conhecimento: e.target.value }))} />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-600 mb-1">Origem</label>
                <select className="border rounded px-2 py-1 text-sm"
                  value={formData.fonte}
                  onChange={e => setFormData(f => ({ ...f, fonte: e.target.value }))}
                  data-testid="form-fonte">
                  <option value="MUNICIPAL">MUNICIPAL</option>
                  <option value="DCM_FA">DCM_FA</option>
                  <option value="BNCC_COMPUTACAO">BNCC_COMPUTACAO</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 p-4 border-t bg-gray-50">
              <button
                onClick={() => setShowForm(false)}
                className="px-3 py-1 border border-gray-300 rounded text-sm"
                data-testid="form-cancel"
              >Cancelar</button>
              <button
                onClick={save}
                disabled={saving}
                className="px-3 py-1 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50"
                data-testid="form-save"
              >
                {saving ? 'Salvando...' : (editing ? 'Salvar alterações' : 'Criar')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
