"""
CmdeFrequencyPort — contrato do provedor de ENVIO de frequência CMDE (Sprint 002.a).

Provider plugável: em produção será o CmdeClient real (BaseGovClient); em homologação/testes
será o CmdeFrequencySimulator. A camada de envio (Worker, Sprint 002.d) depende SOMENTE desta
porta — nunca de uma implementação concreta.
"""
from abc import ABC, abstractmethod

from mig.cmde.dtos import CmdeFrequencyPayloadDTO, CmdeFrequencyResponseDTO


class CmdeFrequencyPort(ABC):
    provider: str = "cmde"

    @abstractmethod
    async def enviar_frequencia(self, payload: CmdeFrequencyPayloadDTO) -> CmdeFrequencyResponseDTO:
        """
        Envia um lote/payload de frequência ao CMDE.

        Contrato:
        - Sucesso/aceite/rejeição parcial → retorna CmdeFrequencyResponseDTO (valid=True).
        - Resposta fora do contrato → CmdeFrequencyResponseDTO(valid=False).
        - Erro de transporte (5xx/timeout) → levanta MigError (recuperável quando aplicável).
        """
        ...
