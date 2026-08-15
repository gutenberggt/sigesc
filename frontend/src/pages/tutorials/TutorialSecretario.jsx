import {
  BookOpen,
  Briefcase,
  ClipboardCheck,
  FileText,
  FolderOpen,
  Route,
} from 'lucide-react';
import TutorialRoleGuide from './TutorialRoleGuide';
import {
  secretaryTutorialBySlug,
  secretaryTutorialCategories,
  secretaryTutorials,
} from './secretaryTutorials';

const categoryStyles = {
  'Comece aqui': {
    badge: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
    Icon: Route,
  },
  'Cadastro e matrícula': {
    badge: 'bg-green-500/10 border-green-500/20 text-green-300',
    Icon: FolderOpen,
  },
  'Vida escolar e acompanhamento': {
    badge: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
    Icon: ClipboardCheck,
  },
  'Documentos e fechamento': {
    badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
    Icon: FileText,
  },
  'Gestão administrativa e social': {
    badge: 'bg-amber-500/10 border-amber-500/20 text-amber-300',
    Icon: Briefcase,
  },
  'Monitoramento e apoio à gestão': {
    badge: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-300',
    Icon: BookOpen,
  },
};

const theme = {
  accentText: 'text-green-300',
  accentTextStrong: 'text-green-200',
  activeNav: 'bg-green-500/15 text-green-200 border border-green-500/25',
  progress: 'from-green-500 to-emerald-400',
  primaryButton: 'bg-green-600 hover:bg-green-500',
  objectiveBox: 'border-green-500/20 bg-green-500/10',
  resourceHover: 'hover:border-green-500/40',
  stepCircle: 'bg-green-500/15 border-green-500/25 text-green-200',
  completionBox: 'border-green-500/25 bg-gradient-to-br from-green-500/10 to-emerald-500/5',
  checkbox: 'border border-green-400/50',
  navHover: 'hover:border-green-500/30',
};

export default function TutorialSecretario({ slug }) {
  return (
    <TutorialRoleGuide
      slug={slug}
      tutorials={secretaryTutorials}
      tutorialBySlug={secretaryTutorialBySlug}
      categories={secretaryTutorialCategories}
      categoryStyles={categoryStyles}
      queryParam="secretario"
      roleBreadcrumb="Secretários"
      trailTitle="Trilha do Secretário"
      trailDescription="Siga a trilha pela ordem do trabalho da secretaria: confira o contexto, mantenha cadastros e vínculos consistentes, acompanhe registros, emita documentos e conclua com revisão do fechamento."
      headerSubtitle="Trilha do Secretário"
      mindsetTitle="Como pensar como secretário no SIGESC"
      mindsetText="Antes de gravar, confirme pessoa, escola, turma, ano e vínculo. Depois da ação, confira o histórico e o documento resultante. A secretaria protege a continuidade da vida escolar: não apaga o passado para corrigir o presente e não inventa dados para preencher lacunas."
      theme={theme}
    />
  );
}
