"""FeatureFlags — resolução de ambiente e chaves de habilitação do MIG.

Fundação: resolve ambiente (homologacao/producao) → URL base. Flags dinâmicas de
on/off e rollout gradual serão adicionadas na sprint de infra.
"""

CMDE_ENVIRONMENTS = {
    "homologacao": "https://api-cmde.hmg.gestaopresente.mec.gov.br/v1",
    "producao": "https://api-cmde.gestaopresente.mec.gov.br/v1",
}


class FeatureFlags:
    @staticmethod
    def resolve_cmde_base_url(environment: str) -> str:
        return CMDE_ENVIRONMENTS.get(environment or "homologacao",
                                     CMDE_ENVIRONMENTS["homologacao"])
