# P0-F7.9D7.8 — Runtime workload hardening

Data: 2026-08-30

## Objetivo

Impedir preventivamente que novos vínculos docentes ativos sejam criados ou
mantidos com `carga_horaria_semanal` incompatível com a matriz curricular
canônica, sem reabrir a remediação histórica P0-F7.9D7.x.

## Arquitetura

A regra curricular permanece centralizada. O router não conhece a matriz nem
faz cálculo de carga. A fronteira de domínio
`backend/services/teacher_assignment_integrity.py` passa a consumir a SSoT
`backend/utils/curricular_workload_policy.py` por meio de
`resolve_curricular_workload()`.

A validação é aditiva ao P0-F7.9B:

1. `validate_teacher_assignment_curriculum()` continua validando turma ×
   componente × escola × ano;
2. `validate_teacher_assignment_workload()` resolve a carga pela SSoT e valida
   `carga_horaria_semanal` somente quando a política se aplica;
3. Geografia, História e Ciências falham fechado quando a carga é ausente,
   irresolúvel ou divergente;
4. componentes ainda fora da SSoT de carga preservam o comportamento existente
   (`NOT_APPLICABLE`) para não ampliar escopo silenciosamente.

## Writers protegidos

A mesma barreira é ligada a todas as superfícies ativas de
`teacher_assignments`:

- criação titular;
- criação de substituição, após eventual herança da carga do titular;
- atualização cujo estado resultante seja ativo.

Os tokens históricos `ativo` e `active` passam a ser tratados de forma
consistente tanto na decisão de validação quanto em consultas de vínculo ativo.

## Regras preservadas

- multisseriada continua usando `MAX_ANNUAL_WORKLOAD` na SSoT;
- conversão institucional continua `ha / 8 = hm`, `hm / 5 = hs`, equivalente a
  `ha / 40 = hs`;
- nenhuma regra é duplicada no router;
- inativação/encerramento de passivo histórico continua permitido;
- hard delete de `teacher_assignments` continua bloqueado;
- isolamento por tenant e auditoria existentes são preservados.

## Casos de regressão obrigatórios

- EJA Anos Finais / Geografia / 80h anuais → 2h semanais: aceita `2`, rejeita
  `3`;
- componente coberto sem carga semanal: rejeita;
- Fundamental Anos Finais multisseriada 6º+7º / Geografia: 120h máximas → 3h
  semanais;
- componente fora da SSoT de carga: comportamento anterior preservado;
- erro de resolução da política: fail-closed;
- `ativo` e `active`: ambos reconhecidos como ativos;
- substituição: validação de carga somente depois da eventual herança do
  titular.

## Segurança operacional

Esta etapa altera somente código. Não executa migração, backfill ou escrita de
dados em produção. Qualquer deploy posterior segue o fluxo GitHub-only normal.
