# Assessment Policy Multi-Mantenedora v1 — Sprint 006 Shadow Runner

**Status:** EM EXECUÇÃO  
**Base:** `edf21116c7c333d8c89ea168a1def12bfaaab331` (merge PR #59)  
**Natureza:** leitura operacional + relatório; **sem cutover e sem escrita em dados acadêmicos**.

## 1. Objetivo

Conectar a infraestrutura pura de Shadow/Dry-run aos dados reais do SIGESC de forma estritamente read-only, permitindo varrer `grades` por mantenedora/ano, construir o contexto acadêmico, resolver a `AssessmentPolicy` publicada e comparar o `final_average` legado persistido com o Calculator v1.

A Sprint 006 **não** altera o runtime oficial de Notas e **não** publica políticas municipais automaticamente.

## 2. Fluxo

```text
mantenedora + ano + reference_date
        |
        v
classes do tenant/ano
        |
        v
grades dessas classes/ano
        |
        v
context_builder read-only
        |
        v
Policy Resolver
        |
        v
mapping explícito por policy_id
        |
        v
Shadow Engine / Calculator v1
        |
        v
relatório por policy + issues por registro
```

## 3. Regras de segurança

1. O tenant scope começa em `classes.mantenedora_id`; o runner nunca faz varredura global de `grades`.
2. `grades` é lido somente para `class_id` previamente comprovada no tenant e no ano.
3. Se o documento de Grade possuir `mantenedora_id` explícito divergente, o registro vira issue fail-closed.
4. O contexto usa `build_assessment_policy_context()`, preservando as regras de série efetiva e multisseriação da Sprint 002.
5. A policy é resolvida pelo Resolver publicado; nenhuma policy é escolhida por heurística do runner.
6. O mapping é fornecido explicitamente por `policy_id`; ausência de mapping vira issue `ASSESSMENT_SHADOW_RUNNER_MAPPING_REQUIRED`.
7. O runner não infere `b1`, `b2`, `rec_s1`, `rec_s2` ou `recovery`.
8. O runner não chama `calculate_and_update_grade()` nem `grade_calculator.py`.
9. Nenhum `insert`, `update`, `replace`, `delete` ou `bulk_write` é permitido no módulo.
10. `reference_date` deve pertencer ao `academic_year` solicitado.

## 4. Saída

`ShadowRunnerReport` contém:

- mantenedora/ano/data de referência;
- total de documentos lidos (`scanned`);
- total efetivamente comparado (`compared`);
- registros não resolvidos (`unresolved`);
- comparáveis, matches e diferenças;
- `match_rate` agregado;
- grupos por policy/mapping;
- issues com código, mensagem e contexto mínimo do registro.

Cada grupo preserva `policy_id`, `policy_key`, versão, `rule_hash`, `mapping_hash` e o `ShadowBatchReport` da Sprint 005.

## 5. Escopo deliberadamente excluído

- endpoint HTTP;
- UI de mantenedora;
- cron/scheduler;
- persistência de relatórios;
- alteração de `grades.final_average`;
- alteração de `grades.status`;
- backfill;
- criação automática de `assessment_policies`;
- criação automática de mapping municipal;
- ativação de feature flag de cutover;
- substituição do motor legado.

## 6. Floresta do Araguaia

A infraestrutura desta Sprint permite executar um dry-run real quando houver uma policy publicada e um mapping explicitamente aprovados.

Não serão presumidos nesta sprint:

- associação operacional de campos legados de recuperação;
- regra `only_if_improves` quando não formalizada;
- qualquer regra específica de outra mantenedora.

A frequência não participa da comparação de `final_average`; ela permanece responsabilidade do Academic Outcome Engine e da SSoT de Frequência.

## 7. Critérios de aceite

- [x] tenant scope por classes antes de ler grades;
- [x] filtro de ano explícito em classes e grades;
- [x] context builder canônico reutilizado;
- [x] Resolver canônico reutilizado;
- [x] mapping obrigatório por policy_id;
- [x] agrupamento por policy/mapping;
- [x] relatório agregado sem persistência;
- [x] issue por registro não resolvido;
- [x] testes com Grade compatível, mapping ausente e tenant divergente;
- [x] guard estático contra primitivas de escrita e motor legado;
- [ ] Shadow Runner Gate verde;
- [ ] regressões anteriores verdes;
- [ ] CI geral / Transferência / DVD verdes;
- [ ] revisão final do diff.

## 8. Gate para próxima etapa

A próxima etapa operacional somente poderá preparar um dry-run assistido sobre dados de produção quando:

1. esta Sprint estiver integrada;
2. houver policy publicada e íntegra para o escopo escolhido;
3. o mapping legado dessa policy estiver explicitamente aprovado;
4. o dry-run começar por escopo pequeno (escola/turma/série) e somente leitura;
5. nenhum dado acadêmico for alterado como efeito do teste.
