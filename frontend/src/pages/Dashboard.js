import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Users, School, BookOpen, GraduationCap, Bell, FileText, BarChart3 } from 'lucide-react';

export const Dashboard = () => {
  const { user } = useAuth();

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
          { title: 'Escolas', icon: School, value: '0', color: 'blue' },
          { title: 'Usuários', icon: Users, value: '1', color: 'green' },
          { title: 'Turmas', icon: BookOpen, value: '0', color: 'purple' },
          { title: 'Alunos', icon: GraduationCap, value: '0', color: 'orange' }
        ];
      case 'secretario':
        return [
          { title: 'Alunos', icon: GraduationCap, value: '0', color: 'blue' },
          { title: 'Turmas', icon: BookOpen, value: '0', color: 'green' },
          { title: 'Professores', icon: Users, value: '0', color: 'purple' },
          { title: 'Avisos', icon: Bell, value: '0', color: 'orange' }
        ];
      case 'diretor':
      case 'coordenador':
        return [
          { title: 'Turmas', icon: BookOpen, value: '0', color: 'blue' },
          { title: 'Alunos', icon: GraduationCap, value: '0', color: 'green' },
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
          { title: 'Escolas', icon: School, value: '0', color: 'blue' },
          { title: 'Total Alunos', icon: GraduationCap, value: '0', color: 'green' },
          { title: 'Total Turmas', icon: BookOpen, value: '0', color: 'purple' },
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

        {/* Info de desenvolvimento */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <BarChart3 className="text-blue-600" size={24} />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-900">Sistema em Desenvolvimento - Fase 1 Concluída</h3>
              <div className="mt-2 text-sm text-blue-700">
                <p>✅ Autenticação JWT implementada</p>
                <p>✅ Sistema de papéis (RBAC) funcionando</p>
                <p>✅ Dashboard por papel configurado</p>
                <p className="mt-2 font-medium">Próxima fase: Cadastros de Escolas, Usuários e Turmas</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
};
