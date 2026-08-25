# Runbook — lote P0 com data confirmada

Data administrativa confirmada: `2026-01-15`.

## Pré-condição

Executar somente após deploy do PR correspondente e gerar um manifesto contendo exclusivamente os 7 casos confirmados no campo `ready`.

## Dry-run

```bash
cd /app
python scripts/reconcile_enrollment_p0_confirmed_date_2026.py \
  --manifest /tmp/sigesc_enrollment_p0_confirmed_date_7.json \
  --confirmed-date 2026-01-15
```

Esperado antes da aplicação: `READY: 7`, `ALREADY_CANONICAL: 0`, `BLOCKED: 0`.

## Aplicação

Somente após autorização humana explícita:

```bash
python scripts/reconcile_enrollment_p0_confirmed_date_2026.py \
  --manifest /tmp/sigesc_enrollment_p0_confirmed_date_7.json \
  --confirmed-date 2026-01-15 \
  --apply \
  --confirm-count 7 \
  --confirm-token RECONCILE-P0-CONFIRMED-DATE-2026 \
  --receipt /tmp/sigesc_enrollment_p0_confirmed_date_apply_7.json
```

## Pós-condição

Reexecutar em dry-run. Esperado: `READY: 0`, `ALREADY_CANONICAL: 7`, `BLOCKED: 0`.

Depois executar `python scripts/audit_enrollment_canonical.py`. O reparo não altera notas nem frequências.
