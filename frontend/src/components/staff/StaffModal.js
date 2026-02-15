import { useRef, useState } from 'react';
import { Camera, Plus, Minus, Upload, FileText, X } from 'lucide-react';
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
  const certificadoInputRef = useRef(null);
  const [certificadoIdx, setCertificadoIdx] = useState(null);
  const [uploadingCertificado, setUploadingCertificado] = useState(false);
  
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
  
  // Upload de certificado
  const handleCertificadoClick = (idx, tipo) => {
    setCertificadoIdx({ idx, tipo });
    certificadoInputRef.current?.click();
  };
  
  const handleCertificadoChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file || certificadoIdx === null) return;
    
    setUploadingCertificado(true);
    try {
      // Criar FormData para upload
      const formData = new FormData();
      formData.append('file', file);
      
      const API_URL = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem('token');
      
      const response = await fetch(`${API_URL}/api/upload/certificado`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      
      if (response.ok) {
        const data = await response.json();
        const { idx, tipo } = certificadoIdx;
        
        if (tipo === 'formacao') {
          const novasFormacoes = [...staffForm.formacoes];
          // Converter string para objeto se necessário
          if (typeof novasFormacoes[idx] === 'string') {
            novasFormacoes[idx] = { nome: novasFormacoes[idx], certificado_url: data.url };
          } else {
            novasFormacoes[idx] = { ...novasFormacoes[idx], certificado_url: data.url };
          }
          setStaffForm({ ...staffForm, formacoes: novasFormacoes });
        } else if (tipo === 'especializacao') {
          const novasEspecializacoes = [...staffForm.especializacoes];
          if (typeof novasEspecializacoes[idx] === 'string') {
            novasEspecializacoes[idx] = { nome: novasEspecializacoes[idx], certificado_url: data.url };
          } else {
            novasEspecializacoes[idx] = { ...novasEspecializacoes[idx], certificado_url: data.url };
          }
          setStaffForm({ ...staffForm, especializacoes: novasEspecializacoes });
        }
      }
    } catch (error) {
      console.error('Erro ao fazer upload:', error);
    } finally {
      setUploadingCertificado(false);
      setCertificadoIdx(null);
      if (certificadoInputRef.current) {
        certificadoInputRef.current.value = '';
      }
    }
  };
  
  // Helper para obter nome da formação (string ou objeto)
  const getFormacaoNome = (f) => typeof f === 'string' ? f : f?.nome || '';
  const getFormacaoCertificado = (f) => typeof f === 'string' ? null : f?.certificado_url;
  
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editingStaff ? 'Editar Servidor(a)' : 'Novo(a) Servidor(a)'}
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
        
        {/* CPF e Matrícula */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
            <input
              type="text"
              value={staffForm.cpf || ''}
              onChange={(e) => {
                // Formatar CPF: 000.000.000-00
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                if (value.length > 9) {
                  value = value.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/, '$1.$2.$3-$4');
                } else if (value.length > 6) {
                  value = value.replace(/(\d{3})(\d{3})(\d{1,3})/, '$1.$2.$3');
                } else if (value.length > 3) {
                  value = value.replace(/(\d{3})(\d{1,3})/, '$1.$2');
                }
                setStaffForm({ ...staffForm, cpf: value });
              }}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              placeholder="000.000.000-00"
            />
          </div>
          {editingStaff && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Matrícula</label>
              <input
                type="text"
                value={editingStaff.matricula}
                disabled
                className="w-full px-3 py-2 border rounded-lg bg-gray-100 text-gray-600"
              />
              <p className="text-xs text-gray-500 mt-1">Gerada automaticamente</p>
            </div>
          )}
        </div>
        
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
              onChange={(e) => {
                // Formatar telefone: (99) 99999-9999
                let value = e.target.value.replace(/\D/g, '');
                if (value.length > 11) value = value.slice(0, 11);
                if (value.length > 10) {
                  value = value.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
                } else if (value.length > 6) {
                  value = value.replace(/(\d{2})(\d{4,5})(\d{0,4})/, '($1) $2-$3');
                } else if (value.length > 2) {
                  value = value.replace(/(\d{2})(\d{0,5})/, '($1) $2');
                } else if (value.length > 0) {
                  value = value.replace(/(\d{0,2})/, '($1');
                }
                setStaffForm({ ...staffForm, celular: value });
              }}
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
