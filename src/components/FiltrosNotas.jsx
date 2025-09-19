import React from "react";
import "./FiltrosNotas.css";

export default function FiltrosNotas({ filters, setFilters, anosLetivos }) {
  return (
    <div className="filtros-container">
      <div className="filtro-item">
        <label htmlFor="anoLetivo">Ano Letivo</label>
        <select
          id="anoLetivo"
          value={filters.selectedYear || ""}
          onChange={(e) =>
            setFilters({ ...filters, selectedYear: e.target.value })
          }
        >
          <option value="">Selecione</option>
          {anosLetivos.map((ano) => (
            <option key={ano} value={ano}>
              {ano}
            </option>
          ))}
        </select>
      </div>

      <div className="filtro-item">
        <label htmlFor="componente">Componente</label>
        <select
          id="componente"
          value={filters.selectedComponente || ""}
          onChange={(e) =>
            setFilters({ ...filters, selectedComponente: e.target.value })
          }
        >
          <option value="">Selecione</option>
          <option value="matematica">Matemática</option>
          <option value="portugues">Português</option>
          <option value="ciencias">Ciências</option>
        </select>
      </div>
    </div>
  );
}
