import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  Award,
  BarChart3,
  Bell,
  BookMarked,
  BookOpen,
  Briefcase,
  Calendar,
  CheckSquare,
  ChevronRight,
  ClipboardList,
  Download,
  Eye,
  FileText,
  FolderOpen,
  GraduationCap,
  Home,
  Key,
  ListChecks,
  MessageCircle,
  PenLine,
  Printer,
  School,
  Search,
  Settings,
  ShieldCheck,
  Smartphone,
  UserCog,
  UserPlus,
  Users,
} from 'lucide-react';
import TutorialCoordenador from './tutorials/TutorialCoordenador';
import TutorialDiretor from './tutorials/TutorialDiretor';
import TutorialSecretario from './tutorials/TutorialSecretario';
import { coordinatorTutorials } from './tutorials/coordinatorTutorials';
import { directorTutorials } from './tutorials/directorTutorials';
import { secretaryTutorials } from './tutorials/secretaryTutorials';

const coordinatorIcons = {
  'primeiros-passos': Key,
  'turmas-estudantes': School,
  'acompanhamento-diarios': BarChart3,
  frequencia: CheckSquare,
  notas: PenLine,
  'registro-conteudos': BookOpen,
  'adaptacoes-curriculares': BookMarked,
  'cobertura-curricular': ClipboardList,
  'calendario-diario': Calendar,
  'integridade-grade': Settings,
  intervencoes: ListChecks,
  'plano-acao': FileText,
  'atestados-justificativas': FileText,
  boletins: BookOpen,
  'livro-promocao': Award,
  'diario-aee': Award,
  'avisos-calendario': Bell,
  'validar-documentos': CheckSquare,
  'indicadores-ranking': BarChart3,
};

const directorIcons = {
  'primeiros-passos': Key,
  'turmas-estudantes': School,
  'historico-movimentacoes': ListChecks,
  'acompanhamento-diarios': BarChart3,
  frequencia: CheckSquare,
  'atestados-justificativas': FileText,
  'registro-conteudos': BookOpen,
  'cobertura-curricular': ClipboardList,
  'calendario-diario': Calendar,
  'integridade-grade': Settings,
  'diario-aee': Award,
  'pre-matriculas': UserPlus,
  intervencoes: ListChecks,
  'plano-acao': FileText,
  'avisos-calendario': Bell,
  'rh-folha': Briefcase,
  boletins: BookOpen,
  'livro-promocao': Award,
  declaracoes: FileText,
  'validar-documentos': CheckSquare,
  'ranking-gestao': BarChart3,
  'fechamento-gerencial': ShieldCheck,
};

const secretaryIcons = {
  'primeiros-passos': Key,
  'escola-equipe-usuarios': School,
  'cadastro-aluno': UserPlus,
  'busca-edicao-cadastral': Search,
  'documentos-aluno': FileText,
  'matricula-turma': CheckSquare,
  remanejamento: School,
  transferencia: Users,
  'historico-movimentacoes': ListChecks,
  'pre-matriculas': UserPlus,
  frequencia: CheckSquare,
  notas: PenLine,
  'atestados-justificativas': FileText,
  'acompanhamento-diarios': BarChart3,
  'registro-conteudos': BookOpen,
  'calendario-diario': Calendar,
  'integridade-grade': Settings,
  'diario-aee': Award,
  'boletim-online': BookOpen,
  'livro-promocao': Award,
  declaracoes: FileText,
  'validar-documentos': ShieldCheck,
  'avisos-calendario': Bell,
  'bolsa-familia-busca-ativa': Users,
  'rh-folha': Briefcase,
  'painel-rede': BarChart3,
  'cobertura-curricular': ClipboardList,
  'intervencoes-plano-acao': ListChecks,
  'ranking-gestao': BarChart3,
  'fechamento-secretaria': ShieldCheck,
};

const buildTrailCards = (tutorials, queryParam, iconMap) => tutorials.map((tutorial) => ({
  title: tutorial.title,
  icon: iconMap[tutorial.slug] || BookOpen,
  stage: tutorial.category,
  link: `/tutoriais?${queryParam}=${encodeURIComponent(tutorial.slug)}`,
}));

const staticBlocks = [
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
      { title: 'Consulta de estudantes da turma', icon: Users },
      { title: 'Visualização de atestados médicos', icon: FileText },
      { title: 'Geração de boletins da turma', icon: BookOpen },
      { title: 'Consulta de notas lançadas', icon: Eye },
      { title: 'Calendário escolar', icon: Calendar },
      { title: 'Comunicação com coordenação', icon: MessageCircle },
      { title: 'Modo offline - trabalhando sem internet', icon: Smartphone },
    ],
  },
  {
    id: 'professor-aee',
    title: 'Professor(a) AEE',
    icon: Award,
    color: 'teal',
    description: 'Tutoriais para o Atendimento Educacional Especializado',
    tutorials: [
      { title: 'Guia Completo do Diário AEE', icon: BookOpen, link: '/tutoriais/professor-aee/diario-aee' },
      { title: 'Criando um Plano de AEE', icon: FileText },
      { title: 'Registrando Atendimentos', icon: CheckSquare },
      { title: 'Acompanhamento do Diário', icon: ClipboardList },
      { title: 'Gerando PDF do Diário', icon: Printer },
    ],
  },
  {
    id: 'alunos',
    title: 'Estudantes(as)',
    icon: GraduationCap,
    color: 'cyan',
    description: 'Tutoriais para consulta de notas, frequência e documentos',
    tutorials: [
      { title: 'Acesso ao portal do estudante', icon: Key },
      { title: 'Consulta de notas e boletim', icon: BookOpen },
      { title: 'Verificação de frequência', icon: CheckSquare },
      { title: 'Download de documentos', icon: Download },
      { title: 'Calendário de atividades', icon: Calendar },
      { title: 'Avisos e comunicados', icon: Bell },
    ],
  },
  {
    id: 'responsaveis',
    title: 'Responsáveis',
    icon: Users,
    color: 'pink',
    description: 'Tutoriais para acompanhamento escolar do estudante',
    tutorials: [
      { title: 'Realizando a pré-matrícula online', icon: UserPlus },
      { title: 'Acompanhamento do status da pré-matrícula', icon: ListChecks },
      { title: 'Acesso ao portal do responsável', icon: Key },
      { title: 'Consulta de notas do estudante', icon: BookOpen },
      { title: 'Verificação de frequência', icon: CheckSquare },
      { title: 'Download de boletim', icon: Download },
      { title: 'Visualização de avisos da escola', icon: Bell },
      { title: 'Comunicação com a escola', icon: MessageCircle },
      { title: 'Atualização de dados cadastrais', icon: PenLine },
    ],
  },
];

const colorClasses = {
  blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400', icon: 'from-blue-500 to-blue-700', hover: 'hover:bg-blue-500/20' },
  purple: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-400', icon: 'from-purple-500 to-purple-700', hover: 'hover:bg-purple-500/20' },
  green: { bg: 'bg-green-500/10', border: 'border-green-500/30', text: 'text-green-400', icon: 'from-green-500 to-green-700', hover: 'hover:bg-green-500/20' },
  orange: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-400', icon: 'from-orange-500 to-orange-700', hover: 'hover:bg-orange-500/20' },
  teal: { bg: 'bg-teal-500/10', border: 'border-teal-500/30', text: 'text-teal-400', icon: 'from-teal-500 to-teal-700', hover: 'hover:bg-teal-500/20' },
  cyan: { bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-400', icon: 'from-cyan-500 to-cyan-700', hover: 'hover:bg-cyan-500/20' },
  pink: { bg: 'bg-pink-500/10', border: 'border-pink-500/30', text: 'text-pink-400', icon: 'from-pink-500 to-pink-700', hover: 'hover:bg-pink-500/20' },
};

export default function TutorialsPage() {
  const [expandedBlock, setExpandedBlock] = useState(null);
  const [searchParams] = useSearchParams();
  const secretarySlug = searchParams.get('secretario');
  const directorSlug = searchParams.get('diretor');
  const coordinatorSlug = searchParams.get('coordenador');

  if (secretarySlug) return <TutorialSecretario slug={secretarySlug} />;
  if (directorSlug) return <TutorialDiretor slug={directorSlug} />;
  if (coordinatorSlug) return <TutorialCoordenador slug={coordinatorSlug} />;

  const tutorialBlocks = [
    {
      id: 'diretores',
      title: 'Diretores',
      icon: UserCog,
      color: 'blue',
      description: 'Trilha completa para gestão pedagógica, operacional, documental e tomada de decisão',
      tutorials: buildTrailCards(directorTutorials, 'diretor', directorIcons),
    },
    {
      id: 'coordenadores',
      title: 'Coordenadores',
      icon: ClipboardList,
      color: 'purple',
      description: 'Trilha completa para acompanhamento, intervenção e fechamento pedagógico',
      tutorials: buildTrailCards(coordinatorTutorials, 'coordenador', coordinatorIcons),
    },
    {
      id: 'secretarios',
      title: 'Secretários',
      icon: FolderOpen,
      color: 'green',
      description: 'Trilha completa para cadastro, matrícula, escrituração, documentos e fechamento escolar',
      tutorials: buildTrailCards(secretaryTutorials, 'secretario', secretaryIcons),
    },
    ...staticBlocks,
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <header className="fixed top-0 left-0 right-0 z-50 bg-slate-900/80 backdrop-blur-md border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-500 to-blue-700 p-2 rounded-xl">
                <GraduationCap className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">SIGESC</h1>
                <p className="text-xs text-slate-400">Sistema de Gestão Escolar</p>
              </div>
            </Link>
            <div className="flex items-center gap-4">
              <Link to="/" className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors">
                <ArrowLeft size={18} />
                <span className="text-sm">Voltar</span>
              </Link>
              <Link to="/login" className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white px-5 py-2 rounded-lg font-medium transition-all duration-300 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40">
                Acessar Sistema
              </Link>
            </div>
          </div>
        </div>
      </header>

      <section className="pt-28 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-2 mb-6">
            <BookOpen size={16} className="text-blue-400" />
            <span className="text-blue-300 text-sm font-medium">Central de Ajuda</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
            Tutoriais do <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-500 text-transparent bg-clip-text">SIGESC</span>
          </h1>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Aprenda a utilizar as funcionalidades do sistema com trilhas organizadas por perfil e rotina de trabalho.
          </p>
        </div>
      </section>

      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6">
          {tutorialBlocks.map((block) => {
            const Icon = block.icon;
            const colors = colorClasses[block.color];
            const isExpanded = expandedBlock === block.id;

            return (
              <div key={block.id} className={`${colors.bg} ${colors.border} border rounded-2xl overflow-hidden transition-all duration-300`}>
                <button onClick={() => setExpandedBlock(isExpanded ? null : block.id)} className={`w-full p-6 flex items-center justify-between gap-4 ${colors.hover} transition-colors`}>
                  <div className="flex items-center gap-4 min-w-0">
                    <div className={`p-3 rounded-xl bg-gradient-to-br ${colors.icon} shadow-lg flex-shrink-0`}>
                      <Icon className="h-6 w-6 text-white" />
                    </div>
                    <div className="text-left min-w-0">
                      <h2 className="text-xl font-bold text-white">{block.title}</h2>
                      <p className="text-sm text-slate-400 mt-1">{block.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={`text-sm ${colors.text} font-medium`}>{block.tutorials.length} tutoriais</span>
                    <ChevronRight size={20} className={`${colors.text} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                  </div>
                </button>

                <div className={`overflow-hidden transition-all duration-300 ${isExpanded ? 'max-h-[3600px]' : 'max-h-0'}`}>
                  <div className="px-6 pb-6 border-t border-slate-700/50 pt-4">
                    <ul className="space-y-2">
                      {block.tutorials.map((tutorial, index) => {
                        const TutorialIcon = tutorial.icon;
                        const content = (
                          <>
                            <TutorialIcon size={18} className={`${colors.text} flex-shrink-0`} />
                            <div className="flex-1 min-w-0">
                              <span className="text-slate-300 text-sm group-hover:text-white transition-colors block">{tutorial.title}</span>
                              {tutorial.stage && <span className={`text-[10px] uppercase tracking-wide mt-0.5 block ${colors.text} opacity-70`}>{tutorial.stage}</span>}
                            </div>
                            {tutorial.link ? (
                              <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full mr-2">Disponível</span>
                            ) : (
                              <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full mr-2">Em breve</span>
                            )}
                            <ChevronRight size={16} className="text-slate-600 group-hover:text-slate-400 transition-colors" />
                          </>
                        );

                        return tutorial.link ? (
                          <Link key={`${block.id}-${index}`} to={tutorial.link} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors group">
                            {content}
                          </Link>
                        ) : (
                          <li key={`${block.id}-${index}`} className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/50 opacity-60 cursor-not-allowed">
                            {content}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto bg-gradient-to-br from-slate-800 to-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
          <MessageCircle size={48} className="text-blue-400 mx-auto mb-4" />
          <h3 className="text-2xl font-bold text-white mb-2">Precisa de mais ajuda?</h3>
          <p className="text-slate-400 mb-6">Entre em contato com nossa equipe de suporte para tirar suas dúvidas.</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a href="https://wa.me/5594984223453?text=Olá! Preciso de ajuda com o SIGESC." target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-6 py-3 rounded-xl font-medium transition-colors">
              <Smartphone size={20} /> WhatsApp: (94) 98422-3453
            </a>
            <a href="mailto:contato@aprenderdigital.top" className="flex items-center gap-2 text-slate-300 hover:text-white px-6 py-3 transition-colors">
              <MessageCircle size={20} /> contato@aprenderdigital.top
            </a>
          </div>
        </div>
      </section>

      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
          <span className="text-slate-400">© {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar</span>
          <div className="flex items-center gap-2 text-slate-500">
            <span>Desenvolvido por</span>
            <a href="https://www.facebook.com/prof.gutenbergbarroso" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 transition-colors font-medium">Gutenberg Barroso</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
