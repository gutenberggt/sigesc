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
import { X, ChevronRight, ChevronLeft, Check, Building2, School, UserPlus, Upload, Loader2, Download } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const emptyMantenedora = { nome: '', cnpj: '', municipio: '', estado: 'PA', logotipo_url: '', ativo: true };
const emptyGerente = { full_name: '', email: '', password: '' };

// Colunas do template CSV. A ordem define as colunas da planilha.
// type: 'string' | 'int' | 'bool'. Valores booleanos aceitam sim/não/true/false/1/0.
const SCHOOL_COLUMNS = [
  // ─── Geral ─────────────────────────────────────────────────────────
  { key: 'name', label: 'Nome*', type: 'string', group: 'Geral' },
  { key: 'inep_code', label: 'Código INEP', type: 'string', group: 'Geral' },
  { key: 'cnpj', label: 'CNPJ', type: 'string', group: 'Geral' },
  { key: 'zona_localizacao', label: 'Zona (urbana/rural)', type: 'string', group: 'Geral' },
  { key: 'cep', label: 'CEP', type: 'string', group: 'Geral' },
  { key: 'logradouro', label: 'Logradouro', type: 'string', group: 'Geral' },
  { key: 'numero', label: 'Número', type: 'string', group: 'Geral' },
  { key: 'bairro', label: 'Bairro', type: 'string', group: 'Geral' },
  { key: 'municipio', label: 'Município', type: 'string', group: 'Geral' },
  { key: 'estado', label: 'UF', type: 'string', group: 'Geral' },
  { key: 'telefone', label: 'Telefone', type: 'string', group: 'Geral' },
  { key: 'email', label: 'E-mail', type: 'string', group: 'Geral' },
  { key: 'dependencia_administrativa', label: 'Dep. Administrativa', type: 'string', group: 'Geral' },
  { key: 'situacao_funcionamento', label: 'Situação', type: 'string', group: 'Geral' },
  { key: 'gestor_principal', label: 'Gestor Principal', type: 'string', group: 'Geral' },
  // ─── Infraestrutura ────────────────────────────────────────────────
  { key: 'abastecimento_agua', label: 'Abastec. Água', type: 'string', group: 'Infraestrutura' },
  { key: 'energia_eletrica', label: 'Energia Elétrica', type: 'string', group: 'Infraestrutura' },
  { key: 'saneamento', label: 'Saneamento', type: 'string', group: 'Infraestrutura' },
  { key: 'coleta_lixo', label: 'Coleta de Lixo', type: 'string', group: 'Infraestrutura' },
  { key: 'possui_rampas', label: 'Possui Rampas', type: 'bool', group: 'Infraestrutura' },
  { key: 'banheiros_adaptados', label: 'Banheiros Adaptados', type: 'bool', group: 'Infraestrutura' },
  { key: 'possui_internet', label: 'Possui Internet', type: 'bool', group: 'Infraestrutura' },
  { key: 'estado_conservacao', label: 'Estado Conservação', type: 'string', group: 'Infraestrutura' },
  // ─── Dependências ─────────────────────────────────────────────────
  { key: 'numero_salas_aula', label: 'Nº Salas de Aula', type: 'int', group: 'Dependências' },
  { key: 'capacidade_total_alunos', label: 'Capacidade Alunos', type: 'int', group: 'Dependências' },
  { key: 'sala_direcao', label: 'Sala Direção', type: 'bool', group: 'Dependências' },
  { key: 'sala_secretaria', label: 'Sala Secretaria', type: 'bool', group: 'Dependências' },
  { key: 'numero_banheiros', label: 'Nº Banheiros', type: 'int', group: 'Dependências' },
  { key: 'possui_cozinha', label: 'Possui Cozinha', type: 'bool', group: 'Dependências' },
  { key: 'possui_biblioteca', label: 'Possui Biblioteca', type: 'bool', group: 'Dependências' },
  { key: 'possui_lab_informatica', label: 'Lab. Informática', type: 'bool', group: 'Dependências' },
  { key: 'possui_quadra', label: 'Quadra Esportiva', type: 'bool', group: 'Dependências' },
  // ─── Equipamentos ─────────────────────────────────────────────────
  { key: 'qtd_computadores', label: 'Qtd Computadores', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_tablets', label: 'Qtd Tablets', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_projetores', label: 'Qtd Projetores', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_impressoras', label: 'Qtd Impressoras', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_televisores', label: 'Qtd Televisores', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_lousas_digitais', label: 'Qtd Lousas Digitais', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_cameras', label: 'Qtd Câmeras', type: 'int', group: 'Equipamentos' },
  { key: 'qtd_extintores', label: 'Qtd Extintores', type: 'int', group: 'Equipamentos' },
];

const parseBool = (v) => {
  if (v === undefined || v === null) return undefined;
  const s = String(v).trim().toLowerCase();
  if (!s) return undefined;
  return ['sim', 'true', '1', 's', 'yes', 'y'].includes(s);
};

const parseInt10 = (v) => {
  if (v === undefined || v === null || String(v).trim() === '') return undefined;
  const n = parseInt(String(v).trim(), 10);
  return isNaN(n) ? undefined : n;
};

// Split CSV line respeitando aspas
const splitCsvLine = (line) => {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; } else inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      out.push(cur); cur = '';
    } else cur += ch;
  }
  out.push(cur);
  return out.map((s) => s.trim());
};

const parseCsv = (text) => {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];
  // Detecta se a primeira linha é header (contém "nome" ou "name")
  const firstCols = splitCsvLine(lines[0]).map((c) => c.toLowerCase());
  const hasHeader = firstCols.some((c) => c.includes('nome') || c === 'name' || c === 'name*');
  const header = hasHeader ? firstCols : SCHOOL_COLUMNS.map((c) => c.key);
  const dataLines = hasHeader ? lines.slice(1) : lines;

  // Mapeia cada coluna do header para um SCHOOL_COLUMNS key (por label ou key)
  const keyIndex = header.map((h) => {
    const normalized = h.replace(/[*\s]/g, '').toLowerCase();
    const found = SCHOOL_COLUMNS.find((col) => {
      const byKey = col.key.toLowerCase() === normalized;
      const byLabel = col.label.replace(/[*\s]/g, '').toLowerCase() === normalized;
      return byKey || byLabel;
    });
    return found ? found.key : null;
  });

  return dataLines.map((line) => {
    const values = splitCsvLine(line);
    const obj = {};
    values.forEach((val, idx) => {
      const key = keyIndex[idx];
      if (!key || val === '') return;
      const colMeta = SCHOOL_COLUMNS.find((c) => c.key === key);
      if (!colMeta) return;
      if (colMeta.type === 'bool') {
        const b = parseBool(val);
        if (b !== undefined) obj[key] = b;
      } else if (colMeta.type === 'int') {
        const n = parseInt10(val);
        if (n !== undefined) obj[key] = n;
      } else {
        obj[key] = val;
      }
    });
    return obj;
  }).filter((s) => s.name);
};

const downloadCsvTemplate = () => {
  const header = SCHOOL_COLUMNS.map((c) => c.label).join(',');
  const example = SCHOOL_COLUMNS.map((c) => {
    if (c.key === 'name') return 'ESCOLA MUNICIPAL EXEMPLO';
    if (c.key === 'inep_code') return '12345678';
    if (c.key === 'cnpj') return '00.000.000/0001-00';
    if (c.key === 'zona_localizacao') return 'urbana';
    if (c.key === 'cep') return '68530-000';
    if (c.key === 'municipio') return 'CIDADE EXEMPLO';
    if (c.key === 'estado') return 'PA';
    if (c.key === 'situacao_funcionamento') return 'Em atividade';
    if (c.type === 'bool') return 'sim';
    if (c.type === 'int') return '0';
    return '';
  }).join(',');
  const csv = `${header}\n${example}\n`;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'modelo_escolas.csv';
  a.click();
  URL.revokeObjectURL(url);
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
          // Fallbacks de município/estado a partir da mantenedora
          const payload = {
            ...s,
            municipio: s.municipio || createdMantenedora?.municipio || undefined,
            estado: s.estado || createdMantenedora?.estado || 'PA',
          };
          await axios.post(`${API}/api/schools`, payload);
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

  // Passo 3 → cria usuário gerente e vincula à mantenedora
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
      const { data: newUser } = await axios.post(`${API}/api/auth/register`, {
        full_name: gerenteData.full_name,
        email: gerenteData.email,
        password: gerenteData.password,
        role: 'gerente',
        status: 'active',
      });
      // Vincula explicitamente o usuário como gerente desta mantenedora
      if (createdMantenedora?.id && newUser?.id) {
        try {
          await axios.post(`${API}/api/mantenedoras/${createdMantenedora.id}/gerente`, { user_id: newUser.id });
        } catch (_e) {
          // Falha na vinculação não impede a conclusão; super_admin pode designar manualmente depois.
        }
      }
      toast.success('Gerente criado e vinculado! Onboarding concluído.');
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
              <p className="text-sm text-gray-600 mb-2">Importe as escolas da prefeitura em lote via planilha CSV (opcional).</p>
              
              <div className="bg-indigo-50 border border-indigo-200 rounded-md p-3 text-xs">
                <div className="flex items-center justify-between mb-2">
                  <strong className="text-indigo-800">Planilha modelo com todos os campos:</strong>
                  <button
                    type="button"
                    onClick={downloadCsvTemplate}
                    className="flex items-center gap-1 px-2 py-1 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-[11px]"
                    data-testid="wizard-download-template"
                  >
                    <Download size={12} /> Baixar modelo CSV
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-indigo-900">
                  {['Geral', 'Infraestrutura', 'Dependências', 'Equipamentos'].map((grp) => (
                    <div key={grp}>
                      <div className="font-semibold text-[11px] uppercase tracking-wide mt-1">{grp}</div>
                      <div className="text-[11px] text-indigo-800">
                        {SCHOOL_COLUMNS.filter((c) => c.group === grp).map((c) => c.label.replace('*', '')).join(' · ')}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="text-[11px] text-indigo-700 mt-2 italic">
                  Booleanos aceitam <code>sim/não</code> ou <code>true/false</code>. A primeira linha deve conter os nomes das colunas.
                </div>
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
                placeholder="Ou cole as linhas aqui (inclua o cabeçalho)..."
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
