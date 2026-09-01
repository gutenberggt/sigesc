# ANA-LUCIA-F2.4 — Preflight read-only de Remapeamento Cirúrgico

## Objetivo

Verificar, sem qualquer escrita, se os registros de 2026 atribuíveis à professora Ana Lucia Faria Pinto e persistidos nas oito turmas-alvo sob a identidade `Língua Inglesa / eja_final` podem futuramente ter apenas o `course_id` remapeado para a identidade operacional correta `Língua Inglesa / fundamental_anos_finais` sem colisões estruturais.

## Evidência herdada

A F2.3 classificou o caso como `CURRENT_BINDING_VS_LEGACY_DATA_IDENTITY_SPLIT`: os oito `teacher_assignments` e os oito vínculos DVD atuais apontam para a identidade de Anos Finais, enquanto o histórico relevante de `learning_objects` e `attendance` está majoritariamente sob a identidade de EJA Final.

Os dois documentos de `courses` são semanticamente legítimos e não devem ser consolidados globalmente. A F2.4, portanto, limita-se aos documentos das oito turmas-alvo atribuíveis à professora.

## Chaves naturais auditadas

A fase reutiliza as semânticas do P0-F3 após colapso do `course_id`:

- `learning_objects`: `class_id + date`;
- `attendance`: `class_id + date + period(default=regular) + aula_numero`.

Se origem e destino já possuem a mesma chave natural, o documento é classificado como colisão e nenhum payload pedagógico é lido para decidir automaticamente qual venceria.

## Critérios de bloqueio

O preflight bloqueia um futuro remapeamento direto quando encontrar qualquer um destes sinais:

1. tenant ausente ou divergente no candidato;
2. `assignment_id` já vinculado no candidato;
3. chave natural incompleta;
4. multiplicidade interna na origem ou destino;
5. chave natural já existente na identidade de destino.

Registros inativos/deletados ou não atribuíveis à professora são excluídos do conjunto candidato e contabilizados separadamente.

## Linhagem de cópia

`copied_from_id` é analisado apenas como metadado estrutural. O preflight registra se um futuro remapeamento deixaria filhos remapeados apontando para ancestrais que permaneceriam na identidade EJA, sem alterar a linhagem.

## Boundary

- MongoDB somente leitura;
- nenhum HTTP/login;
- sem `attendance.records`;
- sem estudantes/matrículas;
- sem valores de notas/frequência;
- sem texto pedagógico;
- sem IDs técnicos brutos em evidência;
- sem mutação, backfill, merge, remapeamento, exclusão ou saneamento.

## Resultado esperado

A saída deve separar:

- documentos candidatos;
- documentos excluídos do escopo;
- documentos estruturalmente não colidentes;
- colisões que exigem adjudicação humana;
- drift em relação ao baseline F2.2/F2.3;
- riscos de linhagem de cópia.

Mesmo que o preflight fique integralmente limpo, **nenhuma escrita fica autorizada**. Qualquer F3/F2.5 de remapeamento real exige autorização explícita separada e um executor fail-closed próprio.
