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
    status: Optional[Literal['active', 'inactive']] = None
    # ... outros campos podem ser adicionados conforme necessário

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
    grade_level: str  # Ex: "1º Ano EF", "6º Ano", etc
    teacher_ids: List[str] = []

class ClassCreate(ClassBase):
    pass

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    shift: Optional[Literal['morning', 'afternoon', 'evening', 'full_time']] = None
    grade_level: Optional[str] = None
    teacher_ids: Optional[List[str]] = None

class Class(ClassBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= COURSE (DISCIPLINA) MODELS =============

class CourseBase(BaseModel):
    school_id: str
    name: str
    code: Optional[str] = None
    workload: Optional[int] = None  # Carga horária

class CourseCreate(CourseBase):
    pass

class CourseUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    workload: Optional[int] = None

class Course(CourseBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= STUDENT MODELS =============

class StudentBase(BaseModel):
    user_id: Optional[str] = None  # Opcional se aluno não tem acesso ao portal
    school_id: str
    enrollment_number: str
    class_id: str
    birth_date: Optional[str] = None
    guardian_ids: List[str] = []

class StudentCreate(StudentBase):
    pass

class StudentUpdate(BaseModel):
    user_id: Optional[str] = None
    class_id: Optional[str] = None
    birth_date: Optional[str] = None
    guardian_ids: Optional[List[str]] = None

class Student(StudentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= GUARDIAN MODELS =============

class GuardianBase(BaseModel):
    user_id: str
    student_ids: List[str] = []
    relationship: Literal['pai', 'mae', 'responsavel']

class GuardianCreate(GuardianBase):
    pass

class GuardianUpdate(BaseModel):
    student_ids: Optional[List[str]] = None
    relationship: Optional[Literal['pai', 'mae', 'responsavel']] = None

class Guardian(GuardianBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= ENROLLMENT MODELS =============

class EnrollmentBase(BaseModel):
    student_id: str
    class_id: str
    course_id: str
    academic_year: int
    status: Literal['active', 'completed', 'cancelled'] = 'active'

class EnrollmentCreate(EnrollmentBase):
    pass

class EnrollmentUpdate(BaseModel):
    status: Optional[Literal['active', 'completed', 'cancelled']] = None

class Enrollment(EnrollmentBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= GRADES MODELS =============

class GradeBase(BaseModel):
    enrollment_id: str
    academic_year: int
    b1: Optional[float] = None
    b2: Optional[float] = None
    b3: Optional[float] = None
    b4: Optional[float] = None
    rec2: Optional[float] = None  # Recuperação após 2º bimestre
    rec4: Optional[float] = None  # Recuperação após 4º bimestre
    final_average: Optional[float] = None
    approved: Optional[bool] = None

class GradeCreate(BaseModel):
    enrollment_id: str
    academic_year: int

class GradeUpdate(BaseModel):
    b1: Optional[float] = None
    b2: Optional[float] = None
    b3: Optional[float] = None
    b4: Optional[float] = None
    rec2: Optional[float] = None
    rec4: Optional[float] = None

class Grade(GradeBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
