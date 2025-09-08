import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { db } from "../firebase/config";
import {
  doc,
  getDoc,
  collection,
  query,
  where,
  getDocs,
  documentId,
} from "firebase/firestore";
import pdfMake from "pdfmake/build/pdfmake";
import pdfFonts from "pdfmake/build/vfs_fonts";
pdfMake.vfs = pdfFonts.vfs;

function formatDatePorExtenso(dataStr) {
  if (!dataStr) return "";
  const [ano, mes, dia] = dataStr.split("-").map((n) => parseInt(n, 10));
  const meses = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
  ];
  meses[5] = "junho";
  meses.splice(6, 0, "julho");
  return `${dia} de ${meses[mes - 1]} de ${ano}`;
}

function formatLocalDate(date) {
  const d = new Date(date);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function normalize(str) {
  return (str || "")
    .normalize("NFD")
    .replace(/\u0300-\u036f/g, "")
    .toLowerCase()
    .trim();
}

let brasaoCache = null;
const CACHE_VALIDITY = 7 * 24 * 60 * 60 * 1000;

async function getBase64FromUrlCached(url) {
  if (brasaoCache) return brasaoCache;
  const storedData = localStorage.getItem("brasaoFlorestaCache");
  if (storedData) {
    try {
      const parsed = JSON.parse(storedData);
      if (
        parsed.base64 &&
        parsed.timestamp &&
        Date.now() - parsed.timestamp < CACHE_VALIDITY
      ) {
        brasaoCache = parsed.base64;
        return parsed.base64;
      }
    } catch {}
  }
  const res = await fetch(url, { cache: "no-store" });
  const blob = await res.blob();
  const dataUrl = await new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });
  brasaoCache = dataUrl;
  localStorage.setItem(
    "brasaoFlorestaCache",
    JSON.stringify({
      base64: dataUrl,
      timestamp: Date.now(),
    })
  );
  return dataUrl;
}

function RelatorioFrequenciaPage() {
  const { schoolId, turmaId, year, period, componente } = useParams();
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const generateReport = async () => {
      try {
        const brasaoFlorestaBase64 = await getBase64FromUrlCached(
          "https://sigesc-omega.vercel.app/brasao_floresta.png"
        );

        const [
          schoolDoc,
          turmaDoc,
          matriculasSnap,
          eventosSnap,
          horarioSnap,
          periodDoc,
          servidoresSnap,
        ] = await Promise.all([
          getDoc(doc(db, "schools", schoolId)),
          getDoc(doc(db, "turmas", turmaId)),
          getDocs(
            query(
              collection(db, "matriculas"),
              where("turmaId", "==", turmaId),
              where("anoLetivo", "==", year.toString())
            )
          ),
          getDocs(
            query(
              collection(db, "eventos"),
              where("anoLetivo", "==", year.toString())
            )
          ),
          getDoc(doc(db, "horarios", turmaId)),
          /^\d+$/.test(period) ? null : getDoc(doc(db, "bimestres", period)),
          getDocs(collection(db, "servidores")),
        ]);

        if (!schoolDoc.exists() || !turmaDoc.exists()) {
          throw new Error("Escola ou Turma não encontrada.");
        }

        const schoolData = schoolDoc.data();
        const turmaData = { id: turmaDoc.id, ...turmaDoc.data() };

        let professorNome = "Não Localizado";
        let professorPessoaId = null;
        const compParam = componente || "";
        const compNorm = normalize(compParam);

        outerLoop: for (const servidorDoc of servidoresSnap.docs) {
          const servidor = servidorDoc.data();
          if (servidor?.ativo === false) continue;
          const alocacoes = Array.isArray(servidor?.alocacoes)
            ? servidor.alocacoes
            : [];
          for (const alocacao of alocacoes) {
            if (String(alocacao?.anoLetivo) !== year.toString()) continue;
            const funcoes = Array.isArray(alocacao?.funcoes)
              ? alocacao.funcoes
              : [];
            for (const funcao of funcoes) {
              if (funcao?.funcao !== "Professor(a)") continue;
              if (funcao?.turmaId !== turmaId) continue;
              if (schoolId) {
                const schoolInFunc = funcao?.schoolId;
                const schoolInAloc = alocacao?.schoolId;
                if (
                  (schoolInFunc && schoolInFunc !== schoolId) ||
                  (schoolInAloc && schoolInAloc !== schoolId)
                ) {
                  continue;
                }
              }
              if (compParam === "DIARIO") {
                professorPessoaId = servidor?.pessoaId || null;
                break outerLoop;
              } else {
                const comps = Array.isArray(funcao?.componentesCurriculares)
                  ? funcao.componentesCurriculares
                  : [];
                const match = comps.some((c) => normalize(c) === compNorm);
                if (match) {
                  professorPessoaId = servidor?.pessoaId || null;
                  break outerLoop;
                }
              }
            }
          }
        }

        if (professorPessoaId) {
          try {
            const pessoaDoc = await getDoc(
              doc(db, "pessoas", professorPessoaId)
            );
            if (pessoaDoc.exists()) {
              const pessoaData = pessoaDoc.data();
              professorNome = pessoaData?.nomeCompleto || "Nome não cadastrado";
            } else {
              professorNome = "Pessoa não encontrada";
            }
          } catch (e) {
            console.error("Erro ao buscar pessoa do professor:", e);
            professorNome = "Erro ao localizar nome";
          }
        }

        let dataInicio, dataFim, periodoLabel;
        if (/^\d+$/.test(period)) {
          const month = parseInt(period, 10);
          dataInicio = new Date(year, month - 1, 1);
          dataFim = new Date(year, month, 0);
          const monthName = dataInicio.toLocaleString("pt-BR", {
            month: "long",
          });
          periodoLabel = monthName.charAt(0).toUpperCase() + monthName.slice(1);
        } else {
          if (!periodDoc?.exists()) throw new Error("Bimestre não encontrado.");
          const bimestreData = periodDoc.data();
          const [sy, sm, sd] = bimestreData.dataInicio.split("-").map(Number);
          const [ey, em, ed] = bimestreData.dataFim.split("-").map(Number);
          dataInicio = new Date(sy, sm - 1, sd);
          dataFim = new Date(ey, em - 1, ed);
          periodoLabel = bimestreData.nome;
        }

        const feriados = new Set();
        eventosSnap.forEach((d) => {
          const evento = d.data();
          if (evento.tipo?.toUpperCase().includes("FERIADO")) {
            feriados.add(evento.data);
          }
        });

        const horarioData = horarioSnap.exists()
          ? horarioSnap.data().horario || {}
          : {};

        const diasLetivos = [];
        const isAnosFinais =
          turmaData.nivelEnsino === "ENSINO FUNDAMENTAL - ANOS FINAIS" ||
          turmaData.nivelEnsino ===
            "EDUCAÇÃO DE JOVENS E ADULTOS - EJA - ANOS FINAIS";

        for (
          let d = new Date(dataInicio);
          d <= dataFim;
          d.setDate(d.getDate() + 1)
        ) {
          const dataFormatada = formatLocalDate(d);
          if (feriados.has(dataFormatada)) continue;

          const diaSemana = d.getDay();
          if (diaSemana === 0 || diaSemana === 6) continue;

          if (!isAnosFinais) {
            diasLetivos.push({
              data: dataFormatada,
              aulas: [{ id: "aulaUnica", nome: "Frequência do Dia" }],
            });
          } else {
            const weekDayName = [
              "domingo",
              "segunda",
              "terca",
              "quarta",
              "quinta",
              "sexta",
              "sabado",
            ][diaSemana];
            const aulasDia = horarioData[weekDayName] || [];
            const aulasFiltradas = aulasDia
              .map((aula, idx) => ({ id: `aula${idx + 1}`, nome: aula }))
              .filter((a) => a.nome)
              .filter(
                (a) => componente === "DIARIO" || a.nome.startsWith(componente)
              );
            if (aulasFiltradas.length > 0) {
              diasLetivos.push({ data: dataFormatada, aulas: aulasFiltradas });
            }
          }
        }

        const studentIds = matriculasSnap.docs.map((d) => d.data().pessoaId);
        const [alunosSnap, frequenciaSnap] = await Promise.all([
          studentIds.length > 0
            ? getDocs(
                query(
                  collection(db, "pessoas"),
                  where(documentId(), "in", studentIds)
                )
              )
            : Promise.resolve({ docs: [] }),
          getDocs(
            query(
              collection(db, "frequencias"),
              where("turmaId", "==", turmaId)
            )
          ),
        ]);

        const alunosDaTurma = alunosSnap.docs
          .map((doc) => ({ id: doc.id, ...doc.data() }))
          .sort((a, b) => a.nomeCompleto.localeCompare(b.nomeCompleto));

        const frequenciaData = {};
        frequenciaSnap.forEach((doc) => {
          const f = doc.data();
          if (!frequenciaData[f.alunoId]) frequenciaData[f.alunoId] = {};
          if (!frequenciaData[f.alunoId][f.data])
            frequenciaData[f.alunoId][f.data] = {};
          frequenciaData[f.alunoId][f.data][f.aulaId] = f.status;
        });

        // === Cabeçalho ===
        const cabecalho = {
          table: {
            widths: [60, "*", "*"],
            body: [
              [
                { image: brasaoFlorestaBase64, width: 40, rowSpan: 2 },
                {
                  stack: [
                    {
                      text: "PREFEITURA MUNICIPAL DE FLORESTA DO ARAGUAIA",
                      style: "subheader",
                      alignment: "left",
                    },
                    {
                      text: "SECRETARIA MUNICIPAL DE EDUCAÇÃO",
                      style: "subheader",
                      alignment: "left",
                    },
                    {
                      table: {
                        widths: ["70%", "30%"],
                        body: [
                          [
                            {
                              text: `ESCOLA: ${schoolData.nomeEscola?.toUpperCase() || ""}`,
                              style: "infoText",
                            },
                            { text: `ANO LETIVO: ${year}`, style: "infoText" },
                          ],
                        ],
                      },
                      layout: "noBorders",
                      margin: [0, 4, 0, 0],
                    },
                    {
                      table: {
                        widths: ["100%"],
                        body: [
                          [
                            {
                              text: `COMPONENTE: ${componente === "DIARIO" ? "GERAL" : (componente || "").toUpperCase()}`,
                              style: "infoText",
                            },
                          ],
                        ],
                      },
                      layout: "noBorders",
                      margin: [0, 2, 0, 0],
                    },
                  ],
                },
                {
                  stack: [
                    {
                      text: "REGISTRO DE FREQUÊNCIA",
                      style: "header",
                      alignment: "right",
                    },
                    {
                      text: "Legenda: P - Presente, F - Falta, J - Falta Justificada",
                      fontSize: 8,
                      alignment: "right",
                    },
                    {
                      table: {
                        widths: ["50%", "50%"],
                        body: [
                          [
                            {
                              text: `TURMA: ${turmaData.nomeTurma || ""}`,
                              style: "infoText",
                            },
                            {
                              text: `PERÍODO: ${periodoLabel?.toUpperCase() || ""}`,
                              style: "infoText",
                            },
                          ],
                        ],
                      },
                      layout: "noBorders",
                      margin: [0, 4, 0, 0],
                    },
                    {
                      table: {
                        widths: ["100%"],
                        body: [
                          [
                            {
                              text: `PROFESSOR(A): ${professorNome || ""}`,
                              style: "infoText",
                            },
                          ],
                        ],
                      },
                      layout: "noBorders",
                      margin: [0, 2, 0, 0],
                    },
                  ],
                },
              ],
              [{}, {}, {}],
            ],
          },
          layout: "noBorders",
          margin: [0, 0, 0, 1],
        };

        const nomeColWidth = 170;
        const diaColWidth = 10;
        const maxDiasPorTabela = 43;

        const totaisAlunos = alunosDaTurma.map((aluno) => {
          let faltas = 0;
          let totalAulas = 0;
          diasLetivos.forEach((dia) => {
            if (!dia.data) return;
            dia.aulas.forEach((aula) => {
              const status =
                frequenciaData[aluno.id]?.[dia.data]?.[aula.id] || "";
              if (status) {
                totalAulas++;
                if (status === "F") faltas++;
              }
            });
          });
          const freqPercent =
            totalAulas > 0
              ? Math.round(((totalAulas - faltas) / totalAulas) * 100) + "%"
              : "";
          return { id: aluno.id, faltas, freqPercent };
        });

        function criarTabelaFrequencia(diasSubset, incluirTotais) {
          const headerRow = [
            { text: "Nº", style: "tableHeader" },
            {
              text: "NOME",
              style: "tableHeader",
              alignment: "left",
              width: nomeColWidth,
            },
            ...diasSubset.map((d) => {
              if (!d.data) return { text: "", style: "tableHeader" };
              const [, m, day] = d.data.split("-");
              return {
                text: `${day}\n${m}`,
                style: "tableHeader",
                alignment: "center",
              };
            }),
          ];
          if (incluirTotais) {
            headerRow.push({
              text: "FTS",
              style: "tableHeader",
              alignment: "center",
            });
            headerRow.push({
              text: "%FRQ",
              style: "tableHeader",
              alignment: "center",
            });
          }
          const body = [headerRow];
          for (let i = 0; i < alunosDaTurma.length; i++) {
            const aluno = alunosDaTurma[i];
            const totais = totaisAlunos.find((t) => t.id === aluno.id);
            const row = [
              (i + 1).toString(),
              {
                text: aluno.nomeCompleto.padEnd(40, " "),
                alignment: "left",
                noWrap: true,
                width: nomeColWidth,
              },
            ];
            for (let j = 0; j < diasSubset.length; j++) {
              const dia = diasSubset[j];
              if (!dia.data) {
                row.push("");
                continue;
              }
              const presencas = dia.aulas
                .map((aula) => {
                  const status =
                    frequenciaData[aluno.id]?.[dia.data]?.[aula.id] || "";
                  return status;
                })
                .join("");
              row.push({ text: presencas, alignment: "center" });
            }
            if (incluirTotais) {
              row.push({
                text: totais.faltas.toString(),
                bold: true,
                alignment: "center",
              });
              row.push({ text: totais.freqPercent, alignment: "center" });
            }
            body.push(row);
          }
          const widths = [
            "auto",
            nomeColWidth,
            ...Array(diasSubset.length).fill(diaColWidth),
          ];
          if (incluirTotais) widths.push("auto", "auto");
          return {
            style: "tableExample",
            table: { headerRows: 1, widths, body },
            layout: {
              paddingLeft: (i) => (i >= 2 && i < diasSubset.length + 2 ? 1 : 4),
              paddingRight: (i) =>
                i >= 2 && i < diasSubset.length + 2 ? 1 : 4,
              paddingTop: () => 1,
              paddingBottom: () => 1,
              hLineWidth: () => 0.5,
              vLineWidth: () => 0.5,
            },
            pageBreak: "after",
          };
        }

        const tabelasFrequencia = [];
        for (let i = 0; i < diasLetivos.length; i += maxDiasPorTabela) {
          const subset = diasLetivos.slice(i, i + maxDiasPorTabela);
          while (subset.length < maxDiasPorTabela) {
            subset.push({ data: null, aulas: [] });
          }
          const incluirTotais = i + maxDiasPorTabela >= diasLetivos.length;
          tabelasFrequencia.push(criarTabelaFrequencia(subset, incluirTotais));
        }
        if (tabelasFrequencia.length > 0) {
          tabelasFrequencia[tabelasFrequencia.length - 1].pageBreak = undefined;
        }

        // ... (todo o código acima permanece igual)

        const docDefinition = {
          pageOrientation: "landscape",
          pageSize: "A4",
          pageMargins: [20, 20, 20, 40],
          content: [
            cabecalho,
            ...tabelasFrequencia,
            {
              columns: [
                {
                  width: "40%",
                  text: `Floresta do Araguaia, ${formatDatePorExtenso(diasLetivos[diasLetivos.length - 1]?.data)}`,
                  alignment: "left",
                  fontSize: 10,
                },
                {
                  width: "30%",
                  text: "_____________________________________________\nProfessor(a)",
                  alignment: "center",
                  fontSize: 10,
                },
                {
                  width: "30%",
                  text: "_____________________________________________\nCoordenador(a)",
                  alignment: "center",
                  fontSize: 10,
                },
              ],
              margin: [0, 30, 0, 0],
            },
          ],
          styles: {
            header: { fontSize: 13, bold: true },
            subheader: { fontSize: 9, bold: true },
            infoText: { fontSize: 9 },
            tableHeader: { bold: true, fontSize: 8, fillColor: "#eeeeee" },
            tableExample: { margin: [0, 5, 0, 15], fontSize: 7 },
          },
        };

        pdfMake.createPdf(docDefinition).open();
        setIsLoading(false);
      } catch (err) {
        console.error(err);
        setError(err.message);
        setIsLoading(false);
      }
    };

    generateReport();
  }, [schoolId, turmaId, year, period, componente, navigate]);

  if (isLoading) return <div>Gerando relatório...</div>;
  if (error) return <div>Erro: {error}</div>;
  return null;
}

export default RelatorioFrequenciaPage;
