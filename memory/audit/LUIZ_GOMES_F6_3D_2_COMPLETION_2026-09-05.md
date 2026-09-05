# LUIZ-GOMES-F6.3d.2 — conclusão técnica adaptativa

Data: 2026-09-05
Tracking: #357

## Contexto

As execuções anteriores da F6.3d.2 foram operacionalmente íntegras, mas demonstraram que o dump BSON coerente de 18/08/2026 não preserva necessariamente os campos de identidade com os mesmos nomes do schema atual:

- gate #409: `SCHOOL_CONTEXT_NOT_UNIQUE`;
- gate #411: `SCHOOL_CONTEXT_NOT_FOUND`, com `schools.name` inutilizável;
- gate #413: `SCHOOL_CONTEXT_NOT_STRUCTURALLY_RESOLVED`, com `candidate_school_groups=0` sob a suposição `classes.school_id`.

Esses resultados não demonstram ausência de conteúdo. Demonstram que os probes anteriores ainda carregavam hipóteses rígidas de schema histórico.

## Probe adaptativo

A versão adaptativa passa a resolver a estrutura histórica somente por aliases explícitos e convergência estrutural, sem assumir previamente os nomes atuais dos campos.

São avaliados aliases de:

- nome, ID, ano e vínculo escolar/tenant da turma;
- nome e ID do componente curricular;
- referência de turma, referência de componente e data em `learning_objects`;
- campos estruturais de ator e, quando disponível, de `teacher_assignments`.

O probe exige uma única solução estrutural capaz de identificar as seis turmas esperadas e evidência de Matemática nas quatro turmas-controle. Soluções múltiplas ou ausência de solução encerram fail-closed.

## Estados terminais

A F6.3d.2 só é tecnicamente encerrada em um de dois estados:

### A — `COMPLETED`

Exige cumulativamente:

1. schema histórico adaptativo resolvido de forma única;
2. exatamente uma estrutura coerente para as seis turmas;
3. Matemática comprovada nas quatro turmas-controle;
4. ator histórico derivado de forma exata sem lookup em `users`;
5. classificação de 8º A e 9º A.

### B — `INCONCLUSIVE / HISTORICAL_SCHEMA_INSUFFICIENT`

É aceito somente quando o próprio dump não preserva relações suficientes para resolver de forma única o schema/ator necessário. O resultado deve trazer `insufficiency_reason` explícito e `schema_resolution.terminal_state=INSUFFICIENT`.

Erros operacionais, de probe ou de boundary não são aceitos como estado terminal.

## Boundary

- dump de 18/08/2026 restaurado exclusivamente em Mongo temporário;
- `--network none`, zero portas publicadas;
- fonte BSON montada read-only;
- nenhuma escrita em produção;
- nenhuma leitura de estudantes, matrículas, notas ou `attendance.records`;
- payload pedagógico reduzido a presença/ausência booleana;
- nenhum ID técnico publicado;
- nenhum lookup em `users`;
- nenhuma recuperação, backfill, remapeamento ou deploy autorizado por esta fase.

Qualquer recuperação posterior exige etapa própria, preflight, CAS/idempotência, rollback e autorização específica.
