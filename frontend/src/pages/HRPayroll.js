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
  Loader2, CheckCircle2, XCircle, Info
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STATUS_LABELS = {
  not_started: 'Não Iniciada',
  drafting: 'Em Preenchimento',
  pending_review: 'Pendente de Conferência',
  submitted: 'Enviada',
  under_analysis: 'Em Análise',
  returned: 'Devolvida',
  approved: 'Aprovada',
  closed: 'Fechada',
  reopened: 'Reaberta',
  cancelled: 'Cancelada',
};

const STATUS_COLORS = {
  not_started: 'bg-gray-100 text-gray-700',
  drafting: 'bg-yellow-100 text-yellow-800',
  pending_review: 'bg-orange-100 text-orange-800',
  submitted: 'bg-blue-100 text-blue-800',
  under_analysis: 'bg-indigo-100 text-indigo-800',
  returned: 'bg-red-100 text-red-800',
  approved: 'bg-green-100 text-green-800',
  closed: 'bg-slate-200 text-slate-800',
  reopened: 'bg-purple-100 text-purple-800',
  cancelled: 'bg-red-200 text-red-900',
};

const OCCURRENCE_TYPES = [
  { value: 'falta', label: 'Falta' },
  { value: 'falta_justificada', label: 'Falta Justificada' },
  { value: 'atestado', label: 'Atestado Médico' },
  { value: 'afastamento', label: 'Afastamento' },
  { value: 'licenca', label: 'Licença' },
  { value: 'substituicao', label: 'Substituição' },
  { value: 'hora_complementar', label: 'Hora Complementar' },
  { value: 'atraso', label: 'Atraso' },
  { value: 'saida_antecipada', label: 'Saída Antecipada' },
  { value: 'outro', label: 'Outro' },
];

const MONTHS = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
];

function StatusBadge({ status }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export default function HRPayroll() {
  const { user } = useAuth();
  const token = localStorage.getItem('accessToken');
  const isAdmin = ['admin', 'admin_teste'].includes(user?.role);
  const isSemed = ['semed', 'semed3'].includes(user?.role);
  const isGlobal = isAdmin || isSemed;

  // Views: dashboard | payroll-detail | item-detail
  const [view, setView] = useState('dashboard');
  const [loading, setLoading] = useState(false);

  // Dashboard state
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

  // Return reason
  const [showReturnModal, setShowReturnModal] = useState(false);
  const [returnPayrollId, setReturnPayrollId] = useState(null);
  const [returnReason, setReturnReason] = useState('');

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

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
      if (res.ok) {
        const data = await res.json();
        setCurrentPayroll(data);
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [token]);

  const fetchOccurrences = useCallback(async (itemId) => {
    try {
      const res = await fetch(`${API_URL}/api/hr/occurrences?payroll_item_id=${itemId}`, { headers });
      if (res.ok) setOccurrences(await res.json());
    } catch (e) { console.error(e); }
  }, [token]);

  // Initial load
  useEffect(() => {
    fetchCompetencies();
  }, [fetchCompetencies]);

  // When competency selected, load data
  useEffect(() => {
    if (selectedCompetency) {
      fetchPayrolls(selectedCompetency.id);
      fetchDashboard(selectedCompetency.id);
    }
  }, [selectedCompetency]);

  // Create competency
  const handleCreateCompetency = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/hr/competencies`, {
        method: 'POST', headers,
        body: JSON.stringify(newComp)
      });
      if (res.ok) {
        const created = await res.json();
        await fetchCompetencies();
        setSelectedCompetency(created);
        setShowNewCompetency(false);
      } else {
        const err = await res.json();
        alert(err.detail || 'Erro ao criar competência');
      }
    } catch (e) { alert('Erro de conexão'); }
    setLoading(false);
  };

  // Submit payroll
  const handleSubmitPayroll = async (payrollId) => {
    if (!confirm('Confirma o envio desta folha para análise da Secretaria?')) return;
    try {
      const res = await fetch(`${API_URL}/api/hr/school-payrolls/${payrollId}/submit`, {
        method: 'PUT', headers
      });
      if (res.ok) {
        if (currentPayroll) fetchPayrollDetail(payrollId);
        if (selectedCompetency) {
          fetchPayrolls(selectedCompetency.id);
          fetchDashboard(selectedCompetency.id);
        }
      }
    } catch (e) { console.error(e); }
  };

  // Approve payroll
  const handleApprovePayroll = async (payrollId) => {
    if (!confirm('Confirma a aprovação desta folha?')) return;
    try {
      const res = await fetch(`${API_URL}/api/hr/school-payrolls/${payrollId}/approve`, {
        method: 'PUT', headers
      });
      if (res.ok) {
        if (currentPayroll) fetchPayrollDetail(payrollId);
        if (selectedCompetency) {
          fetchPayrolls(selectedCompetency.id);
          fetchDashboard(selectedCompetency.id);
        }
      }
    } catch (e) { console.error(e); }
  };

  // Return payroll
  const handleReturnPayroll = async () => {
    try {
      await fetch(`${API_URL}/api/hr/school-payrolls/${returnPayrollId}/return`, {
        method: 'PUT', headers,
        body: JSON.stringify({ reason: returnReason })
      });
      setShowReturnModal(false);
      setReturnReason('');
      if (currentPayroll) fetchPayrollDetail(returnPayrollId);
      if (selectedCompetency) {
        fetchPayrolls(selectedCompetency.id);
        fetchDashboard(selectedCompetency.id);
      }
    } catch (e) { console.error(e); }
  };

  // Update payroll item
  const handleSaveItem = async () => {
    if (!editingItem) return;
    try {
      const res = await fetch(`${API_URL}/api/hr/payroll-items/${editingItem.id}`, {
        method: 'PUT', headers,
        body: JSON.stringify({
          worked_hours: parseFloat(editingItem.worked_hours) || 0,
          taught_classes: parseInt(editingItem.taught_classes) || 0,
          extra_classes: parseInt(editingItem.extra_classes) || 0,
          complementary_hours: parseFloat(editingItem.complementary_hours) || 0,
          complementary_reason: editingItem.complementary_reason || '',
          observations: editingItem.observations || '',
        })
      });
      if (res.ok) {
        setEditingItem(null);
        fetchPayrollDetail(currentPayroll.id);
      }
    } catch (e) { console.error(e); }
  };

  // Create occurrence
  const handleCreateOccurrence = async () => {
    if (!currentItem) return;
    try {
      const res = await fetch(`${API_URL}/api/hr/occurrences`, {
        method: 'POST', headers,
        body: JSON.stringify({
          payroll_item_id: currentItem.id,
          ...occForm,
          days: parseInt(occForm.days) || 1,
          hours: parseFloat(occForm.hours) || 0,
        })
      });
      if (res.ok) {
        setShowOccForm(false);
        setOccForm({});
        fetchOccurrences(currentItem.id);
        fetchPayrollDetail(currentPayroll.id);
      } else {
        const err = await res.json();
        alert(err.detail || 'Erro ao registrar ocorrência');
      }
    } catch (e) { console.error(e); }
  };

  // Cancel occurrence
  const handleCancelOccurrence = async (occId) => {
    if (!confirm('Cancelar esta ocorrência?')) return;
    try {
      await fetch(`${API_URL}/api/hr/occurrences/${occId}`, {
        method: 'DELETE', headers
      });
      fetchOccurrences(currentItem.id);
      fetchPayrollDetail(currentPayroll.id);
    } catch (e) { console.error(e); }
  };

  // Close competency
  const handleCloseCompetency = async () => {
    if (!selectedCompetency || !confirm('Fechar esta competência? As folhas aprovadas serão bloqueadas.')) return;
    try {
      await fetch(`${API_URL}/api/hr/competencies/${selectedCompetency.id}/close`, {
        method: 'PUT', headers
      });
      fetchCompetencies();
      setSelectedCompetency(prev => ({ ...prev, status: 'closed' }));
      fetchDashboard(selectedCompetency.id);
    } catch (e) { console.error(e); }
  };

  // ===================== RENDER =====================

  // ITEM DETAIL VIEW
  if (view === 'item-detail' && currentItem) {
    const isEditable = currentPayroll && !['approved', 'closed'].includes(currentPayroll.status);
    return (
      <div className="p-4 max-w-5xl mx-auto space-y-4" data-testid="hr-item-detail">
        <button onClick={() => { setView('payroll-detail'); setCurrentItem(null); }}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
          data-testid="hr-back-to-payroll">
          <ArrowLeft size={16} /> Voltar para a folha
        </button>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <UserCheck size={20} />
              {currentItem.employee_name}
            </CardTitle>
            <p className="text-sm text-gray-500">
              Matrícula: {currentItem.employee_matricula || 'N/A'} | Cargo: {currentItem.employee_cargo || 'N/A'} | Vínculo: {currentItem.employee_vinculo || 'N/A'}
            </p>
          </CardHeader>
          <CardContent>
            {editingItem ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div>
                    <label className="text-xs font-medium text-gray-600">Horas Trabalhadas</label>
                    <Input type="number" step="0.5" value={editingItem.worked_hours || ''}
                      onChange={e => setEditingItem({ ...editingItem, worked_hours: e.target.value })}
                      data-testid="hr-edit-worked-hours" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Aulas Ministradas</label>
                    <Input type="number" value={editingItem.taught_classes || ''}
                      onChange={e => setEditingItem({ ...editingItem, taught_classes: e.target.value })}
                      data-testid="hr-edit-taught-classes" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Aulas Extras/Substituição</label>
                    <Input type="number" value={editingItem.extra_classes || ''}
                      onChange={e => setEditingItem({ ...editingItem, extra_classes: e.target.value })}
                      data-testid="hr-edit-extra-classes" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Horas Complementares</label>
                    <Input type="number" step="0.5" value={editingItem.complementary_hours || ''}
                      onChange={e => setEditingItem({ ...editingItem, complementary_hours: e.target.value })}
                      data-testid="hr-edit-complementary-hours" />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-gray-600">Motivo Horas Complementares</label>
                    <Input value={editingItem.complementary_reason || ''}
                      onChange={e => setEditingItem({ ...editingItem, complementary_reason: e.target.value })}
                      data-testid="hr-edit-complementary-reason" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600">Observações</label>
                  <Textarea value={editingItem.observations || ''}
                    onChange={e => setEditingItem({ ...editingItem, observations: e.target.value })}
                    rows={2} data-testid="hr-edit-observations" />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handleSaveItem} data-testid="hr-save-item-btn">
                    <Check size={16} className="mr-1" /> Salvar
                  </Button>
                  <Button variant="outline" onClick={() => setEditingItem(null)} data-testid="hr-cancel-edit-btn">
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <InfoCard label="Carga Prevista" value={`${currentItem.expected_hours || 0}h`} />
                  <InfoCard label="Horas Trabalhadas" value={`${currentItem.worked_hours || 0}h`} />
                  <InfoCard label="Aulas Previstas" value={currentItem.expected_classes || 0} />
                  <InfoCard label="Aulas Ministradas" value={currentItem.taught_classes || 0} />
                  <InfoCard label="Horas Complementares" value={`${currentItem.complementary_hours || 0}h`} />
                  <InfoCard label="Faltas" value={currentItem.absences || 0} />
                  <InfoCard label="Atestado (dias)" value={currentItem.medical_leave_days || 0} />
                  <InfoCard label="Afastamento (dias)" value={currentItem.leave_days || 0} />
                </div>
                {currentItem.validation_status === 'has_issues' && (
                  <div className="bg-amber-50 border border-amber-200 rounded p-2 mb-3 text-sm text-amber-800 flex items-start gap-2">
                    <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                    {currentItem.validation_notes}
                  </div>
                )}
                {currentItem.observations && (
                  <p className="text-sm text-gray-600 mb-3"><strong>Obs:</strong> {currentItem.observations}</p>
                )}
                {isEditable && (
                  <Button variant="outline" size="sm" onClick={() => setEditingItem({ ...currentItem })} data-testid="hr-edit-item-btn">
                    <Edit3 size={14} className="mr-1" /> Editar Lançamento
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Ocorrências */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Ocorrências</CardTitle>
              {isEditable && (
                <Button size="sm" onClick={() => { setShowOccForm(true); setOccForm({ type: 'falta', days: 1, start_date: '' }); }}
                  data-testid="hr-add-occurrence-btn">
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
                      value={occForm.type || ''} onChange={e => setOccForm({ ...occForm, type: e.target.value })}
                      data-testid="hr-occ-type">
                      {OCCURRENCE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Data Início</label>
                    <Input type="date" value={occForm.start_date || ''}
                      onChange={e => setOccForm({ ...occForm, start_date: e.target.value })}
                      data-testid="hr-occ-start-date" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Data Fim</label>
                    <Input type="date" value={occForm.end_date || ''}
                      onChange={e => setOccForm({ ...occForm, end_date: e.target.value })}
                      data-testid="hr-occ-end-date" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Dias</label>
                    <Input type="number" value={occForm.days || ''}
                      onChange={e => setOccForm({ ...occForm, days: e.target.value })}
                      data-testid="hr-occ-days" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">Horas</label>
                    <Input type="number" step="0.5" value={occForm.hours || ''}
                      onChange={e => setOccForm({ ...occForm, hours: e.target.value })}
                      data-testid="hr-occ-hours" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600">N. Documento</label>
                    <Input value={occForm.document_number || ''}
                      onChange={e => setOccForm({ ...occForm, document_number: e.target.value })}
                      data-testid="hr-occ-doc-number" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600">Motivo / Justificativa</label>
                  <Textarea value={occForm.reason || ''} rows={2}
                    onChange={e => setOccForm({ ...occForm, reason: e.target.value })}
                    data-testid="hr-occ-reason" />
                </div>
                <div className="flex gap-2">
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
                    <div>
                      <span className="font-medium text-sm">
                        {OCCURRENCE_TYPES.find(t => t.value === occ.type)?.label || occ.type}
                      </span>
                      <span className="text-gray-500 text-xs ml-2">
                        {occ.start_date}{occ.end_date && occ.end_date !== occ.start_date ? ` a ${occ.end_date}` : ''} ({occ.days} dia(s))
                      </span>
                      {occ.reason && <p className="text-xs text-gray-600 mt-0.5">{occ.reason}</p>}
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

  // PAYROLL DETAIL VIEW
  if (view === 'payroll-detail' && currentPayroll) {
    const canSubmit = ['not_started', 'drafting', 'returned', 'reopened'].includes(currentPayroll.status);
    const canApprove = isGlobal && currentPayroll.status === 'submitted';
    const canReturn = isGlobal && ['submitted', 'under_analysis'].includes(currentPayroll.status);
    const isEditable = !['approved', 'closed'].includes(currentPayroll.status);
    const items = currentPayroll.items || [];

    return (
      <div className="p-4 max-w-6xl mx-auto space-y-4" data-testid="hr-payroll-detail">
        <button onClick={() => { setView('dashboard'); setCurrentPayroll(null); }}
          className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
          data-testid="hr-back-to-dashboard">
          <ArrowLeft size={16} /> Voltar
        </button>

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2" data-testid="hr-payroll-title">
              <Building2 size={22} /> {currentPayroll.school_name}
            </h2>
            <p className="text-sm text-gray-500">
              Competência: {MONTHS[(currentPayroll.month || 1) - 1]}/{currentPayroll.year}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <StatusBadge status={currentPayroll.status} />
            {canSubmit && (
              <Button size="sm" onClick={() => handleSubmitPayroll(currentPayroll.id)}
                data-testid="hr-submit-payroll-btn">
                <Send size={14} className="mr-1" /> Enviar para Análise
              </Button>
            )}
            {canApprove && (
              <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => handleApprovePayroll(currentPayroll.id)}
                data-testid="hr-approve-payroll-btn">
                <Check size={14} className="mr-1" /> Aprovar
              </Button>
            )}
            {canReturn && (
              <Button size="sm" variant="outline" className="border-red-300 text-red-600 hover:bg-red-50"
                onClick={() => { setReturnPayrollId(currentPayroll.id); setShowReturnModal(true); }}
                data-testid="hr-return-payroll-btn">
                <RotateCcw size={14} className="mr-1" /> Devolver
              </Button>
            )}
          </div>
        </div>

        {currentPayroll.return_reason && currentPayroll.status === 'returned' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800 flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <div><strong>Motivo da devolução:</strong> {currentPayroll.return_reason}</div>
          </div>
        )}

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <SummaryCard icon={<Users size={18} />} label="Servidores" value={items.length} color="blue" />
          <SummaryCard icon={<CheckCircle2 size={18} />} label="Conferidos" 
            value={items.filter(i => i.validation_status === 'ok').length} color="green" />
          <SummaryCard icon={<AlertTriangle size={18} />} label="Com Pendência" 
            value={items.filter(i => i.validation_status === 'has_issues').length} color="amber" />
          <SummaryCard icon={<Clock size={18} />} label="H. Complementares" 
            value={`${items.reduce((s, i) => s + (i.complementary_hours || 0), 0)}h`} color="purple" />
          <SummaryCard icon={<XCircle size={18} />} label="Faltas Total"
            value={items.reduce((s, i) => s + (i.absences || 0), 0)} color="red" />
        </div>

        {/* Items table */}
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
                    <th className="text-center p-3 font-medium">Aulas</th>
                    <th className="text-center p-3 font-medium">Compl.</th>
                    <th className="text-center p-3 font-medium">Faltas</th>
                    <th className="text-center p-3 font-medium">Atest.</th>
                    <th className="text-center p-3 font-medium">Afast.</th>
                    <th className="text-center p-3 font-medium">Status</th>
                    <th className="text-center p-3 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(item => (
                    <tr key={item.id} className="border-b hover:bg-gray-50 cursor-pointer"
                      onClick={() => { setCurrentItem(item); setView('item-detail'); fetchOccurrences(item.id); }}>
                      <td className="p-3">
                        <div className="font-medium">{item.employee_name}</div>
                        <div className="text-xs text-gray-500">{item.employee_matricula}</div>
                      </td>
                      <td className="p-3 text-center text-xs">{item.employee_cargo || '-'}</td>
                      <td className="p-3 text-center">{item.expected_hours || 0}h</td>
                      <td className="p-3 text-center">{item.worked_hours || 0}h</td>
                      <td className="p-3 text-center">{item.taught_classes || 0}/{item.expected_classes || 0}</td>
                      <td className="p-3 text-center">{item.complementary_hours || 0}h</td>
                      <td className="p-3 text-center">{item.absences || 0}</td>
                      <td className="p-3 text-center">{item.medical_leave_days || 0}</td>
                      <td className="p-3 text-center">{item.leave_days || 0}</td>
                      <td className="p-3 text-center">
                        {item.validation_status === 'ok' && <CheckCircle2 size={16} className="text-green-500 mx-auto" />}
                        {item.validation_status === 'has_issues' && <AlertTriangle size={16} className="text-amber-500 mx-auto" />}
                        {item.validation_status === 'pending' && <Clock size={16} className="text-gray-400 mx-auto" />}
                      </td>
                      <td className="p-3 text-center" onClick={e => e.stopPropagation()}>
                        <Button variant="ghost" size="sm"
                          onClick={() => { setCurrentItem(item); setView('item-detail'); fetchOccurrences(item.id); }}
                          data-testid={`hr-view-item-${item.id}`}>
                          <Eye size={14} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan={11} className="text-center py-8 text-gray-500">Nenhum servidor nesta folha</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Return modal */}
        {showReturnModal && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" data-testid="hr-return-modal">
            <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
              <h3 className="font-bold text-lg mb-3">Devolver Folha para Correção</h3>
              <Textarea placeholder="Informe o motivo da devolução..." value={returnReason}
                onChange={e => setReturnReason(e.target.value)} rows={4}
                data-testid="hr-return-reason" />
              <div className="flex gap-2 mt-4 justify-end">
                <Button variant="outline" onClick={() => setShowReturnModal(false)}>Cancelar</Button>
                <Button className="bg-red-600 hover:bg-red-700" onClick={handleReturnPayroll}
                  data-testid="hr-confirm-return-btn">
                  Devolver
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // DASHBOARD VIEW (DEFAULT)
  return (
    <div className="p-4 max-w-6xl mx-auto space-y-5" data-testid="hr-dashboard">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FileText size={26} /> RH / Folha de Pagamento
        </h1>
        {isAdmin && (
          <Button onClick={() => setShowNewCompetency(!showNewCompetency)} data-testid="hr-new-competency-btn">
            <Plus size={16} className="mr-1" /> Nova Competência
          </Button>
        )}
      </div>

      {/* New competency form */}
      {showNewCompetency && (
        <Card data-testid="hr-new-competency-form">
          <CardContent className="p-4">
            <h3 className="font-semibold mb-3">Abrir Nova Competência</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600">Ano</label>
                <Input type="number" value={newComp.year}
                  onChange={e => setNewComp({ ...newComp, year: parseInt(e.target.value) })}
                  data-testid="hr-new-comp-year" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Mês</label>
                <select className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  value={newComp.month} onChange={e => setNewComp({ ...newComp, month: parseInt(e.target.value) })}
                  data-testid="hr-new-comp-month">
                  {MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Início Lançamento</label>
                <Input type="date" value={newComp.launch_start || ''}
                  onChange={e => setNewComp({ ...newComp, launch_start: e.target.value })}
                  data-testid="hr-new-comp-start" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Fim Lançamento</label>
                <Input type="date" value={newComp.launch_end || ''}
                  onChange={e => setNewComp({ ...newComp, launch_end: e.target.value })}
                  data-testid="hr-new-comp-end" />
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              <Button onClick={handleCreateCompetency} disabled={loading} data-testid="hr-create-competency-btn">
                {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Check size={14} className="mr-1" />}
                Criar e Gerar Pré-Folha
              </Button>
              <Button variant="outline" onClick={() => setShowNewCompetency(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Competency selector */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Calendar size={18} /> Competências
          </CardTitle>
        </CardHeader>
        <CardContent>
          {competencies.length === 0 ? (
            <p className="text-sm text-gray-500 py-3 text-center">
              Nenhuma competência aberta. {isAdmin ? 'Clique em "Nova Competência" para começar.' : 'Aguarde a Secretaria abrir a competência.'}
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {competencies.map(c => (
                <button key={c.id}
                  onClick={() => setSelectedCompetency(c)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${
                    selectedCompetency?.id === c.id
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
                  }`}
                  data-testid={`hr-comp-${c.year}-${c.month}`}>
                  {MONTHS[c.month - 1]}/{c.year}
                  {c.status === 'closed' && <span className="ml-1 text-xs opacity-70">(Fechada)</span>}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dashboard summary */}
      {selectedCompetency && dashboardData && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <SummaryCard icon={<Building2 size={18} />} label="Escolas" 
              value={dashboardData.summary?.total_schools || 0} color="blue" />
            <SummaryCard icon={<Users size={18} />} label="Servidores" 
              value={dashboardData.summary?.total_employees || 0} color="indigo" />
            <SummaryCard icon={<AlertTriangle size={18} />} label="Pendências" 
              value={dashboardData.summary?.total_issues || 0} color="amber" />
            <SummaryCard icon={<CheckCircle2 size={18} />} label="Aprovadas"
              value={dashboardData.payrolls_by_status?.approved || 0} color="green" />
          </div>

          {/* Status summary bar */}
          {Object.keys(dashboardData.payrolls_by_status || {}).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(dashboardData.payrolls_by_status).map(([st, count]) => (
                <div key={st} className="flex items-center gap-1.5">
                  <StatusBadge status={st} />
                  <span className="text-sm font-medium">{count}</span>
                </div>
              ))}
            </div>
          )}

          {/* Admin controls */}
          {isAdmin && selectedCompetency.status === 'open' && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="border-red-300 text-red-600"
                onClick={handleCloseCompetency} data-testid="hr-close-competency-btn">
                Fechar Competência
              </Button>
            </div>
          )}

          {/* School payrolls list */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Folhas por Escola</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {payrolls.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">Nenhuma folha encontrada para esta competência</p>
              ) : (
                <div className="divide-y">
                  {payrolls.map(p => (
                    <div key={p.id}
                      className="flex items-center justify-between p-4 hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => { fetchPayrollDetail(p.id); setView('payroll-detail'); }}
                      data-testid={`hr-payroll-${p.id}`}>
                      <div>
                        <div className="font-medium text-gray-900">{p.school_name}</div>
                        <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                          <span>{p.total_employees} servidor(es)</span>
                          {p.pending_issues > 0 && (
                            <span className="text-amber-600 font-medium">{p.pending_issues} pendência(s)</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={p.status} />
                        <ChevronRight size={18} className="text-gray-400" />
                      </div>
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

function InfoCard({ label, value }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-bold text-gray-900">{value}</div>
    </div>
  );
}

function SummaryCard({ icon, label, value, color }) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600 border-blue-200',
    green: 'bg-green-50 text-green-600 border-green-200',
    amber: 'bg-amber-50 text-amber-600 border-amber-200',
    red: 'bg-red-50 text-red-600 border-red-200',
    purple: 'bg-purple-50 text-purple-600 border-purple-200',
    indigo: 'bg-indigo-50 text-indigo-600 border-indigo-200',
  };
  return (
    <div className={`rounded-lg border p-3 ${colors[color] || colors.blue}`}>
      <div className="flex items-center gap-2 mb-1">{icon}<span className="text-xs font-medium">{label}</span></div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}
