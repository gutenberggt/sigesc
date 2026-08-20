import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Layout } from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import MyDiariesSection from '../components/professor/MyDiariesSection';
import { 
  GraduationCap, 
  Users, 
  BookOpen, 
  ClipboardList,
  Calendar,
  CheckSquare,
  User,
  School,
  Clock,
  FileText,
  Sparkles,
  Award,
  Shield,
  ChevronDown
} from 'lucide-react';
import { professorAPI } from '../services/api';
import { mantenedoraAPI } from '../services/api';

export default function ProfessorDashboard() {
  const { user, switchRole, getAvailableRoles } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [turmas, setTurmas] = useState([]);
  const [error, setError] = useState(null);
  const [mensagemDestaque, setMensagemDestaque] = useState('');
  const [mensagemDestaqueCor, setMensagemDestaqueCor] = useState('azul_marinho');
  const [showRoleSelector, setShowRoleSelector] = useState(false);
  const [switchingRole, setSwitchingRole] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [profileData, turmasData, mantenedoraData] = await Promise.all([
        professorAPI.getProfile(),
        professorAPI.getTurmas(),
        mantenedoraAPI.get().catch(() => null)
      ]);
      
      setProfile(profileData);
      setTurmas(turmasData);
      
      if (mantenedoraData?.mensagem_destaque) {
        setMensagemDestaque(mantenedoraData.mensagem_destaque);
        setMensagemDestaqueCor(mantenedoraData.mensagem_destaque_cor || 'azul_marinho');
      }
    } catch (err) {
      console.error('Erro ao carregar dados:', err);
      setError(err.response?.data?.detail || 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  // No DVD, ações pedagógicas precisam nascer do card do vínculo para carregar
  // assignment_id. Atalhos genéricos apenas posicionam o professor em Meus Diários.
  const openFromMyDiaries = () => {
    const section = document.querySelector('[data-testid="meus-diarios-section"]');
    if (section) {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    navigate('/professor');
  };

  const roleLabels = {
    super_admin: 'Super Administrador',
    gerente: 'Gerente da Mantenedora',
    admin: 'Administrador',
    admin_teste: 'Administrador',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    apoio_pedagogico: 'Apoio Pedagógico',
    auxiliar_secretaria: 'Auxiliar de Secretaria',
    professor: 'Professor(a)',
    aluno: 'Estudante',
    responsavel: 'Responsável(is)',
    ass_social: 'Ass. Social',
    ass_social_2: 'Ass. Social',
    agente_vacinas: 'Agente de Vacinas',
    semed: 'SEMED',
    semed1: 'Tutor',
    semed2: 'Analista',
    semed3: 'Administração'
  };

  const availableRoles = Array.from(new Set(
    getAvailableRoles ? getAvailableRoles().filter(Boolean) : [user?.role].filter(Boolean)
  ));
  const hasMultipleRoles = availableRoles.length > 1;

  const handleSwitchRole = async (newRole) => {
    if (!newRole || newRole === user?.role) {
      setShowRoleSelector(false);
      return;
    }

    setSwitchingRole(true);
    try {
      const result = await switchRole(newRole);
      if (!result?.success) {
        window.alert(result?.error || 'Erro ao trocar papel');
        return;
      }

      setShowRoleSelector(false);
      // A sessão já foi rotacionada pelo AuthContext. /dashboard resolve a home
      // correta para o novo papel ativo e recria os contexts com o novo JWT.
      window.location.assign('/dashboard');
    } catch (switchError) {
      console.error('Erro ao trocar papel:', switchError);
      window.alert('Erro ao trocar papel');
    } finally {
      setSwitchingRole(false);
    }
  };

  // Separar turmas regulares e AEE
  const turmasAEE = turmas.filter(t => t.atendimento_programa === 'aee');
  const turmasRegulares = turmas.filter(t => !t.atendimento_programa || (t.atendimento_programa !== 'aee' && t.atendimento_programa !== 'reforco' && t.atendimento_programa !== 'recomposicao'));
  const hasRegularTurmas = turmasRegulares.length > 0;
  const hasAeeTurmas = turmasAEE.length > 0;

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
          <div className="flex items-center justify-between gap-4">
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

            {/* Troca de papel existe somente na barra azul do dashboard */}
            {hasMultipleRoles && (
              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={() => setShowRoleSelector((current) => !current)}
                  disabled={switchingRole}
                  className="flex items-center gap-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-lg transition-colors border border-white/20 disabled:opacity-50"
                  data-testid="professor-role-switcher-button"
                >
                  <Shield size={18} />
                  <span>Trocar Papel</span>
                  <ChevronDown size={16} className={`transition-transform ${showRoleSelector ? 'rotate-180' : ''}`} />
                </button>

                {showRoleSelector && (
                  <div
                    className="absolute right-0 top-full mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50"
                    data-testid="professor-role-switcher-menu"
                  >
                    <div className="px-3 py-2 border-b border-gray-100">
                      <p className="text-xs text-gray-500 font-medium">Selecione o papel:</p>
                    </div>
                    {availableRoles.map((role) => (
                      <button
                        type="button"
                        key={role}
                        onClick={() => handleSwitchRole(role)}
                        disabled={switchingRole}
                        className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex items-center justify-between disabled:opacity-50 ${
                          role === user?.role ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                        }`}
                        data-testid={`professor-role-option-${role}`}
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
          </div>
        </div>

        {/* Mensagem de Destaque */}
        {mensagemDestaque && (
          <div
            data-testid="mensagem-destaque-professor-dashboard"
            className="p-4 bg-gray-50 border-l-4 rounded-lg font-semibold text-base"
            style={{ 
              color: { azul_marinho: '#001f5b', verde: '#16a34a', amarelo: '#ca8a04', vermelho: '#dc2626' }[mensagemDestaqueCor] || '#001f5b',
              borderColor: { azul_marinho: '#001f5b', verde: '#16a34a', amarelo: '#ca8a04', vermelho: '#dc2626' }[mensagemDestaqueCor] || '#001f5b'
            }}
          >
            {mensagemDestaque}
          </div>
        )}

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

        {/* Menu de Acesso Rápido */}
        <div>
          <h2 className="text-xl font-bold mb-4">Acesso Rápido</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {hasRegularTurmas && (
              <>
                <Card 
                  className="cursor-pointer hover:bg-blue-50 transition-colors"
                  onClick={openFromMyDiaries}
                  data-testid="menu-lancar-notas"
                >
                  <CardContent className="p-4 text-center">
                    <ClipboardList className="mx-auto mb-2 text-blue-600" size={32} />
                    <p className="font-medium">Lançar Notas</p>
                    <p className="text-[11px] text-slate-500 mt-1">Escolha o diário/vínculo abaixo</p>
                  </CardContent>
                </Card>

                <Card 
                  className="cursor-pointer hover:bg-green-50 transition-colors"
                  onClick={openFromMyDiaries}
                  data-testid="menu-frequencia"
                >
                  <CardContent className="p-4 text-center">
                    <CheckSquare className="mx-auto mb-2 text-green-600" size={32} />
                    <p className="font-medium">Frequência</p>
                    <p className="text-[11px] text-slate-500 mt-1">Escolha o diário/vínculo abaixo</p>
                  </CardContent>
                </Card>

                <Card 
                  className="cursor-pointer hover:bg-purple-50 transition-colors"
                  onClick={openFromMyDiaries}
                  data-testid="menu-objetos-conhecimento"
                >
                  <CardContent className="p-4 text-center">
                    <BookOpen className="mx-auto mb-2 text-purple-600" size={32} />
                    <p className="font-medium">Objetos de Conhecimento</p>
                    <p className="text-[11px] text-slate-500 mt-1">Escolha o diário/vínculo abaixo</p>
                  </CardContent>
                </Card>

                <Card 
                  className="cursor-pointer hover:bg-emerald-50 transition-colors"
                  onClick={() => navigate('/admin/promotion')}
                  data-testid="menu-livro-promocao"
                >
                  <CardContent className="p-4 text-center">
                    <Award className="mx-auto mb-2 text-emerald-600" size={32} />
                    <p className="font-medium">Livro de Promoção</p>
                  </CardContent>
                </Card>
              </>
            )}

            {hasAeeTurmas && (
              <Card 
                className="cursor-pointer hover:bg-teal-50 transition-colors"
                onClick={() => navigate('/admin/diario-aee')}
                data-testid="menu-diario-aee"
              >
                <CardContent className="p-4 text-center">
                  <FileText className="mx-auto mb-2 text-teal-600" size={32} />
                  <p className="font-medium">Diário AEE</p>
                </CardContent>
              </Card>
            )}

            <Card 
              className="cursor-pointer hover:bg-violet-50 transition-colors"
              onClick={() => navigate('/admin/text-improvement')}
              data-testid="menu-apoio-escrita"
            >
              <CardContent className="p-4 text-center">
                <Sparkles className="mx-auto mb-2 text-violet-600" size={32} />
                <p className="font-medium">Apoio à Escrita</p>
                <p className="text-[11px] text-slate-500 mt-1">Sugestões automáticas dos seus registros</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-indigo-50 transition-colors"
              onClick={() => navigate('/professor/calendario')}
              data-testid="menu-calendario"
            >
              <CardContent className="p-4 text-center">
                <Calendar className="mx-auto mb-2 text-indigo-600" size={32} />
                <p className="font-medium">Calendário</p>
              </CardContent>
            </Card>

            <Card 
              className="cursor-pointer hover:bg-orange-50 transition-colors"
              onClick={() => navigate('/professor/perfil')}
              data-testid="menu-perfil"
            >
              <CardContent className="p-4 text-center">
                <User className="mx-auto mb-2 text-orange-600" size={32} />
                <p className="font-medium">Meu Perfil</p>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Turmas regulares e Diário por Vínculo em uma única seção */}
        <MyDiariesSection legacyClasses={turmasRegulares} />

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

        {/* AEE permanece separado e sem alteração funcional */}
        {hasAeeTurmas && (
          <div>
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
              <GraduationCap className="text-blue-600" />
              Minhas Turmas
            </h2>
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold mb-3 flex items-center gap-2 text-teal-700">
                  <FileText size={18} />
                  Turmas AEE
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {turmasAEE.map((turma) => (
                    <Card key={turma.id} className="hover:shadow-lg transition-shadow border-l-4 border-l-teal-500">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-lg flex items-center gap-2">
                          <FileText className="text-teal-600" size={20} />
                          {turma.name}
                        </CardTitle>
                        <CardDescription className="flex items-center gap-1">
                          <School size={14} />
                          {turma.school_name}
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => navigate('/admin/diario-aee')}
                          className="w-full flex items-center gap-1 border-teal-300 text-teal-700 hover:bg-teal-50"
                          data-testid={`diario-aee-${turma.id}`}
                        >
                          <FileText size={14} />
                          Abrir Diário AEE
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
