# F2.1A — Retificação de Matrícula/Turma: frequência canônica compensável

> Issue: #567  
> Baseline: `42d42c65f89081546402ac8346254229f3394ee4`  
> Pré-requisito: F2.0 (#565) publicado com `/prepare-execution`, sem `/execute`.  
> Status inicial: **implementação interna, não exposta para retificação real**.

## Objetivo

Fechar o domínio de frequência necessário à futura saga de `retificacao_enturmacao` sem criar aulas fictícias no destino e sem expor execução acadêmica.

A F2.1A deve:

1. extrair a validação/desvalidação institucional de `attendance` para serviço canônico reutilizável;
2. criar o ledger individual `attendance_rectifications`;
3. implementar primitivo interno de retirada do `records[]` do estudante na origem via CAS/versionamento;
4. preservar todos os demais estudantes e a identidade da aula;
5. quando o documento estiver validado, desvalidá-lo com trilha append-only e deixá-lo pendente de nova validação;
6. manter retry idempotente e falha concorrente explícita;
7. permanecer sem `/execute` e `/rollback` da retificação.

## Invariantes

- `attendance` continua a SSoT do diário da turma.
- `attendance_rectifications` preserva a evidência individual para a frequência efetiva futura.
- Nunca criar `attendance` no destino para representar sessão que não existiu.
- Nunca mover documento inteiro de frequência.
- `validated_by`/`validated_at` não sobrevivem a mudança de payload.
- `validation_history[]` é append-only.
- Toda alteração de `attendance` usa CAS sobre `version`.
- `date`, `course_id`, `aula_numero`, `assignment_id`, autoria docente e records dos demais estudantes permanecem intactos.
- Tenant divergente é invisível/fail-closed.
- Nenhum dado real de estudante será processado nesta fase.

## Estado de produção

Mesmo após merge/deploy, a funcionalidade ficará inerte para retificação real: não haverá rota pública que invoque o primitivo e o gate global de mutação acadêmica permanecerá fechado.

## Saída esperada

Código + testes + CI específico verdes, regressão das rotas atuais de validação/desvalidação, revisão do diff e publicação segura sem ativação da saga acadêmica completa.
