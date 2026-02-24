import { Link } from 'react-router-dom';
import { 
  ArrowLeft, 
  BookOpen, 
  GraduationCap,
  Users,
  Calendar,
  Target,
  Activity,
  MessageSquare,
  FileText,
  CheckSquare,
  Clock,
  Printer,
  HelpCircle,
  Lightbulb,
  ChevronRight,
  Award
} from 'lucide-react';

export default function TutorialDiárioAEE() {
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
      <main className="pt-24 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          
          {/* Header do Tutorial */}
          <div className="mb-12">
            <div className="inline-flex items-center gap-2 bg-teal-500/10 border border-teal-500/20 rounded-full px-4 py-2 mb-6">
              <Award size={16} className="text-teal-400" />
              <span className="text-teal-300 text-sm font-medium">Professor(a) AEE</span>
            </div>
            
            <h1 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              Guia Prático do Diário AEE
            </h1>
            
            <p className="text-lg text-slate-400">
              Passo a passó completo para o Professor de Atendimento Educacional Especializado
            </p>
          </div>

          {/* Índice */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 mb-10">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <BookOpen size={20} className="text-teal-400" />
              Índice
            </h2>
            <nav className="space-y-2">
              {[
                { href: '#acesso', label: 'Como Acessar' },
                { href: '#abas', label: 'Entendendo as Abas' },
                { href: '#plano', label: 'Passo 1: Criar um Plano de AEE' },
                { href: '#atendimentos', label: 'Passo 2: Registrar Atendimentos' },
                { href: '#diario', label: 'Passo 3: Acompanhar o Diário' },
                { href: '#fluxo', label: 'Resumo: Fluxo de Trabalho' },
                { href: '#faq', label: 'Perguntas Frequentes' },
              ].map((item) => (
                <a 
                  key={item.href}
                  href={item.href} 
                  className="flex items-center gap-2 text-slate-300 hover:text-teal-400 transition-colors py-1"
                >
                  <ChevronRight size={16} className="text-slate-600" />
                  {item.label}
                </a>
              ))}
            </nav>
          </div>

          {/* Seção: Como Acessar */}
          <section id="acesso" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-teal-500/20 rounded-lg">
                  <GraduationCap size={24} className="text-teal-400" />
                </div>
                Como Acessar
              </h2>
              
              <ol className="space-y-4 text-slate-300">
                <li className="flex gap-3">
                  <span className="flex-shrink-0 w-8 h-8 bg-teal-500/20 text-teal-400 rounded-full flex items-center justify-center font-bold">1</span>
                  <span>Faça login no SIGESC com seu usuário e senha</span>
                </li>
                <li className="flex gap-3">
                  <span className="flex-shrink-0 w-8 h-8 bg-teal-500/20 text-teal-400 rounded-full flex items-center justify-center font-bold">2</span>
                  <span>No <strong className="text-white">Menu de Administração</strong>, clique em <strong className="text-white">"Diário AEE"</strong></span>
                </li>
                <li className="flex gap-3">
                  <span className="flex-shrink-0 w-8 h-8 bg-teal-500/20 text-teal-400 rounded-full flex items-center justify-center font-bold">3</span>
                  <span>Selecione sua <strong className="text-white">escola</strong> no campo superior</span>
                </li>
                <li className="flex gap-3">
                  <span className="flex-shrink-0 w-8 h-8 bg-teal-500/20 text-teal-400 rounded-full flex items-center justify-center font-bold">4</span>
                  <span>Confirme se o <strong className="text-white">ano letivo</strong> está correto</span>
                </li>
              </ol>
            </div>
          </section>

          {/* Seção: Entendendo as Abas */}
          <section id="abas" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-purple-500/20 rounded-lg">
                  <BookOpen size={24} className="text-purple-400" />
                </div>
                Entendendo as Abas
              </h2>
              
              <p className="text-slate-400 mb-6">O Diário AEE possui <strong className="text-white">4 abas</strong> na parte inferior da tela:</p>
              
              <div className="grid gap-4">
                {[
                  { icon: Users, color: 'blue', title: 'Estudantes AEE', desc: 'Ver todos os alunos que você atende' },
                  { icon: FileText, color: 'green', title: 'Planos de AEE', desc: 'Criar e gerenciar os planos de cada aluno' },
                  { icon: CheckSquare, color: 'orange', title: 'Atendimentos', desc: 'Registrar cada sessão realizada' },
                  { icon: Calendar, color: 'pink', title: 'Diário', desc: 'Visualizar o consolidado e gerar PDF' },
                ].map((item, index) => {
                  const Icon = item.icon;
                  return (
                    <div key={index} className={`bg-${item.color}-500/10 border border-${item.color}-500/20 rounded-xl p-4 flex items-center gap-4`}>
                      <div className={`p-2 bg-${item.color}-500/20 rounded-lg`}>
                        <Icon size={20} className={`text-${item.color}-400`} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">{item.title}</h3>
                        <p className="text-sm text-slate-400">{item.desc}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          {/* Seção: Criar Plano */}
          <section id="plano" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-green-500/20 rounded-lg">
                  <FileText size={24} className="text-green-400" />
                </div>
                Passo 1: Criar um Plano de AEE
              </h2>
              
              <p className="text-slate-400 mb-6">
                O Plano de AEE é o documento que organiza todo o atendimento do estudante. 
                Você deve criar <strong className="text-white">um plano para cada aluno</strong> que atende.
              </p>

              <div className="bg-slate-900/50 rounded-xl p-4 mb-6">
                <h3 className="font-semibold text-white mb-3">Como criar:</h3>
                <ol className="space-y-2 text-slate-300 text-sm">
                  <li>1. Clique na aba <strong className="text-green-400">"Planos de AEE"</strong></li>
                  <li>2. Clique no botão <strong className="text-green-400">"Novo Plano de AEE"</strong></li>
                  <li>3. Preencha as informações em cada seção</li>
                </ol>
              </div>

              {/* Subsecoes do Plano */}
              <div className="space-y-6">
                
                {/* Seção 1 */}
                <div className="border-l-4 border-blue-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Users size={18} className="text-blue-400" />
                    Seção 1: Identificação do Estudante
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Aluno:</strong> Selecione o nome do estudante na lista</p>
                    <p><strong className="text-slate-200">Público-Alvo (PAEE):</strong> Escolha a categoria (Ex: TEA, Deficiência Intelectual, etc.)</p>
                    <p><strong className="text-slate-200">Turma de Origem:</strong> Informe a turma regular do aluno (Ex: 3o Ano A)</p>
                    <p><strong className="text-slate-200">Professor Regente:</strong> Nome do professor da sala regular</p>
                    <p><strong className="text-slate-200">Justificativa Pedagógica:</strong> Descreva as barreiras e necessidades de apoio</p>
                  </div>
                  <div className="mt-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                    <p className="text-sm text-yellow-300 flex items-start gap-2">
                      <Lightbulb size={16} className="flex-shrink-0 mt-0.5" />
                      <span><strong>Dica:</strong> Não mencione CID ou laudo médico na justificativa - foque no que o aluno precisa para aprender.</span>
                    </p>
                  </div>
                </div>

                {/* Seção 2 */}
                <div className="border-l-4 border-purple-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Calendar size={18} className="text-purple-400" />
                    Seção 2: Vigência do Plano
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Data de Elaboração:</strong> Data em que você está criando o plano</p>
                    <p><strong className="text-slate-200">Período de Vigência:</strong> Por quanto tempo este plano vale (bimestre, semestre ou ano)</p>
                    <p><strong className="text-slate-200">Próxima Revisão:</strong> Quando você vai revisar e atualizar este plano</p>
                  </div>
                  <div className="mt-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                    <p className="text-sm text-yellow-300 flex items-start gap-2">
                      <Lightbulb size={16} className="flex-shrink-0 mt-0.5" />
                      <span><strong>Dica:</strong> E recomendado revisar o plano pelo menos a cada bimestre para ajustar as estratégias.</span>
                    </p>
                  </div>
                </div>

                {/* Seção 3 */}
                <div className="border-l-4 border-cyan-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity size={18} className="text-cyan-400" />
                    Seção 3: Linha de Base (Situação Inicial)
                  </h3>
                  <p className="text-sm text-slate-400 mb-3">
                    Aqui você registra <strong className="text-white">como o aluno está HOJE</strong>, antes de iniciar as intervenções. Isso permite medir o progresso depois.
                  </p>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Situação Atual:</strong> Como o estudante está hoje em relação a aprendizagem?</p>
                    <p><strong className="text-slate-200">Potencialidades:</strong> Quais são os pontos fortes do aluno? Do que ele gosta?</p>
                    <p><strong className="text-slate-200">Dificuldades Observadas:</strong> Quais são as principais barreiras que ele enfrenta?</p>
                    <p><strong className="text-slate-200">Formas de Comunicação:</strong> Como o aluno se comunica e participa das atividades?</p>
                  </div>
                  <div className="mt-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                    <p className="text-sm text-yellow-300 flex items-start gap-2">
                      <Lightbulb size={16} className="flex-shrink-0 mt-0.5" />
                      <span><strong>Dica:</strong> Seja específico! Em vez de "tem dificuldade em português", escreva "ainda não reconhece todas as letras do alfabeto".</span>
                    </p>
                  </div>
                </div>

                {/* Seção 4 */}
                <div className="border-l-4 border-orange-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Clock size={18} className="text-orange-400" />
                    Seção 4: Cronograma de Atendimento
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Dias de Atendimento:</strong> Marque os dias da semana que o aluno e atendido</p>
                    <p><strong className="text-slate-200">Modalidade:</strong> Individual, Pequeno Grupo, Coensino ou Mista</p>
                    <p><strong className="text-slate-200">Horário Início/Fim:</strong> Horário do atendimento</p>
                    <p><strong className="text-slate-200">Carga Horaria Semanal:</strong> Total de horas por semana (Ex: 4 horas)</p>
                    <p><strong className="text-slate-200">Local:</strong> Onde acontecé o atendimento</p>
                  </div>
                </div>

                {/* Seção 5 */}
                <div className="border-l-4 border-green-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Target size={18} className="text-green-400" />
                    Seção 5: Objetivos e Barreiras
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Barreiras Identificadas:</strong> Liste as barreiras que impedem a participação e aprendizagem (uma por linha)</p>
                    <p><strong className="text-slate-200">Objetivos do Atendimento:</strong> O que você quer que o aluno alcance? Seja específico!</p>
                    <p><strong className="text-slate-200">Recursos de Acessibilidade:</strong> Quais recursos serão usados?</p>
                  </div>
                  <div className="mt-3 bg-green-500/10 border border-green-500/20 rounded-lg p-3">
                    <p className="text-sm text-green-300 mb-2"><strong>Exemplo de objetivos:</strong></p>
                    <p className="text-sm text-slate-400">❌ Evite: "Melhorar a leitura"</p>
                    <p className="text-sm text-slate-400">✅ Prefira: "Reconhecer e nomear todas as letras do alfabeto até o final do bimestre"</p>
                  </div>
                </div>

                {/* Seção 6 */}
                <div className="border-l-4 border-pink-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Activity size={18} className="text-pink-400" />
                    Seção 6: Estratégias de Acompanhamento
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Indicadores de Progresso:</strong> Como você vai saber se o aluno está avançando?</p>
                    <p><strong className="text-slate-200">Frequência de Revisão:</strong> De quanto em quanto tempo vai revisar o plano</p>
                    <p><strong className="text-slate-200">Critérios para Ajustar:</strong> Em que situações vai mudar as estratégias?</p>
                  </div>
                </div>

                {/* Seção 7 */}
                <div className="border-l-4 border-teal-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <MessageSquare size={18} className="text-teal-400" />
                    Seção 7: Articulação com Sala Comum
                  </h3>
                  <p className="text-sm text-slate-400 mb-3">Esta seção conecta o AEE com a sala de aula regular.</p>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-slate-200">Orientações para Sala Comum:</strong> Orientações gerais para o professor regente</p>
                    <p><strong className="text-slate-200">Combinados com Professor Regente:</strong> Acordos específicos entre você com o professor da sala regular</p>
                    <p><strong className="text-slate-200">Adaptações por Componente:</strong> Adaptações específicas por disciplina</p>
                    <p><strong className="text-slate-200">Adequações Curriculares:</strong> Ajustes no currículo para garantir o acesso a aprendizagem</p>
                  </div>
                </div>

                {/* Seção 8 */}
                <div className="border-l-4 border-slate-500 pl-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <CheckSquare size={18} className="text-slate-400" />
                    Seção 8: Status do Plano
                  </h3>
                  <div className="space-y-2 text-sm text-slate-300">
                    <p><strong className="text-yellow-400">Rascunho:</strong> Ainda está em elaboração</p>
                    <p><strong className="text-green-400">Ativo:</strong> Plano em vigor, sendo executado</p>
                    <p><strong className="text-orange-400">Em Revisão:</strong> Está sendo atualizado</p>
                    <p><strong className="text-red-400">Encerrado:</strong> Plano finalizado</p>
                  </div>
                </div>

              </div>

              {/* Finalizar */}
              <div className="mt-6 bg-green-500/10 border border-green-500/20 rounded-xl p-4">
                <h3 className="font-semibold text-white mb-3">Finalizando o Plano:</h3>
                <ol className="space-y-2 text-sm text-slate-300">
                  <li>1. Revise todas as informações</li>
                  <li>2. Clique em <strong className="text-green-400">"Salvar"</strong></li>
                  <li>3. O plano aparecerá na lista da aba "Planos de AEE"</li>
                </ol>
              </div>
            </div>
          </section>

          {/* Seção: Registrar Atendimentos */}
          <section id="atendimentos" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-orange-500/20 rounded-lg">
                  <CheckSquare size={24} className="text-orange-400" />
                </div>
                Passo 2: Registrar Atendimentos
              </h2>
              
              <p className="text-slate-400 mb-6">
                Após criar o plano, você deve registrar <strong className="text-white">cada sessão de atendimento</strong> realizada.
              </p>

              <div className="bg-slate-900/50 rounded-xl p-4 mb-6">
                <h3 className="font-semibold text-white mb-3">Como registrar:</h3>
                <ol className="space-y-2 text-slate-300 text-sm">
                  <li>1. Clique na aba <strong className="text-orange-400">"Atendimentos"</strong></li>
                  <li>2. Clique em <strong className="text-orange-400">"Registrar Atendimento"</strong></li>
                  <li>3. Preencha os campos</li>
                  <li>4. Clique em <strong className="text-orange-400">"Salvar"</strong></li>
                </ol>
              </div>

              <div className="space-y-3 text-sm">
                <h3 className="font-semibold text-white mb-3">Campos do atendimento:</h3>
                {[
                  { label: 'Plano/Estudante', desc: 'Selecione o aluno que foi atendido' },
                  { label: 'Data', desc: 'Data do atendimento' },
                  { label: 'Horário', desc: 'Início e fim da sessão' },
                  { label: 'Presença', desc: 'O aluno compareceu? Se nao, informe o motivo' },
                  { label: 'Objetivo Trabalhado', desc: 'Qual objetivo do plano foi trabalhado hoje?' },
                  { label: 'Atividade Realizada', desc: 'Descreva o que foi feito na sessão' },
                  { label: 'Recursos Utilizados', desc: 'Quais materiais/recursos foram usados?' },
                  { label: 'Nivel de Apoio', desc: 'Quanto apoio o aluno precisou? (Independente, Mínimo, Moderado ou Total)' },
                  { label: 'Resposta do Estudante', desc: 'Como o aluno reagiu? Participou bem?' },
                  { label: 'Evidências', desc: 'Registre observações sobre o progresso' },
                  { label: 'Próximo Atendimento', desc: 'O que será trabalhado na próxima sessão?' },
                ].map((item, index) => (
                  <div key={index} className="flex gap-2 text-slate-300">
                    <span className="text-slate-200 font-medium min-w-[160px]">{item.label}:</span>
                    <span className="text-slate-400">{item.desc}</span>
                  </div>
                ))}
              </div>

              <div className="mt-6 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                <p className="text-sm text-yellow-300 flex items-start gap-2">
                  <Lightbulb size={16} className="flex-shrink-0 mt-0.5" />
                  <span><strong>Dica:</strong> Registre o atendimento logo após a sessão, enquanto as informações estão frescas na memória!</span>
                </p>
              </div>
            </div>
          </section>

          {/* Seção: Acompanhar Diário */}
          <section id="diario" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-pink-500/20 rounded-lg">
                  <Calendar size={24} className="text-pink-400" />
                </div>
                Passo 3: Acompanhar o Diário
              </h2>
              
              <p className="text-slate-400 mb-6">
                A aba <strong className="text-white">"Diário"</strong> mostra o consolidado de todos os atendimentos.
              </p>

              <div className="grid md:grid-cols-2 gap-4 mb-6">
                <div className="bg-slate-900/50 rounded-xl p-4">
                  <h3 className="font-semibold text-white mb-3">O que você encontra:</h3>
                  <ul className="space-y-2 text-sm text-slate-300">
                    <li>• Resumo dos atendimentos por período</li>
                    <li>• Estatísticas de frequência</li>
                    <li>• Visão geral do progresso dos alunos</li>
                  </ul>
                </div>
                <div className="bg-slate-900/50 rounded-xl p-4">
                  <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
                    <Printer size={18} className="text-pink-400" />
                    Gerar PDF:
                  </h3>
                  <ol className="space-y-2 text-sm text-slate-300">
                    <li>1. Clique na aba "Diário"</li>
                    <li>2. Clique em <strong className="text-pink-400">"Gerar PDF"</strong></li>
                    <li>3. O sistema criara um documento com todos os registros</li>
                  </ol>
                </div>
              </div>

              <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                <p className="text-sm text-yellow-300 flex items-start gap-2">
                  <Lightbulb size={16} className="flex-shrink-0 mt-0.5" />
                  <span><strong>Dica:</strong> Gere o PDF mensalmente para ter um arquivo de acompanhamento e para reuniões pedagógicas.</span>
                </p>
              </div>
            </div>
          </section>

          {/* Seção: Fluxo de Trabalho */}
          <section id="fluxo" className="mb-12">
            <div className="bg-gradient-to-br from-teal-500/10 to-blue-500/10 border border-teal-500/30 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-teal-500/20 rounded-lg">
                  <Activity size={24} className="text-teal-400" />
                </div>
                Resumo: Fluxo de Trabalho
              </h2>
              
              <div className="space-y-4">
                {[
                  { num: '1', title: 'CRIAR PLANO DE AEE', desc: '(uma vez por aluno/período)', color: 'green' },
                  { num: '2', title: 'REGISTRAR ATENDIMENTOS', desc: '(após cada sessão)', color: 'orange' },
                  { num: '3', title: 'ACOMPANHAR DIARIO', desc: '(semanalmente)', color: 'pink' },
                  { num: '4', title: 'GERAR PDF', desc: '(mensalmente ou quando necessário)', color: 'purple' },
                  { num: '5', title: 'REVISAR PLANO', desc: '(conforme frequência definida)', color: 'blue' },
                ].map((item, index) => (
                  <div key={index} className="flex items-center gap-4">
                    <div className={`w-10 h-10 bg-${item.color}-500/20 text-${item.color}-400 rounded-full flex items-center justify-center font-bold text-lg`}>
                      {item.num}
                    </div>
                    <div className="flex-1 bg-slate-800/50 rounded-lg p-3">
                      <span className="text-white font-medium">{item.title}</span>
                      <span className="text-slate-400 text-sm ml-2">{item.desc}</span>
                    </div>
                    {index < 4 && (
                      <div className="text-slate-600">↓</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Seção: FAQ */}
          <section id="faq" className="mb-12">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <div className="p-2 bg-blue-500/20 rounded-lg">
                  <HelpCircle size={24} className="text-blue-400" />
                </div>
                Perguntas Frequentes
              </h2>
              
              <div className="space-y-4">
                {[
                  { 
                    q: 'Preciso criar um plano novo a cada bimestre?',
                    a: 'Não necessariamente. Você pode editar o plano existente e atualizar as informações. Crie um novo apenas se houver mudanças significativas ou no início de um novo ano letivo.'
                  },
                  { 
                    q: 'E se o aluno faltar?',
                    a: 'Registre o atendimento normalmente, marque "Ausente" no campo de presenca e informe o motivo da falta.'
                  },
                  { 
                    q: 'Posso editar um atendimento já registrado?',
                    a: 'Sim! Na lista de atendimentos, clique no ícone de editar (lápis) ao lado do registro.'
                  },
                  { 
                    q: 'O que faco se o aluno mudar de turma?',
                    a: 'Edite o plano e atualize as informações de turma e professor regente.'
                  },
                ].map((item, index) => (
                  <div key={index} className="bg-slate-900/50 rounded-xl p-4">
                    <h3 className="font-semibold text-white mb-2 flex items-start gap-2">
                      <span className="text-blue-400">P:</span>
                      {item.q}
                    </h3>
                    <p className="text-slate-400 text-sm flex items-start gap-2">
                      <span className="text-green-400">R:</span>
                      {item.a}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Ajuda */}
          <section className="mb-12">
            <div className="bg-gradient-to-br from-slate-800 to-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
              <HelpCircle size={48} className="text-teal-400 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-white mb-2">Precisa de mais ajuda?</h3>
              <p className="text-slate-400 mb-4">
                Entre em contato com a coordenação pedagógica ou o suporte técnico da sua rede de ensino.
              </p>
              <Link
                to="/tutoriais"
                className="inline-flex items-center gap-2 text-teal-400 hover:text-teal-300 transition-colors"
              >
                <ArrowLeft size={18} />
                Voltar aos Tutoriais
              </Link>
            </div>
          </section>

        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <span>© {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar</span>
          </div>
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <span>Desenvolvido por</span>
            <a 
              href="https://www.facebook.com/prof.gutenbergbarroso" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 transition-colors font-medium"
            >
              Gutenberg Barroso
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
