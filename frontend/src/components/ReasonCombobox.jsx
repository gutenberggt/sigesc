/**
 * ReasonCombobox — Combobox pesquisável agrupado para Motivos MEC
 *
 * Decisão arquitetural (Fev/2026 P0 — Refatoração Bolsa Família Motivos MEC):
 *   - Combobox ÚNICO pesquisável com agrupamento visual (não dois selects).
 *   - Suporta busca por nome, código MEC e subcódigo (3a, 11a, …).
 *   - Navegação por teclado via shadcn Command.
 *   - Mostra disabled/desabilitado quando frequência ≥ 75%.
 */
import { useEffect, useMemo, useState } from 'react';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

export function ReasonCombobox({
  value,
  onChange,
  groups,
  disabled = false,
  placeholder = 'Selecione o motivo MEC...',
  required = false,
  testIdPrefix = 'reason',
  resolvedLabel,
}) {
  const [open, setOpen] = useState(false);

  // Index plano para encontrar o label do valor selecionado
  const reasonsIndex = useMemo(() => {
    const idx = new Map();
    (groups || []).forEach((g) => {
      (g.reasons || []).forEach((r) => {
        idx.set(r.id, { ...r, group_name: g.name, group_mec_code: g.mec_code });
      });
    });
    return idx;
  }, [groups]);

  // Permite preview por label vindo do banco (legado/cached) quando o id não está no índice
  const currentReason = value ? reasonsIndex.get(value) : null;
  const buttonLabel = currentReason
    ? `${currentReason.mec_subcode} • ${currentReason.name}`
    : resolvedLabel || placeholder;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-required={required}
          disabled={disabled}
          data-testid={`${testIdPrefix}-combobox-trigger`}
          className={cn(
            'w-full flex items-center justify-between gap-2 border rounded px-3 py-2 text-sm text-left',
            'bg-white hover:bg-gray-50 transition-colors',
            'disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed',
            !currentReason && !resolvedLabel ? 'text-gray-400' : 'text-gray-900',
            required && !currentReason && !disabled ? 'border-amber-400' : 'border-gray-300',
          )}
        >
          <span className="truncate">{buttonLabel}</span>
          <div className="flex items-center gap-1 shrink-0">
            {currentReason && !disabled ? (
              <X
                size={14}
                className="text-gray-400 hover:text-gray-700"
                onClick={(e) => {
                  e.stopPropagation();
                  onChange(null);
                }}
                data-testid={`${testIdPrefix}-combobox-clear`}
              />
            ) : null}
            <ChevronsUpDown size={14} className="text-gray-400" />
          </div>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[460px] p-0"
        align="start"
        data-testid={`${testIdPrefix}-combobox-popover`}
      >
        <Command
          filter={(itemValue, search) => {
            // itemValue contém "mec_subcode|mec_group_code|name|group_name" lowercased
            const term = search.toLowerCase().trim();
            if (!term) return 1;
            return itemValue.includes(term) ? 1 : 0;
          }}
        >
          <CommandInput
            placeholder="Buscar motivo, código (ex: 3a, 11a)..."
            data-testid={`${testIdPrefix}-combobox-search`}
          />
          <CommandList className="max-h-[420px]">
            <CommandEmpty>Nenhum motivo encontrado.</CommandEmpty>
            {(groups || []).map((g, gIdx) => (
              <CommandGroup
                key={g.group_id}
                heading={`${g.mec_code}. ${g.name}`}
              >
                {(g.reasons || []).map((r) => {
                  const searchKey = [
                    r.mec_subcode,
                    r.mec_group_code,
                    r.name,
                    g.name,
                  ].join('|').toLowerCase();
                  return (
                    <CommandItem
                      key={r.id}
                      value={searchKey}
                      onSelect={() => {
                        onChange(r.id);
                        setOpen(false);
                      }}
                      data-testid={`${testIdPrefix}-combobox-item-${r.mec_subcode}`}
                    >
                      <Check
                        className={cn(
                          'mr-2 h-4 w-4',
                          value === r.id ? 'opacity-100' : 'opacity-0',
                        )}
                      />
                      <span className="font-mono text-xs text-gray-500 w-12">
                        {r.mec_subcode}
                      </span>
                      <span className="flex-1">{r.name}</span>
                    </CommandItem>
                  );
                })}
                {gIdx < (groups.length - 1) && <CommandSeparator />}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default ReasonCombobox;
