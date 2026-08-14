/**
 * ⛔ MÓDULO BLOQUEADO — Tutorial Diário AEE
 *
 * Faz parte do módulo Diário AEE (bloqueado). NÃO altere sem autorização
 * explícita do usuário. Veja /app/memory/PRD.md → "MÓDULOS BLOQUEADOS".
 *
 * Alteração autorizada explicitamente pelo proprietário em 14/08/2026:
 * revisão pedagógica e visual APENAS deste tutorial, sem mudança funcional
 * no Diário AEE.
 */
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Award,
  BookOpen,
  Calendar,
  CheckSquare,
  ChevronRight,
  Clock,
  Download,
  Eye,
  FileText,
  GraduationCap,
  HelpCircle,
  Lightbulb,
  Printer,
  School,
  Target,
  Users,
} from 'lucide-react';

const navItems = [
  { href: '#comece-aqui', label: 'Comece por aqui' },
  { href: '#mapa-tela', label: 'Conheça a tela' },
  { href: '#plano', label: '1. Criar o Plano de AEE' },
  { href: '#atendimento', label: '2. Registrar um Atendimento' },
  { href: '#diario', label: '3. Acompanhar o Diário' },
  { href: '#pdf', label: '4. Gerar o PDF' },
  { href: '#modelos', label: 'Atalho: usar Modelos' },
  { href: '#duvidas', label: 'Dúvidas e erros comuns' },
  { href: '#checklist', label: 'Checklist final' },
];

const screenAreas = [
  {
    icon: School,
    title: 'Escola/Polo AEE',
    text: 'Define em qual unidade você está trabalhando. Confira este campo antes de iniciar.',
    tone: 'blue',
  },
  {
    icon: Calendar,
    title: 'Ano Letivo',
    text: 'Garante que planos, atendimentos e relatórios sejam consultados no ano correto.',
    tone: 'purple',
  },
  {
    icon: Users,
    title: 'Turma AEE',
    text: 'Quando disponível, filtra estudantes, planos e atendimentos da turma selecionada.',
    tone: 'cyan',
  },
];

const tabs = [
  {
    icon: Users,
    title: 'Estudantes',
    text: 'Veja quem possui Plano de AEE e acesse ações rápidas do estudante.',
    className: 'border-blue-500/30 bg-blue-500/10',
    iconClassName: 'text-blue-400',
  },
  {
    icon: FileText,
    title: 'Planos de AEE',
    text: 'Crie, consulte, edite e acompanhe os planos pedagógicos.',
    className: 'border-green-500/30 bg-green-500/10',
    iconClassName: 'text-green-400',
  },
  {
    icon: CheckSquare,
    title: 'Atendimentos',
    text: 'Registre cada encontro realizado e mantenha o histórico pedagógico atualizado.',
    className: 'border-orange-500/30 bg-orange-500/10',
    iconClassName: 'text-orange-400',
  },
  {
    icon: BookOpen,
    title: 'Diário Consolidado',
    text: 'Acompanhe estudantes, atendimentos, planos, carga horária e frequência.',
    className: 'border-pink-500/30 bg-pink-500/10',
    iconClassName: 'text-pink-400',
  },
  {
    icon: Award,
    title: 'Modelos',
    text: 'Quando disponível para o seu perfil, permite iniciar um plano a partir de um modelo pronto.',
    className: 'border-teal-500/30 bg-teal-500/10',
    iconClassName: 'text-teal-400',
  },
];

const planGroups = [
  {
    number: '1',
    title: 'Identifique o estudante',
    text: 'Selecione o aluno e confira turma de origem, professor regente, público-alvo e informações básicas.',
  },
  {
    number: '2',
    title: 'Descreva a situação inicial',
    text: 'Registre potencialidades, barreiras observadas, formas de comunicação e como o estudante participa hoje.',
  },
  {
    number: '3',
    title: 'Defina o atendimento',
    text: 'Informe modalidade, dias, horários, carga horária semanal e local do atendimento.',
  },
  {
    number: '4',
    title: 'Estabeleça objetivos e estratégias',
    text: 'Transforme as necessidades observadas em objetivos claros, recursos de acessibilidade e ações pedagógicas.',
  },
  {
    number: '5',
    title: 'Planeje o acompanhamento',
    text: 'Defina indicadores de progresso, frequência de revisão e articulação com a sala comum.',
  },
];

const attendanceFields = [
  ['Plano/Estudante', 'Escolha o plano do estudante atendido.'],
  ['Data e horário', 'Informe quando o atendimento ocorreu.'],
  ['Presença', 'Mantenha marcado se o estudante compareceu; em caso de ausência, registre o motivo.'],
  ['Objetivo trabalhado', 'Indique qual objetivo do Plano de AEE foi trabalhado naquele encontro.'],
  ['Atividade/Estratégia realizada', 'Descreva de forma objetiva o que foi feito.'],
  ['Nível de apoio', 'Registre o grau de apoio necessário: independente, mínimo, moderado ou total.'],
  ['Resposta do estudante', 'Anote como o estudante participou e respondeu à proposta.'],
  ['Próximo encontro', 'Deixe indicado o encaminhamento para a continuidade do trabalho.'],
];

const commonQuestions = [
  {
    question: 'O botão “Novo Atendimento” está desabilitado. O que faço?',
    answer: 'Primeiro crie um Plano de AEE para pelo menos um estudante. O atendimento precisa estar vinculado a um plano.',
  },
  {
    question: 'O estudante faltou. Devo deixar de registrar?',
    answer: 'Não. Abra o atendimento, desmarque “Presente” e informe o motivo da ausência. Assim o histórico fica completo.',
  },
  {
    question: 'Preciso criar um novo plano a cada bimestre?',
    answer: 'Não necessariamente. O plano pode ser revisado e atualizado. Um novo plano deve ser criado quando o fluxo pedagógico da rede ou uma mudança relevante justificar isso.',
  },
  {
    question: 'Posso corrigir um atendimento já salvo?',
    answer: 'Quando seu perfil possuir permissão de edição, use o ícone de editar no registro do atendimento e faça a correção necessária.',
  },
  {
    question: 'Não encontro a aba “Modelos”. Há algum problema?',
    answer: 'Não necessariamente. A aba é exibida conforme a permissão do seu perfil. Se ela não aparecer, siga normalmente pelo botão “Novo Plano de AEE”.',
  },
];

function StepBadge({ children }) {
  return (
    <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-teal-500/20 font-bold text-teal-300">
      {children}
    </span>
  );
}

function Tip({ children, tone = 'yellow' }) {
  const styles = tone === 'green'
    ? 'border-green-500/30 bg-green-500/10 text-green-200'
    : tone === 'blue'
      ? 'border-blue-500/30 bg-blue-500/10 text-blue-200'
      : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200';

  return (
    <div className={`rounded-xl border p-4 ${styles}`}>
      <div className="flex items-start gap-3 text-sm leading-relaxed">
        <Lightbulb size={18} className="mt-0.5 flex-shrink-0" />
        <div>{children}</div>
      </div>
    </div>
  );
}

function SectionTitle({ icon: Icon, kicker, title, description }) {
  return (
    <div className="mb-6">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-teal-300">
        <Icon size={18} />
        {kicker}
      </div>
      <h2 className="text-2xl font-bold text-white sm:text-3xl">{title}</h2>
      {description && <p className="mt-3 max-w-3xl leading-relaxed text-slate-400">{description}</p>}
    </div>
  );
}

export default function TutorialDiarioAEE() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100">
      <header className="fixed left-0 right-0 top-0 z-50 border-b border-slate-700/50 bg-slate-950/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="flex items-center gap-3">
            <div className="rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 p-2">
              <GraduationCap className="h-8 w-8 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">SIGESC</h1>
              <p className="text-xs text-slate-400">Sistema de Gestão Escolar</p>
            </div>
          </Link>

          <Link
            to="/tutoriais"
            className="flex items-center gap-2 text-sm text-slate-300 transition-colors hover:text-white"
          >
            <ArrowLeft size={18} />
            <span className="hidden sm:inline">Voltar aos Tutoriais</span>
            <span className="sm:hidden">Voltar</span>
          </Link>
        </div>
      </header>

      <main className="px-4 pb-20 pt-24 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <section className="mb-10 overflow-hidden rounded-3xl border border-teal-500/20 bg-gradient-to-br from-teal-500/10 via-slate-900 to-blue-500/10 p-6 sm:p-9">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-teal-500/20 bg-teal-500/10 px-4 py-2">
              <Award size={16} className="text-teal-400" />
              <span className="text-sm font-medium text-teal-200">Professor(a) AEE • Guia passo a passo</span>
            </div>

            <h1 className="max-w-4xl text-3xl font-bold leading-tight text-white sm:text-5xl">
              Diário AEE: do primeiro acesso ao PDF, sem complicação
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-relaxed text-slate-300 sm:text-lg">
              Este guia foi organizado na mesma ordem em que o trabalho acontece no dia a dia. Você vai aprender o que conferir, onde clicar, o que escrever e como saber se concluiu cada etapa corretamente.
            </p>

            <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['1', 'Selecionar escola e ano'],
                ['2', 'Criar o Plano de AEE'],
                ['3', 'Registrar atendimentos'],
                ['4', 'Acompanhar e gerar PDF'],
              ].map(([number, text]) => (
                <div key={number} className="flex items-center gap-3 rounded-xl border border-slate-700/60 bg-slate-950/40 p-3">
                  <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-teal-500/20 text-sm font-bold text-teal-300">
                    {number}
                  </span>
                  <span className="text-sm font-medium text-slate-200">{text}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="mb-10 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-5 sm:p-6">
            <div className="mb-4 flex items-center gap-2">
              <BookOpen size={20} className="text-teal-400" />
              <h2 className="text-lg font-semibold text-white">Ir direto ao que você precisa</h2>
            </div>
            <nav className="grid gap-2 sm:grid-cols-2">
              {navItems.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="group flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700/50 hover:text-teal-300"
                >
                  <ChevronRight size={16} className="text-slate-500 transition-transform group-hover:translate-x-0.5 group-hover:text-teal-400" />
                  {item.label}
                </a>
              ))}
            </nav>
          </section>

          <section id="comece-aqui" className="mb-12 scroll-mt-24 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-6 sm:p-8">
            <SectionTitle
              icon={CheckSquare}
              kicker="Antes de começar"
              title="Faça três conferências rápidas"
              description="A maior parte das dúvidas no início acontece porque a pessoa está olhando a escola, o ano ou a turma errados. Confira estes pontos primeiro."
            />

            <div className="space-y-4">
              {[
                ['1', 'Entre no SIGESC e abra o Diário AEE.', 'No menu do sistema, acesse o módulo Diário AEE.'],
                ['2', 'Confira a Escola/Polo AEE.', 'Selecione a unidade em que o atendimento está sendo registrado.'],
                ['3', 'Confira o Ano Letivo e, se aparecer, a Turma AEE.', 'Os dados exibidos abaixo obedecem a esses filtros.'],
              ].map(([number, title, text]) => (
                <div key={number} className="flex gap-4 rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                  <StepBadge>{number}</StepBadge>
                  <div>
                    <h3 className="font-semibold text-white">{title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-slate-400">{text}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="blue">
                <strong>Se nenhuma escola aparecer:</strong> a unidade precisa estar habilitada para AEE no cadastro de escolas. Nesse caso, procure a gestão da rede ou um usuário responsável pelo cadastro.
              </Tip>
            </div>
          </section>

          <section id="mapa-tela" className="mb-12 scroll-mt-24">
            <SectionTitle
              icon={Eye}
              kicker="Conheça a tela"
              title="Primeiro entenda onde cada coisa fica"
              description="Você não precisa memorizar tudo. Pense na tela em duas partes: filtros na parte superior e abas de trabalho logo abaixo."
            />

            <div className="mb-5 grid gap-4 md:grid-cols-3">
              {screenAreas.map((item) => {
                const Icon = item.icon;
                const toneClasses = {
                  blue: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
                  purple: 'border-purple-500/30 bg-purple-500/10 text-purple-400',
                  cyan: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-400',
                };
                return (
                  <div key={item.title} className={`rounded-2xl border p-5 ${toneClasses[item.tone]}`}>
                    <Icon size={22} className="mb-3" />
                    <h3 className="font-semibold text-white">{item.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-slate-400">{item.text}</p>
                  </div>
                );
              })}
            </div>

            <div className="rounded-2xl border border-slate-700/60 bg-slate-800/40 p-5 sm:p-6">
              <h3 className="mb-4 font-semibold text-white">As abas do Diário AEE</h3>
              <div className="grid gap-3 md:grid-cols-2">
                {tabs.map((tab) => {
                  const Icon = tab.icon;
                  return (
                    <div key={tab.title} className={`rounded-xl border p-4 ${tab.className}`}>
                      <div className="flex items-start gap-3">
                        <Icon size={20} className={`mt-0.5 flex-shrink-0 ${tab.iconClassName}`} />
                        <div>
                          <h4 className="font-semibold text-white">{tab.title}</h4>
                          <p className="mt-1 text-sm leading-relaxed text-slate-400">{tab.text}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-xs leading-relaxed text-slate-500">
                A aba “Modelos” depende da permissão do seu perfil. Se ela não aparecer, isso não impede o uso normal do Diário AEE.
              </p>
            </div>
          </section>

          <section id="plano" className="mb-12 scroll-mt-24 rounded-2xl border border-green-500/20 bg-green-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={FileText}
              kicker="Passo 1"
              title="Crie o Plano de AEE do estudante"
              description="O plano é a base do trabalho. Ele organiza o ponto de partida, os objetivos, a rotina de atendimento e como o progresso será acompanhado."
            />

            <div className="mb-6 rounded-xl border border-green-500/20 bg-slate-950/40 p-5">
              <h3 className="font-semibold text-white">Caminho na tela</h3>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Estudantes ou Planos de AEE</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-green-500/15 px-3 py-2 font-semibold text-green-300">Novo Plano de AEE</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Preencher e salvar</span>
              </div>
            </div>

            <h3 className="mb-4 text-lg font-semibold text-white">Em vez de pensar em muitos campos, pense em 5 perguntas:</h3>
            <div className="space-y-3">
              {planGroups.map((group) => (
                <div key={group.number} className="flex gap-4 rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-green-500/15 font-bold text-green-300">
                    {group.number}
                  </span>
                  <div>
                    <h4 className="font-semibold text-white">{group.title}</h4>
                    <p className="mt-1 text-sm leading-relaxed text-slate-400">{group.text}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-slate-700/60 bg-slate-950/40 p-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <Target size={18} className="text-green-400" />
                  Exemplo de objetivo bem escrito
                </div>
                <p className="mb-2 text-sm text-red-300">Evite: “Melhorar a leitura.”</p>
                <p className="text-sm leading-relaxed text-green-200">
                  Prefira: “Reconhecer e nomear as letras do alfabeto trabalhadas, com redução progressiva de apoio, até a próxima revisão do plano.”
                </p>
              </div>

              <div className="rounded-xl border border-slate-700/60 bg-slate-950/40 p-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <Activity size={18} className="text-cyan-400" />
                  Exemplo de linha de base
                </div>
                <p className="text-sm leading-relaxed text-slate-300">
                  “Reconhece o próprio nome e algumas letras. Participa melhor com apoio visual e instruções curtas. Mantém atenção por períodos breves e responde positivamente a atividades com material concreto.”
                </p>
              </div>
            </div>

            <div className="mt-5">
              <Tip>
                <strong>Escreva sobre aprendizagem e participação.</strong> Na justificativa pedagógica, descreva barreiras, apoios e necessidades observadas no contexto escolar. Evite transformar o campo em reprodução de laudo ou CID.
              </Tip>
            </div>

            <div className="mt-5 rounded-xl border border-green-500/30 bg-green-500/10 p-4">
              <p className="text-sm text-green-100">
                <strong>Você concluiu este passo quando:</strong> o plano aparece na aba “Planos de AEE” e pode ser associado a um novo atendimento.
              </p>
            </div>
          </section>

          <section id="atendimento" className="mb-12 scroll-mt-24 rounded-2xl border border-orange-500/20 bg-orange-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={CheckSquare}
              kicker="Passo 2"
              title="Registre cada atendimento realizado"
              description="O atendimento é o registro do que realmente aconteceu. Faça o lançamento logo após o encontro sempre que possível, enquanto as informações ainda estão claras."
            />

            <div className="mb-6 rounded-xl border border-orange-500/20 bg-slate-950/40 p-5">
              <h3 className="font-semibold text-white">Caminho mais simples</h3>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Atendimentos</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-orange-500/15 px-3 py-2 font-semibold text-orange-300">Novo Atendimento</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Preencher</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Salvar</span>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-slate-700/60">
              {attendanceFields.map(([label, text], index) => (
                <div
                  key={label}
                  className={`grid gap-1 bg-slate-900/40 p-4 sm:grid-cols-[190px_1fr] sm:gap-4 ${index > 0 ? 'border-t border-slate-700/60' : ''}`}
                >
                  <span className="text-sm font-semibold text-slate-200">{label}</span>
                  <span className="text-sm leading-relaxed text-slate-400">{text}</span>
                </div>
              ))}
            </div>

            <details className="mt-6 rounded-xl border border-orange-500/20 bg-orange-500/10 p-4 open:bg-orange-500/15">
              <summary className="cursor-pointer font-semibold text-orange-200">Ver exemplo de um registro pedagógico objetivo</summary>
              <div className="mt-4 space-y-3 text-sm leading-relaxed text-slate-300">
                <p><strong className="text-white">Objetivo trabalhado:</strong> ampliar a autonomia na identificação de palavras do cotidiano.</p>
                <p><strong className="text-white">Atividade:</strong> pareamento entre imagens e palavras com apoio de cartões visuais; leitura mediada de cinco palavras familiares.</p>
                <p><strong className="text-white">Resposta do estudante:</strong> realizou três associações de forma independente e duas com pista verbal.</p>
                <p><strong className="text-white">Próximo encontro:</strong> retomar as cinco palavras e introduzir duas novas, reduzindo gradualmente as pistas.</p>
              </div>
            </details>

            <div className="mt-5">
              <Tip>
                <strong>Se o estudante faltar, registre mesmo assim.</strong> Desmarque “Presente” e informe o motivo da ausência. O histórico do Diário fica mais fiel quando presenças e ausências estão documentadas.
              </Tip>
            </div>

            <div className="mt-5 rounded-xl border border-orange-500/30 bg-orange-500/10 p-4">
              <p className="text-sm text-orange-100">
                <strong>Você concluiu este passo quando:</strong> o atendimento aparece na lista com estudante, data, horário, objetivo e atividade registrados.
              </p>
            </div>
          </section>

          <section id="diario" className="mb-12 scroll-mt-24 rounded-2xl border border-pink-500/20 bg-pink-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={BookOpen}
              kicker="Passo 3"
              title="Use o Diário Consolidado para acompanhar o trabalho"
              description="Esta aba transforma os registros individuais em uma visão geral do AEE. Ela serve para acompanhamento pedagógico, conferência da rotina e preparação de relatórios."
            />

            <div className="grid gap-4 md:grid-cols-2">
              {[
                ['Estudantes', 'Quantidade de estudantes atendidos no filtro selecionado.'],
                ['Atendimentos', 'Total de registros realizados no período consultado.'],
                ['Planos Ativos', 'Quantidade de planos considerados na visão atual.'],
                ['Carga Horária', 'Soma do tempo registrado nos atendimentos.'],
                ['Grade de Atendimentos', 'Organização dos horários por dia da semana.'],
                ['Fichas Individuais', 'Resumo de presença, carga horária e dados de cada estudante.'],
              ].map(([title, text]) => (
                <div key={title} className="rounded-xl border border-slate-700/60 bg-slate-900/50 p-4">
                  <h3 className="font-semibold text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-400">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="blue">
                <strong>Faça uma conferência periódica.</strong> Se a carga horária, a frequência ou a quantidade de atendimentos parecer diferente do esperado, volte à aba “Atendimentos” e confira os registros antes de gerar o PDF.
              </Tip>
            </div>
          </section>

          <section id="pdf" className="mb-12 scroll-mt-24 rounded-2xl border border-purple-500/20 bg-purple-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Printer}
              kicker="Passo 4"
              title="Gere o PDF somente depois de conferir os registros"
              description="O PDF é o resultado documental do trabalho registrado. Por isso, a melhor sequência é: registrar → conferir → gerar."
            />

            <div className="space-y-4">
              {[
                ['1', 'Abra a aba “Diário Consolidado”.'],
                ['2', 'Confira se Escola/Polo AEE, Ano Letivo e Turma AEE estão corretos.'],
                ['3', 'Revise os indicadores e as fichas individuais.'],
                ['4', 'Clique em “Baixar PDF Completo”.'],
                ['5', 'Escolha o período solicitado quando o sistema apresentar as opções e conclua o download.'],
              ].map(([number, text]) => (
                <div key={number} className="flex items-start gap-4 rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                  <StepBadge>{number}</StepBadge>
                  <p className="pt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-5 rounded-xl border border-purple-500/30 bg-purple-500/10 p-4">
              <p className="text-sm text-purple-100">
                <strong>Também existe PDF individual:</strong> nas fichas do estudante, o ícone de download permite gerar o documento de um aluno específico.
              </p>
            </div>
          </section>

          <section id="modelos" className="mb-12 scroll-mt-24 rounded-2xl border border-teal-500/20 bg-teal-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Award}
              kicker="Atalho opcional"
              title="Se a aba Modelos aparecer, use-a para ganhar tempo"
              description="Os modelos ajudam a iniciar um plano com uma estrutura previamente preparada. Eles são um ponto de partida — o plano do estudante continua precisando ser conferido e personalizado."
            />

            <div className="grid gap-4 md:grid-cols-3">
              {[
                ['1', 'Abra “Modelos” ou escolha a opção de criar plano a partir de modelo.'],
                ['2', 'Selecione o modelo adequado e o estudante.'],
                ['3', 'Revise o plano criado, personalize o que for necessário e salve.'],
              ].map(([number, text]) => (
                <div key={number} className="rounded-xl border border-teal-500/20 bg-slate-900/50 p-5">
                  <span className="mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-teal-500/20 text-sm font-bold text-teal-300">{number}</span>
                  <p className="text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="green">
                <strong>Modelo não é plano pronto.</strong> Ele acelera o preenchimento, mas a observação do estudante, os objetivos e as estratégias precisam representar a situação real daquele aluno.
              </Tip>
            </div>
          </section>

          <section id="duvidas" className="mb-12 scroll-mt-24 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-6 sm:p-8">
            <SectionTitle
              icon={HelpCircle}
              kicker="Quando algo não sair como esperado"
              title="Dúvidas e erros comuns"
              description="Abra apenas a pergunta que corresponde ao seu problema."
            />

            <div className="space-y-3">
              {commonQuestions.map((item) => (
                <details key={item.question} className="group rounded-xl border border-slate-700/60 bg-slate-900/50 p-4 open:border-blue-500/30 open:bg-blue-500/5">
                  <summary className="flex cursor-pointer list-none items-start justify-between gap-4 font-semibold text-white">
                    <span>{item.question}</span>
                    <ChevronRight size={18} className="mt-0.5 flex-shrink-0 text-slate-500 transition-transform group-open:rotate-90 group-open:text-blue-400" />
                  </summary>
                  <p className="mt-3 border-t border-slate-700/50 pt-3 text-sm leading-relaxed text-slate-400">{item.answer}</p>
                </details>
              ))}
            </div>
          </section>

          <section id="checklist" className="mb-12 scroll-mt-24 overflow-hidden rounded-2xl border border-green-500/30 bg-gradient-to-br from-green-500/10 to-teal-500/10 p-6 sm:p-8">
            <SectionTitle
              icon={CheckSquare}
              kicker="Antes de encerrar"
              title="Checklist do Diário AEE em dia"
              description="Use esta lista como uma conferência rápida da sua rotina."
            />

            <div className="grid gap-3 md:grid-cols-2">
              {[
                'Escola/Polo AEE, ano letivo e turma conferidos.',
                'Cada estudante atendido possui Plano de AEE adequado ao período.',
                'Os objetivos do plano estão claros e observáveis.',
                'Cada atendimento realizado — inclusive ausência — foi registrado.',
                'Objetivo, atividade, resposta do estudante e encaminhamento foram descritos.',
                'O Diário Consolidado foi conferido antes da emissão do PDF.',
                'O PDF foi gerado no período correto quando necessário.',
                'O plano será revisado conforme a frequência definida.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-xl border border-green-500/20 bg-slate-950/30 p-4">
                  <CheckSquare size={18} className="mt-0.5 flex-shrink-0 text-green-400" />
                  <span className="text-sm leading-relaxed text-slate-200">{item}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-700/60 bg-slate-800/40 p-7 text-center sm:p-9">
            <HelpCircle size={44} className="mx-auto mb-4 text-teal-400" />
            <h2 className="text-xl font-bold text-white">Ainda ficou com alguma dúvida?</h2>
            <p className="mx-auto mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
              Procure a coordenação pedagógica ou o suporte técnico da sua rede. Ao pedir ajuda, informe em qual etapa você estava e o que apareceu na tela — isso facilita muito a orientação.
            </p>
            <div className="mt-5 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                to="/tutoriais"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700/60"
              >
                <ArrowLeft size={17} />
                Voltar aos Tutoriais
              </Link>
              <Link
                to="/login"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-500"
              >
                <BookOpen size={17} />
                Acessar o SIGESC
              </Link>
            </div>
          </section>
        </div>
      </main>

      <footer className="border-t border-slate-700/50 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 text-sm sm:flex-row">
          <span className="text-slate-400">© {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar</span>
          <div className="flex items-center gap-2 text-slate-500">
            <Clock size={15} />
            <span>Guia do Diário AEE</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
