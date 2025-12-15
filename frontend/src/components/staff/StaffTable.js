import { Eye, Edit, Trash2, Phone, User, Building2, GraduationCap } from 'lucide-react';
import { CARGOS, STATUS_SERVIDOR, TIPOS_VINCULO } from './constants';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatWhatsAppLink = (celular) => {
  if (!celular) return null;
  const numero = celular.replace(/\D/g, '');
  const numeroCompleto = numero.startsWith('55') ? numero : `55${numero}`;
  return `https://wa.me/${numeroCompleto}`;
};

export const StaffTable = ({
  filteredStaff,
  canEdit,
  canDelete,
  onView,
  onEdit,
  onNewLotacao,
  onNewAlocacao,
  onDelete
}) => {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Foto</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cargo</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Vínculo</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Celular</th>
            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {filteredStaff.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                Nenhum servidor encontrado
              </td>
            </tr>
          ) : filteredStaff.map(staff => (
            <tr key={staff.id} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden">
                  {staff.foto_url ? (
                    <img 
                      src={`${API_URL}${staff.foto_url}`} 
                      alt={staff.nome}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <User size={20} className="text-gray-400" />
                  )}
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="font-medium text-gray-900">{staff.nome}</div>
                <div className="text-xs text-gray-500">Mat: {staff.matricula}</div>
              </td>
              <td className="px-4 py-3 text-gray-700">{CARGOS[staff.cargo] || staff.cargo}</td>
              <td className="px-4 py-3 text-gray-700">{TIPOS_VINCULO[staff.tipo_vinculo] || staff.tipo_vinculo}</td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[staff.status]?.color || 'bg-gray-100'}`}>
                  {STATUS_SERVIDOR[staff.status]?.label || staff.status}
                </span>
              </td>
              <td className="px-4 py-3">
                {staff.celular ? (
                  <a
                    href={formatWhatsAppLink(staff.celular)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-green-600 hover:text-green-700"
                  >
                    <Phone size={14} />
                    <span className="text-sm">{staff.celular}</span>
                  </a>
                ) : (
                  <span className="text-gray-400 text-sm">-</span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex justify-center gap-2">
                  <button
                    onClick={() => onView(staff)}
                    className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                    title="Ver detalhes"
                  >
                    <Eye size={16} />
                  </button>
                  {canEdit && (
                    <>
                      <button
                        onClick={() => onEdit(staff)}
                        className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded"
                        title="Editar"
                      >
                        <Edit size={16} />
                      </button>
                      <button
                        onClick={() => onNewLotacao(staff)}
                        className="p-1.5 text-green-600 hover:bg-green-50 rounded"
                        title="Nova Lotação"
                      >
                        <Building2 size={16} />
                      </button>
                      {staff.cargo === 'professor' && (
                        <button
                          onClick={() => onNewAlocacao(staff)}
                          className="p-1.5 text-purple-600 hover:bg-purple-50 rounded"
                          title="Alocar Turma"
                        >
                          <GraduationCap size={16} />
                        </button>
                      )}
                    </>
                  )}
                  {canDelete && (
                    <button
                      onClick={() => onDelete(staff, 'staff')}
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

export default StaffTable;
