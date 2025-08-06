import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { db } from '../firebase/config';
import { doc, getDoc, collection, query, where, documentId, getDocs } from 'firebase/firestore';

function FichaServidorPage() {
  const { servidorId } = useParams();
  const navigate = useNavigate();

  const [servidor, setServidor] = useState(null);
  const [pessoa, setPessoa] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ======================= INÍCIO DAS ADIÇÕES =======================
  // FUNÇÕES DE FORMATAÇÃO
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
  // ======================== FIM DAS ADIÇÕES =========================

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

  if (loading) return <p className="p-6 text-center">Carregando...</p>;
  if (error) return <p className="p-6 text-center text-red-500">{error}</p>;
  if (!servidor || !pessoa) return <p className="p-6 text-center">Dados do servidor não encontrados.</p>;

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-4xl mx-auto">
        <div className="flex justify-between items-start mb-4">
            <div>
                <h2 className="text-2xl font-bold text-gray-800">Ficha do Servidor</h2>
                {/* ======================= INÍCIO DAS ALTERAÇÕES ======================= */}
                <p><span className="font-semibold">Nome:</span> {pessoa.nomeCompleto} <span className="font-semibold ml-4">CPF:</span> {pessoa.cpf}</p>
                <p><span className="font-semibold">Código Educacenso/Inep:</span> {pessoa.codigoINEP || 'N/A'} <span className="font-semibold ml-4">Data de Nascimento:</span> {formatDate(pessoa.dataNascimento)}</p>
                {/* ======================== FIM DAS ALTERAÇÕES ========================= */}
            </div>
            <button onClick={() => navigate(-1)} className="bg-gray-300 text-gray-800 py-2 px-4 rounded">Voltar</button>
        </div>

        {/* ======================= INÍCIO DAS ADIÇÕES ======================= */}
        {/* NOVA SEÇÃO: ENDEREÇO */}
        <div className="border-t pt-4 mb-6">
          <h3 className="text-lg font-semibold mb-2">Endereço</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <p><span className="font-semibold">Endereço Completo:</span> {`${pessoa.enderecoLogradouro || ''}, ${pessoa.enderecoNumero || ''} - ${pessoa.enderecoBairro || ''}`}</p>
            <p><span className="font-semibold">Município:</span> {`${pessoa.municipioResidencia || ''} - ${pessoa.naturalidadeEstado || ''}`}</p>
            <p><span className="font-semibold">CEP:</span> {pessoa.cep}</p>
          </div>
        </div>

        {/* NOVA SEÇÃO: DOCUMENTAÇÃO */}
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
        
        {/* NOVA SEÇÃO: CONTATOS */}
        <div className="border-t pt-4 mb-6">
          <h3 className="text-lg font-semibold mb-2">Contatos</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <p><span className="font-semibold">E-mail:</span> {pessoa.emailContato || 'N/A'}</p>
            <p><span className="font-semibold">Celular:</span> {formatTelefone(pessoa.celular)}</p>
          </div>
        </div>
        {/* ======================== FIM DAS ADIÇÕES ========================= */}

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
                                        <p><span className="font-semibold">Níveis de Ensino:</span> {funcao.niveisEnsino.join(', ')}</p>
                                        <div>
                                            <p className="font-semibold">Componentes Curriculares:</p>
                                            <ul className="list-disc list-inside ml-4 text-sm">
                                                {funcao.componentesCurriculares.map(c => <li key={c}>{c}</li>)}
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

        <div className="flex justify-end space-x-2 mt-6">
            <button onClick={() => navigate(`/dashboard/escola/servidor/editar/${servidorId}`)} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">Editar Servidor</button>
            
        </div>
      </div>
    </div>
  );
}

export default FichaServidorPage;