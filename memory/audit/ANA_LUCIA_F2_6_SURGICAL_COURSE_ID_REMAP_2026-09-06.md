# ANA-LUCIA-F2.6 — remapeamento cirúrgico de `course_id`

Data: 06/09/2026
Tracking: #480
PR de implementação: #483

## Autorização

O proprietário autorizou explicitamente a execução de todas as etapas necessárias para a conclusão do saneamento, incluindo escrita controlada em produção, merge e deploy, desde que preservados os gates e a governança existentes.

## Escopo fechado

Somente os registros de 2026 atribuíveis a Ana Lucia Faria Pinto nas oito combinações de Língua Inglesa dos 6º/9º anos da E M E I E F Monsenhor Augusto Dias de Brito:

- 6º ANO A/B/C/D;
- 9º ANO A/B/C/D.

Baseline adjudicado:

- `learning_objects`: 198 candidatos;
- `attendance`: 392 candidatos;
- total: 590 documentos;
- 8 `learning_objects` já existentes na identidade atual;
- 17 `attendance` já existentes na identidade atual;
- zero colisões de chave natural no F2.4;
- 74 frequências com tenant ausente, adjudicadas deterministicamente no F2.5B sem backfill;
- 4 frequências agregadas sem `aula_numero`, preserváveis sem inferência/backfill;
- 74 relações `copied_from_id`, sendo 73 pais dentro do conjunto candidato e 1 pai ausente preexistente, sem nova quebra de linhagem causada pelo remapeamento.

## Única mutação autorizada

`course_id`: identidade legada de Língua Inglesa/EJA Final → identidade canônica de Língua Inglesa/Ensino Fundamental Anos Finais.

Não autorizado neste executor:

- backfill de `mantenedora_id`;
- backfill/inferência de `aula_numero`;
- alteração de `copied_from_id`;
- alteração de autoria;
- alteração de `attendance.records`;
- alteração de conteúdo/metodologia/observações;
- alteração de notas;
- exclusão, inserção, merge global de componente ou atualização em massa.

## Executor

`backend/scripts/ana_lucia_f2_6_surgical_course_id_remap.py`

Contrato:

1. resolve dinamicamente professora, staff, vínculos, turmas, escola, tenant e as duas identidades do componente;
2. exige baseline exato e adjudicações F2.4/F2.5B antes da primeira escrita;
3. executa `update_one` CAS documento a documento;
4. altera somente `course_id`;
5. em qualquer falha durante a execução ou pós-condição, tenta rollback compensatório em ordem reversa;
6. só retorna sucesso em `APPLIED_AND_VERIFIED` ou quando detecta estado previamente aplicado e integralmente verificável (`ALREADY_APPLIED_VERIFIED`).

## Runtime gate

Workflow: `.github/workflows/ana-lucia-f2-6-surgical-course-id-remap.yml`

O runtime exige issue aberta pelo proprietário no formato:

```text
[ANA-LUCIA-F2.6-RUNTIME] <TARGET_SHA>
```

com corpo contendo autorização explícita, SHA exato de `main`, ano 2026, tracking #480 e baselines 198/392.

A execução ocorre no environment `production`, usa confiança SSH pinada e transmite o executor do SHA autorizado diretamente ao container backend em execução. O artefato de evidência é retido por 90 dias.

## Sequência de conclusão

1. gates do PR verdes;
2. PR #483 marcado pronto e integrado em `main`;
3. CI de `main` verde;
4. F2.6 executado e pós-verificado em produção;
5. release de produção pelo workflow canônico SIGESC/Coolify;
6. smoke pós-deploy e registro de encerramento.
