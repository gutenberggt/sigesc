# Assessment Policy v1 — Sprint 007 — Configuração Assistida + Dry-run Piloto

## 1. Objetivo

Permitir que a política avaliativa seja administrada a partir do contexto da **Mantenedora**, preservando `assessment_policies` como fonte única, versionada e auditável das regras.

A Sprint 007 cria a ponte administrativa necessária para configurar uma policy candidata e executar um dry-run piloto sem ativar a policy no runtime oficial de Notas.

## 2. Decisão arquitetural

O documento `mantenedoras` continua armazenando dados institucionais e alguns parâmetros legados (`media_aprovacao`, `frequencia_minima` e dependência), mas esses campos passam a ser tratados apenas como **referência legada** para a nova arquitetura.

A SSoT da política avaliativa é:

`assessment_policies`

Razões:

- versão por ano/vigência;
- escopo por escola/turma/série/componente/etapa/modalidade;
- hash determinístico da regra;
- lifecycle DRAFT → VALIDATED → PUBLISHED;
- reprodução histórica;
- isolamento por mantenedora;
- impossibilidade de alterar silenciosamente uma regra já publicada.

## 3. Regra municipal conhecida usada como caso de prova

Os testes podem representar a regra informada para a mantenedora de Floresta do Araguaia como **configuração**, nunca como constante global do engine:

- 1º e 2º Ano: avaliação conceitual C/ED/ND;
- equivalência C=10,0; ED=7,5; ND=5,0;
- 3º Ano em diante: avaliação numérica conforme policy aplicável;
- pesos B1=2, B2=3, B3=2, B4=3;
- média mínima por componente 5,0;
- frequência mínima informada 75%.

A arquitetura não presume que outra mantenedora utilize qualquer uma dessas regras.

## 4. Pendências institucionais deliberadamente não inferidas

Antes de uma policy municipal real poder ser considerada completa para publicação, o cadastro precisa registrar explicitamente:

1. qual entrada operacional representa cada recuperação no schema legado;
2. se a recuperação somente substitui o resultado quando melhora o valor original (`only_if_improves`);
3. qual é a base canônica da frequência de 75% (`global`, `stage` ou `component`);
4. a fonte normativa/institucional que fundamenta a policy.

O sistema não deriva esses valores do comportamento histórico do código.

## 5. Assisted Config

`backend/assessment_policy/assisted_config.py`

Responsabilidades:

- validar policy candidata sem IO;
- validar mapping legado explícito;
- calcular hash da regra e hash do mapping;
- indicar `can_save_draft`, `can_validate` e `can_dry_run`;
- bloquear edição de policy publicada/histórica;
- exigir contrato equivalente ao de publicação antes de liberar o piloto.

Salvar um DRAFT continua permitido mesmo com pendências semânticas, justamente para permitir construção progressiva da regra. Validar/dry-run exige completude.

## 6. Candidate Pilot Runner

`backend/assessment_policy/pilot_runner.py`

Responsabilidades:

- receber explicitamente uma policy DRAFT/VALIDATED;
- ler turmas e grades exclusivamente em modo read-only;
- reconstruir o contexto acadêmico canônico;
- respeitar série efetiva do estudante em turma multisseriada;
- ignorar explicitamente (`skipped_out_of_scope`) registros que não pertençam ao escopo da policy candidata;
- comparar `grades.final_average` persistido com o Calculator v1;
- produzir relatório de matches, divergências e issues.

O piloto não consulta a policy publicada atual para substituir a candidata e não altera nenhum dado.

## 7. API administrativa

Prefixo: `/assessment-policy-admin`

Nesta sprint:

- `GET /overview`
- `POST /preview`
- `POST /drafts`
- `PUT /drafts/{policy_id}`
- `POST /drafts/{policy_id}/validate`
- `POST /pilot`

Não existem endpoints de `publish` ou `cutover`.

A API exige `super_admin` e usa a mantenedora ativa como escopo obrigatório.

A única persistência permitida pela Sprint 007 ocorre no lifecycle de DRAFT/VALIDATED da coleção `assessment_policies`. O piloto é read-only.

## 8. Tela da Mantenedora

A interface deve apresentar uma seção própria de **Política de Avaliação** dentro do cadastro da mantenedora, deixando visualmente claro que:

- os campos antigos de aprovação são referência legada;
- as regras versionadas residem em `assessment_policies`;
- salvar um rascunho não publica a regra;
- validar não ativa a regra;
- o piloto não altera notas;
- publicação/cutover não estão disponíveis nesta sprint.

## 9. Invariantes

- nenhuma regra municipal hardcoded no Calculator/Outcome;
- nenhuma alteração no `grade_calculator.py` legado;
- nenhuma escrita em `grades`, frequência ou matrícula pelo piloto;
- nenhum backfill;
- nenhuma policy municipal criada automaticamente;
- nenhum publish/cutover;
- nenhuma alteração automática de `final_average` ou `status`;
- multisseriação usa a série individual comprovada, nunca o rótulo amplo da turma.

## 10. Gate

O workflow `Assessment Policy v1 - Assisted Config Gate` executa toda a regressão acumulada da Assessment Policy, os testes específicos da Sprint 007, o Scope Creep Guard e um guard explícito contra endpoints de publish/cutover e chamadas ao motor legado.

Somente após todos os gates, CI geral, Transferência e DVD ficarem verdes a sprint poderá ser integrada.
