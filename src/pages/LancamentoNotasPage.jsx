import React, { useEffect, useState } from "react";
import { collection, getDocs } from "firebase/firestore";
import { db } from "../firebase/config";
import FiltrosNotas from "../components/FiltrosNotas";
import TabelaNotasIniciais from "../components/TabelaNotasIniciais";
import TabelaNotasFinais from "../components/TabelaNotasFinais";

export default function LancamentoNotasPage() {
  const [schools, setSchools] = useState([]);
  const [turmas, setTurmas] = useState([]);

  // ✅ Estado unificado de filtros
  const [filters, setFilters] = useState({
    selectedYear: "",
    selectedSchoolId: "",
    selectedTurmaId: "",
    selectedComponenteId: "",
  });

  // 🔎 Buscar escolas
  useEffect(() => {
    const fetchSchools = async () => {
      const querySnapshot = await getDocs(collection(db, "escolas"));
      const lista = querySnapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      setSchools(lista);
    };
    fetchSchools();
  }, []);

  // 🔎 Buscar turmas da escola e ano letivo selecionados
  useEffect(() => {
    const fetchTurmas = async () => {
      if (!filters.selectedSchoolId || !filters.selectedYear) {
        setTurmas([]);
        return;
      }

      const querySnapshot = await getDocs(collection(db, "turmas"));
      const lista = querySnapshot.docs
        .map((doc) => ({ id: doc.id, ...doc.data() }))
        .filter(
          (t) =>
            t.schoolId === filters.selectedSchoolId &&
            t.anoLetivo === filters.selectedYear
        );

      setTurmas(lista);
    };
    fetchTurmas();
  }, [filters.selectedSchoolId, filters.selectedYear]);

  // Turma selecionada
  const selectedTurma = turmas.find((t) => t.id === filters.selectedTurmaId);

  // Verifica se é Anos Iniciais
  const isAnosIniciais =
    selectedTurma?.nivelEnsino === "ENSINO FUNDAMENTAL - ANOS INICIAIS" ||
    selectedTurma?.nivelEnsino ===
      "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS INICIAIS";

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-4">Lançamento de Notas</h1>

      {/* Filtros */}
      <FiltrosNotas
        filters={filters}
        setFilters={setFilters}
        schools={schools}
        turmas={turmas}
        selectedTurma={selectedTurma}
      />

      {/* Aviso se a turma não tiver componentes */}
      {selectedTurma && (selectedTurma.componentes || []).length === 0 && (
        <div className="mt-4 p-3 bg-yellow-100 border border-yellow-300 rounded text-yellow-800">
          Nenhum componente curricular vinculado a esta turma.
        </div>
      )}

      {/* Renderização condicional das tabelas */}
      {selectedTurma && (
        <div className="mt-6">
          {isAnosIniciais ? (
            <TabelaNotasIniciais turma={selectedTurma} />
          ) : (
            filters.selectedComponenteId && (
              <TabelaNotasFinais
                turma={selectedTurma}
                componente={filters.selectedComponenteId}
              />
            )
          )}
        </div>
      )}
    </div>
  );
}
