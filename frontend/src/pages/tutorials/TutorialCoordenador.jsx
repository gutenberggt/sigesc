import { ClipboardCheck, Route, ShieldCheck, Target } from 'lucide-react';
import TutorialRoleGuide from './TutorialRoleGuide';
import {
  coordinatorTutorialBySlug,
  coordinatorTutorialCategories,
  coordinatorTutorials,
} from './coordinatorTutorials';

const categoryStyles = {
  'Comece aqui': {
    badge: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
    Icon: Route,
  },
  'Rotina pedagógica': {
    badge: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
    Icon: ClipboardCheck,
  },
  'Currículo e intervenção': {
    badge: 'bg-purple-500/10 border-purple-500/20 text-purple-300',
    Icon: Target,
  },
  'Fechamento e evidências': {
    badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
    Icon: ShieldCheck,
  },
};

const theme = {
  accentText: 'text-purple-300',
  accentTextStrong: 'text-purple-200',
  activeNav: 'bg-purple-500/15 text-purple-200 border border-purple-500/25',
  progress: 'from-purple-500 to-cyan-400',
  primaryButton: 'bg-purple-600 hover:bg-purple-500',
  objectiveBox: 'border-purple-500/20 bg-purple-500/10',
  resourceHover: 'hover:border-purple-500/40',
  stepCircle: 'bg-purple-500/15 border-purple-500/25 text-purple-200',
  completionBox: 'border-purple-500/25 bg-gradient-to-br from-purple-500/10 to-cyan-500/5',
  checkbox: 'border border-purple-400/50',
  navHover: 'hover:border-purple-500/30',
};

export default function TutorialCoordenador({ slug }) {
  return (
    <TutorialRoleGuide
      slug={slug}
      tutorials={coordinatorTutorials}
      tutorialBySlug={coordinatorTutorialBySlug}
      categories={coordinatorTutorialCategories}
      categoryStyles={categoryStyles}
      queryParam="coordenador"
      roleBreadcrumb="Coordenadores"
      trailTitle="Trilha do Coordenador"
      trailDescription="Você não precisa estudar tudo de uma vez. Siga a ordem sugerida e volte aos guias quando surgir uma situação real."
      headerSubtitle="Trilha do Coordenador"
      mindsetTitle="Como pensar como coordenador no SIGESC"
      mindsetText="Primeiro confirme o contexto, depois leia a evidência, investigue a causa e só então defina a ação. O objetivo não é ‘achar erro’, e sim transformar registros escolares em acompanhamento pedagógico útil."
      theme={theme}
    />
  );
}
