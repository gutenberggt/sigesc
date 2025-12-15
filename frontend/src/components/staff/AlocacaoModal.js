import { GraduationCap, BookOpen, Plus, Minus, Trash2, AlertTriangle } from 'lucide-react';
import { Modal } from '@/components/Modal';
import { Button } from '@/components/ui/button';

export const AlocacaoModal = ({
  isOpen,
  onClose,
  alocacaoForm,
  professors,
  professorSchools,
  loadingProfessorSchools,
  filteredClasses,
  courses,
  alocacaoTurmas,
  alocacaoComponentes,
  selectedAlocacaoClass,
  setSelectedAlocacaoClass,
  selectedAlocacaoComponent,
  setSelectedAlocacaoComponent,
  cargaHorariaTotal,
  professorCargaHoraria,
  cargaHorariaExistente,
  existingAlocacoes,
  groupedAlocacoes,
  loadingExisting,
  canDelete,
  onProfessorChange,
  onSchoolChange,
  onAddTurma,
  onRemoveTurma,
  onAddComponente,
  onRemoveComponente,
  onDeleteExisting,
  onDeleteTurmaAlocacoes,
  onSave,
  saving
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Gerenciar Alocações de Professor"
      size="lg"
    >
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Professor */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Professor *</label>
          <select
            value={alocacaoForm.staff_id}
            onChange={(e) => onProfessorChange(e.target.value)}
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Selecione o professor</option>
            {professors.map(s => (
              <option key={s.id} value={s.id}>
                {s.nome} - {s.matricula}
              </option>
            ))}
          </select>
        </div>
        
        {/* Alocações existentes */}
        {alocacaoForm.staff_id && (
          <div className="p-4 bg-gray-50 rounded-lg border">
            <h4 className="font-medium text-gray-800 mb-2 flex items-center gap-2">
              <GraduationCap size={16} />
              Alocações Atuais
              {loadingExisting && <span className="text-gray-400 text-sm">(carregando...)</span>}
            </h4>
            
            {!loadingExisting && groupedAlocacoes.length === 0 ? (
              <p className="text-sm text-gray-500 italic">
                O professor não está alocado em nenhuma turma.
              </p>
            ) : (
              <div className="space-y-3">
                {groupedAlocacoes.map(turma => {
                  const totalSemanal = turma.componentes.reduce((sum, comp) => {
                    const courseData = courses.find(c => c.id === comp.course_id);
                    const workload = courseData?.workload || 0;
                    return sum + (workload / 40);
                  }, 0);
                  
                  const totalMensal = turma.componentes.reduce((sum, comp) => {
                    const courseData = courses.find(c => c.id === comp.course_id);
                    const workload = courseData?.workload || 0;
                    return sum + (workload / 8);
                  }, 0);
                  
                  return (
                    <div key={turma.class_id} className="bg-white rounded border overflow-hidden">
                      <div className="flex items-center gap-2 bg-blue-50 px-3 py-2 border-b">
                        <GraduationCap size={16} className="text-blue-600" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-blue-900">{turma.class_name}</p>
                          <p className="text-xs text-blue-600">
                            {turma.school_name}
                            {totalSemanal > 0 && (
                              <span className="ml-2 font-medium text-green-700">
                                ({totalSemanal}h/sem • {totalMensal}h/mês)
                              </span>
                            )}
                          </p>
                        </div>
                        {canDelete && (
                          <button 
                            type="button"
                            onClick={() => onDeleteTurmaAlocacoes(turma.class_id)}
                            className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                            title="Excluir todas alocações desta turma"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                      
                      <div className="p-2 space-y-1">
                        {turma.componentes.map(comp => {
                          const courseData = courses.find(c => c.id === comp.course_id);
                          const workloadTotal = courseData?.workload || 0;
                          const cargaSemanalCalculada = workloadTotal > 0 ? workloadTotal / 40 : null;
                          
                          return (
                            <div key={comp.id} className="flex items-center gap-2 bg-purple-50 px-3 py-1.5 rounded">
                              <BookOpen size={14} className="text-purple-600" />
                              <span className="flex-1 text-sm">
                                {comp.course_name}
                                {cargaSemanalCalculada && (
                                  <span className="text-gray-500 ml-1">({cargaSemanalCalculada}h/sem)</span>
                                )}
                              </span>
                              {canDelete && (
                                <button 
                                  type="button"
                                  onClick={() => onDeleteExisting(comp.id)}
                                  className="p-0.5 text-red-500 hover:text-red-700"
                                  title="Excluir alocação"
                                >
                                  <Minus size={14} />
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
        
        {/* Adicionar nova alocação */}
        {alocacaoForm.staff_id && professorSchools.length > 0 && (
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
              <Plus size={16} />
              Adicionar Nova Alocação
            </h4>
            
            {/* Escola */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Escola
                {loadingProfessorSchools && <span className="text-gray-400 ml-2">(carregando...)</span>}
              </label>
              <select
                value={alocacaoForm.school_id}
                onChange={(e) => onSchoolChange(e.target.value)}
                disabled={loadingProfessorSchools}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-gray-100"
              >
                <option value="">Selecione a escola</option>
                {professorSchools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            
            {/* Turmas */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Série/Ano (Turma)</label>
              <div className="flex gap-2">
                <select
                  value={selectedAlocacaoClass}
                  onChange={(e) => setSelectedAlocacaoClass(e.target.value)}
                  disabled={!alocacaoForm.school_id}
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-gray-100"
                >
                  <option value="">Selecione a turma</option>
                  {filteredClasses.filter(c => !alocacaoTurmas.find(t => t.id === c.id)).map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <Button type="button" onClick={onAddTurma} disabled={!selectedAlocacaoClass}>
                  <Plus size={16} />
                </Button>
              </div>
              
              {alocacaoTurmas.length > 0 && (
                <div className="mt-2 space-y-1">
                  {alocacaoTurmas.map(turma => (
                    <div key={turma.id} className="flex items-center gap-2 bg-blue-100 px-3 py-2 rounded border border-blue-300">
                      <GraduationCap size={16} className="text-blue-600" />
                      <span className="flex-1 text-sm font-medium">{turma.name}</span>
                      <button 
                        type="button"
                        onClick={() => onRemoveTurma(turma.id)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Minus size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            {/* Componentes */}
            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">Componentes Curriculares</label>
              <div className="flex gap-2">
                <select
                  value={selectedAlocacaoComponent}
                  onChange={(e) => setSelectedAlocacaoComponent(e.target.value)}
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">Selecione o componente</option>
                  <option value="TODOS" className="font-bold">TODOS</option>
                  {courses.filter(c => !alocacaoComponentes.find(ac => ac.id === c.id)).map(c => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.workload ? `(${c.workload}h)` : ''}
                    </option>
                  ))}
                </select>
                <Button type="button" onClick={onAddComponente} disabled={!selectedAlocacaoComponent}>
                  <Plus size={16} />
                </Button>
              </div>
              
              {alocacaoComponentes.length > 0 && (
                <div className="mt-2 space-y-1">
                  {alocacaoComponentes.map(comp => (
                    <div key={comp.id} className="flex items-center gap-2 bg-purple-100 px-3 py-2 rounded border border-purple-300">
                      <BookOpen size={16} className="text-purple-600" />
                      <span className="flex-1 text-sm font-medium">
                        {comp.name}
                        {comp.workload && (
                          <span className="text-gray-500 ml-1">
                            ({comp.workload}h → {comp.workload / 40}h/sem)
                          </span>
                        )}
                      </span>
                      <button 
                        type="button"
                        onClick={() => onRemoveComponente(comp.id)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Minus size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            {/* Carga Horária Total */}
            {(alocacaoTurmas.length > 0 && alocacaoComponentes.length > 0) && (
              <div className="p-3 bg-green-100 border border-green-300 rounded-lg">
                <div className="flex justify-between items-center">
                  <div>
                    <span className="text-sm font-medium text-green-800">Carga Horária Semanal Total:</span>
                    <p className="text-xs text-green-600 mt-0.5">
                      {alocacaoTurmas.length} turma(s) × {alocacaoComponentes.length} componente(s) = {alocacaoTurmas.length * alocacaoComponentes.length} alocações
                    </p>
                  </div>
                  <span className="text-xl font-bold text-green-700">{cargaHorariaTotal}h</span>
                </div>
              </div>
            )}
            
            {/* Aviso de carga horária excedida */}
            {alocacaoForm.staff_id && professorCargaHoraria > 0 && (
              <div className={`p-3 rounded-lg border mt-3 ${
                (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria 
                  ? 'bg-red-50 border-red-300' 
                  : 'bg-blue-50 border-blue-200'
              }`}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-700">Resumo da Carga Horária do Professor:</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div className="bg-white rounded p-2">
                    <p className="text-gray-500 text-xs">Cadastrada</p>
                    <p className="font-bold text-gray-800">{professorCargaHoraria}h/sem</p>
                  </div>
                  <div className="bg-white rounded p-2">
                    <p className="text-gray-500 text-xs">Já Alocada</p>
                    <p className="font-bold text-blue-600">{cargaHorariaExistente}h/sem</p>
                  </div>
                  <div className="bg-white rounded p-2">
                    <p className="text-gray-500 text-xs">Nova Alocação</p>
                    <p className="font-bold text-green-600">+{cargaHorariaTotal}h/sem</p>
                  </div>
                </div>
                <div className="mt-2 pt-2 border-t border-gray-200 flex justify-between items-center">
                  <span className="text-sm text-gray-600">Total após salvar:</span>
                  <span className={`font-bold ${
                    (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria 
                      ? 'text-red-600' 
                      : 'text-green-600'
                  }`}>
                    {cargaHorariaExistente + cargaHorariaTotal}h / {professorCargaHoraria}h
                  </span>
                </div>
                
                {(cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria && (
                  <div className="mt-2 p-2 bg-red-100 rounded border border-red-200">
                    <p className="text-sm text-red-800 font-bold flex items-center gap-1">
                      <AlertTriangle size={16} />
                      Não é possível salvar:
                    </p>
                    <ul className="text-xs text-red-700 mt-2 ml-4 list-disc">
                      <li>Aumentar a carga horária semanal no cadastro do professor (aba Servidores)</li>
                      <li>Reduzir o número de turmas ou componentes nesta alocação</li>
                      <li>Remover alocações existentes antes de adicionar novas</li>
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Mensagem se professor não tem lotação */}
        {alocacaoForm.staff_id && professorSchools.length === 0 && !loadingProfessorSchools && (
          <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm text-yellow-800">
              <strong>Atenção:</strong> Este professor não possui lotação em nenhuma escola. 
              Vá na aba Lotações para adicionar antes de fazer alocações.
            </p>
          </div>
        )}
        
        <div className="flex gap-2 pt-4 border-t">
          <Button 
            onClick={onSave} 
            disabled={
              saving || 
              alocacaoTurmas.length === 0 || 
              alocacaoComponentes.length === 0 ||
              (professorCargaHoraria > 0 && (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria)
            } 
            className="flex-1"
          >
            {saving ? 'Salvando...' : 
              (alocacaoTurmas.length > 0 && alocacaoComponentes.length > 0) 
                ? `Adicionar ${alocacaoTurmas.length * alocacaoComponentes.length} alocação(ões)` 
                : 'Adicionar Alocação'}
          </Button>
          <Button 
            variant="outline" 
            onClick={onClose}
          >
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default AlocacaoModal;
