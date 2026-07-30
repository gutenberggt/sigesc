"""
CryptoProvider — abstração de assinatura/criptografia para provedores governamentais.

DECISÃO (Sprint 000, aprovada): NÃO implementar PGP nesta fase. Remove-se a implementação
inerte e o armazenamento desnecessário de chaves, preservando APENAS esta abstração para
ativação futura caso a especificação oficial do CMDE passe a exigir.

`NullCryptoProvider` é o comportamento atual (passthrough, sem criptografia). Quando/se o MEC
exigir PGP, cria-se `PgpCryptoProvider(CryptoProvider)` sem alterar os chamadores.
"""
from abc import ABC, abstractmethod


class CryptoProvider(ABC):
    @abstractmethod
    def sign(self, payload: bytes) -> bytes: ...

    @abstractmethod
    def encrypt(self, payload: bytes) -> bytes: ...

    @property
    @abstractmethod
    def enabled(self) -> bool: ...


class NullCryptoProvider(CryptoProvider):
    """Passthrough — nenhum uso de criptografia (estado atual do CMDE)."""
    def sign(self, payload: bytes) -> bytes:
        return payload

    def encrypt(self, payload: bytes) -> bytes:
        return payload

    @property
    def enabled(self) -> bool:
        return False
