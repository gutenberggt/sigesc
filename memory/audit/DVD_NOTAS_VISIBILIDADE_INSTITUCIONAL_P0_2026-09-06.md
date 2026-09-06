# DVD — Visibilidade Institucional de Notas — P0 — 2026-09-06

## Incidente observado

Na E M E I E F Jose Pereira Barbosa, turma **5º ANO A**, as notas já salvas de **Língua Portuguesa** e **Matemática** não eram exibidas ao perfil Professor no **Lançamento de Notas** nem no **Livro de Promoção**.

## Causa arquitetural

A Fase 5 do DVD tratava `grade_ownership` simultaneamente como:

1. prova de autoria/autorização de escrita; e
2. filtro de visibilidade de leitura.

Isso fazia valores pertencentes a outro assignment/professor serem mascarados como `null`, mesmo quando o professor atual possuía vínculo válido e estava autorizado a acessar a mesma turma/componente.

## Regra canônica corrigida

`grades` é registro acadêmico institucional. Portanto:

> Todo perfil autorizado a ler uma turma/componente deve visualizar os valores de notas/conceitos já salvos naquele escopo.

`grade_ownership` continua sendo a SSoT de autoria e governança de **escrita**, não de ocultação do valor acadêmico.

Para Professor:

- valor de outro vínculo: **visível**;
- campo de outro vínculo: **somente leitura** (`dvd_locked_fields`);
- snapshot de autoria de outro vínculo: **não exposto**;
- tentativa de alterar campo alheio: continua bloqueada pelo motor `grade_assignment_scope`;
- ausência de vínculo autorizado: continua fail-closed.

## Superfícies cobertas

A política é aplicada às projeções de leitura usadas por:

- Lançamento de Notas por turma/componente;
- Livro de Promoção;
- visão Por Estudante;
- leituras agregadas híbridas DVD/legado;
- pull offline de notas, filtrado pelo escopo docente autorizado em vez de `teacher_id` no ownership.

## Segurança preservada

A correção é read-only em relação aos dados persistidos. Não executa:

- `insert/update/delete` em `grades`;
- backfill de `grade_ownership`;
- apropriação retroativa de notas;
- alteração de cálculo de média/situação;
- ampliação de turma/componente autorizado.

A autorização continua ancorada em `teacher_class_assignments`/`teacher_assignments` e no resolvedor híbrido do DVD.
