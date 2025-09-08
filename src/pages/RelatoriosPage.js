import React, { useState, useEffect } from "react";
import { db } from "../firebase/config";
import {
  collection,
  getDocs,
  query,
  where,
  orderBy,
  doc,
  getDoc,
} from "firebase/firestore";
import { useNavigate } from "react-router-dom";

function RelatoriosPage() {
  const navigate = useNavigate();

  // Estados dos Filtros
  const [reportType, setReportType] = useState("frequencia"); // Padrão para o primeiro relatório
  const [availableSchools, setAvailableSchools] = useState([]);
  const [selectedSchoolId, setSelectedSchoolId] = useState("");
  const [availableTurmas, setAvailableTurmas] = useState([]);
  const [selectedTurmaId, setSelectedTurmaId] = useState("");
  const [availablePeriods, setAvailablePeriods] = useState([]);
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [availableComponentes, setAvailableComponentes] = useState([]);
  const [selectedComponente, setSelectedComponente] = useState("");

  const selectedTurmaObject = selectedTurmaId
    ? availableTurmas.find((t) => t.id === selectedTurmaId)
    : null;
  const showComponenteFilter =
    selectedTurmaObject &&
    (selectedTurmaObject.nivelEnsino === "ENSINO FUNDAMENTAL - ANOS FINAIS" ||
      selectedTurmaObject.nivelEnsino ===
        "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS");

  // Carrega filtros
  useEffect(() => {
    const fetchSchools = async () => {
      const schoolsSnapshot = await getDocs(collection(db, "schools"));
      setAvailableSchools(
        schoolsSnapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
      );
    };
    fetchSchools();
  }, []);

  useEffect(() => {
    const fetchTurmas = async () => {
      if (!selectedSchoolId) {
        setAvailableTurmas([]);
        setSelectedTurmaId("");
        return;
      }
      const q = query(
        collection(db, "turmas"),
        where("schoolId", "==", selectedSchoolId)
      );
      const snapshot = await getDocs(q);
      setAvailableTurmas(
        snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }))
      );
      setSelectedTurmaId("");
    };
    fetchTurmas();
  }, [selectedSchoolId]);

  useEffect(() => {
    const populateComponentes = async () => {
      if (!selectedTurmaId) {
        setAvailableComponentes([]);
        setSelectedComponente("");
        return;
      }
      const horarioRef = doc(db, "horarios", selectedTurmaId);
      const horarioSnap = await getDoc(horarioRef);
      if (horarioSnap.exists()) {
        const horarioData = horarioSnap.data().horario;
        const componentes = new Set();
        Object.values(horarioData).forEach((aulasDoDia) => {
          if (Array.isArray(aulasDoDia)) {
            aulasDoDia.forEach((aula) => {
              if (aula) {
                componentes.add(aula.split(" - ")[0]);
              }
            });
          }
        });
        setAvailableComponentes(Array.from(componentes).sort());
      } else {
        setAvailableComponentes([]);
      }
      setSelectedComponente("");
    };
    populateComponentes();
  }, [selectedTurmaId]);

  useEffect(() => {
    const fetchPeriods = async () => {
      if (!selectedYear) return;
      const q = query(
        collection(db, "bimestres"),
        where("anoLetivo", "==", selectedYear.toString()),
        orderBy("dataInicio")
      );
      const snapshot = await getDocs(q);
      const bimestresList = snapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      const isBimestral =
        bimestresList.length > 0 &&
        bimestresList[0].modoLancamento === "Bimestral";

      if (isBimestral) {
        setAvailablePeriods(
          bimestresList.map((b) => ({ value: b.id, label: b.nome }))
        );
      } else {
        const meses = Array.from({ length: 12 }, (_, i) => {
          const month = i + 1;
          const monthName = new Date(selectedYear, i, 1).toLocaleString(
            "pt-BR",
            { month: "long" }
          );
          return {
            value: month,
            label: monthName.charAt(0).toUpperCase() + monthName.slice(1),
          };
        });
        setAvailablePeriods(meses);
      }
      setSelectedPeriod("");
    };
    fetchPeriods();
  }, [selectedYear]);

  // Função que abre o relatório correto em uma nova aba
  const handleGenerateReport = () => {
    if (
      !selectedTurmaId ||
      !selectedPeriod ||
      (showComponenteFilter && !selectedComponente)
    ) {
      alert("Por favor, selecione todos os filtros necessários.");
      return;
    }

    // Constrói a URL baseada no tipo de relatório
    const componenteParam = showComponenteFilter
      ? selectedComponente
      : "DIARIO";
    let url = "";

    switch (reportType) {
      case "frequencia":
        url = `/relatorio/frequencia/${selectedSchoolId}/${selectedTurmaId}/${selectedYear}/${selectedPeriod}/${componenteParam}`;
        break;
      case "notas":
        // url = `/relatorio/notas/...`; // Futura implementação
        alert("Relatório de Notas ainda não implementado.");
        return;
      case "registros":
        // url = `/relatorio/registros/...`; // Futura implementação
        alert("Relatório de Registros ainda não implementado.");
        return;
      default:
        alert("Tipo de relatório desconhecido.");
        return;
    }

    window.open(url, "_blank");
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">
          Gerar Relatórios
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              1. Tipo de Relatório
            </label>
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="p-2 border rounded-md w-full"
            >
              <option value="frequencia">Relatório de Frequência</option>
              <option value="notas" disabled>
                Relatório de Notas (em breve)
              </option>
              <option value="registros" disabled>
                Relatório de Registros (em breve)
              </option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              2. Ano Letivo
            </label>
            <input
              type="number"
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value)}
              className="p-2 border rounded-md w-full"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              3. Escola
            </label>
            <select
              value={selectedSchoolId}
              onChange={(e) => setSelectedSchoolId(e.target.value)}
              className="p-2 border rounded-md w-full"
            >
              <option value="">Selecione a Escola</option>
              {availableSchools.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nomeEscola}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              4. Turma
            </label>
            <select
              value={selectedTurmaId}
              onChange={(e) => setSelectedTurmaId(e.target.value)}
              className="p-2 border rounded-md w-full"
              disabled={!selectedSchoolId}
            >
              <option value="">Selecione a Turma</option>
              {availableTurmas.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nomeTurma}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              5. Período
            </label>
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="p-2 border rounded-md w-full"
              disabled={!selectedTurmaId}
            >
              <option value="">Selecione o Período</option>
              {availablePeriods.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          {showComponenteFilter && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                6. Componente Curricular
              </label>
              <select
                value={selectedComponente}
                onChange={(e) => setSelectedComponente(e.target.value)}
                className="p-2 border rounded-md w-full"
                disabled={!selectedTurmaId}
              >
                <option value="">Selecione o Componente</option>
                {availableComponentes.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="pt-4 flex justify-end">
            <button
              onClick={handleGenerateReport}
              className="bg-blue-600 text-white p-2 px-6 rounded-md hover:bg-blue-700"
            >
              Gerar Relatório
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default RelatoriosPage;
