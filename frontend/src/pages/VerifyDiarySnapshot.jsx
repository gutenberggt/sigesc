/**
 * Verificação pública de documento institucional (Fase 5b — Mai/2026).
 *
 * Rota: /verify/diary/{token}  (SEM auth)
 *
 * O cidadão escaneia QR no PDF → cai aqui → vê dados institucionais
 * LGPD-safe (apenas verificação, sem PII).
 *
 * Diretrizes do owner:
 *   - Política LGPD 1c: code + status + escola + turma + período +
 *     hash + assinaturas (sem alunos/conteúdo/autores).
 *   - QR verifica o SNAPSHOT (não o PDF). Snapshot é a autoridade.
 *   - UI minimalista, institucional, sem login. Otimizada para celular.
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Building2,
  School,
  CalendarDays,
  Hash,
  Pen,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${API_URL}/api`;

const STATUS_META = {
  published: {
    label: 'Documento Válido',
    sub: 'Publicado institucionalmente.',
    icon: ShieldCheck,
    cls: 'bg-emerald-50 border-emerald-600 text-emerald-900',
    badge: 'bg-emerald-700 text-white',
  },
  superseded: {
    label: 'Substituído',
    sub: 'Este documento foi substituído por uma versão mais recente.',
    icon: ShieldAlert,
    cls: 'bg-amber-50 border-amber-500 text-amber-900',
    badge: 'bg-amber-600 text-white',
  },
  revoked: {
    label: 'Documento Revogado',
    sub: 'Este documento foi revogado institucionalmente.',
    icon: ShieldX,
    cls: 'bg-red-50 border-red-600 text-red-900',
    badge: 'bg-red-700 text-white',
  },
  draft: {
    label: 'Documento Não Publicado',
    sub: 'Snapshot ainda em rascunho.',
    icon: AlertTriangle,
    cls: 'bg-gray-50 border-gray-400 text-gray-700',
    badge: 'bg-gray-600 text-white',
  },
};

const SIGNATURE_TYPE_LABEL = {
  manual: 'Assinatura física',
  image: 'Assinatura eletrônica (imagem)',
  icp_brasil: 'Assinatura digital qualificada (ICP-Brasil)',
};

function formatDateBR(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function VerifyDiarySnapshot() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/verify/diary/${token}`, {
          // SEM credentials — endpoint público.
          withCredentials: false,
        });
        if (!aborted) setData(res.data);
      } catch (e) {
        if (aborted) return;
        if (e.response?.status === 429) {
          setError({
            kind: 'rate_limit',
            message:
              e.response?.data?.detail?.message ||
              'Muitas requisições. Tente novamente em alguns minutos.',
          });
        } else if (e.response?.status === 404) {
          setError({
            kind: 'not_found',
            message:
              'Documento não encontrado. Verifique se o código está correto ou se o documento já foi publicado.',
          });
        } else {
          setError({
            kind: 'unknown',
            message: 'Erro ao verificar o documento. Tente novamente.',
          });
        }
      } finally {
        if (!aborted) setLoading(false);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="text-center" data-testid="verify-loading">
          <Loader2
            size={32}
            className="animate-spin mx-auto text-blue-600 mb-2"
          />
          <p className="text-sm text-gray-600">
            Verificando autenticidade institucional…
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    const Icon = error.kind === 'not_found' ? ShieldX : ShieldAlert;
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div
          className="max-w-md w-full bg-white rounded-lg border-2 border-red-300 p-6 text-center"
          data-testid="verify-error"
        >
          <Icon size={48} className="mx-auto text-red-600 mb-3" />
          <h1 className="text-lg font-semibold text-gray-900">
            Não foi possível verificar
          </h1>
          <p className="text-sm text-gray-600 mt-2">{error.message}</p>
          <p className="text-[11px] text-gray-400 mt-4">
            Identificador: <code className="font-mono">{token?.slice(0, 16)}…</code>
          </p>
        </div>
      </div>
    );
  }

  if (!data) return null;
  const meta = STATUS_META[data.status] || STATUS_META.draft;
  const StatusIcon = meta.icon;
  const activeSigs = (data.signatures || []).filter(
    (s) => s.status !== 'revoked',
  );

  return (
    <div className="min-h-screen bg-gray-50 py-6 px-4" data-testid="verify-page">
      <div className="max-w-2xl mx-auto space-y-4">
        {/* Branding mínimo */}
        <div className="text-center text-xs text-gray-500 uppercase tracking-wider">
          {data.mantenedora_name || 'Sistema SIGESC'} · Verificação Institucional
        </div>

        {/* Status principal */}
        <div
          className={`rounded-lg border-2 p-6 ${meta.cls}`}
          data-testid={`verify-status-${data.status}`}
        >
          <div className="flex items-start gap-3">
            <StatusIcon size={36} className="flex-shrink-0 mt-1" />
            <div className="flex-1">
              <h1 className="text-2xl font-bold">{meta.label}</h1>
              <p className="text-sm opacity-80 mt-1">{meta.sub}</p>
              <span
                className={`inline-block mt-3 px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wide ${meta.badge}`}
              >
                {data.status}
              </span>
            </div>
          </div>
        </div>

        {/* Identificação institucional */}
        <div
          className="bg-white rounded-lg border border-gray-200 p-5 space-y-3"
          data-testid="verify-identification"
        >
          <h2 className="text-sm uppercase tracking-wide text-gray-500 font-medium">
            Identificação institucional
          </h2>
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <Hash size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm">
                <div className="text-gray-500 text-[11px] uppercase">Código</div>
                <code
                  className="font-mono font-semibold text-gray-900"
                  data-testid="verify-code"
                >
                  {data.code || '—'}
                </code>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Building2
                size={16}
                className="text-gray-400 mt-0.5 flex-shrink-0"
              />
              <div className="text-sm">
                <div className="text-gray-500 text-[11px] uppercase">Escola</div>
                <div className="text-gray-900 font-medium">
                  {data.school_name || '—'}
                </div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <School size={16} className="text-gray-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm">
                <div className="text-gray-500 text-[11px] uppercase">Turma</div>
                <div className="text-gray-900 font-medium">
                  {data.class_name || '—'}
                </div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <CalendarDays
                size={16}
                className="text-gray-400 mt-0.5 flex-shrink-0"
              />
              <div className="text-sm">
                <div className="text-gray-500 text-[11px] uppercase">Período</div>
                <div className="text-gray-900 font-medium">
                  {data.period?.from} a {data.period?.to}
                  {data.period?.label && (
                    <span className="text-gray-500 ml-2">
                      ({data.period.label})
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle2
                size={16}
                className="text-gray-400 mt-0.5 flex-shrink-0"
              />
              <div className="text-sm">
                <div className="text-gray-500 text-[11px] uppercase">
                  Emitido em
                </div>
                <div className="text-gray-900 font-medium">
                  {formatDateBR(data.issued_at)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Assinaturas */}
        <div
          className="bg-white rounded-lg border border-gray-200 p-5"
          data-testid="verify-signatures"
        >
          <h2 className="text-sm uppercase tracking-wide text-gray-500 font-medium mb-3">
            Assinaturas Institucionais ({activeSigs.length})
          </h2>
          {activeSigs.length === 0 ? (
            <p className="text-sm text-gray-500 italic">
              Nenhuma assinatura institucional ativa no momento.
            </p>
          ) : (
            <ul className="space-y-3">
              {activeSigs.map((s, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 p-3 bg-gray-50 rounded border border-gray-200"
                >
                  <Pen size={16} className="text-emerald-600 flex-shrink-0 mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-gray-900">
                      {s.full_name}
                    </div>
                    <div className="text-xs text-gray-600">{s.role}</div>
                    <div className="text-[11px] text-gray-500 mt-1">
                      {SIGNATURE_TYPE_LABEL[s.signature_type] || s.signature_type}{' '}
                      · {formatDateBR(s.signed_at)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Hash documental */}
        <div
          className="bg-gray-100 rounded-lg border border-gray-300 p-4"
          data-testid="verify-hash"
        >
          <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
            Hash documental (SHA-256)
          </div>
          <code className="text-[10px] font-mono text-gray-700 break-all">
            {data.payload_hash_sha256}
          </code>
          <div className="mt-2 text-[10px] text-gray-500">
            Schema v{data.schema_version} · Semantic Rules v
            {data.semantic_rules_version}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-[11px] text-gray-400 pt-4">
          Esta página apresenta informações públicas de verificação
          institucional, sem dados pessoais de alunos, professores ou conteúdo
          pedagógico, em conformidade com a LGPD.
        </div>
      </div>
    </div>
  );
}
