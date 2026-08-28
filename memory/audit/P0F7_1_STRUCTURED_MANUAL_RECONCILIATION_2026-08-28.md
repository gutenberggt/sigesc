# P0-F7.1 — Materialização estruturada das conciliações manuais

## Estado

Implementação de suporte **privada, offline e sem banco de dados**. Esta etapa não executa alterações no SIGESC e não constitui autorização para executor.

## Origem

O P0-F7 de produção confirmou 144 decisões humanas seladas, com zero drift e zero documentos ausentes. Restaram 9 blockers: 8 `MANUAL_RECONCILIATION_REQUIRES_STRUCTURED_VALUE` e 1 `TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED`.

As 8 reconciliações manuais pertencem exclusivamente a **Ciências**, coleção `learning_objects`: 6 no campo `methodology` e 2 no campo `content`.

## Objetivo

Transformar exclusivamente as 8 decisões `MANUAL_RECONCILIATION` já seladas no P0-F6 em valores finais estruturados fornecidos por um responsável humano.

A P0-F7.1:

- valida a cadeia P0-F5 -> P0-F6 -> P0-F7 por SHA canônico;
- exige P0-F7 com `snapshot_drift_units=0` e `missing_review_documents=0`;
- exige correspondência exata entre as decisões manuais do P0-F6 e os blockers manuais do P0-F7;
- aceita apenas `learning_objects.content` e `learning_objects.methodology` nesta versão;
- gera uma estação HTML autocontida/offline e privada (`0600`);
- mostra Registro 1, Registro 2, contexto, autoria e justificativa humana anterior;
- mantém o campo de valor final vazio: nenhuma sugestão, combinação ou preenchimento automático;
- exporta JSON privado somente após todas as unidades receberem valor final não vazio;
- sela o JSON final com `structured_reconciliation_manifest_sha256`;
- não acessa MongoDB, não possui `--apply` e não executa qualquer mutação.

## Contrato de segurança

- `database_access = false`
- `database_mutation = false`
- `automatic_recommendation = false`
- `automatic_resolution = false`
- `no_automatic_combination = true`
- `not_authorization_for_executor = true`
- arquivos sensíveis gerados em modo `0600`
- CSP offline com `connect-src 'none'`

## CLI

Construção da estação:

```bash
python scripts/build_p0f7_1_private_structured_manual_reconciliation_station.py build \
  --packet <p0f5-private-review.json> \
  --sealed <p0f6-human-decisions-sealed.json> \
  --preflight <p0f7-private-preflight.json> \
  --output <p0f7-1-station.html>
```

Selagem posterior:

```bash
python scripts/build_p0f7_1_private_structured_manual_reconciliation_station.py seal \
  --packet <p0f5-private-review.json> \
  --sealed <p0f6-human-decisions-sealed.json> \
  --preflight <p0f7-private-preflight.json> \
  --reconciliations <p0f7-1-manual-reconciliations.json> \
  --output <p0f7-1-manual-reconciliations-sealed.json>
```

## Fora de escopo

- interpretar automaticamente a justificativa anterior;
- sugerir texto final;
- resolver o blocker de alocação docente de Geografia;
- remapear `course_id`;
- atualizar, excluir, consolidar ou retirar `courses`;
- calcular ou autorizar o número final de writes;
- executar qualquer alteração em produção.

O blocker docente será tratado separadamente na P0-F7.2 read-only.
