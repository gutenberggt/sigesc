import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Settings, Key, Server, User, Mail, Phone, Briefcase, CheckCircle2, AlertCircle, XCircle, Loader2, ExternalLink, RefreshCw, School, Users, FileText, Shield, Copy, ChevronDown, ChevronUp, Info, Home } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ENV_LABELS = {
  homologacao: 'Homologação (Testes)',
  producao: 'Produção'
};

const STATUS_MAP = {
  not_configured: { label: 'Não Configurada', icon: XCircle, color: 'text-gray-500', bg: 'bg-gray-100' },
  pending: { label: 'Pendente', icon: AlertCircle, color: 'text-yellow-600', bg: 'bg-yellow-100' },
  configured: { label: 'Configurada', icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-100' },
};

export default function MECIntegration() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const token = localStorage.getItem('accessToken');
  const headers = { Authorization: `Bearer ${token}` };

  const [config, setConfig] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showMapping, setShowMapping] = useState(false);
  const [mappingData, setMappingData] = useState(null);
  const [loadingMapping, setLoadingMapping] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [configRes, statusRes] = await Promise.all([
        axios.get(`${API}/mec/config`, { headers }),
        axios.get(`${API}/mec/sync/status`, { headers })
      ]);
      setConfig(configRes.data);
      setSyncStatus(statusRes.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/mec/config`, config, { headers });
      await loadData();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleChange = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  };

  const loadMapping = async () => {
    setShowMapping(true);
    setLoadingMapping(true);
    try {
      const res = await axios.get(`${API}/mec/students/mapping`, { headers });
      setMappingData(res.data);
    } catch (e) { console.error(e); }
    setLoadingMapping(false);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  if (loading) {
    return (
      <Layout>
        <div className="p-8 flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
          <span className="ml-3 text-gray-500">Carregando...</span>
        </div>
      </Layout>
    );
  }

  const statusInfo = STATUS_MAP[config?.status || 'not_configured'];
  const StatusIcon = statusInfo.icon;

  return (
    <Layout>
    <div className="space-y-6" data-testid="mec-integration-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/dashboard')} className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors" data-testid="mec-home-btn">
            <Home size={18} /><span>Início</span>
          </button>
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Integração MEC Gestão Presente</h2>
            <p className="text-gray-600 mt-1">Configure o envio e consulta de dados educacionais via API do MEC</p>
          </div>
        </div>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${statusInfo.bg}`}>
          <StatusIcon className={`h-5 w-5 ${statusInfo.color}`} />
          <span className={`font-medium ${statusInfo.color}`} data-testid="mec-status">{statusInfo.label}</span>
        </div>
      </div>

      {/* Status Cards */}
      {syncStatus?.details && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center"><Users className="h-5 w-5 text-blue-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Alunos Ativos</p>
                <p className="text-xl font-bold">{syncStatus.details.students_total}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center"><FileText className="h-5 w-5 text-green-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Com CPF</p>
                <p className="text-xl font-bold text-green-600">{syncStatus.details.students_with_cpf}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center"><Shield className="h-5 w-5 text-purple-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Com NIS</p>
                <p className="text-xl font-bold text-purple-600">{syncStatus.details.students_with_nis}</p>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center"><School className="h-5 w-5 text-orange-600" /></div>
              <div>
                <p className="text-xs text-gray-500">Escolas com INEP</p>
                <p className="text-xl font-bold text-orange-600">{syncStatus.details.schools_with_inep}/{syncStatus.details.schools_total}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Guia Passo a Passo */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <button
          onClick={() => setShowGuide(!showGuide)}
          className="w-full flex items-center justify-between px-6 py-4 hover:bg-gray-50 transition-colors"
          data-testid="toggle-guide"
        >
          <div className="flex items-center gap-3">
            <Info className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-gray-900">Guia: Como Solicitar Acesso à API do MEC</span>
          </div>
          {showGuide ? <ChevronUp className="h-5 w-5 text-gray-400" /> : <ChevronDown className="h-5 w-5 text-gray-400" />}
        </button>

        {showGuide && (
          <div className="px-6 pb-6 border-t">
            <div className="mt-4 space-y-4">
              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">1</div>
                <div>
                  <h4 className="font-medium text-gray-900">Gerar Chave PGP</h4>
                  <p className="text-sm text-gray-600 mt-1">Crie um par de chaves PGP (pública e privada). A chave pública (.asc) será enviada ao MEC.</p>
                  <a href="https://www.youtube.com/watch?v=TGHoGHEICVE" target="_blank" rel="noopener noreferrer" className="text-sm text-blue-600 hover:underline flex items-center gap-1 mt-1">
                    <ExternalLink size={12} /> Tutorial em vídeo
                  </a>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">2</div>
                <div>
                  <h4 className="font-medium text-gray-900">Enviar E-mail ao MEC</h4>
                  <p className="text-sm text-gray-600 mt-1">Envie para <strong>gestaopresente@mec.gov.br</strong> com:</p>
                  <ul className="text-sm text-gray-600 mt-1 list-disc ml-4 space-y-0.5">
                    <li>Chave PGP pública (arquivo .asc)</li>
                    <li>IP do servidor que fará as consultas</li>
                    <li>Nome completo, e-mail institucional, CPF, telefone e cargo do responsável</li>
                  </ul>
                  <button onClick={() => copyToClipboard('gestaopresente@mec.gov.br')} className="text-sm text-blue-600 hover:underline flex items-center gap-1 mt-1">
                    <Copy size={12} /> Copiar e-mail
                  </button>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">3</div>
                <div>
                  <h4 className="font-medium text-gray-900">Receber Chaves do MEC</h4>
                  <p className="text-sm text-gray-600 mt-1">O MEC enviará duas chaves criptografadas: uma para homologação e outra para produção. Descriptografe-as com sua chave privada PGP.</p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm">4</div>
                <div>
                  <h4 className="font-medium text-gray-900">Configurar no SIGESC</h4>
                  <p className="text-sm text-gray-600 mt-1">Insira a chave de API recebida no formulário abaixo e selecione o ambiente.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Configuração */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
          <Settings className="h-5 w-5 text-gray-600" />
          Configuração da Integração
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Ambiente */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ambiente</label>
            <select
              value={config?.environment || 'homologacao'}
              onChange={e => handleChange('environment', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="env-select"
            >
              <option value="homologacao">Homologação (Testes)</option>
              <option value="producao">Produção</option>
            </select>
          </div>

          {/* Chave API */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Key className="inline h-4 w-4 mr-1" />Chave de API
            </label>
            <input
              type="password"
              value={config?.api_key || ''}
              onChange={e => handleChange('api_key', e.target.value)}
              placeholder="Cole a chave de API recebida do MEC"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="api-key-input"
            />
          </div>

          {/* IP do Servidor */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Server className="inline h-4 w-4 mr-1" />IP do Servidor
            </label>
            <input
              type="text"
              value={config?.server_ip || ''}
              onChange={e => handleChange('server_ip', e.target.value)}
              placeholder="Ex: 192.168.1.100"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
              data-testid="server-ip-input"
            />
          </div>

          {/* Chave PGP Pública */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Shield className="inline h-4 w-4 mr-1" />Chave PGP Pública
            </label>
            <textarea
              value={config?.pgp_public_key || ''}
              onChange={e => handleChange('pgp_public_key', e.target.value)}
              placeholder="Cole sua chave PGP pública aqui (conteúdo do arquivo .asc)"
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 font-mono"
              data-testid="pgp-key-input"
            />
          </div>
        </div>

        {/* Dados do Responsável */}
        <h4 className="text-sm font-semibold text-gray-700 mt-6 mb-4">Dados do Responsável pela Integração</h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 mb-1"><User className="inline h-3 w-3 mr-1" />Nome Completo</label>
            <input type="text" value={config?.responsible_name || ''} onChange={e => handleChange('responsible_name', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-name" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Mail className="inline h-3 w-3 mr-1" />E-mail Institucional</label>
            <input type="email" value={config?.responsible_email || ''} onChange={e => handleChange('responsible_email', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-email" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">CPF</label>
            <input type="text" value={config?.responsible_cpf || ''} onChange={e => handleChange('responsible_cpf', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-cpf" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Phone className="inline h-3 w-3 mr-1" />Telefone</label>
            <input type="text" value={config?.responsible_phone || ''} onChange={e => handleChange('responsible_phone', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-phone" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1"><Briefcase className="inline h-3 w-3 mr-1" />Cargo</label>
            <input type="text" value={config?.responsible_role || ''} onChange={e => handleChange('responsible_role', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" data-testid="resp-role" />
          </div>
        </div>

        {/* Botão Salvar */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
            data-testid="save-config-btn"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Salvar Configuração
          </button>
        </div>
      </div>

      {/* Links Úteis */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Links Úteis</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <a href="https://api-cmde.hmg.gestaopresente.mec.gov.br/v1/documentation" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 border rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-colors">
            <ExternalLink className="h-4 w-4 text-blue-600" />
            <div>
              <p className="font-medium text-sm text-gray-900">Swagger - Homologação</p>
              <p className="text-xs text-gray-500">Documentação interativa da API (ambiente de testes)</p>
            </div>
          </a>
          <a href="https://api-cmde.gestaopresente.mec.gov.br/v1/documentation" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 border rounded-lg hover:bg-green-50 hover:border-green-300 transition-colors">
            <ExternalLink className="h-4 w-4 text-green-600" />
            <div>
              <p className="font-medium text-sm text-gray-900">Swagger - Produção</p>
              <p className="text-xs text-gray-500">Documentação interativa da API (ambiente de produção)</p>
            </div>
          </a>
        </div>
      </div>

      {/* Mapeamento de Dados */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="px-6 py-4 flex items-center justify-between border-b">
          <h3 className="text-lg font-semibold text-gray-900">Mapeamento de Dados SIGESC → MEC</h3>
          <button
            onClick={loadMapping}
            disabled={loadingMapping}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 flex items-center gap-2 transition-colors"
            data-testid="load-mapping-btn"
          >
            {loadingMapping ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Verificar Dados
          </button>
        </div>

        {showMapping && mappingData && (
          <div>
            <div className="px-6 py-3 bg-gray-50 border-b flex items-center gap-6 text-sm">
              <span className="text-gray-600">Total: <strong>{mappingData.total}</strong></span>
              <span className="text-green-600">Prontos: <strong>{mappingData.ready_count}</strong></span>
              <span className="text-red-600">Incompletos: <strong>{mappingData.not_ready_count}</strong></span>
            </div>

            {mappingData.not_ready_count > 0 && (
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="text-left px-6 py-2 text-xs text-gray-500 uppercase">Aluno</th>
                      <th className="text-left px-4 py-2 text-xs text-gray-500 uppercase">Escola</th>
                      <th className="text-left px-4 py-2 text-xs text-gray-500 uppercase">Campos Faltantes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {mappingData.students.filter(s => !s.ready).slice(0, 50).map(s => (
                      <tr key={s.id} className="hover:bg-gray-50">
                        <td className="px-6 py-2 font-medium text-gray-900">{s.full_name}</td>
                        <td className="px-4 py-2 text-gray-600">{s.school_name}</td>
                        <td className="px-4 py-2">
                          {s.missing_fields.map(f => (
                            <span key={f} className="inline-block px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs mr-1">{f}</span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {showMapping && loadingMapping && (
          <div className="p-8 flex items-center justify-center">
            <Loader2 className="h-6 w-6 text-blue-500 animate-spin" />
            <span className="ml-3 text-gray-500">Verificando dados...</span>
          </div>
        )}
      </div>
    </div>
    </Layout>
  );
}
