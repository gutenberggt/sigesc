from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone
import uuid

# ============= AUTH MODELS =============

class SchoolLink(BaseModel):
    """Vínculo de usuário com escola"""
    school_id: str
    roles: List[str] = []  # Pode ter múltiplos papéis na mesma escola
    class_ids: Optional[List[str]] = []  # Turmas vinculadas (para professores/coordenadores)

class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    role: Literal['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'aluno', 'responsavel', 'semed']
    status: Literal['active', 'inactive'] = 'active'
    avatar_url: Optional[str] = None
    school_links: List[SchoolLink] = []

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: Literal['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'aluno', 'responsavel', 'semed']
    school_links: List[SchoolLink] = []

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[Literal['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'aluno', 'responsavel', 'semed']] = None
    status: Optional[Literal['active', 'inactive']] = None
    avatar_url: Optional[str] = None
    school_links: Optional[List[SchoolLink]] = None

class User(UserBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserInDB(User):
    password_hash: str

class UserResponse(User):
    """Resposta sem password_hash"""
    pass

# Auth requests/responses
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# ============= USER PROFILE MODELS =============

class ProfileExperience(BaseModel):
    """Experiência profissional do usuário"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    titulo: str
    instituicao: str
    local: Optional[str] = None
    data_inicio: Optional[str] = None  # YYYY-MM
    data_fim: Optional[str] = None  # YYYY-MM ou None se atual
    atual: bool = False
    descricao: Optional[str] = None

class ProfileEducation(BaseModel):
    """Formação acadêmica do usuário"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instituicao: str
    grau: str  # Graduação, Pós-graduação, Mestrado, Doutorado, etc.
    area: Optional[str] = None
    data_inicio: Optional[str] = None  # YYYY
    data_fim: Optional[str] = None  # YYYY
    descricao: Optional[str] = None

class ProfileSkill(BaseModel):
    """Competência/Habilidade do usuário"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    nivel: Optional[Literal['basico', 'intermediario', 'avancado', 'especialista']] = None

class ProfileCertification(BaseModel):
    """Certificação do usuário"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    organizacao: str
    data_emissao: Optional[str] = None  # YYYY-MM
    data_validade: Optional[str] = None  # YYYY-MM
    url: Optional[str] = None

class UserProfileBase(BaseModel):
    """Perfil do usuário - similar ao LinkedIn"""
    # Informações Básicas (header)
    headline: Optional[str] = None  # Título profissional
    sobre: Optional[str] = None  # Sobre mim / Resumo
    localizacao: Optional[str] = None  # Cidade/Estado
    
    # Contato
    telefone: Optional[str] = None
    website: Optional[str] = None
    
    # Redes Sociais
    linkedin_url: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    whatsapp: Optional[str] = None  # Número do WhatsApp
    
    # Foto de capa e avatar
    foto_capa_url: Optional[str] = None
    foto_url: Optional[str] = None
    
    # Visibilidade
    is_public: bool = True  # Perfil público por padrão
    
    # Dados profissionais
    experiencias: List[ProfileExperience] = []
    formacoes: List[ProfileEducation] = []
    competencias: List[ProfileSkill] = []
    certificacoes: List[ProfileCertification] = []

class UserProfileCreate(UserProfileBase):
    user_id: str

class UserProfileUpdate(BaseModel):
    headline: Optional[str] = None
    sobre: Optional[str] = None
    localizacao: Optional[str] = None
    telefone: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    whatsapp: Optional[str] = None
    foto_capa_url: Optional[str] = None
    foto_url: Optional[str] = None
    is_public: Optional[bool] = None
    experiencias: Optional[List[ProfileExperience]] = None
    formacoes: Optional[List[ProfileEducation]] = None
    competencias: Optional[List[ProfileSkill]] = None
    certificacoes: Optional[List[ProfileCertification]] = None

class UserProfile(UserProfileBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= CONNECTION MODELS =============

class ConnectionBase(BaseModel):
    """Conexão entre dois usuários"""
    requester_id: str  # Quem enviou o convite
    receiver_id: str   # Quem recebeu o convite
    status: Literal['pending', 'accepted', 'rejected'] = 'pending'
    message: Optional[str] = None  # Mensagem opcional no convite

class ConnectionCreate(BaseModel):
    receiver_id: str
    message: Optional[str] = None

class Connection(ConnectionBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

class ConnectionResponse(BaseModel):
    """Resposta de conexão com dados do usuário"""
    id: str
    user_id: str
    full_name: str
    email: str
    role: str
    headline: Optional[str] = None
    foto_url: Optional[str] = None
    status: str
    connected_at: Optional[datetime] = None

# ============= MESSAGE MODELS =============

class MessageAttachment(BaseModel):
    """Anexo de mensagem (PDF ou imagem)"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal['image', 'pdf']
    url: str
    filename: str
    size: Optional[int] = None

class MessageBase(BaseModel):
    """Mensagem entre usuários conectados"""
    sender_id: str
    receiver_id: str
    content: Optional[str] = None  # Texto da mensagem
    attachments: Optional[List[MessageAttachment]] = []
    is_read: bool = False

class MessageCreate(BaseModel):
    receiver_id: str
    content: Optional[str] = None
    attachments: Optional[List[dict]] = []

class Message(MessageBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MessageResponse(BaseModel):
    """Resposta de mensagem com dados do remetente"""
    id: str
    sender_id: str
    sender_name: str
    sender_foto_url: Optional[str] = None
    receiver_id: str
    content: Optional[str] = None
    attachments: Optional[List[MessageAttachment]] = []
    is_read: bool
    created_at: datetime

class ConversationResponse(BaseModel):
    """Resumo de uma conversa"""
    connection_id: str
    user_id: str
    full_name: str
    foto_url: Optional[str] = None
    headline: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int = 0

# ============= MESSAGE LOG MODELS =============

class MessageLog(BaseModel):
    """Log permanente de mensagens para compliance (retenção 30 dias após exclusão)"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_message_id: str
    connection_id: str
    sender_id: str
    sender_name: str
    sender_email: str
    receiver_id: str
    receiver_name: str
    receiver_email: str
    content: Optional[str] = None
    attachments: Optional[List[dict]] = []  # URLs dos arquivos preservados
    created_at: datetime  # Data original da mensagem
    logged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: Optional[datetime] = None  # Quando foi excluída (se aplicável)
    expires_at: Optional[datetime] = None  # 30 dias após exclusão

class ConversationLog(BaseModel):
    """Log de uma conversa completa"""
    user_id: str
    user_name: str
    user_email: str
    conversations: List[dict] = []  # Lista de conversas com seus participantes
    total_messages: int = 0
    total_attachments: int = 0
    date_range: Optional[dict] = None  # { start: date, end: date }

# ============= ANNOUNCEMENT MODELS =============

class AnnouncementRecipient(BaseModel):
    """Destinatário de um aviso"""
    type: Literal['role', 'school', 'class', 'individual']  # Tipo de destinatário
    # Para type='role': target_roles contém os papéis (ex: ['professor', 'secretario'])
    # Para type='school': school_ids contém IDs das escolas
    # Para type='class': class_ids contém IDs das turmas
    # Para type='individual': user_ids contém IDs dos usuários
    target_roles: Optional[List[str]] = []
    school_ids: Optional[List[str]] = []
    class_ids: Optional[List[str]] = []
    user_ids: Optional[List[str]] = []

class AnnouncementBase(BaseModel):
    """Aviso/comunicado"""
    title: str
    content: str
    recipient: AnnouncementRecipient

class AnnouncementCreate(AnnouncementBase):
    """Criação de aviso"""
    pass

class AnnouncementUpdate(BaseModel):
    """Atualização de aviso"""
    title: Optional[str] = None
    content: Optional[str] = None
    recipient: Optional[AnnouncementRecipient] = None

class Announcement(AnnouncementBase):
    """Aviso completo"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str
    sender_name: str
    sender_role: str
    sender_foto_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

class AnnouncementResponse(BaseModel):
    """Resposta de aviso com status de leitura"""
    id: str
    title: str
    content: str
    recipient: AnnouncementRecipient
    sender_id: str
    sender_name: str
    sender_role: str
    sender_foto_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_read: bool = False
    read_at: Optional[datetime] = None

class AnnouncementReadStatus(BaseModel):
    """Status de leitura de um aviso por um usuário"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    announcement_id: str
    user_id: str
    read_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class NotificationCount(BaseModel):
    """Contagem de notificações não lidas"""
    unread_messages: int = 0
    unread_announcements: int = 0
    total: int = 0

# ============= SCHOOL MODELS =============

class SchoolBase(BaseModel):
    # Dados Gerais - Identificação
    name: str
    inep_code: Optional[str] = None
    sigla: Optional[str] = None
    caracteristica_escolar: Optional[str] = None
    zona_localizacao: Optional[Literal['urbana', 'rural']] = None
    cnpj: Optional[str] = None
    situacao_funcionamento: Optional[str] = 'Em atividade'
    
    # Tipo de Unidade (Sede/Anexa)
    tipo_unidade: Optional[Literal['sede', 'anexa']] = 'sede'
    anexa_a: Optional[str] = None  # ID da escola sede (quando tipo_unidade = 'anexa')
    
    # Dados Gerais - Localização
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    distrito: Optional[str] = None
    estado: Optional[str] = None
    ddd_telefone: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    
    # Dados Gerais - Contatos
    email: Optional[str] = None
    site: Optional[str] = None
    
    # Dados Gerais - Georreferenciamento
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    
    # Dados Gerais - Regras
    bloquear_lancamento_anos_encerrados: Optional[bool] = False
    usar_regra_alternativa: Optional[bool] = False
    
    # Dados Gerais - Vinculação
    dependencia_administrativa: Optional[str] = None
    orgao_responsavel: Optional[str] = None
    regulamentacao: Optional[str] = None
    esfera_administrativa: Optional[str] = None
    
    # Dados Gerais - Mantenedora
    categoria_mantenedora: Optional[str] = None
    cnpj_mantenedora: Optional[str] = None
    forma_contratacao_estadual: Optional[str] = None
    forma_contratacao_municipal: Optional[str] = None
    possui_convenio: Optional[bool] = False
    
    # Dados Gerais - Equipe
    secretario_escolar: Optional[str] = None
    gestor_principal: Optional[str] = None
    cargo_gestor: Optional[str] = None
    
    # Dados Gerais - Oferta
    niveis_ensino_oferecidos: List[str] = []
    anos_letivos_ativos: List[int] = []
    
    # Educação Infantil - Sub-níveis
    educacao_infantil_bercario: Optional[bool] = False
    educacao_infantil_maternal_i: Optional[bool] = False
    educacao_infantil_maternal_ii: Optional[bool] = False
    educacao_infantil_pre_i: Optional[bool] = False
    educacao_infantil_pre_ii: Optional[bool] = False
    
    # Fundamental Anos Iniciais - Sub-níveis
    fundamental_inicial_1ano: Optional[bool] = False
    fundamental_inicial_2ano: Optional[bool] = False
    fundamental_inicial_3ano: Optional[bool] = False
    fundamental_inicial_4ano: Optional[bool] = False
    fundamental_inicial_5ano: Optional[bool] = False
    
    # Fundamental Anos Finais - Sub-níveis
    fundamental_final_6ano: Optional[bool] = False
    fundamental_final_7ano: Optional[bool] = False
    fundamental_final_8ano: Optional[bool] = False
    fundamental_final_9ano: Optional[bool] = False
    
    # EJA Anos Iniciais - Sub-níveis
    eja_inicial_1etapa: Optional[bool] = False
    eja_inicial_2etapa: Optional[bool] = False
    
    # EJA Anos Finais - Sub-níveis
    eja_final_3etapa: Optional[bool] = False
    eja_final_4etapa: Optional[bool] = False
    
    # Infraestrutura - Serviços
    abastecimento_agua: Optional[str] = None
    energia_eletrica: Optional[str] = None
    saneamento: Optional[str] = None
    coleta_lixo: Optional[str] = None
    
    # Infraestrutura - Acessibilidade
    possui_rampas: Optional[bool] = False
    possui_corrimao: Optional[bool] = False
    banheiros_adaptados: Optional[bool] = False
    sinalizacao_tatil: Optional[bool] = False
    
    # Infraestrutura - Segurança
    saidas_emergencia: Optional[int] = None
    extintores: Optional[int] = None
    brigada_incendio: Optional[bool] = False
    plano_evacuacao: Optional[bool] = False
    
    # Infraestrutura - Conectividade
    possui_internet: Optional[bool] = False
    tipo_conexao: Optional[str] = None
    cobertura_rede: Optional[str] = None
    
    # Infraestrutura - Conservação
    estado_conservacao: Optional[str] = None
    possui_cercamento: Optional[bool] = False
    
    # Dependências - Salas
    numero_salas_aula: Optional[int] = None
    capacidade_total_alunos: Optional[int] = None
    salas_recursos_multifuncionais: Optional[int] = None
    
    # Dependências - Administração
    sala_direcao: Optional[bool] = False
    sala_secretaria: Optional[bool] = False
    sala_coordenacao: Optional[bool] = False
    sala_professores: Optional[bool] = False
    
    # Dependências - Serviços
    numero_banheiros: Optional[int] = None
    banheiros_acessiveis: Optional[int] = None
    possui_cozinha: Optional[bool] = False
    possui_refeitorio: Optional[bool] = False
    possui_almoxarifado: Optional[bool] = False
    
    # Dependências - Outros
    possui_biblioteca: Optional[bool] = False
    possui_lab_ciencias: Optional[bool] = False
    possui_lab_informatica: Optional[bool] = False
    possui_quadra: Optional[bool] = False
    
    # Equipamentos - Tecnologia
    qtd_computadores: Optional[int] = None
    qtd_tablets: Optional[int] = None
    qtd_projetores: Optional[int] = None
    qtd_impressoras: Optional[int] = None
    qtd_televisores: Optional[int] = None
    qtd_projetores_multimidia: Optional[int] = None
    qtd_aparelhos_som: Optional[int] = None
    qtd_lousas_digitais: Optional[int] = None
    
    # Equipamentos - Didáticos
    possui_kits_cientificos: Optional[bool] = False
    possui_instrumentos_musicais: Optional[bool] = False
    
    # Equipamentos - Segurança
    qtd_extintores: Optional[int] = None
    qtd_cameras: Optional[int] = None
    
    # Recursos - Pedagógicos
    possui_material_didatico: Optional[bool] = False
    tamanho_acervo: Optional[int] = None
    
    # Recursos - Programas
    participa_programas_governamentais: List[str] = []
    
    # Dados do Ensino - Etapas
    educacao_infantil: Optional[bool] = False
    fundamental_anos_iniciais: Optional[bool] = False
    fundamental_anos_finais: Optional[bool] = False
    ensino_medio: Optional[bool] = False
    eja: Optional[bool] = False
    
    # Dados do Ensino - Atendimentos
    aee: Optional[bool] = False  # Atendimento educacional especializado
    atendimento_integral: Optional[bool] = False
    reforco_escolar: Optional[bool] = False
    aulas_complementares: Optional[bool] = False
    
    # Dados do Ensino - Regime
    turnos_funcionamento: List[str] = []
    organizacao_turmas: Optional[str] = None
    tipo_avaliacao: Optional[str] = None
    
    # Espaços Escolares
    possui_quadra_esportiva: Optional[bool] = False
    possui_patio: Optional[bool] = False
    possui_parque: Optional[bool] = False
    possui_brinquedoteca: Optional[bool] = False
    possui_auditorio: Optional[bool] = False
    possui_horta: Optional[bool] = False
    possui_estacionamento: Optional[bool] = False
    
    # Permissão - Data Limite de Lançamento por Bimestre
    bimestre_1_limite_lancamento: Optional[str] = None
    bimestre_2_limite_lancamento: Optional[str] = None
    bimestre_3_limite_lancamento: Optional[str] = None
    bimestre_4_limite_lancamento: Optional[str] = None
    
    # Anos Letivos da escola e seus status
    # Formato: { "2025": { "status": "aberto" }, "2026": { "status": "fechado" } }
    anos_letivos: Optional[dict] = None
    
    # Status geral
    status: Literal['active', 'inactive'] = 'active'

class SchoolCreate(SchoolBase):
    pass

class SchoolUpdate(BaseModel):
    # Todos os campos opcionais para atualização parcial
    name: Optional[str] = None
    inep_code: Optional[str] = None
    sigla: Optional[str] = None
    caracteristica_escolar: Optional[str] = None
    zona_localizacao: Optional[Literal['urbana', 'rural']] = None
    cnpj: Optional[str] = None
    situacao_funcionamento: Optional[str] = None
    
    # Tipo de Unidade
    tipo_unidade: Optional[Literal['sede', 'anexa']] = None
    anexa_a: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    distrito: Optional[str] = None
    estado: Optional[str] = None
    ddd_telefone: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    site: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    
    # Equipe
    secretario_escolar: Optional[str] = None
    gestor_principal: Optional[str] = None
    cargo_gestor: Optional[str] = None
    
    # Infraestrutura
    abastecimento_agua: Optional[str] = None
    energia_eletrica: Optional[str] = None
    saneamento: Optional[str] = None
    coleta_lixo: Optional[str] = None
    possui_rampas: Optional[bool] = None
    possui_corrimao: Optional[bool] = None
    banheiros_adaptados: Optional[bool] = None
    sinalizacao_tatil: Optional[bool] = None
    saidas_emergencia: Optional[int] = None
    extintores: Optional[int] = None
    brigada_incendio: Optional[bool] = None
    plano_evacuacao: Optional[bool] = None
    possui_internet: Optional[bool] = None
    tipo_conexao: Optional[str] = None
    cobertura_rede: Optional[str] = None
    estado_conservacao: Optional[str] = None
    possui_cercamento: Optional[bool] = None
    
    # Dependências
    numero_salas_aula: Optional[int] = None
    capacidade_total_alunos: Optional[int] = None
    salas_recursos_multifuncionais: Optional[int] = None
    sala_direcao: Optional[bool] = None
    sala_secretaria: Optional[bool] = None
    sala_coordenacao: Optional[bool] = None
    sala_professores: Optional[bool] = None
    numero_banheiros: Optional[int] = None
    banheiros_acessiveis: Optional[int] = None
    possui_cozinha: Optional[bool] = None
    possui_refeitorio: Optional[bool] = None
    possui_almoxarifado: Optional[bool] = None
    possui_biblioteca: Optional[bool] = None
    possui_lab_ciencias: Optional[bool] = None
    possui_lab_informatica: Optional[bool] = None
    possui_quadra: Optional[bool] = None
    
    # Equipamentos
    qtd_computadores: Optional[int] = None
    qtd_tablets: Optional[int] = None
    qtd_projetores: Optional[int] = None
    qtd_impressoras: Optional[int] = None
    qtd_televisores: Optional[int] = None
    qtd_projetores_multimidia: Optional[int] = None
    qtd_aparelhos_som: Optional[int] = None
    qtd_lousas_digitais: Optional[int] = None
    possui_kits_cientificos: Optional[bool] = None
    possui_instrumentos_musicais: Optional[bool] = None
    qtd_extintores: Optional[int] = None
    qtd_cameras: Optional[int] = None
    
    # Vinculação
    dependencia_administrativa: Optional[str] = None
    orgao_responsavel: Optional[str] = None
    regulamentacao: Optional[str] = None  # Autorização ou Reconhecimento
    esfera_administrativa: Optional[str] = None
    
    # Recursos
    possui_material_didatico: Optional[bool] = None
    tamanho_acervo: Optional[int] = None
    participa_programas_governamentais: Optional[List[str]] = None
    
    # Dados do Ensino - Etapas principais
    educacao_infantil: Optional[bool] = None
    fundamental_anos_iniciais: Optional[bool] = None
    fundamental_anos_finais: Optional[bool] = None
    ensino_medio: Optional[bool] = None
    eja: Optional[bool] = None
    eja_final: Optional[bool] = None
    
    # Sub-níveis Educação Infantil
    educacao_infantil_bercario: Optional[bool] = None
    educacao_infantil_maternal_i: Optional[bool] = None
    educacao_infantil_maternal_ii: Optional[bool] = None
    educacao_infantil_pre_i: Optional[bool] = None
    educacao_infantil_pre_ii: Optional[bool] = None
    
    # Sub-níveis Fundamental Inicial
    fundamental_inicial_1ano: Optional[bool] = None
    fundamental_inicial_2ano: Optional[bool] = None
    fundamental_inicial_3ano: Optional[bool] = None
    fundamental_inicial_4ano: Optional[bool] = None
    fundamental_inicial_5ano: Optional[bool] = None
    
    # Sub-níveis Fundamental Final
    fundamental_final_6ano: Optional[bool] = None
    fundamental_final_7ano: Optional[bool] = None
    fundamental_final_8ano: Optional[bool] = None
    fundamental_final_9ano: Optional[bool] = None
    
    # Sub-níveis EJA
    eja_inicial_1etapa: Optional[bool] = None
    eja_inicial_2etapa: Optional[bool] = None
    eja_final_3etapa: Optional[bool] = None
    eja_final_4etapa: Optional[bool] = None
    
    # Atendimentos
    aee: Optional[bool] = None
    atendimento_integral: Optional[bool] = None
    reforco_escolar: Optional[bool] = None
    aulas_complementares: Optional[bool] = None
    
    # Regime
    turnos_funcionamento: Optional[List[str]] = None
    organizacao_turmas: Optional[str] = None
    tipo_avaliacao: Optional[str] = None
    
    # Espaços Escolares
    possui_quadra_esportiva: Optional[bool] = None
    possui_patio: Optional[bool] = None
    possui_parque: Optional[bool] = None
    possui_brinquedoteca: Optional[bool] = None
    possui_auditorio: Optional[bool] = None
    possui_horta: Optional[bool] = None
    possui_estacionamento: Optional[bool] = None
    
    # Permissão - Data Limite de Lançamento por Bimestre
    bimestre_1_limite_lancamento: Optional[str] = None
    bimestre_2_limite_lancamento: Optional[str] = None
    bimestre_3_limite_lancamento: Optional[str] = None
    bimestre_4_limite_lancamento: Optional[str] = None
    
    # Anos Letivos da escola e seus status
    anos_letivos: Optional[dict] = None
    
    status: Optional[Literal['active', 'inactive']] = None

class School(SchoolBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= CLASS (TURMA) MODELS =============

class ClassBase(BaseModel):
    school_id: str
    academic_year: int
    name: str
    shift: Literal['morning', 'afternoon', 'evening', 'full_time']
    education_level: Optional[str] = None  # Nível de ensino (educacao_infantil, fundamental_anos_iniciais, etc.)
    grade_level: str  # Ex: "1º Ano", "6º Ano", "Berçário", etc
    teacher_ids: List[str] = []

class ClassCreate(ClassBase):
    pass

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    shift: Optional[Literal['morning', 'afternoon', 'evening', 'full_time']] = None
    education_level: Optional[str] = None
    grade_level: Optional[str] = None
    teacher_ids: Optional[List[str]] = None

class Class(ClassBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= COURSE (COMPONENTE CURRICULAR) MODELS =============

class CourseBase(BaseModel):
    # Escola (opcional para compatibilidade com dados legados)
    school_id: Optional[str] = None
    
    # Nível de Ensino (opcional para compatibilidade com dados legados)
    nivel_ensino: Optional[Literal['educacao_infantil', 'fundamental_anos_iniciais', 'fundamental_anos_finais', 'ensino_medio', 'eja', 'eja_final']] = None
    
    # Séries/Anos que usam este componente (opcional - se vazio, aplica a todas do nível)
    # Para Fundamental Anos Iniciais: não precisa preencher (é o mesmo para todos)
    # Para Fundamental Anos Finais: pode especificar séries com carga horária diferente
    grade_levels: List[str] = []  # Ex: ["6º Ano", "7º Ano"] ou vazio para todas
    
    # Atendimento/Programa (opcional)
    atendimento_programa: Optional[Literal['aee', 'atendimento_integral', 'reforco_escolar', 'aulas_complementares', 'transversal_formativa', 'recomposicao_aprendizagem']] = None
    
    # Nome do componente curricular
    name: str
    
    # Componente Optativo - não interfere na aprovação, frequência ou carga horária da série
    # Só pode ser marcado para componentes que NÃO são do atendimento "Regular" (atendimento_programa != None)
    optativo: Optional[bool] = False
    
    # Código (opcional)
    code: Optional[str] = None
    
    # Carga horária (específica para o nível/atendimento)
    workload: Optional[int] = None

class CourseCreate(CourseBase):
    pass

class CourseUpdate(BaseModel):
    school_id: Optional[str] = None
    nivel_ensino: Optional[Literal['educacao_infantil', 'fundamental_anos_iniciais', 'fundamental_anos_finais', 'ensino_medio', 'eja', 'eja_final']] = None
    grade_levels: Optional[List[str]] = None
    atendimento_programa: Optional[Literal['aee', 'atendimento_integral', 'reforco_escolar', 'aulas_complementares', 'transversal_formativa', 'recomposicao_aprendizagem']] = None
    name: Optional[str] = None
    optativo: Optional[bool] = None
    code: Optional[str] = None
    workload: Optional[int] = None

class Course(CourseBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= STUDENT MODELS =============

class AuthorizedPerson(BaseModel):
    """Pessoa autorizada a buscar o aluno"""
    name: str
    relationship: str  # Parentesco: tio, avó, vizinho, etc.
    phone: Optional[str] = None
    document: Optional[str] = None  # CPF ou RG

class StudentBase(BaseModel):
    # === IDENTIFICAÇÃO ===
    school_id: str
    enrollment_number: str  # Código interno/matrícula
    inep_code: Optional[str] = None  # Código INEP do aluno
    
    # === DADOS PESSOAIS ===
    full_name: Optional[str] = None
    birth_date: Optional[str] = None  # dd/mm/aaaa
    sex: Optional[Literal['masculino', 'feminino']] = None
    nationality: Optional[str] = 'Brasileira'
    birth_city: Optional[str] = None  # Naturalidade
    birth_state: Optional[str] = None
    color_race: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarada']] = None
    
    # === DOCUMENTOS ===
    cpf: Optional[str] = None
    rg: Optional[str] = None
    rg_issue_date: Optional[str] = None
    rg_issuer: Optional[str] = None  # Órgão emissor
    rg_state: Optional[str] = None  # Estado emissor
    nis: Optional[str] = None  # NIS/PIS/PASEP
    sus_number: Optional[str] = None  # Número do Cartão SUS
    
    # Certidão Civil
    civil_certificate_type: Optional[Literal['nascimento', 'casamento']] = None
    civil_certificate_number: Optional[str] = None
    civil_certificate_book: Optional[str] = None  # Livro
    civil_certificate_page: Optional[str] = None  # Folha
    civil_certificate_registry: Optional[str] = None  # Cartório
    civil_certificate_city: Optional[str] = None
    civil_certificate_state: Optional[str] = None
    civil_certificate_date: Optional[str] = None
    
    # Passaporte (opcional)
    passport_number: Optional[str] = None
    passport_country: Optional[str] = None
    passport_expiry: Optional[str] = None
    
    # Justificativa de ausência de documentação
    no_documents_justification: Optional[str] = None
    
    # === RESPONSÁVEIS ===
    father_name: Optional[str] = None
    father_cpf: Optional[str] = None
    father_rg: Optional[str] = None
    father_phone: Optional[str] = None
    
    mother_name: Optional[str] = None
    mother_cpf: Optional[str] = None
    mother_rg: Optional[str] = None
    mother_phone: Optional[str] = None
    
    # Responsável legal (obrigatório)
    legal_guardian_type: Optional[Literal['mother', 'father', 'both', 'other']] = None  # Mãe, Pai, Mãe e Pai, Outro
    guardian_name: Optional[str] = None
    guardian_cpf: Optional[str] = None
    guardian_rg: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_relationship: Optional[str] = None  # Parentesco
    guardian_user_id: Optional[str] = None  # Vínculo com usuário do sistema
    
    # Autorizados a buscar (até 5)
    authorized_persons: List[AuthorizedPerson] = []
    
    # === INFORMAÇÕES COMPLEMENTARES ===
    uses_school_transport: Optional[bool] = False
    transport_type: Optional[str] = None  # Tipo de veículo
    transport_route: Optional[str] = None  # Rota
    
    religion: Optional[str] = None
    benefits: List[str] = []  # Bolsa família, etc.
    
    # Deficiências/Transtornos
    has_disability: Optional[bool] = False
    disabilities: List[str] = []  # Lista de deficiências
    disability_details: Optional[str] = None
    
    is_literate: Optional[bool] = None  # Alfabetizado
    is_emancipated: Optional[bool] = False  # Emancipado
    
    # === DOCUMENTOS/ANEXOS ===
    photo_url: Optional[str] = None
    documents_urls: List[str] = []  # URLs dos documentos gerais
    medical_report_url: Optional[str] = None  # Laudo médico
    
    # === VÍNCULO ESCOLAR ===
    class_id: Optional[str] = None
    user_id: Optional[str] = None  # Se aluno tem acesso ao portal
    guardian_ids: List[str] = []  # IDs dos responsáveis no sistema
    
    # === OBSERVAÇÕES ===
    observations: Optional[str] = None
    
    # Status
    status: Literal['active', 'inactive', 'dropout', 'transferred', 'deceased'] = 'active'

class StudentCreate(StudentBase):
    pass

class StudentUpdate(BaseModel):
    # Identificação
    school_id: Optional[str] = None
    enrollment_number: Optional[str] = None
    inep_code: Optional[str] = None
    
    # Dados pessoais
    full_name: Optional[str] = None
    birth_date: Optional[str] = None
    sex: Optional[Literal['masculino', 'feminino']] = None
    nationality: Optional[str] = None
    birth_city: Optional[str] = None
    birth_state: Optional[str] = None
    color_race: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarada']] = None
    
    # Documentos
    cpf: Optional[str] = None
    rg: Optional[str] = None
    rg_issue_date: Optional[str] = None
    rg_issuer: Optional[str] = None
    rg_state: Optional[str] = None
    nis: Optional[str] = None
    sus_number: Optional[str] = None
    
    civil_certificate_type: Optional[Literal['nascimento', 'casamento']] = None
    civil_certificate_number: Optional[str] = None
    civil_certificate_book: Optional[str] = None
    civil_certificate_page: Optional[str] = None
    civil_certificate_registry: Optional[str] = None
    civil_certificate_city: Optional[str] = None
    civil_certificate_state: Optional[str] = None
    civil_certificate_date: Optional[str] = None
    
    passport_number: Optional[str] = None
    passport_country: Optional[str] = None
    passport_expiry: Optional[str] = None
    no_documents_justification: Optional[str] = None
    
    # Responsáveis
    father_name: Optional[str] = None
    father_cpf: Optional[str] = None
    father_rg: Optional[str] = None
    father_phone: Optional[str] = None
    
    mother_name: Optional[str] = None
    mother_cpf: Optional[str] = None
    mother_rg: Optional[str] = None
    mother_phone: Optional[str] = None
    
    legal_guardian_type: Optional[Literal['mother', 'father', 'both', 'other']] = None
    guardian_name: Optional[str] = None
    guardian_cpf: Optional[str] = None
    guardian_rg: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_relationship: Optional[str] = None
    guardian_user_id: Optional[str] = None
    
    authorized_persons: Optional[List[AuthorizedPerson]] = None
    
    # Informações complementares
    uses_school_transport: Optional[bool] = None
    transport_type: Optional[str] = None
    transport_route: Optional[str] = None
    religion: Optional[str] = None
    benefits: Optional[List[str]] = None
    has_disability: Optional[bool] = None
    disabilities: Optional[List[str]] = None
    disability_details: Optional[str] = None
    is_literate: Optional[bool] = None
    is_emancipated: Optional[bool] = None
    
    # Anexos
    photo_url: Optional[str] = None
    documents_urls: Optional[List[str]] = None
    medical_report_url: Optional[str] = None
    
    # Vínculo escolar
    class_id: Optional[str] = None
    user_id: Optional[str] = None
    guardian_ids: Optional[List[str]] = None
    
    # Observações
    observations: Optional[str] = None
    status: Optional[Literal['active', 'inactive', 'dropout', 'transferred', 'deceased']] = None

class Student(StudentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============= STUDENT HISTORY MODELS =============

class StudentHistoryBase(BaseModel):
    """Histórico de movimentações do aluno"""
    student_id: str
    school_id: str
    school_name: str
    class_id: Optional[str] = None
    class_name: Optional[str] = None
    enrollment_id: Optional[str] = None
    action_type: Literal['matricula', 'remanejamento', 'transferencia_saida', 'transferencia_entrada', 'mudanca_status', 'edicao'] = 'matricula'
    previous_status: Optional[str] = None
    new_status: str
    observations: Optional[str] = None
    user_id: str
    user_name: str
    action_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StudentHistoryCreate(StudentHistoryBase):
    pass

class StudentHistory(StudentHistoryBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))


# ============= GUARDIAN MODELS =============

class GuardianBase(BaseModel):
    """Responsável/Guardian - Pessoa responsável por um ou mais alunos"""
    # Dados pessoais
    full_name: str
    cpf: Optional[str] = None
    rg: Optional[str] = None
    birth_date: Optional[str] = None
    
    # Contato
    phone: Optional[str] = None
    cell_phone: Optional[str] = None
    email: Optional[str] = None
    
    # Endereço
    address: Optional[str] = None
    address_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    
    # Trabalho
    occupation: Optional[str] = None
    workplace: Optional[str] = None
    work_phone: Optional[str] = None
    
    # Vínculo
    relationship: Literal['pai', 'mae', 'avo', 'tio', 'irmao', 'responsavel', 'outro'] = 'responsavel'
    student_ids: List[str] = []
    user_id: Optional[str] = None  # Se o responsável tem acesso ao portal
    
    # Status
    status: Literal['active', 'inactive'] = 'active'
    observations: Optional[str] = None

class GuardianCreate(GuardianBase):
    pass

class GuardianUpdate(BaseModel):
    full_name: Optional[str] = None
    cpf: Optional[str] = None
    rg: Optional[str] = None
    birth_date: Optional[str] = None
    phone: Optional[str] = None
    cell_phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    address_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    occupation: Optional[str] = None
    workplace: Optional[str] = None
    work_phone: Optional[str] = None
    relationship: Optional[Literal['pai', 'mae', 'avo', 'tio', 'irmao', 'responsavel', 'outro']] = None
    student_ids: Optional[List[str]] = None
    user_id: Optional[str] = None
    status: Optional[Literal['active', 'inactive']] = None
    observations: Optional[str] = None

class Guardian(GuardianBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= ENROLLMENT MODELS =============

class EnrollmentBase(BaseModel):
    """Matrícula - Vínculo do aluno com turma e componentes curriculares"""
    student_id: str
    school_id: str
    class_id: str
    course_ids: List[str] = []  # Lista de componentes curriculares
    academic_year: int
    enrollment_date: Optional[str] = None
    enrollment_number: Optional[str] = None  # Número da matrícula
    
    # Situação
    status: Literal['active', 'completed', 'cancelled', 'transferred'] = 'active'
    
    # Observações
    observations: Optional[str] = None

class EnrollmentCreate(EnrollmentBase):
    pass

class EnrollmentUpdate(BaseModel):
    class_id: Optional[str] = None
    course_ids: Optional[List[str]] = None
    enrollment_date: Optional[str] = None
    enrollment_number: Optional[str] = None
    status: Optional[Literal['active', 'completed', 'cancelled', 'transferred']] = None
    observations: Optional[str] = None

class Enrollment(EnrollmentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= GRADES MODELS =============

class GradeBase(BaseModel):
    """Notas por bimestre de um aluno em um componente curricular"""
    student_id: str  # ID do aluno
    class_id: str  # ID da turma
    course_id: str  # ID do componente curricular
    academic_year: int  # Ano letivo
    
    # Notas por bimestre (0 a 10)
    b1: Optional[float] = None  # 1º Bimestre (peso 2)
    b2: Optional[float] = None  # 2º Bimestre (peso 3)
    b3: Optional[float] = None  # 3º Bimestre (peso 2)
    b4: Optional[float] = None  # 4º Bimestre (peso 3)
    
    # Recuperação por semestre (substitui menor nota do semestre)
    rec_s1: Optional[float] = None  # Recuperação 1º Semestre (B1/B2)
    rec_s2: Optional[float] = None  # Recuperação 2º Semestre (B3/B4)
    
    # Campo legado para compatibilidade
    recovery: Optional[float] = None
    
    # Resultados calculados
    final_average: Optional[float] = None
    status: Literal['cursando', 'aprovado', 'reprovado_nota', 'reprovado_frequencia', 'recuperacao'] = 'cursando'
    
    # Observações
    observations: Optional[str] = None

class GradeCreate(BaseModel):
    student_id: str
    class_id: str
    course_id: str
    academic_year: int
    b1: Optional[float] = None
    b2: Optional[float] = None
    b3: Optional[float] = None
    b4: Optional[float] = None
    rec_s1: Optional[float] = None  # Recuperação 1º Semestre
    rec_s2: Optional[float] = None  # Recuperação 2º Semestre
    recovery: Optional[float] = None  # Campo legado
    observations: Optional[str] = None

class GradeUpdate(BaseModel):
    b1: Optional[float] = None
    b2: Optional[float] = None
    b3: Optional[float] = None
    b4: Optional[float] = None
    rec_s1: Optional[float] = None  # Recuperação 1º Semestre
    rec_s2: Optional[float] = None  # Recuperação 2º Semestre
    recovery: Optional[float] = None  # Campo legado
    observations: Optional[str] = None

class Grade(GradeBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= ATTENDANCE MODELS =============

class AttendanceBase(BaseModel):
    enrollment_id: str
    academic_year: int
    bimester: Literal[1, 2, 3, 4]
    total_classes: int
    absences: int = 0
    attendance_percentage: Optional[float] = None

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceUpdate(BaseModel):
    total_classes: Optional[int] = None
    absences: Optional[int] = None

class Attendance(AttendanceBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= NOTICE MODELS =============

class NoticeBase(BaseModel):
    school_id: str
    title: str
    content: str
    target_type: Literal['global', 'school', 'class', 'course', 'user']
    target_ids: List[str] = []  # IDs de turmas, disciplinas ou usuários
    created_by: str  # user_id
    read_by: List[str] = []  # user_ids que já leram

class NoticeCreate(BaseModel):
    school_id: str
    title: str
    content: str
    target_type: Literal['global', 'school', 'class', 'course', 'user']
    target_ids: List[str] = []

class NoticeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class Notice(NoticeBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= DOCUMENT MODELS =============

class DocumentBase(BaseModel):
    student_id: str
    type: Literal['boletim', 'ficha', 'declaracao_matricula', 'declaracao_frequencia', 'declaracao_conclusao', 'carteira_estudante']
    period: str  # Ex: "2024-1" para 1º bimestre, "2024" para anual
    url: Optional[str] = None

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= CALENDAR EVENT MODELS =============

class CalendarEventBase(BaseModel):
    """Evento do Calendário Letivo"""
    name: str  # Nome do evento
    description: Optional[str] = None  # Descrição detalhada
    
    # Tipo do evento
    event_type: Literal[
        'feriado_nacional',
        'feriado_estadual', 
        'feriado_municipal',
        'sabado_letivo',
        'recesso_escolar',
        'evento_escolar',
        'outros'
    ]
    
    # Indica se é dia letivo ou não letivo
    is_school_day: bool = False  # True = Letivo, False = Não Letivo
    
    # Período do evento
    start_date: str  # Data início (YYYY-MM-DD)
    end_date: str  # Data fim (YYYY-MM-DD) - igual start_date se for um único dia
    
    # Turno/Período do dia
    period: Literal['integral', 'manha', 'tarde', 'noite', 'personalizado'] = 'integral'
    
    # Horários personalizados (apenas se period = 'personalizado')
    start_time: Optional[str] = None  # HH:MM
    end_time: Optional[str] = None  # HH:MM
    
    # Ano letivo
    academic_year: int
    
    # Cor para exibição no calendário (hex)
    color: Optional[str] = None

class CalendarEventCreate(CalendarEventBase):
    pass

class CalendarEventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[Literal[
        'feriado_nacional',
        'feriado_estadual', 
        'feriado_municipal',
        'sabado_letivo',
        'recesso_escolar',
        'evento_escolar',
        'outros'
    ]] = None
    is_school_day: Optional[bool] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    period: Optional[Literal['integral', 'manha', 'tarde', 'noite', 'personalizado']] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    color: Optional[str] = None

class CalendarEvent(CalendarEventBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= ATTENDANCE MODELS (FREQUÊNCIA) =============

class AttendanceRecord(BaseModel):
    """Registro de frequência individual de um aluno"""
    student_id: str
    status: Literal['P', 'F', 'J']  # P=Presente, F=Falta, J=Justificado
    
class AttendanceBase(BaseModel):
    """Frequência de uma turma em uma data"""
    class_id: str  # ID da turma
    date: str  # Data (YYYY-MM-DD)
    academic_year: int  # Ano letivo
    
    # Tipo de frequência baseado no nível de ensino
    # 'daily' = uma frequência por dia (Fundamental Anos Iniciais, EJA Anos Iniciais)
    # 'by_component' = frequência por componente curricular (Fundamental Anos Finais, EJA Anos Finais)
    attendance_type: Literal['daily', 'by_component']
    
    # Se attendance_type = 'by_component', indica o componente curricular
    course_id: Optional[str] = None
    
    # Período (para Escola Integral e Aulas Complementares)
    period: Literal['regular', 'integral', 'complementar'] = 'regular'
    
    # Lista de registros de frequência dos alunos
    records: List[AttendanceRecord] = []
    
    # Observações gerais
    observations: Optional[str] = None

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceUpdate(BaseModel):
    records: Optional[List[AttendanceRecord]] = None
    observations: Optional[str] = None

class Attendance(AttendanceBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_by: Optional[str] = None  # ID do usuário que criou
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= ATTENDANCE SETTINGS =============

class AttendanceSettings(BaseModel):
    """Configurações de frequência"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    academic_year: int
    allow_future_dates: bool = False  # Permitir lançamento em datas futuras
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None

# ============= OBJETOS DE CONHECIMENTO MODELS =============

class LearningObjectBase(BaseModel):
    """Registro de conteúdos ministrados (Objetos de Conhecimento)"""
    class_id: str  # ID da turma
    course_id: str  # ID do componente curricular
    date: str  # Data do registro (YYYY-MM-DD)
    academic_year: int
    content: str  # Conteúdo/objeto de conhecimento ministrado
    observations: Optional[str] = None  # Observações do professor
    methodology: Optional[str] = None  # Metodologia utilizada
    resources: Optional[str] = None  # Recursos utilizados
    number_of_classes: int = 1  # Número de aulas

class LearningObjectCreate(BaseModel):
    class_id: str
    course_id: str
    date: str
    academic_year: int
    content: str
    observations: Optional[str] = None
    methodology: Optional[str] = None
    resources: Optional[str] = None
    number_of_classes: int = 1

class LearningObjectUpdate(BaseModel):
    content: Optional[str] = None
    observations: Optional[str] = None
    methodology: Optional[str] = None
    resources: Optional[str] = None
    number_of_classes: Optional[int] = None

class LearningObject(BaseModel):
    """Modelo completo do registro de objetos de conhecimento"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    class_id: str
    course_id: str
    date: str
    academic_year: int
    content: str
    observations: Optional[str] = None
    methodology: Optional[str] = None
    resources: Optional[str] = None
    number_of_classes: int = 1
    recorded_by: Optional[str] = None  # ID do usuário que registrou
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= SERVIDOR (STAFF) MODELS =============

class StaffBase(BaseModel):
    """Servidor - Funcionário da rede de ensino"""
    # Dados Pessoais
    nome: str  # Nome completo do servidor
    cpf: Optional[str] = None  # CPF do servidor (usado para gerar senha)
    foto_url: Optional[str] = None  # URL da foto do servidor
    data_nascimento: Optional[str] = None  # Data de nascimento (YYYY-MM-DD)
    sexo: Optional[Literal['masculino', 'feminino', 'outro']] = None
    cor_raca: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarado']] = None
    celular: Optional[str] = None  # Número do celular para WhatsApp
    email: Optional[str] = None
    
    # Dados Funcionais (matrícula será gerada automaticamente)
    cargo: Literal['auxiliar', 'auxiliar_secretaria', 'auxiliar_servicos_gerais', 'coordenador', 'diretor', 'mediador', 'merendeira', 'professor', 'secretario', 'vigia', 'zelador', 'outro']
    cargo_especifico: Optional[str] = None  # Descrição específica do cargo
    
    # Vínculo Empregatício
    tipo_vinculo: Literal['efetivo', 'contratado', 'temporario', 'comissionado'] = 'efetivo'
    data_admissao: Optional[str] = None  # Data de admissão (YYYY-MM-DD)
    carga_horaria_semanal: Optional[int] = None  # Horas semanais
    
    # Formação (lista de formações)
    formacoes: Optional[List[str]] = []  # Lista de formações
    especializacoes: Optional[List[str]] = []  # Lista de especializações
    
    # Status do servidor
    status: Literal['ativo', 'afastado', 'licenca', 'ferias', 'aposentado', 'exonerado'] = 'ativo'
    motivo_afastamento: Optional[str] = None
    data_afastamento: Optional[str] = None
    previsao_retorno: Optional[str] = None
    
    # Vínculo com usuário do sistema (criado automaticamente para professores)
    user_id: Optional[str] = None
    
    # Observações
    observacoes: Optional[str] = None

class StaffCreate(BaseModel):
    """Modelo para criar servidor (sem matrícula - será gerada automaticamente)"""
    nome: str
    cpf: Optional[str] = None
    foto_url: Optional[str] = None
    data_nascimento: Optional[str] = None
    sexo: Optional[Literal['masculino', 'feminino', 'outro']] = None
    cor_raca: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarado']] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    cargo: Literal['auxiliar', 'auxiliar_secretaria', 'auxiliar_servicos_gerais', 'coordenador', 'diretor', 'mediador', 'merendeira', 'professor', 'secretario', 'vigia', 'zelador', 'outro']
    cargo_especifico: Optional[str] = None
    tipo_vinculo: Literal['efetivo', 'contratado', 'temporario', 'comissionado'] = 'efetivo'
    data_admissao: Optional[str] = None
    carga_horaria_semanal: Optional[int] = None
    formacoes: Optional[List[str]] = []
    especializacoes: Optional[List[str]] = []
    status: Literal['ativo', 'afastado', 'licenca', 'ferias', 'aposentado', 'exonerado'] = 'ativo'
    motivo_afastamento: Optional[str] = None
    data_afastamento: Optional[str] = None
    previsao_retorno: Optional[str] = None
    observacoes: Optional[str] = None

class StaffUpdate(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    foto_url: Optional[str] = None
    data_nascimento: Optional[str] = None
    sexo: Optional[Literal['masculino', 'feminino', 'outro']] = None
    cor_raca: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarado']] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    cargo: Optional[Literal['auxiliar', 'auxiliar_secretaria', 'auxiliar_servicos_gerais', 'coordenador', 'diretor', 'mediador', 'merendeira', 'professor', 'secretario', 'vigia', 'zelador', 'outro']] = None
    cargo_especifico: Optional[str] = None
    tipo_vinculo: Optional[Literal['efetivo', 'contratado', 'temporario', 'comissionado']] = None
    data_admissao: Optional[str] = None
    carga_horaria_semanal: Optional[int] = None
    formacoes: Optional[List[str]] = None
    especializacoes: Optional[List[str]] = None
    status: Optional[Literal['ativo', 'afastado', 'licenca', 'ferias', 'aposentado', 'exonerado']] = None
    motivo_afastamento: Optional[str] = None
    data_afastamento: Optional[str] = None
    previsao_retorno: Optional[str] = None
    user_id: Optional[str] = None
    observacoes: Optional[str] = None

class Staff(BaseModel):
    """Modelo completo do servidor com matrícula"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    matricula: str  # Gerada automaticamente
    nome: str
    cpf: Optional[str] = None
    foto_url: Optional[str] = None
    data_nascimento: Optional[str] = None
    sexo: Optional[Literal['masculino', 'feminino', 'outro']] = None
    cor_raca: Optional[Literal['branca', 'preta', 'parda', 'amarela', 'indigena', 'nao_declarado']] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    cargo: Literal['auxiliar', 'auxiliar_secretaria', 'auxiliar_servicos_gerais', 'coordenador', 'diretor', 'mediador', 'merendeira', 'professor', 'secretario', 'vigia', 'zelador', 'outro']
    cargo_especifico: Optional[str] = None
    tipo_vinculo: Literal['efetivo', 'contratado', 'temporario', 'comissionado'] = 'efetivo'
    data_admissao: Optional[str] = None
    carga_horaria_semanal: Optional[int] = None
    formacoes: Optional[List[str]] = []
    especializacoes: Optional[List[str]] = []
    status: Literal['ativo', 'afastado', 'licenca', 'ferias', 'aposentado', 'exonerado'] = 'ativo'
    motivo_afastamento: Optional[str] = None
    data_afastamento: Optional[str] = None
    previsao_retorno: Optional[str] = None
    user_id: Optional[str] = None
    observacoes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= LOTAÇÃO (SCHOOL ASSIGNMENT) MODELS =============

class SchoolAssignmentBase(BaseModel):
    """Lotação - Vínculo do servidor com uma escola"""
    staff_id: str  # ID do servidor
    school_id: str  # ID da escola
    
    # Função na escola
    funcao: Literal['professor', 'diretor', 'vice_diretor', 'coordenador', 'secretario', 'apoio'] = 'professor'
    
    # Período da lotação
    data_inicio: str  # Data início (YYYY-MM-DD)
    data_fim: Optional[str] = None  # Data fim (YYYY-MM-DD) - null se ainda ativo
    
    # Carga horária nesta escola
    carga_horaria: Optional[int] = None  # Horas semanais nesta escola
    turno: Optional[Literal['matutino', 'vespertino', 'noturno', 'integral']] = None
    
    # Status
    status: Literal['ativo', 'encerrado', 'transferido'] = 'ativo'
    motivo_encerramento: Optional[str] = None
    
    # Ano letivo
    academic_year: int
    
    observacoes: Optional[str] = None

class SchoolAssignmentCreate(SchoolAssignmentBase):
    pass

class SchoolAssignmentUpdate(BaseModel):
    funcao: Optional[Literal['professor', 'diretor', 'vice_diretor', 'coordenador', 'secretario', 'apoio']] = None
    data_fim: Optional[str] = None
    carga_horaria: Optional[int] = None
    turno: Optional[Literal['matutino', 'vespertino', 'noturno', 'integral']] = None
    status: Optional[Literal['ativo', 'encerrado', 'transferido']] = None
    motivo_encerramento: Optional[str] = None
    observacoes: Optional[str] = None

class SchoolAssignment(SchoolAssignmentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

# ============= ALOCAÇÃO DE PROFESSOR (TEACHER ASSIGNMENT) MODELS =============

class TeacherAssignmentBase(BaseModel):
    """Alocação de Professor - Vínculo do professor com turma e componente curricular"""
    staff_id: str  # ID do servidor (professor)
    school_id: str  # ID da escola
    class_id: str  # ID da turma
    course_id: str  # ID do componente curricular
    
    # Ano letivo
    academic_year: int
    
    # Carga horária semanal para este componente
    carga_horaria_semanal: Optional[int] = None  # Aulas por semana
    
    # Status
    status: Literal['ativo', 'substituido', 'encerrado'] = 'ativo'
    
    # Professor substituto (se houver)
    substituto_staff_id: Optional[str] = None
    data_substituicao: Optional[str] = None
    motivo_substituicao: Optional[str] = None
    
    observacoes: Optional[str] = None

class TeacherAssignmentCreate(TeacherAssignmentBase):
    pass

class TeacherAssignmentUpdate(BaseModel):
    carga_horaria_semanal: Optional[int] = None
    status: Optional[Literal['ativo', 'substituido', 'encerrado']] = None
    substituto_staff_id: Optional[str] = None
    data_substituicao: Optional[str] = None
    motivo_substituicao: Optional[str] = None
    observacoes: Optional[str] = None

class TeacherAssignment(TeacherAssignmentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None



# ============= UNIDADE MANTENEDORA MODELS =============

class MantenedoraBase(BaseModel):
    """Unidade Mantenedora - Instituição que mantém as escolas"""
    
    # Identificação
    nome: str
    cnpj: Optional[str] = None
    codigo_inep: Optional[str] = None
    natureza_juridica: Optional[str] = None  # Pública Municipal, Pública Estadual, Privada, etc.
    logotipo_url: Optional[str] = None  # URL do logotipo
    brasao_url: Optional[str] = None  # URL do brasão
    slogan: Optional[str] = None  # Slogan da instituição para cabeçalhos dos documentos
    
    # Endereço
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    
    # Contato
    telefone: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    site: Optional[str] = None
    contato_nome: Optional[str] = None  # Nome da pessoa de contato
    contato_cargo: Optional[str] = None  # Cargo da pessoa de contato
    
    # Responsável Legal
    responsavel_nome: Optional[str] = None
    responsavel_cargo: Optional[str] = None
    responsavel_cpf: Optional[str] = None

class MantenedoraUpdate(BaseModel):
    """Modelo para atualização da Mantenedora"""
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    codigo_inep: Optional[str] = None
    natureza_juridica: Optional[str] = None
    logotipo_url: Optional[str] = None
    brasao_url: Optional[str] = None  # URL do brasão
    slogan: Optional[str] = None  # Slogan da instituição
    
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    
    telefone: Optional[str] = None
    celular: Optional[str] = None
    email: Optional[str] = None
    site: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_cargo: Optional[str] = None
    
    responsavel_nome: Optional[str] = None
    responsavel_cargo: Optional[str] = None
    responsavel_cpf: Optional[str] = None

class Mantenedora(MantenedoraBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None



# ============= CALENDÁRIO - PERÍODOS BIMESTRAIS =============

class PeriodoBimestral(BaseModel):
    """Modelo para um período bimestral"""
    bimestre: int  # 1, 2, 3 ou 4
    data_inicio: str  # Formato: YYYY-MM-DD
    data_fim: str  # Formato: YYYY-MM-DD
    
class CalendarioLetivoBase(BaseModel):
    """Modelo base para configuração do Calendário Letivo"""
    ano_letivo: int
    school_id: Optional[str] = None  # Se None, aplica a todas as escolas
    
    # Períodos bimestrais
    bimestre_1_inicio: Optional[str] = None
    bimestre_1_fim: Optional[str] = None
    bimestre_2_inicio: Optional[str] = None
    bimestre_2_fim: Optional[str] = None
    bimestre_3_inicio: Optional[str] = None
    bimestre_3_fim: Optional[str] = None
    bimestre_4_inicio: Optional[str] = None
    bimestre_4_fim: Optional[str] = None
    
    # Recesso/Férias entre semestres
    recesso_inicio: Optional[str] = None
    recesso_fim: Optional[str] = None
    
    # Dias letivos previstos
    dias_letivos_previstos: Optional[int] = 200

class CalendarioLetivoCreate(CalendarioLetivoBase):
    pass

class CalendarioLetivoUpdate(BaseModel):
    """Modelo para atualização do Calendário Letivo"""
    bimestre_1_inicio: Optional[str] = None
    bimestre_1_fim: Optional[str] = None
    bimestre_2_inicio: Optional[str] = None
    bimestre_2_fim: Optional[str] = None
    bimestre_3_inicio: Optional[str] = None
    bimestre_3_fim: Optional[str] = None
    bimestre_4_inicio: Optional[str] = None
    bimestre_4_fim: Optional[str] = None
    recesso_inicio: Optional[str] = None
    recesso_fim: Optional[str] = None
    dias_letivos_previstos: Optional[int] = None

class CalendarioLetivo(CalendarioLetivoBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
