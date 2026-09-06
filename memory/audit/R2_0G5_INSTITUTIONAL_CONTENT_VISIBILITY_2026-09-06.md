# R2.0g.5 — Paridade institucional de exibição de conteúdos

## Incidente

Após a R2.0g.4, o conteúdo canônico reconstruído para Luiz Gomes dos Santos passou
a aparecer em `/professor/objetos-conhecimento`, mas continuou ausente para o
mesmo recorte quando a tela `LearningObjects` era aberta por gestão em
`/admin/learning-objects`.

## Requisito do owner

A mesma escola + turma + componente + período deve produzir a mesma projeção
pedagógica para os perfis autorizados de professor, coordenação, secretaria,
direção, gerência, administração, super administração e SEMED.

A paridade é de **leitura**. Escrita continua sujeita a RBAC, ownership pedagógico,
escola, tenant, deadlines e regras DVD.

## Causa

- R2.0g.4 era condicionada exclusivamente a `/professor/objetos-conhecimento`;
- gestão usa o mesmo componente React por `/admin/learning-objects`, mas seguia no
  reader legado;
- o reader canônico DVD aceitava `semed3`, porém não `semed`, `semed1`, `semed2`;
- `auxiliar_secretaria` já possuía a superfície de consulta, mas não integrava o
  conjunto gerencial de visualização de snapshots DVD.

## Decisão

1. Generalizar a ponte de composição para as duas superfícies de `LearningObjects`.
2. No fallback do professor, preservar a R2.0g.4: somente canônicos sem
   `assignment_id` são compostos automaticamente.
3. Na superfície institucional de gestão, compor também canônicos com
   `assignment_id`, sempre após o filtro canônico de autorização.
4. Manter `content_entries` como SSoT; nunca duplicar em `learning_objects`.
5. Preservar o `assignment_id` se um item composto for manipulado posteriormente.
6. Ampliar somente leitura institucional para `semed`, `semed1`, `semed2` e
   `auxiliar_secretaria`; nenhum papel novo recebe escrita.

## Segurança

- tenant/school scope continuam fail-closed;
- `MANAGEMENT_EDIT_ROLES` não é alterado;
- `WRITE_ROLES` não é alterado;
- nenhum dado acadêmico é criado, migrado, copiado ou regravado pela correção;
- outros componentes continuam excluídos pela dupla validação
  `class_id + component_id + período`;
- canônicos DVD continuam sujeitos ao snapshot histórico de assignment.

## Gates

- teste de política backend: extensão somente de VIEW e idempotência;
- contrato estático: professor + gestão cobertos pela mesma ponte;
- regressão frontend: professor legado não absorve assignment DVD;
- regressão frontend: gestão absorve canônicos com e sem assignment do mesmo
  recorte, sem misturar componente;
- preservação da precedência canônica sobre representação legada equivalente;
- CI global antes de qualquer merge.

## Governança

Issue: #477.

Nenhum merge, deploy ou nova cópia de conteúdo está implícito nesta etapa.
