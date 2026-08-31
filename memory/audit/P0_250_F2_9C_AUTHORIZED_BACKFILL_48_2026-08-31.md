# P0 #250 — F2.9C — Executor/backfill autorizado dos 48 targets selados

Data: 2026-08-31  
Escopo: `teacher_class_assignments`  
Ano letivo: 2026  
Referência temporal: 2026-08-31

## 1. Autorização humana explícita

O responsável humano autorizou de forma clara e explícita a F2.9C: execução controlada do backfill dos **48 targets previamente selados pela F2.9B**.

Esta autorização é restrita ao conjunto criptograficamente selado abaixo. Não autoriza expansão de escopo, tratamento automático dos 883 casos `REQUIRES_REVIEW`, remapeamentos adicionais, exclusões funcionais, hard delete ou qualquer outra mutação fora das 48 inserções projetadas.

A autorização operacional será materializada por uma issue criada pelo proprietário e vinculada ao **SHA exato do executor já mergeado em `main`**. O workflow recusa execução se `main` se mover ou se qualquer seal abaixo divergir.

## 2. Fonte selada F2.9B

- F2.9B source/main SHA: `eea0ee3b9905b65e82e440243566b6f44926f7af`
- F2.9B successful run: `33356353896`
- Artifact privado: `9745250820`
- Artifact digest: `26d0904d231a7ed23f41487a57a8e2fd08b0e0b6ac96b14ef7897d130123ddfd`
- Targets selados: `48`
- Targets SHA-256: `fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177`
- Operations SHA-256: `f3fb8c4b7d8d3a9e51939b8cf2d40e756759744e431471d073afd038295b47e5`
- Bundle SHA-256: `ddca5bb662a5670b96459ad5f5748f123ed65e52bdd2fe739e933b18d4d164d4`

A F2.9C não reconstrói targets por inferência própria. Ela só aceita o manifesto privado exato da F2.9B e revalida toda a cadeia de hashes antes de alcançar qualquer primitive de escrita.

## 3. Fonte SSoT F2.9A

O manifesto F2.9B deriva do planner F2.9A homologado e o executor fixa também a cadeia de origem:

- F2.9A SHA: `794cf799a8f4091d35401d45d8203109b4e5dd0d`
- F2.9A run: `33350397799`
- planner blob SHA: `42178d99c479ab43d4345c4a5346cac6735eefd3`
- plan SHA-256: `fbfe46dd455e45ad65c510d75022d52918c8993c21cc76593f1915d5324fb177`

Os blobs da F2.9A e F2.9B são verificados pelo guard e novamente pelo workflow de produção.

## 4. Gate exato de produção

A execução só pode ocorrer a partir de uma issue owner-authored com título:

`[P0-250-F2.9C-EXECUTE-48-TARGETS] <TARGET_SHA>`

O corpo deve fixar simultaneamente:

- autorização `P0_250_F2_9C_EXECUTE=AUTHORIZED`;
- confirmação `APPLY_P0_250_F2_9C_SEALED_48_TARGETS`;
- ano/referência;
- SHA exato de `main` contendo o executor;
- F2.9B source SHA;
- artifact ID e artifact digest;
- targets SHA-256;
- operations SHA-256;
- bundle SHA-256.

Qualquer divergência fecha o caminho antes de produção.

## 5. Preflight e live reseal antes da primeira escrita

Antes da primeira inserção o executor exige que o estado dos 48 targets seja homogêneo:

1. **todos ausentes**, permitindo prosseguir; ou
2. **todos presentes e exatamente iguais ao manifesto**, tratado como replay idempotente sem novas escritas.

Estado parcial, documento divergente, drift do vínculo legado, colisão de chave natural ou conflito de `grades_official_owner` causa falha fechada.

Quando todos estão ausentes, o executor exige ainda um **live reseal**: F2.9A + F2.9B são reexecutadas em produção imediatamente antes do write e o manifesto resultante deve ser canonicamente idêntico ao bundle selado. Depois do reseal, as precondições são verificadas uma segunda vez.

## 6. Superfície de mutação

A superfície normal é deliberadamente mínima:

- coleção: `teacher_class_assignments`;
- operação normal: `insert_one`;
- quantidade máxima desta autorização: exatamente 48 inserções;
- nenhum `update`, `replace`, `bulk_write`, `delete_many`, hard delete ou mutação em outra coleção.

Antes de cada `insert_one`, são rechecados vínculo legado, ausência do target ID, ausência da chave natural ativa e conflito de proprietário oficial de notas. Depois de cada insert, exige-se igualdade exata com o documento selado e cardinalidade natural igual a 1.

## 7. Rollback compensatório

Se qualquer operação do lote falhar, o executor percorre apenas as inserções feitas nesta execução, em ordem reversa.

O único primitive adicional permitido é `delete_one`, exclusivamente para rollback, e apenas quando o documento persistido ainda é **exatamente igual** ao target selado correspondente (`DELETE_INSERTED_IF_EXACT_PROJECTED_MATCH`).

Se um documento tiver mudado ou se qualquer remoção compensatória não puder ser confirmada, o executor classifica o cenário como `CRITICAL_ROLLBACK_INCOMPLETE` e deve parar sem nova tentativa automática.

## 8. Idempotência e recuperação de falhas externas

Se uma execução anterior tiver concluído as 48 inserções, mas falhado posteriormente no upload/comentário do receipt, uma nova execução não duplica dados. Se os 48 documentos estiverem presentes e exatamente iguais aos targets selados, a classificação será:

`F2_9C_48_TARGETS_ALREADY_APPLIED_EXACT`

com zero novas escritas.

O sucesso com escrita nova será:

`F2_9C_48_TARGETS_APPLIED_AND_VERIFIED`

## 9. Evidência e privacidade

O workflow gera:

- receipt público redigido, com contagens, classificação e hashes;
- receipt privado por operação em artifact do GitHub Actions com retenção limitada.

IDs de target, professor/staff e PII não devem aparecer em logs ou comentário público. A execução não lê notas, frequência, conteúdo acadêmico ou dados de estudantes.

## 10. Encerramento

A F2.9C pode fechar apenas a issue-gate técnica criada para a execução. **A issue #250 deve permanecer aberta** para verificação pós-backfill e encerramento funcional posterior.
