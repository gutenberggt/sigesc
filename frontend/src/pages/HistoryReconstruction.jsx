import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { schoolsAPI, classesAPI, studentsAPI, historyReconstructionAPI } from '@/services/api';
import {
  History, Home, Search, ShieldAlert, FileText, Loader2, CheckCircle2,
  ClipboardCheck, ClipboardList, BookOpen, AlertTriangle,
} from 'lucide-react';

const SCOPES = [
  { value: 'student', label: 'Aluno', help: 'Reprocessa um aluno específico.' },
  { value: 'class', label: 'Turma', help: 'Reprocessa todos os alunos de uma turma.' },
  { value: 'school', label: 'Escola', help: 'Reprocessa todos os alunos de uma escola.' },
];

const MIN_REASON = 10;

export default function HistoryReconstruction() {
  const navigate = useNavigate();

  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);

  const [scope, setScope] = useState('student');
  const [schoolId, setSchoolId] = useState('');
  const [classId, setClassId] = useState('');
  const [studentId, setStudentId] = useState('');
  const [academicYear, setAcademicYear] = useState('');

  const [preview, setPreview] = useState(null);
  const [loadingDry, setLoadingDry] = useState(false);
  const [loadingExec, setLoadingExec] = useState(false);
  const [result, setResult] = useState(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const PHRASE = 'CONFIRMO A RECONSTRUCAO';

  useEffect(() => {
    schoolsAPI.getAll().then((s) => setSchools(s || [])).catch(() => toast.error('Falha ao carregar escolas'));
  }, []);

  useEffect(() => {
    setClassId('');
    setStudentId('');
    setClasses([]);
    setStudents([]);
    setPreview(null);
    setResult(null);
    if (!schoolId) return;
    if (scope === 'class') {
      classesAPI.getAll(schoolId).then((c) => setClasses(c || [])).catch(() => toast.error('Falha ao carregar turmas'));
    }
    if (scope === 'student') {
      studentsAPI.getAll({ school_id: schoolId })
        .then((s) => {
          // studentsAPI.getAll returns paginated dict { students: [...], total, ... } OR an array.
          const arr = Array.isArray(s) ? s : (s?.students || s?.items || []);
          setStudents(arr);
        })
        .catch(() => toast.error('Falha ao carregar alunos'));
    }
  }, [schoolId, scope]);

  const buildScopePayload = () => {
    const p = { scope };
    if (academicYear) p.academic_year = parseInt(academicYear, 10);
    if (scope === 'student') p.student_id = studentId;
    if (scope === 'class') p.class_id = classId;
    if (scope === 'school') p.school_id = schoolId;
    return p;
  };

  const scopeReady = () => {
    if (scope === 'student') return !!studentId;
    if (scope === 'class') return !!classId;
    if (scope === 'school') return !!schoolId;
    return false;
  };

  const runDryRun = async () => {
    setLoadingDry(true);
    setResult(null);
    setPreview(null);
    try {
      const data = await historyReconstructionAPI.dryRun(buildScopePayload());
      setPreview(data);
      if (data.movements_detected === 0) {
        toast.info('Nenhuma movimentação detectada no escopo selecionado.');
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Falha na simulação (dry-run).');
    } finally {
      setLoadingDry(false);
    }
  };

  const runExecute = async () => {
    setLoadingExec(true);
    try {
      const data = await historyReconstructionAPI.execute({ ...buildScopePayload(), reason: reason.trim() });
      setResult(data);
      setConfirmOpen(false);
      setReason('');
      setConfirmPhrase('');
      setPreview(null);
      toast.success(`Reconstrução concluída: ${data.protocol}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Falha ao executar a reconstrução.');
    } finally {
      setLoadingExec(false);
    }
  };

  const openReceipt = async (protocol) => {
    try {
      const blob = await historyReconstructionAPI.receiptBlob(protocol);
      window.open(window.URL.createObjectURL(blob), '_blank');
    } catch (e) {
      toast.error('Falha ao gerar recibo.');
    }
  };

  const totalToConsolidate = preview
    ? (preview.to_consolidate?.attendance || 0) + (preview.to_consolidate?.grades || 0) + (preview.to_consolidate?.content_entries || 0)
    : 0;

  return (
    <Layout>
      <div className="space-y-6" data-testid="history-reconstruction-page">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-gray-500 hover:text-blue-600 transition-colors" data-testid="recon-home">
            <Home size={20} /><span>Início</span>
          </button>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <History className="text-purple-600" /> Reconstrução de Histórico Pedagógico
          </h1>
        </div>

        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3 text-sm text-amber-800">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <p>
            Esta ferramenta reprocessa (de forma <strong>idempotente</strong>) a consolidação pedagógica de alunos que
            mudaram de turma no mesmo ano letivo, copiando <strong>frequência, notas e conteúdo</strong> das turmas de
            origem para a turma atual. <strong>Não altera os dados de origem</strong>. Sempre execute a <strong>simulação</strong> antes.
          </p>
        </div>

        {/* Configuração de escopo */}
        <Card>
          <CardContent className="p-6 space-y-4">
            <h2 className="text-lg font-semibold text-gray-800">Escopo</h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {SCOPES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setScope(s.value)}
                  data-testid={`recon-scope-${s.value}`}
                  className={`text-left border rounded-lg p-3 transition-colors ${scope === s.value ? 'border-purple-500 bg-purple-50' : 'border-gray-200 hover:border-gray-300'}`}
                >
                  <p className="font-medium text-gray-900">{s.label}</p>
                  <p className="text-xs text-gray-500 mt-1">{s.help}</p>
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Escola</label>
                <select
                  value={schoolId}
                  onChange={(e) => setSchoolId(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg bg-white"
                  data-testid="recon-school-select"
                >
                  <option value="">Selecione a escola…</option>
                  {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>

              {scope === 'class' && (
                <div>
                  <label className="block text-sm font-medium mb-1">Turma</label>
                  <select
                    value={classId}
                    onChange={(e) => setClassId(e.target.value)}
                    disabled={!schoolId}
                    className="w-full px-3 py-2 border rounded-lg bg-white disabled:bg-gray-100"
                    data-testid="recon-class-select"
                  >
                    <option value="">Selecione a turma…</option>
                    {classes.map((c) => <option key={c.id} value={c.id}>{c.name}{c.academic_year ? ` (${c.academic_year})` : ''}</option>)}
                  </select>
                </div>
              )}

              {scope === 'student' && (
                <div>
                  <label className="block text-sm font-medium mb-1">Aluno</label>
                  <select
                    value={studentId}
                    onChange={(e) => setStudentId(e.target.value)}
                    disabled={!schoolId}
                    className="w-full px-3 py-2 border rounded-lg bg-white disabled:bg-gray-100"
                    data-testid="recon-student-select"
                  >
                    <option value="">Selecione o aluno…</option>
                    {students.map((s) => <option key={s.id} value={s.id}>{s.full_name || s.name}</option>)}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium mb-1">Ano letivo (opcional)</label>
                <input
                  type="number"
                  value={academicYear}
                  onChange={(e) => setAcademicYear(e.target.value)}
                  placeholder="Ex.: 2026 — vazio = todos os anos"
                  className="w-full px-3 py-2 border rounded-lg"
                  data-testid="recon-year-input"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button onClick={runDryRun} disabled={!scopeReady() || loadingDry} data-testid="recon-dryrun-btn">
                {loadingDry ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Search size={16} className="mr-2" />}
                Simular (dry-run)
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Resultado da simulação */}
        {preview && (
          <Card data-testid="recon-preview">
            <CardContent className="p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">Resultado da simulação</h2>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Stat label="Alunos no escopo" value={preview.students_in_scope} color="gray" />
                <Stat label="Movimentações" value={preview.movements_detected} color="blue" />
                <Stat label="Frequências" value={preview.to_consolidate?.attendance ?? 0} color="cyan" icon={ClipboardCheck} />
                <Stat label="Notas" value={preview.to_consolidate?.grades ?? 0} color="teal" icon={ClipboardList} />
                <Stat label="Conteúdos" value={preview.to_consolidate?.content_entries ?? 0} color="purple" icon={BookOpen} />
              </div>

              {preview.details && preview.details.length > 0 && (
                <div className="max-h-64 overflow-y-auto border rounded">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-100 sticky top-0">
                      <tr>
                        <th className="text-left p-2">Aluno</th>
                        <th className="text-left p-2">Origem → Destino</th>
                        <th className="text-center p-2">Ano</th>
                        <th className="text-center p-2">Freq.</th>
                        <th className="text-center p-2">Notas</th>
                        <th className="text-center p-2">Conteúdo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.details.map((d, i) => (
                        <tr key={i} className="border-t">
                          <td className="p-2 font-mono text-[11px]">{d.student_id}</td>
                          <td className="p-2 font-mono text-[11px]">{d.source_class_id} → {d.target_class_id}</td>
                          <td className="p-2 text-center">{d.academic_year || '—'}</td>
                          <td className="p-2 text-center">{d.missing?.attendance ?? 0}</td>
                          <td className="p-2 text-center">{d.missing?.grades ?? 0}</td>
                          <td className="p-2 text-center">{d.missing?.content_entries ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {preview.movements_detected === 0 ? (
                <p className="text-sm text-blue-700 bg-blue-50 p-3 rounded">
                  Nenhuma movimentação a reconstruir neste escopo. Os históricos já estão consolidados.
                </p>
              ) : totalToConsolidate === 0 ? (
                <p className="text-sm text-green-700 bg-green-50 p-3 rounded">
                  ✅ Movimentações detectadas, porém os dados já estão consolidados (nada a copiar).
                </p>
              ) : (
                <div className="flex justify-end">
                  <Button variant="default" className="bg-purple-600 hover:bg-purple-700" onClick={() => setConfirmOpen(true)} data-testid="recon-open-execute">
                    <History size={16} className="mr-2" /> Executar reconstrução ({totalToConsolidate} registro(s))
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Resultado da execução */}
        {result && (
          <Card data-testid="recon-result">
            <CardContent className="p-6 space-y-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="text-green-600" size={22} />
                <h2 className="text-lg font-semibold text-green-800">Reconstrução concluída — {result.protocol}</h2>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Stat label="Alunos" value={result.students_processed} color="gray" />
                <Stat label="Movimentações" value={result.movements_processed} color="blue" />
                <Stat label="Frequências" value={result.applied_counts?.attendance ?? 0} color="cyan" />
                <Stat label="Notas" value={result.applied_counts?.grades ?? 0} color="teal" />
                <Stat label="Conteúdos" value={result.applied_counts?.content_entries ?? 0} color="purple" />
              </div>
              <div className="flex justify-end">
                <Button variant="outline" onClick={() => openReceipt(result.protocol)} data-testid="recon-receipt-btn">
                  <FileText size={16} className="mr-2" /> Baixar recibo (PDF)
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setConfirmOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="recon-confirm-modal">
            <div className="flex items-center justify-between p-4 border-b">
              <h3 className="font-semibold text-purple-700 flex items-center gap-2"><ShieldAlert size={18} /> Confirmar reconstrução</h3>
            </div>
            <div className="p-4 space-y-3 text-sm">
              <p className="text-gray-600">
                Esta ação copia os dados pedagógicos faltantes para a turma atual. É idempotente e auditada.
              </p>
              <div>
                <label className="block text-sm font-medium mb-1">Justificativa (mín. {MIN_REASON} caracteres)</label>
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="w-full px-3 py-2 border rounded-lg" data-testid="recon-reason" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Digite: <span className="font-mono text-purple-700">{PHRASE}</span></label>
                <input value={confirmPhrase} onChange={(e) => setConfirmPhrase(e.target.value)} className="w-full px-3 py-2 border rounded-lg" data-testid="recon-phrase" />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancelar</Button>
                <Button
                  className="bg-purple-600 hover:bg-purple-700"
                  disabled={loadingExec || reason.trim().length < MIN_REASON || confirmPhrase.trim() !== PHRASE}
                  onClick={runExecute}
                  data-testid="recon-confirm-execute"
                >
                  {loadingExec ? <Loader2 size={16} className="mr-2 animate-spin" /> : <History size={16} className="mr-2" />} Confirmar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}

function Stat({ label, value, color = 'gray', icon: Icon }) {
  const colors = {
    gray: 'bg-gray-50 text-gray-700',
    blue: 'bg-blue-50 text-blue-700',
    cyan: 'bg-cyan-50 text-cyan-700',
    teal: 'bg-teal-50 text-teal-700',
    purple: 'bg-purple-50 text-purple-700',
  };
  return (
    <div className={`rounded-lg p-3 text-center ${colors[color]}`}>
      <p className="text-2xl font-bold flex items-center justify-center gap-1">
        {Icon && <Icon size={16} />}{value}
      </p>
      <p className="text-xs mt-1">{label}</p>
    </div>
  );
}
