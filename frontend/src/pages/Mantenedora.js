import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Save, MapPin, Phone, User, Loader2, Upload, Image, X, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { mantenedoraAPI, uploadAPI } from '@/services/api';
import { formatCEP, formatPhone, formatCPF, formatCNPJ } from '@/utils/formatters';
import { useMantenedora } from '@/contexts/MantenedoraContext';

export default function Mantenedora() {
  const navigate = useNavigate();
  const { refreshMantenedora } = useMantenedora();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [alert, setAlert] = useState(null);
  const fileInputRef = useRef(null);
  const [formData, setFormData] = useState({
    // Identificação
    nome: '',
    cnpj: '',
    codigo_inep: '',
    natureza_juridica: 'Pública Municipal',
    logotipo_url: '',
    
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
    responsavel_cpf: ''
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
        responsavel_cpf: data.responsavel_cpf || ''
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
      await mantenedoraAPI.update(formData);
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
