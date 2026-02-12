import { Link } from 'react-router-dom';
import { 
  GraduationCap, 
  ArrowLeft,
  CheckCircle,
  AlertCircle,
  Info,
  ChevronRight,
  Key,
  User,
  Shield,
  BookOpen,
  Home
} from 'lucide-react';

export default function TutorialAcesso() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-slate-900/80 backdrop-blur-md border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <Link to="/" className="flex items-center gap-3">
                <div className="bg-gradient-to-br from-blue-500 to-blue-700 p-2 rounded-xl">
                  <GraduationCap className="h-8 w-8 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-white">SIGESC</h1>
                  <p className="text-xs text-slate-400">Sistema de Gestão Escolar</p>
                </div>
              </Link>
            </div>
            <div className="flex items-center gap-4">
              <Link
                to="/tutoriais"
                className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
              >
                <ArrowLeft size={18} />
                <span className="text-sm">Voltar aos Tutoriais</span>
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-slate-400 mb-8">
            <Link to="/" className="hover:text-white transition-colors">Início</Link>
            <ChevronRight size={14} />
            <Link to="/tutoriais" className="hover:text-white transition-colors">Tutoriais</Link>
            <ChevronRight size={14} />
            <span className="text-green-400">Secretários</span>
            <ChevronRight size={14} />
            <span className="text-white">Acesso ao sistema</span>
          </nav>

          {/* Title */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-gradient-to-br from-green-500 to-green-700">
                <Key className="h-6 w-6 text-white" />
              </div>
              <div>
                <span className="text-green-400 text-sm font-medium">Tutorial para Secretários</span>
                <h1 className="text-3xl font-bold text-white">Acesso ao Sistema e Permissões</h1>
              </div>
            </div>
            <p className="text-slate-400 text-lg">
              Aprenda como acessar o SIGESC e conheça as permissões disponíveis para o perfil de Secretário.
            </p>
          </div>

          {/* Tutorial Content */}
          <div className="space-y-12">
            
            {/* Section 1: Acessando o Sistema */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">1</span>
                Acessando o Sistema
              </h2>
              
              <div className="space-y-6">
                <p className="text-slate-300">
                  Para acessar o SIGESC, abra seu navegador e digite o endereço fornecido pela sua secretaria de educação.
                </p>
                
                {/* Step 1.1 */}
                <div className="bg-slate-900/50 rounded-xl p-5 border border-slate-700/50">
                  <h3 className="text-lg font-semibold text-white mb-3">Passo 1: Tela de Login</h3>
                  <p className="text-slate-400 mb-4">
                    Você verá a tela de login do sistema. Digite seu <strong className="text-white">e-mail</strong> e <strong className="text-white">senha</strong> nos campos indicados.
                  </p>
                  <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                    <img 
                      src="/tutorials/tela-login.png" 
                      alt="Tela de Login do SIGESC" 
                      className="w-full"
                    />
                  </div>
                </div>

                {/* Step 1.2 */}
                <div className="bg-slate-900/50 rounded-xl p-5 border border-slate-700/50">
                  <h3 className="text-lg font-semibold text-white mb-3">Passo 2: Preencha suas credenciais</h3>
                  <p className="text-slate-400 mb-4">
                    Digite o e-mail e senha fornecidos pelo administrador do sistema e clique no botão <strong className="text-blue-400">"Entrar"</strong>.
                  </p>
                  <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                    <img 
                      src="/tutorials/tela-login-preenchido.png" 
                      alt="Tela de Login preenchida" 
                      className="w-full"
                    />
                  </div>
                </div>

                {/* Alert */}
                <div className="flex items-start gap-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                  <AlertCircle className="text-yellow-400 flex-shrink-0 mt-0.5" size={20} />
                  <div>
                    <p className="text-yellow-200 font-medium">Esqueceu sua senha?</p>
                    <p className="text-yellow-200/70 text-sm mt-1">
                      Entre em contato com o administrador do sistema para solicitar uma nova senha.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* Section 2: Dashboard */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">2</span>
                Conhecendo o Dashboard
              </h2>
              
              <div className="space-y-6">
                <p className="text-slate-300">
                  Após o login, você será direcionado ao <strong className="text-white">Dashboard</strong> (painel principal), onde terá uma visão geral do sistema.
                </p>
                
                <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                  <img 
                    src="/tutorials/tela-dashboard.png" 
                    alt="Dashboard do SIGESC" 
                    className="w-full"
                  />
                </div>

                {/* Dashboard Elements */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
                  <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                      <h4 className="font-semibold text-white">Cards de Estatísticas</h4>
                    </div>
                    <p className="text-slate-400 text-sm">
                      Exibem números totais de escolas, turmas, alunos, servidores e usuários.
                    </p>
                  </div>
                  
                  <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-3 h-3 rounded-full bg-green-500"></div>
                      <h4 className="font-semibold text-white">Acesso Rápido</h4>
                    </div>
                    <p className="text-slate-400 text-sm">
                      Botões de atalho para as principais funcionalidades do sistema.
                    </p>
                  </div>
                  
                  <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-3 h-3 rounded-full bg-purple-500"></div>
                      <h4 className="font-semibold text-white">Menu de Administração</h4>
                    </div>
                    <p className="text-slate-400 text-sm">
                      Acesso a todas as funcionalidades administrativas do sistema.
                    </p>
                  </div>
                  
                  <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                      <h4 className="font-semibold text-white">Meu Perfil</h4>
                    </div>
                    <p className="text-slate-400 text-sm">
                      Acesse e edite suas informações pessoais e configurações.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* Section 3: Permissões */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">3</span>
                Permissões do Secretário
              </h2>
              
              <div className="space-y-6">
                <p className="text-slate-300">
                  Como Secretário, você tem acesso às seguintes funcionalidades:
                </p>

                {/* Permissions Grid */}
                <div className="grid grid-cols-1 gap-3">
                  {[
                    { title: 'Gestão de Alunos(as)', desc: 'Cadastrar, editar, transferir e gerenciar todos os alunos(as)', allowed: true },
                    { title: 'Matrículas', desc: 'Realizar matrículas, remanejamentos e transferências', allowed: true },
                    { title: 'Pré-Matrículas', desc: 'Visualizar e processar solicitações de pré-matrícula', allowed: true },
                    { title: 'Turmas', desc: 'Visualizar turmas e alunos matriculados', allowed: true },
                    { title: 'Documentos', desc: 'Gerar declarações, boletins e fichas em PDF', allowed: true },
                    { title: 'Frequência', desc: 'Visualizar relatórios de frequência dos alunos', allowed: true },
                    { title: 'Notas', desc: 'Visualizar notas e boletins dos alunos', allowed: true },
                    { title: 'Atestados Médicos', desc: 'Registrar e gerenciar atestados médicos', allowed: true },
                    { title: 'Upload de Documentos', desc: 'Fazer upload de documentos dos alunos', allowed: true },
                    { title: 'Cadastro de Escolas', desc: 'Apenas visualização (sem edição)', allowed: 'partial' },
                    { title: 'Cadastro de Usuários', desc: 'Não permitido para secretários', allowed: false },
                    { title: 'Configurações do Sistema', desc: 'Não permitido para secretários', allowed: false },
                  ].map((permission, index) => (
                    <div 
                      key={index}
                      className={`flex items-center gap-4 p-4 rounded-xl border ${
                        permission.allowed === true 
                          ? 'bg-green-500/5 border-green-500/20' 
                          : permission.allowed === 'partial'
                          ? 'bg-yellow-500/5 border-yellow-500/20'
                          : 'bg-red-500/5 border-red-500/20'
                      }`}
                    >
                      {permission.allowed === true ? (
                        <CheckCircle className="text-green-400 flex-shrink-0" size={20} />
                      ) : permission.allowed === 'partial' ? (
                        <Info className="text-yellow-400 flex-shrink-0" size={20} />
                      ) : (
                        <AlertCircle className="text-red-400 flex-shrink-0" size={20} />
                      )}
                      <div>
                        <p className={`font-medium ${
                          permission.allowed === true 
                            ? 'text-green-200' 
                            : permission.allowed === 'partial'
                            ? 'text-yellow-200'
                            : 'text-red-200'
                        }`}>
                          {permission.title}
                        </p>
                        <p className="text-slate-400 text-sm">{permission.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* Section 4: Perfil */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">4</span>
                Seu Perfil
              </h2>
              
              <div className="space-y-6">
                <p className="text-slate-300">
                  Clique em <strong className="text-white">"Meu Perfil"</strong> no canto superior direito para visualizar e editar suas informações.
                </p>
                
                <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                  <img 
                    src="/tutorials/tela-perfil.png" 
                    alt="Tela Meu Perfil" 
                    className="w-full"
                  />
                </div>

                <div className="flex items-start gap-3 bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                  <Info className="text-blue-400 flex-shrink-0 mt-0.5" size={20} />
                  <div>
                    <p className="text-blue-200 font-medium">Dica</p>
                    <p className="text-blue-200/70 text-sm mt-1">
                      Mantenha seus dados de contato atualizados para receber notificações importantes do sistema.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* Section 5: Tela de Alunos */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">5</span>
                Navegando pelo Sistema
              </h2>
              
              <div className="space-y-6">
                <p className="text-slate-300">
                  Use o menu <strong className="text-white">"Acesso Rápido"</strong> ou o <strong className="text-white">"Menu de Administração"</strong> para navegar entre as funcionalidades.
                </p>
                
                <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                  <img 
                    src="/tutorials/tela-alunos.png" 
                    alt="Tela de Alunos" 
                    className="w-full"
                  />
                </div>

                <p className="text-slate-400">
                  A tela de <strong className="text-white">Alunos</strong> permite buscar, filtrar e gerenciar todos os alunos cadastrados no sistema.
                </p>
              </div>
            </section>

            {/* Summary */}
            <section className="bg-gradient-to-br from-green-500/10 to-blue-500/10 border border-green-500/30 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-3">
                <CheckCircle className="text-green-400" size={28} />
                Resumo
              </h2>
              
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Acesse o sistema pelo endereço fornecido usando seu e-mail e senha</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>O Dashboard oferece uma visão geral e acesso rápido às funcionalidades</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Como Secretário, você tem acesso completo à gestão de alunos e documentos</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Mantenha seu perfil atualizado para receber notificações</span>
                </li>
              </ul>
            </section>

          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between mt-12 pt-8 border-t border-slate-700/50">
            <Link
              to="/tutoriais"
              className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={18} />
              Voltar aos Tutoriais
            </Link>
            <Link
              to="/tutoriais/secretarios/cadastro-alunos"
              className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-5 py-2.5 rounded-xl font-medium transition-colors"
            >
              Próximo: Cadastro de Alunos
              <ChevronRight size={18} />
            </Link>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-slate-400 text-sm">
            © {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar
          </div>
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <span>Desenvolvido por</span>
            <a 
              href="https://aprenderdigital.top" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 transition-colors font-medium"
            >
              Aprender Digital
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
