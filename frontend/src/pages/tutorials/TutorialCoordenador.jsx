import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Clock3,
  ExternalLink,
  GraduationCap,
  Lightbulb,
  ListChecks,
  Route,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react';
import {
  coordinatorTutorialBySlug,
  coordinatorTutorialCategories,
  coordinatorTutorials,
} from './coordinatorTutorials';

const categoryStyles = {
  'Comece aqui': {
    badge: 'bg-blue-500/10 border-blue-500/20 text-blue-300',
    icon: 'bg-blue-500/15 text-blue-300',
    Icon: Route,
  },
  'Rotina pedagógica': {
    badge: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300',
    icon: 'bg-cyan-500/15 text-cyan-300',
    Icon: ClipboardCheck,
  },
  'Currículo e intervenção': {
    badge: 'bg-purple-500/10 border-purple-500/20 text-purple-300',
    icon: 'bg-purple-500/15 text-purple-300',
    Icon: Target,
  },
  'Fechamento e evidências': {
    badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300',
    icon: 'bg-emerald-500/15 text-emerald-300',
    Icon: ShieldCheck,
  },
};

function TrailNav({ currentSlug }) {
  return (
    <aside className="lg:sticky lg:top-24 self-start">
      <div className="bg-slate-800/55 border border-slate-700/60 rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <ListChecks size={19} className="text-purple-300" />
          <h2 className="font-semibold text-white">Trilha do Coordenador</h2>
        </div>
        <p className="text-xs leading-5 text-slate-400 mb-5">
          Você não precisa estudar tudo de uma vez. Siga a ordem sugerida e volte aos guias quando surgir uma situação real.
        </p>

        <div className="space-y-5">
          {coordinatorTutorialCategories.map((category) => {
            const items = coordinatorTutorials.filter((item) => item.category === category);
            return (
              <div key={category}>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  {category}
                </p>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = item.slug === currentSlug;
                    return (
                      <Link
                        key={item.slug}
                        to={`/tutoriais/coordenadores/${item.slug}`}
                        className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                          active
                            ? 'bg-purple-500/15 text-purple-200 border border-purple-500/25'
                            : 'text-slate-400 hover:text-white hover:bg-slate-700/50'
                        }`}
                        aria-current={active ? 'page' : undefined}
                      >
                        {item.title}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function NotFoundTutorial() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center px-4">
      <div className="max-w-lg text-center">
        <BookOpen size={52} className="text-purple-300 mx-auto mb-5" />
        <h1 className="text-2xl font-bold text-white mb-3">Tutorial não encontrado</h1>
        <p className="text-slate-400 mb-6">O endereço pode ter mudado ou este guia ainda não está disponível.</p>
        <Link
          to="/tutoriais"
          className="inline-flex items-center gap-2 rounded-xl bg-purple-600 px-5 py-3 font-medium text-white hover:bg-purple-500 transition-colors"
        >
          <ArrowLeft size={18} />
          Voltar aos Tutoriais
        </Link>
      </div>
    </div>
  );
}

export default function TutorialCoordenador() {
  const { slug } = useParams();
  const tutorial = coordinatorTutorialBySlug[slug];

  if (!tutorial) return <NotFoundTutorial />;

  const currentIndex = coordinatorTutorials.findIndex((item) => item.slug === slug);
  const previous = currentIndex > 0 ? coordinatorTutorials[currentIndex - 1] : null;
  const next = currentIndex < coordinatorTutorials.length - 1 ? coordinatorTutorials[currentIndex + 1] : null;
  const progress = Math.round(((currentIndex + 1) / coordinatorTutorials.length) * 100);
  const style = categoryStyles[tutorial.category] || categoryStyles['Comece aqui'];
  const CategoryIcon = style.Icon;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-3 min-w-0">
            <div className="bg-gradient-to-br from-blue-500 to-blue-700 p-2 rounded-xl flex-shrink-0">
              <GraduationCap className="h-7 w-7 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-white font-bold leading-tight">SIGESC</p>
              <p className="text-xs text-slate-500 truncate">Trilha do Coordenador</p>
            </div>
          </Link>
          <Link
            to="/tutoriais"
            className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white transition-colors"
          >
            <ArrowLeft size={17} />
            <span className="hidden sm:inline">Todos os Tutoriais</span>
            <span className="sm:hidden">Voltar</span>
          </Link>
        </div>
      </header>

      <div className="h-1 bg-slate-800">
        <div
          className="h-full bg-gradient-to-r from-purple-500 to-cyan-400 transition-all"
          style={{ width: `${progress}%` }}
          aria-label={`Progresso da trilha: ${progress}%`}
        />
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 lg:py-12">
        <div className="grid lg:grid-cols-[280px_minmax(0,1fr)] gap-8">
          <TrailNav currentSlug={slug} />

          <article className="min-w-0">
            <nav className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mb-5" aria-label="Navegação estrutural">
              <Link to="/tutoriais" className="hover:text-slate-300">Tutoriais</Link>
              <ChevronRight size={14} />
              <span>Coordenadores</span>
              <ChevronRight size={14} />
              <span className="text-slate-300">{tutorial.category}</span>
            </nav>

            <section className="mb-8">
              <div className="flex flex-wrap items-center gap-3 mb-5">
                <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${style.badge}`}>
                  <CategoryIcon size={14} />
                  {tutorial.category}
                </span>
                <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                  <Clock3 size={14} />
                  leitura aproximada: {tutorial.estimatedTime}
                </span>
                <span className="text-xs text-slate-600">
                  Guia {currentIndex + 1} de {coordinatorTutorials.length}
                </span>
              </div>

              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-white mb-5">
                {tutorial.title}
              </h1>
              <p className="text-lg leading-8 text-slate-400 max-w-4xl">
                {tutorial.intro}
              </p>
            </section>

            <section className="grid md:grid-cols-[1fr_auto] gap-4 mb-8">
              <div className="rounded-2xl border border-purple-500/20 bg-purple-500/10 p-5 sm:p-6">
                <div className="flex gap-3 items-start">
                  <Target size={22} className="text-purple-300 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-purple-200 mb-1">Objetivo deste guia</p>
                    <p className="text-sm sm:text-base leading-7 text-slate-300">{tutorial.objective}</p>
                  </div>
                </div>
              </div>
              <Link
                to={tutorial.systemRoute}
                className="rounded-2xl border border-slate-700 bg-slate-800/70 px-5 py-4 flex md:flex-col items-center justify-center gap-2 text-sm font-medium text-slate-200 hover:border-purple-500/40 hover:text-white transition-colors"
              >
                <ExternalLink size={19} className="text-purple-300" />
                Abrir recurso no SIGESC
              </Link>
            </section>

            <section className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-5 sm:p-6 mb-8">
              <div className="flex gap-3 items-start">
                <Sparkles size={21} className="text-blue-300 flex-shrink-0 mt-0.5" />
                <div>
                  <h2 className="font-semibold text-white mb-2">Como pensar como coordenador no SIGESC</h2>
                  <p className="text-sm leading-6 text-slate-400">
                    Primeiro confirme o contexto, depois leia a evidência, investigue a causa e só então defina a ação. O objetivo não é “achar erro”, e sim transformar registros escolares em acompanhamento pedagógico útil.
                  </p>
                </div>
              </div>
            </section>

            <section className="mb-10">
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <ClipboardList size={21} className="text-cyan-300" />
                Antes de começar
              </h2>
              <div className="grid sm:grid-cols-2 gap-3">
                {tutorial.before.map((item) => (
                  <div key={item} className="rounded-xl border border-slate-800 bg-slate-900/55 p-4 flex gap-3">
                    <CheckCircle2 size={18} className="text-cyan-400 flex-shrink-0 mt-0.5" />
                    <p className="text-sm leading-6 text-slate-300">{item}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="mb-10">
              <div className="flex items-center justify-between gap-4 mb-5">
                <h2 className="text-2xl font-bold text-white">Passo a passo</h2>
                <span className="text-xs text-slate-500">Siga na ordem</span>
              </div>
              <div className="space-y-4">
                {tutorial.steps.map((step, index) => (
                  <div key={step.title} className="rounded-2xl border border-slate-800 bg-slate-900/55 p-5 sm:p-6">
                    <div className="flex gap-4 items-start">
                      <div className="w-9 h-9 rounded-full bg-purple-500/15 border border-purple-500/25 text-purple-200 flex items-center justify-center font-bold flex-shrink-0">
                        {index + 1}
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-base sm:text-lg font-semibold text-white mb-2">{step.title}</h3>
                        <p className="text-sm sm:text-base leading-7 text-slate-400">{step.text}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="grid xl:grid-cols-2 gap-5 mb-10">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/55 p-5 sm:p-6">
                <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
                  <BarChart3 size={19} className="text-cyan-300" />
                  O que observar
                </h2>
                <ul className="space-y-3">
                  {tutorial.observe.map((item) => (
                    <li key={item} className="flex gap-3 text-sm text-slate-300">
                      <ChevronRight size={16} className="text-cyan-400 flex-shrink-0 mt-0.5" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl border border-emerald-500/15 bg-emerald-500/5 p-5 sm:p-6">
                <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
                  <Lightbulb size={19} className="text-emerald-300" />
                  Boas práticas
                </h2>
                <ul className="space-y-3">
                  {tutorial.bestPractices.map((item) => (
                    <li key={item} className="flex gap-3 text-sm leading-6 text-slate-300">
                      <CheckCircle2 size={16} className="text-emerald-400 flex-shrink-0 mt-1" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            {tutorial.attention?.length > 0 && (
              <section className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 sm:p-6 mb-10">
                <h2 className="font-semibold text-amber-100 mb-4 flex items-center gap-2">
                  <AlertTriangle size={20} className="text-amber-300" />
                  Atenção
                </h2>
                <ul className="space-y-3">
                  {tutorial.attention.map((item) => (
                    <li key={item} className="text-sm leading-6 text-amber-100/80">• {item}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="rounded-2xl border border-purple-500/25 bg-gradient-to-br from-purple-500/10 to-cyan-500/5 p-6 sm:p-7 mb-10">
              <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <CheckCircle2 size={21} className="text-purple-300" />
                Você concluiu este guia quando...
              </h2>
              <div className="space-y-3">
                {tutorial.doneWhen.map((item) => (
                  <div key={item} className="flex gap-3 items-start">
                    <div className="mt-1 w-5 h-5 rounded border border-purple-400/50 bg-slate-950/40 flex-shrink-0" />
                    <p className="text-sm sm:text-base leading-6 text-slate-300">{item}</p>
                  </div>
                ))}
              </div>
            </section>

            <nav className="grid sm:grid-cols-2 gap-4 border-t border-slate-800 pt-7" aria-label="Tutoriais anterior e próximo">
              {previous ? (
                <Link
                  to={`/tutoriais/coordenadores/${previous.slug}`}
                  className="group rounded-2xl border border-slate-800 bg-slate-900/45 p-5 hover:border-purple-500/30 transition-colors"
                >
                  <span className="text-xs text-slate-500 flex items-center gap-1 mb-2">
                    <ArrowLeft size={14} /> Anterior
                  </span>
                  <span className="text-sm font-medium text-slate-200 group-hover:text-white">{previous.title}</span>
                </Link>
              ) : <div />}

              {next ? (
                <Link
                  to={`/tutoriais/coordenadores/${next.slug}`}
                  className="group rounded-2xl border border-slate-800 bg-slate-900/45 p-5 hover:border-purple-500/30 transition-colors sm:text-right"
                >
                  <span className="text-xs text-slate-500 flex items-center sm:justify-end gap-1 mb-2">
                    Próximo <ArrowRight size={14} />
                  </span>
                  <span className="text-sm font-medium text-slate-200 group-hover:text-white">{next.title}</span>
                </Link>
              ) : (
                <Link
                  to="/tutoriais"
                  className="group rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5 sm:text-right"
                >
                  <span className="text-xs text-emerald-400 mb-2 block">Trilha concluída</span>
                  <span className="text-sm font-medium text-slate-200 group-hover:text-white">Voltar à Central de Tutoriais</span>
                </Link>
              )}
            </nav>
          </article>
        </div>
      </main>

      <footer className="border-t border-slate-800/80 py-7 px-4">
        <div className="max-w-7xl mx-auto text-center text-xs text-slate-600">
          SIGESC — Tutoriais de apoio ao trabalho pedagógico
        </div>
      </footer>
    </div>
  );
}
