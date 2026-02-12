import { useState, useEffect } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import { db, getPendingSyncItems } from '@/db/database';
import { useLiveQuery } from 'dexie-react-hooks';
import { syncService } from '@/services/syncService';
import { 
  Cloud, CloudOff, RefreshCw, CheckCircle, AlertCircle, 
  Clock, Upload, Trash2, ChevronDown, ChevronUp,
  FileText, Users, Calendar, X, Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';

/**
 * Componente de Status de Sincronização Detalhado
 * Mostra progresso, lista de pendências e permite gerenciar a fila
 */
export function SyncStatusPanel() {
  const { isOnline, syncStatus, lastSyncTime, triggerSync } = useOffline();
  const [expanded, setExpanded] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [serverStatus, setServerStatus] = useState(null);

  // Lista de itens pendentes de sincronização (atualização em tempo real)
  const pendingItems = useLiveQuery(
    () => db.syncQueue.where('status').anyOf(['pending', 'failed']).toArray(),
    [],
    []
  );

  // Busca status do servidor
  useEffect(() => {
    if (isOnline && expanded) {
      fetchServerStatus();
    }
  }, [isOnline, expanded]);

  const fetchServerStatus = async () => {
    const result = await syncService.getServerStatus();
    if (result.success) {
      setServerStatus(result.data);
    }
  };

  // Processa sincronização
  const handleSync = async () => {
    if (!isOnline) {
      toast.error('Sem conexão com internet');
      return;
    }

    setSyncing(true);
    setProgress({ current: 0, total: pendingItems?.length || 0 });

    try {
      const result = await triggerSync();
      
      if (result.success) {
        toast.success(`Sincronização concluída! ${result.results?.succeeded || 0} item(ns) enviados.`);
        fetchServerStatus();
      } else {
        toast.error(result.error || 'Erro na sincronização');
      }
    } catch (err) {
      toast.error('Erro ao sincronizar');
    } finally {
      setSyncing(false);
    }
  };

  // Remove item da fila
  const handleRemoveItem = async (itemId) => {
    try {
      await db.syncQueue.delete(itemId);
      toast.success('Item removido da fila');
    } catch (err) {
      toast.error('Erro ao remover item');
    }
  };

  // Limpa itens com falha
  const handleClearFailed = async () => {
    try {
      await db.syncQueue.where('status').equals('failed').delete();
      toast.success('Itens com falha removidos');
    } catch (err) {
      toast.error('Erro ao limpar itens');
    }
  };

  // Retenta itens com falha
  const handleRetryFailed = async () => {
    try {
      await db.syncQueue
        .where('status').equals('failed')
        .modify({ status: 'pending', retries: 0, lastError: null });
      toast.success('Itens marcados para reenvio');
    } catch (err) {
      toast.error('Erro ao remarcar itens');
    }
  };

  // Formata timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString('pt-BR', { 
      day: '2-digit', 
      month: '2-digit', 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  // Ícone por coleção
  const getCollectionIcon = (collection) => {
    switch (collection) {
      case 'grades': return <FileText className="w-4 h-4 text-blue-500" />;
      case 'attendance': return <Calendar className="w-4 h-4 text-green-500" />;
      case 'students': return <Users className="w-4 h-4 text-purple-500" />;
      default: return <FileText className="w-4 h-4 text-gray-500" />;
    }
  };

  // Nome da operação
  const getOperationLabel = (operation) => {
    switch (operation) {
      case 'create': return 'Criar';
      case 'update': return 'Atualizar';
      case 'delete': return 'Excluir';
      default: return operation;
    }
  };

  // Conta itens por status
  const pendingCount = pendingItems?.filter(i => i.status === 'pending').length || 0;
  const failedCount = pendingItems?.filter(i => i.status === 'failed').length || 0;

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      {/* Header - sempre visível */}
      <div 
        className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          {/* Status de conexão */}
          {isOnline ? (
            <Cloud className="w-5 h-5 text-green-500" />
          ) : (
            <CloudOff className="w-5 h-5 text-red-500" />
          )}
          
          <div>
            <h3 className="font-medium text-gray-900">
              {isOnline ? 'Online' : 'Offline'}
            </h3>
            <p className="text-xs text-gray-500">
              Última sync: {lastSyncTime ? formatTime(lastSyncTime) : 'Nunca'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Badge de pendências */}
          {pendingCount > 0 && (
            <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded-full flex items-center gap-1">
              <Upload className="w-3 h-3" />
              {pendingCount} pendente(s)
            </span>
          )}
          
          {failedCount > 0 && (
            <span className="px-2 py-1 bg-red-100 text-red-700 text-xs font-medium rounded-full flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {failedCount} erro(s)
            </span>
          )}

          {pendingCount === 0 && failedCount === 0 && (
            <span className="px-2 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-full flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              Sincronizado
            </span>
          )}

          {expanded ? (
            <ChevronUp className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </div>

      {/* Conteúdo expandido */}
      {expanded && (
        <div className="border-t p-4 space-y-4">
          {/* Barra de progresso durante sincronização */}
          {syncing && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">Sincronizando...</span>
                <span className="text-gray-500">
                  {progress.current}/{progress.total}
                </span>
              </div>
              <Progress value={progress.total > 0 ? (progress.current / progress.total) * 100 : 0} />
            </div>
          )}

          {/* Ações */}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={handleSync}
              disabled={syncing || !isOnline || (pendingCount === 0 && failedCount === 0)}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {syncing ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-1" />
              )}
              Sincronizar agora
            </Button>

            {failedCount > 0 && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRetryFailed}
                  disabled={syncing}
                >
                  <RefreshCw className="w-4 h-4 mr-1" />
                  Tentar novamente ({failedCount})
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleClearFailed}
                  disabled={syncing}
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="w-4 h-4 mr-1" />
                  Limpar erros
                </Button>
              </>
            )}
          </div>

          {/* Status do servidor */}
          {serverStatus && (
            <div className="bg-gray-50 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Dados no Servidor</h4>
              <div className="grid grid-cols-5 gap-2 text-center text-xs">
                <div>
                  <div className="font-semibold text-gray-900">{serverStatus.collections.grades}</div>
                  <div className="text-gray-500">Notas</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-900">{serverStatus.collections.attendance}</div>
                  <div className="text-gray-500">Freq.</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-900">{serverStatus.collections.students}</div>
                  <div className="text-gray-500">Alunos(as)</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-900">{serverStatus.collections.classes}</div>
                  <div className="text-gray-500">Turmas</div>
                </div>
                <div>
                  <div className="font-semibold text-gray-900">{serverStatus.collections.courses}</div>
                  <div className="text-gray-500">Comp.</div>
                </div>
              </div>
            </div>
          )}

          {/* Lista de itens pendentes */}
          {pendingItems && pendingItems.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-700 mb-2">
                Fila de Sincronização ({pendingItems.length})
              </h4>
              <div className="max-h-60 overflow-y-auto space-y-2">
                {pendingItems.map((item) => (
                  <div 
                    key={item.id}
                    className={`flex items-center justify-between p-2 rounded-lg text-sm ${
                      item.status === 'failed' 
                        ? 'bg-red-50 border border-red-200' 
                        : 'bg-gray-50 border border-gray-200'
                    }`}
                  >
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      {getCollectionIcon(item.collection)}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium capitalize">{item.collection}</span>
                          <span className={`px-1.5 py-0.5 text-xs rounded ${
                            item.operation === 'create' ? 'bg-green-100 text-green-700' :
                            item.operation === 'update' ? 'bg-blue-100 text-blue-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            {getOperationLabel(item.operation)}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 truncate">
                          ID: {item.recordId?.substring(0, 20)}...
                        </div>
                        {item.lastError && (
                          <div className="text-xs text-red-600 truncate">
                            Erro: {item.lastError}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2 ml-2">
                      {item.status === 'failed' && (
                        <span className="text-xs text-red-600">
                          {item.retries}x
                        </span>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveItem(item.id);
                        }}
                        className="p-1 hover:bg-gray-200 rounded"
                        title="Remover da fila"
                      >
                        <X className="w-4 h-4 text-gray-400" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mensagem quando não há pendências */}
          {(!pendingItems || pendingItems.length === 0) && (
            <div className="text-center py-4 text-gray-500">
              <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-500" />
              <p className="text-sm">Todos os dados estão sincronizados!</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SyncStatusPanel;
