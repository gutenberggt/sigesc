import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { usePermissions } from '@/hooks/usePermissions';
import { Users, School, BookOpen, GraduationCap, Bell, FileText, BarChart3, ClipboardList, Calendar, ClipboardCheck, Briefcase, User, Shield, Award, UserPlus, ChevronDown, HeartHandshake, Wifi, Syringe, Building2, Activity, Siren, Layers, Wrench, Megaphone, MessageSquare, BookMarked, Search } from 'lucide-react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useState, useEffect, useMemo } from 'react';
import { schoolsAPI, usersAPI, classesAPI, profilesAPI, studentsAPI, staffAPI, mantenedoraAPI, analyticsAPI } from '@/services/api';
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
  const [mensagemDestaque, setMensagemDestaque] = useState('');
  const [mensagemDestaqueCor, setMensagemDestaqueCor] = useState('azul_marinho');

  // IDs das escolas que o usuário (secretário) tem vínculo
  const userSchoolIdsJson = JSON.stringify(user?.school_ids || user?.school_links?.map(link => link.school_id) || []);
  const userSchoolIds = useMemo(() => {
    return JSON.parse(userSchoolIdsJson);
  }, [userSchoolIdsJson]);
  
  const { isAdmin, isSuperAdmin, isSecretario, isDiretor, isCoordenador, isProfessor, isSemed, isSchoolStaff, isAdminOrSecretary, isSemedFull, isAssistenteSocial, hasRole } = usePermissions();

  // Feb 2026: Menu categorizado por área funcional. Cada item tem uma função `visible`
  // que recebe os flags de permissão e retorna boolean. Categorias sem itens visíveis
  // são suprimidas automaticamente.
  const adminMenuCategories = useMemo(() => {
    const ctx = { isAdmin, isSuperAdmin, isSecretario, isDiretor, isCoordenador, isProfessor, isSemed, isSchoolStaff, isSemedFull, isAssistenteSocial, hasRole };
    return [
      {
        title: 'Gestão Institucional',
        icon: Building2,
        items: [
          { label: 'Mantenedora', icon: School, color: 'indigo', route: '/admin/mantenedora', testId: 'nav-mantenedora-button', visible: c => c.isAdmin },
          { label: 'Integração MEC', icon: GraduationCap, color: 'emerald', route: '/admin/mec', testId: 'nav-mec-button', visible: c => c.isAdmin },
          { label: 'Auditoria', icon: Shield, color: 'blue', route: '/admin/audit-logs', testId: 'nav-audit-logs-button', visible: c => c.isAdmin || c.isSemedFull },
          { label: 'Usuários Online', icon: Wifi, color: 'green', route: '/admin/online-users', testId: 'nav-online-users-button', visible: c => c.isAdmin || c.isSemedFull },
          { label: 'Ferramentas', icon: Wrench, color: 'amber', route: '/admin/tools', testId: 'nav-admin-tools-button', visible: c => c.isAdmin },
          { label: 'Log de Conversas', icon: MessageSquare, color: 'red', route: '/admin/logs', testId: 'nav-logs-button', visible: c => c.isAdmin },
        ],
      },
      {
        title: 'Gestão Escolar',
        icon: School,
        items: [
          { label: 'Componentes Curriculares', icon: BookOpen, color: 'orange', route: '/admin/courses', testId: 'nav-courses-button', visible: c => c.isAdmin },
          { label: 'Pré-Matrículas', icon: UserPlus, color: 'pink', route: '/admin/pre-matriculas', testId: 'nav-pre-matriculas-button', visible: c => !c.hasRole('semed', 'semed1', 'semed2') },
          { label: 'Livro de Promoção', icon: Award, color: 'emerald', route: '/admin/promotion', testId: 'nav-promotion-button', visible: c => c.isAdmin || c.isSchoolStaff || c.isSemed },
        ],
      },
      {
        title: 'Gestão Pedagógica',
        icon: BookMarked,
        items: [
          { label: 'Frequência', icon: ClipboardCheck, color: 'cyan', route: '/admin/attendance', testId: 'nav-attendance-button', visible: () => true },
          { label: 'Registro de Conteúdos', icon: BookOpen, color: 'purple', route: '/admin/learning-objects', testId: 'nav-learning-objects-button', visible: () => true },
          { label: 'Notas', icon: ClipboardList, color: 'teal', route: '/admin/grades', testId: 'nav-grades-button', visible: () => true },
          { label: 'Diário AEE', icon: BookOpen, color: 'blue', route: '/admin/diario-aee', testId: 'nav-diario-aee-button', visible: c => c.isAdmin || c.isCoordenador || c.isProfessor || c.isSecretario || c.isDiretor || c.hasRole('semed1', 'semed2', 'semed3') },
        ],
      },
      {
        title: 'Gestão Social e Comunitária',
        icon: HeartHandshake,
        items: [
          { label: 'Avisos', icon: Megaphone, color: 'orange', route: '/avisos', testId: 'nav-avisos-button', visible: () => true },
          { label: 'Calendário', icon: Calendar, color: 'indigo', route: '/admin/calendar', testId: 'nav-calendar-button', visible: () => true },
          { label: 'Assistência Social', icon: HeartHandshake, color: 'pink', route: '/ass-social', testId: 'nav-ass-social-button', visible: c => c.isAdmin },
          { label: 'Controle de Vacinas', icon: Syringe, color: 'teal', route: '/vacinas', testId: 'nav-vacinas-button', visible: c => c.isAdmin },
          { label: 'Bolsa Família', icon: Users, color: 'amber', route: '/admin/bolsa-familia', testId: 'nav-bolsa-familia-button', visible: c => c.isAdmin },
        ],
      },
      {
        title: 'Monitoramento e Análise',
        icon: BarChart3,
        items: [
          { label: 'Acompanhamento de Diários', icon: BarChart3, color: 'violet', route: '/admin/diary-dashboard', testId: 'nav-diary-dashboard-button', visible: c => c.isAdmin || c.isSchoolStaff || c.isSemed },
          { label: 'Dashboard Analítico', icon: BarChart3, color: 'emerald', route: '/admin/analytics', testId: 'nav-analytics-button', visible: c => c.isAdmin || c.isSemedFull },
          { label: 'Painel do Secretário', icon: Activity, color: 'blue', route: '/semed/panel', testId: 'nav-semed-panel-button', visible: c => c.isAdmin || c.isSemedFull || c.isSemed },
          { label: 'Planos de Ação', icon: ClipboardList, color: 'orange', route: '/action-plans', testId: 'nav-action-plans-button', visible: c => c.isAdmin || c.isSemedFull || c.isSemed || c.isSchoolStaff },
          { label: 'Motor PMPI-GE', icon: Siren, color: 'red', route: '/pmpi/engine', testId: 'nav-pmpi-engine-button', visible: c => c.isAdmin || c.isSemedFull },
        ],
      },
      {
        title: 'Recursos Humanos',
        icon: Briefcase,
        items: [
          { label: 'RH / Folha', icon: FileText, color: 'teal', route: '/admin/hr', testId: 'nav-hr-payroll-button', visible: c => c.isAdmin || c.hasRole('semed2', 'semed3', 'diretor', 'secretario') },
        ],
      },
    ].map(cat => ({
      ...cat,
      items: cat.items.filter(i => i.visible(ctx)),
    })).filter(cat => cat.items.length > 0);
  }, [isAdmin, isSuperAdmin, isSecretario, isDiretor, isCoordenador, isProfessor, isSemed, isSchoolStaff, isSemedFull, isAssistenteSocial, hasRole]);

  // Feb 2026: busca rápida — filtra itens por label/categoria
  const [menuSearch, setMenuSearch] = useState('');
  const filteredAdminMenu = useMemo(() => {
    const q = menuSearch.trim().toLowerCase();
    if (!q) return adminMenuCategories;
    const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const nq = norm(q);
    return adminMenuCategories
      .map(cat => ({
        ...cat,
        items: cat.items.filter(i => norm(i.label).includes(nq) || norm(cat.title).includes(nq)),
      }))
      .filter(cat => cat.items.length > 0);
  }, [adminMenuCategories, menuSearch]);

  useEffect(() => {
    // Não carrega stats se for professor (será redirecionado)
    if (isProfessor) return;
    
    const loadData = async () => {
      try {
        setLoading(true);
        const currentYear = new Date().getFullYear();
        const [schoolsData, usersData, usersCount, classesData, studentsData, staffData, profileData, mantenedoraData, analyticsData] = await Promise.all([
          schoolsAPI.getAll().catch(() => []),
          usersAPI.getAll().catch(() => []),
          usersAPI.count().catch(() => null),
          classesAPI.getAll().catch(() => []),
          studentsAPI.getAll().catch(() => []),
          staffAPI.list().catch(() => []),
          profilesAPI.getMyProfile().catch(() => null),
          mantenedoraAPI.get().catch(() => null),
          analyticsAPI.getOverview({ academic_year: currentYear }).catch(() => null)
        ]);

        // Para secretário, diretor e coordenador, filtra apenas dados das escolas vinculadas
        let filteredSchools = schoolsData;
        // Handle paginated response from classesAPI - extract items array if needed
        const classesArray = Array.isArray(classesData) ? classesData : (classesData?.items || []);
        let filteredClasses = classesArray;
        // Handle paginated response from studentsAPI - extract items array
        const studentsArray = Array.isArray(studentsData) ? studentsData : (studentsData?.items || []);
        let filteredStudents = studentsArray;
        
        if (isSchoolStaff && userSchoolIds.length > 0) {
          filteredSchools = schoolsData.filter(s => userSchoolIds.includes(s.id));
          filteredClasses = classesArray.filter(c => userSchoolIds.includes(c.school_id));
          // Filtra alunos apenas das escolas vinculadas
          filteredStudents = studentsArray.filter(s => userSchoolIds.includes(s.school_id));
        }

        // Conta apenas escolas ATIVAS
        const activeSchoolsCount = filteredSchools.filter(s => 
          s.status === 'active' || s.status === 'Active' || !s.status
        ).length;

        // Conta apenas alunos ATIVOS no ano corrente
        // Se analytics retornou dados, usa a contagem filtrada por ano letivo
        // Senão, faz fallback contando alunos ativos na lista
        const activeStudentsCount = analyticsData?.students?.active 
          ?? filteredStudents.filter(s => 
            s.status === 'active' || s.status === 'Ativo' || s.status === 'ativo'
          ).length;

        // Conta servidores - staffData pode ser array ou objeto com items
        const staffCount = Array.isArray(staffData) ? staffData.length : (staffData?.items?.length || 0);

        setStats({
          schools: activeSchoolsCount,
          users: usersCount?.total ?? usersData.length,
          classes: filteredClasses.length,
          students: activeStudentsCount,
          staff: staffCount
        });
        
        setProfile(profileData);
        if (mantenedoraData?.mensagem_destaque) {
          setMensagemDestaque(mantenedoraData.mensagem_destaque);
          setMensagemDestaqueCor(mantenedoraData.mensagem_destaque_cor || 'azul_marinho');
        }
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  // Redireciona professor para o dashboard específico
  if (isProfessor) {
    return <Navigate to="/professor" replace />;
  }

  // Redireciona assistente social para o dashboard específico
  if (isAssistenteSocial) {
    return <Navigate to="/ass-social" replace />;
  }

  // Redireciona assistente social 2 para o dashboard específico
  if (user?.role === 'ass_social_2') {
    return <Navigate to="/ass-social" replace />;
  }

  // Redireciona agente de vacinas para o dashboard específico
  if (user?.role === 'agente_vacinas') {
    return <Navigate to="/vacinas" replace />;
  }

  // Redireciona aluno para o portal do aluno
  if (user?.role === 'aluno' || user?.role === 'student') {
    return <Navigate to="/aluno" replace />;
  }

  const roleLabels = {
    super_admin: 'Super Administrador',
    gerente: 'Gerente da Mantenedora',
    admin: 'Administrador',
    ass_social: 'Ass. Social',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    apoio_pedagogico: 'Apoio Pedagógico',
    auxiliar_secretaria: 'Auxiliar de Secretaria',
    professor: 'Professor(a)',
    aluno: 'Aluno(a)',
    responsavel: 'Responsável(is)',
    semed: 'SEMED',
    semed1: 'Tutor',
    semed2: 'Analista',
    semed3: 'Administração',
    admin_teste: 'Administrador'
  };

  const getDashboardCards = () => {
    switch (user?.role) {
      case 'super_admin':
      case 'gerente':
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
      case 'apoio_pedagogico':
      case 'auxiliar_secretaria':
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
      case 'semed1':
      case 'semed2':
      case 'semed3':
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
        {/* Mensagem de Destaque da Mantenedora */}
        {mensagemDestaque && (
          <p
            data-testid="mensagem-destaque-dashboard"
            className="text-center font-bold -my-5"
            style={{ color: { azul_marinho: '#001f5b', verde: '#16a34a', amarelo: '#ca8a04', vermelho: '#dc2626' }[mensagemDestaqueCor] || '#001f5b' }}
          >
            {mensagemDestaque}
          </p>
        )}

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
        {(isAdmin || isAdminOrSecretary || isSemed) && (
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

        {/* Menu de navegação completo - Admin/Secretário/SEMED (Feb 2026: categorizado) */}
        {(isAdmin || isAdminOrSecretary || isSemed) && adminMenuCategories.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm p-6 border border-gray-200">
            <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-2">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">
                  {isSemed ? 'Consultar Módulos' : 'Menu de Administração'}
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  Funções organizadas por área. Você visualiza apenas os itens compatíveis com seu perfil.
                </p>
              </div>
              <div className="relative w-full md:w-72">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={menuSearch}
                  onChange={(e) => setMenuSearch(e.target.value)}
                  placeholder="Buscar funcionalidade..."
                  data-testid="menu-search-input"
                  className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            </div>
            {filteredAdminMenu.length === 0 ? (
              <div className="text-center py-12 text-gray-500" data-testid="menu-search-empty">
                <Search size={36} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm">Nenhum item encontrado para "<span className="font-medium">{menuSearch}</span>"</p>
              </div>
            ) : (
            <div className="space-y-6 mt-4">
              {filteredAdminMenu.map((cat) => {
                const CatIcon = cat.icon;
                return (
                  <section key={cat.title} data-testid={`menu-cat-${cat.title.toLowerCase().replace(/\s+/g, '-').replace(/[ãáàâéêíóôõúç]/g, '')}`}>
                    <div className="flex items-center gap-2 mb-3 pb-2 border-b border-gray-100">
                      <CatIcon size={18} className="text-gray-500" />
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
                        {cat.title}
                      </h3>
                      <span className="text-xs text-gray-400 ml-auto">{cat.items.length} {cat.items.length === 1 ? 'item' : 'itens'}</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      {cat.items.map((item) => {
                        const ItemIcon = item.icon;
                        const styles = {
                          indigo: { btn: 'hover:bg-indigo-50 hover:border-indigo-300', icon: 'text-indigo-600' },
                          emerald: { btn: 'hover:bg-emerald-50 hover:border-emerald-300', icon: 'text-emerald-600' },
                          blue: { btn: 'hover:bg-blue-50 hover:border-blue-300', icon: 'text-blue-600' },
                          green: { btn: 'hover:bg-green-50 hover:border-green-300', icon: 'text-green-600' },
                          amber: { btn: 'hover:bg-amber-50 hover:border-amber-300', icon: 'text-amber-600' },
                          orange: { btn: 'hover:bg-orange-50 hover:border-orange-300', icon: 'text-orange-600' },
                          red: { btn: 'hover:bg-red-50 hover:border-red-300', icon: 'text-red-600' },
                          pink: { btn: 'hover:bg-pink-50 hover:border-pink-300', icon: 'text-pink-600' },
                          teal: { btn: 'hover:bg-teal-50 hover:border-teal-300', icon: 'text-teal-600' },
                          cyan: { btn: 'hover:bg-cyan-50 hover:border-cyan-300', icon: 'text-cyan-600' },
                          purple: { btn: 'hover:bg-purple-50 hover:border-purple-300', icon: 'text-purple-600' },
                          violet: { btn: 'hover:bg-violet-50 hover:border-violet-300', icon: 'text-violet-600' },
                        };
                        const s = styles[item.color] || styles.indigo;
                        return (
                          <button
                            key={item.testId}
                            onClick={() => navigate(item.route)}
                            className={`flex items-center space-x-3 p-4 border border-gray-200 rounded-lg transition-all ${s.btn}`}
                            data-testid={item.testId}
                          >
                            <ItemIcon className={s.icon} size={24} />
                            <span className="font-medium text-gray-900">{item.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
            )}
          </div>
        )}

        {/* Menu de Acesso Rápido - Coordenador */}
        {isCoordenador && (
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
                  <p className="font-medium text-sm">Alunos(as)</p>
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
                  <span className="text-xs text-gray-500">Visualização</span>
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
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-blue-50 transition-colors"
                onClick={() => navigate('/admin/learning-objects')}
              >
                <CardContent className="p-4 text-center">
                  <BookOpen className="mx-auto mb-2 text-blue-600" size={32} />
                  <p className="font-medium text-sm">Conteúdos</p>
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>

              <Card 
                className="cursor-pointer hover:bg-violet-50 transition-colors"
                onClick={() => navigate('/admin/diary-dashboard')}
                data-testid="nav-diary-dashboard-card"
              >
                <CardContent className="p-4 text-center">
                  <BarChart3 className="mx-auto mb-2 text-violet-600" size={32} />
                  <p className="font-medium text-sm">Acompanhamento de Diários</p>
                  <span className="text-xs text-gray-500">Visualização</span>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* Menu de Navegação Completo - Coordenador */}
        {isCoordenador && (
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
                  <span className="font-medium text-gray-900 block">Alunos(as)</span>
                  <span className="text-xs text-gray-500">Visualizar dados dos alunos(as)</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/grades')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-teal-50 hover:border-teal-300 transition-all"
              >
                <ClipboardList className="text-teal-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Notas</span>
                  <span className="text-xs text-gray-500">Visualizar notas</span>
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
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-cyan-50 hover:border-cyan-300 transition-all"
              >
                <ClipboardCheck className="text-cyan-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Frequência</span>
                  <span className="text-xs text-gray-500">Visualizar frequência</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/learning-objects')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-300 transition-all"
              >
                <BookOpen className="text-blue-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Objetos de Conhecimento</span>
                  <span className="text-xs text-gray-500">Visualizar conteúdos</span>
                </div>
              </button>
              
              <button
                onClick={() => navigate('/admin/diary-dashboard')}
                className="flex items-center space-x-3 p-4 border border-gray-200 rounded-lg hover:bg-violet-50 hover:border-violet-300 transition-all"
                data-testid="nav-diary-dashboard-menu"
              >
                <BarChart3 className="text-violet-600" size={24} />
                <div className="text-left">
                  <span className="font-medium text-gray-900 block">Acompanhamento de Diários</span>
                  <span className="text-xs text-gray-500">Acompanhar diários de classe</span>
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
