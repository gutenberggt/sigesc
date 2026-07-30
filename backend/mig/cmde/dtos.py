"""DTOs/Schemas do CMDE (contratos explícitos SIGESC ↔ CMDE)."""
from pydantic import BaseModel
from typing import Optional, List


class MecConfigUpdateDTO(BaseModel):
    """Campos aceitos no PUT /mec/config.

    DECISÃO Sprint 000 (aprovada): PGP não é persistido nesta fase (opção b). Os campos
    pgp_public_key/pgp_private_key foram removidos do contrato de persistência; a abstração
    CryptoProvider (mig/core/crypto.py) é mantida para ativação futura.
    """
    environment: Optional[str] = None
    api_key: Optional[str] = None
    server_ip: Optional[str] = None
    responsible_name: Optional[str] = None
    responsible_email: Optional[str] = None
    responsible_cpf: Optional[str] = None
    responsible_phone: Optional[str] = None
    responsible_role: Optional[str] = None


class MappingRowDTO(BaseModel):
    id: str
    full_name: str
    cpf: str = ""
    nis: str = ""
    inep_code: str = ""
    school_name: str = ""
    school_inep: str = ""
    ready: bool = False
    missing_fields: List[str] = []


# ===== Sprint 002 — Envio de Frequência CMDE (contratos de payload/resposta) =====
class FrequencyItemDTO(BaseModel):
    """Frequência consolidada de UM aluno numa competência (representação do SSoT)."""
    student_id: str
    cpf: str = ""
    nis: str = ""
    inep_aluno: str = ""
    school_inep: str = ""
    competencia: str                       # YYYY-MM
    dias_letivos: int = 0
    faltas_validas: int = 0
    frequencia_percentual: float = 0.0
    situacao: str = ""


class FrequencyBatchRequestDTO(BaseModel):
    """Parâmetros de construção de lote (usado a partir da Sprint 002.b)."""
    competencia: str
    school_id: Optional[str] = None
    class_id: Optional[str] = None
    dry_run: bool = True


class CmdeFrequencyPayloadDTO(BaseModel):
    """
    Payload enviado ao CMDE. PLACEHOLDER até o contrato OFICIAL da API do MEC.
    O formato final (campos/estrutura) será ajustado quando o contrato for confirmado.
    """
    correlation_id: str
    tenant: Optional[str] = None
    competencia: str
    school_inep: str = ""
    items: List[FrequencyItemDTO] = []


class CmdeItemResultDTO(BaseModel):
    """Resultado por item retornado pelo CMDE (aceite/rejeição)."""
    ref: str                               # referência do item (student_id)
    accepted: bool
    code: Optional[str] = None
    reason: Optional[str] = None


class CmdeFrequencyResponseDTO(BaseModel):
    """
    Resposta normalizada do CMDE. `valid=False` sinaliza resposta fora do contrato
    (corpo não parseável / schema inesperado) — tratada como erro pela camada de envio.
    """
    protocol: Optional[str] = None
    http_status: int = 200
    valid: bool = True
    items: List[CmdeItemResultDTO] = []
    raw: Optional[dict] = None
