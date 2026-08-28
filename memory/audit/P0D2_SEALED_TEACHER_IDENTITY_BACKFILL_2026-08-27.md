# P0-D2 — Seal do backfill de identidade docente

Data operacional: 2026-08-27 (America/Belem) / 2026-08-28 UTC.

## Objetivo

Selar o executor P0-D1 aos 6 backfills `staff.user_id` aprovados pelo P0-C Semantic V3, sem executar mutação em produção nesta etapa.

## Evidência aprovada

- merge P0-D1: `f6fb25a5b623a56a7cad80c617d3a318159ae04b`
- SHA físico do executor observado no dry-run: `ac4eb06d679b2b9d11779097e17683f59fb0edc42d2171fa90cbe2282a31d622`
- canonical manifest SHA-256: `68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a`
- source P0-B evidence SHA-256: `519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be`
- `READY_SAFE = 6`
- `ALREADY_CANONICAL = 33`
- evidence method: `EXACT_PAIR_PLUS_EMAIL`
- `LEGACY_MIGRATION_DRIFT = 0`

## Dry-run P0-D1

- timestamp base: `20260828T025345Z`
- status: `PASS`
- `database_mutation = false`
- `live_state = READY`
- `ready_count = 6`
- pós-check Semantic V3: manifesto vivo inalterado

Backup aprovado:

- bundle SHA-256: `fac42381eb1d702002334be1e25d06ade594bf6376125a5008d09b995c7cc100`
- `backup-metadata.json`: `d04c532d3a27c7bfa729aa04f46e43056d0d72ceb3e8f987f929a8e573f8eeeb`
- `staff_before.json`: `62a87da7a701652a750c89aa71811f16103636fd3152c47dc85e08be2aae543a`
- `manifest.json`: `d9fc8cd1191d37ba81d6967d3ed2a25a860342e44bd57e15b3911c746d16c1ba`
- `BACKUP-SEAL.json`: `9fa9e7c87ecc394aa1ff58935f0f45accdebd0e3b95cd458096d137ee046ddc9`

## Contrato do P0-D2

O entrypoint `backend/scripts/apply_teacher_identity_backfill_p0d2_sealed.py`:

1. não possui mutadores MongoDB próprios;
2. fixa o manifesto canônico P0-C V3;
3. fixa `READY_COUNT = 6`;
4. fixa a cadeia P0-B;
5. fixa o bundle SHA-256 produzido pelo dry-run aprovado;
6. deriva o manifesto exclusivamente do backup selado informado em runtime;
7. não expõe argumentos para trocar manifesto, hash aprovado ou contagem;
8. usa `VERIFY_ONLY` como modo padrão;
9. delega apply/rollback somente ao executor P0-D1;
10. preserva as confirmações literais do P0-D1.

## Governança

Integrar o código P0-D2 em `main` não autoriza escrita no MongoDB.

Após merge e deploy, primeiro deve ocorrer `VERIFY_ONLY` sobre o backup aprovado. Somente uma autorização humana explícita separada poderá liberar a execução real do apply. O rollback permanece vinculado ao mesmo bundle selado.

AEE, `teacher_allocations`, `teacher_class_assignments`, `teacher_assignments`, notas, frequência e conteúdo permanecem fora do escopo de mutação.
