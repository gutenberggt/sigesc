/**
 * SilentModeToggle — Botão de Modo Silencioso no header.
 * Mostra sino normal quando ativo é 'som ON'; sino riscado + badge com horário quando silenciado.
 * Popover oferece 15, 30, 60 e 120 minutos, ou desativar.
 */
import { useEffect, useState } from 'react';
import { Bell, BellOff } from 'lucide-react';
import { isSilentModeActive, getSilentUntil, activateSilentMode, deactivateSilentMode, formatSilentUntil } from '@/utils/silentMode';

const OPTIONS = [
  { label: '15 min', minutes: 15 },
  { label: '30 min', minutes: 30 },
  { label: '1 hora', minutes: 60 },
  { label: '2 horas', minutes: 120 },
];

export const SilentModeToggle = () => {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(isSilentModeActive());
  const [until, setUntil] = useState(getSilentUntil());

  useEffect(() => {
    const refresh = () => {
      setActive(isSilentModeActive());
      setUntil(getSilentUntil());
    };
    // Atualiza a cada 30s (para quando o timeout expira)
    const interval = setInterval(refresh, 30000);
    window.addEventListener('silent-mode-changed', refresh);
    return () => {
      clearInterval(interval);
      window.removeEventListener('silent-mode-changed', refresh);
    };
  }, []);

  const handleActivate = (minutes) => {
    activateSilentMode(minutes);
    setOpen(false);
  };

  const handleDeactivate = () => {
    deactivateSilentMode();
    setOpen(false);
  };

  return (
    <div className="relative" data-testid="silent-mode-toggle">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md transition-colors text-xs font-medium ${
          active
            ? 'bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100'
            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
        }`}
        title={active ? `Mensagens silenciadas até ${formatSilentUntil(until)}` : 'Silenciar bips das mensagens'}
        data-testid="silent-mode-button"
      >
        {active ? (
          <>
            <BellOff size={16} />
            <span className="hidden md:inline">até {formatSilentUntil(until)}</span>
          </>
        ) : (
          <Bell size={16} />
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-md shadow-lg z-50" data-testid="silent-mode-menu">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500 border-b border-gray-100">
            Silenciar bips de mensagens
          </div>
          {active && (
            <>
              <div className="px-3 py-2 text-xs text-amber-700 bg-amber-50 flex items-center gap-1.5">
                <BellOff size={12} />
                <span>Ativo até {formatSilentUntil(until)}</span>
              </div>
              <button
                onClick={handleDeactivate}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 text-gray-700 border-b border-gray-100"
                data-testid="silent-mode-deactivate"
              >
                Reativar bips de mensagens
              </button>
            </>
          )}
          {OPTIONS.map((opt) => (
            <button
              key={opt.minutes}
              onClick={() => handleActivate(opt.minutes)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 text-gray-700"
              data-testid={`silent-mode-option-${opt.minutes}`}
            >
              Silenciar bips por {opt.label}
            </button>
          ))}
          <div className="px-3 py-2 text-[10px] text-gray-500 border-t border-gray-100 italic">
            Nota: as notificações visuais continuam aparecendo normalmente.
          </div>
        </div>
      )}
    </div>
  );
};

export default SilentModeToggle;
