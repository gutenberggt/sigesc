/**
 * Página PÚBLICA de verificação de Histórico Escolar Consolidado.
 * SEM autenticação. Acessível por qualquer pessoa via QR Code.
 * Caminho: /verify/historico/:token
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent } from '@/components/ui/card';
import { ShieldCheck, ShieldAlert, Loader2, FileText, Hash } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function VerifyHistory() {
  const { token } = useParams();
  const [state, setState] = useState({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    const isolated = axios.create();
    isolated
      .get(`${API}/api/verify/historico/${token}`)
      .then((r) => { if (!cancelled) setState({ status: 'ok', data: r.data }); })
      .catch((e) => {
        if (cancelled) return;
        const detail = e?.response?.data?.detail || e.message || 'Falha de comunicação';
        setState({ status: 'error', detail });
      });
    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 px-4 py-12 flex items-center justify-center">
      <div className="max-w-xl w-full">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-slate-900">Verificação de Documento</h1>
          <p className="text-sm text-slate-600 mt-1">Sistema SIGESC · Histórico Escolar Consolidado</p>
        </div>

        {state.status === 'loading' && (
          <Card>
            <CardContent className="py-10 flex items-center justify-center gap-2 text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" /> Validando documento…
            </CardContent>
          </Card>
        )}

        {state.status === 'error' && (
          <Card className="border-red-200">
            <CardContent className="py-8 text-center">
              <ShieldAlert className="w-12 h-12 mx-auto text-red-600 mb-3" />
              <div className="text-base font-medium text-red-800">Documento não encontrado</div>
              <div className="text-xs text-red-700 mt-2" data-testid="verify-error-detail">{state.detail}</div>
              <div className="text-xs text-slate-500 mt-4">
                Verifique se o QR Code foi lido corretamente ou se o link foi copiado por completo.
              </div>
            </CardContent>
          </Card>
        )}

        {state.status === 'ok' && state.data?.valid === false && (
          <Card className="border-amber-300">
            <CardContent className="py-8 text-center">
              <ShieldAlert className="w-12 h-12 mx-auto text-amber-600 mb-3" />
              <div className="text-base font-medium text-amber-800">
                {state.data?.revoked ? 'Documento revogado' : 'Documento inválido'}
              </div>
              <div className="text-xs text-amber-700 mt-2">{state.data?.reason}</div>
            </CardContent>
          </Card>
        )}

        {state.status === 'ok' && state.data?.valid === true && (
          <Card className="border-emerald-300 shadow-sm" data-testid="verify-history-ok-card">
            <CardContent className="py-6">
              <div className="flex items-center gap-3 pb-4 border-b border-emerald-100">
                <ShieldCheck className="w-10 h-10 text-emerald-600 shrink-0" />
                <div>
                  <div className="text-base font-semibold text-emerald-900">Histórico autêntico</div>
                  <div className="text-xs text-emerald-700">
                    Consolidado automaticamente pelo SIGESC a partir dos registros internos.
                  </div>
                </div>
              </div>

              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 mt-5 text-sm">
                <Field label="Tipo de documento" value={state.data.document_type} />
                <Field label="Aluno(a)" value={state.data.student_name} />
                <Field label="Escola atual" value={state.data.school_name} />
                <Field
                  label="Anos consolidados"
                  value={(state.data.years_covered || []).join(', ') || '—'}
                />
                <Field label="Total de séries" value={state.data.records_count ?? '—'} />
                <Field label="Emitido em" value={formatDate(state.data.issued_at)} />
                <Field
                  label="Verification ID"
                  value={(state.data.verification_id || '').slice(0, 12) + '…'}
                  mono
                />
              </dl>

              <div className="mt-5 pt-4 border-t border-emerald-100">
                <div className="text-xs font-medium text-slate-700 flex items-center gap-1.5 mb-1">
                  <Hash className="w-3.5 h-3.5" /> Hash SHA-256 do PDF
                </div>
                <code className="block text-[10.5px] bg-slate-100 rounded px-2 py-1.5 break-all text-slate-700" data-testid="verify-history-sha256">
                  {state.data.pdf_sha256}
                </code>
                <div className="text-[11px] text-slate-500 mt-2 leading-relaxed">
                  {state.data.note}
                </div>
              </div>

              <div className="mt-5 flex items-center gap-2 text-[11px] text-slate-500">
                <FileText className="w-3.5 h-3.5" />
                Esta página não exibe notas detalhadas, dados pessoais sensíveis nem registros disciplinares — apenas dados-resumo para confirmação de autenticidade (LGPD).
              </div>
            </CardContent>
          </Card>
        )}

        <div className="text-center text-[11px] text-slate-400 mt-6">
          SIGESC · Sistema Integrado de Gestão Escolar
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, mono = false }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={`text-sm text-slate-900 mt-0.5 ${mono ? 'font-mono text-xs' : ''}`}>
        {value || '—'}
      </dd>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return iso;
  }
}
