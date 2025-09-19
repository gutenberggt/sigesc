import React, { useState, useEffect, useCallback } from "react";
import { db } from "../firebase/config";
import { doc, getDoc, setDoc, collection, getDocs } from "firebase/firestore";
import { useNavigate, useParams } from "react-router-dom";
import CustomDropdown from "../components/CustomDropdown";
import { FaPlusCircle } from "react-icons/fa";

function HorarioPage() {
  const navigate = useNavigate();
  const { turmaId } = useParams();

  const [turma, setTurma] = useState(null);
  const [, setEscola] = useState(null);
  const [componentesDisponiveis, setComponentesDisponiveis] = useState([]);
  const [numeroDeAulas, setNumeroDeAulas] = useState(5);
  const [scheduleRows, setScheduleRows] = useState([]);
  const [horariosDasAulas, setHorariosDasAulas] = useState([]);
  const [horario, setHorario] = useState({});
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const diasDaSemana = [
    { id: "segunda", nome: "Segunda-feira" },
    { id: "terca", nome: "Terça-feira" },
    { id: "quarta", nome: "Quarta-feira" },
    { id: "quinta", nome: "Quinta-feira" },
    { id: "sexta", nome: "Sexta-feira" },
  ];

  const handleNumeroDeAulasChange = (novoNumero) => {
    if (loading || novoNumero === numeroDeAulas) return;
    const confirmReset = window.confirm(
      "Alterar o número de aulas irá resetar o quadro de horários atual, incluindo os intervalos. Deseja continuar?"
    );
    if (confirmReset) {
      setNumeroDeAulas(novoNumero);
      const defaultRows = Array.from({ length: novoNumero }, (_, i) => ({
        type: "aula",
        label: `${i + 1}ª Aula`,
      }));
      setScheduleRows(defaultRows);
      const defaultHorarios = Array.from({ length: novoNumero }, () => ({
        inicio: "",
        fim: "",
      }));
      setHorariosDasAulas(defaultHorarios);
    }
  };

  useEffect(() => {
    const newHorario = {};
    scheduleRows.forEach((row, index) => {
      diasDaSemana.forEach((dia) => {
        if (!newHorario[dia.id]) newHorario[dia.id] = [];
        newHorario[dia.id][index] = horario[dia.id]?.[index] || "";
      });
      if (row.type === "intervalo") {
        if (!newHorario.intervalos) newHorario.intervalos = {};
        newHorario.intervalos[index] =
          horario.intervalos?.[index] || "INTERVALO";
      }
    });
    setHorario(newHorario);
  }, [scheduleRows]);

  // ======================= INÍCIO DA CORREÇÃO =======================
  // FUNÇÃO DE BUSCA DE DADOS REESCRITA COM MECANISMO DE FALLBACK
  const fetchDadosIniciais = useCallback(async () => {
    if (!turmaId) return;
    setLoading(true);
    setError("");
    try {
      const turmaRef = doc(db, "turmas", turmaId);
      const turmaSnap = await getDoc(turmaRef);

      if (!turmaSnap.exists()) {
        setError("Turma não encontrada.");
        setLoading(false);
        return;
      }

      const turmaData = turmaSnap.data();
      setTurma(turmaData);

      const escolaRef = doc(db, "schools", turmaData.schoolId);
      const escolaSnap = await getDoc(escolaRef);
      const escolaData = escolaSnap.exists() ? escolaSnap.data() : null;
      setEscola(escolaData);

      let professoresDaTurma = [];
      const professoresMap = turmaData.professores || {};

      // Tenta a busca otimizada primeiro
      for (const professorId in professoresMap) {
        const professorInfo = professoresMap[professorId];
        (professorInfo.componentes || []).forEach((comp) => {
          professoresDaTurma.push({
            value: `${comp} - ${professorInfo.nome}`,
            subject: comp,
            teacher: professorInfo.nome,
          });
        });
      }

      // Se a busca otimizada não retornar resultados, usa o fallback
      if (professoresDaTurma.length === 0) {
        console.warn(
          "Nenhum professor encontrado no documento da turma. Usando busca de fallback na coleção 'servidores'."
        );
        //const servidoresQuery = query(
        //collection(db, "servidores"),
        //where("alocacoes", "array-contains-any", [
        //{ funcoes: [{ turmaId: turmaId }] },
        //])
        //);
        // A consulta acima é complexa. A forma mais garantida é filtrar no cliente.
        const todosServidoresSnap = await getDocs(collection(db, "servidores"));

        for (const servidorDoc of todosServidoresSnap.docs) {
          const servidorData = servidorDoc.data();

          for (const aloc of servidorData.alocacoes) {
            if (
              aloc.schoolId === turmaData.schoolId &&
              aloc.anoLetivo === turmaData.anoLetivo
            ) {
              for (const funcao of aloc.funcoes) {
                if (
                  funcao.turmaId === turmaId &&
                  funcao.funcao === "Professor(a)"
                ) {
                  const pessoaDoc = await getDoc(
                    doc(db, "pessoas", servidorData.pessoaId)
                  );
                  const nomeCompletoProfessor = pessoaDoc.exists()
                    ? pessoaDoc.data().nomeCompleto
                    : "Desconhecido";
                  const primeiroNomeProfessor =
                    nomeCompletoProfessor.split(" ")[0];

                  (funcao.componentesCurriculares || []).forEach((comp) => {
                    professoresDaTurma.push({
                      value: `${comp} - ${primeiroNomeProfessor}`,
                      subject: comp,
                      teacher: primeiroNomeProfessor,
                    });
                  });
                }
              }
            }
          }
        }
      }

      // Aplica o filtro da escola integral
      let componentesValidos = [...professoresDaTurma];
      if (escolaData && escolaData.integral === "Não") {
        const componentesARemover = [
          "Recreação, Esporte e Lazer",
          "Arte e Cultura",
          "Tecnologia e Informática",
          "Acompanhamento Pedagógico de Língua Portuguesa",
          "Acompanhamento Pedagógico de Matemática",
        ];
        componentesValidos = professoresDaTurma.filter(
          (p) => !componentesARemover.includes(p.subject)
        );
      }

      const unique = [
        ...new Map(
          componentesValidos.map((item) => [item["value"], item])
        ).values(),
      ];
      setComponentesDisponiveis(unique);

      // Busca o horário existente (lógica mantida)
      const horarioRef = doc(db, "horarios", turmaId);
      const horarioSnap = await getDoc(horarioRef);
      if (horarioSnap.exists()) {
        const data = horarioSnap.data();
        setHorario(data.horario || {});
        setScheduleRows(data.scheduleRows || []);
        setHorariosDasAulas(data.horariosDasAulas || []);
        if (data.scheduleRows && data.scheduleRows.length > 0) {
          setNumeroDeAulas(
            data.scheduleRows.filter((r) => r.type === "aula").length
          );
        }
      } else {
        const defaultRows = Array.from({ length: 5 }, (_, i) => ({
          type: "aula",
          label: `${i + 1}ª Aula`,
        }));
        setScheduleRows(defaultRows);
        setHorariosDasAulas(
          Array.from({ length: 5 }, () => ({ inicio: "", fim: "" }))
        );
      }
    } catch (err) {
      setError("Falha ao carregar dados iniciais.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [turmaId]);
  // ======================== FIM DA CORREÇÃO =========================

  useEffect(() => {
    fetchDadosIniciais();
  }, [fetchDadosIniciais]);

  const handleHorarioChange = (dia, aulaIndex, value) => {
    const novoHorario = { ...horario };
    if (!novoHorario[dia]) {
      novoHorario[dia] = [];
    }
    novoHorario[dia][aulaIndex] = value;
    setHorario(novoHorario);
  };

  const handleTimeChange = (aulaIndex, type, value) => {
    const newTimes = JSON.parse(JSON.stringify(horariosDasAulas));
    if (!newTimes[aulaIndex]) newTimes[aulaIndex] = { inicio: "", fim: "" };
    newTimes[aulaIndex][type] = value;
    setHorariosDasAulas(newTimes);
  };

  const handleInsertInterval = (index) => {
    const newScheduleRows = [...scheduleRows];
    newScheduleRows.splice(index + 1, 0, {
      type: "intervalo",
      label: "Intervalo",
    });
    setScheduleRows(newScheduleRows);

    const newTimes = [...horariosDasAulas];
    newTimes.splice(index + 1, 0, null);
    setHorariosDasAulas(newTimes);
  };

  const handleIntervalChange = (rowIndex, value) => {
    const newHorario = { ...horario };
    if (!newHorario.intervalos) newHorario.intervalos = {};
    newHorario.intervalos[rowIndex] = value;
    setHorario(newHorario);
  };

  const handleSave = async () => {
    setIsSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const horarioRef = doc(db, "horarios", turmaId);
      const horarioData = {
        schoolId: turma.schoolId,
        turmaId: turmaId,
        turmaNome: turma.nomeTurma,
        anoLetivo: turma.anoLetivo,
        horario: horario,
        scheduleRows: scheduleRows,
        horariosDasAulas: horariosDasAulas,
      };
      await setDoc(horarioRef, horarioData, { merge: true });
      setSuccess("Horário salvo com sucesso!");
    } catch (err) {
      setError("Erro ao salvar o horário.");
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) return <div className="p-6 text-center">Carregando...</div>;

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-800">
              Quadro de Aulas
            </h2>
            {turma && (
              <p className="text-gray-600">
                Editando horário para a turma:{" "}
                <span className="font-semibold">{turma.nomeTurma}</span> (
                {turma.anoLetivo})
              </p>
            )}
          </div>
          <div className="w-full max-w-xs">
            <label
              htmlFor="numeroAulas"
              className="block text-sm font-medium text-gray-700 text-right"
            >
              Aulas por dia
            </label>
            <input
              type="number"
              id="numeroAulas"
              value={numeroDeAulas}
              onChange={(e) =>
                handleNumeroDeAulasChange(
                  Math.max(1, Math.min(10, parseInt(e.target.value, 10) || 1))
                )
              }
              min="1"
              max="10"
              className="mt-1 block w-full p-2 border border-gray-300 rounded-md text-center"
            />
          </div>
        </div>

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && (
          <p className="text-green-500 text-center mb-4">{success}</p>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full border">
            <thead>
              <tr className="bg-gray-200">
                <th className="py-2 px-3 border w-48">Horário</th>
                {diasDaSemana.map((dia) => (
                  <th key={dia.id} className="py-2 px-3 border">
                    {dia.nome}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scheduleRows.map((row, rowIndex) => {
                if (row.type === "aula") {
                  return (
                    <tr key={rowIndex}>
                      <td className="p-1 border text-center font-semibold align-top">
                        <div className="flex items-center justify-center">
                          <button
                            onClick={() => handleInsertInterval(rowIndex)}
                            className="text-green-500 hover:text-green-700 mr-2"
                            title="Adicionar intervalo após esta aula"
                          >
                            <FaPlusCircle />
                          </button>
                          <div>
                            {row.label}
                            <div className="flex gap-1 mt-1 justify-center">
                              <input
                                type="text"
                                placeholder="hh:mm"
                                maxLength="5"
                                value={horariosDasAulas[rowIndex]?.inicio || ""}
                                onChange={(e) =>
                                  handleTimeChange(
                                    rowIndex,
                                    "inicio",
                                    e.target.value
                                  )
                                }
                                className="w-16 p-1 text-center border rounded"
                              />
                              <input
                                type="text"
                                placeholder="hh:mm"
                                maxLength="5"
                                value={horariosDasAulas[rowIndex]?.fim || ""}
                                onChange={(e) =>
                                  handleTimeChange(
                                    rowIndex,
                                    "fim",
                                    e.target.value
                                  )
                                }
                                className="w-16 p-1 text-center border rounded"
                              />
                            </div>
                          </div>
                        </div>
                      </td>
                      {diasDaSemana.map((dia) => (
                        <td key={dia.id} className="p-1 border">
                          <CustomDropdown
                            options={componentesDisponiveis}
                            value={horario[dia.id]?.[rowIndex] || ""}
                            onChange={(selectedValue) =>
                              handleHorarioChange(
                                dia.id,
                                rowIndex,
                                selectedValue
                              )
                            }
                            placeholder="-- Vago --"
                          />
                        </td>
                      ))}
                    </tr>
                  );
                }
                if (row.type === "intervalo") {
                  return (
                    <tr key={rowIndex} className="bg-gray-100">
                      <td className="py-2 px-3 border text-center font-semibold">
                        {row.label}
                      </td>
                      <td colSpan={diasDaSemana.length} className="p-1 border">
                        <input
                          type="text"
                          value={horario.intervalos?.[rowIndex] || "INTERVALO"}
                          onChange={(e) =>
                            handleIntervalChange(rowIndex, e.target.value)
                          }
                          className="w-full p-2 border-gray-300 rounded-md text-center font-semibold bg-gray-100"
                        />
                      </td>
                    </tr>
                  );
                }
                return null;
              })}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end space-x-4 mt-6">
          <button
            onClick={() => navigate(-1)}
            className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition"
          >
            Voltar
          </button>
          <button
            onClick={handleSave}
            disabled={isSubmitting}
            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition"
          >
            {isSubmitting ? "Salvando..." : "Salvar Horário"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default HorarioPage;
