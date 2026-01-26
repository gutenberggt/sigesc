import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Save, MapPin, Phone, User, Loader2, Upload, Image, X, Home, CheckSquare, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { mantenedoraAPI, uploadAPI } from '@/services/api';
import { formatCEP, formatPhone, formatCPF, formatCNPJ } from '@/utils/formatters';
import { useMantenedora } from '@/contexts/MantenedoraContext';

export default function Mantenedora() {
  const navigate = useNavigate();
  const { refreshMantenedora } = useMantenedora();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingBrasao, setUploadingBrasao] = useState(false);
  const [alert, setAlert] = useState(null);
  const fileInputRef = useRef(null);
  const brasaoInputRef = useRef(null);
  const [formData, setFormData] = useState({
    // Identificação
    nome: '',
    cnpj: '',
    codigo_inep: '',
    natureza_juridica: 'Pública Municipal',
    logotipo_url: '',
    brasao_url: '',  // URL do brasão
    slogan: '',  // Slogan para cabeçalhos dos documentos
    
    // Condicionais para aprovação
    media_aprovacao: '6.0',
    aprovacao_com_dependencia: false,
    max_componentes_dependencia: '',
    cursar_apenas_dependencia: false,
    qtd_componentes_apenas_dependencia: '',
    frequencia_minima: '75',
    
    // Endereço
    cep: '',
    logradouro: '',
    numero: '',
    complemento: '',
    bairro: '',
    municipio: '',
    estado: '',
    
    // Contato
    telefone: '',
    celular: '',
    email: '',
    site: '',
    contato_nome: '',
    contato_cargo: '',
    
    // Responsável Legal
    responsavel_nome: '',
    responsavel_cargo: '',
    responsavel_cpf: '',
    responsavel_celular: '',
    responsavel_email: '',
    
    // Configurações de Exibição
    exibir_pre_matricula: true
  });

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };

  const loadMantenedora = useCallback(async () => {
    try {
      setLoading(true);
      const data = await mantenedoraAPI.get();
      setFormData({
        nome: data.nome || '',
        cnpj: data.cnpj || '',
        codigo_inep: data.codigo_inep || '',
        natureza_juridica: data.natureza_juridica || 'Pública Municipal',
        logotipo_url: data.logotipo_url || '',
        brasao_url: data.brasao_url || '',
        slogan: data.slogan || '',
        // Condicionais para aprovação - garantir formato correto para Select
        media_aprovacao: data.media_aprovacao != null ? Number(data.media_aprovacao).toFixed(1) : '6.0',
        frequencia_minima: data.frequencia_minima?.toString() || '75',
        aprovacao_com_dependencia: data.aprovacao_com_dependencia || false,
        max_componentes_dependencia: data.max_componentes_dependencia?.toString() || '',
        cursar_apenas_dependencia: data.cursar_apenas_dependencia || false,
        qtd_componentes_apenas_dependencia: data.qtd_componentes_apenas_dependencia?.toString() || '',
        // Endereço
        cep: data.cep || '',
        logradouro: data.logradouro || '',
        numero: data.numero || '',
        complemento: data.complemento || '',
        bairro: data.bairro || '',
        municipio: data.municipio || '',
        estado: data.estado || '',
        telefone: data.telefone || '',
        celular: data.celular || '',
        email: data.email || '',
        site: data.site || '',
        contato_nome: data.contato_nome || '',
        contato_cargo: data.contato_cargo || '',
        responsavel_nome: data.responsavel_nome || '',
        responsavel_cargo: data.responsavel_cargo || '',
        responsavel_cpf: data.responsavel_cpf || '',
        responsavel_celular: data.responsavel_celular || '',
        responsavel_email: data.responsavel_email || '',
        // Configurações de Exibição
        exibir_pre_matricula: data.exibir_pre_matricula !== false // default true
      });
    } catch (error) {
      console.error('Erro ao carregar mantenedora:', error);
      showAlert('error', 'Erro ao carregar dados da mantenedora');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMantenedora();
  }, [loadMantenedora]);

  // Upload do logotipo
  const handleLogoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validar tipo de arquivo
    if (!file.type.startsWith('image/')) {
      showAlert('error', 'Por favor, selecione uma imagem');
      return;
    }

    // Validar tamanho (máximo 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showAlert('error', 'A imagem deve ter no máximo 5MB');
      return;
    }

    try {
      setUploading(true);
      const result = await uploadAPI.upload(file, 'logotipo');
      
      if (result.url) {
        setFormData(prev => ({ ...prev, logotipo_url: result.url }));
        showAlert('success', 'Logotipo enviado com sucesso!');
      }
    } catch (error) {
      console.error('Erro ao enviar logotipo:', error);
      showAlert('error', 'Erro ao enviar logotipo');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleRemoveLogo = () => {
    setFormData(prev => ({ ...prev, logotipo_url: '' }));
  };

  // Upload do brasão
  const handleBrasaoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validar tipo de arquivo
    if (!file.type.startsWith('image/')) {
      showAlert('error', 'Por favor, selecione uma imagem');
      return;
    }

    // Validar tamanho (máximo 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showAlert('error', 'A imagem deve ter no máximo 5MB');
      return;
    }

    try {
      setUploadingBrasao(true);
      const result = await uploadAPI.upload(file, 'brasao');
      
      if (result.url) {
        setFormData(prev => ({ ...prev, brasao_url: result.url }));
        showAlert('success', 'Brasão enviado com sucesso!');
      }
    } catch (error) {
      console.error('Erro ao enviar brasão:', error);
      showAlert('error', 'Erro ao enviar brasão');
    } finally {
      setUploadingBrasao(false);
      if (brasaoInputRef.current) {
        brasaoInputRef.current.value = '';
      }
    }
  };

  const handleRemoveBrasao = () => {
    setFormData(prev => ({ ...prev, brasao_url: '' }));
  };

  const handleInputChange = (field, value) => {
    // Aplicar formatação automática
    let formattedValue = value;
    
    if (field === 'cep') {
      formattedValue = formatCEP(value);
    } else if (field === 'telefone' || field === 'celular') {
      formattedValue = formatPhone(value);
    } else if (field === 'responsavel_cpf') {
      formattedValue = formatCPF(value);
    } else if (field === 'cnpj') {
      formattedValue = formatCNPJ(value);
    }
    
    setFormData(prev => ({ ...prev, [field]: formattedValue }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.nome.trim()) {
      showAlert('error', 'O nome da mantenedora é obrigatório');
      return;
    }
    
    try {
      setSaving(true);
      
      // Preparar dados para envio, convertendo valores numéricos
      const dataToSend = {
        ...formData,
        media_aprovacao: formData.media_aprovacao ? parseFloat(formData.media_aprovacao) : null,
        frequencia_minima: formData.frequencia_minima ? parseFloat(formData.frequencia_minima) : null,
        max_componentes_dependencia: formData.max_componentes_dependencia ? parseInt(formData.max_componentes_dependencia) : null,
        qtd_componentes_apenas_dependencia: formData.qtd_componentes_apenas_dependencia ? parseInt(formData.qtd_componentes_apenas_dependencia) : null,
      };
      
      await mantenedoraAPI.update(dataToSend);
      // Atualiza o contexto global da mantenedora
      refreshMantenedora();
      showAlert('success', 'Dados salvos com sucesso!');
    } catch (error) {
      console.error('Erro ao salvar:', error);
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar dados');
    } finally {
      setSaving(false);
    }
  };

  // Busca CEP
  const handleCEPBlur = async () => {
    const cep = formData.cep.replace(/\D/g, '');
    if (cep.length === 8) {
      try {
        const response = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const data = await response.json();
        if (!data.erro) {
          setFormData(prev => ({
            ...prev,
            logradouro: data.logradouro || prev.logradouro,
            bairro: data.bairro || prev.bairro,
            municipio: data.localidade || prev.municipio,
            estado: data.uf || prev.estado
          }));
        }
      } catch (error) {
        console.error('Erro ao buscar CEP:', error);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <Home size={18} />
            <span>Início</span>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Unidade Mantenedora</h1>
            <p className="text-gray-600">Dados da instituição que mantém as escolas</p>
          </div>
        </div>
      </div>

      {/* Alert */}
      {alert && (
        <div className={`p-4 rounded-lg ${
          alert.type === 'success' 
            ? 'bg-green-50 text-green-800 border border-green-200' 
            : 'bg-red-50 text-red-800 border border-red-200'
        }`}>
          {alert.message}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Identificação */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Building2 className="w-5 h-5 text-blue-600" />
                Identificação
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="nome">Nome da Mantenedora *</Label>
                <Input
                  id="nome"
                  value={formData.nome}
                  onChange={(e) => handleInputChange('nome', e.target.value)}
                  placeholder="Ex: Prefeitura Municipal de..."
                  required
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="cnpj">CNPJ</Label>
                  <Input
                    id="cnpj"
                    value={formData.cnpj}
                    onChange={(e) => handleInputChange('cnpj', e.target.value)}
                    placeholder="00.000.000/0000-00"
                    maxLength={18}
                  />
                </div>
                <div>
                  <Label htmlFor="codigo_inep">Código INEP</Label>
                  <Input
                    id="codigo_inep"
                    value={formData.codigo_inep}
                    onChange={(e) => handleInputChange('codigo_inep', e.target.value)}
                    placeholder="Código INEP"
                  />
                </div>
              </div>
              
              <div>
                <Label htmlFor="natureza_juridica">Natureza Jurídica</Label>
                <select
                  id="natureza_juridica"
                  value={formData.natureza_juridica}
                  onChange={(e) => handleInputChange('natureza_juridica', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="Pública Municipal">Pública Municipal</option>
                  <option value="Pública Estadual">Pública Estadual</option>
                  <option value="Pública Federal">Pública Federal</option>
                  <option value="Privada">Privada</option>
                  <option value="Filantrópica">Filantrópica</option>
                  <option value="Comunitária">Comunitária</option>
                  <option value="Confessional">Confessional</option>
                </select>
              </div>

              {/* Logotipo */}
              <div>
                <Label>Logotipo</Label>
                <div className="mt-2">
                  {formData.logotipo_url ? (
                    <div className="relative inline-block">
                      <img
                        src={formData.logotipo_url}
                        alt="Logotipo da Mantenedora"
                        className="w-32 h-32 object-contain border border-gray-200 rounded-lg bg-white"
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24" fill="none" stroke="%239ca3af" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>';
                        }}
                      />
                      <button
                        type="button"
                        onClick={handleRemoveLogo}
                        className="absolute -top-2 -right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600 transition-colors"
                        title="Remover logotipo"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="w-32 h-32 border-2 border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center text-gray-400">
                      <Image className="w-8 h-8 mb-1" />
                      <span className="text-xs">Sem logotipo</span>
                    </div>
                  )}
                  
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleLogoUpload}
                    accept="image/*"
                    className="hidden"
                  />
                  
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className="mt-2"
                  >
                    {uploading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Enviando...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4 mr-2" />
                        {formData.logotipo_url ? 'Alterar' : 'Enviar'} Logotipo
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* Brasão */}
              <div>
                <Label>Brasão</Label>
                <div className="mt-2">
                  {formData.brasao_url ? (
                    <div className="relative inline-block">
                      <img
                        src={formData.brasao_url}
                        alt="Brasão da Mantenedora"
                        className="w-32 h-32 object-contain border border-gray-200 rounded-lg bg-white"
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 24 24" fill="none" stroke="%239ca3af" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>';
                        }}
                      />
                      <button
                        type="button"
                        onClick={handleRemoveBrasao}
                        className="absolute -top-2 -right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600 transition-colors"
                        title="Remover brasão"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="w-32 h-32 border-2 border-dashed border-gray-300 rounded-lg flex flex-col items-center justify-center text-gray-400">
                      <Image className="w-8 h-8 mb-1" />
                      <span className="text-xs">Sem brasão</span>
                    </div>
                  )}
                  
                  <input
                    type="file"
                    ref={brasaoInputRef}
                    onChange={handleBrasaoUpload}
                    accept="image/*"
                    className="hidden"
                  />
                  
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => brasaoInputRef.current?.click()}
                    disabled={uploadingBrasao}
                    className="mt-2"
                  >
                    {uploadingBrasao ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Enviando...
                      </>
                    ) : (
                      <>
                        <Upload className="w-4 h-4 mr-2" />
                        {formData.brasao_url ? 'Alterar' : 'Enviar'} Brasão
                      </>
                    )}
                  </Button>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  O brasão será exibido no certificado de conclusão
                </p>
              </div>

              {/* Slogan */}
              <div>
                <Label htmlFor="slogan">Slogan</Label>
                <Input
                  id="slogan"
                  value={formData.slogan}
                  onChange={(e) => handleInputChange('slogan', e.target.value)}
                  placeholder="Ex: Cuidar do povo é nossa prioridade"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Este texto aparecerá nos cabeçalhos dos documentos (boletins, fichas, etc.)
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Condicionais para Aprovação */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <CheckSquare className="w-5 h-5 text-purple-600" />
                Condicionais para Aprovação
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Média para aprovação */}
              <div>
                <Label htmlFor="media_aprovacao">Média para Aprovação</Label>
                <Select
                  value={formData.media_aprovacao}
                  onValueChange={(value) => handleInputChange('media_aprovacao', value)}
                >
                  <SelectTrigger className="w-48 mt-1">
                    <SelectValue placeholder="Selecione a média" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="5.0">5,0</SelectItem>
                    <SelectItem value="6.0">6,0</SelectItem>
                    <SelectItem value="7.0">7,0</SelectItem>
                    <SelectItem value="8.0">8,0</SelectItem>
                    <SelectItem value="9.0">9,0</SelectItem>
                    <SelectItem value="10.0">10,0</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">
                  Média mínima necessária para aprovação do aluno
                </p>
              </div>

              {/* Frequência mínima */}
              <div>
                <Label htmlFor="frequencia_minima">Frequência Mínima para Aprovação (%)</Label>
                <Select
                  value={formData.frequencia_minima}
                  onValueChange={(value) => handleInputChange('frequencia_minima', value)}
                >
                  <SelectTrigger className="w-48 mt-1">
                    <SelectValue placeholder="Selecione a frequência" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="60">60%</SelectItem>
                    <SelectItem value="65">65%</SelectItem>
                    <SelectItem value="70">70%</SelectItem>
                    <SelectItem value="75">75%</SelectItem>
                    <SelectItem value="80">80%</SelectItem>
                    <SelectItem value="85">85%</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">
                  Frequência mínima necessária para aprovação (padrão LDB: 75%)
                </p>
              </div>

              {/* Aprovação com dependência */}
              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="aprovacao_com_dependencia"
                    checked={formData.aprovacao_com_dependencia}
                    onCheckedChange={(checked) => {
                      handleInputChange('aprovacao_com_dependencia', checked);
                      if (!checked) {
                        handleInputChange('max_componentes_dependencia', '');
                      }
                    }}
                  />
                  <Label htmlFor="aprovacao_com_dependencia" className="cursor-pointer">
                    Aprovação com dependência
                  </Label>
                </div>
                
                {formData.aprovacao_com_dependencia && (
                  <div className="ml-6 p-3 bg-gray-50 rounded-lg border">
                    <Label htmlFor="max_componentes_dependencia">
                      Quantidade máxima de Componentes para ser aprovado com dependência
                    </Label>
                    <Select
                      value={formData.max_componentes_dependencia}
                      onValueChange={(value) => handleInputChange('max_componentes_dependencia', value)}
                    >
                      <SelectTrigger className="w-48 mt-1">
                        <SelectValue placeholder="Selecione" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">1 componente</SelectItem>
                        <SelectItem value="2">2 componentes</SelectItem>
                        <SelectItem value="3">3 componentes</SelectItem>
                        <SelectItem value="4">4 componentes</SelectItem>
                        <SelectItem value="5">5 componentes</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              {/* Cursar apenas dependência */}
              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="cursar_apenas_dependencia"
                    checked={formData.cursar_apenas_dependencia}
                    onCheckedChange={(checked) => {
                      handleInputChange('cursar_apenas_dependencia', checked);
                      if (!checked) {
                        handleInputChange('qtd_componentes_apenas_dependencia', '');
                      }
                    }}
                  />
                  <Label htmlFor="cursar_apenas_dependencia" className="cursor-pointer">
                    Cursar apenas dependência
                  </Label>
                </div>
                
                {formData.cursar_apenas_dependencia && (
                  <div className="ml-6 p-3 bg-gray-50 rounded-lg border">
                    <Label htmlFor="qtd_componentes_apenas_dependencia">
                      Quantidade de Componentes para cursar apenas dependência
                    </Label>
                    <Select
                      value={formData.qtd_componentes_apenas_dependencia}
                      onValueChange={(value) => handleInputChange('qtd_componentes_apenas_dependencia', value)}
                    >
                      <SelectTrigger className="w-48 mt-1">
                        <SelectValue placeholder="Selecione" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">1 componente</SelectItem>
                        <SelectItem value="2">2 componentes</SelectItem>
                        <SelectItem value="3">3 componentes</SelectItem>
                        <SelectItem value="4">4 componentes</SelectItem>
                        <SelectItem value="5">5 componentes</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              
              <p className="text-xs text-gray-500 border-t pt-3 mt-3">
                Estas regras serão consideradas no resultado final do aluno
              </p>
            </CardContent>
          </Card>

          {/* Endereço */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <MapPin className="w-5 h-5 text-green-600" />
                Endereço
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label htmlFor="cep">CEP</Label>
                  <Input
                    id="cep"
                    value={formData.cep}
                    onChange={(e) => handleInputChange('cep', e.target.value)}
                    onBlur={handleCEPBlur}
                    placeholder="00000-000"
                    maxLength={9}
                  />
                </div>
                <div className="col-span-2">
                  <Label htmlFor="logradouro">Logradouro</Label>
                  <Input
                    id="logradouro"
                    value={formData.logradouro}
                    onChange={(e) => handleInputChange('logradouro', e.target.value)}
                    placeholder="Rua, Avenida, etc."
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <Label htmlFor="numero">Número</Label>
                  <Input
                    id="numero"
                    value={formData.numero}
                    onChange={(e) => handleInputChange('numero', e.target.value)}
                    placeholder="Nº"
                  />
                </div>
                <div className="col-span-3">
                  <Label htmlFor="complemento">Complemento</Label>
                  <Input
                    id="complemento"
                    value={formData.complemento}
                    onChange={(e) => handleInputChange('complemento', e.target.value)}
                    placeholder="Sala, Andar, etc."
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label htmlFor="bairro">Bairro</Label>
                  <Input
                    id="bairro"
                    value={formData.bairro}
                    onChange={(e) => handleInputChange('bairro', e.target.value)}
                    placeholder="Bairro"
                  />
                </div>
                <div>
                  <Label htmlFor="municipio">Município</Label>
                  <Input
                    id="municipio"
                    value={formData.municipio}
                    onChange={(e) => handleInputChange('municipio', e.target.value)}
                    placeholder="Cidade"
                  />
                </div>
                <div>
                  <Label htmlFor="estado">Estado</Label>
                  <select
                    id="estado"
                    value={formData.estado}
                    onChange={(e) => handleInputChange('estado', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">UF</option>
                    <option value="AC">AC</option>
                    <option value="AL">AL</option>
                    <option value="AP">AP</option>
                    <option value="AM">AM</option>
                    <option value="BA">BA</option>
                    <option value="CE">CE</option>
                    <option value="DF">DF</option>
                    <option value="ES">ES</option>
                    <option value="GO">GO</option>
                    <option value="MA">MA</option>
                    <option value="MT">MT</option>
                    <option value="MS">MS</option>
                    <option value="MG">MG</option>
                    <option value="PA">PA</option>
                    <option value="PB">PB</option>
                    <option value="PR">PR</option>
                    <option value="PE">PE</option>
                    <option value="PI">PI</option>
                    <option value="RJ">RJ</option>
                    <option value="RN">RN</option>
                    <option value="RS">RS</option>
                    <option value="RO">RO</option>
                    <option value="RR">RR</option>
                    <option value="SC">SC</option>
                    <option value="SP">SP</option>
                    <option value="SE">SE</option>
                    <option value="TO">TO</option>
                  </select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Contato */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Phone className="w-5 h-5 text-purple-600" />
                Contato
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="contato_nome">Nome do Contato</Label>
                  <Input
                    id="contato_nome"
                    value={formData.contato_nome}
                    onChange={(e) => handleInputChange('contato_nome', e.target.value)}
                    placeholder="Nome da pessoa de contato"
                  />
                </div>
                <div>
                  <Label htmlFor="contato_cargo">Cargo</Label>
                  <Input
                    id="contato_cargo"
                    value={formData.contato_cargo}
                    onChange={(e) => handleInputChange('contato_cargo', e.target.value)}
                    placeholder="Ex: Secretário(a) de Educação"
                  />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="telefone">Telefone</Label>
                  <Input
                    id="telefone"
                    value={formData.telefone}
                    onChange={(e) => handleInputChange('telefone', e.target.value)}
                    placeholder="(00) 0000-0000"
                    maxLength={15}
                  />
                </div>
                <div>
                  <Label htmlFor="celular">Celular</Label>
                  <Input
                    id="celular"
                    value={formData.celular}
                    onChange={(e) => handleInputChange('celular', e.target.value)}
                    placeholder="(00) 00000-0000"
                    maxLength={15}
                  />
                </div>
              </div>
              
              <div>
                <Label htmlFor="email">E-mail</Label>
                <Input
                  id="email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  placeholder="contato@exemplo.gov.br"
                />
              </div>
              
              <div>
                <Label htmlFor="site">Site</Label>
                <Input
                  id="site"
                  value={formData.site}
                  onChange={(e) => handleInputChange('site', e.target.value)}
                  placeholder="https://www.exemplo.gov.br"
                />
              </div>
            </CardContent>
          </Card>

          {/* Responsável Legal */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <User className="w-5 h-5 text-orange-600" />
                Responsável Legal
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="responsavel_nome">Nome do Responsável</Label>
                <Input
                  id="responsavel_nome"
                  value={formData.responsavel_nome}
                  onChange={(e) => handleInputChange('responsavel_nome', e.target.value)}
                  placeholder="Nome completo"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="responsavel_cargo">Cargo</Label>
                  <Input
                    id="responsavel_cargo"
                    value={formData.responsavel_cargo}
                    onChange={(e) => handleInputChange('responsavel_cargo', e.target.value)}
                    placeholder="Ex: Prefeito(a)"
                  />
                </div>
                <div>
                  <Label htmlFor="responsavel_cpf">CPF</Label>
                  <Input
                    id="responsavel_cpf"
                    value={formData.responsavel_cpf}
                    onChange={(e) => handleInputChange('responsavel_cpf', e.target.value)}
                    placeholder="000.000.000-00"
                    maxLength={14}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Configurações de Exibição */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Settings className="w-5 h-5 text-gray-600" />
                Configurações de Exibição
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="exibir_pre_matricula"
                  checked={formData.exibir_pre_matricula}
                  onCheckedChange={(checked) => handleInputChange('exibir_pre_matricula', checked)}
                  data-testid="exibir-pre-matricula-checkbox"
                />
                <Label htmlFor="exibir_pre_matricula" className="cursor-pointer">
                  Exibir botão de Pré-Matrícula na tela de login
                </Label>
              </div>
              <p className="text-xs text-gray-500">
                Quando habilitado, o botão de pré-matrícula será exibido na tela de login para os responsáveis realizarem a pré-matrícula de novos alunos.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Botão Salvar */}
        <div className="mt-6 flex justify-end">
          <Button 
            type="submit" 
            disabled={saving}
            className="px-8"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Salvando...
              </>
            ) : (
              <>
                <Save className="w-4 h-4 mr-2" />
                Salvar Alterações
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
