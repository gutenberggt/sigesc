import { Link } from 'react-router-dom';
import {
  GraduationCap,
  ArrowLeft,
  CheckCircle,
  AlertCircle,
  Info,
  ChevronRight,
  Users,
  UserCheck,
  School,
  ClipboardList,
  FileText
} from 'lucide-react';

export default function TutorialTransferencia() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900" data-testid="tutorial-transferencia-page">
      {/* Header */}
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
            <Link
              to="/tutoriais"
              className="flex items-center gap-2 text-slate-300 hover:text-white transition-colors"
              data-testid="tutorial-back-link"
            >
              <ArrowLeft size={18} />
              <span className="text-sm">Voltar aos Tutoriais</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">

          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-slate-400 mb-8">
            <Link to="/" className="hover:text-white transition-colors">Início</Link>
            <ChevronRight size={14} />
            <Link to="/tutoriais" className="hover:text-white transition-colors">Tutoriais</Link>
            <ChevronRight size={14} />
            <span className="text-green-400">Secretários</span>
            <ChevronRight size={14} />
            <span className="text-white">Transferência entre escolas</span>
          </nav>

          {/* Title */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-gradient-to-br from-green-500 to-green-700">
                <Users className="h-6 w-6 text-white" />
              </div>
              <div>
                <span className="text-green-400 text-sm font-medium">Tutorial para Secretários</span>
                <h1 className="text-3xl font-bold text-white">Transferir um Aluno de uma Escola para Outra</h1>
              </div>
            </div>
            <p className="text-slate-400 text-lg">
              Tutorial rápido: a transferência acontece em <strong className="text-white">2 etapas</strong> —
              primeiro você marca o aluno como <strong className="text-white">Transferido</strong> na escola de
              origem e, em seguida, o <strong className="text-white">Matricula</strong> na escola de destino.
            </p>
          </div>

          {/* Aviso de pré-requisito */}
          <div className="flex items-start gap-3 bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 mb-10">
            <Info className="text-blue-400 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <p className="text-blue-200 font-medium">Antes de começar</p>
              <p className="text-blue-200/70 text-sm mt-1">
                A ação <strong>"Transferir"</strong> só fica disponível para alunos com status
                <strong> "Ativo"</strong>. Você precisa ter perfil de <strong>Secretário</strong> ou
                <strong> Administrador</strong>.
              </p>
            </div>
          </div>

          {/* Steps */}
          <div className="space-y-12">

            {/* Etapa 1 */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">1</span>
                <School size={22} className="text-green-400" />
                Etapa 1 — Marcar o aluno como "Transferido"
              </h2>
              <ol className="space-y-4 text-slate-300 list-none">
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">1.1</strong> No menu, acesse <strong className="text-white">Alunos</strong> (Gestão de Alunos).
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">1.2</strong> Use a <strong className="text-white">busca</strong> ou os filtros para localizar o aluno e clique em <strong className="text-blue-400">"Editar"</strong>.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">1.3</strong> Abra o seletor de <strong className="text-white">Ações de Vínculo</strong> e escolha a opção <strong className="text-blue-400">🔄 Transferir</strong>.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">1.4</strong> Informe o <strong className="text-white">motivo</strong> da transferência (opcional) e confirme.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">1.5</strong> Pronto: o status do aluno muda para <span className="inline-block bg-yellow-100 text-yellow-800 text-xs font-medium px-2 py-0.5 rounded">Transferido</span> e a matrícula na escola de origem é encerrada.
                </li>
              </ol>

              <div className="mt-6 space-y-5">
                <figure>
                  <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                    <img src="/tutorials/transf-1-lista.png" alt="Tela de Alunos com a escola selecionada" className="w-full" />
                  </div>
                  <figcaption className="text-slate-400 text-sm mt-2 text-center">Tela <strong className="text-slate-200">Alunos</strong>: selecione a escola e clique em <strong className="text-slate-200">Editar</strong>.</figcaption>
                </figure>
                <figure>
                  <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                    <img src="/tutorials/transf-2-acoes.png" alt="Aba Turma/Observações com o seletor de Ação" className="w-full" />
                  </div>
                  <figcaption className="text-slate-400 text-sm mt-2 text-center">Na aba <strong className="text-slate-200">Turma/Observações</strong>, abra o seletor <strong className="text-slate-200">Ação</strong> e escolha <strong className="text-slate-200">Transferir</strong>.</figcaption>
                </figure>
                <figure>
                  <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                    <img src="/tutorials/transf-3-transferir.png" alt="Modal Transferir Aluno" className="w-full" />
                  </div>
                  <figcaption className="text-slate-400 text-sm mt-2 text-center">Informe o motivo e a data, depois clique em <strong className="text-slate-200">Confirmar Transferência</strong>.</figcaption>
                </figure>
              </div>
            </section>

            {/* Etapa 2 */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">2</span>
                <UserCheck size={22} className="text-green-400" />
                Etapa 2 — Matricular na escola de destino
              </h2>
              <ol className="space-y-4 text-slate-300 list-none">
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">2.1</strong> Ainda na ficha do aluno (ou localizando-o novamente em <strong className="text-white">Alunos</strong>), abra as <strong className="text-white">Ações de Vínculo</strong>.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">2.2</strong> Como o aluno está "Transferido", a ação <strong className="text-blue-400">✅ Matricular</strong> ficará disponível. Selecione-a.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">2.3</strong> Escolha a <strong className="text-white">Escola de destino</strong>, a <strong className="text-white">Turma</strong> e o <strong className="text-white">Ano letivo</strong>.
                </li>
                <li className="bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
                  <strong className="text-white">2.4</strong> Confirme. O sistema gera uma <strong className="text-white">nova matrícula</strong> na escola de destino e o status volta para <span className="inline-block bg-green-100 text-green-800 text-xs font-medium px-2 py-0.5 rounded">Ativo</span>.
                </li>
              </ol>

              <figure className="mt-6">
                <div className="rounded-lg overflow-hidden border border-slate-700 shadow-xl">
                  <img src="/tutorials/transf-4-matricular.png" alt="Modal Matricular Aluno com escola, turma e ano letivo de destino" className="w-full" />
                </div>
                <figcaption className="text-slate-400 text-sm mt-2 text-center">No modal <strong className="text-slate-200">Matricular Aluno</strong>, escolha a <strong className="text-slate-200">Escola de Destino</strong>, a <strong className="text-slate-200">Turma de Destino</strong> e o <strong className="text-slate-200">Ano Letivo</strong>, e clique em <strong className="text-slate-200">Confirmar Matrícula</strong>.</figcaption>
              </figure>

              <div className="flex items-start gap-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 mt-6">
                <AlertCircle className="text-yellow-400 flex-shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="text-yellow-200 font-medium">Transferência para fora da rede</p>
                  <p className="text-yellow-200/70 text-sm mt-1">
                    Se o aluno saiu para uma escola que <strong>não pertence à rede</strong> (outro município
                    ou rede privada/estadual), basta concluir a <strong>Etapa 1</strong>. Ele permanece com
                    status "Transferido" e aparece como <strong>"Fora da rede"</strong> nos relatórios.
                  </p>
                </div>
              </div>
            </section>

            {/* Conferência */}
            <section className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
                <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold">3</span>
                <ClipboardList size={22} className="text-green-400" />
                Como conferir se deu certo
              </h2>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Abra a ficha do aluno e veja o <strong className="text-white">Histórico de Movimentações</strong>: devem aparecer os registros <strong>"Transf. Saída"</strong> e, quando matriculado, <strong>"Transf. Entrada"</strong>.</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Na escola de destino, o aluno aparecerá na <strong className="text-white">turma escolhida</strong> com uma nova matrícula.</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>No PDF de <strong className="text-white">Acompanhamento Bolsa Família</strong>, alunos transferidos aparecem na seção final, indicando a escola de destino ou "Fora da rede".</span>
                </li>
              </ul>
            </section>

            {/* Resumo */}
            <section className="bg-gradient-to-br from-green-500/10 to-blue-500/10 border border-green-500/30 rounded-2xl p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-3">
                <CheckCircle className="text-green-400" size={28} />
                Resumo
              </h2>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span><strong className="text-white">Etapa 1:</strong> Alunos → Editar → Ações de Vínculo → <strong>Transferir</strong> (status vira "Transferido").</span>
                </li>
                <li className="flex items-start gap-2">
                  <ChevronRight className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span><strong className="text-white">Etapa 2:</strong> Ações de Vínculo → <strong>Matricular</strong> → escolha escola, turma e ano (status volta para "Ativo").</span>
                </li>
                <li className="flex items-start gap-2">
                  <FileText className="text-green-400 flex-shrink-0 mt-1" size={16} />
                  <span>Saída para fora da rede? Faça só a Etapa 1.</span>
                </li>
              </ul>
            </section>

          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between mt-12 pt-8 border-t border-slate-700/50">
            <Link
              to="/tutoriais"
              className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft size={18} />
              Voltar aos Tutoriais
            </Link>
          </div>

        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="text-slate-400 text-sm">
            © {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar
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
