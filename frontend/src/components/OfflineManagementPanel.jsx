import { useState, useEffect } from 'react';
import { useOffline } from '@/contexts/OfflineContext';
import { useOfflineSync } from '@/hooks/useOfflineSync';
import { db, countPendingSyncItems, clearAllData } from '@/db/database';
import { useLiveQuery } from 'dexie-react-hooks';
import { 
  Cloud, CloudOff, RefreshCw, Database, Trash2, 
  CheckCircle, AlertCircle, WifiOff, Download, Upload,
  ChevronDown, ChevronUp, HardDrive
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';

/**
 * Painel completo de gerenciamento offline
 * Mostra status de conexão, dados em cache, pendências e permite sincronização manual
 */
export function OfflineManagementPanel({ academicYear, classId }) {
  const { isOnline, pendingSyncCount, syncStatus, syncProgress, triggerSync, lastSyncTime } = useOffline();
  const { syncing, progress, error, syncAll, syncClass } = useOfflineSync();
  const [expanded, setExpanded] = useState(false);
  const [clearing, setClearing] = useState(false);

  // Contagem de registros no cache local
  const cacheStats = useLiveQuery(async () => {
    const [grades, attendance, students, classes, courses] = await Promise.all([
      db.grades.count(),
      db.attendance.count(),
      db.students.count(),
      db.classes.count(),
      db.courses.count()
    ]);
    return { grades, attendance, students, classes, courses };
  }, [], { grades: 0, attendance: 0, students: 0, classes: 0, courses: 0 });

  // Formata última sincronização
  const formatLastSync = () => {
    if (!lastSyncTime) return 'Nunca';
    const now = new Date();
    const diff = Math.floor((now - lastSyncTime) / 1000);
    
    if (diff < 60) return 'Agora';
    if (diff < 3600) return `${Math.floor(diff / 60)}min atrás`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h atrás`;
    return lastSyncTime.toLocaleDateString('pt-BR');
  };

  // Sincroniza dados da turma atual
  const handleSyncClass = async () => {
    if (!classId) {
      toast.error('Selecione uma turma primeiro');
      return;
    }
    
    const success = await syncClass(classId, academicYear);
    if (success) {
      toast.success('Dados da turma sincronizados!');
    } else {
      toast.error('Erro ao sincronizar turma');
    }
  };

  // Sincroniza todos os dados
  const handleSyncAll = async () => {
    const success = await syncAll({ academicYear, classId });
    if (success) {
      toast.success('Todos os dados sincronizados!');
    } else {
      toast.error('Erro na sincronização');
    }
  };

  // Sincroniza fila de pendências
  const handleSyncPending = async () => {
    const result = await triggerSync();
    if (result.success) {
      toast.success(`${result.results?.succeeded || 0} itens sincronizados!`);
    } else {
      toast.error('Erro ao sincronizar pendências');
    }
  };

  // Limpa todos os dados locais
  const handleClearData = async () => {
    if (!window.confirm('Tem certeza? Isso apagará todos os dados offline não sincronizados!')) {
      return;
    }
    
    setClearing(true);
    try {
      await clearAllData();
      toast.success('Dados locais limpos');
    } catch (err) {
      toast.error('Erro ao limpar dados');
    } finally {
      setClearing(false);
    }
  };

  // Status badge
  const StatusBadge = () => {
    if (!isOnline) {
      return (
        <span className="flex items-center gap-1 px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs font-medium">
          <WifiOff className="w-3 h-3" />
          Offline
        </span>
      );
    }
    if (syncStatus === 'syncing' || syncing) {
      return (
        <span className="flex items-center gap-1 px-2 py-1 bg-yellow-100 text-yellow-700 rounded-full text-xs font-medium">
          <RefreshCw className="w-3 h-3 animate-spin" />
          Sincronizando
        </span>
      );
    }
    if (pendingSyncCount > 0) {
      return (
        <span className="flex items-center gap-1 px-2 py-1 bg-orange-100 text-orange-700 rounded-full text-xs font-medium">
          <Upload className="w-3 h-3" />
          {pendingSyncCount} pendente(s)
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">
        <CheckCircle className="w-3 h-3" />
        Sincronizado
      </span>
    );
  };

  return (
    <Card className="mb-4">
      <CardHeader 
        className="cursor-pointer py-3"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-blue-600" />
            <CardTitle className="text-sm font-medium">Modo Offline</CardTitle>
            <StatusBadge />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">
              Última sync: {formatLastSync()}
            </span>
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </div>
      </CardHeader>
      
      {expanded && (
        <CardContent className="pt-0">
          {/* Progresso de sincronização */}
          {(syncStatus === 'syncing' || syncing) && (
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>Sincronizando {progress.collection || syncProgress.current}...</span>
                <span>{progress.current || syncProgress.current}/{progress.total || syncProgress.total}</span>
              </div>
              <Progress 
                value={((progress.current || syncProgress.current) / (progress.total || syncProgress.total || 1)) * 100} 
                className="h-2"
              />
            </div>
          )}

          {/* Estatísticas do cache */}
          <div className="grid grid-cols-5 gap-2 mb-4">
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-lg font-semibold text-blue-600">{cacheStats.students}</div>
              <div className="text-xs text-gray-500">Alunos</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-lg font-semibold text-green-600">{cacheStats.grades}</div>
              <div className="text-xs text-gray-500">Notas</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-lg font-semibold text-purple-600">{cacheStats.attendance}</div>
              <div className="text-xs text-gray-500">Freq.</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-lg font-semibold text-orange-600">{cacheStats.classes}</div>
              <div className="text-xs text-gray-500">Turmas</div>
            </div>
            <div className="text-center p-2 bg-gray-50 rounded">
              <div className="text-lg font-semibold text-teal-600">{cacheStats.courses}</div>
              <div className="text-xs text-gray-500">Comp.</div>
            </div>
          </div>

          {/* Botões de ação */}
          <div className="flex flex-wrap gap-2">
            {pendingSyncCount > 0 && isOnline && (
              <Button 
                size="sm" 
                onClick={handleSyncPending}
                disabled={syncStatus === 'syncing'}
                className="bg-orange-600 hover:bg-orange-700"
              >
                <Upload className="w-4 h-4 mr-1" />
                Enviar {pendingSyncCount} pendência(s)
              </Button>
            )}
            
            {classId && isOnline && (
              <Button 
                size="sm" 
                variant="outline"
                onClick={handleSyncClass}
                disabled={syncing}
              >
                <Download className="w-4 h-4 mr-1" />
                Baixar turma
              </Button>
            )}
            
            {isOnline && (
              <Button 
                size="sm" 
                variant="outline"
                onClick={handleSyncAll}
                disabled={syncing}
              >
                <RefreshCw className={`w-4 h-4 mr-1 ${syncing ? 'animate-spin' : ''}`} />
                Sincronizar tudo
              </Button>
            )}
            
            <Button 
              size="sm" 
              variant="ghost"
              onClick={handleClearData}
              disabled={clearing || syncing}
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <Trash2 className="w-4 h-4 mr-1" />
              Limpar cache
            </Button>
          </div>

          {/* Erro */}
          {error && (
            <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}

          {/* Info quando offline */}
          {!isOnline && (
            <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
              <strong>Modo Offline Ativo:</strong> Você pode continuar lançando notas e frequência. 
              Os dados serão sincronizados automaticamente quando a conexão for restaurada.
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

/**
 * Badge compacto para indicar dados offline em cards/tabelas
 */
export function OfflineDataBadge({ isOffline, pendingCount = 0 }) {
  if (!isOffline && pendingCount === 0) return null;

  return (
    <span className={`
      inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium
      ${isOffline ? 'bg-yellow-100 text-yellow-800' : 'bg-orange-100 text-orange-800'}
    `}>
      {isOffline ? (
        <>
          <HardDrive className="w-3 h-3" />
          Dados locais
        </>
      ) : (
        <>
          <Upload className="w-3 h-3" />
          {pendingCount} pendente(s)
        </>
      )}
    </span>
  );
}

/**
 * Indicador inline para campos com dados não sincronizados
 */
export function UnsyncedIndicator({ show = false }) {
  if (!show) return null;
  
  return (
    <span className="inline-block w-2 h-2 bg-orange-500 rounded-full ml-1" title="Não sincronizado" />
  );
}

export default OfflineManagementPanel;
