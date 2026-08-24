import { ClipboardCheck, Route, ShieldCheck, Target, UserCog } from 'lucide-react';
import TutorialRoleGuide from './TutorialRoleGuide';
import {
  directorTutorialCategories,
  directorTutorials,
} from './directorTutorials';
import { enhanceDirectorTutorials } from './directorTutorialEnhancements';

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

const didacticDirectorTutorials = enhanceDirectorTutorials(directorTutorials);
const didacticDirectorTutorialBySlug = Object.fromEntries(
  didacticDirectorTutorials.map((tutorial) => [tutorial.slug, tutorial])
);

export default function TutorialDiretor({ slug }) {
  return (
    <TutorialRoleGuide
      slug={slug}
      tutorials={didacticDirectorTutorials}
      tutorialBySlug={didacticDirectorTutorialBySlug}
      categories={directorTutorialCategories}
      categoryStyles={categoryStyles}
      queryParam="diretor"
      roleBreadcrumb="Diretores"
      trailTitle="Guia do Diretor"
      trailDescription="Use esta trilha como companhia para a rotina de gestão. Você pode seguir na ordem ou abrir apenas o assunto de que precisa hoje. Cada guia explica o que observar, como agir com segurança e apresenta exemplos próximos da realidade escolar."
      headerSubtitle="Guia do Diretor"
      mindsetTitle="Uma forma tranquila de usar o SIGESC na direção"
      mindsetText="Você não precisa resolver tudo sozinho nem dominar todas as telas. Comece pela pergunta que precisa responder, confirme os dados, converse com a equipe responsável e acompanhe o retorno. O SIGESC organiza evidências; a decisão continua sendo humana, contextualizada e construída com a equipe escolar."
      theme={theme}
    />
  );
}
