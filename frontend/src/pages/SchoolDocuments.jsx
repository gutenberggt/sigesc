/**
 * Emissão de Declarações Escolares — /admin/declaracoes
 *
 * Fluxo (G1.7):
 *   1. Busca/seleciona aluno
 *   2. Escolhe tipo (matrícula, frequência, escolaridade)
 *   3. Informa finalidade + campos específicos do tipo
 *   4. Emite → download automático do PDF + registro no histórico
 *   5. Pode revogar/baixar de novo pelas emissões anteriores
 *
 * Toda emissão já nasce com código público `SIGESC-XXXX-XXXX`,
 * QR code no PDF e validade respeitando política por tipo:
 *   matrícula=90d · frequência=30d · escolaridade=180d
 */
import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  ChevronLeft, FileText, Send, Search, Download, Ban,
  CheckCircle2, AlertTriangle, Clock, User, Hash,
  Loader2, X,
} from 'lucide-react';
import { studentsAPI } from '@/services/api';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DOC_TYPES = [
  {
    value: 'matricula',
    label: 'Declaração de Matrícula',
    desc: 'Comprova que o aluno está matriculado — 90 dias de validade',
    validity: 90,
  },
  {
    value: 'frequencia',
    label: 'Declaração de Frequência',
    desc: 'Para benefícios sociais e bolsas — 30 dias de validade',
    validity: 30,
  },
  {
    value: 'escolaridade',
    label: 'Declaração de Escolaridade',
    desc: 'Para transferência e consulado — 180 dias de validade',
    validity: 180,
  },
];

export default function SchoolDocuments() {
  const [students, setStudents] = useState([]);
  const [studentQuery, setStudentQuery] = useState('');
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [docType, setDocType] = useState('matricula');
  const [purpose, setPurpose] = useState('');
  const [frequencia, setFrequencia] = useState('');
  const [bimestre, setBimestre] = useState('');
  const [serieConcluida, setSerieConcluida] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [lastIssued, setLastIssued] = useState(null);
  const [history, setHistory] = useState([]);
  const [toast, setToast] = useState(null);

  const loadStudents = useCallback(async () => {
    try {
      const data = await studentsAPI.list();
      setStudents(data || []);
    } catch { /* ignore */ }
  }, []);

  const loadHistory = useCallback(async (studentId = null) => {
    try {
      const url = studentId
        ? `${API}/school-documents?student_id=${studentId}`
        : `${API}/school-documents?limit=20`;
      const r = await axios.get(url);
      setHistory(r.data?.items || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadStudents(); loadHistory(); }, [loadStudents, loadHistory]);

  const filteredStudents = studentQuery
    ? students.filter(s => (s.full_name || '').toLowerCase().includes(studentQuery.toLowerCase()))
    : students.slice(0, 15);

  const resetSpecifics = () => {
    setFrequencia(''); setBimestre(''); setSerieConcluida('');
  };

  const issue = async (e) => {
    e.preventDefault();
    if (!selectedStudent) {
      setToast({ type: 'error', msg: 'Selecione um aluno antes de emitir' });
      return;
    }
    setIssuing(true); setToast(null);
    try {
      const body = {
        student_id: selectedStudent.id,
        doc_type: docType,
        purpose: purpose.trim(),
      };
      if (docType === 'frequencia') {
        if (frequencia) body.frequencia_pct = parseFloat(frequencia);
        if (bimestre) body.bimestre = bimestre;
      }
      if (docType === 'escolaridade' && serieConcluida) {
        body.serie_concluida = serieConcluida;
      }
      const r = await axios.post(`${API}/school-documents/issue`, body, {
        responseType: 'blob',
      });
      // Download
      const code = r.headers['x-sigesc-code'];
      const validUntil = r.headers['x-sigesc-valid-until'];
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `sigesc-${docType}-${code}.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setLastIssued({ code, docType, validUntil, studentName: selectedStudent.full_name });
      setToast({ type: 'success', msg: `Declaração emitida: ${code}` });
      setPurpose(''); resetSpecifics();
      // Atualiza histórico
      loadHistory(selectedStudent.id);
    } catch (err) {
      const msg = err.response?.status === 403
        ? 'Sem permissão para emitir (apenas secretaria).'
        : 'Falha ao emitir declaração.';
      setToast({ type: 'error', msg });
    } finally {
      setIssuing(false);
    }
  };

  const downloadByCode = async (code, dt) => {
    try {
      const r = await axios.get(`${API}/school-documents/${code}/pdf`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `sigesc-${dt}-${code}.pdf`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setToast({ type: 'error', msg: 'Falha ao baixar PDF' });
    }
  };

  const revoke = async (code) => {
    const reason = window.prompt('Motivo da revogação (obrigatório):');
    if (!reason) return;
    try {
      await axios.post(`${API}/school-documents/${code}/revoke`, { reason });
      setToast({ type: 'success', msg: 'Documento revogado' });
      loadHistory(selectedStudent?.id);
    } catch {
      setToast({ type: 'error', msg: 'Falha ao revogar' });
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6" data-testid="school-docs-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Link to="/dashboard" className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-2">
            <ChevronLeft className="h-4 w-4 mr-1" /> Voltar
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FileText className="h-6 w-6 text-indigo-600" />
            Declarações Escolares
          </h1>
          <p className="text-sm text-gray-500 max-w-3xl">
            Emissão institucional com código público verificável e QR code.
            Toda declaração nasce com selo de autenticidade validável em{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">/verificar</code>.
          </p>
        </div>
      </div>

      {toast && (
        <div
          className={`mb-4 border rounded-lg px-3 py-2 text-sm flex items-center gap-2 ${
            toast.type === 'error'
              ? 'bg-red-50 border-red-200 text-red-800'
              : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`}
          data-testid="school-docs-toast"
        >
          {toast.type === 'error' ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          {toast.msg}
          <button onClick={() => setToast(null)} className="ml-auto"><X className="h-4 w-4" /></button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Seleção aluno */}
        <div className="lg:col-span-1 bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1">
            <User className="h-4 w-4" /> 1. Selecione o aluno
          </h2>
          <div className="relative mb-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              value={studentQuery}
              onChange={e => setStudentQuery(e.target.value)}
              placeholder="Buscar por nome..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded text-sm"
              data-testid="school-docs-student-search"
            />
          </div>
          <div className="max-h-80 overflow-y-auto divide-y divide-gray-100">
            {filteredStudents.length === 0 ? (
              <div className="text-xs text-gray-500 py-3 text-center">Nenhum aluno encontrado.</div>
            ) : filteredStudents.map(s => (
              <button
                key={s.id}
                onClick={() => { setSelectedStudent(s); loadHistory(s.id); }}
                className={`w-full text-left py-2 px-2 rounded hover:bg-indigo-50 ${
                  selectedStudent?.id === s.id ? 'bg-indigo-100 text-indigo-900' : 'text-gray-700'
                }`}
                data-testid={`school-docs-student-${s.id}`}
              >
                <div className="text-sm font-semibold">{s.full_name}</div>
                <div className="text-[11px] text-gray-500">
                  {s.birth_date || '—'} · {s.enrollment_number || 'sem matrícula'}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Formulário emissão */}
        <div className="lg:col-span-2 bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1">
            <FileText className="h-4 w-4" /> 2. Escolha o tipo e emita
          </h2>
          {!selectedStudent ? (
            <div className="bg-gray-50 border border-dashed border-gray-300 rounded p-6 text-center text-sm text-gray-500">
              Selecione um aluno à esquerda para habilitar a emissão.
            </div>
          ) : (
            <form onSubmit={issue} className="space-y-4">
              <div className="bg-indigo-50 border border-indigo-200 rounded px-3 py-2 text-sm text-indigo-900">
                Emitindo para <strong>{selectedStudent.full_name}</strong>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {DOC_TYPES.map(t => (
                  <label
                    key={t.value}
                    className={`border rounded p-3 cursor-pointer transition ${
                      docType === t.value
                        ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200'
                        : 'border-gray-200 hover:border-indigo-300'
                    }`}
                  >
                    <input
                      type="radio" className="hidden" name="doc_type"
                      value={t.value} checked={docType === t.value}
                      onChange={() => { setDocType(t.value); resetSpecifics(); }}
                      data-testid={`school-docs-type-${t.value}`}
                    />
                    <div className="font-semibold text-sm text-gray-900">{t.label}</div>
                    <div className="text-[11px] text-gray-600 mt-1">{t.desc}</div>
                    <div className="text-[10px] mt-1.5 inline-flex items-center gap-1 text-indigo-700">
                      <Clock className="h-3 w-3" /> {t.validity} dias
                    </div>
                  </label>
                ))}
              </div>

              {docType === 'frequencia' && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">% de frequência</label>
                    <input
                      type="number" step="0.1" min="0" max="100"
                      value={frequencia} onChange={e => setFrequencia(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      placeholder="Ex.: 95.5"
                      data-testid="school-docs-frequencia"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Bimestre (opcional)</label>
                    <input
                      type="text" value={bimestre} onChange={e => setBimestre(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      placeholder="Ex.: 2º bimestre"
                    />
                  </div>
                </div>
              )}
              {docType === 'escolaridade' && (
                <div>
                  <label className="block text-xs text-gray-600 mb-1">
                    Série concluída/cursada (opcional)
                  </label>
                  <input
                    type="text" value={serieConcluida} onChange={e => setSerieConcluida(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                    placeholder="Ex.: 5º ano do Ensino Fundamental"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs text-gray-600 mb-1">
                  Finalidade <span className="text-gray-400">(opcional — aumenta valor do documento)</span>
                </label>
                <input
                  type="text" value={purpose} onChange={e => setPurpose(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  placeholder="Ex.: Apresentação em banco, benefício do bolsa família, consulado..."
                  data-testid="school-docs-purpose"
                />
              </div>

              <button
                type="submit" disabled={issuing}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 disabled:opacity-60"
                data-testid="school-docs-submit"
              >
                {issuing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Emitir e baixar PDF
              </button>

              {lastIssued && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm" data-testid="school-docs-last">
                  <div className="flex items-center gap-2 text-emerald-900 font-semibold mb-1">
                    <CheckCircle2 className="h-4 w-4" /> Declaração emitida com sucesso
                  </div>
                  <div className="text-xs text-gray-700 space-y-0.5">
                    <div>Aluno: <strong>{lastIssued.studentName}</strong></div>
                    <div>Tipo: <strong>{DOC_TYPES.find(t => t.value === lastIssued.docType)?.label}</strong></div>
                    <div>Código: <code className="font-mono bg-white border border-gray-300 rounded px-1">{lastIssued.code}</code></div>
                    <div>Válido até: <strong>{new Date(lastIssued.validUntil).toLocaleDateString('pt-BR')}</strong></div>
                  </div>
                </div>
              )}
            </form>
          )}
        </div>
      </div>

      {/* Histórico */}
      <div className="mt-6 bg-white border border-gray-200 rounded-lg p-4" data-testid="school-docs-history">
        <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1">
          <Hash className="h-4 w-4" /> Emissões recentes
          {selectedStudent && (
            <span className="text-xs font-normal text-gray-500">
              — apenas de {selectedStudent.full_name}
            </span>
          )}
        </h2>
        {history.length === 0 ? (
          <div className="text-xs text-gray-500 py-3">Nenhuma emissão registrada ainda.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b">
                  <th className="py-2 pr-3">Código</th>
                  <th className="py-2 pr-3">Aluno</th>
                  <th className="py-2 pr-3">Tipo</th>
                  <th className="py-2 pr-3">Finalidade</th>
                  <th className="py-2 pr-3">Emitido</th>
                  <th className="py-2 pr-3">Válido até</th>
                  <th className="py-2 pr-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {history.map(d => (
                  <tr key={d.id} className="border-b border-gray-100" data-testid={`school-docs-row-${d.code}`}>
                    <td className="py-2 pr-3 font-mono text-xs">{d.code}</td>
                    <td className="py-2 pr-3">{d.student_name}</td>
                    <td className="py-2 pr-3">
                      {DOC_TYPES.find(t => t.value === d.doc_type)?.label || d.doc_type}
                    </td>
                    <td className="py-2 pr-3 text-xs text-gray-600">{d.purpose || '—'}</td>
                    <td className="py-2 pr-3 text-xs">{new Date(d.emitted_at).toLocaleString('pt-BR')}</td>
                    <td className="py-2 pr-3 text-xs">{new Date(d.valid_until).toLocaleDateString('pt-BR')}</td>
                    <td className="py-2 pr-3 text-right space-x-2">
                      <button
                        onClick={() => downloadByCode(d.code, d.doc_type)}
                        className="inline-flex items-center gap-1 text-xs text-indigo-700 hover:underline"
                        data-testid={`school-docs-download-${d.code}`}
                      >
                        <Download className="h-3 w-3" /> PDF
                      </button>
                      <button
                        onClick={() => revoke(d.code)}
                        className="inline-flex items-center gap-1 text-xs text-red-700 hover:underline"
                        data-testid={`school-docs-revoke-${d.code}`}
                      >
                        <Ban className="h-3 w-3" /> Revogar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
