/**
 * Portal Público de Verificação — /verificar e /verificar/:code
 *
 * Página SEM autenticação. Qualquer pessoa (vereador, conselheiro, cidadão)
 * pode validar um documento emitido pelo SIGESC digitando o código
 * `SIGESC-XXXX-XXXX` ou escaneando o QR code do PDF.
 *
 * LGPD-safe: o endpoint público `/api/public/verify/{code}` retorna APENAS
 * metadata mínima (tipo, data emissão, emissor, escopo) + status de
 * integridade. Zero dados operacionais são expostos.
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ShieldCheck, ShieldAlert, ShieldX, Search, Loader2, Lock, Hash,
  FileText, Calendar, Building2, AlertTriangle,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Normalização client-side idêntica à do backend — evita chamada quando
// o código é sintaticamente inválido.
function normalizeClient(raw) {
  if (!raw) return null;
  const cleaned = raw.toUpperCase().replace(/[\s-]/g, '').replace(/^SIGESC/, '');
  if (!/^[A-Z2-9]{8}$/.test(cleaned)) return null;
  return `SIGESC-${cleaned.slice(0, 4)}-${cleaned.slice(4)}`;
}

const STATUS_UI = {
  valido: {
    icon: ShieldCheck,
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-900',
    iconColor: 'text-emerald-600',
    title: 'Documento autêntico e íntegro',
  },
  invalido: {
    icon: ShieldX,
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-900',
    iconColor: 'text-red-600',
    title: 'Documento inválido',
  },
  revogado: {
    icon: ShieldAlert,
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-900',
    iconColor: 'text-amber-600',
    title: 'Documento revogado',
  },
};

export default function VerifyPublic() {
  const { code: urlCode } = useParams();
  const navigate = useNavigate();
  const [input, setInput] = useState(urlCode || '');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const doVerify = useCallback(async (codeRaw) => {
    const normalized = normalizeClient(codeRaw);
    if (!normalized) {
      setError('Código inválido. Use o formato SIGESC-XXXX-XXXX.');
      setResult(null);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const r = await axios.get(`${API}/public/verify/${encodeURIComponent(normalized)}`);
      setResult(r.data);
      // Atualiza URL (compartilhável) sem re-render
      navigate(`/verificar/${normalized}`, { replace: true });
    } catch (e) {
      if (e.response?.status === 429) {
        setError('Muitas tentativas — aguarde 1 minuto e tente novamente.');
      } else {
        setError('Não foi possível verificar agora. Tente novamente em instantes.');
      }
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    if (urlCode && !result && !loading) {
      doVerify(urlCode);
    }
  }, [urlCode, result, loading, doVerify]);

  const onSubmit = (e) => {
    e.preventDefault();
    doVerify(input);
  };

  const ui = result ? STATUS_UI[result.status] : null;

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-indigo-950 via-indigo-900 to-slate-900 text-white"
      data-testid="verify-public-page"
    >
      <div className="max-w-3xl mx-auto px-4 py-10 sm:py-14">
        <header className="text-center mb-8">
          <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-widest text-indigo-300 border border-indigo-700/60 rounded-full px-3 py-1 mb-4">
            <Lock className="h-3 w-3" />
            Portal Público de Verificação
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold mb-2">
            Verifique a autenticidade de um documento SIGESC
          </h1>
          <p className="text-sm text-indigo-200/80 max-w-xl mx-auto">
            Digite o código de verificação impresso no documento ou escaneie o QR Code.
            Nenhum login é necessário.
          </p>
        </header>

        <form
          onSubmit={onSubmit}
          className="bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-5 shadow-2xl"
        >
          <label className="text-xs uppercase tracking-wider text-indigo-200 block mb-2">
            Código de verificação
          </label>
          <div className="flex gap-2 flex-wrap sm:flex-nowrap">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="SIGESC-ABCD-1234"
              className="flex-1 bg-white/90 text-gray-900 font-mono tracking-wider text-lg px-4 py-3 rounded-lg outline-none focus:ring-2 focus:ring-indigo-400 placeholder:text-gray-400"
              data-testid="verify-input"
              autoComplete="off"
              spellCheck="false"
              autoFocus
            />
            <button
              type="submit"
              disabled={loading || !input}
              className="inline-flex items-center justify-center gap-2 bg-indigo-500 hover:bg-indigo-400 disabled:bg-indigo-800 disabled:opacity-70 px-6 py-3 rounded-lg font-semibold transition"
              data-testid="verify-submit"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Verificar
            </button>
          </div>
          <p className="text-[11px] text-indigo-300/80 mt-3">
            Aceita também: sem hífens ({' '}
            <code className="bg-indigo-950/60 px-1 rounded text-indigo-200">sigescabcd1234</code>
            {' '}) ou sem prefixo ({' '}
            <code className="bg-indigo-950/60 px-1 rounded text-indigo-200">abcd-1234</code>
            {' '})
          </p>
        </form>

        {error && (
          <div
            className="mt-4 bg-red-500/20 border border-red-500/50 text-red-100 rounded-lg px-4 py-3 text-sm flex items-center gap-2"
            data-testid="verify-error"
          >
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {result && ui && (
          <ResultCard result={result} ui={ui} />
        )}

        <footer className="mt-10 text-center text-xs text-indigo-300/60">
          <p>
            Infraestrutura de Confiança SIGESC · Verificação pública baseada em
            SHA256 + HMAC-SHA256.
          </p>
          <p className="mt-1">
            <Link to="/" className="underline hover:text-white">Voltar ao sistema</Link>
          </p>
        </footer>
      </div>
    </div>
  );
}

function ResultCard({ result, ui }) {
  const Icon = ui.icon;
  return (
    <div
      className={`mt-6 ${ui.bg} ${ui.border} border rounded-2xl p-6 text-gray-900 shadow-xl`}
      data-testid={`verify-result-${result.status}`}
    >
      <div className="flex items-start gap-4">
        <Icon className={`h-10 w-10 ${ui.iconColor} flex-shrink-0`} />
        <div className="flex-1">
          <h2 className={`text-xl font-bold ${ui.text} mb-1`}>{ui.title}</h2>
          <p className="text-sm text-gray-700 mb-4" data-testid="verify-result-message">
            {result.mensagem}
          </p>

          {result.codigo && (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 text-gray-800">
                <Hash className="h-4 w-4 text-gray-500" />
                <span className="text-xs uppercase text-gray-500 tracking-wider">Código:</span>
                <code className="font-mono font-bold tracking-wider bg-white/60 border border-gray-300 rounded px-2 py-0.5">
                  {result.codigo}
                </code>
              </div>
              {result.tipo_label && (
                <div className="flex items-center gap-2 text-gray-800">
                  <FileText className="h-4 w-4 text-gray-500" />
                  <span className="text-xs uppercase text-gray-500 tracking-wider">Tipo:</span>
                  <strong>{result.tipo_label}</strong>
                </div>
              )}
              {result.emitido_em && (
                <div className="flex items-center gap-2 text-gray-800">
                  <Calendar className="h-4 w-4 text-gray-500" />
                  <span className="text-xs uppercase text-gray-500 tracking-wider">Emitido em:</span>
                  <strong>{new Date(result.emitido_em).toLocaleDateString('pt-BR')}</strong>
                </div>
              )}
              {result.emitido_por && (
                <div className="flex items-center gap-2 text-gray-800">
                  <Building2 className="h-4 w-4 text-gray-500" />
                  <span className="text-xs uppercase text-gray-500 tracking-wider">Emitido por:</span>
                  <strong>{result.emitido_por}</strong>
                </div>
              )}
              {result.escopo && result.escopo !== '—' && (
                <div className="flex items-center gap-2 text-gray-800">
                  <Building2 className="h-4 w-4 text-gray-500" />
                  <span className="text-xs uppercase text-gray-500 tracking-wider">Escopo:</span>
                  <strong>{result.escopo}</strong>
                </div>
              )}
              {result.revogado_em && (
                <div className="flex items-center gap-2 text-amber-900 bg-amber-100/70 border border-amber-300 rounded px-2 py-1 mt-2">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="text-xs uppercase tracking-wider">Revogado em:</span>
                  <strong>{new Date(result.revogado_em).toLocaleDateString('pt-BR')}</strong>
                </div>
              )}
            </div>
          )}

          <div className="mt-5 pt-4 border-t border-gray-300/60 grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-gray-500 uppercase tracking-wider block">Integridade</span>
              <strong
                className={
                  result.integridade === 'confirmada' ? 'text-emerald-700'
                  : result.integridade === 'revogada' ? 'text-amber-700'
                  : 'text-red-700'
                }
              >
                {result.integridade}
              </strong>
            </div>
            <div>
              <span className="text-gray-500 uppercase tracking-wider block">Assinatura do servidor</span>
              <strong className={result.assinatura_valida ? 'text-emerald-700' : 'text-red-700'}>
                {result.assinatura_valida ? 'válida' : 'inválida / ausente'}
              </strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
