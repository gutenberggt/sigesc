// src/pages/adicionarEventosPage.js

import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { doc, getDoc, setDoc, addDoc, collection } from 'firebase/firestore';
import { useNavigate, useParams } from 'react-router-dom';

function AdicionarEventosPage() {
  const navigate = useNavigate();
  const { eventoId } = useParams(); // Para o modo de edição
  const isEditing = Boolean(eventoId);

  // Estados do formulário
  const [anoLetivo, setAnoLetivo] = useState(new Date().getFullYear().toString());
  const [data, setData] = useState('');
  const [descricao, setDescricao] = useState('');
  const [tipo, setTipo] = useState('FERIADO NACIONAL');
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Se estiver editando, busca os dados do evento
  const fetchEvento = useCallback(async () => {
    if (isEditing) {
      const docRef = doc(db, 'eventos', eventoId);
      const docSnap = await getDoc(docRef);
      if (docSnap.exists()) {
        const data = docSnap.data();
        setAnoLetivo(data.anoLetivo);
        setData(data.data);
        setDescricao(data.descricao);
        setTipo(data.tipo);
      } else {
        setError("Evento não encontrado.");
      }
    }
  }, [eventoId, isEditing]);

  useEffect(() => {
    fetchEvento();
  }, [fetchEvento]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!anoLetivo || !data || !descricao || !tipo) {
      setError("Todos os campos são obrigatórios.");
      return;
    }
    setIsSubmitting(true);

    const eventoData = {
      anoLetivo,
      data,
      descricao: descricao.toUpperCase(),
      tipo,
    };

    try {
      if (isEditing) {
        // Usamos setDoc com o ID existente para atualizar
        await setDoc(doc(db, 'eventos', eventoId), eventoData);
        setSuccess("Evento atualizado com sucesso!");
      } else {
        await addDoc(collection(db, 'eventos'), eventoData);
        setSuccess("Evento cadastrado com sucesso!");
      }
      setTimeout(() => navigate('/dashboard/calendario/eventos'), 1500);
    } catch (err) {
      console.error("Erro ao salvar evento:", err);
      setError("Ocorreu um erro ao salvar o evento.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold mb-6 text-gray-800">
          {isEditing ? 'Editar Evento' : 'Adicionar Novo Evento'}
        </h2>

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="anoLetivo" className="block text-sm font-medium text-gray-700">Ano Letivo</label>
            <input type="number" id="anoLetivo" value={anoLetivo} onChange={(e) => setAnoLetivo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
          </div>
          <div>
            <label htmlFor="data" className="block text-sm font-medium text-gray-700">Data</label>
            <input type="date" id="data" value={data} onChange={(e) => setData(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
          </div>
          <div>
            <label htmlFor="descricao" className="block text-sm font-medium text-gray-700">Descrição</label>
            <input type="text" id="descricao" value={descricao} onChange={(e) => setDescricao(e.target.value)} className="mt-1 block w-full p-2 border rounded-md" />
          </div>
          <div>
            <label htmlFor="tipo" className="block text-sm font-medium text-gray-700">Tipo</label>
            <select id="tipo" value={tipo} onChange={(e) => setTipo(e.target.value)} className="mt-1 block w-full p-2 border rounded-md">
                <option value="FERIADO NACIONAL">Feriado Nacional</option>
                <option value="FERIADO ESTADUAL">Feriado Estadual</option>
                <option value="FERIADO MUNICIPAL">Feriado Municipal</option>
                <option value="RECESSO">Recesso</option>
                <option value="DIA LETIVO">Dia Letivo</option>
            </select>
          </div>
          <div className="flex justify-end space-x-4 pt-4">
            <button type="button" onClick={() => navigate('/dashboard/calendario/eventos')} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">
                Cancelar
            </button>
            <button type="submit" disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">
                {isSubmitting ? 'Salvando...' : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default AdicionarEventosPage;