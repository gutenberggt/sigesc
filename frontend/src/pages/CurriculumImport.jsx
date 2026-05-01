/**
 * CurriculumImport — UI do importador de PDF curricular (BNCC/DCM).
 *
 * Fluxo:
 *   1. Upload do PDF (com escolha de componente: LP/MA/TODOS e fonte: DCM_FA/BNCC/MUNICIPAL).
 *   2. Extração automática no backend (pdfplumber + regex).
 *   3. Tabela revisional: filtros (status, busca), edição inline de código/descrição/ano,
 *      aprovar/rejeitar em massa (seleção múltipla).
 *   4. Botão "Importar aprovados" persiste em `curriculum_skills`.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Upload, FileText, Check, X, Edit2, Filter, Search, Loader2, AlertCircle, CheckCheck, Trash2, BookOpen } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_CONFIG = {
  pending:    { label: 'Pendente',   color: 'bg-gray-100 text-gray-700 border-gray-200' },
  approved:   { label: 'Aprovado',   color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  rejected:   { label: 'Rejeitado',  color: 'bg-rose-50 text-rose-700 border-rose-200' },
  imported:   { label: 'Importado',  color: 'bg-blue-50 text-blue-700 border-blue-200' },
  duplicate:  { label: 'Duplicado',  color: 'bg-amber-50 text-amber-700 border-amber-200' },
  edited:     { label: 'Editado',    color: 'bg-violet-50 text-violet-700 border-violet-200' },
};

const COMPONENT_OPTIONS = [
  { value: '', label: 'Todos os componentes' },
  { value: 'LP', label: 'Língua Portuguesa (LP)' },
  { value: 'MA', label: 'Matemática (MA)' },
  { value: 'CI', label: 'Ciências (CI)' },
  { value: 'GE', label: 'Geografia (GE)' },
  { value: 'HI', label: 'História (HI)' },
  { value: 'AR', label: 'Arte (AR)' },
  { value: 'EF', label: 'Educação Física (EF)' },
  { value: 'LI', label: 'Língua Inglesa (LI)' },
  { value: 'ER', label: 'Ensino Religioso (ER)' },
  { value: 'EA', label: 'Estudos Amazônicos (EA)' },
];

export default function CurriculumImport() {
  const [batches, setBatches] = useState([]);
  const [currentBatch, setCurrentBatch] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Upload form
  const [selectedFile, setSelectedFile] = useState(null);
  const [only, setOnly] = useState('LP');
  const [fonte, setFonte] = useState('DCM_FA');
  const fileRef = useRef(null);

  // Review filters
  const [statusFilter, setStatusFilter] = useState('pending');
  const [searchQ, setSearchQ] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(new Set());

  const fetchBatches = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/curriculum/import/batches`);
      setBatches(r.data);
    } catch {
      toast.error('Falha ao carregar lotes de importação.');
    }
  }, []);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const handleUpload = async () => {
    if (!selectedFile) return toast.info('Selecione um PDF antes.');
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', selectedFile);
      const params = new URLSearchParams();
      if (only) params.append('only', only);
      if (fonte) params.append('fonte', fonte);
      const r = await axios.post(
        `${API}/api/curriculum/import/upload?${params}`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      toast.success(`${r.data.total_items} habilidades extraídas (${r.data.duplicates} duplicadas).`);
      await fetchBatches();
      await openBatch(r.data.batch_id);
      setSelectedFile(null);
      if (fileRef.current) fileRef.current.value = '';
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no upload.');
    } finally {
      setUploading(false);
    }
  };

  const openBatch = async (batchId) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/curriculum/import/batches/${batchId}`);
      setCurrentBatch(r.data);
      setSelectedIdx(new Set());
      setStatusFilter('pending');
    } catch {
      toast.error('Falha ao abrir lote.');
    } finally {
      setLoading(false);
    }
  };

  const updateItem = async (idx, patch) => {
    if (!currentBatch) return;
    try {
      await axios.put(
        `${API}/api/curriculum/import/batches/${currentBatch.id}/items/${idx}`,
        patch
      );
      setCurrentBatch((b) => ({
        ...b,
        items: b.items.map(it => it.idx === idx ? { ...it, ...patch } : it),
      }));
    } catch {
      toast.error('Falha ao salvar edição.');
    }
  };

  const bulkStatus = async (status) => {
    if (!currentBatch || selectedIdx.size === 0) return;
    const indices = [...selectedIdx];
    try {
      await axios.post(
        `${API}/api/curriculum/import/batches/${currentBatch.id}/bulk-status`,
        { indices, status }
      );
      toast.success(`${indices.length} ${status}.`);
      setCurrentBatch((b) => ({
        ...b,
        items: b.items.map(it => indices.includes(it.idx) ? { ...it, status } : it),
      }));
      setSelectedIdx(new Set());
    } catch {
      toast.error('Falha na ação em massa.');
    }
  };

  const commitBatch = async () => {
    if (!currentBatch) return;
    const approvedCount = currentBatch.items.filter(i => i.status === 'approved').length;
    if (approvedCount === 0) return toast.info('Aprove pelo menos 1 habilidade antes.');
    if (!window.confirm(`Importar ${approvedCount} habilidades como ${currentBatch.fonte}?`)) return;
    try {
      const r = await axios.post(`${API}/api/curriculum/import/batches/${currentBatch.id}/commit`);
      toast.success(`${r.data.skills_inserted} importadas · ${r.data.components_created} componentes criados.`);
      await openBatch(currentBatch.id);
      await fetchBatches();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Falha no commit.');
    }
  };

  const cancelBatch = async () => {
    if (!currentBatch) return;
    if (!window.confirm('Excluir este lote? Itens já importados permanecem em curriculum_skills.')) return;
    try {
      await axios.delete(`${API}/api/curriculum/import/batches/${currentBatch.id}`);
      toast.success('Lote removido.');
      setCurrentBatch(null);
      await fetchBatches();
    } catch {
      toast.error('Falha ao excluir lote.');
    }
  };

  const filteredItems = (currentBatch?.items || []).filter((it) => {
    if (statusFilter && it.status !== statusFilter) return false;
    if (searchQ) {
      const q = searchQ.toLowerCase();
      if (!it.codigo.toLowerCase().includes(q) && !it.descricao.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const statusCounts = (currentBatch?.items || []).reduce((acc, i) => {
    acc[i.status] = (acc[i.status] || 0) + 1;
    return acc;
  }, {});

  const toggleSelect = (idx) => {
    setSelectedIdx((prev) => {
      const n = new Set(prev);
      if (n.has(idx)) n.delete(idx);
      else n.add(idx);
      return n;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIdx.size === filteredItems.length) setSelectedIdx(new Set());
    else setSelectedIdx(new Set(filteredItems.map(i => i.idx)));
  };

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6" data-testid="curriculum-import-page">
      <div className="flex items-center gap-2 mb-2">
        <BookOpen className="h-6 w-6 text-purple-600" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Importar Currículo (PDF)</h1>
          <p className="text-sm text-gray-500">BNCC / DCM Floresta do Araguaia — PDF → Extração → Revisão → Importação.</p>
        </div>
      </div>

      {/* Upload */}
      <div className="bg-white border rounded-lg p-4" data-testid="upload-card">
        <h2 className="text-sm font-semibold text-gray-800 mb-3">📥 Novo lote</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <label className="text-xs text-gray-600">Arquivo PDF</label>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              onChange={(e) => setSelectedFile(e.target.files?.[0])}
              className="w-full mt-1 px-3 py-1.5 border rounded text-sm"
              data-testid="upload-file-input"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600">Componente</label>
            <select
              value={only}
              onChange={(e) => setOnly(e.target.value)}
              className="w-full mt-1 px-3 py-1.5 border rounded text-sm"
              data-testid="upload-component-select"
            >
              {COMPONENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-600">Fonte</label>
            <select
              value={fonte}
              onChange={(e) => setFonte(e.target.value)}
              className="w-full mt-1 px-3 py-1.5 border rounded text-sm"
              data-testid="upload-fonte-select"
            >
              <option value="DCM_FA">DCM Floresta do Araguaia</option>
              <option value="BNCC">BNCC</option>
              <option value="MUNICIPAL">Municipal (adaptado)</option>
            </select>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={handleUpload}
            disabled={uploading || !selectedFile}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300 text-sm"
            data-testid="upload-submit-button"
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {uploading ? 'Extraindo...' : 'Enviar e extrair'}
          </button>
          <span className="text-xs text-gray-400">Máx 30 MB. Só PDFs. Extração leva ~10-30s.</span>
        </div>
      </div>

      {/* Lista de batches */}
      {batches.length > 0 && !currentBatch && (
        <div className="bg-white border rounded-lg p-4" data-testid="batches-list-card">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">📚 Lotes recentes</h2>
          <div className="space-y-2">
            {batches.slice(0, 10).map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => openBatch(b.id)}
                className="w-full text-left border rounded-lg p-3 hover:bg-gray-50 flex items-center justify-between gap-3"
                data-testid={`batch-row-${b.id}`}
              >
                <div className="min-w-0">
                  <div className="font-medium truncate flex items-center gap-2">
                    <FileText className="h-4 w-4 text-gray-500" />
                    {b.filename}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {b.total_items} itens · {(b.only_components || []).join(', ') || 'todos'} · {b.fonte} · {new Date(b.created_at).toLocaleString('pt-BR')}
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded border ${b.status === 'committed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : b.status === 'pending_review' ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                  {b.status}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Batch detail */}
      {currentBatch && (
        <div className="bg-white border rounded-lg" data-testid="batch-detail-card">
          <div className="p-4 border-b flex items-center justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCurrentBatch(null)}
                  className="text-xs text-gray-500 hover:text-gray-800"
                  data-testid="back-to-list-button"
                >
                  ← Voltar
                </button>
                <h2 className="text-lg font-semibold truncate">{currentBatch.filename}</h2>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {currentBatch.total_items} itens · {(currentBatch.only_components || []).join(', ') || 'todos'} · {currentBatch.fonte}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={commitBatch}
                disabled={!(statusCounts.approved)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:bg-gray-300 text-sm"
                data-testid="commit-batch-button"
              >
                <CheckCheck className="h-4 w-4" />
                Importar {statusCounts.approved || 0} aprovadas
              </button>
              <button
                type="button"
                onClick={cancelBatch}
                className="inline-flex items-center gap-1.5 px-2 py-1.5 text-rose-600 border border-rose-200 rounded-lg hover:bg-rose-50 text-sm"
                data-testid="cancel-batch-button"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Filtros + bulk actions */}
          <div className="p-3 bg-gray-50 border-b flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1 text-xs">
              <Filter className="h-3 w-3 text-gray-500" />
              {Object.entries(STATUS_CONFIG).map(([k, cfg]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setStatusFilter(k === statusFilter ? '' : k)}
                  className={`px-2 py-0.5 rounded border transition-colors ${k === statusFilter ? cfg.color : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-100'}`}
                  data-testid={`filter-${k}`}
                >
                  {cfg.label} · {statusCounts[k] || 0}
                </button>
              ))}
            </div>
            <div className="flex-1 min-w-[200px] relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400" />
              <input
                type="text"
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="Buscar por código ou descrição..."
                className="w-full pl-7 pr-2 py-1 border rounded text-xs"
                data-testid="batch-search-input"
              />
            </div>
            {selectedIdx.size > 0 && (
              <div className="flex items-center gap-1 text-xs">
                <span className="text-gray-600">{selectedIdx.size} selecionados:</span>
                <button type="button" onClick={() => bulkStatus('approved')} className="px-2 py-0.5 bg-emerald-600 text-white rounded" data-testid="bulk-approve-button">
                  <Check className="h-3 w-3 inline" /> Aprovar
                </button>
                <button type="button" onClick={() => bulkStatus('rejected')} className="px-2 py-0.5 bg-rose-600 text-white rounded" data-testid="bulk-reject-button">
                  <X className="h-3 w-3 inline" /> Rejeitar
                </button>
                <button type="button" onClick={() => bulkStatus('pending')} className="px-2 py-0.5 bg-gray-600 text-white rounded" data-testid="bulk-reset-button">
                  Pendente
                </button>
              </div>
            )}
          </div>

          {/* Tabela */}
          <div className="overflow-x-auto" data-testid="batch-table">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr className="text-xs text-gray-600">
                  <th className="px-2 py-2 text-left w-6">
                    <input
                      type="checkbox"
                      checked={filteredItems.length > 0 && selectedIdx.size === filteredItems.length}
                      onChange={toggleSelectAll}
                      data-testid="select-all-checkbox"
                    />
                  </th>
                  <th className="px-2 py-2 text-left">Código</th>
                  <th className="px-2 py-2 text-left">Descrição</th>
                  <th className="px-2 py-2 text-left w-16">Ano</th>
                  <th className="px-2 py-2 text-left w-20">Comp.</th>
                  <th className="px-2 py-2 text-left w-16">Pág.</th>
                  <th className="px-2 py-2 text-left w-28">Status</th>
                  <th className="px-2 py-2 text-left w-24">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center text-gray-400 py-8">Nenhum item neste filtro.</td>
                  </tr>
                )}
                {filteredItems.map((it) => (
                  <BatchRow
                    key={it.idx}
                    item={it}
                    selected={selectedIdx.has(it.idx)}
                    onToggle={() => toggleSelect(it.idx)}
                    onUpdate={(patch) => updateItem(it.idx, patch)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {loading && <div className="text-center text-sm text-gray-400 py-8"><Loader2 className="inline h-4 w-4 animate-spin" /> Carregando...</div>}
    </div>
  );
}

function BatchRow({ item, selected, onToggle, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    codigo: item.codigo,
    descricao: item.descricao,
    ano: item.ano ?? '',
  });

  const save = () => {
    const patch = {};
    if (draft.codigo !== item.codigo) patch.codigo = draft.codigo;
    if (draft.descricao !== item.descricao) patch.descricao = draft.descricao;
    const newAno = draft.ano === '' ? null : Number(draft.ano);
    if (newAno !== item.ano) patch.ano = newAno;
    if (Object.keys(patch).length > 0) {
      patch.status = 'edited';
      onUpdate(patch);
    }
    setEditing(false);
  };

  const statusCfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending;

  return (
    <tr className="border-b hover:bg-gray-50" data-testid={`batch-item-${item.idx}`}>
      <td className="px-2 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          data-testid={`select-item-${item.idx}`}
        />
      </td>
      <td className="px-2 py-2 font-mono text-xs">
        {editing ? (
          <input value={draft.codigo} onChange={(e) => setDraft(d => ({ ...d, codigo: e.target.value.toUpperCase() }))} className="w-24 px-1 py-0.5 border rounded text-xs" />
        ) : (
          <span className="font-semibold text-purple-700">{item.codigo}</span>
        )}
      </td>
      <td className="px-2 py-2 text-xs max-w-[520px]">
        {editing ? (
          <textarea value={draft.descricao} onChange={(e) => setDraft(d => ({ ...d, descricao: e.target.value }))} rows={2} className="w-full px-1 py-0.5 border rounded text-xs" />
        ) : (
          <div className="line-clamp-2 text-gray-700" title={item.descricao}>{item.descricao}</div>
        )}
      </td>
      <td className="px-2 py-2 text-xs">
        {editing ? (
          <input type="number" min={1} max={9} value={draft.ano} onChange={(e) => setDraft(d => ({ ...d, ano: e.target.value }))} className="w-12 px-1 py-0.5 border rounded text-xs" />
        ) : (
          item.ano ?? <span className="text-gray-400 italic">{item.ano_range ? `${item.ano_range[0]}º-${item.ano_range[1]}º` : '—'}</span>
        )}
      </td>
      <td className="px-2 py-2 text-xs text-gray-500">{item.componente_codigo}</td>
      <td className="px-2 py-2 text-xs text-gray-400">{item.page}</td>
      <td className="px-2 py-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${statusCfg.color}`}>{statusCfg.label}</span>
      </td>
      <td className="px-2 py-2">
        {editing ? (
          <div className="flex items-center gap-1">
            <button type="button" onClick={save} className="text-emerald-600 hover:text-emerald-800" title="Salvar" data-testid={`save-item-${item.idx}`}>
              <Check className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => { setDraft({ codigo: item.codigo, descricao: item.descricao, ano: item.ano ?? '' }); setEditing(false); }} className="text-gray-400 hover:text-gray-700" title="Cancelar">
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setEditing(true)} className="text-blue-600 hover:text-blue-800" title="Editar" data-testid={`edit-item-${item.idx}`}>
              <Edit2 className="h-3.5 w-3.5" />
            </button>
            {item.status !== 'imported' && item.status !== 'duplicate' && (
              <>
                <button type="button" onClick={() => onUpdate({ status: 'approved' })} className="text-emerald-600 hover:text-emerald-800" title="Aprovar" data-testid={`approve-item-${item.idx}`}>
                  <Check className="h-3.5 w-3.5" />
                </button>
                <button type="button" onClick={() => onUpdate({ status: 'rejected' })} className="text-rose-600 hover:text-rose-800" title="Rejeitar" data-testid={`reject-item-${item.idx}`}>
                  <X className="h-3.5 w-3.5" />
                </button>
              </>
            )}
            {item.status === 'duplicate' && (
              <AlertCircle className="h-3.5 w-3.5 text-amber-500" title="Código já existe em curriculum_skills" />
            )}
          </div>
        )}
      </td>
    </tr>
  );
}
