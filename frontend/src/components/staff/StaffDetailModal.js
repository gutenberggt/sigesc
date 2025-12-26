import { User, Phone, GraduationCap, Building2, Briefcase, CreditCard } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { CARGOS, STATUS_SERVIDOR, TIPOS_VINCULO, SEXOS, FUNCOES, TURNOS } from './constants';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const formatWhatsAppLink = (celular) => {
  if (!celular) return null;
  const numero = celular.replace(/\D/g, '');
  const numeroCompleto = numero.startsWith('55') ? numero : `55${numero}`;
  return `https://wa.me/${numeroCompleto}`;
};

export const StaffDetailModal = ({
  isOpen,
  onClose,
  selectedStaff
}) => {
  if (!selectedStaff) return null;
  
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Detalhes do Servidor"
      size="lg"
    >
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Info básica com foto */}
        <div className="p-4 bg-gray-50 rounded-lg flex gap-4">
          <div className="w-20 h-20 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden flex-shrink-0">
            {selectedStaff.foto_url ? (
              <img 
                src={`${API_URL}${selectedStaff.foto_url}`} 
                alt={selectedStaff.nome}
                className="w-full h-full object-cover"
              />
            ) : (
              <User size={32} className="text-gray-400" />
            )}
          </div>
          <div>
            <h3 className="font-bold text-lg text-gray-900">{selectedStaff.nome}</h3>
            <p className="text-gray-600">Matrícula: {selectedStaff.matricula}</p>
            <div className="mt-2 flex gap-2 flex-wrap">
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[selectedStaff.status]?.color}`}>
                {STATUS_SERVIDOR[selectedStaff.status]?.label}
              </span>
              <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {CARGOS[selectedStaff.cargo]}
              </span>
            </div>
          </div>
        </div>
        
        {/* Dados pessoais */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="text-sm text-gray-500">Celular</span>
            {selectedStaff.celular ? (
              <a
                href={formatWhatsAppLink(selectedStaff.celular)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-green-600 hover:text-green-700 font-medium"
              >
                <Phone size={14} />
                {selectedStaff.celular}
              </a>
            ) : (
              <p className="font-medium">-</p>
            )}
          </div>
          <div>
            <span className="text-sm text-gray-500">E-mail</span>
            <p className="font-medium">{selectedStaff.email || '-'}</p>
          </div>
          <div>
            <span className="text-sm text-gray-500">Data de Nascimento</span>
            <p className="font-medium">{selectedStaff.data_nascimento || '-'}</p>
          </div>
          <div>
            <span className="text-sm text-gray-500">Sexo</span>
            <p className="font-medium">{SEXOS[selectedStaff.sexo] || '-'}</p>
          </div>
        </div>
        
        {/* Dados funcionais */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="text-sm text-gray-500">Tipo de Vínculo</span>
            <p className="font-medium">{TIPOS_VINCULO[selectedStaff.tipo_vinculo]}</p>
          </div>
          <div>
            <span className="text-sm text-gray-500">Data de Admissão</span>
            <p className="font-medium">{selectedStaff.data_admissao || '-'}</p>
          </div>
          <div>
            <span className="text-sm text-gray-500">Carga Horária</span>
            <p className="font-medium">{selectedStaff.carga_horaria_semanal ? `${selectedStaff.carga_horaria_semanal}h/semana` : '-'}</p>
          </div>
        </div>
        
        {/* Formações */}
        {(selectedStaff.formacoes?.length > 0 || selectedStaff.especializacoes?.length > 0) && (
          <div className="p-4 bg-blue-50 rounded-lg">
            <h4 className="font-medium text-blue-900 mb-2 flex items-center gap-2">
              <GraduationCap size={18} />
              Formação Acadêmica
            </h4>
            {selectedStaff.formacoes?.length > 0 && (
              <div className="mb-2">
                <span className="text-sm text-gray-600 font-medium">Formações:</span>
                <ul className="list-disc list-inside text-sm">
                  {selectedStaff.formacoes.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {selectedStaff.especializacoes?.length > 0 && (
              <div>
                <span className="text-sm text-gray-600 font-medium">Especializações:</span>
                <ul className="list-disc list-inside text-sm">
                  {selectedStaff.especializacoes.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        
        {/* Lotações */}
        {selectedStaff.lotacoes?.length > 0 && (
          <div className="p-4 bg-green-50 rounded-lg">
            <h4 className="font-medium text-green-900 mb-2 flex items-center gap-2">
              <Building2 size={18} />
              Lotações
            </h4>
            <div className="space-y-2">
              {selectedStaff.lotacoes.map(lot => (
                <div key={lot.id} className="p-2 bg-white rounded border">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">{lot.school_name}</p>
                      <p className="text-sm text-gray-600">{FUNCOES[lot.funcao]} • {TURNOS[lot.turno] || '-'}</p>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      lot.status === 'ativo' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {lot.status === 'ativo' ? 'Ativo' : 'Encerrado'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {/* Alocações */}
        {selectedStaff.alocacoes?.length > 0 && (
          <div className="p-4 bg-purple-50 rounded-lg">
            <h4 className="font-medium text-purple-900 mb-2 flex items-center gap-2">
              <Briefcase size={18} />
              Turmas/Componentes
            </h4>
            <div className="space-y-2">
              {selectedStaff.alocacoes.map(aloc => (
                <div key={aloc.id} className="p-2 bg-white rounded border">
                  <p className="font-medium">{aloc.class_name}</p>
                  <p className="text-sm text-gray-600">{aloc.course_name}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        
        <Button variant="outline" onClick={onClose} className="w-full">
          Fechar
        </Button>
      </div>
    </Modal>
  );
};

export default StaffDetailModal;
