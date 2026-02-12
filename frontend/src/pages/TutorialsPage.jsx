import { useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  GraduationCap, 
  Users, 
  BookOpen,
  ArrowLeft,
  ChevronRight,
  UserCog,
  ClipboardList,
  FileText,
  School,
  Calendar,
  Bell,
  BarChart3,
  Upload,
  Download,
  Settings,
  PenLine,
  CheckSquare,
  UserPlus,
  Search,
  Printer,
  Key,
  Eye,
  MessageCircle,
  FolderOpen,
  ListChecks,
  UserCheck,
  Clock,
  Award,
  BookMarked,
  Home,
  Smartphone
} from 'lucide-react';

export default function TutorialsPage() {
  const [expandedBlock, setExpandedBlock] = useState(null);

  const tutorialBlocks = [
    {
      id: 'diretores',
      title: 'Diretores',
      icon: UserCog,
      color: 'blue',
      description: 'Tutoriais para gestão escolar e acompanhamento da unidade',
      tutorials: [
        { title: 'Acesso ao sistema e primeiro login', icon: Key },
        { title: 'Visão geral do Dashboard', icon: BarChart3 },
        { title: 'Acompanhamento de matrículas da escola', icon: Users },
        { title: 'Visualização de relatórios de frequência', icon: ClipboardList },
        { title: 'Consulta de notas e boletins', icon: FileText },
        { title: 'Gerenciamento de turmas da escola', icon: School },
        { title: 'Visualização do calendário escolar', icon: Calendar },
        { title: 'Gestão de avisos e comunicados', icon: Bell },
        { title: 'Acompanhamento de professores', icon: UserCheck },
        { title: 'Relatórios gerenciais da escola', icon: BarChart3 },
        { title: 'Exportação de dados para Excel', icon: Download },
      ]
    },
    {
      id: 'coordenadores',
      title: 'Coordenadores',
      icon: ClipboardList,
      color: 'purple',
      description: 'Tutoriais para coordenação pedagógica e acompanhamento de turmas',
      tutorials: [
        { title: 'Acesso ao sistema e navegação', icon: Key },
        { title: 'Visão geral das turmas', icon: School },
        { title: 'Acompanhamento de lançamento de notas', icon: PenLine },
        { title: 'Verificação de frequência por turma', icon: CheckSquare },
        { title: 'Consulta de alunos por turma', icon: Users },
        { title: 'Geração de relatórios de desempenho', icon: BarChart3 },
        { title: 'Acompanhamento de atestados médicos', icon: FileText },
        { title: 'Visualização de boletins', icon: BookOpen },
        { title: 'Comunicação com professores', icon: MessageCircle },
        { title: 'Calendário de atividades', icon: Calendar },
      ]
    },
    {
      id: 'secretarios',
      title: 'Secretários',
      icon: FolderOpen,
      color: 'green',
      description: 'Tutoriais para gestão de documentos, matrículas e cadastros',
      tutorials: [
        { title: 'Acesso ao sistema e permissões', icon: Key, link: '/tutoriais/secretarios/acesso' },
        { title: 'Cadastro de novos alunos', icon: UserPlus },
        { title: 'Matrícula de alunos em turmas', icon: CheckSquare },
        { title: 'Transferência de alunos entre escolas', icon: Users },
        { title: 'Remanejamento de alunos entre turmas', icon: School },
        { title: 'Edição de dados cadastrais de alunos', icon: PenLine },
        { title: 'Busca e filtros de alunos', icon: Search },
        { title: 'Gestão de pré-matrículas', icon: ListChecks },
        { title: 'Geração de declarações em PDF', icon: FileText },
        { title: 'Impressão de fichas individuais', icon: Printer },
        { title: 'Geração de boletins', icon: BookOpen },
        { title: 'Registro de atestados médicos', icon: FileText },
        { title: 'Upload de documentos do aluno', icon: Upload },
        { title: 'Histórico de movimentações do aluno', icon: Clock },
        { title: 'Ações em lote (status de alunos)', icon: ListChecks },
        { title: 'Cadastro de turmas', icon: School },
        { title: 'Alocação de professores em turmas', icon: UserCheck },
        { title: 'Exportação de relatórios', icon: Download },
      ]
    },
    {
      id: 'professores',
      title: 'Professores(as)',
      icon: BookMarked,
      color: 'orange',
      description: 'Tutoriais para lançamento de notas, frequência e acompanhamento de turmas',
      tutorials: [
        { title: 'Acesso ao sistema do professor', icon: Key },
        { title: 'Visão geral do painel do professor', icon: Home },
        { title: 'Visualização das turmas atribuídas', icon: School },
        { title: 'Lançamento de notas por bimestre', icon: PenLine },
        { title: 'Lançamento de frequência diária', icon: CheckSquare },
        { title: 'Consulta de alunos da turma', icon: Users },
        { title: 'Visualização de atestados médicos', icon: FileText },
        { title: 'Geração de boletins da turma', icon: BookOpen },
        { title: 'Consulta de notas lançadas', icon: Eye },
        { title: 'Calendário escolar', icon: Calendar },
        { title: 'Comunicação com coordenação', icon: MessageCircle },
        { title: 'Modo offline - trabalhando sem internet', icon: Smartphone },
      ]
    },
    {
      id: 'alunos',
      title: 'Alunos(as)',
      icon: GraduationCap,
      color: 'cyan',
      description: 'Tutoriais para consulta de notas, frequência e documentos',
      tutorials: [
        { title: 'Acesso ao portal do aluno', icon: Key },
        { title: 'Consulta de notas e boletim', icon: BookOpen },
        { title: 'Verificação de frequência', icon: CheckSquare },
        { title: 'Download de documentos', icon: Download },
        { title: 'Calendário de atividades', icon: Calendar },
        { title: 'Avisos e comunicados', icon: Bell },
      ]
    },
    {
      id: 'responsaveis',
      title: 'Responsáveis',
      icon: Users,
      color: 'pink',
      description: 'Tutoriais para acompanhamento escolar do aluno',
      tutorials: [
        { title: 'Realizando a pré-matrícula online', icon: UserPlus },
        { title: 'Acompanhamento do status da pré-matrícula', icon: Clock },
        { title: 'Acesso ao portal do responsável', icon: Key },
        { title: 'Consulta de notas do aluno', icon: BookOpen },
        { title: 'Verificação de frequência', icon: CheckSquare },
        { title: 'Download de boletim', icon: Download },
        { title: 'Visualização de avisos da escola', icon: Bell },
        { title: 'Comunicação com a escola', icon: MessageCircle },
        { title: 'Atualização de dados cadastrais', icon: PenLine },
      ]
    }
  ];

  const colorClasses = {
    blue: {
      bg: 'bg-blue-500/10',
      border: 'border-blue-500/30',
      text: 'text-blue-400',
      icon: 'from-blue-500 to-blue-700',
      hover: 'hover:bg-blue-500/20'
    },
    purple: {
      bg: 'bg-purple-500/10',
      border: 'border-purple-500/30',
      text: 'text-purple-400',
      icon: 'from-purple-500 to-purple-700',
      hover: 'hover:bg-purple-500/20'
    },
    green: {
      bg: 'bg-green-500/10',
      border: 'border-green-500/30',
      text: 'text-green-400',
      icon: 'from-green-500 to-green-700',
      hover: 'hover:bg-green-500/20'
    },
    orange: {
      bg: 'bg-orange-500/10',
      border: 'border-orange-500/30',
      text: 'text-orange-400',
      icon: 'from-orange-500 to-orange-700',
      hover: 'hover:bg-orange-500/20'
    },
    cyan: {
      bg: 'bg-cyan-500/10',
      border: 'border-cyan-500/30',
      text: 'text-cyan-400',
      icon: 'from-cyan-500 to-cyan-700',
      hover: 'hover:bg-cyan-500/20'
    },
    pink: {
      bg: 'bg-pink-500/10',
      border: 'border-pink-500/30',
      text: 'text-pink-400',
      icon: 'from-pink-500 to-pink-700',
      hover: 'hover:bg-pink-500/20'
    }
  };

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
                to="/"
                className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
              >
                <ArrowLeft size={18} />
                <span className="text-sm">Voltar</span>
              </Link>
              <Link
                to="/login"
                className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white px-5 py-2 rounded-lg font-medium transition-all duration-300 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40"
              >
                Acessar Sistema
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="pt-28 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-2 mb-6">
            <BookOpen size={16} className="text-blue-400" />
            <span className="text-blue-300 text-sm font-medium">Central de Ajuda</span>
          </div>
          
          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
            Tutoriais do
            <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-500 text-transparent bg-clip-text"> SIGESC</span>
          </h1>
          
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Aprenda a utilizar todas as funcionalidades do sistema com nossos tutoriais organizados por perfil de usuário
          </p>
        </div>
      </section>

      {/* Tutorial Blocks */}
      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {tutorialBlocks.map((block) => {
              const Icon = block.icon;
              const colors = colorClasses[block.color];
              const isExpanded = expandedBlock === block.id;
              
              return (
                <div
                  key={block.id}
                  className={`${colors.bg} ${colors.border} border rounded-2xl overflow-hidden transition-all duration-300`}
                >
                  {/* Block Header */}
                  <button
                    onClick={() => setExpandedBlock(isExpanded ? null : block.id)}
                    className={`w-full p-6 flex items-center justify-between ${colors.hover} transition-colors`}
                  >
                    <div className="flex items-center gap-4">
                      <div className={`p-3 rounded-xl bg-gradient-to-br ${colors.icon} shadow-lg`}>
                        <Icon className="h-6 w-6 text-white" />
                      </div>
                      <div className="text-left">
                        <h2 className="text-xl font-bold text-white">{block.title}</h2>
                        <p className="text-sm text-slate-400 mt-1">{block.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-sm ${colors.text} font-medium`}>
                        {block.tutorials.length} tutoriais
                      </span>
                      <ChevronRight 
                        size={20} 
                        className={`${colors.text} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} 
                      />
                    </div>
                  </button>
                  
                  {/* Tutorial List */}
                  <div className={`overflow-hidden transition-all duration-300 ${isExpanded ? 'max-h-[800px]' : 'max-h-0'}`}>
                    <div className="px-6 pb-6">
                      <div className="border-t border-slate-700/50 pt-4">
                        <ul className="space-y-2">
                          {block.tutorials.map((tutorial, index) => {
                            const TutorialIcon = tutorial.icon;
                            const content = (
                              <>
                                <TutorialIcon size={18} className={`${colors.text} flex-shrink-0`} />
                                <span className="text-slate-300 text-sm group-hover:text-white transition-colors flex-1">
                                  {tutorial.title}
                                </span>
                                {tutorial.link ? (
                                  <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full mr-2">Disponível</span>
                                ) : (
                                  <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full mr-2">Em breve</span>
                                )}
                                <ChevronRight size={16} className="text-slate-600 group-hover:text-slate-400 transition-colors" />
                              </>
                            );
                            
                            return tutorial.link ? (
                              <Link
                                key={index}
                                to={tutorial.link}
                                className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors group"
                              >
                                {content}
                              </Link>
                            ) : (
                              <li 
                                key={index}
                                className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 opacity-60 cursor-not-allowed"
                              >
                                {content}
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Help Section */}
      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-gradient-to-br from-slate-800 to-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
            <MessageCircle size={48} className="text-blue-400 mx-auto mb-4" />
            <h3 className="text-2xl font-bold text-white mb-2">Precisa de mais ajuda?</h3>
            <p className="text-slate-400 mb-6">
              Entre em contato com nossa equipe de suporte para tirar suas dúvidas
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href="https://wa.me/5594984223453?text=Olá! Preciso de ajuda com o SIGESC."
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-6 py-3 rounded-xl font-medium transition-colors"
              >
                <Smartphone size={20} />
                WhatsApp: (94) 98422-3453
              </a>
              <a
                href="mailto:contato@aprenderdigital.top"
                className="flex items-center gap-2 text-slate-300 hover:text-white px-6 py-3 transition-colors"
              >
                <MessageCircle size={20} />
                contato@aprenderdigital.top
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <span>© {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar</span>
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
