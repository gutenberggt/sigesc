# Assessment Policy v1 — Sprint 008 — Fase 1
## OperationalBinding — contratos puros e canonicalização

## 1. Objetivo

Implementar exclusivamente o contrato puro do `OperationalBinding` e sua
canonicalização, sem repository, MongoDB, HTTP, router, UI, publicação ou
cutover.

## 2. Entregáveis autorizados

- `backend/assessment_policy/operational_binding.py`;
- testes puros do contrato;
- workflow/gate próprio;
- extensão mínima do Scope Creep Guard;
- documentação de auditoria da Fase 0 e Fase 1.

## 3. Contrato

`AssessmentPolicyOperationalBinding` contém:

- identidade do binding;
- identidade exata da policy;
- `policy_rule_hash`;
- `binding_version`;
- `revision`;
- `source_schema`;
- `period_field_map`;
- `recovery_field_map`;
- lifecycle `draft/validated/superseded`;
- `mapping_hash`;
- metadados de criação/validação.

### DRAFT

- pode possuir mapping incompleto;
- não carrega `mapping_hash` persistido;
- não carrega metadados de validação.

### VALIDATED / SUPERSEDED

- exige `mapping_hash`;
- exige `validated_by` e `validated_at`;
- mudanças futuras deverão ocorrer por nova versão, não por mutação silenciosa.

A persistência/lifecycle real não pertence a esta fase.

## 4. Canonicalização

O hash do mapping **não é reimplementado**.

`calculate_operational_mapping_hash()` delega ao mesmo
`calculate_mapping_hash()` usado pelo Shadow v1.

O módulo fornece também serialização canônica do conteúdo operacional efetivo
para auditoria, excluindo:

- `id`;
- `revision`;
- `status`;
- `mapping_hash` derivado;
- autoria;
- timestamps.

A Fase 1 **não cria `binding_hash`** e não altera `rule_hash`.

## 5. Validação pura

`validate_operational_binding(policy, binding)` verifica:

- tenant;
- `policy_id`;
- `policy_key`;
- `policy_version`;
- aderência do `policy_rule_hash` ao conteúdo atual da policy;
- integridade de eventual `policy.rule_hash`;
- mapping semântico pelo contrato canônico do Shadow;
- integridade de eventual `mapping_hash` persistido.

Nenhuma consulta ao banco é executada.

## 6. Fail-closed

Mudança no conteúdo da policy sem mudança correspondente no binding resulta em
`ASSESSMENT_POLICY_BINDING_POLICY_RULE_HASH_MISMATCH`.

Mapping inválido resulta em `ASSESSMENT_POLICY_BINDING_MAPPING_INVALID`.

`mapping_hash` divergente resulta em
`ASSESSMENT_POLICY_BINDING_MAPPING_HASH_MISMATCH`.

Nenhum campo legado é inferido.

## 7. Invariantes

- zero MongoDB;
- zero HTTP/FastAPI;
- zero router;
- zero UI;
- zero publish/cutover;
- zero alteração de Notas;
- zero alteração de `grade_calculator.py`;
- zero backfill;
- `AssessmentPolicy` continua separada do binding;
- `rule_hash` continua exclusivamente normativo;
- `mapping_hash` continua exclusivamente operacional.

## 8. Gate

O workflow `Assessment Policy v1 - Operational Binding Gate` deve executar:

- compile do pacote;
- regressão acumulada da Assessment Policy;
- testes específicos da Fase 1;
- Scope Creep Guard;
- guard estático contra IO/router/publish/cutover no novo módulo.
