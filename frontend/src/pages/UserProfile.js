import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';
import { useAuth } from '@/contexts/AuthContext';
import { profilesAPI, uploadAPI } from '@/services/api';
import { 
  Home, User, Edit, Plus, Trash2, MapPin, Phone, Mail, Globe, Linkedin,
  Briefcase, GraduationCap, Award, Star, Camera, Lock, Unlock, Save, X,
  Calendar, Building2, CheckCircle, AlertCircle
} from 'lucide-react';

// Mapa de roles para exibição
const ROLE_LABELS = {
  admin: 'Administrador',
  secretario: 'Secretário(a)',
  diretor: 'Diretor(a)',
  coordenador: 'Coordenador(a)',
  professor: 'Professor(a)',
  semed: 'SEMED'
};

export const UserProfile = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { userId } = useParams(); // Se tiver userId na URL, é perfil de outro usuário
  
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  
  // Modals
  const [showEditModal, setShowEditModal] = useState(false);
  const [showExperienceModal, setShowExperienceModal] = useState(false);
  const [showEducationModal, setShowEducationModal] = useState(false);
  const [showSkillModal, setShowSkillModal] = useState(false);
  const [showCertificationModal, setShowCertificationModal] = useState(false);
  
  // Dados em edição
  const [editData, setEditData] = useState({});
  const [editingItem, setEditingItem] = useState(null);
  
  // Verificar se é o próprio perfil ou admin
  const isOwnProfile = !userId || userId === user?.id;
  const isAdmin = user?.role === 'admin';
  const canEdit = isOwnProfile || isAdmin;

  useEffect(() => {
    loadProfile();
  }, [userId]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      let data;
      if (userId && userId !== user?.id) {
        data = await profilesAPI.getByUserId(userId);
      } else {
        data = await profilesAPI.getMyProfile();
      }
      setProfile(data);
    } catch (error) {
      console.error('Erro ao carregar perfil:', error);
      showAlert('error', 'Erro ao carregar perfil');
    } finally {
      setLoading(false);
    }
  };

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  };

  const handleSaveProfile = async () => {
    try {
      setSaving(true);
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile(editData)
        : await profilesAPI.updateProfile(userId, editData);
      setProfile({ ...profile, ...updatedProfile });
      setShowEditModal(false);
      showAlert('success', 'Perfil atualizado com sucesso!');
    } catch (error) {
      console.error('Erro ao salvar perfil:', error);
      showAlert('error', 'Erro ao salvar perfil');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleVisibility = async () => {
    try {
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ is_public: !profile.is_public })
        : await profilesAPI.updateProfile(userId, { is_public: !profile.is_public });
      setProfile({ ...profile, ...updatedProfile });
      showAlert('success', `Perfil agora é ${updatedProfile.is_public ? 'público' : 'privado'}`);
    } catch (error) {
      showAlert('error', 'Erro ao alterar visibilidade');
    }
  };

  // Experiência
  const handleSaveExperience = async () => {
    try {
      setSaving(true);
      let experiencias = [...(profile.experiencias || [])];
      
      if (editingItem) {
        const index = experiencias.findIndex(e => e.id === editingItem.id);
        if (index !== -1) {
          experiencias[index] = { ...editingItem, ...editData };
        }
      } else {
        experiencias.push({ id: crypto.randomUUID(), ...editData });
      }
      
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ experiencias })
        : await profilesAPI.updateProfile(userId, { experiencias });
      setProfile({ ...profile, ...updatedProfile });
      setShowExperienceModal(false);
      setEditData({});
      setEditingItem(null);
      showAlert('success', 'Experiência salva!');
    } catch (error) {
      showAlert('error', 'Erro ao salvar experiência');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteExperience = async (id) => {
    if (!confirm('Deseja remover esta experiência?')) return;
    try {
      const experiencias = (profile.experiencias || []).filter(e => e.id !== id);
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ experiencias })
        : await profilesAPI.updateProfile(userId, { experiencias });
      setProfile({ ...profile, ...updatedProfile });
      showAlert('success', 'Experiência removida');
    } catch (error) {
      showAlert('error', 'Erro ao remover experiência');
    }
  };

  // Formação
  const handleSaveEducation = async () => {
    try {
      setSaving(true);
      let formacoes = [...(profile.formacoes || [])];
      
      if (editingItem) {
        const index = formacoes.findIndex(e => e.id === editingItem.id);
        if (index !== -1) {
          formacoes[index] = { ...editingItem, ...editData };
        }
      } else {
        formacoes.push({ id: crypto.randomUUID(), ...editData });
      }
      
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ formacoes })
        : await profilesAPI.updateProfile(userId, { formacoes });
      setProfile({ ...profile, ...updatedProfile });
      setShowEducationModal(false);
      setEditData({});
      setEditingItem(null);
      showAlert('success', 'Formação salva!');
    } catch (error) {
      showAlert('error', 'Erro ao salvar formação');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteEducation = async (id) => {
    if (!confirm('Deseja remover esta formação?')) return;
    try {
      const formacoes = (profile.formacoes || []).filter(e => e.id !== id);
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ formacoes })
        : await profilesAPI.updateProfile(userId, { formacoes });
      setProfile({ ...profile, ...updatedProfile });
      showAlert('success', 'Formação removida');
    } catch (error) {
      showAlert('error', 'Erro ao remover formação');
    }
  };

  // Competências
  const handleSaveSkill = async () => {
    try {
      setSaving(true);
      let competencias = [...(profile.competencias || [])];
      
      if (editingItem) {
        const index = competencias.findIndex(e => e.id === editingItem.id);
        if (index !== -1) {
          competencias[index] = { ...editingItem, ...editData };
        }
      } else {
        competencias.push({ id: crypto.randomUUID(), ...editData });
      }
      
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ competencias })
        : await profilesAPI.updateProfile(userId, { competencias });
      setProfile({ ...profile, ...updatedProfile });
      setShowSkillModal(false);
      setEditData({});
      setEditingItem(null);
      showAlert('success', 'Competência salva!');
    } catch (error) {
      showAlert('error', 'Erro ao salvar competência');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSkill = async (id) => {
    if (!confirm('Deseja remover esta competência?')) return;
    try {
      const competencias = (profile.competencias || []).filter(e => e.id !== id);
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ competencias })
        : await profilesAPI.updateProfile(userId, { competencias });
      setProfile({ ...profile, ...updatedProfile });
      showAlert('success', 'Competência removida');
    } catch (error) {
      showAlert('error', 'Erro ao remover competência');
    }
  };

  // Certificações
  const handleSaveCertification = async () => {
    try {
      setSaving(true);
      let certificacoes = [...(profile.certificacoes || [])];
      
      if (editingItem) {
        const index = certificacoes.findIndex(e => e.id === editingItem.id);
        if (index !== -1) {
          certificacoes[index] = { ...editingItem, ...editData };
        }
      } else {
        certificacoes.push({ id: crypto.randomUUID(), ...editData });
      }
      
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ certificacoes })
        : await profilesAPI.updateProfile(userId, { certificacoes });
      setProfile({ ...profile, ...updatedProfile });
      setShowCertificationModal(false);
      setEditData({});
      setEditingItem(null);
      showAlert('success', 'Certificação salva!');
    } catch (error) {
      showAlert('error', 'Erro ao salvar certificação');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCertification = async (id) => {
    if (!confirm('Deseja remover esta certificação?')) return;
    try {
      const certificacoes = (profile.certificacoes || []).filter(e => e.id !== id);
      const updatedProfile = isOwnProfile 
        ? await profilesAPI.updateMyProfile({ certificacoes })
        : await profilesAPI.updateProfile(userId, { certificacoes });
      setProfile({ ...profile, ...updatedProfile });
      showAlert('success', 'Certificação removida');
    } catch (error) {
      showAlert('error', 'Erro ao remover certificação');
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  if (!profile) {
    return (
      <Layout>
        <div className="text-center py-12">
          <User size={48} className="mx-auto text-gray-400 mb-4" />
          <p className="text-gray-600">Perfil não encontrado</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Alert */}
        {alert && (
          <div className={`p-4 rounded-lg flex items-center gap-2 ${
            alert.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {alert.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
            {alert.message}
          </div>
        )}

        {/* Header com botão Início */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
            className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <Home size={18} />
            <span>Início</span>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <User className="text-blue-600" />
              {isOwnProfile ? 'Meu Perfil' : 'Perfil do Usuário'}
            </h1>
          </div>
        </div>

        {/* Banner/Cover - Similar ao LinkedIn */}
        <div className="relative">
          <div 
            className="h-48 bg-gradient-to-r from-blue-600 to-blue-800 rounded-t-xl"
            style={profile.foto_capa_url ? { 
              backgroundImage: `url(${profile.foto_capa_url})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center'
            } : {}}
          />
          
          {/* Avatar */}
          <div className="absolute -bottom-16 left-8">
            <div className="relative">
              {profile.foto_url || profile.user?.avatar_url ? (
                <img 
                  src={profile.foto_url || profile.user?.avatar_url}
                  alt="Avatar"
                  className="w-32 h-32 rounded-full border-4 border-white object-cover bg-white"
                />
              ) : (
                <div className="w-32 h-32 rounded-full border-4 border-white bg-gray-200 flex items-center justify-center">
                  <User size={48} className="text-gray-400" />
                </div>
              )}
              {canEdit && (
                <button 
                  className="absolute bottom-0 right-0 bg-blue-600 text-white p-2 rounded-full hover:bg-blue-700"
                  onClick={() => {
                    setEditData({ ...profile });
                    setShowEditModal(true);
                  }}
                >
                  <Camera size={16} />
                </button>
              )}
            </div>
          </div>
          
          {/* Visibilidade e Edição */}
          {canEdit && (
            <div className="absolute top-4 right-4 flex gap-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={handleToggleVisibility}
                className="bg-white/90"
              >
                {profile.is_public ? <Unlock size={16} className="mr-1" /> : <Lock size={16} className="mr-1" />}
                {profile.is_public ? 'Público' : 'Privado'}
              </Button>
              <Button 
                size="sm"
                onClick={() => {
                  setEditData({ ...profile });
                  setShowEditModal(true);
                }}
                className="bg-white/90 text-gray-800 hover:bg-white"
              >
                <Edit size={16} className="mr-1" />
                Editar
              </Button>
            </div>
          )}
        </div>

        {/* Informações Principais - Card */}
        <Card className="pt-20">
          <CardContent className="space-y-4">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">
                {profile.user?.full_name || 'Usuário'}
              </h2>
              <p className="text-lg text-gray-600">
                {profile.headline || ROLE_LABELS[profile.user?.role] || 'Sem título'}
              </p>
              
              <div className="flex flex-wrap gap-4 mt-3 text-sm text-gray-500">
                {profile.localizacao && (
                  <span className="flex items-center gap-1">
                    <MapPin size={14} />
                    {profile.localizacao}
                  </span>
                )}
                {profile.user?.email && (
                  <span className="flex items-center gap-1">
                    <Mail size={14} />
                    {profile.user.email}
                  </span>
                )}
                {profile.telefone && (
                  <span className="flex items-center gap-1">
                    <Phone size={14} />
                    {profile.telefone}
                  </span>
                )}
              </div>
              
              {/* Links */}
              <div className="flex gap-3 mt-3">
                {profile.website && (
                  <a 
                    href={profile.website} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    <Globe size={16} />
                    Website
                  </a>
                )}
                {profile.linkedin_url && (
                  <a 
                    href={profile.linkedin_url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    <Linkedin size={16} />
                    LinkedIn
                  </a>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Sobre */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <User className="text-blue-600" />
              Sobre
            </CardTitle>
            {canEdit && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setEditData({ sobre: profile.sobre || '' });
                  setShowEditModal(true);
                }}
              >
                <Edit size={16} />
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {profile.sobre ? (
              <p className="text-gray-700 whitespace-pre-line">{profile.sobre}</p>
            ) : (
              <p className="text-gray-400 italic">
                {canEdit ? 'Clique em editar para adicionar uma descrição sobre você.' : 'Nenhuma descrição adicionada.'}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Experiência */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="text-blue-600" />
              Experiência
            </CardTitle>
            {canEdit && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setEditData({});
                  setEditingItem(null);
                  setShowExperienceModal(true);
                }}
              >
                <Plus size={16} />
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {(profile.experiencias || []).length === 0 ? (
              <p className="text-gray-400 italic">
                {canEdit ? 'Adicione suas experiências profissionais.' : 'Nenhuma experiência adicionada.'}
              </p>
            ) : (
              <div className="space-y-6">
                {(profile.experiencias || []).map((exp) => (
                  <div key={exp.id} className="flex gap-4 group">
                    <div className="flex-shrink-0">
                      <div className="w-12 h-12 bg-gray-100 rounded flex items-center justify-center">
                        <Building2 className="text-gray-400" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="font-semibold text-gray-900">{exp.titulo}</h4>
                          <p className="text-gray-700">{exp.instituicao}</p>
                          {exp.local && <p className="text-sm text-gray-500">{exp.local}</p>}
                          <p className="text-sm text-gray-500">
                            {exp.data_inicio || 'N/A'} - {exp.atual ? 'Presente' : (exp.data_fim || 'N/A')}
                          </p>
                        </div>
                        {canEdit && (
                          <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                            <button 
                              onClick={() => {
                                setEditData(exp);
                                setEditingItem(exp);
                                setShowExperienceModal(true);
                              }}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Edit size={16} className="text-gray-500" />
                            </button>
                            <button 
                              onClick={() => handleDeleteExperience(exp.id)}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Trash2 size={16} className="text-red-500" />
                            </button>
                          </div>
                        )}
                      </div>
                      {exp.descricao && (
                        <p className="text-gray-600 mt-2 text-sm whitespace-pre-line">{exp.descricao}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Formação */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <GraduationCap className="text-blue-600" />
              Formação
            </CardTitle>
            {canEdit && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setEditData({});
                  setEditingItem(null);
                  setShowEducationModal(true);
                }}
              >
                <Plus size={16} />
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {(profile.formacoes || []).length === 0 ? (
              <p className="text-gray-400 italic">
                {canEdit ? 'Adicione sua formação acadêmica.' : 'Nenhuma formação adicionada.'}
              </p>
            ) : (
              <div className="space-y-6">
                {(profile.formacoes || []).map((edu) => (
                  <div key={edu.id} className="flex gap-4 group">
                    <div className="flex-shrink-0">
                      <div className="w-12 h-12 bg-gray-100 rounded flex items-center justify-center">
                        <GraduationCap className="text-gray-400" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="font-semibold text-gray-900">{edu.instituicao}</h4>
                          <p className="text-gray-700">{edu.grau}{edu.area ? ` - ${edu.area}` : ''}</p>
                          <p className="text-sm text-gray-500">
                            {edu.data_inicio || 'N/A'} - {edu.data_fim || 'Presente'}
                          </p>
                        </div>
                        {canEdit && (
                          <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                            <button 
                              onClick={() => {
                                setEditData(edu);
                                setEditingItem(edu);
                                setShowEducationModal(true);
                              }}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Edit size={16} className="text-gray-500" />
                            </button>
                            <button 
                              onClick={() => handleDeleteEducation(edu.id)}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Trash2 size={16} className="text-red-500" />
                            </button>
                          </div>
                        )}
                      </div>
                      {edu.descricao && (
                        <p className="text-gray-600 mt-2 text-sm whitespace-pre-line">{edu.descricao}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Competências */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Star className="text-blue-600" />
              Competências
            </CardTitle>
            {canEdit && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setEditData({});
                  setEditingItem(null);
                  setShowSkillModal(true);
                }}
              >
                <Plus size={16} />
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {(profile.competencias || []).length === 0 ? (
              <p className="text-gray-400 italic">
                {canEdit ? 'Adicione suas competências e habilidades.' : 'Nenhuma competência adicionada.'}
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {(profile.competencias || []).map((skill) => (
                  <div 
                    key={skill.id} 
                    className="group bg-blue-50 text-blue-700 px-3 py-1.5 rounded-full flex items-center gap-2"
                  >
                    <span>{skill.nome}</span>
                    {skill.nivel && (
                      <span className="text-xs bg-blue-100 px-2 py-0.5 rounded">
                        {skill.nivel}
                      </span>
                    )}
                    {canEdit && (
                      <button 
                        onClick={() => handleDeleteSkill(skill.id)}
                        className="opacity-0 group-hover:opacity-100 hover:text-red-500"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Certificações */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Award className="text-blue-600" />
              Licenças e Certificações
            </CardTitle>
            {canEdit && (
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => {
                  setEditData({});
                  setEditingItem(null);
                  setShowCertificationModal(true);
                }}
              >
                <Plus size={16} />
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {(profile.certificacoes || []).length === 0 ? (
              <p className="text-gray-400 italic">
                {canEdit ? 'Adicione suas certificações e licenças.' : 'Nenhuma certificação adicionada.'}
              </p>
            ) : (
              <div className="space-y-4">
                {(profile.certificacoes || []).map((cert) => (
                  <div key={cert.id} className="flex gap-4 group">
                    <div className="flex-shrink-0">
                      <div className="w-12 h-12 bg-gray-100 rounded flex items-center justify-center">
                        <Award className="text-gray-400" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h4 className="font-semibold text-gray-900">{cert.nome}</h4>
                          <p className="text-gray-700">{cert.organizacao}</p>
                          <p className="text-sm text-gray-500">
                            Emissão: {cert.data_emissao || 'N/A'}
                            {cert.data_validade && ` • Validade: ${cert.data_validade}`}
                          </p>
                        </div>
                        {canEdit && (
                          <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                            <button 
                              onClick={() => {
                                setEditData(cert);
                                setEditingItem(cert);
                                setShowCertificationModal(true);
                              }}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Edit size={16} className="text-gray-500" />
                            </button>
                            <button 
                              onClick={() => handleDeleteCertification(cert.id)}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              <Trash2 size={16} className="text-red-500" />
                            </button>
                          </div>
                        )}
                      </div>
                      {cert.url && (
                        <a 
                          href={cert.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-blue-600 hover:underline mt-1 inline-block"
                        >
                          Ver credencial
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Modal - Editar Perfil */}
        <Modal
          isOpen={showEditModal}
          onClose={() => setShowEditModal(false)}
          title="Editar Perfil"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Título Profissional</label>
              <input
                type="text"
                value={editData.headline || ''}
                onChange={(e) => setEditData({ ...editData, headline: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Ex: Professor de Matemática"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sobre</label>
              <textarea
                value={editData.sobre || ''}
                onChange={(e) => setEditData({ ...editData, sobre: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 h-32 resize-none"
                placeholder="Fale um pouco sobre você..."
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Localização</label>
                <input
                  type="text"
                  value={editData.localizacao || ''}
                  onChange={(e) => setEditData({ ...editData, localizacao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Cidade, Estado"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Telefone</label>
                <input
                  type="text"
                  value={editData.telefone || ''}
                  onChange={(e) => setEditData({ ...editData, telefone: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="(00) 00000-0000"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Website</label>
                <input
                  type="url"
                  value={editData.website || ''}
                  onChange={(e) => setEditData({ ...editData, website: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="https://..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">LinkedIn</label>
                <input
                  type="url"
                  value={editData.linkedin_url || ''}
                  onChange={(e) => setEditData({ ...editData, linkedin_url: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="https://linkedin.com/in/..."
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setShowEditModal(false)}>Cancelar</Button>
              <Button onClick={handleSaveProfile} disabled={saving}>
                <Save size={16} className="mr-1" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Modal - Experiência */}
        <Modal
          isOpen={showExperienceModal}
          onClose={() => { setShowExperienceModal(false); setEditingItem(null); setEditData({}); }}
          title={editingItem ? 'Editar Experiência' : 'Adicionar Experiência'}
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Cargo *</label>
              <input
                type="text"
                value={editData.titulo || ''}
                onChange={(e) => setEditData({ ...editData, titulo: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Ex: Professor de Matemática"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Instituição *</label>
              <input
                type="text"
                value={editData.instituicao || ''}
                onChange={(e) => setEditData({ ...editData, instituicao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Nome da escola ou instituição"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Local</label>
              <input
                type="text"
                value={editData.local || ''}
                onChange={(e) => setEditData({ ...editData, local: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Cidade, Estado"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Início</label>
                <input
                  type="month"
                  value={editData.data_inicio || ''}
                  onChange={(e) => setEditData({ ...editData, data_inicio: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Término</label>
                <input
                  type="month"
                  value={editData.data_fim || ''}
                  onChange={(e) => setEditData({ ...editData, data_fim: e.target.value })}
                  disabled={editData.atual}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="atual"
                checked={editData.atual || false}
                onChange={(e) => setEditData({ ...editData, atual: e.target.checked, data_fim: e.target.checked ? null : editData.data_fim })}
                className="rounded border-gray-300"
              />
              <label htmlFor="atual" className="text-sm text-gray-700">Trabalho aqui atualmente</label>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Descrição</label>
              <textarea
                value={editData.descricao || ''}
                onChange={(e) => setEditData({ ...editData, descricao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 h-24 resize-none"
                placeholder="Descreva suas atividades..."
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => { setShowExperienceModal(false); setEditingItem(null); setEditData({}); }}>Cancelar</Button>
              <Button onClick={handleSaveExperience} disabled={saving || !editData.titulo || !editData.instituicao}>
                <Save size={16} className="mr-1" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Modal - Formação */}
        <Modal
          isOpen={showEducationModal}
          onClose={() => { setShowEducationModal(false); setEditingItem(null); setEditData({}); }}
          title={editingItem ? 'Editar Formação' : 'Adicionar Formação'}
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Instituição *</label>
              <input
                type="text"
                value={editData.instituicao || ''}
                onChange={(e) => setEditData({ ...editData, instituicao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Nome da universidade ou instituição"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Grau *</label>
                <select
                  value={editData.grau || ''}
                  onChange={(e) => setEditData({ ...editData, grau: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione</option>
                  <option value="Ensino Médio">Ensino Médio</option>
                  <option value="Técnico">Técnico</option>
                  <option value="Graduação">Graduação</option>
                  <option value="Pós-graduação">Pós-graduação</option>
                  <option value="MBA">MBA</option>
                  <option value="Mestrado">Mestrado</option>
                  <option value="Doutorado">Doutorado</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Área</label>
                <input
                  type="text"
                  value={editData.area || ''}
                  onChange={(e) => setEditData({ ...editData, area: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Ex: Pedagogia"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano de Início</label>
                <input
                  type="number"
                  value={editData.data_inicio || ''}
                  onChange={(e) => setEditData({ ...editData, data_inicio: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="2020"
                  min="1950"
                  max="2030"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano de Conclusão</label>
                <input
                  type="number"
                  value={editData.data_fim || ''}
                  onChange={(e) => setEditData({ ...editData, data_fim: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="2024"
                  min="1950"
                  max="2030"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Descrição</label>
              <textarea
                value={editData.descricao || ''}
                onChange={(e) => setEditData({ ...editData, descricao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 h-24 resize-none"
                placeholder="Atividades, honras, etc."
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => { setShowEducationModal(false); setEditingItem(null); setEditData({}); }}>Cancelar</Button>
              <Button onClick={handleSaveEducation} disabled={saving || !editData.instituicao || !editData.grau}>
                <Save size={16} className="mr-1" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Modal - Competência */}
        <Modal
          isOpen={showSkillModal}
          onClose={() => { setShowSkillModal(false); setEditingItem(null); setEditData({}); }}
          title="Adicionar Competência"
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Competência *</label>
              <input
                type="text"
                value={editData.nome || ''}
                onChange={(e) => setEditData({ ...editData, nome: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Ex: Didática, Gestão de sala de aula"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nível</label>
              <select
                value={editData.nivel || ''}
                onChange={(e) => setEditData({ ...editData, nivel: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione (opcional)</option>
                <option value="basico">Básico</option>
                <option value="intermediario">Intermediário</option>
                <option value="avancado">Avançado</option>
                <option value="especialista">Especialista</option>
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => { setShowSkillModal(false); setEditingItem(null); setEditData({}); }}>Cancelar</Button>
              <Button onClick={handleSaveSkill} disabled={saving || !editData.nome}>
                <Save size={16} className="mr-1" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </Modal>

        {/* Modal - Certificação */}
        <Modal
          isOpen={showCertificationModal}
          onClose={() => { setShowCertificationModal(false); setEditingItem(null); setEditData({}); }}
          title={editingItem ? 'Editar Certificação' : 'Adicionar Certificação'}
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome da Certificação *</label>
              <input
                type="text"
                value={editData.nome || ''}
                onChange={(e) => setEditData({ ...editData, nome: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Ex: Curso de Alfabetização"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Organização Emissora *</label>
              <input
                type="text"
                value={editData.organizacao || ''}
                onChange={(e) => setEditData({ ...editData, organizacao: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Ex: MEC, Coursera, etc."
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Emissão</label>
                <input
                  type="month"
                  value={editData.data_emissao || ''}
                  onChange={(e) => setEditData({ ...editData, data_emissao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Validade</label>
                <input
                  type="month"
                  value={editData.data_validade || ''}
                  onChange={(e) => setEditData({ ...editData, data_validade: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">URL da Credencial</label>
              <input
                type="url"
                value={editData.url || ''}
                onChange={(e) => setEditData({ ...editData, url: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="https://..."
              />
            </div>
            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => { setShowCertificationModal(false); setEditingItem(null); setEditData({}); }}>Cancelar</Button>
              <Button onClick={handleSaveCertification} disabled={saving || !editData.nome || !editData.organizacao}>
                <Save size={16} className="mr-1" />
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
};

export default UserProfile;
