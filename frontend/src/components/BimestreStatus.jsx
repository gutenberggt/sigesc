import { AlertCircle, Lock, Unlock, Calendar } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

/**
 * Badge que indica se um bimestre está aberto ou bloqueado para edição
 */
export const BimestreStatusBadge = ({ bimestreInfo, showLabel = true, size = 'default' }) => {
  if (!bimestreInfo) return null;

  const { bimestre, pode_editar, data_limite, motivo } = bimestreInfo;

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${day}/${month}/${year}`;
  };

  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    default: 'text-xs px-2 py-1',
    lg: 'text-sm px-3 py-1.5'
  };

  if (pode_editar) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge 
              variant="outline" 
              className={`bg-green-50 text-green-700 border-green-200 ${sizeClasses[size]}`}
            >
              <Unlock className="w-3 h-3 mr-1" />
              {showLabel && `${bimestre}º Bim`}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <p className="font-medium">{bimestre}º Bimestre - Aberto</p>
            {data_limite && (
              <p className="text-xs text-gray-500">Limite: {formatDate(data_limite)}</p>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant="outline" 
            className={`bg-red-50 text-red-700 border-red-200 ${sizeClasses[size]}`}
          >
            <Lock className="w-3 h-3 mr-1" />
            {showLabel && `${bimestre}º Bim`}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p className="font-medium">{bimestre}º Bimestre - Bloqueado</p>
          <p className="text-xs text-red-500">{motivo}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

/**
 * Alerta que mostra bimestres bloqueados
 */
export const BimestreBlockedAlert = ({ blockedBimestres, className = '' }) => {
  if (!blockedBimestres || blockedBimestres.length === 0) return null;

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${day}/${month}/${year}`;
  };

  return (
    <Alert variant="destructive" className={`bg-red-50 border-red-200 ${className}`}>
      <AlertCircle className="h-4 w-4 text-red-600" />
      <AlertDescription className="text-red-800">
        <span className="font-medium">Atenção:</span> O prazo para edição encerrou para:
        <ul className="mt-1 ml-4 list-disc">
          {blockedBimestres.map(b => (
            <li key={b.bimestre}>
              <strong>{b.bimestre}º Bimestre</strong>
              {b.data_limite && ` (limite: ${formatDate(b.data_limite)})`}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs">Apenas Administradores e Secretários podem editar após o prazo.</p>
      </AlertDescription>
    </Alert>
  );
};

/**
 * Alerta informativo que mostra a data limite dos bimestres ABERTOS
 * Exibe para o professor a data limite ANTES de encerrar o prazo
 */
export const BimestreDeadlineAlert = ({ editStatus, className = '' }) => {
  if (!editStatus || !editStatus.bimestres) return null;

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${day}/${month}/${year}`;
  };

  // Filtrar apenas bimestres ABERTOS que têm data limite configurada
  const openBimestresWithDeadline = editStatus.bimestres.filter(
    b => b.pode_editar && b.data_limite
  );

  if (openBimestresWithDeadline.length === 0) return null;

  // Calcular dias restantes para o bimestre mais próximo de encerrar
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  const bimestresWithDaysLeft = openBimestresWithDeadline.map(b => {
    const deadlineDate = new Date(b.data_limite + 'T23:59:59');
    const diffTime = deadlineDate - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return { ...b, diasRestantes: diffDays };
  }).sort((a, b) => a.diasRestantes - b.diasRestantes);

  const closestDeadline = bimestresWithDaysLeft[0];
  const isUrgent = closestDeadline.diasRestantes <= 7;
  const isVeryUrgent = closestDeadline.diasRestantes <= 3;

  // Determinar cor do alerta baseado na urgência
  const alertClass = isVeryUrgent 
    ? 'bg-orange-50 border-orange-300'
    : isUrgent 
      ? 'bg-yellow-50 border-yellow-200'
      : 'bg-blue-50 border-blue-200';

  const textClass = isVeryUrgent
    ? 'text-orange-800'
    : isUrgent
      ? 'text-yellow-800'
      : 'text-blue-800';

  const iconClass = isVeryUrgent
    ? 'text-orange-600'
    : isUrgent
      ? 'text-yellow-600'
      : 'text-blue-600';

  return (
    <Alert className={`${alertClass} ${className}`}>
      <Calendar className={`h-4 w-4 ${iconClass}`} />
      <AlertDescription className={textClass}>
        <span className="font-medium">
          {isVeryUrgent ? '⚠️ Prazo próximo!' : isUrgent ? '📅 Atenção ao prazo:' : '📅 Prazos de edição:'}
        </span>
        <ul className="mt-1 ml-4 list-disc">
          {bimestresWithDaysLeft.map(b => (
            <li key={b.bimestre}>
              <strong>{b.bimestre}º Bimestre</strong>: até <strong>{formatDate(b.data_limite)}</strong>
              {b.diasRestantes === 0 && <span className="text-red-600 font-semibold"> (último dia!)</span>}
              {b.diasRestantes === 1 && <span className="text-orange-600 font-semibold"> (amanhã!)</span>}
              {b.diasRestantes > 1 && b.diasRestantes <= 7 && (
                <span className="text-yellow-700"> ({b.diasRestantes} dias restantes)</span>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs opacity-80">Após a data limite, somente Administradores e Secretários poderão editar.</p>
      </AlertDescription>
    </Alert>
  );
};

/**
 * Linha de status compacta para mostrar todos os bimestres
 */
export const BimestreStatusRow = ({ editStatus, loading }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Calendar className="w-4 h-4 animate-pulse" />
        <span>Verificando status...</span>
      </div>
    );
  }

  if (!editStatus || !editStatus.bimestres) return null;

  // Se pode editar todos, mostra uma versão simplificada
  if (editStatus.pode_editar_todos) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Status de edição:</span>
        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 text-xs">
          <Unlock className="w-3 h-3 mr-1" />
          Todos os bimestres abertos
        </Badge>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-gray-500">Status:</span>
      {editStatus.bimestres.map(b => (
        <BimestreStatusBadge key={b.bimestre} bimestreInfo={b} size="sm" />
      ))}
    </div>
  );
};

/**
 * Indicador inline para campos de input
 */
export const BimestreFieldIndicator = ({ bimestre, canEdit, dataLimite }) => {
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${day}/${month}/${year}`;
  };

  if (canEdit) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex items-center ml-1">
            <Lock className="w-3 h-3 text-red-500" />
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">
            Bloqueado - prazo encerrado
            {dataLimite && ` em ${formatDate(dataLimite)}`}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default {
  BimestreStatusBadge,
  BimestreBlockedAlert,
  BimestreStatusRow,
  BimestreFieldIndicator
};
