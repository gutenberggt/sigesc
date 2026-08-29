# P0-F7.9D2 — Resolução offline de alvos curriculares seguros

Data: 2026-08-29

## Objetivo

Classificar exclusivamente os conflitos já confirmados pela P0-F7.9C1 (`TEACHER_ASSIGNMENT_LEVEL_MISMATCH` e `TEACHER_ASSIGNMENT_SERIES_MISMATCH`) em três filas de proposta:

- `UNIQUE_SAFE_TARGET`: existe exatamente um componente alternativo homônimo aceito pela mesma fronteira de escrita da P0-F7.9B;
- `MULTIPLE_SAFE_TARGETS_REVIEW`: existem dois ou mais componentes alternativos homônimos aceitos e a escolha exige revisão humana;
- `NO_SAFE_TARGET`: nenhum componente alternativo homônimo é aceito pela fronteira de escrita.

A classificação `UNIQUE_SAFE_TARGET` significa apenas alvo curricular único validado no snapshot atual. Ela **não autoriza escrita automática** e não substitui autorização humana para remediação em produção.

## SSoT

A geração de candidatos usa somente o nome canônico já existente em `utils.curriculum_resolver._norm_name`. O aceite curricular de cada candidato é feito exclusivamente por `services.teacher_assignment_integrity.validate_teacher_assignment_curriculum`.

Não há implementação paralela das regras de nível/série.

## Entradas locais

- `private/p0f7_9c1/p0f7_9c1-network-audit.json`;
- `private/p0f7_9c1/p0f7_9c1-reference.json`;
- 23 páginas `private/p0f7_9c1/pages/school-*.json` já coletadas e seladas.

Nenhuma nova consulta a MongoDB é necessária.

## Política de candidatos

1. exclui o próprio `course_id` atual;
2. exige mesmo nome após `_norm_name`;
3. exige mesma mantenedora;
4. exclui componente explicitamente inativo/desativado/excluído;
5. submete cada candidato restante à `validate_teacher_assignment_curriculum` com a turma, escola e ano originais.

O nome é apenas mecanismo de geração de candidatos. Compatibilidade não é inferida pelo nome.

## Escopo

A P0-F7.9D2 não processa os casos ainda inconclusivos da P0-F7.9C1:

- `TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED`;
- `TEACHER_ASSIGNMENT_CLASS_SERIES_REQUIRED`;
- `TEACHER_ASSIGNMENT_SERIES_SCOPE_REVIEW_REQUIRED`;
- `AUDIT_COURSE_RECORD_MISSING`.

Esses grupos permanecem em filas próprias de investigação/saneamento.

## Segurança

- produção: sem acesso;
- MongoDB: sem acesso;
- backend remoto: sem execução;
- estudantes/matrículas/notas/frequência: não lidos;
- identidade docente: não utilizada;
- `teacher_assignments`: nenhuma escrita;
- remediação: não executada.

## Saída

`private/p0f7_9d2/p0f7_9d2-safe-targets.json`

O relatório contém resumo das três filas e, por vínculo confirmado, o alvo ou os alvos aceitos pelo SSoT, além dos códigos de rejeição dos candidatos homônimos não aceitos.

## Gate para etapa posterior

Nenhum plano de escrita P0-F7.9D3 poderá ser produzido antes de:

1. a P0-F7.9D2 fechar cobertura exata de todos os conflitos confirmados;
2. os `UNIQUE_SAFE_TARGET` serem revisados como propostas, não como mutações aprovadas;
3. qualquer ação de produção receber autorização explícita específica e possuir rollback/auditoria.
