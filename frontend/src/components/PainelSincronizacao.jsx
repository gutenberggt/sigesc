import { useState, useEffect, useCallback } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import {
  Wifi, WifiOff, CheckCircle2, AlertTriangle, RefreshCw,
  Clock, CloudOff, ChevronDown, ChevronUp
} from 'lucide-react';

// Termos em português claro para o professor (sem jargão técnico).
const CATEGORIA_LABELS = {
  attendance: 'Frequência',
  grades: 'Notas',
  students: 'Cadastro de alunos',
  learning_objects: 'Planejamento',
  planning: 'Planejamento',
  outros: 'Outros lançamentos',
};

// Categorias sempre exibidas — tranquilizam o professor mesmo quando está tudo enviado.
const CATEGORIAS_FIXAS = ['attendance', 'grades'];

function tempoRelativo(date) {
  if (!date) return 'ainda não houve envio';
  const d = date instanceof Date ? date : new Date(date);
  if (isNaN(d.getTime())) return 'ainda não houve envio';
  const min = Math.floor((Date.now() - d.getTime()) / 60000);
  if (min < 1) return 'agora mesmo';
  if (min < 60) return `há ${min} ${min === 1 ? 'minuto' : 'minutos'}`;
  const horas = Math.floor(min / 60);
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);
  const hhmm = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === hoje.toDateString()) {
    return horas < 6 ? `há ${horas} ${horas === 1 ? 'hora' : 'horas'}` : `hoje às ${hhmm}`;
  }
  if (d.toDateString() === ontem.toDateString()) return `ontem às ${hhmm}`;
  return `${d.toLocaleDateString('pt-BR')} às ${hhmm}`;
}

const CategoriaItem = ({ chave, dados }) => {
  const label = CATEGORIA_LABELS[chave] || CATEGORIA_LABELS.outros;
  const falhas = dados?.failed || 0;
  const pendentes = dados?.pending || 0;

  let icon, texto, cor;
  if (falhas > 0) {
    icon = <AlertTriangle className="h-4 w-4" />;
    texto = `${falhas} não enviada${falhas > 1 ? 's' : ''}`;
    cor = 'text-red-600';
  } else if (pendentes > 0) {
    icon = <Clock className="h-4 w-4" />;
    texto = `${pendentes} aguardando envio`;
    cor = 'text-amber-600';
  } else {
    icon = <CheckCircle2 className="h-4 w-4" />;
    texto = 'Tudo enviado';
    cor = 'text-green-600';
  }

  return (
    <div className="flex items-center justify-between py-1.5" data-testid={`sinc-categoria-${chave}`}>
      <span className="text-sm text-gray-700">{label}</span>
      <span className={`flex items-center gap-1.5 text-sm font-medium ${cor}`}>
        {icon}
        {texto}
      </span>
    </div>
  );
};

/**
 * Painel de Sincronização — núcleo do módulo offline.
 * Dá ao professor a certeza de que nada se perdeu: status da conexão,
 * última vez que os dados foram enviados, o que está pendente por categoria,
 * um botão manual e os detalhes de eventuais falhas.
 */
export const PainelSincronizacao = ({ className = '' }) => {
  const {
    isOnline, pendingSyncCount, pendingByCategory, failedSyncCount,
    lastSyncTime, syncStatus, triggerSync, retryFailedSync,
    getFailedItems, updatePendingCount,
  } = useOffline();

  const [verDetalhes, setVerDetalhes] = useState(false);
  const [falhas, setFalhas] = useState([]);

  const sincronizando = syncStatus === 'syncing';
  const totalPendentes = pendingSyncCount || 0;
  const totalFalhas = failedSyncCount || 0;

  useEffect(() => { updatePendingCount?.(); }, [updatePendingCount]);

  const carregarFalhas = useCallback(async () => {
    const items = await getFailedItems();
    setFalhas(items || []);
  }, [getFailedItems]);

  const toggleDetalhes = async () => {
    const novo = !verDetalhes;
    setVerDetalhes(novo);
    if (novo) await carregarFalhas();
  };

  const handleSincronizar = async () => {
    await triggerSync();
  };

  const handleTentarNovamente = async () => {
    await retryFailedSync();
    await carregarFalhas();
  };

  const categorias = Array.from(
    new Set([...CATEGORIAS_FIXAS, ...Object.keys(pendingByCategory || {})])
  );

  // Estado geral (prioriza offline → falha → pendente → ok)
  let estado = 'ok';
  if (totalFalhas > 0) estado = 'falha';
  else if (totalPendentes > 0) estado = 'pendente';
  if (!isOnline) estado = 'offline';

  const RESUMO = {
    offline: {
      icon: <CloudOff className="h-6 w-6 text-amber-500" />,
      titulo: 'Você está sem internet',
      detalhe: 'Pode continuar lançando normalmente. Tudo fica salvo no aparelho e será enviado sozinho quando a conexão voltar.',
      cor: 'bg-amber-50 border-amber-200',
    },
    falha: {
      icon: <AlertTriangle className="h-6 w-6 text-red-500" />,
      titulo: `${totalFalhas} lançamento${totalFalhas > 1 ? 's' : ''} não enviado${totalFalhas > 1 ? 's' : ''}`,
      detalhe: 'Toque em "Ver detalhes" para entender e tentar novamente.',
      cor: 'bg-red-50 border-red-200',
    },
    pendente: {
      icon: <Clock className="h-6 w-6 text-amber-500" />,
      titulo: `${totalPendentes} alteração${totalPendentes > 1 ? 'ões' : ''} aguardando envio`,
      detalhe: 'Estão salvas no aparelho. Toque em "Sincronizar Agora" ou aguarde o envio automático.',
      cor: 'bg-amber-50 border-amber-200',
    },
    ok: {
      icon: <CheckCircle2 className="h-6 w-6 text-green-500" />,
      titulo: 'Tudo salvo e enviado',
      detalhe: 'Seus lançamentos estão seguros no servidor.',
      cor: 'bg-green-50 border-green-200',
    },
  }[estado];

  return (
    <div
      className={`rounded-xl border bg-white shadow-sm overflow-hidden ${className}`}
      data-testid="painel-sincronizacao"
    >
      {/* Cabeçalho com status de conexão */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b bg-gray-50">
        <span className="text-sm font-semibold text-gray-800">Seus lançamentos</span>
        <span
          className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
            isOnline ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
          }`}
          data-testid="sinc-status-conexao"
        >
          {isOnline ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
          {isOnline ? 'Conectado' : 'Sem internet'}
        </span>
      </div>

      {/* Resumo principal */}
      <div className={`flex items-start gap-3 px-4 py-3 border-b ${RESUMO.cor}`} data-testid="sinc-resumo">
        {RESUMO.icon}
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900">{RESUMO.titulo}</p>
          <p className="text-xs text-gray-600 mt-0.5">{RESUMO.detalhe}</p>
        </div>
      </div>

      {/* Última vez enviado */}
      <div className="px-4 py-2 text-xs text-gray-500 border-b flex items-center gap-1.5" data-testid="sinc-ultimo-envio">
        <Clock className="h-3.5 w-3.5" />
        Última vez enviado: <span className="font-medium text-gray-700">{tempoRelativo(lastSyncTime)}</span>
      </div>

      {/* Detalhe por categoria */}
      <div className="px-4 py-2 divide-y divide-gray-100">
        {categorias.map((c) => (
          <CategoriaItem key={c} chave={c} dados={(pendingByCategory || {})[c]} />
        ))}
      </div>

      {/* Ação manual */}
      <div className="px-4 py-3 border-t bg-gray-50">
        <button
          onClick={handleSincronizar}
          disabled={!isOnline || sincronizando}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          data-testid="sinc-botao-sincronizar"
        >
          <RefreshCw className={`h-4 w-4 ${sincronizando ? 'animate-spin' : ''}`} />
          {sincronizando ? 'Enviando...' : 'Sincronizar Agora'}
        </button>
        {!isOnline && (
          <p className="text-xs text-center text-gray-500 mt-2">
            O envio acontece automaticamente quando a internet voltar.
          </p>
        )}

        {(totalFalhas > 0 || verDetalhes) && (
          <button
            onClick={toggleDetalhes}
            className="w-full flex items-center justify-center gap-1.5 mt-2 text-xs font-medium text-gray-600 hover:text-gray-900"
            data-testid="sinc-ver-detalhes"
          >
            {verDetalhes ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {verDetalhes ? 'Ocultar detalhes' : 'Ver detalhes'}
          </button>
        )}
      </div>

      {/* Detalhes das falhas */}
      {verDetalhes && (
        <div className="px-4 py-3 border-t bg-white" data-testid="sinc-detalhes-falhas">
          {falhas.length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-2">Nenhuma falha registrada. 🎉</p>
          ) : (
            <>
              <ul className="space-y-2 mb-3">
                {falhas.map((f, i) => (
                  <li key={f.id || i} className="text-xs bg-red-50 rounded-lg px-3 py-2" data-testid="sinc-item-falha">
                    <div className="font-medium text-red-700">
                      {CATEGORIA_LABELS[f.collection] || CATEGORIA_LABELS.outros}
                      {f.timestamp ? ` · ${tempoRelativo(f.timestamp)}` : ''}
                    </div>
                    {f.lastError && <div className="text-red-500 mt-0.5 break-words">{f.lastError}</div>}
                  </li>
                ))}
              </ul>
              <button
                onClick={handleTentarNovamente}
                disabled={!isOnline || sincronizando}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-amber-700 bg-amber-100 hover:bg-amber-200 disabled:opacity-50 transition-colors"
                data-testid="sinc-tentar-novamente"
              >
                <RefreshCw className="h-4 w-4" />
                Tentar enviar novamente
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default PainelSincronizacao;
