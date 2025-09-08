// src/pages/eventosPage.js

import React, { useState, useEffect } from "react";
import { db } from "../firebase/config";
import {
  collection,
  getDocs,
  query,
  orderBy,
  deleteDoc,
  doc,
} from "firebase/firestore";
import { useNavigate } from "react-router-dom";
import { useUser } from "../context/UserContext";

function EventosPage() {
  const navigate = useNavigate();
  const { userData, loading: userLoading } = useUser();
  const [eventos, setEventos] = useState([]);
  const [filteredEventos, setFilteredEventos] = useState([]);
  const [loading, setLoading] = useState(true);

  const [filtroAno, setFiltroAno] = useState(
    new Date().getFullYear().toString()
  );
  const [filtroTipo, setFiltroTipo] = useState("");

  const isAdministrador = userData?.funcao?.toLowerCase() === "administrador";

  const fetchEventos = async () => {
    setLoading(true);
    try {
      const q = query(collection(db, "eventos"), orderBy("data", "asc"));
      const snapshot = await getDocs(q);
      const eventosList = snapshot.docs.map((doc) => ({
        id: doc.id,
        ...doc.data(),
      }));
      setEventos(eventosList);
      setFilteredEventos(eventosList);
    } catch (error) {
      console.error("Erro ao buscar eventos:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEventos();
  }, []);

  useEffect(() => {
    let result = eventos;
    if (filtroAno) {
      result = result.filter((evento) => evento.data.startsWith(filtroAno));
    }
    if (filtroTipo) {
      result = result.filter((evento) => evento.tipo === filtroTipo);
    }
    setFilteredEventos(result);
  }, [filtroAno, filtroTipo, eventos]);

  const handleDelete = async (id) => {
    if (window.confirm("Tem certeza que deseja excluir este evento?")) {
      try {
        await deleteDoc(doc(db, "eventos", id));
        fetchEventos();
      } catch (error) {
        console.error("Erro ao excluir evento:", error);
      }
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "";
    const [year, month, day] = dateString.split("-");
    return `${day}/${month}/${year}`;
  };

  if (userLoading || loading) {
    return <div className="p-6 text-center">Carregando...</div>;
  }

  return (
    <div className="p-6">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-6xl mx-auto">
        {" "}
        {/* Aumentado o max-w- para a tabela maior */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-gray-800">Eventos</h2>
          {isAdministrador && (
            <button
              onClick={() => navigate("/dashboard/calendario/adicionar-evento")}
              className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition"
            >
              Adicionar Evento
            </button>
          )}
        </div>
        <div className="flex space-x-4 mb-4">
          <input
            type="number"
            value={filtroAno}
            onChange={(e) => setFiltroAno(e.target.value)}
            className="p-2 border rounded-md"
            placeholder="Ano Letivo"
          />
          <select
            value={filtroTipo}
            onChange={(e) => setFiltroTipo(e.target.value)}
            className="p-2 border rounded-md"
          >
            <option value="">Todos os Tipos</option>
            <option value="FERIADO NACIONAL">Feriado Nacional</option>
            <option value="FERIADO ESTADUAL">Feriado Estadual</option>
            <option value="FERIADO MUNICIPAL">Feriado Municipal</option>
            <option value="DIA LETIVO">Dia Letivo</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white">
            <thead>
              {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
              <tr className="bg-gray-200 text-gray-600 uppercase text-sm">
                <th className="py-3 px-6 text-left">Data Inicial</th>
                <th className="py-3 px-6 text-left">Data Final</th>
                <th className="py-3 px-6 text-left">Horário</th>
                <th className="py-3 px-6 text-left">Local</th>
                <th className="py-3 px-6 text-left">Descrição</th>
                <th className="py-3 px-6 text-left">Tipo</th>
                {isAdministrador && (
                  <th className="py-3 px-6 text-center">Ações</th>
                )}
              </tr>
              {/* ======================== FIM DA ALTERAÇÃO ========================= */}
            </thead>
            <tbody className="text-gray-700">
              {userLoading || loading ? (
                <tr>
                  <td
                    colSpan={isAdministrador ? "7" : "6"}
                    className="text-center p-4"
                  >
                    Carregando...
                  </td>
                </tr>
              ) : (
                filteredEventos.map((evento) => (
                  <tr key={evento.id} className="border-b hover:bg-gray-100">
                    {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
                    <td className="py-3 px-6">{formatDate(evento.data)}</td>{" "}
                    {/* Mantido como Data Inicial */}
                    <td className="py-3 px-6">
                      {formatDate(evento.dataFinal) || "-"}
                    </td>{" "}
                    {/* Novo campo Data Final */}
                    <td className="py-3 px-6">{evento.horario || "-"}</td>{" "}
                    {/* Novo campo Horário */}
                    <td className="py-3 px-6">{evento.local || "-"}</td>{" "}
                    {/* Novo campo Local */}
                    <td className="py-3 px-6">{evento.descricao}</td>
                    <td className="py-3 px-6">{evento.tipo}</td>
                    {isAdministrador && (
                      <td className="py-3 px-6 text-center">
                        <button
                          onClick={() =>
                            navigate(
                              `/dashboard/calendario/editar-evento/${evento.id}`
                            )
                          }
                          className="text-blue-600 hover:text-blue-800 mr-3"
                        >
                          Editar
                        </button>
                        <button
                          onClick={() => handleDelete(evento.id)}
                          className="text-red-600 hover:text-red-800"
                        >
                          Excluir
                        </button>
                      </td>
                    )}
                    {/* ======================== FIM DA ALTERAÇÃO ========================= */}
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

export default EventosPage;
