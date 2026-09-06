# R2.0g.3 — Hotfix da resolução de professor legado na Cópia Manual de Conteúdo

Data: 2026-09-06
Tracking: #471

## Sintoma
Na interface `Cópia Manual de Conteúdo`, datas válidas do destino apareciam indisponíveis com o motivo `Professor legado não resolvido`, deixando apenas `NÃO COPIAR` selecionável.

## Causa
O contrato histórico do SIGESC é:

- `teacher_assignments.staff_id` referencia `staff.id`;
- `staff.user_id` referencia `users.id`;
- `teacher_class_assignments.teacher_id` referencia `users.id`.

O adapter R2.0g.1 tentava resolver o identificador legado diretamente em `users.id/users.staff_id`, sem atravessar a ponte canônica `staff.id -> staff.user_id -> users.id`.

## Correção
A R2.0g.3 adiciona uma ponte isolada que:

1. aceita ator já canônico em `users.id`;
2. resolve identidade legada por `staff.id -> staff.user_id -> users.id`;
3. usa e-mail somente como fallback inequívoco;
4. prioriza `teacher_assignments.staff_id` sobre campos transitórios;
5. mantém vínculo legado ambíguo como bloqueante;
6. quando o legado está apenas não resolvido, permite usar snapshot inequívoco da frequência da própria data;
7. nunca usa o `super_admin` operador como professor.

## Boundary

- nenhuma escrita acadêmica;
- nenhuma alteração de frequência;
- nenhuma alteração de vínculo docente;
- nenhum deploy nesta preparação;
- nenhum merge sem autorização humana explícita;
- serviço permanece exclusivo do `super_admin`.
