import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { db } from '../firebase/config';
import { doc, getDoc, collection, query, where, documentId, getDocs } from 'firebase/firestore';
import { FaFilePdf } from 'react-icons/fa';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

function FichaServidorPage() {
  const { servidorId } = useParams();
  const navigate = useNavigate();

  const printRef = useRef();
  const [isExporting, setIsExporting] = useState(false);

  const [servidor, setServidor] = useState(null);
  const [pessoa, setPessoa] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const formatDate = (dateString) => {
    if (!dateString || !/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
      return 'N/A';
    }
    const [year, month, day] = dateString.split('-');
    return `${day}/${month}/${year}`;
  };

  const formatTelefone = (value) => {
    if (!value) return 'N/A';
    value = value.replace(/\D/g, '');
    if (value.length > 11) value = value.substring(0, 11);
    if (value.length > 6) {
      value = value.replace(/^(\d{2})(\d)/g, '($1) $2');
      value = value.replace(/(\d)(\d{4})$/, '$1-$2');
    }
    return value;
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const servidorDocRef = doc(db, 'servidores', servidorId);
      const servidorDocSnap = await getDoc(servidorDocRef);
      if (!servidorDocSnap.exists()) {
        setError("Documento do servidor não encontrado.");
        setLoading(false);
        return;
      }
      const servidorData = servidorDocSnap.data();

      const pessoaDocRef = doc(db, 'pessoas', servidorData.pessoaId);
      const pessoaDocSnap = await getDoc(pessoaDocRef);
      if (pessoaDocSnap.exists()) {
        setPessoa(pessoaDocSnap.data());
      } else {
        setError("Dados da pessoa não encontrados.");
      }

      if (servidorData.alocacoes && servidorData.alocacoes.length > 0) {
        const schoolIds = [...new Set(servidorData.alocacoes.map(aloc => aloc.schoolId))];
        const schoolsMap = new Map();

        if (schoolIds.length > 0) {
          const schoolsQuery = query(collection(db, 'schools'), where(documentId(), 'in', schoolIds));
          const schoolsSnapshot = await getDocs(schoolsQuery);
          schoolsSnapshot.docs.forEach(doc => schoolsMap.set(doc.id, doc.data().nomeEscola));
        }

        const enrichedAlocacoes = servidorData.alocacoes.map(aloc => ({
          ...aloc,
          escolaNome: schoolsMap.get(aloc.schoolId) || 'Escola não encontrada'
        }));

        setServidor({ ...servidorData, alocacoes: enrichedAlocacoes });
      } else {
        setServidor(servidorData);
      }

    } catch (err) {
      console.error(err);
      setError("Ocorreu um erro ao carregar os dados.");
    } finally {
      setLoading(false);
    }
  }, [servidorId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleExportClick = () => { setIsExporting(true); };

  // ======================= INÍCIO DA MUDANÇA =======================
  // EFEITO DE EXPORTAÇÃO REESCRITO COM LÓGICA DE 'FATIAR' O CONTEÚDO
  useEffect(() => {
    if (isExporting) {
      const exportPDF = async () => {
        const element = printRef.current;
        const canvas = await html2canvas(element, { scale: 2, useCORS: true });
        
        const pdf = new jsPDF('p', 'mm', 'a4');
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = pdf.internal.pageSize.getHeight();
        
        const canvasWidth = canvas.width;
        const canvasHeight = canvas.height;
        const canvasAspectRatio = canvasHeight / canvasWidth;
        const scaledCanvasHeight = pdfWidth * canvasAspectRatio;

        const marginTop = 15;
        const marginBottom = 15;
        const pageContentHeight = pdfHeight - marginTop - marginBottom;
        
        let yOffset = 0;
        let pages = 0;
        
        // Loop para 'fatiar' o canvas em páginas
        while (yOffset < scaledCanvasHeight) {
            pages++;
            // A última página pode ser menor
            const sliceHeight = Math.min(pageContentHeight, scaledCanvasHeight - yOffset);
            
            // Converte a altura da fatia em mm para pixels do canvas original
            const sliceHeightInCanvasPixels = (sliceHeight / pdfWidth) * canvasWidth;
            const yOffsetInCanvasPixels = (yOffset / pdfWidth) * canvasWidth;

            // Cria um canvas temporário para cada página
            const pageCanvas = document.createElement('canvas');
            pageCanvas.width = canvasWidth;
            pageCanvas.height = sliceHeightInCanvasPixels;
            const pageCtx = pageCanvas.getContext('2d');
            
            // Copia a 'fatia' do canvas principal para o canvas da página
            pageCtx.drawImage(canvas, 0, yOffsetInCanvasPixels, canvasWidth, sliceHeightInCanvasPixels, 0, 0, canvasWidth, sliceHeightInCanvasPixels);
            
            const pageImgData = pageCanvas.toDataURL('image/png');
            
            if (pages > 1) {
              pdf.addPage();
            }
            
            pdf.addImage(pageImgData, 'PNG', 0, marginTop, pdfWidth, sliceHeight);
            
            yOffset += sliceHeight;
        }

        // Adiciona a numeração de páginas em um loop separado
        for (let i = 1; i <= pages; i++) {
          pdf.setPage(i);
          pdf.setFontSize(8);
          pdf.setTextColor(128);
          pdf.text(`Página ${i} de ${pages}`, pdfWidth / 2, pdfHeight - (marginBottom / 2), { align: 'center' });
        }
        
        pdf.save(`ficha_servidor_${pessoa.nomeCompleto}.pdf`);
        setIsExporting(false);
      };
      
      setTimeout(exportPDF, 100);
    }
  }, [isExporting, pessoa]);
  // ======================== FIM DA MUDANÇA =========================

  if (loading) return <p className="p-6 text-center">Carregando...</p>;
  if (error) return <p className="p--6 text-center text-red-500">{error}</p>;
  if (!servidor || !pessoa) return <p className="p-6 text-center">Dados do servidor não encontrados.</p>;

  return (
    <div className="p-6 bg-gray-50">
      <div className="flex justify-end items-center mb-4 max-w-4xl mx-auto print:hidden">
        <div className="flex space-x-2">
          <button onClick={handleExportClick} className="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition flex items-center">
            <FaFilePdf className="mr-2" /> Exportar
          </button>
          <button onClick={() => navigate(-1)} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">Voltar</button>
        </div>
      </div>

      <div ref={printRef} className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <header className={isExporting ? 'block mb-8' : 'hidden'}>
          <div className="flex justify-between items-center">
            <div className="text-left">
              <h4 className="font-bold text-lg">Prefeitura Municipal de Floresta do Araguaia</h4>
              <p className="text-md">Secretaria Municipal de Educação</p>
            </div>
            <img src="/brasao_floresta.png" alt="Brasão de Floresta do Araguaia" className="w-24 h-24 object-contain" />
          </div>
          <hr className="my-4 border-t-2 border-gray-300" />
        </header>

        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-2xl font-bold text-gray-800">Ficha do Servidor</h2>
            <p><span className="font-semibold">Nome:</span> {pessoa.nomeCompleto} <span className="font-semibold ml-4">CPF:</span> {pessoa.cpf}</p>
            <p><span className="font-semibold">Código Educacenso/Inep:</span> {pessoa.codigoINEP || 'N/A'} <span className="font-semibold ml-4">Data de Nascimento:</span> {formatDate(pessoa.dataNascimento)}</p>
          </div>
        </div>

        <div className="border-t pt-4 mb-6">
          <h3 className="text-lg font-semibold mb-2">Endereço</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <p><span className="font-semibold">Endereço Completo:</span> {`${pessoa.enderecoLogradouro || ''}, ${pessoa.enderecoNumero || ''} - ${pessoa.enderecoBairro || ''}`}</p>
            <p><span className="font-semibold">Município:</span> {`${pessoa.municipioResidencia || ''} - ${pessoa.naturalidadeEstado || ''}`}</p>
            <p><span className="font-semibold">CEP:</span> {pessoa.cep}</p>
          </div>
        </div>

        <div className="border-t pt-4 mb-6">
          <h3 className="text-lg font-semibold mb-2">Documentação</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <p><span className="font-semibold">RG:</span> {pessoa.rgNumero || 'N/A'}</p>
            <p><span className="font-semibold">Órgão Emissor:</span> {`${pessoa.rgOrgaoEmissor || ''} - ${pessoa.rgEstado || ''}`}</p>
            <p><span className="font-semibold">Data de Emissão:</span> {formatDate(pessoa.rgDataEmissao)}</p>
            <p><span className="font-semibold">NIS/PIS/PASEP:</span> {pessoa.nisPisPasep || 'N/A'}</p>
            <p><span className="font-semibold">Cartão do SUS:</span> {pessoa.carteiraSUS || 'N/A'}</p>
          </div>
        </div>

        <div className="border-t pt-4 mb-6">
          <h3 className="text-lg font-semibold mb-2">Contatos</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <p><span className="font-semibold">E-mail:</span> {pessoa.emailContato || 'N/A'}</p>
            <p><span className="font-semibold">Celular:</span> {formatTelefone(pessoa.celular)}</p>
          </div>
        </div>

        <div className="border-t pt-4">
          <h3 className="text-xl font-semibold mb-4">Alocações e Funções</h3>
          {servidor.alocacoes && servidor.alocacoes.length > 0 ? (
            servidor.alocacoes.map((alocacao, index) => (
              <div key={index} className="mb-6 p-4 border rounded-lg bg-gray-50">
                <h4 className="text-lg font-bold text-blue-700">{alocacao.escolaNome}</h4>
                <p className="text-sm text-gray-600 mb-4">Ano Letivo: {alocacao.anoLetivo}</p>

                {alocacao.funcoes.map((funcao, funcIndex) => (
                  <div key={funcIndex} className="p-3 border-t">
                    <p><span className="font-semibold">Função:</span> {funcao.funcao}</p>
                    {funcao.funcao === 'Professor(a)' && (
                      <>
                        <p><span className="font-semibold">Turma:</span> {funcao.turmaNome || 'Não especificada'}</p>
                        <p><span className="font-semibold">Níveis de Ensino:</span> {funcao.niveisEnsino?.join(', ') || 'Nenhum nível especificado'}</p>

                        <div>
                          <p className="font-semibold">Componentes Curriculares:</p>
                          <ul className="list-disc list-inside ml-4 text-sm">
                            {funcao.componentesCurriculares?.map(c => <li key={c}>{c}</li>)}
                          </ul>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ))
          ) : (
            <p className="text-gray-500">Nenhuma alocação encontrada para este servidor.</p>
          )}
        </div>
        
        {!isExporting && (
            <div className="flex justify-end space-x-2 mt-6">
                <button onClick={() => navigate(`/dashboard/escola/servidor/editar/${servidorId}`)} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">Editar Servidor</button>
            </div>
        )}

      </div>
    </div>
  );
}

export default FichaServidorPage;