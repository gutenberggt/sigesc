# #480 — Identidade canônica e visibilidade integral do diário

## Escopo aprovado

1. Corrigir a cisão de identidade de `Língua Inglesa` nos 6º/9º anos da E M E I E F Monsenhor Augusto Dias de Brito (2026): registros históricos persistidos sob o componente de EJA Final devem ser remapeados para o componente canônico de Fundamental/Anos Finais, quando comprovadamente atribuíveis a essas turmas.
2. Preservar 3ª/4ª Etapas no componente canônico de EJA, salvo evidência contrária.
3. Frequência permanece granular por aula/slot: `class_id + date + period + aula_numero`. Duas aulas previstas no mesmo dia podem e devem resultar em dois registros de frequência.
4. Conteúdo pode permanecer único por `class_id + course_id + date`, mesmo com duas aulas no dia.
5. Usuários autorizados por tenant/escola/turma/componente/ano devem visualizar todo o histórico válido de frequência e conteúdo independentemente de autoria (`teacher_id`, `staff_id`, `recorded_by`, `created_by`, `updated_by`). Autoria serve para auditoria/rastreabilidade, não para restringir a projeção de leitura.
6. RBAC e isolamento multi-tenant permanecem fail-closed.

## Sequência obrigatória

1. Preflight read-only e inventário exato dos documentos candidatos.
2. Verificação de colisões pelas chaves naturais de frequência e conteúdo.
3. Remapeamento somente de `course_id` nos documentos elegíveis; sem copiar conteúdo pedagógico e sem recriar frequência.
4. Reconciliação pós-remapeamento: cardinalidade, chaves naturais, tenant, assignment, linhagem e ausência de duplicação.
5. Testes HTTP por perfis autorizados para frequência e conteúdo, comprovando visibilidade integral por escopo e não por autoria.
6. Testes de regressão da regra: duas aulas => dois registros de frequência; conteúdo único por data é aceitável.
7. Sem merge e sem deploy até autorização humana explícita.

## Critério para a vistoria solicitada

Para cada data prevista pelo horário e calendário:

- `Frequência = SIM` somente quando todos os slots/aulas previstos para o componente naquela data estiverem registrados.
- `Conteúdo = SIM` quando existir ao menos um conteúdo válido para a turma/componente naquela data.
- Datas não letivas ou futuras não entram como pendência.

## Observação de SSoT

A identidade do componente é contextual ao nível de ensino. Não se deve transformar toda ocorrência de `Língua Inglesa` em um único ID global. A correção é entre a identidade histórica incorreta e a identidade canônica correta para a turma/nível em questão.
