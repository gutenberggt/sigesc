import { useNavigate } from 'react-router-dom';
import { Home, Users, Building2, GraduationCap, UserPlus, Search } from 'lucide-react';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { useStaff } from '@/hooks/useStaff';
import {
  CARGOS,
  STATUS_SERVIDOR,
  StaffTable,
  LotacoesTable,
  AlocacoesTable,
  DeleteConfirmModal,
  StaffModal,
  LotacaoModal,
  AlocacaoModal,
  StaffDetailModal
} from '@/components/staff';

const Staff = () => {
  const navigate = useNavigate();
  const staff = useStaff();

  const TABS = [
    { id: 'servidores', label: 'Servidores', icon: Users },
    { id: 'lotacoes', label: 'Lotações', icon: Building2 },
    { id: 'alocacoes', label: 'Alocações de Professores', icon: GraduationCap }
  ];

  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Alert */}
        {staff.alert.show && (
          <div className={`fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg ${
            staff.alert.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
          }`}>
            {staff.alert.message}
          </div>
        )}
        
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <Users className="text-blue-600" />
                Gestão de Servidores
              </h1>
              <p className="text-sm text-gray-600">Cadastro, Lotação e Alocação de Servidores</p>
            </div>
          </div>
          
          {staff.canEdit && (
            <div className="flex gap-2">
              {staff.activeTab === 'servidores' && (
                <Button onClick={staff.handleNewStaff}>
                  <UserPlus size={16} className="mr-2" />
                  Novo Servidor
                </Button>
              )}
              {staff.activeTab === 'lotacoes' && (
                <Button onClick={() => staff.handleNewLotacao()}>
                  <Building2 size={16} className="mr-2" />
                  Nova Lotação
                </Button>
              )}
              {staff.activeTab === 'alocacoes' && (
                <Button onClick={() => staff.handleNewAlocacao()}>
                  <GraduationCap size={16} className="mr-2" />
                  Nova Alocação
                </Button>
              )}
            </div>
          )}
        </div>
        
        {/* Abas */}
        <div className="bg-white rounded-lg shadow-sm border mb-6">
          <div className="flex border-b items-center justify-between">
            <div className="flex">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => staff.setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-6 py-3 font-medium transition-colors ${
                    staff.activeTab === tab.id
                      ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <tab.icon size={18} />
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="px-6 py-3 text-sm text-gray-600">
              Total: <span className="font-semibold text-gray-900">
                {staff.activeTab === 'servidores' 
                  ? staff.filteredStaff.length 
                  : staff.activeTab === 'lotacoes'
                    ? staff.lotacoes.filter(l => 
                        (!staff.searchTerm || 
                          l.staff_name?.toLowerCase().includes(staff.searchTerm.toLowerCase()) ||
                          l.staff_matricula?.toLowerCase().includes(staff.searchTerm.toLowerCase())
                        ) &&
                        (!staff.filterSchool || l.school_id === staff.filterSchool)
                      ).length
                    : staff.alocacoes.filter(a =>
                        (!staff.searchTerm ||
                          a.staff_name?.toLowerCase().includes(staff.searchTerm.toLowerCase())
                        ) &&
                        (!staff.filterSchool || a.school_id === staff.filterSchool)
                      ).length
                }
              </span> registros
            </div>
          </div>
          
          {/* Filtros */}
          <div className="p-4 border-b bg-gray-50">
            <div className="flex flex-wrap gap-4 items-center">
              <div className="flex-1 min-w-[200px]">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
                  <input
                    type="text"
                    placeholder="Buscar por nome ou matrícula..."
                    value={staff.searchTerm}
                    onChange={(e) => staff.setSearchTerm(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              
              <select
                value={staff.filterSchool}
                onChange={(e) => staff.setFilterSchool(e.target.value)}
                className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Todas as Escolas</option>
                {staff.schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              
              {staff.activeTab === 'servidores' && (
                <>
                  <select
                    value={staff.filterCargo}
                    onChange={(e) => staff.setFilterCargo(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Todos os Cargos</option>
                    {Object.entries(CARGOS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  
                  <select
                    value={staff.filterStatus}
                    onChange={(e) => staff.setFilterStatus(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Todos os Status</option>
                    {Object.entries(STATUS_SERVIDOR).map(([value, { label }]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </>
              )}
            </div>
          </div>
          
          {/* Conteúdo */}
          <div className="p-4">
            {staff.loading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                <p className="mt-2 text-gray-500">Carregando...</p>
              </div>
            ) : staff.activeTab === 'servidores' ? (
              <StaffTable
                filteredStaff={staff.filteredStaff}
                canEdit={staff.canEdit}
                canDelete={staff.canDelete}
                onView={staff.handleViewStaff}
                onEdit={staff.handleEditStaff}
                onNewLotacao={staff.handleNewLotacao}
                onNewAlocacao={staff.handleNewAlocacao}
                onDelete={staff.handleDelete}
              />
            ) : staff.activeTab === 'lotacoes' ? (
              <LotacoesTable
                lotacoes={staff.lotacoes}
                canEdit={staff.canEdit}
                canDelete={staff.canDelete}
                onEncerrar={staff.handleEncerrarLotacao}
                onDelete={staff.handleDelete}
              />
            ) : (
              <AlocacoesTable
                alocacoes={staff.alocacoes}
                canDelete={staff.canDelete}
                onDelete={staff.handleDelete}
              />
            )}
          </div>
        </div>
        
        {/* Modais */}
        <StaffModal
          isOpen={staff.showStaffModal}
          onClose={() => staff.setShowStaffModal(false)}
          editingStaff={staff.editingStaff}
          staffForm={staff.staffForm}
          setStaffForm={staff.setStaffForm}
          fotoPreview={staff.fotoPreview}
          setFotoPreview={staff.setFotoPreview}
          fotoFile={staff.fotoFile}
          setFotoFile={staff.setFotoFile}
          novaFormacao={staff.novaFormacao}
          setNovaFormacao={staff.setNovaFormacao}
          novaEspecializacao={staff.novaEspecializacao}
          setNovaEspecializacao={staff.setNovaEspecializacao}
          addFormacao={staff.addFormacao}
          removeFormacao={staff.removeFormacao}
          addEspecializacao={staff.addEspecializacao}
          removeEspecializacao={staff.removeEspecializacao}
          onSave={staff.handleSaveStaff}
          saving={staff.saving}
        />
        
        <LotacaoModal
          isOpen={staff.showLotacaoModal}
          onClose={() => staff.setShowLotacaoModal(false)}
          lotacaoForm={staff.lotacaoForm}
          setLotacaoForm={staff.setLotacaoForm}
          staffList={staff.staffList}
          schools={staff.schools}
          lotacaoEscolas={staff.lotacaoEscolas}
          selectedLotacaoSchool={staff.selectedLotacaoSchool}
          setSelectedLotacaoSchool={staff.setSelectedLotacaoSchool}
          existingLotacoes={staff.existingLotacoes}
          loadingExisting={staff.loadingExisting}
          canDelete={staff.canDelete}
          onStaffChange={staff.handleLotacaoStaffChange}
          onAddEscola={staff.addEscolaLotacao}
          onRemoveEscola={staff.removeEscolaLotacao}
          onDeleteExisting={staff.handleDeleteExistingLotacao}
          onSave={staff.handleSaveLotacao}
          saving={staff.saving}
        />
        
        <AlocacaoModal
          isOpen={staff.showAlocacaoModal}
          onClose={() => staff.setShowAlocacaoModal(false)}
          alocacaoForm={staff.alocacaoForm}
          professors={staff.professors}
          professorSchools={staff.professorSchools}
          loadingProfessorSchools={staff.loadingProfessorSchools}
          filteredClasses={staff.filteredClasses}
          courses={staff.courses}
          alocacaoTurmas={staff.alocacaoTurmas}
          alocacaoComponentes={staff.alocacaoComponentes}
          selectedAlocacaoClass={staff.selectedAlocacaoClass}
          setSelectedAlocacaoClass={staff.setSelectedAlocacaoClass}
          selectedAlocacaoComponent={staff.selectedAlocacaoComponent}
          setSelectedAlocacaoComponent={staff.setSelectedAlocacaoComponent}
          cargaHorariaTotal={staff.cargaHorariaTotal}
          professorCargaHoraria={staff.professorCargaHoraria}
          cargaHorariaExistente={staff.cargaHorariaExistente}
          existingAlocacoes={staff.existingAlocacoes}
          groupedAlocacoes={staff.groupedAlocacoes}
          loadingExisting={staff.loadingExisting}
          canDelete={staff.canDelete}
          onProfessorChange={staff.handleProfessorChange}
          onSchoolChange={staff.handleAlocacaoSchoolChange}
          onAddTurma={staff.addTurmaAlocacao}
          onRemoveTurma={staff.removeTurmaAlocacao}
          onAddComponente={staff.addComponenteAlocacao}
          onRemoveComponente={staff.removeComponenteAlocacao}
          onDeleteExisting={staff.handleDeleteExistingAlocacao}
          onDeleteTurmaAlocacoes={staff.handleDeleteTurmaAlocacoes}
          onSave={staff.handleSaveAlocacao}
          saving={staff.saving}
        />
        
        <StaffDetailModal
          isOpen={staff.showDetailModal}
          onClose={() => staff.setShowDetailModal(false)}
          selectedStaff={staff.selectedStaff}
        />
        
        <DeleteConfirmModal
          isOpen={staff.showDeleteModal}
          onClose={() => staff.setShowDeleteModal(false)}
          onConfirm={staff.confirmDelete}
          deleting={staff.deleting}
        />
      </div>
    </Layout>
  );
};

export default Staff;
