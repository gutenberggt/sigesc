import { useRef } from 'react';
import { Camera, Plus, Minus } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { CARGOS, STATUS_SERVIDOR, TIPOS_VINCULO, SEXOS, COR_RACA } from './constants';

export const StaffModal = ({
  isOpen,
  onClose,
  editingStaff,
  staffForm,
  setStaffForm,
  fotoPreview,
  setFotoPreview,
  fotoFile,
  setFotoFile,
  novaFormacao,
  setNovaFormacao,
  novaEspecializacao,
  setNovaEspecializacao,
  addFormacao,
  removeFormacao,
  addEspecializacao,
  removeEspecializacao,
  onSave,
  saving
}) => {
  const fileInputRef = useRef(null);
  
  const handleFotoClick = () => {
    fileInputRef.current?.click();
  };
  
  const handleFotoChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setFotoFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setFotoPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };
  
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editingStaff ? 'Editar Servidor' : 'Novo Servidor'}
      size="lg"
    >
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Foto */}
        <div className="flex justify-center">
          <div 
            onClick={handleFotoClick}
            className="w-24 h-24 rounded-full bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center cursor-pointer hover:bg-gray-50 overflow-hidden"
          >
            {fotoPreview ? (
              <img src={fotoPreview} alt="Preview" className="w-full h-full object-cover" />
            ) : (
              <div className="text-center">
                <Camera size={24} className="mx-auto text-gray-400" />
                <span className="text-xs text-gray-500">Adicionar foto</span>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFotoChange}
            className="hidden"
          />
        </div>
        
        {/* Nome */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo *</label>
          <input
            type="text"
            value={staffForm.nome}
            onChange={(e) => setStaffForm({ ...staffForm, nome: e.target.value })}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            placeholder="Nome completo do servidor"
          />
        </div>
        
        {/* Matrícula (apenas visualização se editando) */}
        {editingStaff && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Matrícula</label>
            <input
              type="text"
              value={editingStaff.matricula}
              disabled
              className="w-full px-3 py-2 border rounded-lg bg-gray-100 text-gray-600"
            />
            <p className="text-xs text-gray-500 mt-1">Matrícula gerada automaticamente</p>
          </div>
        )}
        
        {/* Dados pessoais */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data de Nascimento</label>
            <input
              type="date"
              value={staffForm.data_nascimento}
              onChange={(e) => setStaffForm({ ...staffForm, data_nascimento: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Sexo</label>
            <select
              value={staffForm.sexo}
              onChange={(e) => setStaffForm({ ...staffForm, sexo: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Selecione</option>
              {Object.entries(SEXOS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Cor/Raça</label>
            <select
              value={staffForm.cor_raca}
              onChange={(e) => setStaffForm({ ...staffForm, cor_raca: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Selecione</option>
              {Object.entries(COR_RACA).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Contato */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Celular</label>
            <input
              type="text"
              value={staffForm.celular}
              onChange={(e) => setStaffForm({ ...staffForm, celular: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="(99) 99999-9999"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
            <input
              type="email"
              value={staffForm.email}
              onChange={(e) => setStaffForm({ ...staffForm, email: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="email@exemplo.com"
            />
          </div>
        </div>
        
        {/* Dados funcionais */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Cargo *</label>
            <select
              value={staffForm.cargo}
              onChange={(e) => setStaffForm({ ...staffForm, cargo: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(CARGOS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Vínculo</label>
            <select
              value={staffForm.tipo_vinculo}
              onChange={(e) => setStaffForm({ ...staffForm, tipo_vinculo: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(TIPOS_VINCULO).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Data de Admissão</label>
            <input
              type="date"
              value={staffForm.data_admissao}
              onChange={(e) => setStaffForm({ ...staffForm, data_admissao: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horária Semanal</label>
            <input
              type="number"
              value={staffForm.carga_horaria_semanal}
              onChange={(e) => setStaffForm({ ...staffForm, carga_horaria_semanal: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Ex: 40"
            />
          </div>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select
              value={staffForm.status}
              onChange={(e) => setStaffForm({ ...staffForm, status: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(STATUS_SERVIDOR).map(([value, { label }]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Formações */}
        <div className="p-4 bg-blue-50 rounded-lg space-y-3">
          <h4 className="font-medium text-blue-900">Formação Acadêmica</h4>
          
          <div className="flex gap-2">
            <input
              type="text"
              value={novaFormacao}
              onChange={(e) => setNovaFormacao(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addFormacao())}
              className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Ex: Licenciatura em Matemática"
            />
            <Button type="button" onClick={addFormacao} size="sm">
              <Plus size={16} />
            </Button>
          </div>
          
          {staffForm.formacoes?.length > 0 && (
            <div className="space-y-1">
              {staffForm.formacoes.map((f, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-white px-3 py-1.5 rounded border">
                  <span className="flex-1 text-sm">{f}</span>
                  <button 
                    type="button"
                    onClick={() => removeFormacao(idx)}
                    className="text-red-500 hover:text-red-700"
                  >
                    <Minus size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
          
          <h4 className="font-medium text-blue-900 pt-2">Especializações</h4>
          <div className="flex gap-2">
            <input
              type="text"
              value={novaEspecializacao}
              onChange={(e) => setNovaEspecializacao(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addEspecializacao())}
              className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="Ex: Pós-graduação em Educação Especial"
            />
            <Button type="button" onClick={addEspecializacao} size="sm">
              <Plus size={16} />
            </Button>
          </div>
          
          {staffForm.especializacoes?.length > 0 && (
            <div className="space-y-1">
              {staffForm.especializacoes.map((e, idx) => (
                <div key={idx} className="flex items-center gap-2 bg-white px-3 py-1.5 rounded border">
                  <span className="flex-1 text-sm">{e}</span>
                  <button 
                    type="button"
                    onClick={() => removeEspecializacao(idx)}
                    className="text-red-500 hover:text-red-700"
                  >
                    <Minus size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Campos de Afastamento */}
        {['afastado', 'licenca'].includes(staffForm.status) && (
          <div className="p-4 bg-yellow-50 rounded-lg space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Motivo do Afastamento</label>
              <input
                type="text"
                value={staffForm.motivo_afastamento}
                onChange={(e) => setStaffForm({ ...staffForm, motivo_afastamento: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data do Afastamento</label>
                <input
                  type="date"
                  value={staffForm.data_afastamento}
                  onChange={(e) => setStaffForm({ ...staffForm, data_afastamento: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Previsão de Retorno</label>
                <input
                  type="date"
                  value={staffForm.previsao_retorno}
                  onChange={(e) => setStaffForm({ ...staffForm, previsao_retorno: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        )}
        
        {/* Observações */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Observações</label>
          <textarea
            value={staffForm.observacoes}
            onChange={(e) => setStaffForm({ ...staffForm, observacoes: e.target.value })}
            rows={2}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>
        
        {/* Nota sobre matrícula */}
        {!editingStaff && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
            <p className="text-sm text-green-800">
              <strong>Nota:</strong> A matrícula será gerada automaticamente após salvar.
            </p>
          </div>
        )}
        
        {/* Botões */}
        <div className="flex gap-2 pt-4 border-t">
          <Button onClick={onSave} disabled={saving} className="flex-1">
            {saving ? 'Salvando...' : 'Salvar'}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
        </div>
      </div>
    </Modal>
  );
};

export default StaffModal;
