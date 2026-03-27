import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import {
  ArrowLeft, Plus, Send, Check, RotateCcw, AlertTriangle,
  FileText, Users, Building2, Calendar, ChevronRight,
  Clock, UserCheck, X, AlertCircle, Eye, Edit3, Trash2,
  Loader2, CheckCircle2, XCircle, Upload, Paperclip,
  History, FileUp, UserMinus, RefreshCw, Download, Printer,
  BarChart3, TrendingUp, ShieldCheck
} from 'lucide-react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from 'recharts';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_LABELS = {
  not_started: 'Não Iniciada', drafting: 'Em Preenchimento', pending_review: 'Pendente de Conferência',
  submitted: 'Enviada', under_analysis: 'Em Análise', returned: 'Devolvida',
  approved: 'Aprovada', closed: 'Fechada', reopened: 'Reaberta', cancelled: 'Cancelada',
};
const STATUS_COLORS = {
  not_started: 'bg-gray-100 text-gray-700', drafting: 'bg-yellow-100 text-yellow-800',
  pending_review: 'bg-orange-100 text-orange-800', submitted: 'bg-blue-100 text-blue-800',
  under_analysis: 'bg-indigo-100 text-indigo-800', returned: 'bg-red-100 text-red-800',
  approved: 'bg-green-100 text-green-800', closed: 'bg-slate-200 text-slate-800',
  reopened: 'bg-purple-100 text-purple-800', cancelled: 'bg-red-200 text-red-900',
};
const OCCURRENCE_TYPES = [
  { value: 'falta', label: 'Falta' }, { value: 'falta_justificada', label: 'Falta Justificada' },
  { value: 'atestado', label: 'Atestado Médico' }, { value: 'afastamento', label: 'Afastamento' },
  { value: 'licenca', label: 'Licença' }, { value: 'substituicao', label: 'Substituição' },
  { value: 'hora_complementar', label: 'Hora Complementar' },
  { value: 'atraso', label: 'Atraso' }, { value: 'saida_antecipada', label: 'Saída Antecipada' },
  { value: 'outro', label: 'Outro' },
];
const MONTHS = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

const PIE_COLORS = {
  not_started: '#94a3b8', drafting: '#fbbf24', submitted: '#3b82f6',
  under_analysis: '#6366f1', returned: '#ef4444', approved: '#22c55e',
  closed: '#64748b', reopened: '#a855f7',
};

const ChartTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-gray-700 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="flex justify-between gap-4">
          <span>{p.name}:</span><span className="font-bold">{typeof p.value === 'number' && p.value % 1 !== 0 ? p.value.toFixed(1) : p.value}{p.unit || ''}</span>
        </p>
      ))}
    </div>
  );
};
const FIELD_LABELS = {
  worked_hours: 'Horas Trabalhadas', classes_not_taught: 'Horas Não Cumpridas',
  classes_replaced: 'Horas Repostas', extra_classes: 'Horas Extras', complementary_hours: 'Horas Complementares',
  complementary_reason: 'Motivo Complementar', complementary_type: 'Tipo Complementar',
  complementary_period: 'Período Complementar', complementary_authorized_by: 'Autorizado por',
  absences: 'Faltas', justified_absences: 'Faltas Justificadas', medical_leave_days: 'Dias Atestado',
  leave_days: 'Dias Afastamento', observations: 'Observações',
};

function StatusBadge({ status }) {
  return (
    <span data-testid={`hr-status-${status}`} className={`px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}
function InfoCard({ label, value }) {
  return (<div className="bg-gray-50 rounded-lg p-3"><div className="text-xs text-gray-500">{label}</div><div className="text-lg font-bold text-gray-900">{value}</div></div>);
}
function SummaryCard({ icon, label, value, color }) {
  const colors = { blue:'bg-blue-50 text-blue-600 border-blue-200', green:'bg-green-50 text-green-600 border-green-200', amber:'bg-amber-50 text-amber-600 border-amber-200', red:'bg-red-50 text-red-600 border-red-200', purple:'bg-purple-50 text-purple-600 border-purple-200', indigo:'bg-indigo-50 text-indigo-600 border-indigo-200' };
  return (<div className={`rounded-lg border p-3 ${colors[color]||colors.blue}`}><div className="flex items-center gap-2 mb-1">{icon}<span className="text-xs font-medium">{label}</span></div><div className="text-xl font-bold">{value}</div></div>);
}

export default function HRPayroll() {
  const { user } = useAuth();
  const token = localStorage.getItem('accessToken');
  const isAdmin = ['admin', 'admin_teste'].includes(user?.role);
  const isAnalista = ['semed2'].includes(user?.role);
  const isSemedViewer = ['semed3'].includes(user?.role);
  const isGlobal = isAdmin || isAnalista || isSemedViewer;
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const [view, setView] = useState('dashboard');
  const [loading, setLoading] = useState(false);

  // Dashboard
  const [competencies, setCompetencies] = useState([]);
  const [selectedCompetency, setSelectedCompetency] = useState(null);
  const [payrolls, setPayrolls] = useState([]);
  const [dashboardData, setDashboardData] = useState(null);
  const [showNewCompetency, setShowNewCompetency] = useState(false);
  const [newComp, setNewComp] = useState({ year: 2026, month: new Date().getMonth() + 1 });

  // Payroll detail
  const [currentPayroll, setCurrentPayroll] = useState(null);

  // Item detail
  const [currentItem, setCurrentItem] = useState(null);
  const [occurrences, setOccurrences] = useState([]);
  const [showOccForm, setShowOccForm] = useState(false);
  const [occForm, setOccForm] = useState({});
  const [editingItem, setEditingItem] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState([]);
  const [uploading, setUploading] = useState(false);

  // Enums
  const [enums, setEnums] = useState({ complementary_motives: [], leave_subtypes: [] });
  const [schoolEmployees, setSchoolEmployees] = useState([]);

  // Return modal
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [returnPayrollId, setReturnPayrollId] = useState(null);
  const [returnReason, setReturnReason] = useState('');

  // Analytics
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  // Reopen competency modal
  const [showReopenModal, setShowReopenModal] = useState(false);
  const [reopenJustification, setReopenJustification] = useState('');

  // =================== API CALLS ===================

  const fetchCompetencies = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/hr/competencies`, { headers });
      if (res.ok) setCompetencies(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchPayrolls = useCallback(async (compId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/school-payrolls?competency_id=${compId}`, { headers });
      if (res.ok) setPayrolls(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchDashboard = useCallback(async (compId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/dashboard?competency_id=${compId}`, { headers });
      if (res.ok) setDashboardData(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchPayrollDetail = useCallback(async (payrollId) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/hr/school-payrolls/${payrollId}`, { headers });
      if (res.ok) setCurrentPayroll(await res.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [token]);

  const fetchOccurrences = useCallback(async (itemId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/occurrences?payroll_item_id=${itemId}`, { headers });
      if (res.ok) setOccurrences(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchEnums = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/hr/enums`, { headers });
      if (res.ok) setEnums(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchSchoolEmployees = useCallback(async (payrollId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/school-employees/${payrollId}`, { headers });
      if (res.ok) setSchoolEmployees(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchHistory = useCallback(async (itemId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/payroll-items/${itemId}/history`, { headers });
      if (res.ok) setHistory(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  const fetchAnalytics = useCallback(async (compId) => {
    if (!isGlobal) return;
    setAnalyticsLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/hr/dashboard/analytics?competency_id=${compId}`, { headers });
      if (res.ok) setAnalytics(await res.json());
    } catch (e) { console.error(e); }
    setAnalyticsLoading(false);
  }, [token, isGlobal]);

  useEffect(() => { fetchCompetencies(); fetchEnums(); }, []);

  useEffect(() => {
    if (selectedCompetency) {
      fetchPayrolls(selectedCompetency.id);
      fetchDashboard(selectedCompetency.id);
      fetchAnalytics(selectedCompetency.id);
    }
  }, [selectedCompetency]);

  // =================== HANDLERS ===================

  const handleCreateCompetency = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/hr/competencies`, { method: 'POST', headers, body: JSON.stringify(newComp) });
      if (res.ok) {
        const created = await res.json();
        await fetchCompetencies();
        setSelectedCompetency(created);
        setShowNewCompetency(false);
      } else { const err = await res.json(); alert(err.detail || 'Erro'); }
    } catch (e) { alert('Erro de conexão'); }
    setLoading(false);
  };

  const handleSubmitPayroll = async (payrollId) => {
    if (!confirm('Confirma o envio desta folha para análise da Secretaria?')) return;
    const res = await fetch(`${API_URL}/api/hr/school-payrolls/${payrollId}/submit`, { method: 'PUT', headers });
    if (res.ok) {
      const data = await res.json();
      if (data.warnings && data.warnings.length > 0) {
        alert(`Folha enviada com alertas:\n\n${data.warnings.map(w => '- ' + w).join('\n')}`);
      }
      if (currentPayroll) fetchPayrollDetail(payrollId);
      if (selectedCompetency) { fetchPayrolls(selectedCompetency.id); fetchDashboard(selectedCompetency.id); }
    } else {
      const err = await res.json();
      alert(err.detail || 'Erro ao enviar folha');
    }
  };

  const handleApprovePayroll = async (payrollId) => {
    if (!confirm('Confirma a aprovação desta folha?')) return;
    const res = await fetch(`${API_URL}/api/hr/school-payrolls/${payrollId}/approve`, { method: 'PUT', headers });
    if (res.ok) { if (currentPayroll) fetchPayrollDetail(payrollId); if (selectedCompetency) { fetchPayrolls(selectedCompetency.id); fetchDashboard(selectedCompetency.id); } }
  };

  const handleReturnPayroll = async () => {
    const res = await fetch(`${API_URL}/api/hr/school-payrolls/${returnPayrollId}/return`, { method: 'PUT', headers, body: JSON.stringify({ reason: returnReason }) });
    if (res.ok) {
      const data = await res.json();
      alert(data.message || 'Folha devolvida com sucesso');
    }
    setShowReturnModal(false); setReturnReason('');
    if (currentPayroll) fetchPayrollDetail(returnPayrollId);
    if (selectedCompetency) { fetchPayrolls(selectedCompetency.id); fetchDashboard(selectedCompetency.id); }
  };

  const handleSaveItem = async () => {
    if (!editingItem) return;
    const body = {
      worked_hours: parseFloat(editingItem.worked_hours) || 0,
      taught_classes: parseInt(editingItem.taught_classes) || 0,
      classes_not_taught: parseInt(editingItem.classes_not_taught) || 0,
      classes_replaced: parseInt(editingItem.classes_replaced) || 0,
      extra_classes: parseInt(editingItem.extra_classes) || 0,
      complementary_hours: parseFloat(editingItem.complementary_hours) || 0,
      complementary_reason: editingItem.complementary_reason || '',
      complementary_type: editingItem.complementary_type || '',
      complementary_period: editingItem.complementary_period || '',
      complementary_authorized_by: editingItem.complementary_authorized_by || '',
      observations: editingItem.observations || '',
    };
    const res = await fetch(`${API_URL}/api/hr/payroll-items/${editingItem.id}`, { method: 'PUT', headers, body: JSON.stringify(body) });
    if (res.ok) {
      const updated = await res.json();
      setCurrentItem(updated);
      setEditingItem(null);
      fetchPayrollDetail(currentPayroll.id);
    }
  };

  const handleUploadDoc = async (file) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_URL}/api/hr/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      if (res.ok) {
        const data = await res.json();
        setOccForm(prev => ({ ...prev, document_url: data.url }));
      } else { alert('Erro no upload do documento'); }
    } catch (e) { alert('Erro no upload'); }
    setUploading(false);
  };

  const handleCreateOccurrence = async () => {
    if (!currentItem) return;
    const res = await fetch(`${API_URL}/api/hr/occurrences`, {
      method: 'POST', headers,
      body: JSON.stringify({
        payroll_item_id: currentItem.id, ...occForm,
        days: parseInt(occForm.days) || 1, hours: parseFloat(occForm.hours) || 0,
      })
    });
    if (res.ok) {
      setShowOccForm(false); setOccForm({});
      fetchOccurrences(currentItem.id);
      fetchPayrollDetail(currentPayroll.id);
    } else { const err = await res.json(); alert(err.detail || 'Erro'); }
  };

  const handleCancelOccurrence = async (occId) => {
    if (!confirm('Cancelar esta ocorrência?')) return;
    await fetch(`${API_URL}/api/hr/occurrences/${occId}`, { method: 'DELETE', headers });
    fetchOccurrences(currentItem.id);
    fetchPayrollDetail(currentPayroll.id);
  };

  const handleDownloadPdf = async (url, fallbackName) => {
    try {
      const res = await fetch(`${API_URL}${url}`, { headers });
      if (!res.ok) throw new Error('Erro ao gerar PDF');
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch (e) {
      console.error('Erro ao baixar PDF:', e);
    }
  };

  const handleCloseCompetency = async () => {
    if (!selectedCompetency || !confirm('Fechar esta competência? As folhas aprovadas serão bloqueadas.')) return;
    await fetch(`${API_URL}/api/hr/competencies/${selectedCompetency.id}/close`, { method: 'PUT', headers });
    fetchCompetencies();
    setSelectedCompetency(prev => ({ ...prev, status: 'closed' }));
    fetchDashboard(selectedCompetency.id);
  };

  const handleReopenCompetency = async () => {
    if (!reopenJustification || reopenJustification.trim().length < 5) {
      alert('Justificativa obrigatória (mínimo 5 caracteres)');
      return;
    }
    const res = await fetch(`${API_URL}/api/hr/competencies/${selectedCompetency.id}/reopen`, {
      method: 'PUT', headers,
      body: JSON.stringify({ justification: reopenJustification })
    });
    if (res.ok) {
      setShowReopenModal(false);
      setReopenJustification('');
      fetchCompetencies();
      setSelectedCompetency(prev => ({ ...prev, status: 'open' }));
      fetchDashboard(selectedCompetency.id);
    } else {
      const err = await res.json();
      alert(err.detail || 'Erro ao reabrir');
    }
  };

  // =================== RENDER: ITEM DETAIL ===================
  if (view === 'item-detail' && currentItem) {
    const isEditable = currentPayroll && !['approved', 'closed'].includes(currentPayroll.status) && !isSemedViewer;
    return (
      <div className="p-4 max-w-5xl mx-auto space-y-4" data-testid="hr-item-detail">
        <button onClick={() => { setView('payroll-detail'); setCurrentItem(null); setShowHistory(false); }}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900" data-testid="hr-back-to-payroll">
          <ArrowLeft size={16} /> Voltar para a folha
        </button>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2"><UserCheck size={20} /> {currentItem.employee_name}</CardTitle>
                <p className="text-sm text-gray-500">
                  Matrícula: {currentItem.employee_matricula || 'N/A'} | Cargo: {currentItem.employee_cargo || 'N/A'} | Vínculo: {currentItem.employee_vinculo || 'N/A'}
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={() => { setShowHistory(!showHistory); if (!showHistory) fetchHistory(currentItem.id); }}
                data-testid="hr-toggle-history-btn">
                <History size={14} className="mr-1" /> Histórico
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {editingItem ? (
              /* ===== EDITING MODE ===== */
              <div className="space-y-4">
                <h4 className="font-semibold text-sm text-gray-700 border-b pb-1">Carga Horária</h4>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div><label className="text-xs font-medium text-gray-600">Horas Trabalhadas</label>
                    <Input type="number" step="0.5" value={editingItem.worked_hours||''} onChange={e => setEditingItem({...editingItem, worked_hours: e.target.value})} data-testid="hr-edit-worked-hours" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Horas Não Cumpridas</label>
                    <Input type="number" value={editingItem.classes_not_taught||''} onChange={e => setEditingItem({...editingItem, classes_not_taught: e.target.value})} data-testid="hr-edit-classes-not-taught" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Horas Repostas</label>
                    <Input type="number" value={editingItem.classes_replaced||''} onChange={e => setEditingItem({...editingItem, classes_replaced: e.target.value})} data-testid="hr-edit-classes-replaced" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Horas Extras / Substituição</label>
                    <Input type="number" value={editingItem.extra_classes||''} onChange={e => setEditingItem({...editingItem, extra_classes: e.target.value})} data-testid="hr-edit-extra-classes" /></div>
                </div>

                <h4 className="font-semibold text-sm text-gray-700 border-b pb-1 mt-4">Horas Complementares</h4>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div><label className="text-xs font-medium text-gray-600">Qtd. Horas</label>
                    <Input type="number" step="0.5" value={editingItem.complementary_hours||''} onChange={e => setEditingItem({...editingItem, complementary_hours: e.target.value})} data-testid="hr-edit-complementary-hours" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Tipo / Motivo</label>
                    <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" value={editingItem.complementary_type||''} onChange={e => setEditingItem({...editingItem, complementary_type: e.target.value})} data-testid="hr-edit-complementary-type">
                      <option value="">Selecione...</option>
                      {enums.complementary_motives.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                  <div><label className="text-xs font-medium text-gray-600">Período</label>
                    <Input value={editingItem.complementary_period||''} placeholder="Ex: 01/03 a 15/03" onChange={e => setEditingItem({...editingItem, complementary_period: e.target.value})} data-testid="hr-edit-complementary-period" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Autorizado por</label>
                    <Input value={editingItem.complementary_authorized_by||''} onChange={e => setEditingItem({...editingItem, complementary_authorized_by: e.target.value})} data-testid="hr-edit-complementary-auth" /></div>
                  <div className="col-span-2"><label className="text-xs font-medium text-gray-600">Justificativa Detalhada</label>
                    <Input value={editingItem.complementary_reason||''} onChange={e => setEditingItem({...editingItem, complementary_reason: e.target.value})} data-testid="hr-edit-complementary-reason" /></div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600">Observações</label>
                  <Textarea value={editingItem.observations||''} onChange={e => setEditingItem({...editingItem, observations: e.target.value})} rows={2} data-testid="hr-edit-observations" />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handleSaveItem} data-testid="hr-save-item-btn"><Check size={14} className="mr-1" /> Salvar</Button>
                  <Button variant="outline" onClick={() => setEditingItem(null)}>Cancelar</Button>
                </div>
              </div>
            ) : (
              /* ===== READ MODE ===== */
              <div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                  <InfoCard label="Carga Prevista" value={`${currentItem.expected_hours||0}h`} />
                  <InfoCard label="Horas Trabalhadas" value={`${currentItem.worked_hours||0}h`} />
                  <InfoCard label="Horas Não Cumpridas" value={currentItem.classes_not_taught||0} />
                  <InfoCard label="Horas Repostas" value={currentItem.classes_replaced||0} />
                  <InfoCard label="Horas Extras" value={currentItem.extra_classes||0} />
                  <InfoCard label="H. Complementares" value={`${currentItem.complementary_hours||0}h`} />
                  <InfoCard label="Faltas" value={currentItem.absences||0} />
                  <InfoCard label="Faltas Justif." value={currentItem.justified_absences||0} />
                  <InfoCard label="Atestado (dias)" value={currentItem.medical_leave_days||0} />
                  <InfoCard label="Afastamento (dias)" value={currentItem.leave_days||0} />
                </div>
                {currentItem.complementary_type && (
                  <div className="bg-purple-50 border border-purple-200 rounded p-2 mb-3 text-sm">
                    <strong>Complementar:</strong> {currentItem.complementary_type}
                    {currentItem.complementary_period && <> | Período: {currentItem.complementary_period}</>}
                    {currentItem.complementary_authorized_by && <> | Autorizado: {currentItem.complementary_authorized_by}</>}
                    {currentItem.complementary_reason && <div className="text-xs mt-1">Justificativa: {currentItem.complementary_reason}</div>}
                  </div>
                )}
                {currentItem.validation_status === 'has_issues' && (
                  <div className="bg-amber-50 border border-amber-200 rounded p-2 mb-3 text-sm text-amber-800 flex items-start gap-2">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {currentItem.validation_notes}
                  </div>
                )}
                {currentItem.observations && <p className="text-sm text-gray-600 mb-3"><strong>Obs:</strong> {currentItem.observations}</p>}
                {isEditable && (
                  <Button variant="outline" size="sm" onClick={() => setEditingItem({...currentItem})} data-testid="hr-edit-item-btn">
                    <Edit3 size={14} className="mr-1" /> Editar Lançamento
                  </Button>
                )}
                <Button variant="outline" size="sm" className="ml-2 border-blue-300 text-blue-600 hover:bg-blue-50"
                  onClick={() => handleDownloadPdf(`/api/hr/reports/espelho/${currentItem.id}`, 'espelho.pdf')}
                  data-testid="hr-download-espelho-btn">
                  <Printer size={14} className="mr-1" /> Espelho Individual (PDF)
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Histórico de alterações */}
        {showHistory && (
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><History size={16} /> Histórico de Alterações</CardTitle></CardHeader>
            <CardContent>
              {history.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-3">Nenhuma alteração registrada</p>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {history.map(h => (
                    <div key={h.id} className="border rounded p-2 text-xs">
                      <div className="flex justify-between text-gray-500 mb-1">
                        <span className="font-medium">{h.user_name}</span>
                        <span>{new Date(h.timestamp).toLocaleString('pt-BR')}</span>
                      </div>
                      {h.changes?.map((c, i) => (
                        <div key={i} className="text-gray-700">
                          <span className="font-medium">{FIELD_LABELS[c.field] || c.field}:</span>{' '}
                          <span className="text-red-500 line-through">{c.old_value || '(vazio)'}</span>{' '}&rarr;{' '}
                          <span className="text-green-600">{c.new_value || '(vazio)'}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Ocorrências */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Ocorrências ({occurrences.length})</CardTitle>
              {isEditable && (
                <Button size="sm" onClick={() => {
                  setShowOccForm(true);
                  setOccForm({ type: 'falta', days: 1, start_date: '' });
                  if (currentPayroll) fetchSchoolEmployees(currentPayroll.id);
                }} data-testid="hr-add-occurrence-btn">
                  <Plus size={14} className="mr-1" /> Nova Ocorrência
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {showOccForm && (
              <div className="bg-gray-50 border rounded-lg p-4 mb-4 space-y-3" data-testid="hr-occurrence-form">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs font-medium text-gray-600">Tipo</label>
                    <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      value={occForm.type||''} onChange={e => setOccForm({...occForm, type: e.target.value})} data-testid="hr-occ-type">
                      {OCCURRENCE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>
                  <div><label className="text-xs font-medium text-gray-600">Data Início</label>
                    <Input type="date" value={occForm.start_date||''} onChange={e => setOccForm({...occForm, start_date: e.target.value})} data-testid="hr-occ-start-date" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Data Fim</label>
                    <Input type="date" value={occForm.end_date||''} onChange={e => setOccForm({...occForm, end_date: e.target.value})} data-testid="hr-occ-end-date" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Dias</label>
                    <Input type="number" value={occForm.days||''} onChange={e => setOccForm({...occForm, days: e.target.value})} data-testid="hr-occ-days" /></div>
                  <div><label className="text-xs font-medium text-gray-600">Horas</label>
                    <Input type="number" step="0.5" value={occForm.hours||''} onChange={e => setOccForm({...occForm, hours: e.target.value})} data-testid="hr-occ-hours" /></div>
                  <div><label className="text-xs font-medium text-gray-600">N. Documento</label>
                    <Input value={occForm.document_number||''} onChange={e => setOccForm({...occForm, document_number: e.target.value})} data-testid="hr-occ-doc-number" /></div>
                </div>

                {/* Subtipo para afastamento/licença */}
                {['afastamento', 'licenca'].includes(occForm.type) && (
                  <div>
                    <label className="text-xs font-medium text-gray-600">Subtipo</label>
                    <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      value={occForm.subtype||''} onChange={e => setOccForm({...occForm, subtype: e.target.value})} data-testid="hr-occ-subtype">
                      <option value="">Selecione...</option>
                      {enums.leave_subtypes.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                )}

                {/* Motivo para hora complementar */}
                {occForm.type === 'hora_complementar' && (
                  <div>
                    <label className="text-xs font-medium text-gray-600">Motivo (obrigatório)</label>
                    <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      value={occForm.reason||''} onChange={e => setOccForm({...occForm, reason: e.target.value})} data-testid="hr-occ-hc-motive">
                      <option value="">Selecione o motivo...</option>
                      {enums.complementary_motives.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                )}

                {/* Substituição: selecionar servidor substituído */}
                {occForm.type === 'substituicao' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-gray-600">Servidor Substituído (obrigatório)</label>
                      <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                        value={occForm.substituted_employee_id||''} onChange={e => setOccForm({...occForm, substituted_employee_id: e.target.value})} data-testid="hr-occ-substituted">
                        <option value="">Selecione...</option>
                        {schoolEmployees.filter(e => e.id !== currentItem.employee_id).map(e => (
                          <option key={e.id} value={e.id}>{e.nome} ({e.matricula || 'S/M'})</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600">Carga Horária Assumida</label>
                      <Input type="number" step="0.5" value={occForm.hours||''} onChange={e => setOccForm({...occForm, hours: e.target.value})} />
                    </div>
                  </div>
                )}

                {/* Motivo/Justificativa geral */}
                {occForm.type !== 'hora_complementar' && (
                  <div>
                    <label className="text-xs font-medium text-gray-600">Motivo / Justificativa</label>
                    <Textarea value={occForm.reason||''} rows={2} onChange={e => setOccForm({...occForm, reason: e.target.value})} data-testid="hr-occ-reason" />
                  </div>
                )}

                {/* Upload de documento */}
                <div>
                  <label className="text-xs font-medium text-gray-600 flex items-center gap-1">
                    <Paperclip size={12} /> Documento Comprobatório
                  </label>
                  <div className="flex items-center gap-2 mt-1">
                    <label className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-md cursor-pointer hover:bg-gray-50 text-sm">
                      <FileUp size={14} />
                      {uploading ? 'Enviando...' : (occForm.document_url ? 'Substituir arquivo' : 'Anexar arquivo')}
                      <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp"
                        onChange={e => { if (e.target.files[0]) handleUploadDoc(e.target.files[0]); }}
                        disabled={uploading} data-testid="hr-occ-file-input" />
                    </label>
                    {occForm.document_url && (
                      <div className="flex items-center gap-1 text-green-600 text-sm">
                        <CheckCircle2 size={14} />
                        <a href={`${API_URL}${occForm.document_url}`} target="_blank" rel="noreferrer" className="underline">Ver anexo</a>
                        <button onClick={() => setOccForm({...occForm, document_url: null})} className="text-red-400 hover:text-red-600 ml-1"><X size={14} /></button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex gap-2 pt-1">
                  <Button size="sm" onClick={handleCreateOccurrence} data-testid="hr-save-occurrence-btn">
                    <Check size={14} className="mr-1" /> Registrar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowOccForm(false)}>Cancelar</Button>
                </div>
              </div>
            )}

            {occurrences.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">Nenhuma ocorrência registrada</p>
            ) : (
              <div className="space-y-2">
                {occurrences.map(occ => (
                  <div key={occ.id} className="flex items-center justify-between border rounded-lg p-3 hover:bg-gray-50">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{OCCURRENCE_TYPES.find(t => t.value === occ.type)?.label || occ.type}</span>
                        {occ.subtype && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{occ.subtype}</span>}
                        <span className="text-gray-500 text-xs">
                          {occ.start_date}{occ.end_date && occ.end_date !== occ.start_date ? ` a ${occ.end_date}` : ''} ({occ.days} dia(s))
                        </span>
                        {occ.document_url ? (
                          <a href={`${API_URL}${occ.document_url}`} target="_blank" rel="noreferrer" className="text-blue-500 hover:text-blue-700" title="Ver documento">
                            <Paperclip size={14} />
                          </a>
                        ) : (
                          <span className="text-orange-400" title="Sem documento anexado"><AlertCircle size={14} /></span>
                        )}
                      </div>
                      {occ.reason && <p className="text-xs text-gray-600 mt-0.5">{occ.reason}</p>}
                      {occ.type === 'substituicao' && occ.substituted_name && (
                        <p className="text-xs text-indigo-600 mt-0.5 flex items-center gap-1"><UserMinus size={12} /> Substituindo: {occ.substituted_name}</p>
                      )}
                    </div>
                    {isEditable && (
                      <Button size="sm" variant="ghost" onClick={() => handleCancelOccurrence(occ.id)}
                        className="text-red-500 hover:text-red-700" data-testid={`hr-cancel-occ-${occ.id}`}>
                        <Trash2 size={14} />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // =================== RENDER: PAYROLL DETAIL ===================
  if (view === 'payroll-detail' && currentPayroll) {
    const canSubmit = ['not_started', 'drafting', 'returned', 'reopened'].includes(currentPayroll.status) && !isSemedViewer;
    const canApprove = (isAdmin || isAnalista) && currentPayroll.status === 'submitted';
    const canReturn = (isAdmin || isAnalista) && ['submitted', 'under_analysis'].includes(currentPayroll.status);
    const items = currentPayroll.items || [];

    return (
      <div className="p-4 max-w-6xl mx-auto space-y-4" data-testid="hr-payroll-detail">
        <button onClick={() => { setView('dashboard'); setCurrentPayroll(null); }}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900" data-testid="hr-back-to-dashboard">
          <ArrowLeft size={16} /> Voltar
        </button>

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2" data-testid="hr-payroll-title">
              <Building2 size={22} /> {currentPayroll.school_name}
            </h2>
            <p className="text-sm text-gray-500">Competência: {MONTHS[(currentPayroll.month||1)-1]}/{currentPayroll.year}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={currentPayroll.status} />
            {canSubmit && <Button size="sm" onClick={() => handleSubmitPayroll(currentPayroll.id)} data-testid="hr-submit-payroll-btn"><Send size={14} className="mr-1" /> Enviar para Análise</Button>}
            {canApprove && <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => handleApprovePayroll(currentPayroll.id)} data-testid="hr-approve-payroll-btn"><Check size={14} className="mr-1" /> Aprovar</Button>}
            {canReturn && <Button size="sm" variant="outline" className="border-red-300 text-red-600 hover:bg-red-50" onClick={() => { setReturnPayrollId(currentPayroll.id); setShowReturnModal(true); }} data-testid="hr-return-payroll-btn"><RotateCcw size={14} className="mr-1" /> Devolver</Button>}
            <Button size="sm" variant="outline" className="border-blue-300 text-blue-600 hover:bg-blue-50"
              onClick={() => handleDownloadPdf(`/api/hr/reports/folha-escola/${currentPayroll.id}`, 'folha.pdf')}
              data-testid="hr-download-folha-btn">
              <Download size={14} className="mr-1" /> PDF da Folha
            </Button>
          </div>
        </div>

        {currentPayroll.return_reason && currentPayroll.status === 'returned' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800 flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0" /> <div><strong>Motivo da devolução:</strong> {currentPayroll.return_reason}</div>
          </div>
        )}

        {currentPayroll.observations && currentPayroll.status === 'submitted' && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800 flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <div>
              <strong>Alertas no envio:</strong>
              <ul className="mt-1 list-disc list-inside">
                {currentPayroll.observations.split('; ').map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard icon={<Users size={18} />} label="Servidores" value={items.length} color="blue" />
          <SummaryCard icon={<CheckCircle2 size={18} />} label="Conferidos" value={items.filter(i => i.validation_status === 'ok').length} color="green" />
          <SummaryCard icon={<AlertTriangle size={18} />} label="Com Pendência" value={items.filter(i => i.validation_status === 'has_issues').length} color="amber" />
          <SummaryCard icon={<Clock size={18} />} label="H. Complementares" value={`${items.reduce((s,i) => s + (i.complementary_hours||0), 0)}h`} color="purple" />
          <SummaryCard icon={<XCircle size={18} />} label="Faltas Total" value={items.reduce((s,i) => s + (i.absences||0), 0)} color="red" />
        </div>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="hr-items-table">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left p-3 font-medium">Servidor</th>
                    <th className="text-center p-3 font-medium">Cargo</th>
                    <th className="text-center p-3 font-medium">CH Prev.</th>
                    <th className="text-center p-3 font-medium">H. Trab.</th>
                    <th className="text-center p-3 font-medium">Horas</th>
                    <th className="text-center p-3 font-medium">Compl.</th>
                    <th className="text-center p-3 font-medium">Faltas</th>
                    <th className="text-center p-3 font-medium">Atest.</th>
                    <th className="text-center p-3 font-medium">Afast.</th>
                    <th className="text-center p-3 font-medium">Docs</th>
                    <th className="text-center p-3 font-medium">Status</th>
                    <th className="text-center p-3 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(item => (
                    <tr key={item.id} className="border-b hover:bg-gray-50 cursor-pointer"
                      onClick={() => { setCurrentItem(item); setView('item-detail'); fetchOccurrences(item.id); }}>
                      <td className="p-3"><div className="font-medium">{item.employee_name}</div><div className="text-xs text-gray-500">{item.employee_matricula}</div></td>
                      <td className="p-3 text-center text-xs">{item.employee_cargo||'-'}</td>
                      <td className="p-3 text-center">{item.expected_hours||0}h</td>
                      <td className="p-3 text-center">{item.worked_hours||0}h</td>
                      <td className="p-3 text-center">{item.taught_classes||0}/{item.expected_classes||0}</td>
                      <td className="p-3 text-center">{item.complementary_hours||0}h</td>
                      <td className="p-3 text-center">{item.absences||0}</td>
                      <td className="p-3 text-center">{item.medical_leave_days||0}</td>
                      <td className="p-3 text-center">{item.leave_days||0}</td>
                      <td className="p-3 text-center">
                        {(item.documents_count||0) > 0 ? (
                          <span className="text-green-500 flex items-center justify-center gap-0.5"><Paperclip size={14} />{item.documents_count}</span>
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                      <td className="p-3 text-center">
                        {item.validation_status === 'ok' && <CheckCircle2 size={16} className="text-green-500 mx-auto" />}
                        {item.validation_status === 'has_issues' && <AlertTriangle size={16} className="text-amber-500 mx-auto" />}
                        {item.validation_status === 'pending' && <Clock size={16} className="text-gray-400 mx-auto" />}
                      </td>
                      <td className="p-3 text-center" onClick={e => e.stopPropagation()}>
                        <Button variant="ghost" size="sm" onClick={() => { setCurrentItem(item); setView('item-detail'); fetchOccurrences(item.id); }} data-testid={`hr-view-item-${item.id}`}>
                          <Eye size={14} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && <tr><td colSpan={12} className="text-center py-8 text-gray-500">Nenhum servidor nesta folha</td></tr>}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {showReturnModal && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" data-testid="hr-return-modal">
            <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
              <h3 className="font-bold text-lg mb-3">Devolver Folha para Correção</h3>
              <Textarea placeholder="Informe o motivo da devolução..." value={returnReason} onChange={e => setReturnReason(e.target.value)} rows={4} data-testid="hr-return-reason" />
              <div className="flex gap-2 mt-4 justify-end">
                <Button variant="outline" onClick={() => setShowReturnModal(false)}>Cancelar</Button>
                <Button className="bg-red-600 hover:bg-red-700" onClick={handleReturnPayroll} data-testid="hr-confirm-return-btn">Devolver</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // =================== RENDER: DASHBOARD ===================
  return (
    <div className="p-4 max-w-6xl mx-auto space-y-5" data-testid="hr-dashboard">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><FileText size={26} /> RH / Folha de Pagamento</h1>
        {(isAdmin || isAnalista) && <Button onClick={() => setShowNewCompetency(!showNewCompetency)} data-testid="hr-new-competency-btn"><Plus size={16} className="mr-1" /> Nova Competência</Button>}
      </div>

      {showNewCompetency && (
        <Card data-testid="hr-new-competency-form">
          <CardContent className="p-4">
            <h3 className="font-semibold mb-3">Abrir Nova Competência</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div><label className="text-xs font-medium text-gray-600">Ano</label>
                <Input type="number" value={newComp.year} onChange={e => setNewComp({...newComp, year: parseInt(e.target.value)})} data-testid="hr-new-comp-year" /></div>
              <div><label className="text-xs font-medium text-gray-600">Mês</label>
                <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" value={newComp.month} onChange={e => setNewComp({...newComp, month: parseInt(e.target.value)})} data-testid="hr-new-comp-month">
                  {MONTHS.map((m,i) => <option key={i} value={i+1}>{m}</option>)}
                </select></div>
              <div><label className="text-xs font-medium text-gray-600">Início Lançamento</label>
                <Input type="date" value={newComp.launch_start||''} onChange={e => setNewComp({...newComp, launch_start: e.target.value})} data-testid="hr-new-comp-start" /></div>
              <div><label className="text-xs font-medium text-gray-600">Fim Lançamento</label>
                <Input type="date" value={newComp.launch_end||''} onChange={e => setNewComp({...newComp, launch_end: e.target.value})} data-testid="hr-new-comp-end" /></div>
            </div>
            <div className="flex gap-2 mt-3">
              <Button onClick={handleCreateCompetency} disabled={loading} data-testid="hr-create-competency-btn">
                {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Check size={14} className="mr-1" />} Criar e Gerar Pré-Folha
              </Button>
              <Button variant="outline" onClick={() => setShowNewCompetency(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Calendar size={18} /> Competências</CardTitle></CardHeader>
        <CardContent>
          {competencies.length === 0 ? (
            <p className="text-sm text-gray-500 py-3 text-center">{(isAdmin || isAnalista) ? 'Clique em "Nova Competência" para começar.' : 'Aguarde a Secretaria abrir a competência.'}</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {competencies.map(c => (
                <button key={c.id} onClick={() => setSelectedCompetency(c)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${selectedCompetency?.id === c.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'}`}
                  data-testid={`hr-comp-${c.year}-${c.month}`}>
                  {MONTHS[c.month-1]}/{c.year}{c.status === 'closed' && <span className="ml-1 text-xs opacity-70">(Fechada)</span>}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {selectedCompetency && dashboardData && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SummaryCard icon={<Building2 size={18} />} label="Escolas" value={dashboardData.summary?.total_schools||0} color="blue" />
            <SummaryCard icon={<Users size={18} />} label="Servidores" value={dashboardData.summary?.total_employees||0} color="indigo" />
            <SummaryCard icon={<AlertTriangle size={18} />} label="Pendências" value={dashboardData.summary?.total_issues||0} color="amber" />
            <SummaryCard icon={<CheckCircle2 size={18} />} label="Aprovadas" value={dashboardData.payrolls_by_status?.approved||0} color="green" />
          </div>

          {Object.keys(dashboardData.payrolls_by_status||{}).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(dashboardData.payrolls_by_status).map(([st, count]) => (
                <div key={st} className="flex items-center gap-1.5"><StatusBadge status={st} /><span className="text-sm font-medium">{count}</span></div>
              ))}
            </div>
          )}

          {/* =================== PAINEL DE INDICADORES =================== */}
          {isGlobal && analytics && (
            <div className="space-y-4" data-testid="hr-analytics-panel">
              {/* Linha 1: Conformidade + Pizza de Status */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Cards de conformidade */}
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
                    <ShieldCheck size={16} className="text-emerald-600" /> Taxa de Conformidade
                  </h3>
                  <Card className="border-emerald-200 bg-gradient-to-br from-emerald-50 to-white">
                    <CardContent className="p-4">
                      <div className="text-xs text-gray-500 mb-1">Servidores sem pendências</div>
                      <div className="flex items-end gap-2">
                        <span className="text-3xl font-bold text-emerald-700">{analytics.conformity.employees_ok_pct}%</span>
                        <span className="text-xs text-gray-500 mb-1">{analytics.conformity.ok_employees}/{analytics.conformity.total_employees}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                        <div className="bg-emerald-500 h-2 rounded-full transition-all duration-500" style={{ width: `${Math.min(analytics.conformity.employees_ok_pct, 100)}%` }} />
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="border-blue-200 bg-gradient-to-br from-blue-50 to-white">
                    <CardContent className="p-4">
                      <div className="text-xs text-gray-500 mb-1">Folhas enviadas/aprovadas</div>
                      <div className="flex items-end gap-2">
                        <span className="text-3xl font-bold text-blue-700">{analytics.conformity.payrolls_sent_pct}%</span>
                        <span className="text-xs text-gray-500 mb-1">{analytics.conformity.sent_payrolls}/{analytics.conformity.total_payrolls}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                        <div className="bg-blue-500 h-2 rounded-full transition-all duration-500" style={{ width: `${Math.min(analytics.conformity.payrolls_sent_pct, 100)}%` }} />
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Pizza de distribuição de status */}
                <Card className="lg:col-span-2">
                  <CardHeader className="pb-1">
                    <CardTitle className="text-sm flex items-center gap-1.5"><BarChart3 size={16} className="text-indigo-600" /> Distribuição de Status das Folhas</CardTitle>
                  </CardHeader>
                  <CardContent className="p-2">
                    {Object.keys(analytics.status_distribution).length === 0 ? (
                      <p className="text-sm text-gray-400 text-center py-8">Sem dados</p>
                    ) : (
                      <div className="flex items-center">
                        <ResponsiveContainer width="55%" height={200}>
                          <PieChart>
                            <Pie
                              data={Object.entries(analytics.status_distribution).map(([k, v]) => ({ name: STATUS_LABELS[k] || k, value: v, key: k }))}
                              cx="50%" cy="50%" innerRadius={45} outerRadius={80}
                              paddingAngle={3} dataKey="value" strokeWidth={2} stroke="#fff"
                            >
                              {Object.entries(analytics.status_distribution).map(([k]) => (
                                <Cell key={k} fill={PIE_COLORS[k] || '#94a3b8'} />
                              ))}
                            </Pie>
                            <Tooltip content={<ChartTooltip />} />
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="flex-1 space-y-1.5 pl-2">
                          {Object.entries(analytics.status_distribution).map(([k, v]) => (
                            <div key={k} className="flex items-center gap-2 text-xs">
                              <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: PIE_COLORS[k] || '#94a3b8' }} />
                              <span className="text-gray-600 flex-1">{STATUS_LABELS[k] || k}</span>
                              <span className="font-bold text-gray-800">{v}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Linha 2: Horas da Rede + Ranking de Ausências */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Resumo de horas da rede */}
                <Card>
                  <CardHeader className="pb-1">
                    <CardTitle className="text-sm flex items-center gap-1.5"><TrendingUp size={16} className="text-blue-600" /> Horas da Rede</CardTitle>
                  </CardHeader>
                  <CardContent className="p-2">
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={[
                        { name: 'Previstas', value: analytics.network_summary.expected, fill: '#3b82f6' },
                        { name: 'Trabalhadas', value: analytics.network_summary.worked, fill: '#22c55e' },
                        { name: 'Complementares', value: analytics.network_summary.complementary, fill: '#a855f7' },
                      ]} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => `${v}h`} />
                        <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 11 }} />
                        <Tooltip content={<ChartTooltip />} />
                        <Bar dataKey="value" name="Horas" radius={[0, 6, 6, 0]} barSize={28}>
                          {[
                            { fill: '#3b82f6' },
                            { fill: '#22c55e' },
                            { fill: '#a855f7' },
                          ].map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Ranking de ausências por escola */}
                <Card>
                  <CardHeader className="pb-1">
                    <CardTitle className="text-sm flex items-center gap-1.5"><AlertTriangle size={16} className="text-amber-600" /> Ausências por Escola</CardTitle>
                  </CardHeader>
                  <CardContent className="p-2">
                    {analytics.schools_ranking.filter(s => s.absences > 0).length === 0 ? (
                      <p className="text-sm text-gray-400 text-center py-8">Nenhuma ausência registrada</p>
                    ) : (
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={analytics.schools_ranking.filter(s => s.absences > 0).slice(0, 8)}
                          layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 11 }} />
                          <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 10 }} />
                          <Tooltip content={<ChartTooltip />} />
                          <Bar dataKey="absences" name="Total Ausências" fill="#f59e0b" radius={[0, 6, 6, 0]} barSize={22} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Linha 3: Detalhamento de ausências da rede */}
              {(analytics.network_summary.absences > 0 || analytics.network_summary.medical > 0 || analytics.network_summary.leave > 0) && (
                <Card>
                  <CardHeader className="pb-1">
                    <CardTitle className="text-sm flex items-center gap-1.5"><Users size={16} className="text-red-600" /> Detalhamento de Ausências da Rede</CardTitle>
                  </CardHeader>
                  <CardContent className="p-2">
                    <ResponsiveContainer width="100%" height={180}>
                      <BarChart data={[
                        { name: 'Faltas', value: analytics.network_summary.absences, fill: '#ef4444' },
                        { name: 'Atestados', value: analytics.network_summary.medical, fill: '#f97316' },
                        { name: 'Afastamentos', value: analytics.network_summary.leave, fill: '#eab308' },
                      ]} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} />
                        <Tooltip content={<ChartTooltip />} />
                        <Bar dataKey="value" name="Dias" radius={[6, 6, 0, 0]} barSize={50}>
                          {[{ fill: '#ef4444' }, { fill: '#f97316' }, { fill: '#eab308' }].map((e, i) => <Cell key={i} fill={e.fill} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
          {isGlobal && analyticsLoading && (
            <div className="flex items-center justify-center py-6 text-gray-400">
              <Loader2 size={20} className="animate-spin mr-2" /> Carregando indicadores...
            </div>
          )}

          {(isAdmin || isAnalista) && selectedCompetency.status === 'open' && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="border-red-300 text-red-600" onClick={handleCloseCompetency} data-testid="hr-close-competency-btn">Fechar Competência</Button>
            </div>
          )}

          {(isAdmin || isAnalista) && selectedCompetency.status === 'closed' && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="border-purple-300 text-purple-600" onClick={() => setShowReopenModal(true)} data-testid="hr-reopen-competency-btn">
                <RefreshCw size={14} className="mr-1" /> Reabrir Competência
              </Button>
            </div>
          )}

          {isGlobal && selectedCompetency && (
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" className="border-indigo-300 text-indigo-600 hover:bg-indigo-50"
                onClick={() => handleDownloadPdf(`/api/hr/reports/consolidado-rede/${selectedCompetency.id}`, 'consolidado.pdf')}
                data-testid="hr-download-consolidado-btn">
                <Download size={14} className="mr-1" /> Consolidado da Rede (PDF)
              </Button>
              <Button variant="outline" size="sm" className="border-amber-300 text-amber-600 hover:bg-amber-50"
                onClick={() => handleDownloadPdf(`/api/hr/reports/auditoria/${selectedCompetency.id}`, 'auditoria.pdf')}
                data-testid="hr-download-auditoria-btn">
                <FileText size={14} className="mr-1" /> Relatório de Auditoria (PDF)
              </Button>
            </div>
          )}

          {showReopenModal && (
            <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" data-testid="hr-reopen-modal">
              <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
                <h3 className="font-bold text-lg mb-3">Reabrir Competência</h3>
                <p className="text-sm text-gray-600 mb-3">Esta ação será registrada na auditoria. Informe a justificativa:</p>
                <Textarea placeholder="Justificativa para reabertura (mínimo 5 caracteres)..." value={reopenJustification} onChange={e => setReopenJustification(e.target.value)} rows={3} data-testid="hr-reopen-justification" />
                <div className="flex gap-2 mt-4 justify-end">
                  <Button variant="outline" onClick={() => { setShowReopenModal(false); setReopenJustification(''); }}>Cancelar</Button>
                  <Button className="bg-purple-600 hover:bg-purple-700" onClick={handleReopenCompetency} data-testid="hr-confirm-reopen-btn">Reabrir</Button>
                </div>
              </div>
            </div>
          )}

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-base">Folhas por Escola</CardTitle></CardHeader>
            <CardContent className="p-0">
              {payrolls.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Nenhuma folha encontrada</p>
              ) : (
                <div className="divide-y">
                  {payrolls.map(p => (
                    <div key={p.id} className="flex items-center justify-between p-4 hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => { fetchPayrollDetail(p.id); setView('payroll-detail'); }} data-testid={`hr-payroll-${p.id}`}>
                      <div>
                        <div className="font-medium text-gray-900">{p.school_name}</div>
                        <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                          <span>{p.total_employees} servidor(es)</span>
                          {p.pending_issues > 0 && <span className="text-amber-600 font-medium">{p.pending_issues} pendência(s)</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-3"><StatusBadge status={p.status} /><ChevronRight size={18} className="text-gray-400" /></div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
