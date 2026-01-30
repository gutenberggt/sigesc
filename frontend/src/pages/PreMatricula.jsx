import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { School, User, Phone, Mail, MapPin, Calendar, ChevronRight, ArrowLeft, CheckCircle, AlertCircle, Loader2, GraduationCap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Mapeamento de séries/anos disponíveis por escola
const SERIES_CONFIG = {
  // Educação Infantil - Creche
  educacao_infantil_bercario_i: { label: 'Berçário I', nivel: 'Educação Infantil', order: 1, ageRange: '3 a 11 meses' },
  educacao_infantil_bercario_ii: { label: 'Berçário II', nivel: 'Educação Infantil', order: 2, ageRange: '1 ano a 1 ano e 11 meses' },
  educacao_infantil_maternal_i: { label: 'Maternal I', nivel: 'Educação Infantil', order: 3, ageRange: '2 anos a 2 anos e 11 meses' },
  educacao_infantil_maternal_ii: { label: 'Maternal II', nivel: 'Educação Infantil', order: 4, ageRange: '3 anos a 3 anos e 11 meses' },
  // Educação Infantil - Pré-escola
  educacao_infantil_pre_i: { label: 'Pré I', nivel: 'Educação Infantil', order: 5, ageRange: '4 anos' },
  educacao_infantil_pre_ii: { label: 'Pré II', nivel: 'Educação Infantil', order: 6, ageRange: '5 anos' },
  // Retrocompatibilidade com berçário antigo
  educacao_infantil_bercario: { label: 'Berçário', nivel: 'Educação Infantil', order: 1, deprecated: true },
  
  // Fundamental Anos Iniciais
  fundamental_inicial_1ano: { label: '1º Ano', nivel: 'Fundamental - Anos Iniciais', order: 7 },
  fundamental_inicial_2ano: { label: '2º Ano', nivel: 'Fundamental - Anos Iniciais', order: 8 },
  fundamental_inicial_3ano: { label: '3º Ano', nivel: 'Fundamental - Anos Iniciais', order: 9 },
  fundamental_inicial_4ano: { label: '4º Ano', nivel: 'Fundamental - Anos Iniciais', order: 10 },
  fundamental_inicial_5ano: { label: '5º Ano', nivel: 'Fundamental - Anos Iniciais', order: 11 },
  
  // Fundamental Anos Finais
  fundamental_final_6ano: { label: '6º Ano', nivel: 'Fundamental - Anos Finais', order: 12 },
  fundamental_final_7ano: { label: '7º Ano', nivel: 'Fundamental - Anos Finais', order: 13 },
  fundamental_final_8ano: { label: '8º Ano', nivel: 'Fundamental - Anos Finais', order: 14 },
  fundamental_final_9ano: { label: '9º Ano', nivel: 'Fundamental - Anos Finais', order: 15 },
  
  // EJA Anos Iniciais
  eja_inicial_1etapa: { label: 'EJA 1ª Etapa', nivel: 'EJA - Anos Iniciais', order: 15 },
  eja_inicial_2etapa: { label: 'EJA 2ª Etapa', nivel: 'EJA - Anos Iniciais', order: 16 },
  
  // EJA Anos Finais
  eja_final_3etapa: { label: 'EJA 3ª Etapa', nivel: 'EJA - Anos Finais', order: 17 },
  eja_final_4etapa: { label: 'EJA 4ª Etapa', nivel: 'EJA - Anos Finais', order: 18 },
};

export default function PreMatricula() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1: Escolher escola, 2: Preencher dados, 3: Confirmação
  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  
  // Dados do formulário
  const [formData, setFormData] = useState({
    // Dados do Aluno
    aluno_nome: '',
    aluno_data_nascimento: '',
    aluno_sexo: '',
    aluno_cpf: '',
    
    // Dados do Responsável
    responsavel_nome: '',
    responsavel_cpf: '',
    responsavel_telefone: '',
    responsavel_email: '',
    responsavel_parentesco: '',
    
    // Endereço
    endereco_cep: '',
    endereco_logradouro: '',
    endereco_numero: '',
    endereco_bairro: '',
    endereco_cidade: '',
    
    // Série/Ano desejado
    serie_ano_desejado: '',
    observacoes: ''
  });

  // Carrega escolas com pré-matrícula ativa
  useEffect(() => {
    loadSchools();
  }, []);

  const loadSchools = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/schools/pre-matricula`);
      setSchools(response.data || []);
    } catch (error) {
      console.error('Erro ao carregar escolas:', error);
      toast.error('Erro ao carregar escolas disponíveis');
    } finally {
      setLoading(false);
    }
  };

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSchoolSelect = (school) => {
    setSelectedSchool(school);
    setFormData(prev => ({ ...prev, serie_ano_desejado: '' })); // Limpar série ao trocar escola
    setStep(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validações básicas
    if (!formData.aluno_nome || !formData.aluno_data_nascimento || !formData.responsavel_nome || !formData.responsavel_telefone) {
      toast.error('Por favor, preencha todos os campos obrigatórios');
      return;
    }
    
    setSubmitting(true);
    try {
      // Extrair o nível de ensino da série selecionada
      const serieConfig = SERIES_CONFIG[formData.serie_ano_desejado];
      const nivelEnsino = serieConfig?.nivel || '';
      
      await axios.post(`${API_URL}/api/pre-matricula`, {
        school_id: selectedSchool.id,
        ...formData,
        nivel_ensino: nivelEnsino // Preencher automaticamente baseado na série
      });
      
      setSubmitted(true);
      setStep(3);
      toast.success('Pré-matrícula enviada com sucesso!');
    } catch (error) {
      console.error('Erro ao enviar pré-matrícula:', error);
      toast.error(error.response?.data?.detail || 'Erro ao enviar pré-matrícula');
    } finally {
      setSubmitting(false);
    }
  };

  // Séries/Anos disponíveis na escola selecionada
  const getSeriesDisponiveis = () => {
    if (!selectedSchool) return [];
    
    const seriesDisponiveis = [];
    
    // Iterar sobre todas as séries configuradas
    Object.entries(SERIES_CONFIG).forEach(([key, config]) => {
      // Verificar se a escola oferece essa série
      if (selectedSchool[key] === true) {
        seriesDisponiveis.push({
          value: key,
          label: config.label,
          nivel: config.nivel,
          order: config.order
        });
      }
    });
    
    // Ordenar por order
    return seriesDisponiveis.sort((a, b) => a.order - b.order);
  };

  // Agrupar séries por nível de ensino
  const getSeriesAgrupadasPorNivel = () => {
    const series = getSeriesDisponiveis();
    const grupos = {};
    
    series.forEach(serie => {
      if (!grupos[serie.nivel]) {
        grupos[serie.nivel] = [];
      }
      grupos[serie.nivel].push(serie);
    });
    
    return grupos;
  };

  // Step 1: Escolher escola
  const renderSchoolSelection = () => (
    <div className="space-y-6">
      <div className="text-center mb-8">
        <School className="w-16 h-16 text-blue-600 mx-auto mb-4" />
        <h2 className="text-2xl font-bold text-gray-900">Escolha a Escola</h2>
        <p className="text-gray-600 mt-2">Selecione a escola onde deseja realizar a pré-matrícula</p>
      </div>
      
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          <span className="ml-2 text-gray-600">Carregando escolas...</span>
        </div>
      ) : schools.length === 0 ? (
        <div className="text-center py-12">
          <AlertCircle className="w-16 h-16 text-amber-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900">Nenhuma escola disponível</h3>
          <p className="text-gray-600 mt-2">
            No momento, não há escolas com pré-matrícula aberta.
          </p>
          <Button 
            variant="outline" 
            className="mt-6"
            onClick={() => navigate('/login')}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Voltar ao Login
          </Button>
        </div>
      ) : (
        <div className="grid gap-4">
          {schools.map((school) => (
            <div
              key={school.id}
              onClick={() => handleSchoolSelect(school)}
              className="bg-white border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-blue-500 hover:shadow-md transition-all group"
              data-testid={`school-card-${school.id}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                    {school.name}
                  </h3>
                  {school.municipio && (
                    <div className="flex items-center text-sm text-gray-500 mt-1">
                      <MapPin className="w-4 h-4 mr-1" />
                      {school.municipio}{school.estado && ` - ${school.estado}`}
                    </div>
                  )}
                  {school.zona_localizacao && (
                    <span className={`inline-block mt-2 px-2 py-0.5 text-xs rounded-full ${
                      school.zona_localizacao === 'urbana' 
                        ? 'bg-blue-100 text-blue-700' 
                        : 'bg-green-100 text-green-700'
                    }`}>
                      Zona {school.zona_localizacao === 'urbana' ? 'Urbana' : 'Rural'}
                    </span>
                  )}
                </div>
                <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-blue-500 transition-colors" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Step 2: Formulário de pré-matrícula
  const renderForm = () => {
    const seriesAgrupadas = getSeriesAgrupadasPorNivel();
    const temSeriesDisponiveis = Object.keys(seriesAgrupadas).length > 0;
    
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4 mb-6">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setStep(1)}
            className="text-gray-600"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Voltar
          </Button>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-gray-900">Pré-Matrícula</h2>
            <p className="text-sm text-gray-600">{selectedSchool?.name}</p>
          </div>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Dados do Aluno */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <User className="w-5 h-5 text-blue-600" />
              Dados do Aluno
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Label htmlFor="aluno_nome">Nome Completo do Aluno *</Label>
                <Input
                  id="aluno_nome"
                  value={formData.aluno_nome}
                  onChange={(e) => updateFormData('aluno_nome', e.target.value)}
                  placeholder="Nome completo"
                  required
                  data-testid="aluno-nome-input"
                />
              </div>
              <div>
                <Label htmlFor="aluno_data_nascimento">Data de Nascimento *</Label>
                <Input
                  id="aluno_data_nascimento"
                  type="date"
                  value={formData.aluno_data_nascimento}
                  onChange={(e) => updateFormData('aluno_data_nascimento', e.target.value)}
                  required
                  data-testid="aluno-nascimento-input"
                />
              </div>
              <div>
                <Label htmlFor="aluno_sexo">Sexo</Label>
                <Select 
                  value={formData.aluno_sexo} 
                  onValueChange={(value) => updateFormData('aluno_sexo', value)}
                >
                  <SelectTrigger data-testid="aluno-sexo-select">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="masculino">Masculino</SelectItem>
                    <SelectItem value="feminino">Feminino</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="aluno_cpf">CPF do Aluno (opcional)</Label>
                <Input
                  id="aluno_cpf"
                  value={formData.aluno_cpf}
                  onChange={(e) => updateFormData('aluno_cpf', e.target.value)}
                  placeholder="000.000.000-00"
                  data-testid="aluno-cpf-input"
                />
              </div>
              <div>
                <Label htmlFor="serie_ano_desejado" className="flex items-center gap-1">
                  <GraduationCap className="w-4 h-4" />
                  Série/Ano Desejado
                </Label>
                {temSeriesDisponiveis ? (
                  <Select 
                    value={formData.serie_ano_desejado} 
                    onValueChange={(value) => updateFormData('serie_ano_desejado', value)}
                  >
                    <SelectTrigger data-testid="serie-ano-select">
                      <SelectValue placeholder="Selecione a série/ano" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(seriesAgrupadas).map(([nivel, series]) => (
                        <div key={nivel}>
                          <div className="px-2 py-1.5 text-xs font-semibold text-gray-500 bg-gray-50">
                            {nivel}
                          </div>
                          {series.map(serie => (
                            <SelectItem key={serie.value} value={serie.value}>
                              {serie.label}
                            </SelectItem>
                          ))}
                        </div>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <div className="px-3 py-2 border rounded-lg bg-gray-50 text-sm text-gray-500">
                    Esta escola não possui séries cadastradas
                  </div>
                )}
              </div>
            </div>
          </div>
          
          {/* Dados do Responsável */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <User className="w-5 h-5 text-green-600" />
              Dados do Responsável
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <Label htmlFor="responsavel_nome">Nome Completo do Responsável *</Label>
                <Input
                  id="responsavel_nome"
                  value={formData.responsavel_nome}
                  onChange={(e) => updateFormData('responsavel_nome', e.target.value)}
                  placeholder="Nome completo"
                  required
                  data-testid="responsavel-nome-input"
                />
              </div>
              <div>
                <Label htmlFor="responsavel_cpf">CPF do Responsável</Label>
                <Input
                  id="responsavel_cpf"
                  value={formData.responsavel_cpf}
                  onChange={(e) => updateFormData('responsavel_cpf', e.target.value)}
                  placeholder="000.000.000-00"
                  data-testid="responsavel-cpf-input"
                />
              </div>
              <div>
                <Label htmlFor="responsavel_parentesco">Parentesco</Label>
                <Select 
                  value={formData.responsavel_parentesco} 
                  onValueChange={(value) => updateFormData('responsavel_parentesco', value)}
                >
                  <SelectTrigger data-testid="responsavel-parentesco-select">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="mae">Mãe</SelectItem>
                    <SelectItem value="pai">Pai</SelectItem>
                    <SelectItem value="avo">Avô/Avó</SelectItem>
                    <SelectItem value="tio">Tio/Tia</SelectItem>
                    <SelectItem value="responsavel">Responsável Legal</SelectItem>
                    <SelectItem value="outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="responsavel_telefone">Telefone/WhatsApp *</Label>
                <Input
                  id="responsavel_telefone"
                  value={formData.responsavel_telefone}
                  onChange={(e) => updateFormData('responsavel_telefone', e.target.value)}
                  placeholder="(00) 00000-0000"
                  required
                  data-testid="responsavel-telefone-input"
                />
              </div>
              <div>
                <Label htmlFor="responsavel_email">E-mail</Label>
                <Input
                  id="responsavel_email"
                  type="email"
                  value={formData.responsavel_email}
                  onChange={(e) => updateFormData('responsavel_email', e.target.value)}
                  placeholder="email@exemplo.com"
                  data-testid="responsavel-email-input"
                />
              </div>
            </div>
          </div>
          
          {/* Endereço */}
          <div className="bg-white rounded-lg border p-6">
            <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <MapPin className="w-5 h-5 text-purple-600" />
              Endereço
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="endereco_cep">CEP</Label>
                <Input
                  id="endereco_cep"
                  value={formData.endereco_cep}
                  onChange={(e) => updateFormData('endereco_cep', e.target.value)}
                  placeholder="00000-000"
                  data-testid="endereco-cep-input"
                />
              </div>
              <div className="md:col-span-2">
                <Label htmlFor="endereco_logradouro">Logradouro</Label>
                <Input
                  id="endereco_logradouro"
                  value={formData.endereco_logradouro}
                  onChange={(e) => updateFormData('endereco_logradouro', e.target.value)}
                  placeholder="Rua, Avenida, etc."
                  data-testid="endereco-logradouro-input"
                />
              </div>
              <div>
                <Label htmlFor="endereco_numero">Número</Label>
                <Input
                  id="endereco_numero"
                  value={formData.endereco_numero}
                  onChange={(e) => updateFormData('endereco_numero', e.target.value)}
                  placeholder="Nº"
                  data-testid="endereco-numero-input"
                />
              </div>
              <div>
                <Label htmlFor="endereco_bairro">Bairro</Label>
                <Input
                  id="endereco_bairro"
                  value={formData.endereco_bairro}
                  onChange={(e) => updateFormData('endereco_bairro', e.target.value)}
                  placeholder="Bairro"
                  data-testid="endereco-bairro-input"
                />
              </div>
              <div>
                <Label htmlFor="endereco_cidade">Cidade</Label>
                <Input
                  id="endereco_cidade"
                  value={formData.endereco_cidade}
                  onChange={(e) => updateFormData('endereco_cidade', e.target.value)}
                  placeholder="Cidade"
                  data-testid="endereco-cidade-input"
                />
              </div>
            </div>
          </div>
          
          {/* Observações */}
          <div className="bg-white rounded-lg border p-6">
            <Label htmlFor="observacoes">Observações (opcional)</Label>
            <textarea
              id="observacoes"
              value={formData.observacoes}
              onChange={(e) => updateFormData('observacoes', e.target.value)}
              placeholder="Informações adicionais que deseja compartilhar..."
              className="w-full mt-2 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-h-[100px]"
              data-testid="observacoes-input"
            />
          </div>
          
          {/* Botão de envio */}
          <div className="flex justify-end gap-4">
            <Button 
              type="button" 
              variant="outline" 
              onClick={() => setStep(1)}
            >
              Cancelar
            </Button>
            <Button 
              type="submit" 
              disabled={submitting}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="submit-pre-matricula-btn"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Enviando...
                </>
              ) : (
                <>
                  Enviar Pré-Matrícula
                  <ChevronRight className="w-4 h-4 ml-2" />
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    );
  };

  // Step 3: Confirmação
  const renderConfirmation = () => {
    const serieConfig = SERIES_CONFIG[formData.serie_ano_desejado];
    
    return (
      <div className="text-center py-12">
        <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
          <CheckCircle className="w-12 h-12 text-green-600" />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Pré-Matrícula Enviada!</h2>
        <p className="text-gray-600 mb-6 max-w-md mx-auto">
          Sua solicitação de pré-matrícula foi enviada com sucesso para <strong>{selectedSchool?.name}</strong>.
          {serieConfig && (
            <span className="block mt-2">
              Série solicitada: <strong>{serieConfig.label}</strong> ({serieConfig.nivel})
            </span>
          )}
          <span className="block mt-2">A escola entrará em contato pelo telefone ou e-mail informado.</span>
        </p>
        
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 max-w-md mx-auto mb-8">
          <h4 className="font-medium text-blue-800 mb-2">Próximos Passos:</h4>
          <ul className="text-sm text-blue-700 text-left space-y-2">
            <li className="flex items-start gap-2">
              <span className="font-bold">1.</span>
              Aguarde o contato da escola para confirmar a matrícula
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold">2.</span>
              Separe os documentos necessários (certidão de nascimento, comprovante de endereço, etc.)
            </li>
            <li className="flex items-start gap-2">
              <span className="font-bold">3.</span>
              Compare à escola na data agendada para finalizar a matrícula
            </li>
          </ul>
        </div>
        
        <div className="flex justify-center gap-4">
          <Button 
            variant="outline" 
            onClick={() => {
              setStep(1);
              setSelectedSchool(null);
              setFormData({
                aluno_nome: '',
                aluno_data_nascimento: '',
                aluno_sexo: '',
                aluno_cpf: '',
                responsavel_nome: '',
                responsavel_cpf: '',
                responsavel_telefone: '',
                responsavel_email: '',
                responsavel_parentesco: '',
                endereco_cep: '',
                endereco_logradouro: '',
                endereco_numero: '',
                endereco_bairro: '',
                endereco_cidade: '',
                serie_ano_desejado: '',
                observacoes: ''
              });
              setSubmitted(false);
            }}
          >
            Nova Pré-Matrícula
          </Button>
          <Button onClick={() => navigate('/login')}>
            Ir para Login
          </Button>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-gray-100 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <img
            src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png"
            alt="SIGESC Logo"
            className="h-16 mx-auto mb-4"
          />
          <h1 className="text-2xl font-bold text-gray-900">SIGESC</h1>
          <p className="text-gray-600">Sistema Integrado de Gestão Escolar</p>
        </div>
        
        {/* Progress Steps */}
        {!submitted && (
          <div className="flex items-center justify-center mb-8">
            <div className={`flex items-center ${step >= 1 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                step >= 1 ? 'bg-blue-600 text-white' : 'bg-gray-200'
              }`}>1</div>
              <span className="ml-2 text-sm hidden sm:inline">Escola</span>
            </div>
            <div className={`w-12 h-0.5 mx-2 ${step >= 2 ? 'bg-blue-600' : 'bg-gray-200'}`} />
            <div className={`flex items-center ${step >= 2 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-200'
              }`}>2</div>
              <span className="ml-2 text-sm hidden sm:inline">Dados</span>
            </div>
            <div className={`w-12 h-0.5 mx-2 ${step >= 3 ? 'bg-blue-600' : 'bg-gray-200'}`} />
            <div className={`flex items-center ${step >= 3 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                step >= 3 ? 'bg-blue-600 text-white' : 'bg-gray-200'
              }`}>3</div>
              <span className="ml-2 text-sm hidden sm:inline">Confirmação</span>
            </div>
          </div>
        )}
        
        {/* Content */}
        <div className="bg-white rounded-xl shadow-lg p-6 md:p-8">
          {step === 1 && renderSchoolSelection()}
          {step === 2 && renderForm()}
          {step === 3 && renderConfirmation()}
        </div>
        
        {/* Footer */}
        <div className="text-center mt-6">
          <button 
            onClick={() => navigate('/login')}
            className="text-sm text-gray-500 hover:text-blue-600 transition-colors"
          >
            Já tem conta? Faça login
          </button>
        </div>
      </div>
    </div>
  );
}
