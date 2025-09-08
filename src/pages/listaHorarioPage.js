import React, { useState, useEffect } from "react";
import { db } from "../firebase/config";
import {
  collection,
  getDocs,
  query,
  where,
  documentId,
} from "firebase/firestore";
import { Link, useNavigate } from "react-router-dom";

// ======================= INÍCIO DA CORREÇÃO =======================
import { seriesAnosEtapasData } from "../data/ensinoConstants";
// ======================== FIM DA CORREÇÃO =========================

function ListaHorarioPage() {
  const navigate = useNavigate();
  const [horarios, setHorarios] = useState([]);
  const [filteredHorarios, setFilteredHorarios] = useState([]);
  const [loading, setLoading] = useState(true);

  // Estados para os filtros
  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState("");
  const [selectedNivel, setSelectedNivel] = useState("");
  const [selectedSerie, setSelectedSerie] = useState("");
  const [selectedTurma, setSelectedTurma] = useState("");

  // Estados para a criação de um novo horário
  const [escolaParaNovoHorario, setEscolaParaNovoHorario] = useState("");
  const [turmaParaNovoHorario, setTurmaParaNovoHorario] = useState("");
  const [availableTurmasParaNovo, setAvailableTurmasParaNovo] = useState([]);

  // Estados para os dropdowns dinâmicos
  const [availableNiveis, setAvailableNiveis] = useState([]);
  const [availableSeries, setAvailableSeries] = useState([]);
  const [availableTurmas, setAvailableTurmas] = useState([]);

  useEffect(() => {
    const fetchInitialData = async () => {
      setLoading(true);
      try {
        const schoolsSnapshot = await getDocs(collection(db, "schools"));
        setSchools(
          schoolsSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );

        const horariosSnapshot = await getDocs(collection(db, "horarios"));
        const horariosList = horariosSnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        if (horariosList.length > 0) {
          const turmasIds = horariosList.map((h) => h.turmaId).filter(Boolean);
          if (turmasIds.length > 0) {
            const turmasQuery = query(
              collection(db, "turmas"),
              where(documentId(), "in", turmasIds)
            );
            const turmasSnapshot = await getDocs(turmasQuery);
            const turmasMap = new Map();
            turmasSnapshot.docs.forEach((doc) =>
              turmasMap.set(doc.id, doc.data())
            );

            const enrichedHorarios = horariosList.map((h) => ({
              ...h,
              turma: turmasMap.get(h.turmaId),
            }));
            setHorarios(enrichedHorarios);
            setFilteredHorarios(enrichedHorarios);
          } else {
            setHorarios(horariosList);
            setFilteredHorarios(horariosList);
          }
        }
      } catch (error) {
        console.error("Erro ao buscar dados:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchInitialData();
  }, []);

  // Lógica para atualizar os filtros dinâmicos
  useEffect(() => {
    if (selectedSchool) {
      const school = schools.find((s) => s.id === selectedSchool);
      setAvailableNiveis(school?.niveisEnsino || []);
    } else {
      setAvailableNiveis([]);
    }
    setSelectedNivel("");
  }, [selectedSchool, schools]);

  useEffect(() => {
    if (selectedNivel) {
      setAvailableSeries(seriesAnosEtapasData[selectedNivel] || []);
    } else {
      setAvailableSeries([]);
    }
    setSelectedSerie("");
  }, [selectedNivel]);

  useEffect(() => {
    const fetchTurmas = async () => {
      if (selectedSchool && selectedNivel && selectedSerie) {
        const q = query(
          collection(db, "turmas"),
          where("schoolId", "==", selectedSchool),
          where("nivelEnsino", "==", selectedNivel),
          where("anoSerie", "==", selectedSerie)
        );
        const snapshot = await getDocs(q);
        setAvailableTurmas(
          snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );
      } else {
        setAvailableTurmas([]);
      }
    };
    fetchTurmas();
    setSelectedTurma("");
  }, [selectedSchool, selectedNivel, selectedSerie]);

  // Lógica para popular o dropdown de turmas para o novo horário
  useEffect(() => {
    const fetchTurmasParaNovo = async () => {
      if (escolaParaNovoHorario) {
        const q = query(
          collection(db, "turmas"),
          where("schoolId", "==", escolaParaNovoHorario)
        );
        const snapshot = await getDocs(q);
        setAvailableTurmasParaNovo(
          snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
        );
      } else {
        setAvailableTurmasParaNovo([]);
      }
    };
    fetchTurmasParaNovo();
    setTurmaParaNovoHorario("");
  }, [escolaParaNovoHorario]);

  // Lógica para aplicar os filtros na lista de horários
  useEffect(() => {
    let result = horarios;
    if (selectedSchool) {
      result = result.filter((h) => h.turma?.schoolId === selectedSchool);
    }
    if (selectedNivel) {
      result = result.filter((h) => h.turma?.nivelEnsino === selectedNivel);
    }
    if (selectedSerie) {
      result = result.filter((h) => h.turma?.anoSerie === selectedSerie);
    }
    if (selectedTurma) {
      result = result.filter((h) => h.turmaId === selectedTurma);
    }
    setFilteredHorarios(result);
  }, [selectedSchool, selectedNivel, selectedSerie, selectedTurma, horarios]);

  const handleCreateHorario = () => {
    if (turmaParaNovoHorario) {
      navigate(`/dashboard/calendario/horario/${turmaParaNovoHorario}`);
    }
  };

  const handleClearFilters = () => {
    setSelectedSchool("");
    setSelectedNivel("");
    setSelectedSerie("");
    setSelectedTurma("");
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">
          Horários de Aulas
        </h2>

        <div className="mb-8 p-4 border-2 border-dashed rounded-md bg-gray-50">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">
            Criar Novo Horário de Aula
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
            <div className="md:col-span-1">
              <label
  htmlFor="escola-select"
  className="block text-sm font-medium"
>
  Escola
</label>
              <select
                id="escola-select"
                value={escolaParaNovoHorario}
                onChange={(e) => setEscolaParaNovoHorario(e.target.value)}
                className="mt-1 p-2 w-full border rounded-md"
              >
                <option value="">Selecione a Escola</option>
                {schools.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nomeEscola}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-1">
              <label
  htmlFor="turma-select"
  className="block text-sm font-medium"
>
  Turma
</label>
              <select
                id="turma-select"
                value={turmaParaNovoHorario}
                onChange={(e) => setTurmaParaNovoHorario(e.target.value)}
                className="mt-1 p-2 w-full border rounded-md"
                disabled={!escolaParaNovoHorario}
              >
                <option value="">Selecione a Turma</option>
                {availableTurmasParaNovo.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nomeTurma}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-1">
              <button
                onClick={handleCreateHorario}
                disabled={!turmaParaNovoHorario}
                className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition w-full disabled:bg-gray-400"
              >
                Criar Horário
              </button>
            </div>
          </div>
        </div>

        <hr className="my-8" />
        <h3 className="text-xl font-bold mb-4 text-gray-800">
          Horários Cadastrados
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 p-4 border rounded-md bg-gray-50">
          <select
            value={selectedSchool}
            onChange={(e) => setSelectedSchool(e.target.value)}
            className="p-2 border rounded-md"
          >
            <option value="">Filtrar por Escola</option>
            {schools.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nomeEscola}
              </option>
            ))}
          </select>
          <select
            value={selectedNivel}
            onChange={(e) => setSelectedNivel(e.target.value)}
            className="p-2 border rounded-md"
            disabled={!selectedSchool}
          >
            <option value="">Filtrar por Nível</option>
            {availableNiveis.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <select
            value={selectedSerie}
            onChange={(e) => setSelectedSerie(e.target.value)}
            className="p-2 border rounded-md"
            disabled={!selectedNivel}
          >
            <option value="">Filtrar por Série/Ano</option>
            {availableSeries.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={selectedTurma}
            onChange={(e) => setSelectedTurma(e.target.value)}
            className="p-2 border rounded-md"
            disabled={!selectedSerie}
          >
            <option value="">Filtrar por Turma</option>
            {availableTurmas.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nomeTurma}
              </option>
            ))}
          </select>
          <div className="col-span-full flex justify-end">
            <button
              onClick={handleClearFilters}
              className="bg-gray-500 hover:bg-gray-600 text-white font-bold py-2 px-4 rounded transition"
            >
              Limpar Filtros
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                <th className="py-3 px-6 text-left">Turma</th>
                <th className="py-3 px-6 text-left">Nível de Ensino</th>
                <th className="py-3 px-6 text-left">Ano Letivo</th>
                <th className="py-3 px-6 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="text-gray-700">
              {loading ? (
                <tr>
                  <td colSpan="4" className="text-center p-4">
                    Carregando...
                  </td>
                </tr>
              ) : (
                filteredHorarios.map((h) => (
                  <tr key={h.id} className="border-b hover:bg-gray-100">
                    <td className="py-3 px-6">{h.turma?.nomeTurma}</td>
                    <td className="py-3 px-6">{h.turma?.nivelEnsino}</td>
                    <td className="py-3 px-6">{h.anoLetivo}</td>
                    <td className="py-3 px-6 text-center">
                      <Link
                        to={`/dashboard/calendario/horario/${h.turmaId}`}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        Ver / Editar
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ListaHorarioPage;
