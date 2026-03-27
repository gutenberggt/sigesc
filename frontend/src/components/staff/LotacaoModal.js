import { useState } from 'react';
import { Building2, Plus, Minus, Calendar, Pencil, Check, X, Home, Link2 } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { CARGOS, FUNCOES, TURNOS } from './constants';

// Funções que exigem Escola Sede + Escola(s) Anexa(s)
const FUNCOES_COM_SEDE = ['secretario', 'diretor', 'vice_diretor', 'coordenador', 'auxiliar_secretaria'];

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
  saving,
  editingLotacao,
  onEditLotacao,
  onCancelEditLotacao,
  onSaveEditLotacao
}) => {
  const currentYear = new Date().getFullYear();
  const selectedYear = lotacaoForm.academic_year || currentYear;
  
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [selectedAnexaSchool, setSelectedAnexaSchool] = useState('');
  
  const isFuncaoComSede = FUNCOES_COM_SEDE.includes(lotacaoForm.funcao);
  const escolaSede = lotacaoEscolas.find(e => e.tipo_lotacao === 'sede');
  const escolasAnexas = lotacaoEscolas.filter(e => e.tipo_lotacao === 'anexa');
  const escolasRegulares = lotacaoEscolas.filter(e => !e.tipo_lotacao || e.tipo_lotacao === 'regular');
  
  const handleStartEdit = (lotacao) => {
    setEditForm({
      funcao: lotacao.funcao || 'apoio',
      turno: lotacao.turno || '',
      data_inicio: lotacao.data_inicio || ''
    });
    onEditLotacao(lotacao);
  };
  
  const handleSaveEdit = async () => {
    if (!editingLotacao) return;
    setSavingEdit(true);
    try {
      await onSaveEditLotacao(editingLotacao.id, editForm);
    } finally {
      setSavingEdit(false);
    }
  };

  // Handler para selecionar escola sede
  const handleSelectSede = (schoolId) => {
    if (!schoolId) return;
    onAddEscola(schoolId, 'sede');
  };

  // Handler para adicionar escola anexa
  const handleAddAnexa = () => {
    if (!selectedAnexaSchool) return;
    onAddEscola(selectedAnexaSchool, 'anexa');
    setSelectedAnexaSchool('');
  };

  // Handler para adicionar escola regular
  const handleAddRegular = () => {
    if (!selectedLotacaoSchool) return;
    onAddEscola(selectedLotacaoSchool, 'regular');
  };
  
  const lotacoesDoAno = existingLotacoes.filter(
    lot => lot.academic_year === selectedYear || !lot.academic_year
  );

  // Filtrar escolas que já estão na lista
  const usedSchoolIds = lotacaoEscolas.map(e => e.id);
  const availableSchools = schools.filter(s => {
    const jaAdicionada = lotacaoEscolas.find(e => e.id === s.id && e.funcao === lotacaoForm.funcao);
    const jaLotada = existingLotacoes.find(l => l.school_id === s.id && l.funcao === lotacaoForm.funcao && l.status === 'ativo');
    return !jaAdicionada && !jaLotada;
  });

  const TIPO_LABELS = { sede: 'Sede', anexa: 'Anexa', regular: '' };
  
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Gerenciar Lotações">
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Ano Letivo */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <label className="block text-sm font-medium text-blue-800 mb-1 flex items-center gap-2">
            <Calendar size={16} /> Ano Letivo *
          </label>
          <select
            value={selectedYear}
            onChange={(e) => onYearChange(parseInt(e.target.value))}
            className="w-full px-3 py-2 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white font-medium"
            data-testid="lotacao-year-select"
          >
            {[2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022].map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
          <p className="text-xs text-blue-600 mt-1">Selecione o ano para visualizar e adicionar lotações</p>
        </div>
        
        {/* Servidor */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Servidor *</label>
          <select
            value={lotacaoForm.staff_id}
            onChange={(e) => onStaffChange(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            data-testid="lotacao-staff-select"
          >
            <option value="">Selecione o servidor</option>
            {staffList.filter(s => s.status === 'ativo').map(s => (
              <option key={s.id} value={s.id}>{s.nome} - {s.matricula} ({CARGOS[s.cargo]})</option>
            ))}
          </select>
        </div>
        
        {/* Lotações existentes */}
        {lotacaoForm.staff_id && (
          <div className="p-4 bg-gray-50 rounded-lg border">
            <h4 className="font-medium text-gray-800 mb-2 flex items-center gap-2">
              <Building2 size={16} /> Lotações em {selectedYear}
              {loadingExisting && <span className="text-gray-400 text-sm">(carregando...)</span>}
            </h4>
            {!loadingExisting && lotacoesDoAno.length === 0 ? (
              <p className="text-sm text-gray-500 italic">O servidor não possui lotação em {selectedYear}.</p>
            ) : (
              <div className="space-y-2">
                {lotacoesDoAno.map(lot => (
                  <div key={lot.id} className="bg-white px-3 py-2 rounded border">
                    {editingLotacao?.id === lot.id ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-900">{lot.school_name}</p>
                          <div className="flex gap-1">
                            <button type="button" onClick={handleSaveEdit} disabled={savingEdit} className="p-1 text-green-600 hover:text-green-700 hover:bg-green-50 rounded" title="Salvar"><Check size={16} /></button>
                            <button type="button" onClick={onCancelEditLotacao} className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded" title="Cancelar"><X size={16} /></button>
                          </div>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          <div>
                            <label className="block text-xs text-gray-600 mb-1">Função</label>
                            <select value={editForm.funcao} onChange={(e) => setEditForm({ ...editForm, funcao: e.target.value })} className="w-full px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500">
                              {Object.entries(FUNCOES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs text-gray-600 mb-1">Turno</label>
                            <select value={editForm.turno} onChange={(e) => setEditForm({ ...editForm, turno: e.target.value })} className="w-full px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500">
                              <option value="">Sem turno</option>
                              {Object.entries(TURNOS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="block text-xs text-gray-600 mb-1">Data Início</label>
                            <input type="date" value={editForm.data_inicio} onChange={(e) => setEditForm({ ...editForm, data_inicio: e.target.value })} className="w-full px-2 py-1 text-sm border rounded focus:ring-2 focus:ring-blue-500" />
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900">
                            {lot.school_name}
                            {lot.tipo_lotacao === 'sede' && <span className="ml-1.5 text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">Sede</span>}
                            {lot.tipo_lotacao === 'anexa' && <span className="ml-1.5 text-xs px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">Anexa</span>}
                          </p>
                          <p className="text-xs text-gray-500">
                            {FUNCOES[lot.funcao]} {TURNOS[lot.turno] ? `\u2022 ${TURNOS[lot.turno]}` : ''} {lot.data_inicio ? `\u2022 Desde ${lot.data_inicio}` : ''}
                          </p>
                        </div>
                        {canDelete && (
                          <>
                            <button type="button" onClick={() => handleStartEdit(lot)} className="p-1 text-blue-500 hover:text-blue-700 hover:bg-blue-50 rounded" title="Editar"><Pencil size={16} /></button>
                            <button type="button" onClick={() => onDeleteExisting(lot.id)} className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded" title="Excluir"><Minus size={16} /></button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* ===== ADICIONAR NOVA LOTAÇÃO ===== */}
        {lotacaoForm.staff_id && (
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
              <Plus size={16} /> Adicionar Nova Lotação para {selectedYear}
            </h4>
            
            {/* 1) FUNÇÃO — PRIMEIRO */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Função *</label>
              <select
                value={lotacaoForm.funcao}
                onChange={(e) => setLotacaoForm({ ...lotacaoForm, funcao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                data-testid="lotacao-funcao-select"
              >
                {Object.entries(FUNCOES).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {/* 2) ESCOLAS — Condicional */}
            {isFuncaoComSede ? (
              <>
                {/* Escola Sede */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1.5">
                    <Home size={14} className="text-blue-600" /> Escola Sede *
                  </label>
                  <p className="text-xs text-gray-500 mb-1">O servidor será exibido no quadro desta escola</p>
                  <select
                    value={escolaSede?.id || ''}
                    onChange={(e) => handleSelectSede(e.target.value)}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    data-testid="lotacao-escola-sede-select"
                  >
                    <option value="">Selecione a escola sede</option>
                    {schools
                      .filter(s => !escolasAnexas.find(a => a.id === s.id))
                      .map(s => <option key={s.id} value={s.id}>{s.name}</option>)
                    }
                  </select>
                  {escolaSede && (
                    <div className="mt-2 flex items-center gap-2 bg-blue-100 px-3 py-2 rounded border border-blue-300">
                      <Home size={16} className="text-blue-700" />
                      <span className="flex-1 text-sm font-medium text-blue-800">{escolaSede.name}</span>
                      <span className="text-xs px-1.5 py-0.5 bg-blue-200 text-blue-800 rounded font-medium">Sede</span>
                      <button type="button" onClick={() => onRemoveEscola(escolaSede.id, escolaSede.funcao, 'sede')} className="text-red-500 hover:text-red-700"><Minus size={16} /></button>
                    </div>
                  )}
                </div>

                {/* Escola(s) Anexa(s) */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1.5">
                    <Link2 size={14} className="text-amber-600" /> Escola(s) Anexa(s)
                  </label>
                  <p className="text-xs text-gray-500 mb-1">Terá acesso ao papel nessas escolas, mas não aparece no quadro de servidores</p>
                  <div className="flex gap-2">
                    <select
                      value={selectedAnexaSchool}
                      onChange={(e) => setSelectedAnexaSchool(e.target.value)}
                      className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                      data-testid="lotacao-escola-anexa-select"
                    >
                      <option value="">Selecione escola anexa</option>
                      {schools
                        .filter(s => {
                          if (escolaSede && s.id === escolaSede.id) return false;
                          if (escolasAnexas.find(a => a.id === s.id)) return false;
                          return true;
                        })
                        .map(s => <option key={s.id} value={s.id}>{s.name}</option>)
                      }
                    </select>
                    <Button type="button" onClick={handleAddAnexa} disabled={!selectedAnexaSchool}>
                      <Plus size={16} />
                    </Button>
                  </div>
                  {escolasAnexas.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {escolasAnexas.map((escola, index) => (
                        <div key={`${escola.id}-${index}`} className="flex items-center gap-2 bg-amber-50 px-3 py-2 rounded border border-amber-200">
                          <Link2 size={16} className="text-amber-600" />
                          <span className="flex-1 text-sm font-medium">{escola.name}</span>
                          <span className="text-xs px-1.5 py-0.5 bg-amber-200 text-amber-800 rounded font-medium">Anexa</span>
                          <button type="button" onClick={() => onRemoveEscola(escola.id, escola.funcao, 'anexa')} className="text-red-500 hover:text-red-700"><Minus size={16} /></button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              /* Escola(s) — modo regular */
              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola(s) *</label>
                <div className="flex gap-2">
                  <select
                    value={selectedLotacaoSchool}
                    onChange={(e) => setSelectedLotacaoSchool(e.target.value)}
                    className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    data-testid="lotacao-escola-select"
                  >
                    <option value="">Selecione a escola</option>
                    {availableSchools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                  <Button type="button" onClick={handleAddRegular} disabled={!selectedLotacaoSchool}>
                    <Plus size={16} />
                  </Button>
                </div>
                {escolasRegulares.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {escolasRegulares.map((escola, index) => (
                      <div key={`${escola.id}-${index}`} className="flex items-center gap-2 bg-green-50 px-3 py-2 rounded border border-green-200">
                        <Building2 size={16} className="text-green-600" />
                        <span className="flex-1 text-sm font-medium">
                          {escola.name}
                          {escola.funcao && <span className="text-xs text-gray-500 ml-2">({FUNCOES[escola.funcao]})</span>}
                        </span>
                        <button type="button" onClick={() => onRemoveEscola(escola.id, escola.funcao, escola.tipo_lotacao || 'regular')} className="text-red-500 hover:text-red-700"><Minus size={16} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            
            {/* 3) Turno + Data Início */}
            <div className="grid grid-cols-2 gap-4 mb-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turno</label>
                <select
                  value={lotacaoForm.turno}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, turno: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                  data-testid="lotacao-turno-select"
                >
                  <option value="">Selecione</option>
                  {Object.entries(TURNOS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
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
                  data-testid="lotacao-data-inicio"
                />
              </div>
            </div>
            <div className="text-sm text-blue-600 mb-1">Ano Letivo: <strong>{selectedYear}</strong></div>
          </div>
        )}
        
        <div className="flex gap-2 pt-4 border-t">
          <Button 
            onClick={onSave} 
            disabled={saving || lotacaoEscolas.length === 0} 
            className="flex-1"
            data-testid="lotacao-save-btn"
          >
            {saving ? 'Salvando...' : lotacaoEscolas.length > 0 ? `Adicionar ${lotacaoEscolas.length} lotação(ões)` : 'Adicionar Lotação'}
          </Button>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </div>
      </div>
    </Modal>
  );
};

export default LotacaoModal;
