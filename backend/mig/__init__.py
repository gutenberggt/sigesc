"""
MIG — Módulo de Integração Governamental.

Estrutura em três camadas (ver memory/audit/SPRINT_000_PLANO_REFATORACAO_MIG.md):
  - core/       infra reutilizável e agnóstica de provider
  - providers/  contrato comum de provider governamental
  - cmde/       implementação específica do CMDE (MEC Gestão Presente)

Invariantes: routers sem regra de negócio; services sem HTTP direto;
toda saída externa passa pelo cliente único do provider.
"""
