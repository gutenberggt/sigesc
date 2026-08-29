# P0-F7.9D4 — Sealed Remediation Plan

Data: 2026-08-29

## Objetivo

Transformar exclusivamente os casos `CLEAR_FOR_REMEDIATION_PLANNING` da P0-F7.9D3 em um manifesto determinístico e auditável de remediação futura, sem executar escrita em produção.

## Fontes seladas

- P0-F7.9D2: resolução offline de alvos curriculares seguros.
- P0-F7.9D3: collision preflight offline dos `UNIQUE_SAFE_TARGET`.

A D4 valida a cadeia SHA-256 entre D2 e D3, tenant, ano letivo, contagens e estado `PASS`. O plano falha se houver qualquer colisão ativa, drift de fonte, ausência de `staff_id` verificado, divergência de escopo ou mudança de `source_course_id`/`target_course_id` entre D2 e D3.

## Conteúdo do plano

Cada entrada registra:

- `assignment_id`, `school_id`, `class_id`, ano e código de integridade;
- componente de origem e alvo curricular validado;
- pré-condições fail-closed para uma futura escrita;
- mutação pretendida restrita a `course_id`;
- valor de rollback `target -> source`;
- hash determinístico individual e ordem estável;
- hashes canônicos das fontes D2/D3 e do próprio plano.

## Contrato de execução futura

O artefato D4 é `SEALED_PROPOSAL_ONLY_NON_EXECUTABLE`. Ele não contém executor de banco.

Antes de qualquer escrita futura, um executor separado deverá, para cada vínculo:

1. reler o documento sob escopo exato de tenant/ano/escola/turma/id;
2. confirmar que `course_id` ainda é o valor de origem selado e que o vínculo permanece ativo;
3. confirmar `staff_id` presente;
4. reaplicar a SSoT atual de integridade curricular ao alvo;
5. verificar novamente ausência de duplicidade ativa `staff + turma + alvo + ano`;
6. exigir correspondência única de todas as pré-condições;
7. registrar auditoria e validar pós-condições;
8. abortar de forma fail-closed diante de qualquer drift.

A autorização automática de merge de PR não equivale a autorização para escrita em produção. A execução histórica continuará sendo uma fase separada.

## Segurança

- `PRODUCTION_ACCESS=NO`
- `DATABASE_ACCESS=NO`
- `DATABASE_MUTATION=NO`
- `PRODUCTION_WRITES=NO`
- `REMEDIATION_EXECUTED=NO`
- nenhum dado de estudante;
- nenhum nome de professor.
