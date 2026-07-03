# BI-1B_FINAL_MIGRATION_PLAN.md — Plano Definitivo de Migração (Consolidação de Dados)

> Substitui o preliminar `BI-1B_PLAN.md`. Baseado em `DATA_DIVERGENCE_AUDIT.md`.
> **Ainda READ-ONLY até aprovação.** A execução da BI-1B só é autorizada após:
> (1) reexecução do audit em **produção**, (2) aprovação formal deste plano.

## 0. Pré-condição inegociável
Rodar `audit/scripts/data_divergence_audit.py` na **base de produção** (read-only) e
anexar os números reais. Os limiares de decisão abaixo usam os dados de PRODUÇÃO,
não do preview.

## 1. Estratégia
### Escopo (ordem de execução)
1. **D6 (status legados)** — mais simples e de baixo risco. **Primeiro.**
2. **Quarentena de órfãos** — isolar matrículas com `student_id`/`class_id` inexistentes
   (mover para `enrollments_quarantine`, reversível; não apagar).
3. **D2 (vínculo canônico)** — eleger `enrollments` como fonte; derivar/depreciar
   `students.class_id` e `class_students`. **Por último** (maior risco).

### Pré-requisitos
- Backup completo das coleções afetadas (`students`, `enrollments`, `class_students`).
- Índices confirmados em `enrollments (student_id, academic_year)`, `(class_id)`, `(school_id)`.
- Feature-flag `BI_VINCULO_CANONICO` (default OFF) para D2.
- Suíte de regressão ampliada aprovada (ver §4).

### Janela de manutenção
- **D6 e quarentena:** podem ser **online** (idempotentes, sem mudança de leitura).
- **D2 cutover de leitura:** recomendável **janela curta** (baixo tráfego) ao virar a flag,
  mesmo com dual-write, para evitar leitura mista durante a transição.

## 2. Segurança
- **Snapshots por lote:** cada mutação registra `{id, campo, antes, depois, migration_id}`
  em coleção de auditoria dedicada (ex.: `bi_migration_audit`) — via `with_critical_mutation`.
- **Backups:** dump das coleções afetadas antes de cada etapa; retenção pela janela definida.
- **Validações pré-execução:** contagens esperadas conferidas com o relatório de produção;
  abort se divergir do esperado (guarda contra rodar na base errada).
- **Idempotência:** reexecução não altera resultado (chaves de idempotência por `migration_id`).

## 3. Rollback
| Etapa | Critério de interrupção | Como reverter | Tempo estimado |
|---|---|---|---|
| D6 status | contagem afetada ≠ esperado; erro de validação | script de reversão por `bi_migration_audit` (depois→antes) | minutos |
| Quarentena | remoção acidental de registro válido | restaurar de `enrollments_quarantine` (reversível) | minutos |
| D2 leitura | divergência de paridade / erro em fluxo-chave | **flag OFF** (leitura volta ao comportamento atual) — instantâneo | segundos |
| D2 dados | corrupção detectada | restore do backup + reversão por audit | conforme volume (estimar em prod) |

## 4. Validação (testes obrigatórios — antes e depois)
### Automatizados / regressão
- Ampliar além dos 27 testes de transferência: **livro de promoção**, **grid de notas
  multisseriada**, **frequência/consolidação diária**, **boletim/ficha**.
- Teste de **paridade** (flag ON vs OFF) nos fluxos-chave: resultado idêntico.
- Teste de **idempotência** D6 (rodar 2×, estado estável).
- Teste de **reconciliação** D2 (divergência conhecida → verdade esperada).
### Funcionais / manuais
- Login por perfil (admin, secretário, professor, SEMED) e navegação nas telas-núcleo.
- Emissão de boletim e livro de promoção para turma multisseriada.
### Validação de indicadores / dashboards / IA
- Comparar **antes vs. depois**: contagem de matrículas ativas por escola/turma,
  taxa de frequência e rendimento nos dashboards Analytics/PME (não devem mudar
  além da correção esperada de órfãos).
- IA: ainda não consome BI (pré-Motor) — validação plena na BI-5.

## 5. Sequência operacional (runbook resumido)
1. Rodar audit em produção → anexar números.
2. Backup + validar pré-condições.
3. **D6:** migração idempotente de status → validar contagens → testes.
4. **Quarentena de órfãos:** mover → validar relatórios/contagens.
5. **D2:** ativar dual-write (flag ainda OFF na leitura) → reconciliar divergências →
   migrar leituras atrás da flag em ambiente controlado → paridade → **cutover** (flag ON) →
   monitorar drift → depreciar fontes secundárias.
6. Relatório pós-migração + atualização da baseline.

---

## Entrega 8 — Critérios Objetivos para Liberação (respostas)
> Respondidas com base no **preview**; **revalidar com dados de produção** antes do go/no-go.

| Pergunta | Resposta (preliminar) |
|---|---|
| **A migração é segura?** | **D6/quarentena: SIM** (baixo risco, reversível). **D2: SIM sob condições** (flag + dual-write + backup + regressão). |
| **Nível de confiança** | D6: **Alto**. D2: **Médio-Alto**, condicionado à reexecução em produção. |
| **Impacto esperado** | Correção de órfãos e status; **nenhuma mudança visível** ao usuário nos fluxos corretos. |
| **Risco de perda de dados** | **Baixo** — nada é apagado (quarentena + snapshots + backup). |
| **Risco de indisponibilidade** | **Baixo** — D6/quarentena online; D2 com janela curta no cutover. |
| **Tempo estimado de execução** | Preview < 1s; **produção a medir** (esperado poucos minutos com índices). |
| **Online ou janela?** | D6/quarentena **online**; **D2 cutover em janela curta** recomendada. |

## Critério de aprovação da BI-1B (checklist de governança)
- [ ] Escopo totalmente conhecido (audit de **produção** anexado).
- [ ] Riscos quantificados (magnitude real de órfãos/divergências/status).
- [ ] Estratégia de rollback validada (flag + snapshots + backup testados).
- [ ] Critérios de validação definidos (testes automatizados/funcionais/paridade).
- [ ] Impacto operacional aceitável (janela e indisponibilidade acordadas).

> **Diretriz permanente de governança (inscrita no baseline):** nenhuma migração
> estrutural no SIGESC IA sem auditoria prévia + plano de migração aprovado +
> plano de rollback + plano de testes + critérios objetivos de sucesso.
