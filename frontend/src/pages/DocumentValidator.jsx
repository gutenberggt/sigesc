/**
 * Validação de Documentos — /admin/document-validator (Mai/2026)
 *
 * Página interna de apoio (autenticada) para a equipe administrativa
 * consultar:
 *   1. Quais documentos o SIGESC sabe emitir e validar.
 *   2. Validar um código `SIGESC-XXXX-XXXX` ali mesmo (chama o endpoint
 *      público `/api/public/verify/{code}` — LGPD-safe).
 *   3. Acessar atalhos rápidos para o portal público externo (que pode
 *      ser compartilhado com vereadores, conselheiros, cidadãos).
 *
 * Escopo: super_admin, admin, secretario, diretor, coordenador,
 *         auxiliar_secretaria. (Definição de visibilidade no Dashboard.js.)
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ShieldCheck, ShieldX, ShieldAlert, Search, Loader2, ChevronLeft,
  ExternalLink, Copy, FileText, Brain, GraduationCap, ClipboardCheck,
  ScrollText, Award, Stamp, BookMarked, QrCode, Hash, Calendar, Building2,
} from 'lucide-react';
import { Layout } from '@/components/Layout';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const PUBLIC_VERIFY_PATH = '/verificar';

/**
 * Lista canônica de tipos de documentos verificáveis no SIGESC.
 *
 * Mantida em sincronia com `backend/services/verifiable_docs_service.py`
 * (constante `DOC_TYPES`). Quando um tipo novo for habilitado no backend,
 * adicione aqui também — a fonte da verdade pública é o backend.
 */
const DOCUMENT_CATALOG = [
  {
    type: 'plano_acao',
    icon: Brain,
    title: 'Plano de Ação Automático',
    summary: 'Plano gerado por IA (Claude 4.5) com diagnóstico, ações priorizadas e responsáveis.',
    issuedFrom: 'Plano de Ação · Snapshot Auditável',
    issuedRoute: '/admin/plano-acao',
    howTo: 'Vá em Plano de Ação → selecione escola/período → Gerar Plano. O PDF emitido já traz código + QR.',
    color: 'violet',
  },
  {
    type: 'relatorio_mensal',
    icon: ScrollText,
    title: 'Relatório Executivo Mensal',
    summary: 'Relatório consolidado mensal (cron 1º dia, enviado por e-mail) com indicadores e recomendações priorizadas.',
    issuedFrom: 'Relatórios Mensais',
    issuedRoute: '/admin/relatorios-mensais',
    howTo: 'Gerado AUTOMATICAMENTE no dia 1º de cada mês e enviado por e-mail. Para emissão manual, abra a página e clique em "Gerar Agora".',
    color: 'blue',
  },
  {
    type: 'matricula',
    icon: GraduationCap,
    title: 'Declaração de Matrícula',
    summary: 'Comprova que o aluno está matriculado em determinada escola/turma/série em um ano letivo.',
    issuedFrom: 'Declarações Escolares',
    issuedRoute: '/admin/declaracoes',
    howTo: 'Vá em Declarações Escolares → escolha o aluno → tipo "Matrícula" → indique a finalidade → "Emitir e baixar PDF".',
    color: 'emerald',
  },
  {
    type: 'frequencia',
    icon: ClipboardCheck,
    title: 'Declaração de Frequência',
    summary: 'Comprova o percentual de frequência do aluno em um período (bimestre, ano letivo).',
    issuedFrom: 'Declarações Escolares',
    issuedRoute: '/admin/declaracoes',
    howTo: 'Vá em Declarações Escolares → escolha o aluno → tipo "Frequência" → indique o período → "Emitir e baixar PDF".',
    color: 'cyan',
  },
  {
    type: 'escolaridade',
    icon: BookMarked,
    title: 'Declaração de Escolaridade',
    summary: 'Comprova série/etapa concluída (útil para benefícios sociais e bancos).',
    issuedFrom: 'Declarações Escolares',
    issuedRoute: '/admin/declaracoes',
    howTo: 'Vá em Declarações Escolares → escolha o aluno → tipo "Escolaridade" → indique a finalidade → "Emitir e baixar PDF".',
    color: 'teal',
  },
  {
    type: 'historico',
    icon: ScrollText,
    title: 'Histórico Escolar',
    summary: 'Histórico oficial de notas, frequências e situações por ano letivo.',
    issuedFrom: 'Ficha do Aluno · Botão "Histórico"',
    issuedRoute: '/admin/students',
    howTo: 'Vá em Alunos → clique no aluno → aba "Histórico" → botão "Imprimir/Baixar Histórico". O PDF traz código + QR.',
    color: 'indigo',
  },
  {
    type: 'certificado',
    icon: Award,
    title: 'Certificado de Conclusão',
    summary: 'Certificado emitido após conclusão de etapa/curso com QR de validação.',
    issuedFrom: 'Ficha do Aluno · Botão "Certificado"',
    issuedRoute: '/admin/students',
    howTo: 'Disponível APENAS para alunos do 9º Ano EF e EJA 4ª Etapa. Vá em Alunos → ficha → botão "Certificado" no canto superior direito.',
    color: 'amber',
  },
  {
    type: 'ata',
    icon: Stamp,
    title: 'Ata / Documento Administrativo',
    summary: 'Atas de conselho de classe, reuniões, decisões formais — código único por documento.',
    issuedFrom: 'Atas Internas (módulo dedicado)',
    issuedRoute: null,
    howTo: 'Tipo reservado para integrações futuras. Hoje é gerado via API administrativa quando necessário.',
    color: 'slate',
  },
  {
    type: 'generico',
    icon: FileText,
    title: 'Documento Institucional',
    summary: 'Categoria genérica para documentos institucionais não-padronizados emitidos com QR de validação.',
    issuedFrom: 'API interna · uso administrativo',
    issuedRoute: null,
    howTo: 'Reservado para casos não cobertos pelos tipos acima. Emissão manual via API por usuário com permissão.',
    color: 'gray',
  },
];

const COLOR_CLASSES = {
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  cyan: 'bg-cyan-50 text-cyan-700 ring-cyan-200',
  teal: 'bg-teal-50 text-teal-700 ring-teal-200',
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  slate: 'bg-slate-50 text-slate-700 ring-slate-200',
  gray: 'bg-gray-50 text-gray-700 ring-gray-200',
};

const STATUS_UI = {
  valido: {
    icon: ShieldCheck,
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
    text: 'text-emerald-900',
    accent: 'text-emerald-600',
    title: 'Documento autêntico e íntegro',
  },
  invalido: {
    icon: ShieldX,
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-900',
    accent: 'text-red-600',
    title: 'Documento inválido',
  },
  revogado: {
    icon: ShieldAlert,
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-900',
    accent: 'text-amber-600',
    title: 'Documento revogado',
  },
};

function normalizeCodeClient(raw) {
  if (!raw) return null;
  const cleaned = raw.toUpperCase().replace(/[\s-]/g, '').replace(/^SIGESC/, '');
  if (!/^[A-Z2-9]{8}$/.test(cleaned)) return null;
  return `SIGESC-${cleaned.slice(0, 4)}-${cleaned.slice(4)}`;
}

export default function DocumentValidator() {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const publicPortalUrl = `${window.location.origin}${PUBLIC_VERIFY_PATH}`;

  const handleSubmit = async (e) => {
    e?.preventDefault();
    setError('');
    setResult(null);
    const normalized = normalizeCodeClient(code);
    if (!normalized) {
      setError('Código inválido. Formato esperado: SIGESC-XXXX-XXXX (8 caracteres do alfabeto A-Z, 2-9).');
      return;
    }
    setLoading(true);
    try {
      const r = await axios.get(`${API}/public/verify/${encodeURIComponent(normalized)}`);
      setResult(r.data);
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      if (e2?.response?.status === 429) {
        setError('Muitas consultas em pouco tempo. Aguarde 1 minuto e tente novamente.');
      } else if (e2?.response?.status === 404) {
        setResult({ status: 'invalido', codigo: normalized, mensagem: 'Documento não encontrado no repositório.' });
      } else {
        setError(detail || 'Falha ao validar documento.');
      }
    } finally {
      setLoading(false);
    }
  };

  const copyPortalUrl = async () => {
    try {
      await navigator.clipboard.writeText(publicPortalUrl);
      toast.success('Link do portal público copiado!');
    } catch {
      toast.error('Não foi possível copiar — copie manualmente.');
    }
  };

  return (
    <Layout>
      <div className="max-w-6xl mx-auto px-4 py-6" data-testid="document-validator-page">
        <Link
          to="/dashboard"
          className="inline-flex items-center text-sm text-gray-600 hover:text-purple-700 mb-3"
          data-testid="back-to-dashboard"
        >
          <ChevronLeft className="h-4 w-4 mr-1" /> Voltar ao Dashboard
        </Link>

        <header className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="h-7 w-7 text-emerald-600" />
            <h1 className="text-2xl font-bold text-gray-900">Validação de Documentos</h1>
          </div>
          <p className="text-sm text-gray-600 max-w-3xl">
            Confira a autenticidade e a integridade dos documentos emitidos pelo SIGESC.
            Cada documento institucional emitido aqui carrega um código único
            <code className="mx-1 px-1.5 py-0.5 bg-gray-100 rounded text-xs">SIGESC-XXXX-XXXX</code>
            e um QR code que apontam para o portal público de verificação.
          </p>
        </header>

        {/* Validador */}
        <section
          className="bg-white border border-gray-200 rounded-xl p-5 mb-8 shadow-sm"
          data-testid="validator-form-section"
        >
          <div className="flex items-center gap-2 mb-3">
            <Search className="h-5 w-5 text-purple-600" />
            <h2 className="font-semibold text-gray-900">Validar um documento</h2>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Digite o código que aparece no PDF (rodapé) ou escaneie o QR code com seu celular.
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="SIGESC-XXXX-XXXX"
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-purple-500"
              maxLength={20}
              autoComplete="off"
              spellCheck={false}
              data-testid="validator-code-input"
            />
            <button
              type="submit"
              disabled={loading || !code.trim()}
              className="px-5 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 inline-flex items-center justify-center gap-2 disabled:opacity-60 transition-colors"
              data-testid="validator-submit-btn"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Validar
            </button>
          </form>

          {error && (
            <div
              className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm"
              data-testid="validator-error"
            >
              {error}
            </div>
          )}

          {result && (
            <ValidationResult result={result} />
          )}

          <div className="mt-5 pt-4 border-t border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-gray-500">
            <span>
              Para compartilhar com terceiros (vereadores, conselheiros, cidadãos), use o portal público:
            </span>
            <div className="flex items-center gap-2">
              <code
                className="px-2 py-1 bg-gray-50 border border-gray-200 rounded text-xs select-all"
                data-testid="public-portal-url"
              >
                {publicPortalUrl}
              </code>
              <button
                onClick={copyPortalUrl}
                className="text-purple-600 hover:text-purple-800"
                title="Copiar link"
                data-testid="copy-public-url"
              >
                <Copy className="h-4 w-4" />
              </button>
              <Link
                to={PUBLIC_VERIFY_PATH}
                target="_blank"
                rel="noreferrer"
                className="text-purple-600 hover:text-purple-800"
                title="Abrir portal"
              >
                <ExternalLink className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* Catálogo de tipos */}
        <section data-testid="document-catalog">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="h-5 w-5 text-gray-700" />
            <h2 className="font-semibold text-gray-900">Documentos disponíveis no sistema</h2>
            <span className="ml-2 text-xs text-gray-500">
              ({DOCUMENT_CATALOG.length} tipos)
            </span>
          </div>
          <p className="text-xs text-gray-500 mb-4 max-w-3xl">
            Todos os documentos abaixo são emitidos com <strong>código único</strong>,
            <strong> QR de verificação</strong>, <strong>hash SHA-256</strong> e
            <strong> assinatura HMAC do servidor</strong> — qualquer alteração posterior
            é detectada automaticamente.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {DOCUMENT_CATALOG.map((doc) => (
              <DocumentTypeCard key={doc.type} doc={doc} />
            ))}
          </div>
        </section>

        {/* Como funciona */}
        <section className="mt-8 bg-purple-50 border border-purple-200 rounded-xl p-5">
          <h3 className="font-semibold text-purple-900 mb-2 flex items-center gap-2">
            <QrCode className="h-5 w-5" /> Como o SIGESC garante a autenticidade
          </h3>
          <ol className="text-sm text-purple-900 space-y-2 list-decimal list-inside">
            <li>Cada documento gera um <strong>snapshot imutável</strong> no banco com hash SHA-256 do conteúdo.</li>
            <li>O hash é assinado com <strong>HMAC do servidor</strong> — só o backend SIGESC consegue produzir uma assinatura válida.</li>
            <li>Um <strong>código curto</strong> (8 caracteres do alfabeto A-Z, 2-9 — sem ambiguidades) é emitido junto com o PDF.</li>
            <li>O PDF traz <strong>QR code</strong> apontando para o portal público.</li>
            <li>Qualquer pessoa, em qualquer lugar, valida o documento sem precisar de login (LGPD-safe — só metadados mínimos são expostos).</li>
            <li>Se o documento for revogado por administrador autorizado, o portal mostra status <em>"revogado"</em> com data e motivo.</li>
          </ol>
        </section>
      </div>
    </Layout>
  );
}

function DocumentTypeCard({ doc }) {
  const Icon = doc.icon;
  const colorClass = COLOR_CLASSES[doc.color] || COLOR_CLASSES.gray;
  return (
    <div
      className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow flex flex-col"
      data-testid={`doc-type-${doc.type}`}
    >
      <div className="flex items-start gap-3 mb-2">
        <span className={`p-2 rounded-lg ring-1 ring-inset ${colorClass} flex-shrink-0`}>
          <Icon className="h-5 w-5" />
        </span>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 leading-tight">{doc.title}</h3>
          <code className="text-[10px] text-gray-400 font-mono">{doc.type}</code>
        </div>
      </div>
      <p className="text-xs text-gray-600 mb-3 leading-relaxed">{doc.summary}</p>

      {doc.howTo && (
        <details className="mb-3 group">
          <summary className="text-xs font-medium text-purple-700 cursor-pointer hover:text-purple-900 list-none flex items-center gap-1">
            <span className="group-open:rotate-90 inline-block transition-transform">▸</span>
            Como emitir
          </summary>
          <p className="text-[11px] text-gray-600 mt-1.5 pl-4 leading-relaxed border-l-2 border-purple-200 pr-1">
            {doc.howTo}
          </p>
        </details>
      )}

      <div className="border-t border-gray-100 pt-2 flex items-center justify-between mt-auto">
        <span className="text-[11px] text-gray-500 truncate" title={doc.issuedFrom}>
          <strong className="text-gray-700">{doc.issuedFrom}</strong>
        </span>
        {doc.issuedRoute && (
          <Link
            to={doc.issuedRoute}
            className="text-xs text-white bg-purple-600 hover:bg-purple-700 inline-flex items-center gap-1 ml-2 flex-shrink-0 px-2 py-1 rounded transition-colors"
            data-testid={`doc-type-${doc.type}-link`}
          >
            Emitir <ExternalLink className="h-3 w-3" />
          </Link>
        )}
      </div>
    </div>
  );
}

function ValidationResult({ result }) {
  const status = (result?.status || 'invalido').toLowerCase();
  const ui = STATUS_UI[status] || STATUS_UI.invalido;
  const Icon = ui.icon;

  return (
    <div
      className={`mt-5 ${ui.bg} ${ui.border} border rounded-xl p-4`}
      data-testid={`validation-result-${status}`}
    >
      <div className="flex items-start gap-3">
        <Icon className={`h-7 w-7 flex-shrink-0 ${ui.accent}`} />
        <div className="flex-1 min-w-0">
          <h3 className={`font-semibold ${ui.text}`}>{ui.title}</h3>
          {result.codigo && (
            <p className="text-xs text-gray-600 font-mono mt-1">{result.codigo}</p>
          )}
          {result.mensagem && (
            <p className={`text-sm ${ui.text} mt-2`}>{result.mensagem}</p>
          )}

          {/* Metadados públicos LGPD-safe */}
          {(result.tipo || result.emitido_em || result.emitido_por || result.escopo) && (
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 mt-3 text-xs">
              {result.tipo && (
                <Field label="Tipo" icon={FileText} value={result.tipo} />
              )}
              {result.emitido_em && (
                <Field label="Emitido em" icon={Calendar} value={formatDate(result.emitido_em)} />
              )}
              {result.emitido_por && (
                <Field label="Emitido por" icon={Building2} value={result.emitido_por} />
              )}
              {result.escopo && (
                <Field label="Escopo" icon={Building2} value={result.escopo} />
              )}
              {result.public_hash && (
                <Field
                  label="Hash"
                  icon={Hash}
                  value={
                    <code className="font-mono text-[10px] break-all">
                      {result.public_hash.slice(0, 32)}…
                    </code>
                  }
                />
              )}
            </dl>
          )}

          {result.revogado_em && (
            <div className="mt-2 text-xs text-amber-800">
              Revogado em {formatDate(result.revogado_em)}
              {result.motivo_revogacao && ` — ${result.motivo_revogacao}`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, icon: Icon, value }) {
  return (
    <div className="flex items-start gap-1.5">
      {Icon && <Icon className="h-3.5 w-3.5 text-gray-400 mt-0.5 flex-shrink-0" />}
      <span className="text-gray-500">{label}:</span>{' '}
      <span className="text-gray-800 font-medium">{value}</span>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
