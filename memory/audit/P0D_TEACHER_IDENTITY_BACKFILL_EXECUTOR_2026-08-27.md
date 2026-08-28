# P0-D — Executor controlado de backfill `staff.user_id`

Data de referência: 2026-08-27  
Fase: P0-D1  
Modo desta entrega: **código + testes; nenhuma execução de produção**

## 1. Evidência autorizativa

P0-C Semantic V3 foi executado em produção após o merge do PR #186 e convergiu integralmente:

- `teacher_class_assignments_raw_active = 1457`;
- `LEGACY_MIGRATION_SYNTHETIC = 1085`;
- `LEGACY_MIGRATION_SYNTHETIC_UNASSIGNED = 97`;
- `LEGACY_MIGRATION_DRIFT = 0`;
- `OPERATIONAL_DVD = 275`;
- 39 identidades DVD distintas e estruturalmente unânimes;
- `ALREADY_CANONICAL = 33`;
- `READY_SAFE = 6`;
- `USER_NOT_FOUND = 0`;
- evidência dos 6: `EXACT_PAIR_PLUS_EMAIL`;
- blockers: nenhum.

Manifesto de produção:

- canonical SHA-256: `68165e38d51e58071bd0d9b8d91114872b97841f987e8b630b9b6208b77bda9a`;
- P0-B source evidence SHA-256: `519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be`;
- arquivo preservado no host: `/root/sigesc-p0-audits/p0c_semantic_v3_preflight_20260828T023618Z.json`;
- SHA físico do arquivo: `d9fc8cd1191d37ba81d6967d3ed2a25a860342e44bd57e15b3911c746d16c1ba`.

## 2. Escopo exato do P0-D

A única mutação permitida pelo executor é:

`staff.user_id: vazio/ausente -> target_user_id aprovado no manifesto`

Não altera:

- `teacher_class_assignments`;
- `teacher_assignments`;
- `teacher_allocations`;
- grade horária;
- notas;
- frequência;
- conteúdo;
- AEE;
- qualquer outro campo de `staff`.

## 3. Gates do executor

O arquivo `backend/scripts/apply_teacher_identity_backfill_p0d.py`:

1. fixa `ACADEMIC_YEAR=2026` e `REFERENCE_DATE=2026-08-27`;
2. fixa manifesto Semantic V3, versão 3 e o SHA canônico aprovado;
3. fixa a cadeia P0-B;
4. exige exatamente 6 propostas `BACKFILL_STAFF_USER_ID`;
5. exige `expected_user_id_before` vazio;
6. exige evidência `EXACT_PAIR_PLUS_EMAIL` em todos os 6 casos;
7. recalcula o SHA individual de evidência de cada proposta;
8. exige `LEGACY_MIGRATION_DRIFT=0`;
9. verifica tenant, cargo/status do staff e role do user no estado vivo;
10. bloqueia target user já ligado a outro staff;
11. detecta lote parcial (`PARTIAL_APPLY_STATE_DETECTED`) e falha fechado;
12. default é DRY-RUN;
13. DRY-RUN recalcula o manifesto Semantic V3 vivo e exige o mesmo SHA canônico;
14. DRY-RUN cria snapshot imutável, metadata e `BACKUP-SEAL.json`;
15. apply/rollback exigem o hash desse backup selado;
16. cada alteração usa CAS por `staff.id + mantenedora_id + presença/valor anterior de user_id`;
17. preserva a diferença entre campo ausente, `null` e string vazia para rollback exato;
18. falha durante apply/rollback tenta compensação imediata das alterações já realizadas;
19. receipts são persistidos em arquivo e incluem hashes, estado anterior/posterior e mudanças.

## 4. Confirmações de mutação

Mesmo depois de merge/deploy, nenhuma escrita ocorre sem flags explícitas.

Apply exige simultaneamente:

- `--apply`;
- `--expected-backup-sha256 <hash aprovado>`;
- `--confirm APPLY-P0D-TEACHER-IDENTITY-6`.

Rollback exige:

- `--rollback`;
- o mesmo backup selado/hash;
- `--confirm ROLLBACK-P0D-TEACHER-IDENTITY-6`.

## 5. Governança em duas subetapas

### P0-D1

Entrega atual:

- implementar executor;
- validar em CI;
- abrir PR;
- após autorização, merge/deploy;
- executar somente DRY-RUN em produção;
- obter `backup_bundle_sha256` real.

### P0-D2

Somente depois do dry-run de produção:

- criar wrapper de produção selado ao `backup_bundle_sha256` real e ao diretório persistente;
- revisar/CI/PR;
- merge somente após autorização humana;
- execução `--apply` somente após **nova autorização explícita de escrita em produção**.

Autorização de merge de código não equivale a autorização de mutação do MongoDB.

## 6. Invariantes

- fail-closed;
- tenant-aware;
- deterministic manifest;
- snapshot + hash + rollback;
- idempotência detectável;
- nenhuma inferência por nome;
- nenhuma expansão automática além dos 6 casos aprovados;
- nenhuma alteração AEE.
