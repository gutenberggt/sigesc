import React, { useState, useEffect, useRef } from "react";

function CustomDropdown({ options, value, onChange, placeholder }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const handleSelect = (optionValue) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  const selectedOption = options.find((opt) => opt.value === value);

  // Efeito para fechar o dropdown ao clicar fora dele
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <div className="relative w-full" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-2 border border-gray-300 rounded-md bg-white text-left h-full flex items-center"
      >
        {selectedOption ? (
          <div>
            <strong className="block text-sm leading-tight">
              {selectedOption.subject}
            </strong>
            <span className="text-xs text-gray-500 leading-tight">
              {selectedOption.teacher}
            </span>
          </div>
        ) : (
          <span className="text-gray-500">{placeholder}</span>
        )}
      </button>

      {isOpen && (
        <div className="absolute z-10 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-y-auto">
          {/* Opção para limpar a seleção */}
          <div
            onClick={() => handleSelect("")}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 cursor-pointer"
          >
            {placeholder}
          </div>
          {/* Mapeia as opções recebidas */}
          {options.map((option) => (
            <div
              key={option.value}
              onClick={() => handleSelect(option.value)}
              className="px-4 py-2 hover:bg-gray-100 cursor-pointer"
            >
              <strong className="block text-sm leading-tight">
                {option.subject}
              </strong>
              <span className="text-xs text-gray-500 leading-tight">
                {option.teacher}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CustomDropdown;
