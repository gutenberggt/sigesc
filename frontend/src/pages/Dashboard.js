import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Users, School, BookOpen, GraduationCap, Bell, FileText, BarChart3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { schoolsAPI, usersAPI, classesAPI } from '@/services/api';

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

  useEffect(() => {
    const loadStats = async () => {
      try {
        setLoading(true);
        const [schoolsData, usersData, classesData] = await Promise.all([
          schoolsAPI.getAll().catch(() => []),
          usersAPI.getAll().catch(() => []),
          classesAPI.getAll().catch(() => [])
        ]);

        // Conta alunos (usuários com role 'aluno')
        const studentsCount = usersData.filter(u => u.role === 'aluno').length;

        setStats({
          schools: schoolsData.length,
          users: usersData.length,
          classes: classesData.length,
          students: studentsCount
        });
      } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
      } finally {
        setLoading(false);
      }
    };
    loadStats();
  }, []);

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
        {/* Header */}
        <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-900" data-testid="dashboard-title">
            Bem-vindo(a), {user?.full_name}!
          </h1>
          <p className="text-gray-600 mt-2" data-testid="dashboard-subtitle">
            Você está acessando como: <span className="font-semibold">{roleLabels[user?.role]}</span>
          </p>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {cards.map((card, index) => {
            const Icon = card.icon;
            return (
              <div
                key={index}
                className="bg-white rounded-lg shadow-sm p-6 border border-gray-200 hover:shadow-md transition-shadow"
                data-testid={`dashboard-card-${index}`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600 mb-1">{card.title}</p>
                    <p className="text-3xl font-bold text-gray-900">{card.value}</p>
                  </div>
                  <div className={`p-3 rounded-lg ${colorClasses[card.color]}`}>
                    <Icon size={24} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Menu de navegação - Admin/Secretário/SEMED */}
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
            </div>
          </div>
        )}

        {/* Info de desenvolvimento */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <BarChart3 className="text-blue-600" size={24} />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-900">Sistema em Desenvolvimento - Fase 3 Concluída</h3>
              <div className="mt-2 text-sm text-blue-700">
                <p>✅ Autenticação JWT implementada</p>
                <p>✅ Sistema de papéis (RBAC) funcionando</p>
                <p>✅ Dashboard por papel configurado</p>
                <p>✅ CRUD de Escolas, Usuários, Turmas e Disciplinas</p>
                <p>✅ Gestão completa de Alunos (6 abas)</p>
                <p>✅ Gestão de Responsáveis</p>
                <p>✅ Gestão de Matrículas</p>
                <p className="mt-2 font-medium">Próxima fase: Sistema de Notas e Frequência</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};
