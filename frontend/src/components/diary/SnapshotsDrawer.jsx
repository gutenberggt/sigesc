/**
 * Snapshots Drawer — UI Snapshot Management (Fase 8 — Fev/2026)
 *
 * Drawer lateral acessado a partir do Calendário Operacional do Diário.
 * Permite à coordenação/direção:
 *   - Emitir documento institucional do período (cria draft + publica + render PDF).
 *   - Acompanhar status dos snapshots da turma.
 *   - Baixar o PDF institucional.
 *   - Visualizar/copiar URL pública de verificação (QR está embutido no PDF).
 *   - Adicionar/Revogar assinaturas (manual ou imagem).
 *   - Revogar o snapshot (com justificativa e confirmação dupla).
 *
 * Diretrizes do owner (Fev/2026):
 *   - UI institucional, não técnica.
 *   - Nada de JSON cru, sem termos internos.
 *   - Frontend NUNCA recalcula — apenas renderiza o que o backend devolve.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  FileSignature,
  Download,
  Copy,
  Loader2,
  ExternalLink,
  Pen,
  PlusCircle,
  XCircle,
  FilePlus2,
  Hash,
  CircleSlash,
  Image as ImageIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';

const API_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${API_URL}/api`;
const PUBLIC_VERIFY_BASE = `${API_URL}/verify/diary`;

// ----------------------------------------------------------------------------
// Status helpers (Frontend é renderizador puro — só mapeia, não decide)
// ----------------------------------------------------------------------------
const STATUS_META = {
  draft: {
    label: 'Rascunho',
    icon: FilePlus2,
    badge: 'bg-gray-200 text-gray-800 border-gray-400',
    weight: 1,
    description: 'Documento ainda não publicado.',
  },
  published: {
    label: 'Publicado',
    icon: ShieldCheck,
    badge: 'bg-emerald-700 text-white border-emerald-700',
    weight: 2,
    description: 'Documento institucional vigente.',
  },
  superseded: {
    label: 'Substituído',
    icon: ShieldAlert,
    badge: 'bg-amber-600 text-white border-amber-700',
    weight: 3,
    description: 'Substituído por uma emissão posterior.',
  },
  revoked: {
    label: 'Revogado',
    icon: ShieldX,
    badge: 'bg-red-700 text-white border-red-800',
    weight: 4,
    description: 'Invalidado institucionalmente.',
  },
};

const SIGNATURE_ROLES = [
  { value: 'diretor', label: 'Direção' },
  { value: 'secretario', label: 'Secretaria' },
  { value: 'coordenador', label: 'Coordenação Pedagógica' },
  { value: 'gerente', label: 'Gerência (Mantenedora)' },
];

const SIGNATURE_TYPE_LABEL = {
  manual: 'Assinatura física (linha no PDF)',
  image: 'Assinatura digitalizada (imagem)',
  icp_brasil: 'Certificado ICP-Brasil',
};

function shortHash(hash) {
  if (!hash) return '—';
  return `${hash.slice(0, 8)}…${hash.slice(-8)}`;
}

function formatDate(iso) {
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

// ============================================================================
// Sub-componente: cartão de um snapshot
// ============================================================================
function SnapshotCard({
  snap,
  onChanged,
  busy,
  setBusy,
  signatureImage,
}) {
  const meta = STATUS_META[snap.status] || STATUS_META.draft;
  const Icon = meta.icon;
  const activeSigs = (snap.signatures || []).filter(
    (s) => s.status !== 'revoked',
  );
  const verifyUrl = snap.verification_token
    ? `${PUBLIC_VERIFY_BASE}/${snap.verification_token}`
    : null;

  const [renderJob, setRenderJob] = useState(null);
  const [showSignForm, setShowSignForm] = useState(false);
  const [showRevokeDialog, setShowRevokeDialog] = useState(false);
  const [revokeStep, setRevokeStep] = useState(1);
  const [revokeRationale, setRevokeRationale] = useState('');
  const [showRevokeSigDialog, setShowRevokeSigDialog] = useState(null); // signature_id
  const [revokeSigRationale, setRevokeSigRationale] = useState('');

  // ---- Sign form state ----
  const { user } = useAuth();
  const [sigRole, setSigRole] = useState('diretor');
  const [sigFullName, setSigFullName] = useState(user?.full_name || '');
  const [sigType, setSigType] = useState('manual');

  // ----- Fetch render job se publicado -----
  const fetchRenderJob = useCallback(async () => {
    if (snap.status !== 'published') return;
    try {
      const res = await axios.get(`${API}/render-jobs`, {
        params: {
          source_snapshot_id: snap.id,
          document_type: 'diary_period',
          page_size: 1,
        },
      });
      const jobs = res.data?.items || [];
      setRenderJob(jobs[0] || null);
    } catch {
      // Ignora — não bloqueia render do card.
    }
  }, [snap.id, snap.status]);

  useEffect(() => {
    fetchRenderJob();
  }, [fetchRenderJob]);

  // Poll: se job pending/processing → atualiza a cada 4s.
  useEffect(() => {
    if (!renderJob) return undefined;
    if (renderJob.status === 'completed' || renderJob.status === 'failed') {
      return undefined;
    }
    const t = setInterval(fetchRenderJob, 4000);
    return () => clearInterval(t);
  }, [renderJob, fetchRenderJob]);

  // ----- Actions -----
  const handleDownload = async () => {
    if (!renderJob || renderJob.status !== 'completed') return;
    setBusy(`download-${snap.id}`, true);
    try {
      const res = await axios.get(
        `${API}/render-jobs/${renderJob.id}/file`,
        { responseType: 'blob' },
      );
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `diario-${snap.code || snap.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Download iniciado.');
    } catch (e) {
      toast.error('Não foi possível baixar o documento.');
    } finally {
      setBusy(`download-${snap.id}`, false);
    }
  };

  const handleCopyLink = async () => {
    if (!verifyUrl) return;
    try {
      await navigator.clipboard.writeText(verifyUrl);
      toast.success('Link de verificação copiado.');
    } catch {
      toast.error('Não foi possível copiar o link.');
    }
  };

  const handleAddSignature = async () => {
    if (!sigFullName.trim() || sigFullName.trim().length < 3) {
      toast.error('Informe seu nome completo (mínimo 3 caracteres).');
      return;
    }
    if (sigType === 'image' && !signatureImage?.file_id) {
      toast.error(
        'Você não possui assinatura digitalizada cadastrada no seu perfil.',
      );
      return;
    }
    setBusy(`sign-${snap.id}`, true);
    try {
      const body = {
        role: sigRole,
        full_name: sigFullName.trim(),
        signature_type: sigType,
      };
      if (sigType === 'image') {
        body.image_file_id = signatureImage.file_id;
      }
      await axios.post(`${API}/diary/snapshots/${snap.id}/sign`, body);
      toast.success('Assinatura institucional registrada.');
      setShowSignForm(false);
      onChanged();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg =
        typeof d === 'string' ? d : d?.message || 'Falha ao assinar.';
      toast.error(msg);
    } finally {
      setBusy(`sign-${snap.id}`, false);
    }
  };

  const handleRevokeSnapshot = async () => {
    if (revokeRationale.trim().length < 30) {
      toast.error('A justificativa precisa ter ao menos 30 caracteres.');
      return;
    }
    setBusy(`revoke-${snap.id}`, true);
    try {
      await axios.post(`${API}/diary/snapshots/${snap.id}/revoke`, {
        rationale: revokeRationale.trim(),
      });
      toast.success('Documento revogado institucionalmente.');
      setShowRevokeDialog(false);
      setRevokeStep(1);
      setRevokeRationale('');
      onChanged();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg =
        typeof d === 'string' ? d : d?.message || 'Falha ao revogar.';
      toast.error(msg);
    } finally {
      setBusy(`revoke-${snap.id}`, false);
    }
  };

  const handleRevokeSignature = async () => {
    if (revokeSigRationale.trim().length < 30) {
      toast.error('A justificativa precisa ter ao menos 30 caracteres.');
      return;
    }
    setBusy(`revokesig-${showRevokeSigDialog}`, true);
    try {
      await axios.post(
        `${API}/diary/snapshots/${snap.id}/signatures/${showRevokeSigDialog}/revoke`,
        { rationale: revokeSigRationale.trim() },
      );
      toast.success('Assinatura revogada.');
      setShowRevokeSigDialog(null);
      setRevokeSigRationale('');
      onChanged();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg =
        typeof d === 'string' ? d : d?.message || 'Falha ao revogar assinatura.';
      toast.error(msg);
    } finally {
      setBusy(`revokesig-${showRevokeSigDialog}`, false);
    }
  };

  const renderStatusLabel = (() => {
    if (snap.status !== 'published') return null;
    if (!renderJob) return 'Aguardando geração do PDF…';
    if (renderJob.status === 'pending' || renderJob.status === 'processing') {
      return 'Gerando documento…';
    }
    if (renderJob.status === 'failed') return 'Falha ao gerar PDF';
    return null;
  })();

  const canSign = snap.status === 'published';
  const canRevoke = snap.status === 'published' || snap.status === 'draft';

  return (
    <Card
      className={`border-2 ${
        snap.status === 'revoked'
          ? 'border-red-300 bg-red-50/30'
          : snap.status === 'superseded'
          ? 'border-amber-300 bg-amber-50/30'
          : 'border-gray-200'
      }`}
      data-testid={`snapshot-card-${snap.id}`}
      data-status={snap.status}
    >
      <CardContent className="p-4 space-y-3">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Icon size={18} className="text-gray-700 flex-shrink-0" />
              <Badge className={`${meta.badge} text-[10px] font-semibold`}>
                {meta.label}
              </Badge>
              <span
                className="text-xs text-gray-500 font-mono"
                data-testid={`snapshot-code-${snap.id}`}
              >
                {snap.code || '—'}
              </span>
            </div>
            <p className="text-[11px] text-gray-500 mt-1">{meta.description}</p>
          </div>
        </div>

        {/* Metadados */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Período</div>
            <div className="text-gray-900 font-medium tabular-nums">
              {snap.period?.from} → {snap.period?.to}
            </div>
          </div>
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Emitido em</div>
            <div className="text-gray-900 font-medium">
              {formatDate(snap.issued_at)}
            </div>
          </div>
          <div className="col-span-2">
            <div className="text-gray-500 uppercase text-[10px] flex items-center gap-1">
              <Hash size={10} /> Hash documental
            </div>
            <code className="text-[10px] font-mono text-gray-700 break-all">
              {shortHash(snap.payload_hash_sha256)}
            </code>
          </div>
        </div>

        {/* Render / Download */}
        {snap.status === 'published' && (
          <div className="border-t border-gray-200 pt-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="text-xs text-gray-600">
                {renderStatusLabel || (
                  <span className="text-emerald-700 font-medium">
                    Documento institucional pronto.
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={
                  !renderJob ||
                  renderJob.status !== 'completed' ||
                  busy.has(`download-${snap.id}`)
                }
                onClick={handleDownload}
                data-testid={`snapshot-download-${snap.id}`}
              >
                {busy.has(`download-${snap.id}`) ? (
                  <Loader2 size={14} className="animate-spin mr-1" />
                ) : (
                  <Download size={14} className="mr-1" />
                )}
                Baixar PDF
              </Button>
            </div>
          </div>
        )}

        {/* Verificabilidade pública */}
        {verifyUrl && snap.status === 'published' && (
          <div className="border-t border-gray-200 pt-3 space-y-2">
            <div className="text-[10px] uppercase text-gray-500 tracking-wide">
              Verificação pública (QR no PDF)
            </div>
            <div className="flex items-center gap-2">
              <code
                className="flex-1 text-[10px] font-mono bg-gray-50 rounded border border-gray-200 px-2 py-1.5 truncate"
                title={verifyUrl}
              >
                {verifyUrl}
              </code>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleCopyLink}
                data-testid={`snapshot-copy-link-${snap.id}`}
                title="Copiar link"
              >
                <Copy size={14} />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                asChild
                title="Abrir verificação pública"
              >
                <a
                  href={verifyUrl}
                  target="_blank"
                  rel="noreferrer"
                  data-testid={`snapshot-open-link-${snap.id}`}
                >
                  <ExternalLink size={14} />
                </a>
              </Button>
            </div>
          </div>
        )}

        {/* Assinaturas */}
        {(snap.status === 'published' || activeSigs.length > 0) && (
          <div className="border-t border-gray-200 pt-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10px] uppercase text-gray-500 tracking-wide">
                Assinaturas institucionais ({activeSigs.length})
              </div>
              {canSign && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 text-[11px]"
                  onClick={() => setShowSignForm((v) => !v)}
                  data-testid={`snapshot-add-signature-${snap.id}`}
                >
                  <PlusCircle size={12} className="mr-1" />
                  {showSignForm ? 'Cancelar' : 'Assinar'}
                </Button>
              )}
            </div>

            {activeSigs.length === 0 ? (
              <p className="text-[11px] text-gray-500 italic">
                Nenhuma assinatura registrada ainda.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {(snap.signatures || []).map((s) => (
                  <li
                    key={s.id}
                    className={`flex items-start justify-between gap-2 p-2 rounded border ${
                      s.status === 'revoked'
                        ? 'bg-gray-100 border-gray-300 opacity-60 line-through'
                        : 'bg-emerald-50/50 border-emerald-200'
                    }`}
                    data-testid={`signature-row-${s.id}`}
                  >
                    <div className="flex items-start gap-2 flex-1 min-w-0">
                      <Pen
                        size={12}
                        className="text-emerald-700 mt-0.5 flex-shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-900">
                          {s.full_name}
                        </div>
                        <div className="text-[10px] text-gray-600">
                          {s.role}{' '}
                          <span className="opacity-60">
                            ·{' '}
                            {SIGNATURE_TYPE_LABEL[s.signature_type] ||
                              s.signature_type}
                          </span>
                        </div>
                        <div className="text-[10px] text-gray-500">
                          {formatDate(s.signed_at)}
                        </div>
                      </div>
                    </div>
                    {s.status !== 'revoked' && canSign && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 w-6 p-0 text-red-700"
                        onClick={() => setShowRevokeSigDialog(s.id)}
                        title="Revogar assinatura"
                        data-testid={`signature-revoke-${s.id}`}
                      >
                        <XCircle size={12} />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {/* Form de assinatura */}
            {showSignForm && canSign && (
              <div
                className="mt-3 p-3 bg-gray-50 rounded border border-gray-300 space-y-2"
                data-testid={`sign-form-${snap.id}`}
              >
                <div>
                  <Label className="text-[10px] uppercase text-gray-500">
                    Função
                  </Label>
                  <Select value={sigRole} onValueChange={setSigRole}>
                    <SelectTrigger
                      className="h-8 text-xs"
                      data-testid={`sign-role-select-${snap.id}`}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SIGNATURE_ROLES.map((r) => (
                        <SelectItem key={r.value} value={r.value}>
                          {r.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-[10px] uppercase text-gray-500">
                    Nome completo (como assinará)
                  </Label>
                  <Input
                    value={sigFullName}
                    onChange={(e) => setSigFullName(e.target.value)}
                    className="h-8 text-xs"
                    data-testid={`sign-fullname-input-${snap.id}`}
                  />
                </div>
                <div>
                  <Label className="text-[10px] uppercase text-gray-500">
                    Tipo de assinatura
                  </Label>
                  <div className="grid grid-cols-2 gap-2 mt-1">
                    <button
                      type="button"
                      onClick={() => setSigType('manual')}
                      className={`text-left p-2 rounded border text-[11px] ${
                        sigType === 'manual'
                          ? 'border-emerald-700 bg-emerald-50 text-emerald-900'
                          : 'border-gray-300 bg-white text-gray-700'
                      }`}
                      data-testid={`sign-type-manual-${snap.id}`}
                    >
                      <Pen size={12} className="inline mr-1" />
                      <span className="font-medium">Manual</span>
                      <div className="text-[10px] opacity-70 mt-0.5">
                        Linha física no PDF
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setSigType('image')}
                      disabled={!signatureImage?.file_id}
                      className={`text-left p-2 rounded border text-[11px] ${
                        sigType === 'image'
                          ? 'border-emerald-700 bg-emerald-50 text-emerald-900'
                          : 'border-gray-300 bg-white text-gray-700'
                      } ${
                        !signatureImage?.file_id
                          ? 'opacity-50 cursor-not-allowed'
                          : ''
                      }`}
                      data-testid={`sign-type-image-${snap.id}`}
                    >
                      <ImageIcon size={12} className="inline mr-1" />
                      <span className="font-medium">Imagem</span>
                      <div className="text-[10px] opacity-70 mt-0.5">
                        {signatureImage?.file_id
                          ? 'Usa a imagem cadastrada'
                          : 'Nenhuma cadastrada no perfil'}
                      </div>
                    </button>
                  </div>
                </div>
                <Button
                  size="sm"
                  className="w-full bg-emerald-700 hover:bg-emerald-800 text-white"
                  disabled={busy.has(`sign-${snap.id}`)}
                  onClick={handleAddSignature}
                  data-testid={`sign-confirm-${snap.id}`}
                >
                  {busy.has(`sign-${snap.id}`) ? (
                    <Loader2 size={14} className="animate-spin mr-1" />
                  ) : (
                    <FileSignature size={14} className="mr-1" />
                  )}
                  Registrar assinatura institucional
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Revogação do snapshot */}
        {canRevoke && (
          <div className="border-t border-gray-200 pt-3 flex justify-end">
            <Button
              size="sm"
              variant="ghost"
              className="text-red-700 hover:bg-red-50 text-[11px]"
              onClick={() => setShowRevokeDialog(true)}
              data-testid={`snapshot-revoke-${snap.id}`}
            >
              <CircleSlash size={12} className="mr-1" />
              Revogar documento
            </Button>
          </div>
        )}
      </CardContent>

      {/* Dialog: revogar snapshot (confirmação dupla) */}
      <AlertDialog
        open={showRevokeDialog}
        onOpenChange={(v) => {
          if (!v) {
            setShowRevokeDialog(false);
            setRevokeStep(1);
            setRevokeRationale('');
          }
        }}
      >
        <AlertDialogContent
          className="max-w-md"
          data-testid={`revoke-dialog-${snap.id}`}
        >
          <AlertDialogHeader>
            <AlertDialogTitle className="text-red-800 flex items-center gap-2">
              <ShieldX size={18} />
              {revokeStep === 1
                ? 'Revogar este documento institucional?'
                : 'Confirmação final'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {revokeStep === 1 ? (
                <>
                  Revogar é um ato institucional grave. O documento permanecerá
                  registrado na trilha de auditoria, mas perderá validade
                  pública. Esta ação <strong>não pode ser desfeita</strong>.
                </>
              ) : (
                <>
                  Reveja a justificativa abaixo. Ela ficará permanentemente
                  registrada e poderá ser consultada na trilha institucional.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {revokeStep === 1 && (
            <div className="space-y-2">
              <Label className="text-xs text-gray-700">
                Justificativa (mínimo 30 caracteres)
              </Label>
              <Textarea
                rows={4}
                value={revokeRationale}
                onChange={(e) => setRevokeRationale(e.target.value)}
                placeholder="Descreva o motivo institucional desta revogação…"
                data-testid={`revoke-rationale-${snap.id}`}
              />
              <div className="text-[10px] text-gray-500 tabular-nums">
                {revokeRationale.length}/30 caracteres
              </div>
            </div>
          )}
          {revokeStep === 2 && (
            <div className="p-3 bg-red-50 rounded border border-red-200 text-xs text-red-900">
              <strong>Documento:</strong> {snap.code}
              <br />
              <strong>Período:</strong> {snap.period?.from} → {snap.period?.to}
              <br />
              <strong>Motivo:</strong> {revokeRationale}
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel data-testid={`revoke-cancel-${snap.id}`}>
              Cancelar
            </AlertDialogCancel>
            {revokeStep === 1 ? (
              <Button
                className="bg-red-700 hover:bg-red-800 text-white"
                disabled={revokeRationale.trim().length < 30}
                onClick={() => setRevokeStep(2)}
                data-testid={`revoke-step1-confirm-${snap.id}`}
              >
                Continuar
              </Button>
            ) : (
              <AlertDialogAction
                className="bg-red-700 hover:bg-red-800 text-white"
                onClick={handleRevokeSnapshot}
                disabled={busy.has(`revoke-${snap.id}`)}
                data-testid={`revoke-final-confirm-${snap.id}`}
              >
                {busy.has(`revoke-${snap.id}`) ? (
                  <Loader2 size={14} className="animate-spin mr-1" />
                ) : (
                  <ShieldX size={14} className="mr-1" />
                )}
                Confirmar revogação
              </AlertDialogAction>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Dialog: revogar assinatura */}
      <AlertDialog
        open={!!showRevokeSigDialog}
        onOpenChange={(v) => {
          if (!v) {
            setShowRevokeSigDialog(null);
            setRevokeSigRationale('');
          }
        }}
      >
        <AlertDialogContent className="max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-red-800">
              Revogar esta assinatura?
            </AlertDialogTitle>
            <AlertDialogDescription>
              A assinatura permanecerá registrada na trilha institucional, mas
              será marcada como revogada. Justifique o motivo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Textarea
            rows={3}
            value={revokeSigRationale}
            onChange={(e) => setRevokeSigRationale(e.target.value)}
            placeholder="Motivo da revogação (mínimo 30 caracteres)…"
            data-testid="revoke-sig-rationale"
          />
          <div className="text-[10px] text-gray-500 tabular-nums">
            {revokeSigRationale.length}/30 caracteres
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <Button
              className="bg-red-700 hover:bg-red-800 text-white"
              disabled={
                revokeSigRationale.trim().length < 30 ||
                busy.has(`revokesig-${showRevokeSigDialog}`)
              }
              onClick={handleRevokeSignature}
              data-testid="revoke-sig-confirm"
            >
              {busy.has(`revokesig-${showRevokeSigDialog}`) ? (
                <Loader2 size={14} className="animate-spin mr-1" />
              ) : null}
              Revogar
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

// ============================================================================
// Drawer principal
// ============================================================================
export default function SnapshotsDrawer({
  open,
  onOpenChange,
  classId,
  className,
  periodFrom,
  periodTo,
  periodLabel,
}) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyKeys, setBusyKeys] = useState(() => new Set());
  const [emitting, setEmitting] = useState(false);
  const [signatureImage, setSignatureImage] = useState(null);

  const setBusy = useCallback((key, val) => {
    setBusyKeys((prev) => {
      const next = new Set(prev);
      if (val) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);

  // Carrega snapshots da turma
  const fetchSnapshots = useCallback(async () => {
    if (!classId || !open) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API}/diary/snapshots`, {
        params: { class_id: classId, page_size: 50 },
      });
      setSnapshots(res.data?.items || []);
    } catch (e) {
      toast.error('Não foi possível carregar a lista de documentos.');
      setSnapshots([]);
    } finally {
      setLoading(false);
    }
  }, [classId, open]);

  useEffect(() => {
    fetchSnapshots();
  }, [fetchSnapshots]);

  // Carrega assinatura digitalizada do próprio usuário (uma vez por sessão)
  useEffect(() => {
    if (!open) return;
    let aborted = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/users/me/signature-image`);
        if (!aborted) setSignatureImage(res.data || null);
      } catch {
        // 403 esperado para roles sem permissão de assinar — ignora.
        if (!aborted) setSignatureImage(null);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [open]);

  const periodActive = useMemo(
    () =>
      snapshots.find(
        (s) =>
          s.period?.from === periodFrom &&
          s.period?.to === periodTo &&
          (s.status === 'draft' || s.status === 'published'),
      ),
    [snapshots, periodFrom, periodTo],
  );

  const handleEmit = async () => {
    if (!classId || !periodFrom || !periodTo) return;
    setEmitting(true);
    try {
      // 1) Cria draft
      const createRes = await axios.post(`${API}/diary/snapshots`, {
        class_id: classId,
        period_type: 'month',
        period_from: periodFrom,
        period_to: periodTo,
        period_label: periodLabel,
      });
      const snap = createRes.data?.snapshot;
      if (!snap?.id) throw new Error('Falha ao criar rascunho.');

      // 2) Se ainda em draft, publica
      if (snap.status === 'draft') {
        await axios.post(`${API}/diary/snapshots/${snap.id}/publish`);
        toast.success(
          'Documento emitido. O PDF institucional será gerado em segundos.',
        );
      } else {
        toast.info('Já existe um documento ativo para este período.');
      }
      await fetchSnapshots();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg =
        typeof d === 'string' ? d : d?.message || 'Falha ao emitir documento.';
      toast.error(msg);
    } finally {
      setEmitting(false);
    }
  };

  // Ordena: ativos primeiro, depois por data de emissão desc
  const sortedSnapshots = useMemo(() => {
    return [...snapshots].sort((a, b) => {
      const wa = STATUS_META[a.status]?.weight ?? 99;
      const wb = STATUS_META[b.status]?.weight ?? 99;
      if (wa !== wb) return wa - wb;
      return (b.created_at || '').localeCompare(a.created_at || '');
    });
  }, [snapshots]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-full sm:max-w-xl overflow-y-auto"
        data-testid="snapshots-drawer"
      >
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FileSignature size={20} className="text-emerald-700" />
            Documento Institucional do Diário
          </SheetTitle>
          <SheetDescription>
            {className ? `Turma: ${className}.` : ''} Emita, acompanhe, assine e
            consulte a verificabilidade pública dos diários.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-5 space-y-5">
          {/* Card de emissão */}
          <Card
            className="border-emerald-300 bg-emerald-50/40"
            data-testid="emit-card"
          >
            <CardContent className="p-4">
              <div className="text-[11px] uppercase tracking-wide text-emerald-800 font-medium">
                Período atual
              </div>
              <div className="text-sm font-semibold text-gray-900 mt-0.5">
                {periodLabel || `${periodFrom} → ${periodTo}`}
              </div>
              <p className="text-[12px] text-gray-700 mt-2">
                Ao emitir o documento, o sistema congela o conteúdo do período,
                gera o PDF institucional com QR de verificação pública e
                prepara para assinatura.
              </p>
              {periodActive ? (
                <div
                  className="mt-3 text-[11px] text-emerald-900 bg-white border border-emerald-200 rounded px-2 py-1.5"
                  data-testid="period-active-notice"
                >
                  Já existe um documento{' '}
                  <strong>{STATUS_META[periodActive.status]?.label}</strong>{' '}
                  para este período. Consulte abaixo.
                </div>
              ) : (
                <Button
                  className="mt-3 w-full bg-emerald-700 hover:bg-emerald-800 text-white"
                  disabled={emitting || !classId}
                  onClick={handleEmit}
                  data-testid="emit-button"
                >
                  {emitting ? (
                    <Loader2 size={14} className="animate-spin mr-2" />
                  ) : (
                    <FilePlus2 size={14} className="mr-2" />
                  )}
                  Emitir documento do período
                </Button>
              )}
            </CardContent>
          </Card>

          {/* Lista de snapshots */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-900">
                Documentos emitidos
              </h3>
              <span
                className="text-[10px] text-gray-500"
                data-testid="snapshots-count"
              >
                {snapshots.length} no total
              </span>
            </div>

            {loading && (
              <div
                className="text-center py-6 text-gray-500"
                data-testid="snapshots-loading"
              >
                <Loader2 size={18} className="animate-spin inline mr-2" />
                Carregando…
              </div>
            )}

            {!loading && sortedSnapshots.length === 0 && (
              <div
                className="text-center py-6 text-sm text-gray-500 bg-gray-50 rounded border border-dashed border-gray-300"
                data-testid="snapshots-empty"
              >
                Nenhum documento emitido ainda para esta turma.
              </div>
            )}

            {!loading && sortedSnapshots.length > 0 && (
              <div className="space-y-3" data-testid="snapshots-list">
                {sortedSnapshots.map((snap) => (
                  <SnapshotCard
                    key={snap.id}
                    snap={snap}
                    onChanged={fetchSnapshots}
                    busy={busyKeys}
                    setBusy={setBusy}
                    signatureImage={signatureImage}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
