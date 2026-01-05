import { Trash2, XCircle, Calendar } from 'lucide-react';
import { FUNCOES, TURNOS } from './constants';

export const LotacoesTable = ({
  lotacoes,
  canEdit,
  canDelete,
  onEncerrar,
  onDelete,
  filterYear
}) => {
  // Filtrar por ano se especificado
  const filteredLotacoes = filterYear 
    ? lotacoes.filter(lot => lot.academic_year?.toString() === filterYear)
    : lotacoes;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Servidor</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Escola</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              <div className="flex items-center gap-1">
                <Calendar size={14} />
                Ano
              </div>
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Função</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turno</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Período</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {filteredLotacoes.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                Nenhuma lotação encontrada {filterYear ? `para o ano ${filterYear}` : ''}
              </td>
            </tr>
          ) : filteredLotacoes.map(lot => (
            <tr key={lot.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="font-medium text-gray-900">{lot.staff?.nome || lot.staff?.user_name || lot.staff_name || '-'}</div>
                <div className="text-sm text-gray-500">{lot.staff?.matricula || lot.staff_matricula}</div>
              </td>
              <td className="px-4 py-3 text-gray-700">{lot.school_name}</td>
              <td className="px-4 py-3">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                  {lot.academic_year || '-'}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-700">{FUNCOES[lot.funcao] || lot.funcao}</td>
              <td className="px-4 py-3 text-gray-700">{TURNOS[lot.turno] || lot.turno || '-'}</td>
              <td className="px-4 py-3 text-sm text-gray-700">
                {lot.data_inicio} {lot.data_fim ? `- ${lot.data_fim}` : '- atual'}
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  lot.status === 'ativo' ? 'bg-green-100 text-green-800' :
                  lot.status === 'encerrado' ? 'bg-gray-100 text-gray-800' :
                  'bg-yellow-100 text-yellow-800'
                }`}>
                  {lot.status === 'ativo' ? 'Ativo' : lot.status === 'encerrado' ? 'Encerrado' : 'Transferido'}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex justify-center gap-2">
                  {canEdit && lot.status === 'ativo' && (
                    <button
                      onClick={() => onEncerrar(lot)}
                      className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded"
                      title="Encerrar Lotação"
                    >
                      <XCircle size={16} />
                    </button>
                  )}
                  {canDelete && (
                    <button
                      onClick={() => onDelete(lot, 'lotacao')}
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

export default LotacoesTable;
