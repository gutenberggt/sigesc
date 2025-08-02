import React, { useState, useEffect, useCallback } from 'react';
import { db } from '../firebase/config';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { useNavigate, useParams } from 'react-router-dom';

function HorarioPage() {
  const navigate = useNavigate();
  const { turmaId } = useParams(); // Recebe o ID da turma pela URL

  const [turma, setTurma] = useState(null);
  const [horario, setHorario] = useState({
    segunda: Array(5).fill(''),
    terca: Array(5).fill(''),
    quarta: Array(5).fill(''),
    quinta: Array(5).fill(''),
    sexta: Array(5).fill(''),
  });
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const diasDaSemana = [
    { id: 'segunda', nome: 'Segunda-feira' },
    { id: 'terca', nome: 'Terça-feira' },
    { id: 'quarta', nome: 'Quarta-feira' },
    { id: 'quinta', nome: 'Quinta-feira' },
    { id: 'sexta', nome: 'Sexta-feira' },
  ];

  const fetchHorario = useCallback(async () => {
    if (!turmaId) return;
    setLoading(true);
    try {
      // Busca dados da turma para exibir no cabeçalho
      const turmaRef = doc(db, 'turmas', turmaId);
      const turmaSnap = await getDoc(turmaRef);
      if (turmaSnap.exists()) {
        setTurma(turmaSnap.data());
      }

      // Busca o horário existente, se houver
      const horarioRef = doc(db, 'horarios', turmaId);
      const horarioSnap = await getDoc(horarioRef);
      if (horarioSnap.exists()) {
        setHorario(horarioSnap.data().horario);
      }
    } catch (err) {
      setError("Falha ao carregar dados do horário.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [turmaId]);

  useEffect(() => {
    fetchHorario();
  }, [fetchHorario]);

  const handleHorarioChange = (dia, aulaIndex, value) => {
    const novoHorario = { ...horario };
    novoHorario[dia][aulaIndex] = value;
    setHorario(novoHorario);
  };

  const handleSave = async () => {
    setIsSubmitting(true);
    setError('');
    setSuccess('');
    try {
      const horarioRef = doc(db, 'horarios', turmaId);
      const horarioData = {
        schoolId: turma.schoolId,
        turmaId: turmaId,
        anoLetivo: turma.anoLetivo,
        horario: horario,
      };
      await setDoc(horarioRef, horarioData, { merge: true }); // Cria ou atualiza
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
      <div className="bg-white p-8 rounded-lg shadow-md max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold mb-2 text-gray-800">Quadro de Aulas</h2>
        {turma && (
          <p className="mb-6 text-gray-600">
            Editando horário para a turma: <span className="font-semibold">{turma.nomeTurma}</span> ({turma.anoLetivo})
          </p>
        )}

        {error && <p className="text-red-500 text-center mb-4">{error}</p>}
        {success && <p className="text-green-500 text-center mb-4">{success}</p>}

        <div className="overflow-x-auto">
          <table className="min-w-full border">
            <thead>
              <tr className="bg-gray-200">
                <th className="py-2 px-3 border">Horário</th>
                {diasDaSemana.map(dia => (
                  <th key={dia.id} className="py-2 px-3 border">{dia.nome}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }, (_, i) => (
                <tr key={i}>
                  <td className="py-2 px-3 border text-center font-semibold">{i + 1}ª Aula</td>
                  {diasDaSemana.map(dia => (
                    <td key={dia.id} className="p-1 border">
                      <input
                        type="text"
                        value={horario[dia.id][i]}
                        onChange={(e) => handleHorarioChange(dia.id, i, e.target.value)}
                        className="w-full p-2 border-gray-300 rounded-md"
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end space-x-4 mt-6">
            <button onClick={() => navigate(-1)} className="bg-gray-300 hover:bg-gray-400 text-gray-800 font-bold py-2 px-4 rounded transition">
                Voltar
            </button>
            <button onClick={handleSave} disabled={isSubmitting} className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded transition">
                {isSubmitting ? 'Salvando...' : 'Salvar Horário'}
            </button>
        </div>
      </div>
    </div>
  );
}

export default HorarioPage;