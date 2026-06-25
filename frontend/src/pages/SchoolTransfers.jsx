import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { schoolsAPI, schoolTransferAPI } from '@/services/api';
import {
  Building2, Plus, FileText, RotateCcw, Eye, Loader2, ShieldAlert, X, Clock,
} from 'lucide-react';

const STATUS_LABELS = {
  executed: { label: 'Executada', cls: 'bg-green-100 text-green-700' },
  rolled_back: { label: 'Revertida', cls: 'bg-gray-200 text-gray-700' },
  dry_run: { label: 'Simulação', cls: 'bg-blue-100 text-blue-700' },
  failed: { label: 'Falhou', cls: 'bg-red-100 text-red-700' },
  expired: { label: 'Expirada', cls: 'bg-amber-100 text-amber-700' },
};

function daysRemaining(executedAt) {
  if (!executedAt) return null;
  const deadline = new Date(executedAt).getTime() + 7 * 86400000;
  const diff = deadline - Date.now();
  if (diff <= 0) return 0;
  return Math.ceil(diff / 86400000);
}

export default function SchoolTransfers() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [schoolMap, setSchoolMap] = useState({});
  const [detail, setDetail] = useState(null);
  const [rollbackTarget, setRollbackTarget] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [data, schools] = await Promise.all([
        schoolTransferAPI.list({ limit: 100 }),
        schoolsAPI.getAll(),
      ]);
      setItems(data.items || []);
      setSchoolMap(Object.fromEntries((schools || []).map((s) => [s.id, s.name])));
    } catch (e) {
      toast.error('Falha ao carregar transferências');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const name = (id) => schoolMap[id] || id || '—';

  const openReceipt = async (protocol) => {
    try {
      const blob = await schoolTransferAPI.receiptBlob(protocol);
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Falha ao gerar recibo');
    }
  };

  const rows = useMemo(() => items.filter((i) => i.status !== 'dry_run'), [items]);

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="text-blue-600" /> Transferências Institucionais
          </h1>
          <Button onClick={() => navigate('/admin/transferencias/nova')} data-testid="panel-new-transfer">
            <Plus size={16} className="mr-1" /> Nova Transferência
          </Button>
        </div>

        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-blue-600" /></div>
            ) : rows.length === 0 ? (
              <div className="p-8 text-center text-gray-500">Nenhuma transferência registrada.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="panel-table">
                  <thead className="bg-gray-50 text-gray-600 text-left">
                    <tr>
                      <th className="p-3">Protocolo</th>
                      <th className="p-3">Origem</th>
                      <th className="p-3">Destino</th>
                      <th className="p-3">Data</th>
                      <th className="p-3">Operador</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Reversível</th>
                      <th className="p-3 text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {rows.map((it) => {
                      const st = STATUS_LABELS[it.status] || { label: it.status, cls: 'bg-gray-100 text-gray-600' };
                      const dleft = it.status === 'executed' ? daysRemaining(it.executed_at) : null;
                      const reversible = it.status === 'executed' && dleft > 0;
                      return (
                        <tr key={it.protocol || it.id} className="hover:bg-gray-50" data-testid={`panel-row-${it.protocol}`}>
                          <td className="p-3 font-mono text-xs">{it.protocol || '—'}</td>
                          <td className="p-3">{name(it.origin_school_id)}</td>
                          <td className="p-3">{name(it.destination_school_id)}</td>
                          <td className="p-3 whitespace-nowrap">{it.executed_at ? new Date(it.executed_at).toLocaleString('pt-BR') : '—'}</td>
                          <td className="p-3 text-xs">{it.executed_by?.email || '—'}</td>
                          <td className="p-3"><span className={`px-2 py-0.5 rounded-full text-xs ${st.cls}`}>{st.label}</span></td>
                          <td className="p-3">
                            {it.status === 'rolled_back' ? <span className="text-xs text-gray-500">Revertida</span>
                              : reversible ? <span className="text-xs text-green-700 flex items-center gap-1"><Clock size={12} /> {dleft} dia(s)</span>
                              : it.status === 'executed' ? <span className="text-xs text-amber-600">Janela expirada</span>
                              : <span className="text-xs text-gray-400">—</span>}
                          </td>
                          <td className="p-3">
                            <div className="flex items-center justify-end gap-1">
                              <button title="Visualizar" onClick={() => setDetail(it)} className="p-1.5 rounded hover:bg-gray-100" data-testid={`panel-view-${it.protocol}`}><Eye size={16} /></button>
                              {(it.status === 'executed' || it.status === 'rolled_back') && (
                                <button title="Gerar recibo" onClick={() => openReceipt(it.protocol)} className="p-1.5 rounded hover:bg-gray-100 text-blue-600" data-testid={`panel-receipt-${it.protocol}`}><FileText size={16} /></button>
                              )}
                              {reversible && (
                                <button title="Reverter" onClick={() => setRollbackTarget(it)} className="p-1.5 rounded hover:bg-red-50 text-red-600" data-testid={`panel-rollback-${it.protocol}`}><RotateCcw size={16} /></button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {detail && <DetailModal item={detail} name={name} onClose={() => setDetail(null)} />}
      {rollbackTarget && (
        <RollbackModal item={rollbackTarget} onClose={() => setRollbackTarget(null)} onDone={() => { setRollbackTarget(null); load(); }} />
      )}
    </Layout>
  );
}

function DetailModal({ item, name, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()} data-testid="panel-detail-modal">
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">Transferência {item.protocol}</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-4 space-y-2 text-sm">
          <p><strong>Origem:</strong> {name(item.origin_school_id)}</p>
          <p><strong>Destino:</strong> {name(item.destination_school_id)}</p>
          <p><strong>Status:</strong> {item.status}</p>
          <p><strong>Operador:</strong> {item.executed_by?.email || '—'}</p>
          <p><strong>Executada em:</strong> {item.executed_at ? new Date(item.executed_at).toLocaleString('pt-BR') : '—'}</p>
          <p><strong>Justificativa:</strong> {item.reason || '—'}</p>
          <p><strong>Turmas:</strong> {(item.class_ids || []).length}</p>
          {item.modified_counts && (
            <div><strong>Itens movidos:</strong>
              <ul className="ml-4 list-disc text-xs text-gray-600">
                {Object.entries(item.modified_counts).map(([k, v]) => <li key={k}>{k}: {v}</li>)}
              </ul>
            </div>
          )}
          {item.rollback && (
            <div className="bg-gray-50 rounded p-2 mt-2">
              <p className="font-medium text-gray-700">Reversão</p>
              <p className="text-xs">Protocolo: {item.rollback.protocol}</p>
              <p className="text-xs">Por: {item.rollback.rolled_back_by?.email} em {item.rollback.rolled_back_at ? new Date(item.rollback.rolled_back_at).toLocaleString('pt-BR') : '—'}</p>
              <p className="text-xs">Justificativa: {item.rollback.reason}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RollbackModal({ item, onClose, onDone }) {
  const PHRASE = 'CONFIRMO A REVERSÃO DA TRANSFERÊNCIA';
  const [password, setPassword] = useState('');
  const [reason, setReason] = useState('');
  const [phrase, setPhrase] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await schoolTransferAPI.rollback(item.protocol, { password, reason, confirmation_text: phrase });
      toast.success(`Revertida: ${r.rollback_protocol}`);
      onDone();
    } catch (e) {
      const det = e.response?.data?.detail;
      if (det && det.reasons) {
        toast.error('Reversão bloqueada: ' + det.reasons.map((x) => x.label).join('; '));
      } else {
        toast.error(typeof det === 'string' ? det : 'Falha ao reverter');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="panel-rollback-modal">
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold text-red-700 flex items-center gap-2"><ShieldAlert size={18} /> Reverter {item.protocol}</h3>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <div className="p-4 space-y-3 text-sm">
          <p className="text-gray-600">Esta ação desfaz a transferência, restaurando as turmas à escola de origem.</p>
          <div>
            <label className="block text-sm font-medium mb-1">Justificativa (mín. 10)</label>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="w-full px-3 py-2 border rounded-lg" data-testid="rollback-reason" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Senha</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="rollback-password" autoComplete="current-password" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Digite: <span className="font-mono text-red-700">{PHRASE}</span></label>
            <input value={phrase} onChange={(e) => setPhrase(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="rollback-phrase" />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button variant="destructive" disabled={busy || reason.trim().length < 10 || !password || phrase.trim() !== PHRASE} onClick={submit} data-testid="rollback-confirm">
              {busy ? <Loader2 size={16} className="mr-1 animate-spin" /> : <RotateCcw size={16} className="mr-1" />} Confirmar reversão
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
