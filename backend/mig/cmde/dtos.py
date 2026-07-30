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
