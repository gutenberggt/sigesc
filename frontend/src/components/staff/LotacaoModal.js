import { Building2, Plus, Minus, Calendar } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { CARGOS, FUNCOES, TURNOS } from './constants';

export const LotacaoModal = ({
  isOpen,
  onClose,
  lotacaoForm,
  setLotacaoForm,
  staffList,
  schools,
  lotacaoEscolas,
  selectedLotacaoSchool,
  setSelectedLotacaoSchool,
  existingLotacoes,
  loadingExisting,
  canDelete,
  onStaffChange,
  onYearChange,
  onAddEscola,
  onRemoveEscola,
  onDeleteExisting,
  onSave,
  saving
}) => {
  const currentYear = new Date().getFullYear();
  const selectedYear = lotacaoForm.academic_year || currentYear;
  
  // Filtrar lotações pelo ano selecionado
  const lotacoesDoAno = existingLotacoes.filter(
    lot => lot.academic_year === selectedYear || !lot.academic_year
  );
  
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Gerenciar Lotações"
    >
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Seletor de Ano Letivo - PRIMEIRO */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <label className="block text-sm font-medium text-blue-800 mb-1 flex items-center gap-2">
            <Calendar size={16} />
            Ano Letivo *
          </label>
          <select
            value={selectedYear}
            onChange={(e) => onYearChange(parseInt(e.target.value))}
            className="w-full px-3 py-2 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white font-medium"
          >
            {[2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022].map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
          <p className="text-xs text-blue-600 mt-1">
            Selecione o ano para visualizar e adicionar lotações
          </p>
        </div>
        
        {/* Servidor */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Servidor *</label>
          <select
            value={lotacaoForm.staff_id}
            onChange={(e) => onStaffChange(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Selecione o servidor</option>
            {staffList.filter(s => s.status === 'ativo').map(s => (
              <option key={s.id} value={s.id}>
                {s.nome} - {s.matricula} ({CARGOS[s.cargo]})
              </option>
            ))}
          </select>
        </div>
        
        {/* Lotações existentes do ano selecionado */}
        {lotacaoForm.staff_id && (
          <div className="p-4 bg-gray-50 rounded-lg border">
            <h4 className="font-medium text-gray-800 mb-2 flex items-center gap-2">
              <Building2 size={16} />
              Lotações em {selectedYear}
              {loadingExisting && <span className="text-gray-400 text-sm">(carregando...)</span>}
            </h4>
            
            {!loadingExisting && lotacoesDoAno.length === 0 ? (
              <p className="text-sm text-gray-500 italic">
                O servidor não possui lotação em {selectedYear}.
              </p>
            ) : (
              <div className="space-y-2">
                {lotacoesDoAno.map(lot => (
                  <div key={lot.id} className="flex items-center gap-2 bg-white px-3 py-2 rounded border">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{lot.school_name}</p>
                      <p className="text-xs text-gray-500">
                        {FUNCOES[lot.funcao]} • {TURNOS[lot.turno] || 'Sem turno'} • Desde {lot.data_inicio}
                        {lot.academic_year && <span className="ml-1 text-blue-600">• Ano: {lot.academic_year}</span>}
                      </p>
                    </div>
                    {canDelete && (
                      <button 
                        type="button"
                        onClick={() => onDeleteExisting(lot.id)}
                        className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                        title="Excluir lotação"
                      >
                        <Minus size={16} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* Adicionar nova lotação */}
        {lotacaoForm.staff_id && (
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
              <Plus size={16} />
              Adicionar Nova Lotação para {selectedYear}
            </h4>
            
            {/* Escola com botão + */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola(s)</label>
              <div className="flex gap-2">
                <select
                  value={selectedLotacaoSchool}
                  onChange={(e) => setSelectedLotacaoSchool(e.target.value)}
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">Selecione a escola</option>
                  {schools
                    .filter(s => {
                      // Verificar se já está na lista de escolas a serem adicionadas com a mesma função
                      const jaAdicionadaMesmaFuncao = lotacaoEscolas.find(
                        e => e.id === s.id && e.funcao === lotacaoForm.funcao
                      );
                      // Verificar se já existe lotação ativa com a mesma função nessa escola
                      const jaLotadoMesmaFuncao = existingLotacoes.find(
                        l => l.school_id === s.id && l.funcao === lotacaoForm.funcao && l.status === 'ativo'
                      );
                      return !jaAdicionadaMesmaFuncao && !jaLotadoMesmaFuncao;
                    })
                    .map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))
                  }
                </select>
                <Button type="button" onClick={onAddEscola} disabled={!selectedLotacaoSchool}>
                  <Plus size={16} />
                </Button>
              </div>
              
              {/* Lista de escolas a serem adicionadas */}
              {lotacaoEscolas.length > 0 && (
                <div className="mt-2 space-y-1">
                  {lotacaoEscolas.map((escola, index) => (
                    <div key={`${escola.id}-${index}`} className="flex items-center gap-2 bg-green-50 px-3 py-2 rounded border border-green-200">
                      <Building2 size={16} className="text-green-600" />
                      <span className="flex-1 text-sm font-medium">
                        {escola.name}
                        {escola.funcao && <span className="text-xs text-gray-500 ml-2">({FUNCOES[escola.funcao]})</span>}
                      </span>
                      <button 
                        type="button"
                        onClick={() => onRemoveEscola(escola.id, escola.funcao)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Minus size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Função</label>
                <select
                  value={lotacaoForm.funcao}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, funcao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {Object.entries(FUNCOES).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turno</label>
                <select
                  value={lotacaoForm.turno}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, turno: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">Selecione</option>
                  {Object.entries(TURNOS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo *</label>
                <select
                  value={lotacaoForm.academic_year || new Date().getFullYear()}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, academic_year: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {[2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022].map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data Início</label>
                <input
                  type="date"
                  value={lotacaoForm.data_inicio}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, data_inicio: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                />
              </div>
            </div>
          </div>
        )}
        
        <div className="flex gap-2 pt-4 border-t">
          <Button 
            onClick={onSave} 
            disabled={saving || lotacaoEscolas.length === 0} 
            className="flex-1"
          >
            {saving ? 'Salvando...' : lotacaoEscolas.length > 0 ? `Adicionar ${lotacaoEscolas.length} lotação(ões)` : 'Adicionar Lotação'}
          </Button>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default LotacaoModal;
