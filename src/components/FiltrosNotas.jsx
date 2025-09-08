import { useEffect, useMemo } from "react";

export default function FiltrosNotas({
  filters,
  setFilters,
  schools = [],
  turmas = [],
  selectedTurma,
}) {
  // 🔄 Limpa o componente curricular quando troca de turma ou escola
  useEffect(() => {
    setFilters((prev) => ({ ...prev, selectedComponenteId: "" }));
  }, [filters.selectedTurmaId, filters.selectedSchoolId, setFilters]);

  // 📌 Gerar anos letivos dinamicamente das turmas/escolas
  const anosLetivos = useMemo(() => {
    const anos = new Set();
    turmas.forEach((t) => {
      if (t.anoLetivo) anos.add(String(t.anoLetivo));
    });
    return Array.from(anos).sort((a, b) => b.localeCompare(a));
  }, [turmas]);

  // 📌 Mostrar seletor de componente apenas para Anos Finais / EJA Finais
  const nivel = (selectedTurma?.nivelEnsino || "").toUpperCase();
  const showComponenteFilter =
    nivel === "ENSINO FUNDAMENTAL - ANOS FINAIS" ||
    nivel === "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS";

  // 📌 Recupera componentes da turma selecionada
  const componentes = selectedTurma?.componentes || [];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      {/* Ano Letivo */}
      <div>
        <label className="block mb-1 font-medium">Ano Letivo</label>
        <select
          value={filters.selectedYear || ""}
          onChange={(e) =>
            setFilters({ ...filters, selectedYear: e.target.value })
          }
          className="p-2 border rounded-md w-full"
        >
          <option value="">Selecione</option>
          {anosLetivos.map((ano) => (
            <option key={ano} value={ano}>
              {ano}
            </option>
          ))}
        </select>
      </div>

      {/* Escola */}
      <div>
        <label className="block mb-1 font-medium">Escola</label>
        <select
          value={filters.selectedSchoolId || ""}
          onChange={(e) =>
            setFilters({
              ...filters,
              selectedSchoolId: e.target.value,
              selectedTurmaId: "",
              selectedComponenteId: "",
            })
          }
          className="p-2 border rounded-md w-full"
        >
          <option value="">Selecione</option>
          {schools.map((escola) => (
            <option key={escola.id} value={escola.id}>
              {escola.nomeEscola}
            </option>
          ))}
        </select>
      </div>

      {/* Turma */}
      <div>
        <label className="block mb-1 font-medium">Turma</label>
        <select
          value={filters.selectedTurmaId || ""}
          onChange={(e) =>
            setFilters({
              ...filters,
              selectedTurmaId: e.target.value,
              selectedComponenteId: "",
            })
          }
          className="p-2 border rounded-md w-full"
          disabled={!filters.selectedSchoolId || !filters.selectedYear}
        >
          <option value="">Selecione</option>
          {turmas
            .filter(
              (t) =>
                String(t.anoLetivo) === String(filters.selectedYear) &&
                t.schoolId === filters.selectedSchoolId
            )
            .map((turma) => (
              <option key={turma.id} value={turma.id}>
                {turma.nomeTurma} ({turma.anoSerie})
              </option>
            ))}
        </select>
      </div>

      {/* Componente Curricular */}
      {showComponenteFilter && (
        <div>
          <label className="block mb-1 font-medium">
            Componente Curricular
          </label>
          <select
            value={filters.selectedComponenteId || ""}
            onChange={(e) =>
              setFilters({ ...filters, selectedComponenteId: e.target.value })
            }
            className="p-2 border rounded-md w-full"
          >
            <option value="">Selecione</option>
            {componentes.map((comp) => (
              <option key={comp.nome} value={comp.nome}>
                {comp.nome}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
