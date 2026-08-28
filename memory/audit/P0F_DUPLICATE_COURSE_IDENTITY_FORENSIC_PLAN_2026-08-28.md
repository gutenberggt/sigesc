# P0-F — DUPLICATE_COURSE_IDENTITY — plano forense READ-ONLY

Data: 2026-08-28

## 1. Origem

O P0 Global contabiliza `DUPLICATE_COURSE_IDENTITY` por **grupo de identidade**, usando a chave:

`(mantenedora_id, name.casefold(), nivel_ensino.casefold())`

O valor histórico observado em produção foi `3`. Portanto, a hipótese operacional correta é **três grupos duplicados**, e não necessariamente três documentos.

## 2. Objetivo

Produzir evidência determinística para cada grupo duplicado, sem escolher automaticamente um curso canônico e sem executar qualquer mutação.

Para cada grupo o auditor deve registrar:

- identidade nominal normalizada;
- todos os `course_ids` atuais;
- metadados seguros dos cursos;
- quantidade de referências por `course_id` e coleção;
- exemplos seguros de documentos que referenciam cada ID;
- turma e escola quando resolvíveis;
- histórico de auditoria dos cursos;
- arestas históricas `removed_id -> kept_id` quando houver consolidação registrada;
- classificação forense baseada apenas na distribuição das referências.

## 3. SSoT de referências

O auditor usa exclusivamente `services.course_reference_integrity.COURSE_REFERENCE_SPECS` para descobrir as coleções/campos críticos que referenciam `courses.id`.

Não é criada uma segunda lista de referências.

## 4. Classificações

As classificações são conservadoras e **não autorizam consolidação**:

- `NO_REGISTERED_REFERENCES_REQUIRES_REVIEW`
- `ONE_REFERENCED_ID_OTHERS_UNUSED_REQUIRES_REVIEW`
- `MULTIPLE_REFERENCED_IDS_REQUIRES_REVIEW`
- `AUDIT_HISTORY_FOUND_REQUIRES_REVIEW`

Mesmo um ID atualmente sem referências registradas não é automaticamente deletável. Qualquer futura consolidação exigirá etapa separada com contrato próprio, manifesto selado, backup/rollback, CAS e autorização humana explícita para escrita em produção.

## 5. Invariantes

- READ-ONLY;
- sem `--apply`;
- sem `--rollback`;
- sem mutadores MongoDB;
- nenhum curso canônico escolhido automaticamente;
- nenhum remapeamento;
- nenhuma criação/exclusão de curso;
- nenhum writer alterado;
- nenhuma alteração em AEE;
- tenant preservado na própria identidade nominal.

## 6. Execução prevista

Após PR, CI e autorização de merge:

1. deploy do `main` no Coolify;
2. execução do auditor em produção com `--academic-year 2026`;
3. preservação do JSON e SHA-256;
4. resumo compacto dos grupos;
5. decisão individual por grupo em etapa posterior.

## 7. Escopo explicitamente fora do P0-F

- consolidar cursos;
- escolher ID vencedor;
- atualizar referências;
- excluir ou arquivar cursos;
- alterar documentos pedagógicos;
- executar qualquer write no MongoDB.
