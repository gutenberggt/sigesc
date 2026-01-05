import { Trash2, Calendar } from 'lucide-react';

export const AlocacoesTable = ({
  alocacoes,
  canDelete,
  onDelete,
  filterYear
}) => {
  // Filtrar por ano se especificado
  const filteredAlocacoes = filterYear 
    ? alocacoes.filter(aloc => aloc.academic_year?.toString() === filterYear)
    : alocacoes;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Professor</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Escola</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              <div className="flex items-center gap-1">
                <Calendar size={14} />
                Ano
              </div>
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Componente</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">CH/Sem</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {filteredAlocacoes.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                Nenhuma alocação encontrada {filterYear ? `para o ano ${filterYear}` : ''}
              </td>
            </tr>
          ) : filteredAlocacoes.map(aloc => (
            <tr key={aloc.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium text-gray-900">{aloc.staff_name || '-'}</td>
              <td className="px-4 py-3 text-gray-700">{aloc.school_name}</td>
              <td className="px-4 py-3">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                  {aloc.academic_year || '-'}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-700">{aloc.class_name}</td>
              <td className="px-4 py-3 text-gray-700">{aloc.course_name}</td>
              <td className="px-4 py-3 text-gray-700">{aloc.carga_horaria_semanal || '-'}</td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  aloc.status === 'ativo' ? 'bg-green-100 text-green-800' :
                  aloc.status === 'substituido' ? 'bg-yellow-100 text-yellow-800' :
                  'bg-gray-100 text-gray-800'
                }`}>
                  {aloc.status === 'ativo' ? 'Ativo' : aloc.status === 'substituido' ? 'Substituído' : 'Encerrado'}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex justify-center gap-2">
                  {canDelete && (
                    <button
                      onClick={() => onDelete(aloc, 'alocacao')}
                      className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                      title="Excluir"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default AlocacoesTable;
