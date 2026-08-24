# Matrículas — Fonte Canônica · Fase 1

Data: 2026-08-24

## Objetivo

Estabelecer `enrollments` como a fonte canônica do vínculo acadêmico **estudante ↔ turma ↔ ano letivo**, corrigindo os caminhos de maior risco identificados na auditoria sem, nesta fase, migrar ou apagar dados históricos.

## Contrato arquitetural

1. `enrollments` é a fonte oficial da matrícula.
2. `students` continua sendo a fonte da pessoa/estudante.
3. `students.class_id`, `students.school_id`, `students.status` e `students.enrollment_number` são uma **projeção operacional da matrícula REGULAR ativa**, não uma segunda fonte de verdade.
4. Matrículas especiais (`aee`, `recomposicao_aprendizagem`, `reforco_escolar`) podem coexistir com a matrícula regular e **não podem substituir `students.class_id` da turma regular**.
5. `class_students` é legado. Nenhuma nova escrita deve depender dessa coleção. A emissão de documentos escolares deixa de consultá-la nesta fase.
6. `student_history` é trilha histórica/auditoria; não determina a matrícula atual.
7. `pre_matriculas` representa a solicitação anterior à matrícula. Uma conversão só é considerada concluída depois que `students` e `enrollments` foram efetivados de forma coerente.
8. Toda nova matrícula deve nascer com `mantenedora_id` coerente com estudante, escola e turma.
9. Novas escritas usam somente o conjunto de status canônicos: `active`, `completed`, `cancelled`, `transferred`, `relocated`, `progressed`, `dropout`.

## Correções da Fase 1

### P0 — conversão de pré-matrícula

Antes, a conversão criava o estudante com `status=active`, `class_id` e `enrollment_number`, mas não criava o documento equivalente em `enrollments`.

A nova implementação:

- exige uma turma regular válida;
- valida escola e turma;
- usa lock otimista contra dupla conversão;
- cria o estudante inicialmente sem turma e inativo;
- efetiva a matrícula pelo serviço canônico;
- só então marca a pré-matrícula como `convertida`;
- salva `converted_enrollment_id` para rastreabilidade;
- desfaz estudante/matrícula recém-criados caso a efetivação central falhe antes do commit lógico.

### Matrícula especial não altera a turma regular

O serviço canônico distingue turma regular de AEE/recomposição/reforço. A matrícula especial é gravada em `enrollments`, porém não atualiza a projeção `students.class_id`.

### Router de matrículas

`backend/routers/enrollments.py` deixa de inserir matrículas diretamente e delega a criação/cancelamento ao serviço de domínio.

Além disso:

- edição direta não pode mudar aluno/escola/turma/ano de matrícula ativa;
- reativação não pode ocorrer por `PUT` genérico, devendo passar por rematrícula;
- status legado é normalizado antes de novas gravações;
- encerramento/exclusão de matrícula regular reconstrói a projeção do estudante a partir de `enrollments`.

### Documentos escolares

`school_docs_service.py` deixa de usar `class_students` para descobrir a turma atual. A prioridade passa a ser a matrícula regular ativa em `enrollments`.

Durante a transição, `students.class_id` permanece somente como fallback de compatibilidade para registros legados e gera log `ENROLLMENT_LEGACY_FALLBACK`.

## Auditoria read-only

Foi adicionado:

```bash
python scripts/audit_enrollment_canonical.py
python scripts/audit_enrollment_canonical.py --json
```

O auditor não escreve no MongoDB e mede, entre outros:

- estudantes ativos sem matrícula regular ativa;
- divergência `students.class_id` × matrícula regular canônica;
- múltiplas matrículas regulares ativas no mesmo ano;
- matrículas com turma/aluno inexistente;
- divergência matrícula ↔ escola da turma;
- divergência de tenant;
- documentos sem `mantenedora_id`;
- status legados;
- pré-matrículas convertidas cujo estudante não possui `enrollments`.

As amostras da saída usam IDs, não nomes/CPF.

## O que NÃO é feito nesta fase

Nenhum dado de produção é migrado automaticamente neste PR.

Em especial, ainda ficam para a Fase 2:

1. refatorar os writers legados dentro de `backend/routers/students.py` (cadastro, rematrícula, remanejamento, progressão e reclassificação) para o serviço canônico;
2. eliminar a possibilidade de nova escrita de `reclassified` e converter o passivo para `progressed`;
3. executar a auditoria em produção e classificar cada divergência;
4. reparar, de forma auditável, pré-matrículas históricas convertidas sem documento em `enrollments`;
5. reconciliar `students.class_id` com a matrícula regular ativa;
6. retirar o fallback temporário de `students.class_id` dos consumidores após o saneamento;
7. aposentar `class_students` depois de confirmar que não restam consumidores relevantes;
8. avaliar transação MongoDB ou mutation wrapper para operações multi-documento críticas.

## Critério de liberação

A Fase 1 só deve ser integrada a `main` se:

- o CI geral permanecer verde;
- o workflow `Enrollment Canonical Contract` ficar verde;
- revisão do diff não identificar regressão nos fluxos de matrícula;
- não houver merge automático; a integração depende de autorização humana explícita.

## Pós-deploy recomendado

Executar primeiro apenas a auditoria read-only na produção:

```bash
cd /app/backend
python scripts/audit_enrollment_canonical.py --json > /tmp/sigesc_enrollment_canonical_audit.json
```

Não executar correção automática com base no relatório. Os achados serão usados para construir o plano reversível da Fase 2.
