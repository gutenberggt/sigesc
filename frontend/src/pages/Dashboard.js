import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Users, School, BookOpen, GraduationCap, Bell, FileText, BarChart3, ClipboardList, Calendar, ClipboardCheck, Briefcase, User, Shield, Award, UserPlus, ChevronDown } from 'lucide-react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useState, useEffect, useMemo } from 'react';
import { schoolsAPI, usersAPI, classesAPI, profilesAPI, studentsAPI, staffAPI } from '@/services/api';
import { Card, CardContent } from '@/components/ui/card';

export const Dashboard = () => {
  const { user, switchRole, getAvailableRoles } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    schools: 0,
    users: 0,
    classes: 0,
    students: 0,
    staff: 0
  });
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [showRoleSelector, setShowRoleSelector] = useState(false);
  const [switchingRole, setSwitchingRole] = useState(false);

  // IDs das escolas que o usuário (secretário) tem vínculo
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user?.school_ids, user?.school_links]);
  
  const isSecretario = user?.role === 'secretario';
  const isDiretor = user?.role === 'diretor';
  const isCoordenador = user?.role === 'coordenador';
  const isSchoolStaff = isSecretario || isDiretor || isCoordenador;
  const isAdmin = ['admin', 'admin_teste'].includes(user?.role);

  useEffect(() => {
    // Não carrega stats se for professor (será redirecionado)
    if (user?.role === 'professor') return;
    
    const loadData = async () => {
      try {
        setLoading(true);
        const [schoolsData, usersData, classesData, studentsData, staffData, profileData] = await Promise.all([
          schoolsAPI.getAll().catch(() => []),
          usersAPI.getAll().catch(() => []),
          classesAPI.getAll().catch(() => []),
          studentsAPI.getAll().catch(() => []),
          staffAPI.list().catch(() => []),
          profilesAPI.getMyProfile().catch(() => null)
        ]);

        // Para secretário, diretor e coordenador, filtra apenas dados das escolas vinculadas
        let filteredSchools = schoolsData;
        let filteredClasses = classesData;
        let filteredStudents = studentsData;
        
        if (isSchoolStaff && userSchoolIds.length > 0) {
          filteredSchools = schoolsData.filter(s => userSchoolIds.includes(s.id));
          filteredClasses = classesData.filter(c => userSchoolIds.includes(c.school_id));
          // Filtra alunos apenas das escolas vinculadas
          filteredStudents = studentsData.filter(s => userSchoolIds.includes(s.school_id));
        }

        // Conta apenas escolas ATIVAS
        const activeSchoolsCount = filteredSchools.filter(s => 
          s.status === 'active' || s.status === 'Active' || !s.status
        ).length;

        // Conta apenas alunos ATIVOS
        const activeStudentsCount = filteredStudents.filter(s => 
          s.status === 'active' || s.status === 'Ativo' || s.status === 'ativo'
        ).length;

        // Conta servidores - staffData pode ser array ou objeto com items
        const staffCount = Array.isArray(staffData) ? staffData.length : (staffData?.items?.length || 0);

        setStats({
          schools: activeSchoolsCount,
          users: usersData.length,
          classes: filteredClasses.length,
          students: activeStudentsCount,
          staff: staffCount
        });
        
        setProfile(profileData);
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [user?.role, isSchoolStaff, userSchoolIds]);

  // Redireciona professor para o dashboard específico
  if (user?.role === 'professor') {
    return <Navigate to="/professor" replace />;
  }

  const roleLabels = {
    admin: 'Administrador',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    professor: 'Professor(a)',
    aluno: 'Aluno(a)',
    responsavel: 'Responsável(is)',
    semed: 'SEMED',
    admin_teste: 'Administrador'
  };

  const getDashboardCards = () => {
    switch (user?.role) {
      case 'admin':
      case 'admin_teste':
        return [
          { title: 'Escolas', icon: School, value: loading ? '...' : stats.schools.toString(), color: 'blue' },
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'purple' },
          { title: 'Alunos(as)', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'orange' },
          { title: 'Servidores(as)', icon: Briefcase, value: loading ? '...' : stats.staff.toString(), color: 'amber' },
          { title: 'Usuários', icon: Users, value: loading ? '...' : stats.users.toString(), color: 'green' }
        ];
      case 'secretario':
        return [
          { title: 'Escolas', icon: School, value: loading ? '...' : stats.schools.toString(), color: 'blue' },
          { title: 'Alunos(as)', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'green' },
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'purple' },
          { title: 'Avisos', icon: Bell, value: '0', color: 'orange' }
        ];
      case 'diretor':
      case 'coordenador':
        return [
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'blue' },
          { title: 'Alunos(as)', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'green' },
          { title: 'Relatórios', icon: BarChart3, value: '0', color: 'purple' },
          { title: 'Avisos', icon: Bell, value: '0', color: 'orange' }
        ];
      case 'aluno':
      case 'responsavel':
        return [
          { title: 'Notas', icon: FileText, value: 'Ver', color: 'blue' },
          { title: 'Frequência', icon: BarChart3, value: 'Ver', color: 'green' },
          { title: 'Avisos', icon: Bell, value: '0', color: 'purple' },
          { title: 'Documentos', icon: FileText, value: '0', color: 'orange' }
        ];
      case 'semed':
        return [
          { title: 'Escolas', icon: School, value: loading ? '...' : stats.schools.toString(), color: 'blue' },
          { title: 'Total Alunos(as)', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'green' },
          { title: 'Total Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'purple' },
          { title: 'Relatórios', icon: BarChart3, value: 'Ver', color: 'orange' }
        ];
      default:
        return [];
    }
  };

  const cards = getDashboardCards();

  const colorClasses = {
    blue: 'bg-blue-100 text-blue-600',
    green: 'bg-green-100 text-green-600',
    purple: 'bg-purple-100 text-purple-600',
    orange: 'bg-orange-100 text-orange-600',
    amber: 'bg-amber-100 text-amber-600'
  };

  // Obtém os papéis disponíveis para o usuário
  const availableRoles = getAvailableRoles ? getAvailableRoles() : [user?.role];
  const hasMultipleRoles = availableRoles.length > 1;

  // Handler para trocar de papel
  const handleSwitchRole = async (newRole) => {
    if (newRole === user?.role) {
      setShowRoleSelector(false);
      return;
    }
    
    setSwitchingRole(true);
    try {
      const result = await switchRole(newRole);
      if (result.success) {
        setShowRoleSelector(false);
        // Recarrega a página para aplicar as novas permissões
        window.location.reload();
      } else {
        alert(result.error || 'Erro ao trocar papel');
      }
    } catch (error) {
      console.error('Erro ao trocar papel:', error);
      alert('Erro ao trocar papel');
    } finally {
      setSwitchingRole(false);
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header com identificação do usuário - Barra azul */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-lg p-6 text-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* Foto do usuário */}
              <div 
                className="cursor-pointer"
                onClick={() => navigate('/profile')}
              >
                {profile?.foto_url || user?.avatar_url ? (
                  <img 
                    src={profile?.foto_url || user?.avatar_url} 
                    alt="Avatar"
                    className="w-16 h-16 rounded-full border-4 border-white/30 object-cover hover:border-white/50 transition-colors"
                  />
                ) : (
                  <div className="bg-white/20 rounded-full p-3 hover:bg-white/30 transition-colors">
                    <User size={32} />
                  </div>
                )}
              </div>
              <div>
                <h1 className="text-2xl font-bold" data-testid="dashboard-title">
                  Olá, {user?.full_name?.split(' ')[0]}!
                </h1>
                <p className="text-blue-100" data-testid="dashboard-subtitle">
                  {roleLabels[user?.role]}
                </p>
              </div>
            </div>
            
            {/* Seção direita: Seletor de Papel + Botão Perfil */}
            <div className="flex items-center gap-3">
              {/* Seletor de Papel - só aparece se usuário tem múltiplos papéis */}
              {hasMultipleRoles && (
                <div className="relative">
                  <button
                    onClick={() => setShowRoleSelector(!showRoleSelector)}
                    disabled={switchingRole}
                    className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-lg transition-colors border border-white/20"
                  >
                    <Shield size={18} />
                    <span>Trocar Papel</span>
                    <ChevronDown size={16} className={`transition-transform ${showRoleSelector ? 'rotate-180' : ''}`} />
                  </button>
                  
                  {/* Dropdown de papéis */}
                  {showRoleSelector && (
                    <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50">
                      <div className="px-3 py-2 border-b border-gray-100">
                        <p className="text-xs text-gray-500 font-medium">Selecione o papel:</p>
                      </div>
                      {availableRoles.map((role) => (
                        <button
                          key={role}
                          onClick={() => handleSwitchRole(role)}
                          disabled={switchingRole}
                          className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex items-center justify-between ${
                            role === user?.role ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                          }`}
                        >
                          <span>{roleLabels[role] || role}</span>
                          {role === user?.role && (
                            <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">Atual</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
              {/* Botão de Perfil */}
              <button
                onClick={() => navigate('/profile')}
                className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-lg transition-colors"
              >
                <User size={18} />
                <span>Meu Perfil</span>
              </button>
            </div>
          </div>
        </div>

        {/* Cards de Estatísticas */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
          {cards.map((card, index) => {
            const Icon = card.icon;
            return (
              <Card key={index} data-testid={`dashboard-card-${index}`}>
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-gray-600 mb-1">{card.title}</p>
                      <p className="text-3xl font-bold text-gray-900">{card.value}</p>
                    </div>
                    <div className={`p-3 rounded-lg ${colorClasses[card.color]}`}>
                      <Icon size={24} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Acesso Rápido - Segunda linha de blocos */}
        {['admin', 'admin_teste', 'secretario', 'semed'].includes(user?.role) && (
          <div>
            <h2 className="text-xl font-bold mb-4">Acesso Rápido</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <Card 
                className="cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => navigate('/admin/schools')}
              >
                <CardContent className="p-4 text-center">
                  <School className="mx-auto mb-2 text-blue-600" size={32} />
                  <p className="font-medium">Escolas</p>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-purple-50 transition-colors"
                onClick={() => navigate('/admin/classes')}
              >
                <CardContent className="p-4 text-center">
                  <BookOpen className="mx-auto mb-2 text-purple-600" size={32} />
                  <p className="font-medium">Turmas</p>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-orange-50 transition-colors"
                onClick={() => navigate('/admin/students')}
              >
                <CardContent className="p-4 text-center">
                  <GraduationCap className="mx-auto mb-2 text-orange-600" size={32} />
                  <p className="font-medium">Alunos(as)</p>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-amber-50 transition-colors"
                onClick={() => navigate('/admin/staff')}
              >
                <CardContent className="p-4 text-center">
                  <Briefcase className="mx-auto mb-2 text-amber-600" size={32} />
                  <p className="font-medium">Servidores(as)</p>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-green-50 transition-colors"
                onClick={() => navigate('/admin/users')}
              >
                <CardContent className="p-4 text-center">
                  <Users className="mx-auto mb-2 text-green-600" size={32} />
                  <p className="font-medium">Usuários</p>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Menu de navegação completo - Admin/Secretário/SEMED */}
        {['admin', 'admin_teste', 'secretario', 'semed'].includes(user?.role) && (
          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {user?.role === 'semed' ? 'Consultar Módulos' : 'Menu de Administração'}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Mantenedora - apenas para admin */}
              {['admin', 'admin_teste'].includes(user?.role) && (
                <button
                  onClick={() => navigate('/admin/mantenedora')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-all"
                  data-testid="nav-mantenedora-button"
                >
                  <School className="text-indigo-600" size={24} />
                  <span className="font-medium text-gray-900">Mantenedora</span>
                </button>
              )}
              
              <button
                onClick={() => navigate('/avisos')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-orange-50 hover:border-orange-300 transition-all"
                data-testid="nav-avisos-button"
              >
                <Bell className="text-orange-600" size={24} />
                <span className="font-medium text-gray-900">Avisos</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/calendar')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-all"
                data-testid="nav-calendar-button"
              >
                <Calendar className="text-indigo-600" size={24} />
                <span className="font-medium text-gray-900">Calendário</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/analytics')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-emerald-50 hover:border-emerald-300 transition-all"
                data-testid="nav-analytics-button"
              >
                <BarChart3 className="text-emerald-600" size={24} />
                <span className="font-medium text-gray-900">Dashboard Analítico</span>
              </button>
              
              {isAdmin && (
                <button
                  onClick={() => navigate('/admin/courses')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-orange-50 hover:border-orange-300 transition-all"
                  data-testid="nav-courses-button"
                >
                  <BookOpen className="text-orange-600" size={24} />
                  <span className="font-medium text-gray-900">Componentes Curriculares</span>
                </button>
              )}
              
              <button
                onClick={() => navigate('/admin/grades')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-teal-50 hover:border-teal-300 transition-all"
                data-testid="nav-grades-button"
              >
                <ClipboardList className="text-teal-600" size={24} />
                <span className="font-medium text-gray-900">Notas</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/attendance')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-cyan-50 hover:border-cyan-300 transition-all"
                data-testid="nav-attendance-button"
              >
                <ClipboardCheck className="text-cyan-600" size={24} />
                <span className="font-medium text-gray-900">Frequência</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/learning-objects')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-purple-50 hover:border-purple-300 transition-all"
                data-testid="nav-learning-objects-button"
              >
                <BookOpen className="text-purple-600" size={24} />
                <span className="font-medium text-gray-900">Registro de Conteúdos</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/pre-matriculas')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-pink-50 hover:border-pink-300 transition-all"
                data-testid="nav-pre-matriculas-button"
              >
                <UserPlus className="text-pink-600" size={24} />
                <span className="font-medium text-gray-900">Pré-Matrículas</span>
              </button>
              
              {/* Livro de Promoção - admin, secretario, diretor, coordenador, semed */}
              {['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador', 'semed'].includes(user?.role) && (
                <button
                  onClick={() => navigate('/admin/promotion')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-emerald-50 hover:border-emerald-300 transition-all"
                  data-testid="nav-promotion-button"
                >
                  <Award className="text-emerald-600" size={24} />
                  <span className="font-medium text-gray-900">Livro de Promoção</span>
                </button>
              )}
              
              {/* Log de Conversas - apenas para admin */}
              {['admin', 'admin_teste'].includes(user?.role) && (
                <button
                  onClick={() => navigate('/admin/logs')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-red-50 hover:border-red-300 transition-all"
                  data-testid="nav-logs-button"
                >
                  <FileText className="text-red-600" size={24} />
                  <span className="font-medium text-gray-900">Log de Conversas</span>
                </button>
              )}
              
              {/* Logs de Auditoria - apenas admin */}
              {['admin', 'admin_teste'].includes(user?.role) && (
                <button
                  onClick={() => navigate('/admin/audit-logs')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-all"
                  data-testid="nav-audit-logs-button"
                >
                  <Shield className="text-blue-600" size={24} />
                  <span className="font-medium text-gray-900">Auditoria</span>
                </button>
              )}
            </div>
          </div>
        )}

        {/* Menu de Acesso Rápido - Coordenador */}
        {user?.role === 'coordenador' && (
          <div>
            <h2 className="text-xl font-bold mb-4">Acesso Rápido</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <Card 
                className="cursor-pointer hover:bg-purple-50 transition-colors"
                onClick={() => navigate('/admin/classes')}
              >
                <CardContent className="p-4 text-center">
                  <BookOpen className="mx-auto mb-2 text-purple-600" size={32} />
                  <p className="font-medium text-sm">Turmas</p>
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-orange-50 transition-colors"
                onClick={() => navigate('/admin/students')}
              >
                <CardContent className="p-4 text-center">
                  <GraduationCap className="mx-auto mb-2 text-orange-600" size={32} />
                  <p className="font-medium text-sm">Alunos</p>
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-teal-50 transition-colors"
                onClick={() => navigate('/admin/grades')}
              >
                <CardContent className="p-4 text-center">
                  <ClipboardList className="mx-auto mb-2 text-teal-600" size={32} />
                  <p className="font-medium text-sm">Notas</p>
                  <span className="text-xs text-green-600 font-medium">Edição</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-indigo-50 transition-colors"
                onClick={() => navigate('/admin/calendar')}
              >
                <CardContent className="p-4 text-center">
                  <Calendar className="mx-auto mb-2 text-indigo-600" size={32} />
                  <p className="font-medium text-sm">Calendário</p>
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-cyan-50 transition-colors"
                onClick={() => navigate('/admin/attendance')}
              >
                <CardContent className="p-4 text-center">
                  <ClipboardCheck className="mx-auto mb-2 text-cyan-600" size={32} />
                  <p className="font-medium text-sm">Frequência</p>
                  <span className="text-xs text-green-600 font-medium">Edição</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => navigate('/admin/learning-objects')}
              >
                <CardContent className="p-4 text-center">
                  <BookOpen className="mx-auto mb-2 text-blue-600" size={32} />
                  <p className="font-medium text-sm">Conteúdos</p>
                  <span className="text-xs text-green-600 font-medium">Edição</span>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Menu de Navegação Completo - Coordenador */}
        {user?.role === 'coordenador' && (
          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Menu de Navegação</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <button
                onClick={() => navigate('/admin/classes')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-purple-50 hover:border-purple-300 transition-all"
              >
                <BookOpen className="text-purple-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Turmas</span>
                  <span className="text-xs text-gray-500">Visualizar turmas da escola</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/students')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-orange-50 hover:border-orange-300 transition-all"
              >
                <GraduationCap className="text-orange-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Alunos</span>
                  <span className="text-xs text-gray-500">Visualizar dados dos alunos</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/grades')}
                className="flex items-center space-x-3 p-4 border border-green-200 rounded-lg hover:bg-teal-50 hover:border-teal-300 transition-all bg-green-50"
              >
                <ClipboardList className="text-teal-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Notas</span>
                  <span className="text-xs text-green-600">✏️ Lançar e editar notas</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/calendar')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-all"
              >
                <Calendar className="text-indigo-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Calendário Letivo</span>
                  <span className="text-xs text-gray-500">Visualizar calendário escolar</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/attendance')}
                className="flex items-center space-x-3 p-4 border border-green-200 rounded-lg hover:bg-cyan-50 hover:border-cyan-300 transition-all bg-green-50"
              >
                <ClipboardCheck className="text-cyan-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Frequência</span>
                  <span className="text-xs text-green-600">✏️ Lançar e editar frequência</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/learning-objects')}
                className="flex items-center space-x-3 p-4 border border-green-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-all bg-green-50"
              >
                <BookOpen className="text-blue-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Objetos de Conhecimento</span>
                  <span className="text-xs text-green-600">✏️ Registrar conteúdos</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/avisos')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-orange-50 hover:border-orange-300 transition-all"
              >
                <Bell className="text-orange-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Avisos</span>
                  <span className="text-xs text-gray-500">Ver avisos e notificações</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/profile')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-all"
              >
                <User className="text-indigo-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Meu Perfil</span>
                  <span className="text-xs text-gray-500">Gerenciar seu perfil</span>
                </div>
              </button>
            </div>
            
            {/* Legenda */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <p className="text-sm text-gray-500 flex items-center gap-4">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded bg-green-100 border border-green-300"></span>
                  Permite edição
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded bg-gray-100 border border-gray-300"></span>
                  Somente visualização
                </span>
              </p>
            </div>
          </div>
        )}

      </div>
    </Layout>
  );
};
