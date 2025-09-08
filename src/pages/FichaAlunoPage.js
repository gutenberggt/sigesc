import React, { useState, useEffect, useCallback, useRef } from "react";
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
  orderBy,
} from "firebase/firestore";
import { FaUserCircle, FaFilePdf } from "react-icons/fa";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";

// Funções de Formatação (Helpers)
const formatDate = (dateString) => {
  if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
    return "Não Informado";
  }
  const [year, month, day] = dateString.split("-");
  return `${day}/${month}/${year}`;
};

const formatTelefone = (value) => {
  if (!value) return "Não Informado";
  value = value.replace(/\D/g, "");
  if (value.length > 11) value = value.substring(0, 11);
  if (value.length > 6) {
    value = value.replace(/^(\d{2})(\d)/g, "($1) $2");
    value = value.replace(/(\d)(\d{4})$/, "$1-$2");
  }
  return value;
};

// Objeto de Configuração da Ficha (Data-Driven Layout)
const fichaConfig = {
  dadosPessoais: {
    title: "Dados Pessoais",
    fields: [
      {
        label: "Nome",
        accessor: (data) => data.aluno?.nomeCompleto,
        colSpan: { md: 4, lg: 4 },
      },
      {
        label: "CPF",
        accessor: (data) => data.aluno?.cpf,
        colSpan: { md: 2, lg: 2 },
      },
      {
        label: "Data/Nasc.",
        accessor: (data) => data.aluno?.dataNascimento,
        format: formatDate,
        colSpan: { md: 1, lg: 1 },
      },
      {
        label: "Sexo",
        accessor: (data) => data.aluno?.sexo,
        colSpan: { md: 1, lg: 1 },
      },
      {
        label: "Est. Civil",
        accessor: (data) => data.aluno?.estadoCivil,
        colSpan: { md: 1, lg: 1 },
      },
      {
        label: "Nacional.",
        accessor: (data) => data.aluno?.nacionalidade,
        colSpan: { md: 1, lg: 1 },
      },
      {
        label: "Naturalidade",
        accessor: (data) =>
          `${data.aluno?.naturalidadeCidade || ""} - ${data.aluno?.naturalidadeEstado || ""}`,
        colSpan: { md: 2, lg: 2 },
      },
      {
        label: "Raça",
        accessor: (data) => data.aluno?.raca,
        colSpan: { md: 2, lg: 2 },
      },
      {
        label: "Religião",
        accessor: (data) => data.aluno?.religião,
        colSpan: { md: 2, lg: 2 },
      },
    ],
  },
  endereco: {
    title: "Endereço",
    fields: [
      {
        label: "Endereço Completo",
        accessor: (data) =>
          `${data.aluno?.enderecoLogradouro || ""}, ${data.aluno?.enderecoNumero || ""} - ${data.aluno?.enderecoBairro || ""}`,
        colSpan: { md: 4, lg: 4 },
      },
      {
        label: "Município",
        accessor: (data) => data.aluno?.municipioResidencia,
        colSpan: { md: 2, lg: 2 },
      },
      {
        label: "CEP",
        accessor: (data) => data.aluno?.cep,
        colSpan: { md: 1, lg: 1 },
      },
      {
        label: "Ponto de Referência",
        accessor: (data) => data.aluno?.pontodeReferencia,
        colSpan: { md: 5, lg: 5 },
      },
    ],
  },
  informacoesFamiliares: {
    title: "Informações Familiares",
    isSectioned: true,
    sections: {
      mae: {
        title: "Mãe",
        fields: [
          { label: "Nome", accessor: (data) => data.aluno?.pessoaMae },
          {
            label: "Telefone",
            accessor: (data) => data.aluno?.telefoneMae,
            format: formatTelefone,
          },
          {
            label: "Escolaridade",
            accessor: (data) => data.aluno?.escolaridadeMae,
          },
          { label: "Profissão", accessor: (data) => data.aluno?.profissaoMae },
        ],
      },
      pai: {
        title: "Pai",
        fields: [
          { label: "Nome", accessor: (data) => data.aluno?.pessoaPai },
          {
            label: "Telefone",
            accessor: (data) => data.aluno?.telefonePai,
            format: formatTelefone,
          },
          {
            label: "Escolaridade",
            accessor: (data) => data.aluno?.escolaridadePai,
          },
          { label: "Profissão", accessor: (data) => data.aluno?.profissaoPai },
        ],
      },
    },
  },
  documentacao: {
    title: "Documentação",
    fields: [
      {
        label: "RG",
        accessor: (data) => data.aluno?.rgNumero,
        colSpan: { md: 2 },
      },
      {
        label: "Órgão Emissor",
        accessor: (data) =>
          `${data.aluno?.rgOrgaoEmissor || ""} - ${data.aluno?.rgEstado || ""}`,
        colSpan: { md: 1 },
      },
      {
        label: "Data/Emissão",
        accessor: (data) => data.aluno?.rgDataEmissao,
        format: formatDate,
        colSpan: { md: 1 },
      },
      {
        label: "NIS/PIS/PASEP",
        accessor: (data) => data.aluno?.nisPisPasep,
        colSpan: { md: 1 },
      },
      {
        label: "Cartão do SUS",
        accessor: (data) => data.aluno?.carteiraSUS,
        colSpan: { md: 1 },
      },
    ],
  },
  contatos: {
    title: "Contatos",
    fields: [
      {
        label: "E-mail",
        accessor: (data) => data.aluno?.emailContato,
        colSpan: { md: 2 },
      },
      {
        label: "Celular",
        accessor: (data) => data.aluno?.celular,
        format: formatTelefone,
        colSpan: { md: 2 },
      },
      {
        label: "Telefone",
        accessor: (data) => data.aluno?.telefoneResidencial,
        format: formatTelefone,
        colSpan: { md: 2 },
      },
    ],
  },
};

function FichaAlunoPage() {
  const { alunoId } = useParams();
  const navigate = useNavigate();
  const printRef = useRef();

  const [aluno, setAluno] = useState(null);
  const [matriculas, setMatriculas] = useState([]);
  const [matriculaPrincipal, setMatriculaPrincipal] = useState(null);
  const [escolaPrincipal, setEscolaPrincipal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isExporting, setIsExporting] = useState(false);

  const handleExportClick = () => {
    setIsExporting(true);
  };

  useEffect(() => {
    if (isExporting) {
      const exportPDF = async () => {
        const element = printRef.current;
        const canvas = await html2canvas(element, { scale: 2, useCORS: true });

        const imgData = canvas.toDataURL("image/png");
        const pdf = new jsPDF("p", "mm", "a4");
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pageHeight = pdf.internal.pageSize.getHeight();
        const imgWidth = canvas.width;
        const imgHeight = canvas.height;
        const ratio = imgWidth / pdfWidth;
        const scaledImgHeight = imgHeight / ratio;
        let heightLeft = scaledImgHeight;
        let position = 0;
        pdf.addImage(imgData, "PNG", 0, position, pdfWidth, scaledImgHeight);
        heightLeft -= pageHeight;
        while (heightLeft > 0) {
          position = position - pageHeight;
          pdf.addPage();
          pdf.addImage(imgData, "PNG", 0, position, pdfWidth, scaledImgHeight);
          heightLeft -= pageHeight;
        }
        pdf.save(`ficha_aluno_${aluno.nomeCompleto}.pdf`);
        setIsExporting(false);
      };
      exportPDF();
    }
  }, [isExporting, aluno]);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const alunoDocRef = doc(db, "pessoas", alunoId);
        const alunoDocSnap = await getDoc(alunoDocRef);

        if (!alunoDocSnap.exists()) {
          setError("Aluno não encontrado.");
          setLoading(false); // Adicionado para parar o carregamento em caso de erro
          return;
        }
        setAluno({ id: alunoDocSnap.id, ...alunoDocSnap.data() });

        const matriculasQuery = query(
          collection(db, "matriculas"),
          where("pessoaId", "==", alunoId),
          orderBy("dataMatricula", "desc")
        );
        const matriculasSnapshot = await getDocs(matriculasQuery);
        const matriculasList = matriculasSnapshot.docs.map((doc) => ({
          id: doc.id,
          ...doc.data(),
        }));

        if (matriculasList.length > 0) {
          const principal = matriculasList[0];
          setMatriculaPrincipal(principal);
          const schoolIds = [
            ...new Set(matriculasList.map((m) => m.escolaId).filter(Boolean)),
          ];
          const turmaIds = [
            ...new Set(matriculasList.map((m) => m.turmaId).filter(Boolean)),
          ];

          const schoolsMap = new Map();
          if (schoolIds.length > 0) {
            const schoolsQuery = query(
              collection(db, "schools"),
              where(documentId(), "in", schoolIds)
            );
            const schoolsSnapshot = await getDocs(schoolsQuery);
            schoolsSnapshot.docs.forEach((doc) =>
              schoolsMap.set(doc.id, doc.data())
            );
          }
          if (schoolsMap.has(principal.escolaId)) {
            setEscolaPrincipal(schoolsMap.get(principal.escolaId));
          }
          const turmasMap = new Map();
          if (turmaIds.length > 0) {
            const turmasQuery = query(
              collection(db, "turmas"),
              where(documentId(), "in", turmaIds)
            );
            const turmasSnapshot = await getDocs(turmasQuery);
            turmasSnapshot.docs.forEach((doc) =>
              turmasMap.set(doc.id, doc.data().nomeTurma)
            );
          }
          const enrichedMatriculas = matriculasList.map((matricula) => ({
            ...matricula,
            nomeEscola:
              schoolsMap.get(matricula.escolaId)?.nomeEscola || "Não Informado",
            nomeTurma: turmasMap.get(matricula.turmaId) || "Não Informado",
          }));
          setMatriculas(enrichedMatriculas);
        }
      } catch (err) {
        console.error("Erro ao buscar dados do aluno:", err);
        setError("Falha ao carregar dados do aluno.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [alunoId]);

  if (loading)
    return <div className="p-6 text-center">Carregando ficha do aluno...</div>;
  if (error) return <div className="p-6 text-center text-red-600">{error}</div>;
  if (!aluno) return null;

  const allData = { aluno, matriculaPrincipal, escolaPrincipal };
  const { dadosPessoais, ...otherSections } = fichaConfig;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6 print:hidden">
          <h2 className="text-3xl font-bold text-gray-800">Ficha do Aluno</h2>
          <div className="flex space-x-2">
            <button
              onClick={handleExportClick}
              className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition flex items-center"
            >
              <FaFilePdf className="mr-2" /> Exportar
            </button>
            <button
              onClick={() => navigate(-1)}
              className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition"
            >
              Voltar
            </button>
          </div>
        </div>

        <div ref={printRef} className="bg-white p-4 sm:p-8">
          <div className={isExporting ? "block" : "hidden"}>
            <header className="mb-8">
              <div className="flex justify-between items-center">
                <div className="text-left text-xs sm:text-base">
                  <h4 className="font-bold text-lg">
                    Prefeitura Municipal de Floresta do Araguaia
                  </h4>
                  <p className="text-md">Secretaria Municipal de Educação</p>
                  {/* ======================= INÍCIO DA CORREÇÃO ======================= */}
                  <p className="font-semibold text-md">
                    {escolaPrincipal?.nomeEscola || "Escola não informada"}
                  </p>
                  <p className="text-sm text-gray-600">
                    {`${escolaPrincipal?.rua || "Rua não informada"}, ${escolaPrincipal?.numero || "S/N"} - ${escolaPrincipal?.bairro || "Bairro não informado"}, ${escolaPrincipal?.municipio || "Município não informado"} - ${escolaPrincipal?.uf || "UF"} - CEP: ${escolaPrincipal?.cep || "CEP não informado"}`}
                  </p>
                  {/* ======================== FIM DA CORREÇÃO ========================= */}
                </div>
                <img
                  src="/brasao_floresta.png"
                  alt="Brasão de Floresta do Araguaia"
                  className="w-20 h-20 sm:w-24 sm:h-24 object-contain"
                />
              </div>
              <hr className="my-4 border-t-2 border-gray-300" />
            </header>
          </div>

          <div className="bg-white p-8 rounded-lg shadow-md mb-2">
            <div className="flex flex-col md:flex-row gap-8">
              <div className="flex-shrink-0 flex flex-col items-center">
                {matriculaPrincipal?.fotoURL ? (
                  <img
                    src={matriculaPrincipal.fotoURL}
                    alt="Foto do Aluno"
                    className="w-32 h-40 object-cover rounded-lg border-2 border-gray-200 shadow-md"
                  />
                ) : (
                  <div className="w-32 h-40 bg-gray-200 rounded-lg flex items-center justify-center border-2 border-gray-300">
                    <FaUserCircle size={80} className="text-gray-400" />
                  </div>
                )}
                <div className="mt-4 text-center">
                  <span className="font-semibold block">Código Aluno:</span>
                  <span>
                    {matriculaPrincipal?.codigoAluno || "Não Informado"}
                  </span>
                </div>
              </div>
              <div className="flex-grow">
                <h3 className="text-xl font-bold mb-4 text-gray-700 border-b pb-2">
                  {dadosPessoais.title}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-x-6 gap-y-2">
                  {dadosPessoais.fields.map((field) => {
                    const colSpanClasses = `col-span-full lg:col-span-${field.colSpan.lg || 6} md:col-span-${field.colSpan.md || 6}`;
                    const value = field.accessor(allData);
                    const formattedValue = field.format
                      ? field.format(value)
                      : value;
                    return (
                      <div key={field.label} className={colSpanClasses}>
                        <span className="font-semibold text-gray-600">
                          {field.label}:
                        </span>{" "}
                        {formattedValue || "Não Informado"}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {Object.values(otherSections).map((section) => (
            <div
              key={section.title}
              className="bg-white p-8 rounded-lg shadow-md mb-2"
            >
              <h3 className="text-xl font-bold mb-4 text-gray-700 border-b pb-2">
                {section.title}
              </h3>
              {section.isSectioned ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                  {Object.values(section.sections).map((subSection) => (
                    <div key={subSection.title} className="space-y-2">
                      <h4 className="text-lg font-semibold text-gray-600">
                        {subSection.title}
                      </h4>
                      {subSection.fields.map((field) => {
                        const value = field.accessor(allData);
                        const formattedValue = field.format
                          ? field.format(value)
                          : value;
                        return (
                          <p key={field.label}>
                            <span className="font-semibold">
                              {field.label}:
                            </span>{" "}
                            {formattedValue || "Não Informado"}
                          </p>
                        );
                      })}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-x-6 gap-y-1">
                  {section.fields.map((field) => {
                    const colSpanClasses = `col-span-full lg:col-span-${field.colSpan.lg || 6} md:col-span-${field.colSpan.md || 6}`;
                    const value = field.accessor(allData);
                    const formattedValue = field.format
                      ? field.format(value)
                      : value;
                    return (
                      <div key={field.label} className={colSpanClasses}>
                        <span className="font-semibold text-gray-600">
                          {field.label}:
                        </span>{" "}
                        {formattedValue || "Não Informado"}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          <div className="bg-white p-8 rounded-lg shadow-md">
            <h3 className="text-xl font-bold mb-4 text-gray-700 border-b pb-2">
              Histórico de Matrículas
            </h3>
            <div className="overflow-x-auto">
              <table className="min-w-full bg-white">
                <thead>
                  <tr className="bg-gray-200 text-gray-600 uppercase text-sm leading-normal">
                    <th className="py-3 px-6 text-left">Ano</th>
                    <th className="py-3 px-6 text-left">Escola</th>
                    <th className="py-3 px-6 text-left">Curso</th>
                    <th className="py-3 px-6 text-left">Série</th>
                    <th className="py-3 px-6 text-left">Turma</th>
                    <th className="py-3 px-6 text-left">Situação</th>
                    <th className="py-3 px-6 text-left">Data de Matrícula</th>
                  </tr>
                </thead>
                <tbody className="text-gray-600 text-sm font-light">
                  {matriculas.map((m) => (
                    <tr
                      key={m.id}
                      className="border-b border-gray-200 hover:bg-gray-100"
                    >
                      <td className="py-3 px-6 text-left">{m.anoLetivo}</td>
                      <td className="py-3 px-6 text-left">{m.nomeEscola}</td>
                      <td className="py-3 px-6 text-left">{m.nivelEnsino}</td>
                      <td className="py-3 px-6 text-left">{m.anoSerie}</td>
                      <td className="py-3 px-6 text-left">{m.nomeTurma}</td>
                      <td className="py-3 px-6 text-left">
                        {m.situacaoMatricula}
                      </td>
                      <td className="py-3 px-6 text-left">
                        {formatDate(m.dataMatricula)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div
              className={`flex justify-end space-x-4 mt-6 ${isExporting ? "hidden" : ""}`}
            >
              <button
                onClick={() =>
                  navigate(`/dashboard/escola/aluno/editar/${alunoId}`)
                }
                className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition"
              >
                Editar Aluno
              </button>
              <button
                onClick={() =>
                  navigate(`/dashboard/escola/aluno/nova-matricula/${alunoId}`)
                }
                className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition"
              >
                Nova Matrícula
              </button>
            </div>
          </div>

          <div className={isExporting ? "block mt-16 pt-16" : "hidden"}>
            <div className="flex justify-around text-center">
              <div className="w-2/5">
                <hr className="border-t border-gray-800" />
                <p className="mt-2 text-sm">
                  Assinatura do Responsável pelo Aluno
                </p>
              </div>
              <div className="w-2/f">
                <hr className="border-t border-gray-800" />
                <p className="mt-2 text-sm">Responsável pela Matrícula</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default FichaAlunoPage;
