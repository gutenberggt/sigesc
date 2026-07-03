# BI-1B — Plano: Consolidação dos Dados (proposta — requer aprovação)

> ⚠️ Diferente da BI-1A, a **BI-1B ALTERA código e DADOS** (migrações). Só executar
> após aprovação formal. Objetivo: entregar as **fontes únicas** de que o Motor de
> Indicadores depende — vínculo aluno↔turma (D2) e status legados (D6).

## 1. Escopo
- **D2 — Unificação do vínculo aluno↔turma** (fonte canônica = `enrollments`).
- **D6 — Saneamento dos status legados** (matrículas/alunos fora do `Literal`).
- (Preparatório) especificar `dim_*`/`fato_*` para os marts (sem materializar ainda).

## 2. D2 — Estratégia de unificação do vínculo
**Problema:** três fontes divergentes (`enrollments` × `students.class_id` × `class_students`).
**Alvo:** `enrollments` como SSoT do vínculo; demais **derivadas/depreciadas**.

Fases (com feature-flag `BI_VINCULO_CANONICO`):
1. **Auditoria de divergência (READ-ONLY):** script que compara as 3 fontes por aluno/turma/ano
   e produz relatório de inconsistências (nº e exemplos). Nenhuma escrita.
2. **Reconciliação assistida:** regra determinística de "verdade" (prioridade: matrícula ativa
   em `enrollments` > `student.class_id` > `class_students`), com revisão de exceções.
3. **Dual-write controlado:** escritas passam a atualizar `enrollments` como primária e manter
   as demais sincronizadas (transitório), via `with_critical_mutation` (idempotência+lock+audit).
4. **Migração de leituras:** endpoints/consumidores passam a ler de `enrollments` (atrás da flag).
5. **Depreciação:** `students.class_id`/`class_students` viram derivados (view/campo calculado).

## 3. D6 — Saneamento de status legados
1. **Levantamento (READ-ONLY):** contar valores fora do `Literal` (ex.: `enrollments.status='inactive'`).
2. **Mapa de coerção:** `inactive→cancelled`, `inativo→cancelled`, `deceased→cancelled`,
   `reclassified→progressed` (consistente com o `field_validator` já existente).
3. **Migração idempotente** (`with_critical_mutation`): normaliza documentos, registra antes/depois em audit.
4. **Rede de segurança:** manter o `field_validator` de tolerância mesmo após a migração.

## 4. Análise de riscos
| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Regressão no núcleo (notas/frequência/promoção) | Média | **Alto** | feature-flag + dual-write + suíte de regressão ampliada |
| Reconciliação escolher "verdade" errada | Média | Alto | dry-run + relatório + amostra revisada antes do cutover |
| Perda/alteração de histórico | Baixa | **Alto** | backup pré-migração + operações idempotentes + rollback |
| Divergência temporária durante dual-write | Média | Médio | reconciliação periódica + monitor de drift |

## 5. Plano de rollback
- **Flag off** (`BI_VINCULO_CANONICO=false`) → leitura volta ao comportamento atual (reversão instantânea de leitura).
- **Migração D6/D2:** cada mutação idempotente registra snapshot antes/depois → **script de reversão** restaura valores originais por lote.
- **Backup completo** das coleções afetadas antes do cutover (retido pela janela definida).

## 6. Testes de regressão
- Ampliar suíte além dos 27 testes de transferência: casos de **livro de promoção**,
  **grade de notas multisseriada**, **frequência/consolidação**, **boletim** — todos
  validando paridade de resultados **antes vs. depois** (flag on/off).
- Teste de reconciliação (divergência conhecida → verdade esperada).
- Teste idempotência D6 (rodar 2×, resultado estável).

## 7. Critérios de validação (Definition of Done)
1. Relatório de divergência = **0** inconsistências residuais após reconciliação.
2. Paridade 100% dos fluxos-chave com a flag on vs. off (sem diferença visível ao usuário).
3. `status` legados = 0 fora do `Literal` (D6) e migração idempotente comprovada.
4. Rollback testado (flag + script de reversão) em ambiente controlado.
5. Comportamento funcional inalterado para o usuário final ao concluir o cutover.

## 8. Governança (respostas obrigatórias)
- **Problema:** dados-fonte inconsistentes bloqueiam o Motor de Indicadores confiável.
- **Benefício:** fatos de matrícula/frequência/nota corretos → base sólida para BI.
- **Impacto:** núcleo de dados (alto) — por isso faseado com flag/rollback.
- **Testado:** regressão ampliada + paridade + idempotência.
- **Revertível:** flag + snapshots/reversão + backup.
- **Prepara próxima fase:** habilita **BI-2 (Motor de Indicadores)** com fontes únicas.

> Após aprovação da BI-1A e deste plano, a BI-1B pode ser iniciada. A BI-2 (Motor)
> só começa com BI-1B concluída e validada.
