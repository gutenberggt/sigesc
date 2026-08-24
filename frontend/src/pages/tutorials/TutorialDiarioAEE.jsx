/**
 * ⛔ MÓDULO BLOQUEADO — Tutorial Diário AEE
 *
 * Faz parte do módulo Diário AEE. NÃO alterar o comportamento funcional do
 * Diário AEE por meio deste arquivo.
 *
 * Alteração autorizada explicitamente pelo proprietário em 23/08/2026:
 * reorganização editorial e pedagógica do Guia do Professor AEE, após a
 * conclusão e homologação das adequações do Diário AEE V2.
 */
import { Link } from 'react-router-dom';
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Award,
  BookOpen,
  Calendar,
  CheckCircle2,
  CheckSquare,
  ChevronRight,
  Clock,
  Eye,
  FileText,
  GraduationCap,
  HelpCircle,
  History,
  Lightbulb,
  MessageCircle,
  Printer,
  School,
  Target,
  Users,
} from 'lucide-react';

const navItems = [
  { href: '#acolhida', label: 'Comece por aqui' },
  { href: '#mapa', label: 'O caminho do trabalho' },
  { href: '#tela', label: 'Conheça a tela' },
  { href: '#plano', label: '1. Plano de AEE' },
  { href: '#dossie', label: '2. Dossiê AEE V2' },
  { href: '#estudo-caso', label: '3. Estudo de Caso' },
  { href: '#paee', label: '4. PAEE' },
  { href: '#pei', label: '5. PEI' },
  { href: '#agenda', label: '6. Agenda, vigência e revisão' },
  { href: '#vigente', label: '7. Tornar a versão vigente' },
  { href: '#atendimentos', label: '8. Atendimentos' },
  { href: '#acompanhar', label: '9. Acompanhar e consultar' },
  { href: '#pdf', label: '10. Visualização e PDF' },
  { href: '#duvidas', label: 'Dúvidas frequentes' },
  { href: '#checklist', label: 'Checklist do professor' },
];

const screenAreas = [
  {
    icon: School,
    title: 'Escola/Polo AEE',
    text: 'Mostra em qual unidade você está trabalhando. Antes de lançar qualquer registro, confira se a escola está correta.',
    className: 'border-blue-500/30 bg-blue-500/10',
    iconClassName: 'text-blue-400',
  },
  {
    icon: Calendar,
    title: 'Ano Letivo',
    text: 'Organiza os planos e atendimentos no ano correspondente. Um registro de 2026, por exemplo, deve ser consultado no ano letivo 2026.',
    className: 'border-purple-500/30 bg-purple-500/10',
    iconClassName: 'text-purple-400',
  },
  {
    icon: Users,
    title: 'Turma AEE',
    text: 'Quando este filtro estiver disponível, ajuda a localizar os estudantes e os registros da turma selecionada.',
    className: 'border-cyan-500/30 bg-cyan-500/10',
    iconClassName: 'text-cyan-400',
  },
];

const mainTabs = [
  ['Estudantes', 'Localize os estudantes do AEE e confira quem já possui plano.'],
  ['Planos de AEE', 'Crie o registro inicial, abra o Dossiê V2, visualize e acompanhe a situação do plano.'],
  ['Atendimentos', 'Registre o que aconteceu em cada encontro com o estudante.'],
  ['Diário Consolidado', 'Confira frequência, carga horária, atendimentos e fichas individuais.'],
  ['Modelos', 'Quando disponível, oferece um ponto de partida para criar um novo plano.'],
];

const journey = [
  {
    number: '1',
    title: 'Localize o estudante',
    text: 'Confira escola, ano e estudante antes de começar. Isso evita registrar informações no contexto errado.',
  },
  {
    number: '2',
    title: 'Garanta que exista um Plano de AEE',
    text: 'O plano é o ponto de partida. Se o estudante ainda não possui um, crie pelo botão “Novo Plano” ou use um modelo, quando disponível.',
  },
  {
    number: '3',
    title: 'Abra o Dossiê AEE V2',
    text: 'É no Dossiê que o plano ganha profundidade: Estudo de Caso, PAEE, PEI, agenda, vigência, revisão e histórico.',
  },
  {
    number: '4',
    title: 'Revise com calma, seção por seção',
    text: 'Não é necessário preencher tudo de uma vez. Salve cada parte e retome depois, se precisar.',
  },
  {
    number: '5',
    title: 'Quando estiver pronto, torne a versão vigente',
    text: 'O SIGESC mostra o que ainda precisa ser revisto. Quando não houver pendências, a versão pode passar a ser a referência atual.',
  },
  {
    number: '6',
    title: 'Registre os atendimentos e acompanhe a evolução',
    text: 'O trabalho cotidiano alimenta o histórico e ajuda a decidir o que manter, ajustar ou aprofundar nas próximas revisões.',
  },
];

const dossierTabs = [
  ['Visão Geral', 'Mostra qual versão está vigente, se existe uma versão em trabalho e quais pontos ainda precisam de atenção.'],
  ['Estudo de Caso', 'Organiza as informações sobre participação, barreiras, potencialidades, comunicação, apoios e contexto escolar.'],
  ['PAEE', 'Transforma as necessidades observadas em objetivos, recursos, apoios e indicadores de progresso.'],
  ['PEI', 'Registra como o AEE se articula com a sala comum, o currículo, as estratégias de acesso e o acompanhamento do estudante.'],
  ['Agenda', 'Organiza a carga horária e os dias, horários, local e modalidade dos atendimentos.'],
  ['Vigência e Revisão', 'Define quando o plano começa a valer, quando será revisto e, quando necessário, seu período de encerramento.'],
  ['Atendimentos', 'Permite consultar os atendimentos já vinculados ao plano.'],
  ['Articulação', 'Reúne os registros de diálogo e encaminhamentos construídos com a sala comum e outros participantes.'],
  ['Evolução', 'Ajuda a consultar os registros de progresso, mudanças percebidas e necessidades de ajuste.'],
  ['Histórico', 'Mostra as versões e revisões guardadas ao longo do tempo.'],
];

const studyCaseGuides = [
  {
    title: 'Fundamentação pedagógica da identificação para o AEE',
    question: 'Por que este estudante precisa do AEE no contexto escolar?',
    example: '“O estudante participa das atividades da turma, mas encontra barreiras para compreender instruções longas e organizar respostas escritas. Demonstra melhor desempenho quando recebe apoio visual, linguagem objetiva e tempo adicional para organizar a resposta.”',
  },
  {
    title: 'Barreiras identificadas',
    question: 'O que, no ambiente, na comunicação, nas atividades ou na organização da rotina, dificulta sua participação?',
    example: '“Instruções com muitas etapas; excesso de estímulos visuais na folha; dificuldade para solicitar ajuda quando não compreende a tarefa.”',
  },
  {
    title: 'Potencialidades',
    question: 'O que o estudante já faz bem e pode ser usado como ponto de apoio?',
    example: '“Boa memória visual, interesse por jogos de associação, participação positiva em atividades com material concreto e facilidade para aprender por demonstração.”',
  },
  {
    title: 'Comunicação e participação',
    question: 'Como ele se comunica, faz escolhas, demonstra compreensão e participa das propostas?',
    example: '“Expressa preferências verbalmente, responde melhor a perguntas objetivas e participa com mais segurança quando a rotina é antecipada visualmente.”',
  },
  {
    title: 'Contribuições do estudante e da família',
    question: 'O que o próprio estudante e a família ajudam a compreender sobre necessidades, interesses e estratégias que funcionam?',
    example: '“A família informa que listas visuais ajudam na rotina de casa. O estudante relata que prefere receber uma tarefa por vez e pede para conferir o que já concluiu.”',
  },
];

const paeeCycle = [
  ['Barreira prioritária', '“Dificuldade para acompanhar instruções longas apresentadas apenas oralmente.”'],
  ['Objetivo', '“Seguir instruções de até três etapas com apoio visual, reduzindo gradualmente a necessidade de repetição.”'],
  ['Estratégia/Recurso', '“Sequência visual com imagens, instrução curta e conferência de cada etapa concluída.”'],
  ['Indicador de progresso', '“Realiza duas das três etapas com autonomia em quatro de cinco oportunidades observadas.”'],
];

const supportStatuses = [
  ['Não avaliado', 'Use quando você ainda não reuniu informações suficientes para decidir.'],
  ['Não necessário', 'Use quando a necessidade foi analisada e, naquele momento, o apoio não se mostra necessário.'],
  ['Necessário', 'Use quando o apoio é importante para favorecer acesso, participação ou autonomia.'],
  ['Disponibilizado', 'Use quando o recurso ou apoio necessário já está sendo oferecido.'],
  ['Indisponível', 'Use quando a necessidade existe, mas o recurso ainda não está disponível; registre a justificativa e os encaminhamentos possíveis.'],
];

const peiGuides = [
  ['Atividades do AEE', 'Registre as propostas que serão desenvolvidas no atendimento especializado. Ex.: uso de agenda visual, treino de comunicação funcional, organização de materiais, recursos de leitura acessível.'],
  ['Articulação com a Sala Comum', 'Explique como o que é desenvolvido no AEE ajudará a participação na turma regular. Ex.: combinar com o professor regente o uso das mesmas pistas visuais nas atividades coletivas.'],
  ['Combinados com o Professor Regente', 'Registre decisões práticas. Ex.: oferecer instruções em etapas, antecipar mudanças de rotina e permitir resposta oral quando o objetivo da atividade não for avaliar a escrita.'],
  ['Acessibilidade Curricular', 'Descreva como o estudante terá acesso aos objetivos de aprendizagem, sem reduzir automaticamente suas oportunidades de aprender.'],
  ['Acessibilidade Didático-Pedagógica', 'Registre mudanças na forma de apresentar a atividade: material concreto, apoio visual, leitura compartilhada, recursos digitais, organização do espaço ou tempo.'],
  ['Acessibilidade Avaliativa', 'Explique quais condições ajudam o estudante a demonstrar o que aprendeu: mais tempo, leitura do enunciado, resposta oral, apoio visual ou divisão da avaliação em partes.'],
  ['Adaptações por Componente/Campo de Experiência', 'Relacione as estratégias ao que está sendo trabalhado na turma. Na Educação Infantil, considere os campos de experiência; no Ensino Fundamental, os componentes curriculares.'],
  ['Devolutivas à família', 'Registre orientações e retornos que ajudem a família a compreender avanços, estratégias que funcionam e próximos objetivos.'],
];

const attendanceFields = [
  ['Plano/Estudante', 'Escolha o estudante correto. Antes de salvar, confira o nome novamente.'],
  ['Data e horário', 'Registre quando o atendimento realmente ocorreu.'],
  ['Presença', 'Se o estudante compareceu, mantenha a presença. Se faltou, registre a ausência e o motivo.'],
  ['Objetivo trabalhado', 'Escolha ou descreva o foco daquele encontro. Evite objetivos muito amplos.'],
  ['Atividade/Estratégia realizada', 'Conte, de forma simples, o que foi feito para trabalhar o objetivo.'],
  ['Nível de apoio', 'Indique quanto apoio foi necessário: independente, mínimo, moderado ou total.'],
  ['Resposta do estudante', 'Registre o que você observou: participação, acertos, dificuldades, iniciativa, estratégias que ajudaram.'],
  ['Próximo encontro', 'Deixe uma indicação de continuidade para não precisar recomeçar o raciocínio na próxima sessão.'],
];

const commonQuestions = [
  {
    question: 'O que significa “Em trabalho”?',
    answer: 'Significa que existe uma versão sendo revisada. Você pode continuar preenchendo e salvando as seções. Ela ainda não substituiu a versão vigente.',
  },
  {
    question: 'O que significa “Vigente”?',
    answer: 'É a versão que representa o plano atualmente considerado válido para consulta e emissão do documento individual.',
  },
  {
    question: 'Abri o Dossiê e aparece “Plano AEE legado” como fonte efetiva. Isso está errado?',
    answer: 'Não. Isso acontece quando ainda não existe uma versão V2 vigente. O plano anterior continua sendo a referência enquanto a nova versão está em elaboração.',
  },
  {
    question: 'Por que alguns dados aparecem como “Projetado do Plano anterior — revisar”?',
    answer: 'O SIGESC trouxe informações do plano que já existia para evitar que você comece do zero. Leia, atualize o que for necessário e marque a seção como concluída somente depois de revisar.',
  },
  {
    question: 'O sistema mostra várias pendências. Preciso resolver tudo de uma vez?',
    answer: 'Não. Use os botões “Corrigir” para ir até cada parte. Trabalhe por etapas, salve e retome quando precisar. A lista existe para ajudar na conferência final.',
  },
  {
    question: 'Por que os botões de duplicar ou excluir podem aparecer desabilitados em um plano com Dossiê V2?',
    answer: 'Porque esse plano já possui um histórico organizado no Dossiê V2. Nessa situação, continue as alterações pelo próprio Dossiê. O bloqueio evita que o histórico seja quebrado por engano.',
  },
  {
    question: 'Preciso criar um novo plano a cada bimestre?',
    answer: 'Não. Quando o plano já está vigente e precisa de mudanças, abra uma nova versão para revisão. A versão vigente continua valendo até que a nova esteja pronta.',
  },
  {
    question: 'O estudante faltou ao AEE. Devo deixar o dia sem registro?',
    answer: 'Não. Registre o atendimento como ausência e informe o motivo. Isso mantém o histórico de frequência completo.',
  },
  {
    question: 'Posso usar apenas o diagnóstico ou o CID para justificar o AEE?',
    answer: 'O diagnóstico pode compor as informações disponíveis, mas o registro pedagógico precisa explicar o que você observa na escola: barreiras, participação, comunicação, potencialidades, apoios e estratégias necessárias.',
  },
  {
    question: 'Não aparece a aba “Modelos”. Há algum problema?',
    answer: 'Não necessariamente. A exibição depende das permissões do perfil. Você pode criar o plano normalmente pelo botão “Novo Plano”.',
  },
];

function StepBadge({ children, tone = 'teal' }) {
  const classes = tone === 'green'
    ? 'bg-green-500/20 text-green-300'
    : tone === 'orange'
      ? 'bg-orange-500/20 text-orange-300'
      : 'bg-teal-500/20 text-teal-300';
  return (
    <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full font-bold ${classes}`}>
      {children}
    </span>
  );
}

function Tip({ children, tone = 'yellow' }) {
  const styles = tone === 'green'
    ? 'border-green-500/30 bg-green-500/10 text-green-100'
    : tone === 'blue'
      ? 'border-blue-500/30 bg-blue-500/10 text-blue-100'
      : tone === 'orange'
        ? 'border-orange-500/30 bg-orange-500/10 text-orange-100'
        : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-100';
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
      {description && <p className="mt-3 max-w-4xl leading-relaxed text-slate-300">{description}</p>}
    </div>
  );
}

function ExampleBox({ title, children, tone = 'green' }) {
  const styles = tone === 'blue'
    ? 'border-blue-500/30 bg-blue-500/10'
    : tone === 'orange'
      ? 'border-orange-500/30 bg-orange-500/10'
      : 'border-green-500/30 bg-green-500/10';
  return (
    <div className={`rounded-xl border p-5 ${styles}`}>
      <p className="text-sm font-semibold text-white">{title}</p>
      <div className="mt-2 text-sm leading-relaxed text-slate-300">{children}</div>
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

          <Link to="/tutoriais" className="flex items-center gap-2 text-sm text-slate-300 transition-colors hover:text-white">
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
              <span className="text-sm font-medium text-teal-200">Guia do Professor(a) AEE</span>
            </div>

            <h1 className="max-w-4xl text-3xl font-bold leading-tight text-white sm:text-5xl">
              Diário AEE: um roteiro para planejar, registrar, acompanhar e revisar
            </h1>
            <p className="mt-5 max-w-4xl text-base leading-relaxed text-slate-300 sm:text-lg">
              Este guia foi escrito para acompanhar você durante o trabalho — não para transformar sua rotina em uma sequência de termos difíceis. A ideia é simples: mostrar o que fazer, por que cada parte existe, o que vale a pena observar e como escrever registros que realmente ajudem no acompanhamento do estudante.
            </p>

            <div className="mt-6 rounded-2xl border border-teal-500/20 bg-slate-950/35 p-5">
              <p className="text-sm leading-relaxed text-slate-200">
                <strong className="text-white">Você não precisa preencher tudo em uma única vez.</strong> O Dossiê AEE V2 foi organizado para permitir um trabalho por etapas. Leia, observe, converse com os envolvidos, registre o que já está claro e volte às demais partes conforme o acompanhamento avança.
              </p>
            </div>
          </section>

          <section className="mb-10 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-5 sm:p-6">
            <div className="mb-4 flex items-center gap-2">
              <BookOpen size={20} className="text-teal-400" />
              <h2 className="text-lg font-semibold text-white">Ir direto ao que você precisa</h2>
            </div>
            <nav className="grid gap-2 sm:grid-cols-2">
              {navItems.map((item) => (
                <a key={item.href} href={item.href} className="group flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700/50 hover:text-teal-300">
                  <ChevronRight size={16} className="text-slate-500 transition-transform group-hover:translate-x-0.5 group-hover:text-teal-400" />
                  {item.label}
                </a>
              ))}
            </nav>
          </section>

          <section id="acolhida" className="mb-12 scroll-mt-24 rounded-2xl border border-blue-500/20 bg-blue-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Lightbulb}
              kicker="Antes de começar"
              title="Pense no Diário AEE como a memória pedagógica do seu trabalho"
              description="O sistema ajuda a organizar aquilo que você já faz como professor: observar, planejar, atender, conversar com a sala comum, acompanhar respostas do estudante e decidir quais ajustes são necessários."
            />

            <div className="grid gap-4 md:grid-cols-3">
              <ExampleBox title="Planejar" tone="blue">
                Registrar barreiras, potencialidades, objetivos, recursos, estratégias e a organização dos atendimentos.
              </ExampleBox>
              <ExampleBox title="Acompanhar" tone="blue">
                Comparar o que foi planejado com o que o estudante consegue fazer ao longo dos atendimentos.
              </ExampleBox>
              <ExampleBox title="Revisar" tone="blue">
                Ajustar objetivos, apoios e estratégias quando as evidências do cotidiano mostrarem que algo precisa mudar.
              </ExampleBox>
            </div>

            <div className="mt-5">
              <Tip tone="blue">
                <strong>Uma boa regra para escrever:</strong> prefira registrar aquilo que alguém consegue observar. Em vez de “não aprende”, descreva o que acontece: “necessita que a instrução seja dividida em etapas e, com apoio visual, realiza a primeira e a segunda etapa com autonomia”.
              </Tip>
            </div>
          </section>

          <section id="mapa" className="mb-12 scroll-mt-24">
            <SectionTitle
              icon={Target}
              kicker="Visão geral"
              title="O caminho do trabalho, do início ao acompanhamento"
              description="Se você se perder em algum momento, volte a este mapa. Ele mostra a ordem mais confortável para trabalhar no SIGESC."
            />

            <div className="space-y-3">
              {journey.map((item) => (
                <div key={item.number} className="flex gap-4 rounded-xl border border-slate-700/60 bg-slate-800/40 p-4 sm:p-5">
                  <StepBadge>{item.number}</StepBadge>
                  <div>
                    <h3 className="font-semibold text-white">{item.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-slate-300">{item.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section id="tela" className="mb-12 scroll-mt-24 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-6 sm:p-8">
            <SectionTitle
              icon={Eye}
              kicker="Conheça a tela"
              title="Primeiro confira onde você está trabalhando"
              description="Muitos registros incorretos começam apenas porque o professor está olhando outra escola ou outro ano. Faça esta conferência antes de qualquer lançamento."
            />

            <div className="grid gap-4 md:grid-cols-3">
              {screenAreas.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className={`rounded-xl border p-5 ${item.className}`}>
                    <Icon size={22} className={`mb-3 ${item.iconClassName}`} />
                    <h3 className="font-semibold text-white">{item.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-slate-300">{item.text}</p>
                  </div>
                );
              })}
            </div>

            <h3 className="mb-4 mt-7 text-lg font-semibold text-white">As principais abas</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {mainTabs.map(([title, text]) => (
                <div key={title} className="rounded-xl border border-slate-700/60 bg-slate-900/50 p-4">
                  <h4 className="font-semibold text-white">{title}</h4>
                  <p className="mt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>
          </section>

          <section id="plano" className="mb-12 scroll-mt-24 rounded-2xl border border-green-500/20 bg-green-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={FileText}
              kicker="Passo 1"
              title="Garanta que o estudante tenha um Plano de AEE"
              description="O Plano de AEE é o ponto de partida do acompanhamento. Se ele já existe, não crie outro apenas para fazer uma atualização. Abra o plano existente e continue o trabalho pelo Dossiê AEE V2."
            />

            <div className="rounded-xl border border-green-500/20 bg-slate-950/40 p-5">
              <h3 className="font-semibold text-white">Quando o estudante ainda não possui plano</h3>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Planos de AEE</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-green-500/15 px-3 py-2 font-semibold text-green-300">Novo Plano</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Conferir o estudante</span>
                <ChevronRight size={16} className="text-slate-500" />
                <span className="rounded-lg bg-slate-800 px-3 py-2 text-slate-200">Preencher e salvar</span>
              </div>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <ExampleBox title="Se existir a opção “Novo a partir de Modelo”">
                Você pode usá-la para ganhar tempo, mas sempre revise o conteúdo. O modelo é apenas um ponto de partida; objetivos, estratégias e observações precisam representar aquele estudante.
              </ExampleBox>
              <ExampleBox title="Se o plano já possui Dossiê V2">
                Continue as alterações pelo botão <strong>Dossiê V2</strong> ou pelo ícone de editar. Alguns botões podem ficar desabilitados para proteger o histórico do estudante — isso é esperado.
              </ExampleBox>
            </div>
          </section>

          <section id="dossie" className="mb-12 scroll-mt-24 rounded-2xl border border-teal-500/20 bg-teal-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Award}
              kicker="Passo 2"
              title="Abra o Dossiê AEE V2 sem receio: ele foi feito para ser preenchido por etapas"
              description="O Dossiê reúne o planejamento e o histórico do estudante em um único lugar. Na lateral, você encontra as seções que serão usadas ao longo do acompanhamento."
            />

            <div className="grid gap-3 md:grid-cols-2">
              {dossierTabs.map(([title, text]) => (
                <div key={title} className="rounded-xl border border-teal-500/20 bg-slate-900/50 p-4">
                  <h3 className="font-semibold text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <ExampleBox title="Quando aparece “Em trabalho”" tone="orange">
                Existe uma versão que ainda está sendo revisada. Você pode salvar cada seção e continuar depois. Ela ainda não substituiu a versão vigente.
              </ExampleBox>
              <ExampleBox title="Quando aparece “Vigente”">
                Esta é a versão atualmente considerada válida. Se precisar mudar algo mais tarde, abra uma nova versão para revisão; a versão vigente continua preservada enquanto você trabalha na nova.
              </ExampleBox>
            </div>

            <div className="mt-5">
              <Tip>
                <strong>Se aparecer “Plano AEE legado” como fonte efetiva:</strong> não significa que houve erro. Significa apenas que ainda não existe uma versão V2 vigente. Enquanto você revisa a nova versão, o plano anterior continua sendo a referência.
              </Tip>
            </div>
          </section>

          <section id="estudo-caso" className="mb-12 scroll-mt-24 rounded-2xl border border-blue-500/20 bg-blue-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={BookOpen}
              kicker="Passo 3"
              title="Estudo de Caso: escreva sobre o estudante na escola, não apenas sobre um diagnóstico"
              description="Esta seção ajuda a compreender como o estudante participa, aprende, se comunica e enfrenta barreiras no cotidiano escolar. Um registro útil mostra o que foi observado e quais apoios fazem diferença."
            />

            <div className="space-y-4">
              {studyCaseGuides.map((item) => (
                <details key={item.title} className="group rounded-xl border border-blue-500/20 bg-slate-900/50 p-4 open:bg-blue-500/10">
                  <summary className="flex cursor-pointer list-none items-start justify-between gap-4 font-semibold text-white">
                    <span>{item.title}</span>
                    <ChevronRight size={18} className="mt-0.5 flex-shrink-0 text-slate-500 transition-transform group-open:rotate-90 group-open:text-blue-400" />
                  </summary>
                  <div className="mt-4 border-t border-slate-700/50 pt-4">
                    <p className="text-sm font-medium text-blue-200">Pergunte a si mesmo:</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-300">{item.question}</p>
                    <p className="mt-3 text-sm font-medium text-green-200">Exemplo de escrita:</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-300">{item.example}</p>
                  </div>
                </details>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="blue">
                <strong>Evite frases fechadas como “não consegue”, “não sabe” ou “é incapaz”.</strong> Registre em quais condições a dificuldade aparece e quais apoios mudam a resposta do estudante. Isso torna o planejamento muito mais útil.
              </Tip>
            </div>
          </section>

          <section id="paee" className="mb-12 scroll-mt-24 rounded-2xl border border-green-500/20 bg-green-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Target}
              kicker="Passo 4"
              title="PAEE: transforme observações em um plano de ação"
              description="Depois de compreender as barreiras e potencialidades, o PAEE responde a uma pergunta prática: o que o AEE fará para ampliar acesso, participação, autonomia e aprendizagem?"
            />

            <h3 className="mb-4 text-lg font-semibold text-white">Use esta sequência para não se perder:</h3>
            <div className="overflow-hidden rounded-xl border border-slate-700/60">
              {paeeCycle.map(([label, example], index) => (
                <div key={label} className={`grid gap-2 bg-slate-900/50 p-4 sm:grid-cols-[180px_1fr] ${index > 0 ? 'border-t border-slate-700/60' : ''}`}>
                  <span className="text-sm font-semibold text-green-200">{label}</span>
                  <span className="text-sm leading-relaxed text-slate-300">{example}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <ExampleBox title="Materiais e recursos">
                Cite o que realmente será usado: cartões visuais, agenda de rotina, material concreto, teclado ampliado, prancha de comunicação, software, jogos estruturados ou outros recursos adequados ao estudante.
              </ExampleBox>
              <ExampleBox title="Critérios de ajuste">
                Registre quando o planejamento deverá mudar. Ex.: “Se o estudante realizar a atividade de forma independente em quatro encontros consecutivos, reduzir as pistas visuais e ampliar a complexidade da tarefa.”
              </ExampleBox>
            </div>

            <h3 className="mb-3 mt-7 text-lg font-semibold text-white">Ao avaliar apoios, diferencie estas situações</h3>
            <div className="space-y-2">
              {supportStatuses.map(([title, text]) => (
                <div key={title} className="flex gap-3 rounded-xl border border-slate-700/60 bg-slate-900/50 p-4">
                  <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0 text-green-400" />
                  <div>
                    <p className="text-sm font-semibold text-white">{title}</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="green">
                O Dossiê permite avaliar, entre outros, <strong>Tecnologia Assistiva, Comunicação Aumentativa e Alternativa, Profissional de Apoio Escolar, Tradutor/Intérprete de Libras e Guia-intérprete</strong>. Não marque por hábito: registre a situação a partir da necessidade observada e da justificativa pedagógica.
              </Tip>
            </div>
          </section>

          <section id="pei" className="mb-12 scroll-mt-24 rounded-2xl border border-purple-500/20 bg-purple-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={FileText}
              kicker="Passo 5"
              title="PEI: faça a ponte entre o AEE e a participação na sala comum"
              description="Nesta parte, pense menos em “uma atividade separada” e mais em como o estudante terá condições reais de participar das experiências e aprendizagens da turma."
            />

            <div className="space-y-3">
              {peiGuides.map(([title, text]) => (
                <div key={title} className="rounded-xl border border-purple-500/20 bg-slate-900/50 p-4">
                  <h3 className="font-semibold text-white">{title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <ExampleBox title="Exemplo — Educação Infantil" tone="blue">
                “Durante rodas de conversa, antecipar o tema com imagens e oferecer cartões de escolha para favorecer a participação. Nas brincadeiras em pequenos grupos, organizar pares de referência e reduzir estímulos concorrentes quando necessário.”
              </ExampleBox>
              <ExampleBox title="Exemplo — Ensino Fundamental" tone="blue">
                “Em Língua Portuguesa, apresentar textos curtos com apoio de imagem e destacar palavras-chave. Permitir resposta oral nas atividades em que o objetivo principal seja compreensão, registrando gradualmente respostas escritas com apoio.”
              </ExampleBox>
            </div>
          </section>

          <section id="agenda" className="mb-12 scroll-mt-24 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Calendar}
              kicker="Passo 6"
              title="Agenda, vigência e revisão: deixe claro quando e como o atendimento acontecerá"
              description="Essa parte organiza a rotina. Ela ajuda você, a escola e quem acompanha o estudante a compreender a frequência prevista e quando o plano deverá ser revisto."
            />

            <div className="grid gap-4 md:grid-cols-2">
              <ExampleBox title="Carga horária e sessões" tone="blue">
                <p>Informe a carga horária semanal e registre cada sessão no formato mostrado pelo sistema.</p>
                <p className="mt-2 font-medium text-white">Exemplo:</p>
                <p className="mt-1">Terça | 13:30 | 14:20 | Sala de Recursos | Individual</p>
              </ExampleBox>
              <ExampleBox title="Vigência e revisão" tone="blue">
                <p>Registre a data de início e programe a revisão. Se houver data de término prevista, informe-a. A revisão anual não impede que o plano seja revisto antes, quando as necessidades do estudante mudarem.</p>
              </ExampleBox>
            </div>
          </section>

          <section id="vigente" className="mb-12 scroll-mt-24 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={CheckCircle2}
              kicker="Passo 7"
              title="Antes de tornar a versão vigente, use as pendências como uma lista de conferência"
              description="A tela “Visão Geral” informa se a versão ainda possui pontos a revisar. Isso não é uma reprovação do seu trabalho; é uma ajuda para que nenhuma parte importante fique esquecida."
            />

            <div className="space-y-4">
              {[
                ['1', 'Leia a lista de pendências na Visão Geral.'],
                ['2', 'Clique em “Corrigir” para ir diretamente à seção indicada.'],
                ['3', 'Revise os dados. Onde existir a opção “Situação da seção”, marque “Concluído” somente quando aquela parte estiver realmente revisada.'],
                ['4', 'Salve a seção. Faça isso em cada parte necessária.'],
                ['5', 'Volte à Visão Geral. Quando a mensagem indicar que a versão está pronta, clique em “Tornar esta versão Vigente”.'],
              ].map(([number, text]) => (
                <div key={number} className="flex gap-4 rounded-xl border border-amber-500/20 bg-slate-900/50 p-4">
                  <StepBadge tone="orange">{number}</StepBadge>
                  <p className="pt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="orange">
                <strong>Se já existe uma versão vigente e você precisa fazer mudanças:</strong> use “Abrir nova versão para revisão”. Assim, o documento vigente continua preservado enquanto você prepara a atualização. Só depois da conferência a nova versão passa a ser vigente.
              </Tip>
            </div>
          </section>

          <section id="atendimentos" className="mb-12 scroll-mt-24 rounded-2xl border border-orange-500/20 bg-orange-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={CheckSquare}
              kicker="Passo 8"
              title="Atendimentos: registre o que realmente aconteceu"
              description="O plano mostra a intenção; o atendimento mostra a prática. Um bom registro permite que você volte depois e entenda o que foi trabalhado, como o estudante respondeu e qual deve ser o próximo passo."
            />

            <div className="overflow-hidden rounded-xl border border-slate-700/60">
              {attendanceFields.map(([label, text], index) => (
                <div key={label} className={`grid gap-1 bg-slate-900/50 p-4 sm:grid-cols-[190px_1fr] sm:gap-4 ${index > 0 ? 'border-t border-slate-700/60' : ''}`}>
                  <span className="text-sm font-semibold text-orange-200">{label}</span>
                  <span className="text-sm leading-relaxed text-slate-300">{text}</span>
                </div>
              ))}
            </div>

            <details className="mt-6 rounded-xl border border-orange-500/20 bg-orange-500/10 p-4 open:bg-orange-500/15">
              <summary className="cursor-pointer font-semibold text-orange-200">Ver um exemplo completo de registro de atendimento</summary>
              <div className="mt-4 space-y-3 text-sm leading-relaxed text-slate-300">
                <p><strong className="text-white">Objetivo:</strong> seguir uma sequência visual de três etapas com redução progressiva de pistas.</p>
                <p><strong className="text-white">Atividade:</strong> organização do material escolar usando cartões com as etapas “pegar”, “separar” e “guardar”.</p>
                <p><strong className="text-white">Nível de apoio:</strong> mínimo.</p>
                <p><strong className="text-white">Resposta:</strong> realizou as duas primeiras etapas sem ajuda e precisou de uma pista verbal para concluir a terceira.</p>
                <p><strong className="text-white">Próximo encontro:</strong> repetir a sequência com os cartões mais afastados e observar se solicita ajuda espontaneamente quando necessário.</p>
              </div>
            </details>

            <div className="mt-5">
              <Tip>
                <strong>Se houver ausência, registre.</strong> Uma ausência registrada conta a história daquele período e evita que o Diário pareça simplesmente incompleto.
              </Tip>
            </div>
          </section>

          <section id="acompanhar" className="mb-12 scroll-mt-24 rounded-2xl border border-pink-500/20 bg-pink-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Activity}
              kicker="Passo 9"
              title="Use o Dossiê e o Diário Consolidado para enxergar o percurso"
              description="O acompanhamento não acontece apenas quando chega a hora de fazer um relatório. Faça pequenas conferências ao longo do período. Elas ajudam a perceber avanços e necessidades de ajuste com mais naturalidade."
            />

            <div className="grid gap-4 md:grid-cols-2">
              <ExampleBox title="Atendimentos">
                No Dossiê, consulte os registros vinculados ao plano e compare se os objetivos trabalhados estão coerentes com o PAEE.
              </ExampleBox>
              <ExampleBox title="Articulação" tone="blue">
                Consulte os registros construídos com a sala comum e outros participantes. Eles ajudam a verificar se as estratégias combinadas estão chegando ao cotidiano do estudante.
              </ExampleBox>
              <ExampleBox title="Evolução" tone="blue">
                Observe mudanças ao longo do tempo. Não procure apenas “melhorou ou piorou”; procure evidências: mais autonomia, menos pistas, maior participação, novas formas de comunicação ou novas barreiras.
              </ExampleBox>
              <ExampleBox title="Histórico">
                O histórico permite consultar versões anteriores do Dossiê. Isso ajuda a compreender por que um objetivo foi alterado ou quando uma nova estratégia passou a ser adotada.
              </ExampleBox>
            </div>

            <div className="mt-5">
              <Tip tone="blue">
                <strong>Uma pergunta simples para a revisão:</strong> “O que os atendimentos registrados me mostram que eu ainda não sabia quando este plano foi escrito?” A resposta costuma indicar o que deve ser mantido, ampliado ou ajustado.
              </Tip>
            </div>
          </section>

          <section id="pdf" className="mb-12 scroll-mt-24 rounded-2xl border border-purple-500/20 bg-purple-500/5 p-6 sm:p-8">
            <SectionTitle
              icon={Printer}
              kicker="Passo 10"
              title="Visualize antes de gerar o PDF"
              description="O PDF deve refletir o que está vigente. Por isso, antes de imprimir ou salvar, confira a visualização do plano e confirme se a situação apresentada está correta."
            />

            <div className="space-y-4">
              {[
                ['1', 'Na aba “Planos de AEE”, localize o estudante e clique no ícone de visualizar.'],
                ['2', 'Confira o cabeçalho da visualização: situação, versão vigente e informações principais.'],
                ['3', 'Leia os dados do plano antes de gerar o documento.'],
                ['4', 'Clique em “Gerar PDF (Imprimir / Salvar)” quando precisar do documento individual.'],
                ['5', 'Para a visão geral do trabalho, use também o “Diário Consolidado” e confira os registros antes de baixar o PDF completo.'],
              ].map(([number, text]) => (
                <div key={number} className="flex gap-4 rounded-xl border border-slate-700/60 bg-slate-900/50 p-4">
                  <StepBadge>{number}</StepBadge>
                  <p className="pt-1 text-sm leading-relaxed text-slate-300">{text}</p>
                </div>
              ))}
            </div>

            <div className="mt-5">
              <Tip tone="green">
                <strong>Se o plano possui uma versão V2 vigente:</strong> a visualização e o PDF individual devem representar essa versão vigente. Se algo parecer diferente do esperado, volte ao Dossiê e confira a “Visão Geral” antes de emitir o documento.
              </Tip>
            </div>
          </section>

          <section id="duvidas" className="mb-12 scroll-mt-24 rounded-2xl border border-slate-700/60 bg-slate-800/40 p-6 sm:p-8">
            <SectionTitle
              icon={HelpCircle}
              kicker="Quando surgir uma dúvida"
              title="Dúvidas frequentes do professor AEE"
              description="Procure a pergunta mais parecida com a situação que apareceu para você."
            />

            <div className="space-y-3">
              {commonQuestions.map((item) => (
                <details key={item.question} className="group rounded-xl border border-slate-700/60 bg-slate-900/50 p-4 open:border-blue-500/30 open:bg-blue-500/5">
                  <summary className="flex cursor-pointer list-none items-start justify-between gap-4 font-semibold text-white">
                    <span>{item.question}</span>
                    <ChevronRight size={18} className="mt-0.5 flex-shrink-0 text-slate-500 transition-transform group-open:rotate-90 group-open:text-blue-400" />
                  </summary>
                  <p className="mt-3 border-t border-slate-700/50 pt-3 text-sm leading-relaxed text-slate-300">{item.answer}</p>
                </details>
              ))}
            </div>
          </section>

          <section id="checklist" className="mb-12 scroll-mt-24 overflow-hidden rounded-2xl border border-green-500/30 bg-gradient-to-br from-green-500/10 to-teal-500/10 p-6 sm:p-8">
            <SectionTitle
              icon={CheckSquare}
              kicker="Conferência rápida"
              title="Checklist do professor AEE"
              description="Não use como cobrança. Use como lembrete para encerrar a semana ou revisar o trabalho de cada estudante."
            />

            <div className="grid gap-3 md:grid-cols-2">
              {[
                'Conferi Escola/Polo AEE, ano letivo e turma antes de registrar.',
                'Cada estudante atendido possui um Plano de AEE correspondente ao período.',
                'Abri o Dossiê V2 e revisei as informações trazidas do plano anterior.',
                'O Estudo de Caso descreve barreiras, potencialidades, comunicação, participação e apoios observados na escola.',
                'Os objetivos do PAEE são claros e podem ser acompanhados ao longo dos atendimentos.',
                'Os apoios e recursos foram avaliados com justificativa pedagógica.',
                'O PEI está articulado com a participação na sala comum e com o que está sendo ensinado à turma.',
                'Agenda, vigência e data de revisão estão coerentes com a rotina do estudante.',
                'Cada atendimento realizado ou ausência foi registrado.',
                'Os registros mostram o que foi feito, como o estudante respondeu e qual será o próximo passo.',
                'Consultei articulações, evolução e histórico antes de fazer uma revisão importante.',
                'Antes de gerar o PDF, conferi a visualização e a situação vigente do plano.',
              ].map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-xl border border-green-500/20 bg-slate-950/30 p-4">
                  <CheckSquare size={18} className="mt-0.5 flex-shrink-0 text-green-400" />
                  <span className="text-sm leading-relaxed text-slate-200">{item}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-700/60 bg-slate-800/40 p-7 text-center sm:p-9">
            <MessageCircle size={44} className="mx-auto mb-4 text-teal-400" />
            <h2 className="text-xl font-bold text-white">Quando precisar de ajuda, diga em que parte do caminho você está</h2>
            <p className="mx-auto mt-3 max-w-3xl text-sm leading-relaxed text-slate-300">
              Em vez de dizer apenas “não consegui preencher”, informe algo como: “Estou no Dossiê V2, na seção PAEE, e apareceu uma pendência ao tentar concluir”. Isso ajuda a coordenação ou o suporte a entender a situação rapidamente e orientar você com mais segurança.
            </p>
            <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
              <Link to="/tutoriais" className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-700/60">
                <ArrowLeft size={17} /> Voltar aos Tutoriais
              </Link>
              <Link to="/login" className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-teal-500">
                <BookOpen size={17} /> Acessar o SIGESC
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
            <span>Guia do Professor(a) AEE</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
