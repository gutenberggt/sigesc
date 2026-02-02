import { useState, useRef, useEffect } from 'react';
import { searchCities } from '@/data/brazilianCities';

/**
 * Componente de autocomplete para cidades brasileiras
 * Mostra sugestões a partir do 3º caractere digitado
 */
export const CityAutocomplete = ({ 
  value, 
  onChange, 
  disabled = false, 
  placeholder = "Digite pelo menos 3 letras...",
  className = ""
}) => {
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);

  // Fecha sugestões ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleInputChange = (e) => {
    const inputValue = e.target.value;
    onChange(inputValue);
    
    if (inputValue.length >= 3) {
      const matches = searchCities(inputValue);
      setSuggestions(matches);
      setShowSuggestions(matches.length > 0);
      setHighlightedIndex(-1);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  const handleSuggestionClick = (city) => {
    // Extrai apenas o nome da cidade (remove o estado)
    const cityName = city.split(' - ')[0];
    onChange(cityName);
    setShowSuggestions(false);
    setSuggestions([]);
  };

  const handleKeyDown = (e) => {
    if (!showSuggestions || suggestions.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex(prev => 
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex(prev => prev > 0 ? prev - 1 : 0);
        break;
      case 'Enter':
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
          handleSuggestionClick(suggestions[highlightedIndex]);
        }
        break;
      case 'Escape':
        setShowSuggestions(false);
        break;
      default:
        break;
    }
  };

  return (
    <div ref={wrapperRef} className="relative">
      <input
        ref={inputRef}
        type="text"
        value={value || ''}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (value && value.length >= 3) {
            const matches = searchCities(value);
            setSuggestions(matches);
            setShowSuggestions(matches.length > 0);
          }
        }}
        disabled={disabled}
        placeholder={placeholder}
        className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 ${className}`}
        autoComplete="off"
      />
      
      {showSuggestions && suggestions.length > 0 && (
        <ul className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-auto">
          {suggestions.map((city, index) => (
            <li
              key={city}
              onClick={() => handleSuggestionClick(city)}
              className={`px-3 py-2 cursor-pointer text-sm ${
                index === highlightedIndex 
                  ? 'bg-blue-100 text-blue-800' 
                  : 'hover:bg-gray-100'
              }`}
            >
              {city}
            </li>
          ))}
        </ul>
      )}
      
      {value && value.length > 0 && value.length < 3 && (
        <p className="text-xs text-gray-500 mt-1">
          Digite pelo menos 3 caracteres para ver sugestões
        </p>
      )}
    </div>
  );
};

export default CityAutocomplete;
