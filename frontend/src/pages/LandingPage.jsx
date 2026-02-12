import { useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  GraduationCap, 
  Users, 
  School, 
  BarChart3, 
  Shield, 
  Clock, 
  CheckCircle2, 
  ArrowRight,
  MessageCircle,
  Mail,
  Smartphone,
  BookOpen,
  ClipboardList,
  Calendar,
  FileText,
  Bell,
  Cloud,
  Zap,
  Star
} from 'lucide-react';

export default function LandingPage() {
  const [hoveredFeature, setHoveredFeature] = useState(null);

  const features = [
    {
      icon: Users,
      title: 'Gestão de Alunos(as)',
      description: 'Cadastro completo, histórico escolar, documentos e acompanhamento individual de cada estudante.',
      color: 'blue'
    },
    {
      icon: School,
      title: 'Gestão de Escolas',
      description: 'Administre múltiplas unidades escolares com controle centralizado e visão unificada.',
      color: 'green'
    },
    {
      icon: BookOpen,
      title: 'Turmas e Disciplinas',
      description: 'Organize turmas, componentes curriculares e alocação de professores de forma intuitiva.',
      color: 'purple'
    },
    {
      icon: ClipboardList,
      title: 'Notas e Frequência',
      description: 'Lançamento simplificado de notas e controle de presença com relatórios automáticos.',
      color: 'orange'
    },
    {
      icon: Calendar,
      title: 'Calendário Escolar',
      description: 'Gerencie o ano letivo, feriados, eventos e atividades em um calendário integrado.',
      color: 'pink'
    },
    {
      icon: FileText,
      title: 'Documentos e Relatórios',
      description: 'Geração automática de boletins, fichas individuais, atas e declarações em PDF.',
      color: 'cyan'
    },
    {
      icon: Bell,
      title: 'Notificações em Tempo Real',
      description: 'Sistema de avisos e comunicação instantânea entre gestores, professores e secretaria.',
      color: 'yellow'
    },
    {
      icon: Cloud,
      title: 'Funciona Offline',
      description: 'Continue trabalhando mesmo sem internet. Sincronização automática quando reconectar.',
      color: 'indigo'
    }
  ];

  const benefits = [
    'Redução de 70% no tempo de processos administrativos',
    'Eliminação de papelada e arquivos físicos',
    'Acesso de qualquer lugar, a qualquer momento',
    'Relatórios gerenciais em tempo real',
    'Segurança de dados com backup automático',
    'Suporte técnico especializado'
  ];

  const stats = [
    { value: '5000+', label: 'Alunos Gerenciados' },
    { value: '15+', label: 'Escolas Atendidas' },
    { value: '99.9%', label: 'Disponibilidade' },
    { value: '24/7', label: 'Suporte' }
  ];

  const whatsappNumber = '5594984223453';
  const whatsappMessage = encodeURIComponent('Olá! Gostaria de saber mais sobre o SIGESC - Sistema de Gestão Escolar.');

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-slate-900/80 backdrop-blur-md border-b border-slate-700/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-500 to-blue-700 p-2 rounded-xl">
                <GraduationCap className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">SIGESC</h1>
                <p className="text-xs text-slate-400">Sistema de Gestão Escolar</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Link
                to="/tutoriais"
                className="hidden sm:flex items-center gap-2 text-slate-300 hover:text-blue-400 transition-colors"
              >
                <BookOpen size={18} />
                <span className="text-sm">Tutoriais</span>
              </Link>
              <a 
                href={`https://wa.me/${whatsappNumber}?text=${whatsappMessage}`}
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:flex items-center gap-2 text-slate-300 hover:text-green-400 transition-colors"
              >
                <MessageCircle size={18} />
                <span className="text-sm">Fale Conosco</span>
              </a>
              <Link
                to="/login"
                className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white px-5 py-2 rounded-lg font-medium transition-all duration-300 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40"
              >
                Acessar Sistema
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-2 mb-6">
              <Zap size={16} className="text-blue-400" />
              <span className="text-blue-300 text-sm font-medium">Modernize sua gestão escolar</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white mb-6 leading-tight">
              Gestão Escolar
              <span className="block bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-500 text-transparent bg-clip-text">
                Simples e Eficiente
              </span>
            </h1>
            
            <p className="text-lg sm:text-xl text-slate-400 max-w-3xl mx-auto mb-10 leading-relaxed">
              O SIGESC é a solução completa para secretarias de educação e escolas que buscam 
              <strong className="text-slate-200"> automatizar processos</strong>, 
              <strong className="text-slate-200"> reduzir burocracia</strong> e 
              <strong className="text-slate-200"> ter controle total</strong> da rede de ensino.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href={`https://wa.me/${whatsappNumber}?text=${whatsappMessage}`}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-3 bg-green-600 hover:bg-green-500 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all duration-300 shadow-lg shadow-green-500/25 hover:shadow-green-500/40"
              >
                <MessageCircle size={24} />
                Solicitar Demonstração
                <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
              </a>
              <Link
                to="/login"
                className="flex items-center gap-2 text-slate-300 hover:text-white px-6 py-4 rounded-xl font-medium transition-colors border border-slate-700 hover:border-slate-600"
              >
                <Shield size={20} />
                Já sou cliente - Acessar
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-12 px-4 sm:px-6 lg:px-8 border-y border-slate-700/50 bg-slate-800/30">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, index) => (
              <div key={index} className="text-center">
                <div className="text-3xl sm:text-4xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 text-transparent bg-clip-text mb-1">
                  {stat.value}
                </div>
                <div className="text-slate-400 text-sm sm:text-base">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              Tudo que você precisa em um só lugar
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              Funcionalidades completas para gerenciar toda a rede de ensino municipal
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              const colorClasses = {
                blue: 'from-blue-500 to-blue-700 group-hover:shadow-blue-500/30',
                green: 'from-green-500 to-green-700 group-hover:shadow-green-500/30',
                purple: 'from-purple-500 to-purple-700 group-hover:shadow-purple-500/30',
                orange: 'from-orange-500 to-orange-700 group-hover:shadow-orange-500/30',
                pink: 'from-pink-500 to-pink-700 group-hover:shadow-pink-500/30',
                cyan: 'from-cyan-500 to-cyan-700 group-hover:shadow-cyan-500/30',
                yellow: 'from-yellow-500 to-yellow-700 group-hover:shadow-yellow-500/30',
                indigo: 'from-indigo-500 to-indigo-700 group-hover:shadow-indigo-500/30'
              };
              
              return (
                <div
                  key={index}
                  className="group bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:bg-slate-800 hover:border-slate-600 transition-all duration-300 cursor-pointer"
                  onMouseEnter={() => setHoveredFeature(index)}
                  onMouseLeave={() => setHoveredFeature(null)}
                >
                  <div className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${colorClasses[feature.color]} mb-4 shadow-lg transition-shadow duration-300`}>
                    <Icon className="h-6 w-6 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{feature.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gradient-to-b from-slate-800/50 to-slate-900">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl sm:text-4xl font-bold text-white mb-6">
                Por que escolher o SIGESC?
              </h2>
              <p className="text-slate-400 text-lg mb-8">
                Desenvolvido especialmente para a realidade das secretarias municipais de educação brasileiras.
              </p>
              
              <div className="space-y-4">
                {benefits.map((benefit, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center mt-0.5">
                      <CheckCircle2 size={16} className="text-green-400" />
                    </div>
                    <span className="text-slate-300">{benefit}</span>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="relative">
              <div className="bg-gradient-to-br from-blue-500/20 to-purple-500/20 rounded-3xl p-8 border border-slate-700/50">
                <div className="bg-slate-900 rounded-2xl p-6 shadow-2xl">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="bg-gradient-to-br from-blue-500 to-blue-700 p-2 rounded-lg">
                      <BarChart3 className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-white font-semibold">Painel do Gestor</span>
                  </div>
                  
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-sm">Alunos Matriculados</span>
                      <span className="text-white font-semibold">4,521</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div className="bg-gradient-to-r from-blue-500 to-cyan-500 h-2 rounded-full" style={{width: '85%'}}></div>
                    </div>
                    
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-sm">Frequência Média</span>
                      <span className="text-green-400 font-semibold">92.3%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div className="bg-gradient-to-r from-green-500 to-emerald-500 h-2 rounded-full" style={{width: '92%'}}></div>
                    </div>
                    
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-sm">Notas Lançadas</span>
                      <span className="text-purple-400 font-semibold">78%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full" style={{width: '78%'}}></div>
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Decorative elements */}
              <div className="absolute -top-4 -right-4 w-24 h-24 bg-blue-500/10 rounded-full blur-2xl"></div>
              <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-purple-500/10 rounded-full blur-2xl"></div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-3xl p-8 sm:p-12 text-center relative overflow-hidden">
            {/* Background decoration */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2"></div>
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/5 rounded-full translate-y-1/2 -translate-x-1/2"></div>
            
            <div className="relative z-10">
              <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                Pronto para modernizar sua gestão?
              </h2>
              <p className="text-blue-100 text-lg mb-8 max-w-2xl mx-auto">
                Entre em contato conosco e agende uma demonstração gratuita do SIGESC. 
                Veja na prática como podemos transformar a gestão da sua rede de ensino.
              </p>
              
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <a
                  href={`https://wa.me/${whatsappNumber}?text=${whatsappMessage}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-center gap-3 bg-white hover:bg-slate-100 text-blue-700 px-8 py-4 rounded-xl font-semibold text-lg transition-all duration-300 shadow-lg"
                >
                  <MessageCircle size={24} />
                  WhatsApp: (94) 98422-3453
                </a>
                <a
                  href="mailto:contato@aprenderdigital.top"
                  className="flex items-center gap-2 text-white hover:text-blue-100 px-6 py-4 font-medium transition-colors"
                >
                  <Mail size={20} />
                  contato@aprenderdigital.top
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 sm:px-6 lg:px-8 border-t border-slate-700/50">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8 mb-8">
            {/* Company Info */}
            <div>
              <div className="flex items-center gap-3 mb-4">
                <img 
                  src="https://aprenderdigital.top/imagens/logotipo/logo-aprender-digital.png" 
                  alt="Aprender Digital" 
                  className="h-10 w-auto"
                />
              </div>
              <p className="text-slate-400 text-sm">
                A Aprender Digital é especializada em soluções tecnológicas para educação, 
                ajudando instituições a modernizar sua gestão e melhorar resultados.
              </p>
            </div>
            
            {/* Quick Links */}
            <div>
              <h4 className="text-white font-semibold mb-4">Links Rápidos</h4>
              <div className="space-y-2">
                <Link to="/login" className="block text-slate-400 hover:text-white transition-colors text-sm">
                  Acessar Sistema
                </Link>
                <Link to="/pre-matricula" className="block text-slate-400 hover:text-white transition-colors text-sm">
                  Pré-Matrícula Online
                </Link>
                <a 
                  href={`https://wa.me/${whatsappNumber}?text=${whatsappMessage}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-slate-400 hover:text-white transition-colors text-sm"
                >
                  Solicitar Demonstração
                </a>
              </div>
            </div>
            
            {/* Contact */}
            <div>
              <h4 className="text-white font-semibold mb-4">Contato</h4>
              <div className="space-y-3">
                <a 
                  href={`https://wa.me/${whatsappNumber}?text=${whatsappMessage}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-3 text-slate-400 hover:text-green-400 transition-colors text-sm"
                >
                  <Smartphone size={18} />
                  (94) 98422-3453
                </a>
                <a 
                  href="mailto:contato@aprenderdigital.top"
                  className="flex items-center gap-3 text-slate-400 hover:text-blue-400 transition-colors text-sm"
                >
                  <Mail size={18} />
                  contato@aprenderdigital.top
                </a>
              </div>
            </div>
          </div>
          
          <div className="border-t border-slate-700/50 pt-8 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <span>© {new Date().getFullYear()} SIGESC - Sistema de Gestão Escolar</span>
            </div>
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <span>Desenvolvido por</span>
              <a 
                href="https://aprenderdigital.top" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 transition-colors font-medium"
              >
                Aprender Digital
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
