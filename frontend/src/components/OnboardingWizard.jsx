/**
 * OnboardingWizard — Wizard de 3 passos para cadastrar uma nova Mantenedora.
 *   Passo 1: Dados da prefeitura (nome, cnpj, município, estado, brasão).
 *   Passo 2: Importar escolas via planilha CSV (opcional).
 *   Passo 3: Criar usuário gerente (email, senha, nome) vinculado à mantenedora criada.
 *
 * Props:
 *  - isOpen       : bool
 *  - onClose      : () => void
 *  - onComplete   : (mantenedora) => void  — chamado ao concluir todos os passos
 */
import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, ChevronRight, ChevronLeft, Check, Building2, School, UserPlus, Upload, Loader2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const emptyMantenedora = { nome: '', cnpj: '', municipio: '', estado: 'PA', logotipo_url: '', ativo: true };
const emptyGerente = { full_name: '', email: '', password: '' };

const parseCsv = (text) => {
  // CSV simples: uma escola por linha; colunas: nome, inep, municipio (ou apenas nome)
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const cols = line.split(',').map((c) => c.trim());
      return { name: cols[0] || '', codigo_inep: cols[1] || '', municipio: cols[2] || '' };
    })
    .filter((s) => s.name && s.name.toLowerCase() !== 'nome');
};

export const OnboardingWizard = ({ isOpen, onClose, onComplete }) => {
  const [step, setStep] = useState(1);
  const [mantenedoraData, setMantenedoraData] = useState(emptyMantenedora);
  const [createdMantenedora, setCreatedMantenedora] = useState(null);
  const [csvText, setCsvText] = useState('');
  const [parsedSchools, setParsedSchools] = useState([]);
  const [skipSchools, setSkipSchools] = useState(false);
  const [gerenteData, setGerenteData] = useState(emptyGerente);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const close = () => {
    setStep(1);
    setMantenedoraData(emptyMantenedora);
    setCreatedMantenedora(null);
    setCsvText('');
    setParsedSchools([]);
    setSkipSchools(false);
    setGerenteData(emptyGerente);
    onClose();
  };

  // Passo 1 → cria mantenedora
  const handleStep1 = async () => {
    if (!mantenedoraData.nome.trim()) {
      toast.error('Informe o nome da mantenedora');
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await axios.post(`${API}/api/mantenedoras`, mantenedoraData);
      setCreatedMantenedora(data);
      // Seleciona automaticamente o novo tenant para os próximos passos
      localStorage.setItem('activeMantenedoraId', data.id);
      toast.success('Mantenedora criada!');
      setStep(2);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao criar mantenedora');
    } finally {
      setSubmitting(false);
    }
  };

  // Passo 2 → importa escolas (opcional)
  const handleStep2 = async () => {
    if (skipSchools || parsedSchools.length === 0) {
      setStep(3);
      return;
    }
    setSubmitting(true);
    try {
      let created = 0;
      let failed = 0;
      for (const s of parsedSchools) {
        try {
          await axios.post(`${API}/api/schools`, {
            name: s.name,
            codigo_inep: s.codigo_inep || undefined,
            municipio: s.municipio || createdMantenedora?.municipio || undefined,
            estado: createdMantenedora?.estado || 'PA',
          });
          created++;
        } catch (_err) {
          failed++;
        }
      }
      toast.success(`${created} escola(s) criada(s)${failed > 0 ? `. ${failed} falharam.` : ''}`);
      setStep(3);
    } catch (e) {
      toast.error('Erro ao importar escolas');
    } finally {
      setSubmitting(false);
    }
  };

  // Passo 3 → cria usuário gerente
  const handleStep3 = async () => {
    if (!gerenteData.full_name || !gerenteData.email || !gerenteData.password) {
      toast.error('Preencha todos os campos do gerente');
      return;
    }
    if (gerenteData.password.length < 6) {
      toast.error('Senha deve ter pelo menos 6 caracteres');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/api/auth/register`, {
        full_name: gerenteData.full_name,
        email: gerenteData.email,
        password: gerenteData.password,
        role: 'gerente',
        status: 'active',
      });
      toast.success('Gerente criado! Onboarding concluído.');
      if (onComplete) onComplete(createdMantenedora);
      close();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Erro ao criar gerente');
    } finally {
      setSubmitting(false);
    }
  };

  const onCsvFile = async (file) => {
    if (!file) return;
    const text = await file.text();
    setCsvText(text);
    const schools = parseCsv(text);
    setParsedSchools(schools);
    if (schools.length === 0) toast.warning('Nenhuma escola válida detectada no arquivo');
    else toast.success(`${schools.length} escola(s) detectada(s)`);
  };

  const StepHeader = () => (
    <div className="flex items-center justify-between mb-4">
      {[
        { n: 1, label: 'Mantenedora', icon: Building2 },
        { n: 2, label: 'Escolas', icon: School },
        { n: 3, label: 'Gerente', icon: UserPlus },
      ].map(({ n, label, icon: Icon }, idx, arr) => (
        <div key={n} className="flex items-center flex-1">
          <div className={`flex items-center gap-2 ${step === n ? 'text-indigo-700 font-semibold' : step > n ? 'text-green-600' : 'text-gray-400'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${step === n ? 'border-indigo-600 bg-indigo-50' : step > n ? 'border-green-500 bg-green-50' : 'border-gray-300 bg-white'}`}>
              {step > n ? <Check size={14} /> : <Icon size={14} />}
            </div>
            <span className="text-xs uppercase tracking-wide">{label}</span>
          </div>
          {idx < arr.length - 1 && <div className={`flex-1 h-0.5 mx-3 ${step > n ? 'bg-green-500' : 'bg-gray-200'}`} />}
        </div>
      ))}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" data-testid="onboarding-wizard">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-800">Nova Mantenedora — Onboarding</h2>
          <button onClick={close} className="text-gray-400 hover:text-gray-600" data-testid="wizard-close">
            <X size={20} />
          </button>
        </div>

        <div className="p-5">
          <StepHeader />

          {/* Passo 1 */}
          {step === 1 && (
            <div className="space-y-3" data-testid="wizard-step-1">
              <p className="text-sm text-gray-600 mb-3">Dados básicos da prefeitura/mantenedora.</p>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">Nome da Mantenedora *</label>
                <input
                  type="text"
                  value={mantenedoraData.nome}
                  onChange={(e) => setMantenedoraData({ ...mantenedoraData, nome: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                  placeholder="Ex: Prefeitura Municipal de Cidade"
                  data-testid="wizard-mantenedora-nome"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-700 block mb-1">CNPJ</label>
                  <input type="text" value={mantenedoraData.cnpj} onChange={(e) => setMantenedoraData({ ...mantenedoraData, cnpj: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-700 block mb-1">Estado</label>
                  <input type="text" value={mantenedoraData.estado} onChange={(e) => setMantenedoraData({ ...mantenedoraData, estado: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" maxLength={2} />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">Município</label>
                <input type="text" value={mantenedoraData.municipio} onChange={(e) => setMantenedoraData({ ...mantenedoraData, municipio: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">URL do Brasão/Logotipo (opcional)</label>
                <input type="text" value={mantenedoraData.logotipo_url} onChange={(e) => setMantenedoraData({ ...mantenedoraData, logotipo_url: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" placeholder="https://..." />
              </div>
            </div>
          )}

          {/* Passo 2 */}
          {step === 2 && (
            <div className="space-y-3" data-testid="wizard-step-2">
              <p className="text-sm text-gray-600 mb-2">Importe a lista de escolas via arquivo CSV (opcional).</p>
              <div className="bg-gray-50 border border-gray-200 rounded-md p-3 text-xs text-gray-600">
                <strong>Formato esperado:</strong> Uma linha por escola, colunas <code>nome, inep, município</code>.<br />
                <strong>Exemplo:</strong><br />
                <code className="block mt-1 font-mono">ESCOLA MUNICIPAL EXEMPLO,12345678,Cidade</code>
              </div>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 px-3 py-2 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md cursor-pointer hover:bg-indigo-100 text-sm" data-testid="wizard-csv-label">
                  <Upload size={14} />
                  Escolher arquivo CSV
                  <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => onCsvFile(e.target.files?.[0])} data-testid="wizard-csv-input" />
                </label>
                {parsedSchools.length > 0 && (
                  <span className="text-xs text-green-700 font-medium">{parsedSchools.length} escola(s) prontas para criar</span>
                )}
              </div>
              <textarea
                placeholder="Ou cole as linhas aqui..."
                value={csvText}
                onChange={(e) => {
                  setCsvText(e.target.value);
                  setParsedSchools(parseCsv(e.target.value));
                }}
                className="w-full h-28 px-3 py-2 border border-gray-300 rounded-md text-sm font-mono"
                data-testid="wizard-csv-textarea"
              />
              <label className="flex items-center gap-2 text-sm text-gray-600 mt-2">
                <input type="checkbox" checked={skipSchools} onChange={(e) => setSkipSchools(e.target.checked)} data-testid="wizard-skip-schools" />
                Pular importação de escolas (criar depois manualmente)
              </label>
            </div>
          )}

          {/* Passo 3 */}
          {step === 3 && (
            <div className="space-y-3" data-testid="wizard-step-3">
              <p className="text-sm text-gray-600 mb-2">Crie o usuário <strong>Gerente</strong> responsável por esta mantenedora.</p>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">Nome completo *</label>
                <input type="text" value={gerenteData.full_name} onChange={(e) => setGerenteData({ ...gerenteData, full_name: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" data-testid="wizard-gerente-nome" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">E-mail *</label>
                <input type="email" value={gerenteData.email} onChange={(e) => setGerenteData({ ...gerenteData, email: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" data-testid="wizard-gerente-email" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 block mb-1">Senha inicial * (mín. 6 caracteres)</label>
                <input type="password" value={gerenteData.password} onChange={(e) => setGerenteData({ ...gerenteData, password: e.target.value })} className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm" data-testid="wizard-gerente-password" />
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-700">
                O gerente terá permissões completas dentro desta mantenedora (equivalentes ao admin local), mas não acessará dados de outras mantenedoras.
              </div>
            </div>
          )}
        </div>

        {/* Footer com botões */}
        <div className="flex items-center justify-between p-5 border-t border-gray-100 bg-gray-50">
          <button
            onClick={step === 1 ? close : () => setStep(step - 1)}
            disabled={submitting}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50"
            data-testid="wizard-back"
          >
            <ChevronLeft size={14} />
            {step === 1 ? 'Cancelar' : 'Voltar'}
          </button>

          <button
            onClick={step === 1 ? handleStep1 : step === 2 ? handleStep2 : handleStep3}
            disabled={submitting}
            className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 text-sm font-medium disabled:opacity-60"
            data-testid="wizard-next"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            {step === 3 ? 'Concluir' : 'Avançar'}
            {step < 3 && <ChevronRight size={14} />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
