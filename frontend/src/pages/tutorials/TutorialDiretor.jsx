import { ClipboardCheck, Route, ShieldCheck, Target, UserCog } from 'lucide-react';
import TutorialRoleGuide from './TutorialRoleGuide';
import {
  directorTutorialBySlug,
  directorTutorialCategories,
  directorTutorials,
} from './directorTutorials';

const categoryStyles = {
  'Comece aqui': {
    badge: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
    Icon: Route,
  },
  'Acompanhamento pedagógico': {
    badge: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
    Icon: ClipboardCheck,
  },
  'Gestão escolar e intervenção': {
    badge: 'bg-amber-500/10 border-amber-500/20 text-amber-300',
    Icon: Target,
  },
  'Documentos e fechamento': {
    badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
    Icon: ShieldCheck,
  },
  'Monitoramento e decisão': {
    badge: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-300',
    Icon: UserCog,
  },
};

const theme = {
  accentText: 'text-blue-300',
  accentTextStrong: 'text-blue-200',
  activeNav: 'bg-blue-500/15 text-blue-200 border border-blue-500/25',
  progress: 'from-blue-500 to-cyan-400',
  primaryButton: 'bg-blue-600 hover:bg-blue-500',
  objectiveBox: 'border-blue-500/20 bg-blue-500/10',
  resourceHover: 'hover:border-blue-500/40',
  stepCircle: 'bg-blue-500/15 border-blue-500/25 text-blue-200',
  completionBox: 'border-blue-500/25 bg-gradient-to-br from-blue-500/10 to-cyan-500/5',
  checkbox: 'border border-blue-400/50',
  navHover: 'hover:border-blue-500/30',
};

export default function TutorialDiretor({ slug }) {
  return (
    <TutorialRoleGuide
      slug={slug}
      tutorials={directorTutorials}
      tutorialBySlug={directorTutorialBySlug}
      categories={directorTutorialCategories}
      categoryStyles={categoryStyles}
      queryParam="diretor"
      roleBreadcrumb="Diretores"
      trailTitle="Trilha do Diretor"
      trailDescription="Siga a trilha como uma rotina de gestão: primeiro compreenda a escola, depois acompanhe as evidências, organize intervenções e conclua com conferência institucional."
      headerSubtitle="Trilha do Diretor"
      mindsetTitle="Como pensar como diretor no SIGESC"
      mindsetText="Comece pelo panorama da escola, confirme a evidência e o contexto, distribua responsabilidades e acompanhe o retorno. O diretor não precisa executar tudo: sua função é garantir que processos pedagógicos, administrativos e documentais tenham responsáveis, prazos e coerência institucional."
      theme={theme}
    />
  );
}
