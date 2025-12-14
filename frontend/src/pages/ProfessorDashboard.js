import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Layout } from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { 
  GraduationCap, 
  Users, 
  BookOpen, 
  ClipboardList,
  Calendar,
  CheckSquare,
  User,
  School,
  Clock
} from 'lucide-react';
import { professorAPI } from '../services/api';

export default function ProfessorDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [turmas, setTurmas] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Carregar perfil do professor
      const profileData = await professorAPI.getProfile();
      setProfile(profileData);
      
      // Carregar turmas do professor
      const turmasData = await professorAPI.getTurmas();
      setTurmas(turmasData);
    } catch (err) {
      console.error('Erro ao carregar dados:', err);
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  // Calcular estatísticas
  const totalTurmas = turmas.length;
  const totalComponentes = turmas.reduce((sum, t) => sum + (t.componentes?.length || 0), 0);
  const escolas = [...new Set(turmas.map(t => t.school_name))];

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
          <Button onClick={loadData} className="mt-2">Tentar novamente</Button>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header com boas-vindas */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-lg p-6 text-white">
          <div className="flex items-center gap-4">
            <div className="bg-white/20 rounded-full p-3">
              <User size={32} />
            </div>
            <div>
              <h1 className="text-2xl font-bold">
                Olá, {profile?.nome?.split(' ')[0] || user?.full_name?.split(' ')[0]}!
              </h1>
              <p className="text-blue-100">
                {profile?.cargo_especifico || 'Professor(a)'} • Matrícula: {profile?.matricula || 'N/A'}
              </p>
            </div>
          </div>
        </div>

        {/* Cards de estatísticas */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="bg-blue-100 p-3 rounded-lg">
                  <GraduationCap className="text-blue-600" size={24} />
                </div>
                <div>
                  <p className="text-2xl font-bold">{totalTurmas}</p>
                  <p className="text-sm text-gray-500">Turma(s)</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="bg-purple-100 p-3 rounded-lg">
                  <BookOpen className="text-purple-600" size={24} />
                </div>
                <div>
                  <p className="text-2xl font-bold">{totalComponentes}</p>
                  <p className="text-sm text-gray-500">Componente(s)</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="bg-green-100 p-3 rounded-lg">
                  <School className="text-green-600" size={24} />
                </div>
                <div>
                  <p className="text-2xl font-bold">{escolas.length}</p>
                  <p className="text-sm text-gray-500">Escola(s)</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Carga Horária */}
        {profile?.carga_horaria_semanal && (
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="bg-orange-100 p-3 rounded-lg">
                  <Clock className="text-orange-600" size={24} />
                </div>
                <div>
                  <p className="text-lg font-medium">Carga Horária Semanal</p>
                  <p className="text-2xl font-bold text-orange-600">{profile.carga_horaria_semanal}h</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Lista de Turmas */}
        <div>
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <GraduationCap className="text-blue-600" />
            Minhas Turmas
          </h2>

          {turmas.length === 0 ? (
            <Card>
              <CardContent className="p-6 text-center text-gray-500">
                <GraduationCap size={48} className="mx-auto mb-2 text-gray-300" />
                <p>Você ainda não foi alocado em nenhuma turma.</p>
                <p className="text-sm">Entre em contato com a coordenação.</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {turmas.map((turma) => (
                <Card key={turma.id} className="hover:shadow-lg transition-shadow">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <GraduationCap className="text-blue-600" size={20} />
                      {turma.name}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-1">
                      <School size={14} />
                      {turma.school_name}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {/* Componentes */}
                    <div className="space-y-2 mb-4">
                      <p className="text-sm font-medium text-gray-700">Componentes:</p>
                      <div className="flex flex-wrap gap-1">
                        {turma.componentes?.map((comp) => (
                          <span 
                            key={comp.id}
                            className="bg-purple-100 text-purple-700 text-xs px-2 py-1 rounded-full"
                          >
                            {comp.name}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Ações */}
                    <div className="grid grid-cols-2 gap-2">
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => navigate(`/professor/turma/${turma.id}/diario`)}
                        className="flex items-center gap-1"
                      >
                        <ClipboardList size={14} />
                        Diário
                      </Button>
                      <Button 
                        variant="outline" 
                        size="sm"
                        onClick={() => navigate(`/professor/turma/${turma.id}/alunos`)}
                        className="flex items-center gap-1"
                      >
                        <Users size={14} />
                        Alunos
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Menu de Acesso Rápido */}
        <div>
          <h2 className="text-xl font-bold mb-4">Acesso Rápido</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card 
              className="cursor-pointer hover:bg-blue-50 transition-colors"
              onClick={() => navigate('/professor/notas')}
            >
              <CardContent className="p-4 text-center">
                <ClipboardList className="mx-auto mb-2 text-blue-600" size={32} />
                <p className="font-medium">Lançar Notas</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-green-50 transition-colors"
              onClick={() => navigate('/professor/frequencia')}
            >
              <CardContent className="p-4 text-center">
                <CheckSquare className="mx-auto mb-2 text-green-600" size={32} />
                <p className="font-medium">Frequência</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-purple-50 transition-colors"
              onClick={() => navigate('/professor/objetos-conhecimento')}
            >
              <CardContent className="p-4 text-center">
                <BookOpen className="mx-auto mb-2 text-purple-600" size={32} />
                <p className="font-medium">Objetos de Conhecimento</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-indigo-50 transition-colors"
              onClick={() => navigate('/professor/calendario')}
            >
              <CardContent className="p-4 text-center">
                <Calendar className="mx-auto mb-2 text-indigo-600" size={32} />
                <p className="font-medium">Calendário</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-orange-50 transition-colors"
              onClick={() => navigate('/professor/perfil')}
            >
              <CardContent className="p-4 text-center">
                <User className="mx-auto mb-2 text-orange-600" size={32} />
                <p className="font-medium">Meu Perfil</p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </Layout>
  );
}
