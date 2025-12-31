import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Users, School, BookOpen, GraduationCap, Bell, FileText, BarChart3, ClipboardList, Calendar, ClipboardCheck, Briefcase, User } from 'lucide-react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { schoolsAPI, usersAPI, classesAPI, profilesAPI, studentsAPI } from '@/services/api';
import { Card, CardContent } from '@/components/ui/card';

export const Dashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState({
    schools: 0,
    users: 0,
    classes: 0,
    students: 0
  });
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    // Não carrega stats se for professor (será redirecionado)
    if (user?.role === 'professor') return;
    
    const loadData = async () => {
      try {
        setLoading(true);
        const [schoolsData, usersData, classesData, studentsData, profileData] = await Promise.all([
          schoolsAPI.getAll().catch(() => []),
          usersAPI.getAll().catch(() => []),
          classesAPI.getAll().catch(() => []),
          studentsAPI.getAll().catch(() => []),
          profilesAPI.getMyProfile().catch(() => null)
        ]);

        // Conta alunos ativos da coleção students
        const activeStudentsCount = studentsData.filter(s => s.status === 'active').length;

        setStats({
          schools: schoolsData.length,
          users: usersData.length,
          classes: classesData.length,
          students: activeStudentsCount
        });
        
        setProfile(profileData);
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [user?.role]);

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
    aluno: 'Aluno',
    responsavel: 'Responsável',
    semed: 'SEMED'
  };

  const getDashboardCards = () => {
    switch (user?.role) {
      case 'admin':
        return [
          { title: 'Escolas', icon: School, value: loading ? '...' : stats.schools.toString(), color: 'blue' },
          { title: 'Usuários', icon: Users, value: loading ? '...' : stats.users.toString(), color: 'green' },
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'purple' },
          { title: 'Alunos', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'orange' }
        ];
      case 'secretario':
        return [
          { title: 'Alunos', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'blue' },
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'green' },
          { title: 'Professores', icon: Users, value: loading ? '...' : '0', color: 'purple' },
          { title: 'Avisos', icon: Bell, value: '0', color: 'orange' }
        ];
      case 'diretor':
      case 'coordenador':
        return [
          { title: 'Turmas', icon: BookOpen, value: loading ? '...' : stats.classes.toString(), color: 'blue' },
          { title: 'Alunos', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'green' },
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
          { title: 'Total Alunos', icon: GraduationCap, value: loading ? '...' : stats.students.toString(), color: 'green' },
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
    orange: 'bg-orange-100 text-orange-600'
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
                  {roleLabels[user?.role]} • {user?.email}
                </p>
              </div>
            </div>
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

        {/* Cards de Estatísticas */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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
        {['admin', 'secretario', 'semed'].includes(user?.role) && (
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
                className="cursor-pointer hover:bg-green-50 transition-colors"
                onClick={() => navigate('/admin/users')}
              >
                <CardContent className="p-4 text-center">
                  <Users className="mx-auto mb-2 text-green-600" size={32} />
                  <p className="font-medium">Usuários</p>
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
                  <p className="font-medium">Alunos</p>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-indigo-50 transition-colors"
                onClick={() => navigate('/profile')}
              >
                <CardContent className="p-4 text-center">
                  <User className="mx-auto mb-2 text-indigo-600" size={32} />
                  <p className="font-medium">Meu Perfil</p>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Menu de navegação completo - Admin/Secretário/SEMED */}
        {['admin', 'secretario', 'semed'].includes(user?.role) && (
          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {user?.role === 'semed' ? 'Consultar Módulos' : 'Menu de Administração'}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <button
                onClick={() => navigate('/admin/schools')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-all"
                data-testid="nav-schools-button"
              >
                <School className="text-blue-600" size={24} />
                <span className="font-medium text-gray-900">Escolas</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/users')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-green-50 hover:border-green-300 transition-all"
                data-testid="nav-users-button"
              >
                <Users className="text-green-600" size={24} />
                <span className="font-medium text-gray-900">Usuários</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/classes')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-purple-50 hover:border-purple-300 transition-all"
                data-testid="nav-classes-button"
              >
                <BookOpen className="text-purple-600" size={24} />
                <span className="font-medium text-gray-900">Turmas</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/courses')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-orange-50 hover:border-orange-300 transition-all"
                data-testid="nav-courses-button"
              >
                <BookOpen className="text-orange-600" size={24} />
                <span className="font-medium text-gray-900">Componentes Curriculares</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/students')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-red-50 hover:border-red-300 transition-all"
                data-testid="nav-students-button"
              >
                <GraduationCap className="text-red-600" size={24} />
                <span className="font-medium text-gray-900">Alunos</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/grades')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-teal-50 hover:border-teal-300 transition-all"
                data-testid="nav-grades-button"
              >
                <ClipboardList className="text-teal-600" size={24} />
                <span className="font-medium text-gray-900">Notas</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/calendar')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-indigo-50 hover:border-indigo-300 transition-all"
                data-testid="nav-calendar-button"
              >
                <Calendar className="text-indigo-600" size={24} />
                <span className="font-medium text-gray-900">Calendário Letivo</span>
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
                <span className="font-medium text-gray-900">Objetos de Conhecimento</span>
              </button>
              
              <button
                onClick={() => navigate('/admin/staff')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-amber-50 hover:border-amber-300 transition-all"
                data-testid="nav-staff-button"
              >
                <Briefcase className="text-amber-600" size={24} />
                <span className="font-medium text-gray-900">Servidores</span>
              </button>
              
              {/* Mantenedora - apenas para admin */}
              {user?.role === 'admin' && (
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
              
              {/* Log de Conversas - apenas para admin */}
              {user?.role === 'admin' && (
                <button
                  onClick={() => navigate('/admin/logs')}
                  className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-red-50 hover:border-red-300 transition-all"
                  data-testid="nav-logs-button"
                >
                  <FileText className="text-red-600" size={24} />
                  <span className="font-medium text-gray-900">Log de Conversas</span>
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

        {/* Info de desenvolvimento - apenas para admin */}
        {user?.role === 'admin' && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <BarChart3 className="text-blue-600" size={24} />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-blue-900">Sistema em Desenvolvimento - Fase 5.5 Em Andamento</h3>
                <div className="mt-2 text-sm text-blue-700">
                  <p>✅ Autenticação JWT implementada</p>
                  <p>✅ Sistema de papéis (RBAC) funcionando</p>
                  <p>✅ Dashboard por papel configurado</p>
                  <p>✅ CRUD de Escolas, Usuários, Turmas e Disciplinas</p>
                  <p>✅ Gestão completa de Alunos (6 abas)</p>
                  <p>✅ Busca avançada por Nome e CPF</p>
                  <p>✅ Sistema de Notas (lançamento por turma e por aluno)</p>
                  <p>✅ Calendário Letivo (visualização Anual, Mensal, Semanal, Diária)</p>
                  <p>✅ Gestão de Eventos (feriados, sábados letivos, etc.)</p>
                  <p>✅ Controle de Frequência (lançamento e relatórios)</p>
                  <p>✅ Gestão de Servidores (cadastro, lotação, alocação de professores)</p>
                  <p className="mt-2 font-medium">Próxima fase: Portais de Visualização</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};
