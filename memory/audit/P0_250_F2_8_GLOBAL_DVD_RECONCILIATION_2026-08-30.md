# P0 #250 — F2.8: reconciliação global do vínculo docente/DVD

## Motivação

A F2.7 comprovou funcionalmente que a projeção mista resolve o caso real sem perda
de dados: componentes já cobertos pelo Diário por Vínculo (DVD) usam a origem
canônica e componentes ainda legados permanecem visíveis por fallback estritamente
limitado ao entitlement ativo do professor.

Esse mecanismo é uma **rede de segurança de transição**, não a arquitetura final.
A solução definitiva não pode depender de descobrir professor por professor quais
componentes ficaram fora do cutover.

## Problema estrutural

Hoje coexistem duas representações de vínculo:

1. `teacher_assignments`
   - chave operacional histórica: `staff_id + class_id + course_id + academic_year`;
   - alimenta `/professor/turmas` e vários módulos legados;
   - não modela integralmente validade, perfil do diário e capacidades DVD.

2. `teacher_class_assignments`
   - usa `teacher_id` (usuário), turma e `component_id` opcional;
   - possui validade temporal, tenant/escola e `diary_settings` explícitos;
   - é revalidado pela camada canônica de autorização do Diário por Vínculo.

Enquanto essas duas coleções puderem divergir independentemente, qualquer módulo
que escolher uma delas como fonte pode produzir diferenças de visibilidade.

## Objetivo definitivo

Estabelecer a invariável institucional:

`professor + tenant + ano + escola + turma + componente alocado`

`=> exatamente um entitlement canônico válido e a mesma visibilidade em Notas, Frequência, Conteúdo e Promoção.`

A F2.7 deve desaparecer do caminho normal quando a reconciliação provar que nenhum
componente elegível permanece `LEGACY_ONLY`.

## F2.8.0 — decisão arquitetural

A direção proposta é separar **entitlement** de **compatibilidade**:

- `teacher_class_assignments` evolui para a representação canônica do vínculo
  docente rico (identidade do usuário, turma, componente opcional, validade,
  escola/tenant e configuração de diário);
- `teacher_assignments` permanece temporariamente como fonte/compatibilidade
  histórica até a reconciliação e a convergência dos leitores;
- nenhum novo módulo deve decidir autorização consultando uma das coleções de
  forma ad hoc;
- uma camada de serviço canônica deverá projetar o entitlement docente para
  Notas, Frequência, Conteúdo, Promoção e `/professor/turmas`;
- `diary_settings.enabled=false` ou ausência de cobertura DVD não pode ser
  interpretada como inexistência de alocação pedagógica; são dimensões distintas.

A migração de dados só será proposta após inventário global read-only e regras
idempotentes comprovadas.

## F2.8.1 — inventário global read-only

O coletor desta fase varre **todas as alocações ativas de 2026** sem nomes
hardcoded. Ele não lê notas, frequência, conteúdos ou estudantes.

Cada par ativo `staff + turma + componente` é classificado como:

- `CANONICAL_COVERED`;
- `PARTIAL_CUTOVER_COMPONENT_MISSING`;
- `LEGACY_ONLY_CLASS`;
- `DVD_PRESENT_INVALID`;
- `DVD_DUPLICATE_COVERAGE`;
- `LEGACY_DUPLICATE`;
- `IDENTITY_UNRESOLVED`;
- `USER_ROLE_NOT_PROFESSOR`;
- `TENANT_SCOPE_UNRESOLVED`;
- `SCHOOL_SCOPE_MISSING`;
- `COURSE_UNRESOLVED`;
- `OUT_OF_DVD_SCOPE`.

Por professor+turma, a projeção é agregada em:

- `FULL_CANONICAL`;
- `PARTIAL_CUTOVER`;
- `LEGACY_ONLY`;
- `REQUIRES_REVIEW`;
- `OUT_OF_DVD_SCOPE`.

O cenário Abadia (7 componentes canônicos + 2 ainda legados) é apenas um teste de
regressão. Outro professor com 6+3, 8+1 ou qualquer outra combinação é detectado
pela mesma regra.

## F2.8.2 — plano de reconciliação determinístico

Somente após conhecer as cardinalidades globais será gerado um plano de migração
por classes de caso. O plano deverá:

1. resolver `staff_id -> user_id` de forma unívoca;
2. preservar tenant e escola da turma como âncoras;
3. não remapear componente por nome;
4. não criar vínculo quando houver ambiguidade;
5. detectar duplicidade antes de qualquer escrita;
6. preservar validade/substituição/perfil/shared quando já existirem;
7. produzir `dry-run` reproduzível e recibo por lote;
8. ser idempotente: repetir a execução não cria novas linhas nem altera dados já
   reconciliados sem necessidade.

Casos ambíguos ficam `NEEDS_REVIEW` e não são corrigidos automaticamente.

## F2.8.3 — backfill controlado

Qualquer criação/ajuste de `teacher_class_assignments` é mutação de produção e
exigirá autorização específica separada do inventário read-only.

O executor deverá operar em lotes pequenos, com:

- preflight;
- snapshot lógico das chaves afetadas;
- dry-run;
- gate de contagem esperado;
- escrita idempotente;
- pós-verificação;
- recibo/auditoria;
- rollback compensatório quando aplicável.

## F2.8.4 — convergência dos leitores

Depois da reconciliação dos dados, os módulos deixam de resolver entitlement por
caminhos distintos. A camada canônica passa a alimentar:

- `/professor/turmas`;
- Notas;
- Frequência;
- Objetos de Conhecimento;
- Livro de Promoção.

O frontend não deve inferir autorização por componente a partir de nomes ou de
respostas parciais de outro módulo.

## F2.8.5 — retirada do fallback F2.7

O fallback misto só pode ser removido quando uma auditoria global provar:

- zero `PARTIAL_CUTOVER`;
- zero `LEGACY_ONLY` entre classes DVD elegíveis;
- zero `DVD_DUPLICATE_COVERAGE`;
- zero casos críticos `REQUIRES_REVIEW` pendentes para o universo em cutover;
- paridade de entitlement entre os módulos.

Até lá, a F2.7 permanece como proteção de compatibilidade e não como estado final.

## Limites desta PR

Esta PR contém apenas instrumentação, testes e documentação da F2.8.1.

Não executa:

- migração/backfill;
- criação/edição de vínculo;
- alteração de RBAC;
- alteração de notas/frequência/conteúdo;
- deploy funcional;
- fechamento automático da issue #250.
