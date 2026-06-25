import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { schoolsAPI, classesAPI, schoolTransferAPI } from '@/services/api';
import {
  ArrowLeft, ArrowRight, Building2, CheckCircle2, AlertTriangle, XCircle,
  ShieldAlert, FileCheck2, Loader2, Home, Clock,
} from 'lucide-react';

const STEPS = ['Origem', 'Seleção', 'Simulação', 'Confirmação', 'Resultado'];

function StepBar({ step }) {
  return (
    <div className="flex items-center gap-2" data-testid="wizard-stepbar">
      {STEPS.map((s, i) => (
        <div key={s} className="flex items-center gap-2">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
            i === step ? 'bg-blue-600 text-white' : i < step ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
          }`}>
            <span className="w-5 h-5 inline-flex items-center justify-center rounded-full bg-white/30 text-xs">{i + 1}</span>
            {s}
          </div>
          {i < STEPS.length - 1 && <span className="text-gray-300">—</span>}
        </div>
      ))}
    </div>
  );
}

export default function SchoolTransferWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [originId, setOriginId] = useState('');
  const [destId, setDestId] = useState('');
  const [mode, setMode] = useState('whole'); // whole | specific
  const [selectedClassIds, setSelectedClassIds] = useState([]);

  const [dryRun, setDryRun] = useState(null);
  const [loadingDry, setLoadingDry] = useState(false);

  const [password, setPassword] = useState('');
  const [reason, setReason] = useState('');
  const [phrase, setPhrase] = useState('');
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    schoolsAPI.getAll().then(setSchools).catch(() => setSchools([]));
    classesAPI.getAll().then(setClasses).catch(() => setClasses([]));
  }, []);

  const origin = schools.find((s) => s.id === originId);
  const destinations = useMemo(() => {
    if (!origin) return [];
    return schools.filter((s) =>
      s.id !== originId &&
      s.status === 'active' &&
      s.mantenedora_id && s.mantenedora_id === origin.mantenedora_id,
    );
  }, [schools, origin, originId]);

  const originClasses = useMemo(
    () => classes.filter((c) => c.school_id === originId),
    [classes, originId],
  );

  const effectiveClassIds = mode === 'whole' ? originClasses.map((c) => c.id) : selectedClassIds;

  const runDryRun = async () => {
    if (effectiveClassIds.length === 0) { toast.error('Selecione ao menos uma turma'); return; }
    setLoadingDry(true);
    try {
      const d = await schoolTransferAPI.dryRun({
        origin_school_id: originId,
        destination_school_id: destId,
        class_ids: effectiveClassIds,
      });
      setDryRun(d);
      setStep(2);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Falha na simulação (Dry Run)');
    } finally {
      setLoadingDry(false);
    }
  };

  const doExecute = async () => {
    setExecuting(true);
    try {
      const r = await schoolTransferAPI.execute({
        dry_run_token: dryRun.dry_run_token,
        password, reason, confirmation_text: phrase,
      });
      setResult(r);
      setStep(4);
      toast.success(`Transferência executada: ${r.protocol}`);
    } catch (e) {
      const det = e.response?.data?.detail;
      toast.error(typeof det === 'string' ? det : 'Falha ao executar a transferência');
    } finally {
      setExecuting(false);
    }
  };

  const counts = dryRun?.counts || {};

  return (
    <Layout>
      <div className="space-y-6 max-w-4xl">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/admin/transferencias')} className="flex items-center gap-2 text-gray-600 hover:text-gray-900" data-testid="wizard-back-panel">
            <Home size={18} /> Painel
          </button>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="text-blue-600" /> Nova Transferência Institucional
          </h1>
        </div>

        <StepBar step={step} />

        {/* STEP 1 — ORIGEM */}
        {step === 0 && (
          <Card>
            <CardHeader><CardTitle className="text-base">Etapa 1 — Escolas</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Escola de origem (em encerramento)</label>
                  <select value={originId} onChange={(e) => { setOriginId(e.target.value); setDestId(''); setSelectedClassIds([]); }}
                    className="w-full px-3 py-2 border rounded-lg" data-testid="wizard-origin-select">
                    <option value="">Selecione</option>
                    {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Escola de destino</label>
                  <select value={destId} onChange={(e) => setDestId(e.target.value)} disabled={!originId}
                    className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-100" data-testid="wizard-dest-select">
                    <option value="">Selecione</option>
                    {destinations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                  {originId && destinations.length === 0 && (
                    <p className="text-xs text-amber-600 mt-1">Nenhuma escola ativa na mesma mantenedora.</p>
                  )}
                </div>
              </div>
              {originId && (
                <div className="grid grid-cols-2 gap-3 pt-2" data-testid="wizard-origin-summary">
                  <div className="bg-blue-50 p-3 rounded-lg text-center">
                    <p className="text-2xl font-bold text-blue-700">{originClasses.length}</p>
                    <p className="text-xs text-blue-600">Turmas na origem</p>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg text-center">
                    <p className="text-sm text-gray-600">Alunos e matrículas serão detalhados na simulação (Dry Run).</p>
                  </div>
                </div>
              )}
              <div className="flex justify-end">
                <Button disabled={!originId || !destId} onClick={() => setStep(1)} data-testid="wizard-next-1">
                  Avançar <ArrowRight size={16} className="ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP 2 — SELEÇÃO */}
        {step === 1 && (
          <Card>
            <CardHeader><CardTitle className="text-base">Etapa 2 — Seleção de turmas</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <button onClick={() => setMode('whole')} className={`flex-1 p-3 rounded-lg border text-left ${mode === 'whole' ? 'border-blue-600 bg-blue-50' : 'border-gray-200'}`} data-testid="wizard-mode-whole">
                  <p className="font-medium">Escola inteira</p>
                  <p className="text-xs text-gray-500">Transferir todas as {originClasses.length} turmas (encerra a escola origem).</p>
                </button>
                <button onClick={() => setMode('specific')} className={`flex-1 p-3 rounded-lg border text-left ${mode === 'specific' ? 'border-blue-600 bg-blue-50' : 'border-gray-200'}`} data-testid="wizard-mode-specific">
                  <p className="font-medium">Turmas específicas</p>
                  <p className="text-xs text-gray-500">Escolher quais turmas transferir.</p>
                </button>
              </div>

              {mode === 'specific' && (
                <div className="border rounded-lg max-h-64 overflow-y-auto divide-y" data-testid="wizard-class-list">
                  {originClasses.map((c) => (
                    <label key={c.id} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                      <input type="checkbox" checked={selectedClassIds.includes(c.id)}
                        onChange={(e) => setSelectedClassIds((prev) => e.target.checked ? [...prev, c.id] : prev.filter((x) => x !== c.id))} />
                      <span className="text-sm">{c.name} <span className="text-gray-400">· {c.academic_year}</span></span>
                    </label>
                  ))}
                  {originClasses.length === 0 && <p className="p-3 text-sm text-gray-500">Sem turmas na origem.</p>}
                </div>
              )}

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                <p className="font-medium flex items-center gap-1"><ShieldAlert size={15} /> Impacto previsto</p>
                <p className="text-xs mt-1">Serão movidos: {effectiveClassIds.length} turma(s) e todo o histórico vinculado (alunos, matrículas, frequência, notas, conteúdos, AEE e Bolsa Família). Os números exatos aparecem na simulação.</p>
              </div>

              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(0)}><ArrowLeft size={16} className="mr-1" /> Voltar</Button>
                <Button disabled={effectiveClassIds.length === 0 || loadingDry} onClick={runDryRun} data-testid="wizard-run-dryrun">
                  {loadingDry ? <Loader2 size={16} className="mr-1 animate-spin" /> : <FileCheck2 size={16} className="mr-1" />}
                  Simular (Dry Run)
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP 3 — DRY RUN */}
        {step === 2 && dryRun && (
          <Card>
            <CardHeader><CardTitle className="text-base">Etapa 3 — Simulação (Dry Run)</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="wizard-dryrun-counts">
                {[['Turmas', counts.classes], ['Alunos', counts.students_distinct ?? counts.students], ['Matrículas', counts.enrollments], ['Frequência', counts.attendance], ['Notas', counts.grades], ['Conteúdos', counts.content_entries], ['AEE (planos)', counts.planos_aee], ['Bolsa Família', counts.bolsa_familia_tracking]].map(([k, v]) => (
                  <div key={k} className="bg-gray-50 p-3 rounded-lg text-center">
                    <p className="text-xl font-bold text-gray-800">{v ?? 0}</p>
                    <p className="text-[11px] text-gray-500">{k}</p>
                  </div>
                ))}
              </div>

              <div className="space-y-1.5">
                {dryRun.validations.map((v) => (
                  <div key={v.code} className="flex items-center gap-2 text-sm">
                    {v.ok ? <CheckCircle2 size={16} className="text-green-600" />
                      : v.blocking ? <XCircle size={16} className="text-red-600" />
                      : <AlertTriangle size={16} className="text-amber-500" />}
                    <span className={v.ok ? 'text-gray-700' : v.blocking ? 'text-red-700 font-medium' : 'text-amber-700'}>{v.label}</span>
                  </div>
                ))}
              </div>

              {!dryRun.can_execute && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700" data-testid="wizard-blocked">
                  Há bloqueios que impedem a execução. Resolva-os e refaça a simulação.
                </div>
              )}

              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(1)}><ArrowLeft size={16} className="mr-1" /> Voltar</Button>
                <Button disabled={!dryRun.can_execute} onClick={() => setStep(3)} data-testid="wizard-next-3">
                  Avançar para confirmação <ArrowRight size={16} className="ml-1" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP 4 — CONFIRMAÇÃO FORTE */}
        {step === 3 && dryRun && (
          <Card>
            <CardHeader><CardTitle className="text-base text-red-700 flex items-center gap-2"><ShieldAlert size={18} /> Etapa 4 — Confirmação forte</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm" data-testid="wizard-summary">
                <p>Você está transferindo:</p>
                <ul className="list-disc ml-5 mt-1">
                  <li><strong>{counts.classes}</strong> turma(s)</li>
                  <li><strong>{counts.students_distinct ?? counts.students}</strong> aluno(s)</li>
                  <li><strong>{counts.enrollments ?? 0}</strong> matrícula(s)</li>
                </ul>
                <p className="mt-2">Da escola <strong>{dryRun.origin?.name}</strong> para <strong>{dryRun.destination?.name}</strong>.</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Justificativa (mín. 10 caracteres)</label>
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                  className="w-full px-3 py-2 border rounded-lg" data-testid="wizard-reason" placeholder="Ex.: Encerramento da unidade por reordenamento da rede." />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Senha (re-autenticação)</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg" data-testid="wizard-password" autoComplete="current-password" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Digite exatamente: <span className="font-mono text-red-700">{dryRun.confirmation_phrase}</span>
                </label>
                <input value={phrase} onChange={(e) => setPhrase(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg" data-testid="wizard-phrase" />
              </div>

              <div className="flex justify-between">
                <Button variant="outline" onClick={() => setStep(2)}><ArrowLeft size={16} className="mr-1" /> Voltar</Button>
                <Button variant="destructive"
                  disabled={executing || reason.trim().length < 10 || !password || phrase.trim() !== dryRun.confirmation_phrase}
                  onClick={doExecute} data-testid="wizard-execute">
                  {executing ? <Loader2 size={16} className="mr-1 animate-spin" /> : <ShieldAlert size={16} className="mr-1" />}
                  Executar transferência
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STEP 5 — RESULTADO */}
        {step === 4 && result && (
          <Card>
            <CardContent className="p-6 text-center space-y-4" data-testid="wizard-result">
              <CheckCircle2 size={48} className="mx-auto text-green-600" />
              <h2 className="text-xl font-bold">Transferência concluída</h2>
              <div className="inline-block text-left bg-gray-50 rounded-lg p-4 text-sm">
                <p><strong>Protocolo:</strong> <span className="font-mono">{result.protocol}</span></p>
                <p><strong>Data/hora:</strong> {new Date(result.executed_at).toLocaleString('pt-BR')}</p>
                <p><strong>Turmas movidas:</strong> {result.modified_counts?.classes}</p>
                <p><strong>Alunos movidos:</strong> {result.students_moved}</p>
                <p><strong>Escola origem encerrada:</strong> {result.origin_closed ? 'Sim' : 'Não'}</p>
                <p className="flex items-center gap-1 text-amber-700 mt-2">
                  <Clock size={14} /> Reversível por 7 dias (ou até a 1ª emissão de documento oficial).
                </p>
              </div>
              <div className="flex justify-center gap-2">
                <Button variant="outline" onClick={() => navigate('/admin/transferencias')} data-testid="wizard-goto-panel">Ir ao painel</Button>
                <Button onClick={() => window.location.reload()} data-testid="wizard-new">Nova transferência</Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
