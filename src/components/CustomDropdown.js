import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * Dropdown acessível com suporte a teclado.
 *
 * Props:
 * - options: Array<{ id?: string|number, subject?: string, teacher?: string, label?: string }>
 * - selectedOption: objeto da lista ou null
 * - onSelect: (option) => void
 * - placeholder: string
 * - disabled: boolean
 */
export default function CustomDropdown({
  options = [],
  selectedOption = null,
  onSelect,
  placeholder = "Selecione...",
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const btnRef = useRef(null);
  const listRef = useRef(null);

  const items = useMemo(
    () =>
      options.map((opt) => ({
        ...opt,
        _label:
          opt.label ??
          [opt.subject, opt.teacher].filter(Boolean).join(" – ") ??
          String(opt),
      })),
    [options]
  );

  useEffect(() => {
    if (!open) setHighlight(-1);
  }, [open]);

  // fecha ao clicar fora
  useEffect(() => {
    function handleDocClick(e) {
      if (
        btnRef.current &&
        !btnRef.current.contains(e.target) &&
        listRef.current &&
        !listRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleDocClick);
    return () => document.removeEventListener("mousedown", handleDocClick);
  }, [open]);

  function handleKeyDown(e) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(true);
        setHighlight(0);
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      btnRef.current?.focus();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(items.length - 1, h + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(0, h - 1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const opt = items[highlight];
      if (opt) {
        onSelect?.(opt);
        setOpen(false);
        btnRef.current?.focus();
      }
    }
  }

  // CORREÇÃO: Quebra de linha aplicada conforme solicitado pelo Prettier.
  const selectedLabel =
    selectedOption &&
    ([selectedOption.subject, selectedOption.teacher]
      .filter(Boolean)
      .join(" – ") ||
      selectedOption.label);

  return (
    <div className="relative inline-block w-full">
      <button
        type="button"
        ref={btnRef}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="w-full border rounded px-3 py-2 bg-white text-left flex items-center justify-between"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={handleKeyDown}
      >
        <span className={selectedLabel ? "" : "text-gray-500"}>
          {selectedLabel || placeholder}
        </span>
        {/* CORREÇÃO: Atributos do SVG quebrados em várias linhas. */}
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="h-5 w-5 shrink-0"
        >
          {/* CORREÇÃO: Atributos do <path> quebrados em várias linhas. */}
          <path
            d="M5.5 7.5l4.5 4.5 4.5-4.5"
            stroke="currentColor"
            fill="none"
          />
        </svg>
      </button>

      {open && (
        <ul
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={
            highlight >= 0 && items[highlight]
              ? `opt-${items[highlight].id ?? highlight}`
              : undefined
          }
          className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-white shadow-lg focus:outline-none"
          onKeyDown={handleKeyDown}
        >
          {items.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-500">Sem opções</li>
          )}
          {items.map((opt, idx) => {
            const id = `opt-${opt.id ?? idx}`;
            const isActive = idx === highlight;
            const isSelected =
              selectedOption &&
              (selectedOption.id ?? selectedOption) === (opt.id ?? opt);
            return (
              <li key={id} id={id} role="option" aria-selected={isSelected}>
                <button
                  type="button"
                  className={`w-full text-left px-3 py-2 ${
                    isActive ? "bg-gray-100" : ""
                  }`}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => {
                    onSelect?.(opt);
                    setOpen(false);
                    btnRef.current?.focus();
                  }}
                >
                  {opt._label}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
