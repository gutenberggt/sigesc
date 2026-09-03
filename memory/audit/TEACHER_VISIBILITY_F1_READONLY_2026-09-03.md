# TEACHER-VISIBILITY-F1 — Auditoria comparativa read-only

Data: 2026-09-03
Tracking: issue #357

## Objetivo

Investigar, sem qualquer escrita, a situação em que registros de conteúdo e frequência existem ou foram informados pelos docentes, mas não são detectados/exibidos pela projeção atual do SIGESC.

A auditoria compara dois casos concretos em 2026:

### Ana Lucia Faria Pinto Tristão

Escola: **E M E I E F Monsenhor Augusto Dias de Brito**.

17 pares turma/componente:
- Língua Inglesa: 6º ANO A/B/C/D, 9º ANO A/B/C/D, 3ª ETAPA e 4ª ETAPA;
- Literatura e Redação: 6º ANO C/D, 7º ANO B/C e 9º ANO C;
- Estudos Amazônicos: 7º ANO A e 8º ANO C.

A investigação anterior já confirmou, como controle positivo, uma cisão de identidade de **Língua Inglesa**: os vínculos atuais dos oito pares dos 6º/9º anos referenciam uma identidade de `fundamental_anos_finais`, enquanto a massa histórica foi gravada majoritariamente sob outra identidade de mesmo nome (`eja_final`).

### Luiz Gomes dos Santos

Escola: **E M E I E F Jose Pereira Barbosa**.

6 pares, todos Matemática:
- 6º ANO A;
- 6º ANO B;
- 7º ANO A;
- 7º ANO B;
- 8º ANO A;
- 9º ANO A.

A causa do caso Luiz **não é presumida**. O objetivo é verificar se ele reproduz a cisão de identidade observada em Ana Lúcia ou se há drift de assignment, registros legados sem assignment, ausência real de registros ou outra combinação estrutural.

## Correção metodológica em relação a um coletor específico por professor

Um coletor que descubra componentes apenas pelos `course_id/component_id` atualmente referenciados por `teacher_assignments` ou `teacher_class_assignments` é insuficiente: no caso Ana Lúcia, a identidade problemática podia existir nos dados históricos mesmo sem ser o vínculo corrente.

Por isso esta F1 exige:

1. **escola exata** como parte do alvo;
2. catálogo completo de identidades de mesmo nome no tenant;
3. descoberta de identidades também a partir dos próprios metadados persistidos em `learning_objects`, `content_entries`, `attendance` e `attendance_documentary`;
4. comparação entre vínculo atual, vínculo DVD estrutural, vínculo legado e identidade efetivamente presente nos dados;
5. classificação separada de drift de `assignment_id`.

## Coleções lidas

Somente metadados estruturais de:
- `users` e `staff`, exclusivamente para resolver a identidade docente, sem email;
- `schools` e `classes`, para prender o caso à escola/turma/ano corretos;
- `courses`, para resolver identidades de componente e `nivel_ensino`;
- `teacher_assignments`;
- `teacher_class_assignments`;
- `learning_objects`;
- `content_entries`, sem texto pedagógico;
- `attendance`, sem `records`;
- `attendance_documentary`, sem `records`.

O serviço canônico `services.teacher_diaries.list_teacher_diaries` é reutilizado para identificar a projeção docente atualmente autorizada.

## Códigos principais de causa

- `CURRENT_BINDING_VS_SAME_NAME_DATA_IDENTITY_SPLIT`: o diário atual usa uma identidade, mas existem dados do mesmo componente sob outra identidade.
- `CURRENT_IDENTITY_EMPTY_ALT_IDENTITY_HAS_DATA`: caso forte de cisão: a identidade atual não tem dados e outra identidade de mesmo nome concentra os registros.
- `MULTIPLE_SAME_NAME_COMPONENT_IDENTITIES_IN_TENANT`: catálogo contém mais de uma identidade de mesmo nome no tenant/global.
- `LEGACY_BINDING_DIFFERS_FROM_CURRENT_BINDING`: vínculo legado ativo diverge do vínculo atual.
- `RECORDS_ON_HISTORICAL_SAME_TEACHER_ASSIGNMENT`: registros estão ligados a assignment histórico do mesmo professor.
- `LEGACY_RECORDS_WITHOUT_ASSIGNMENT`: registros sem `assignment_id` persistem no legado.
- `TARGET_COMPONENT_DATA_NOT_FOUND`: nenhum dado do componente foi localizado para o par no ano.
- `DATA_IDENTITY_ALIGNED_TO_CURRENT_BINDING`: os dados encontrados estão alinhados à identidade atual.
- `NO_CURRENT_AUTHORIZED_DIARY`: o serviço canônico não projeta diário atual para o par.
- `CROSS_TENANT_SAME_NAME_COMPONENT_REFERENCE`: metadado do par referencia identidade de mesmo nome pertencente a outro tenant.
- `CLASS_HAS_DATA_WITH_UNRESOLVED_COURSE_ID`: existem referências de curso sem correspondente resolvível no catálogo.

## Boundary

A auditoria é estritamente read-only:

- `database_mutation=false`;
- `production_writes=false`;
- MongoDB somente leitura;
- nenhuma chamada HTTP da aplicação;
- nenhum `attendance.records`;
- nenhum estudante ou matrícula;
- nenhum valor de nota;
- nenhum texto pedagógico;
- nenhum ID técnico bruto no resultado;
- nenhuma leitura de `audit_logs.old_value/new_value/description`;
- nenhum backfill, merge de componente, remapeamento de `course_id`, correção de assignment ou saneamento;
- MT-1, Transferência Institucional e AEE intocados.

## Execução em produção

O workflow `.github/workflows/teacher-visibility-f1-readonly.yml` só executa o coletor quando o owner abrir uma issue com título exato:

`[TEACHER-VISIBILITY-F1] <SHA-40-hex-de-main>`

Corpo obrigatório:

```text
TEACHER_VISIBILITY_F1=AUTHORIZED
CONFIRMATION=AUDIT_TWO_TEACHER_VISIBILITY_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=357
TARGET_SHA=<mesmo SHA do titulo>
```

O gate falha fechado se a `main` avançar, se a issue #357 não estiver aberta ou se qualquer campo divergir.

A execução usa o mesmo acesso SSH pinado já empregado pelos workflows forenses existentes e envia o script, via stdin, para execução read-only dentro do container de backend. Nenhum deploy da aplicação é necessário para executar a auditoria após o coletor estar em `main`.

## Saída

O resultado contém uma matriz dos 23 pares com:
- vínculo atual/estrutural/legado;
- quantidade de identidades de mesmo nome;
- fingerprint da identidade (sem ID bruto), nível de ensino e relação com o tenant;
- contagens e intervalos de datas por coleção;
- partição de assignment em atual, histórico do mesmo professor, sem assignment e estrangeiro/indeterminado;
- códigos de causa por par;
- resumo causal por professor.

Nenhuma correção de dados é autorizada por esta F1. Qualquer saneamento posterior exige desenho, preflight e autorização humana próprios.
