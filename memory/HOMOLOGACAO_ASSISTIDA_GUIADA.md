# Homologação Assistida Guiada — Transferência Institucional (ciclo isolado)

> **Garantia de isolamento:** todo o ciclo roda sobre um *sandbox* com **mantenedora dedicada**
> (`HMLSBX-MANT-001`) e duas escolas dedicadas (`HMLSBX-SCHOOL-ORIGIN` / `HMLSBX-SCHOOL-DEST`).
> Nenhum dado real é tocado. Todos os documentos têm a marca `homolog_sandbox: true` e o
> `teardown` remove tudo de forma idempotente.
>
> **Harness:** `/app/backend/scripts/homolog_transfer_sandbox.py`
> **Subcomandos:** `seed` · `baseline` · `validate --expect dest|origin` · `teardown`

Ciclo completo: **dry-run → execute → validate(dest) → receipt → rollback → revalidate(origin)**,
com **GATES de decisão humana** entre as fases. Em cada GATE: marque ✅ para prosseguir ou ❌ para abortar (→ teardown).

---

## Pré-requisitos
- [ ] Logado como **super_admin** (gutenberg@sigesc.com) com a senha em mãos (re-autenticação).
- [ ] Acesso ao terminal do backend (para o harness) e ao app (UI).

---

## FASE 0 — Provisionar o sandbox isolado
```bash
cd /app/backend
python scripts/homolog_transfer_sandbox.py seed
```
Cria mantenedora + 2 escolas + calendário + 2 turmas + 6 alunos + amostras de
frequência, notas, conteúdo, AEE e Bolsa Família. Imprime os IDs e a **baseline** (contagens).

**🚦 GATE 0 — Baseline capturada**
- [ ] A baseline foi impressa e anotada (classes=2, students=6, enrollments=6, attendance=2, grades=6, content_entries=2, planos_aee=2, bolsa_familia_tracking=2).
- [ ] As duas escolas `ESCOLA ORIGEM (HOMOLOG)` e `ESCOLA DESTINO (HOMOLOG)` aparecem no Wizard.
- Decisão: ✅ prosseguir · ❌ abortar (`teardown`).

---

## FASE 1 — Dry Run (na UI)
1. Abrir **Administração → Transferências Institucionais → Nova Transferência** (`/admin/transferencias/nova`).
2. **Etapa 1:** origem = `ESCOLA ORIGEM (HOMOLOG)`; destino = `ESCOLA DESTINO (HOMOLOG)`.
3. **Etapa 2:** modo **Escola inteira**.
4. **Etapa 3:** clicar **Simular (Dry Run)**.

**🚦 GATE 1 — Simulação aprovada**
- [ ] `can_execute = true` (sem bloqueios 🔴).
- [ ] Contagens do Dry Run **== baseline** (turmas/alunos/matrículas/frequência/notas/conteúdo/AEE/Bolsa Família).
- [ ] Avisos 🟡 (se houver) compreendidos.
- Decisão: ✅ prosseguir para execução · ❌ abortar (não há mutação; investigar divergência).

---

## FASE 2 — Execução real (na UI)
5. **Etapa 4 (Confirmação forte):** conferir o resumo "X turmas / Y alunos / Z matrículas, origem → destino".
6. Preencher **justificativa** (≥10), **senha** e a frase exata **`CONFIRMO A TRANSFERÊNCIA INSTITUCIONAL`**.
7. Clicar **Executar**. Anotar o **protocolo** (`TRANSF-AAAA-NNNNNN`) e o horário.

**🚦 GATE 2 — Execução concluída**
- [ ] Protocolo gerado e exibido na Etapa 5.
- [ ] Escola origem marcada como **encerrada**.
- Decisão: ✅ prosseguir para validação · ❌ ir direto ao rollback (Fase 4).

---

## FASE 3 — Validação pós-transferência
```bash
python scripts/homolog_transfer_sandbox.py validate --expect dest
```
Verifica automaticamente: turmas/alunos/matrículas/conteúdo/AEE/Bolsa Família no **destino**,
`school_history` coerente (1 segmento aberto no destino, sem sobreposição/lacuna),
frequência/notas preservadas e **origem encerrada**.

Validação manual de relatórios (na UI, comparar com os PDFs "ANTES" se houver):
- [ ] Histórico Escolar de 1 aluno: períodos anteriores mostram a **escola da época** (origem), não a atual.
- [ ] Frequência/Rendimento conferem.

**🚦 GATE 3 — Pós-transferência aprovado**
- [ ] `validate --expect dest` → **TUDO OK**.
- [ ] Relatórios críticos coerentes.
- Decisão: ✅ prosseguir · ❌ rollback imediato.

---

## FASE 4 — Recibo PDF + QR (na UI)
8. No **Painel** (`/admin/transferencias`), linha do protocolo → **Gerar recibo**.

**🚦 GATE 4 — Recibo válido**
- [ ] PDF abre com campos corretos (protocolo, origem, destino, turmas, alunos, operador, justificativa, data/hora).
- [ ] **QR Code** abre `/v/{token}` e confirma o documento como **autêntico**.
- [ ] A transferência **continua reversível** (gerar recibo não fechou a janela).
- Decisão: ✅ prosseguir para rollback.

---

## FASE 5 — Rollback (na UI)
9. No **Painel**, linha do protocolo → **Reverter**.
10. Justificativa (≥10), senha e frase exata **`CONFIRMO A REVERSÃO DA TRANSFERÊNCIA`**. Confirmar.
11. Anotar **protocolo de rollback** (`ROLLBACK-AAAA-NNNNNN`).
12. (Idempotência) Tentar reverter o **mesmo** protocolo novamente → deve retornar o **mesmo** protocolo de rollback, sem efeito colateral.

**🚦 GATE 5 — Rollback executado**
- [ ] Reversão concluída; `origin_reopened = true`.
- [ ] Idempotência confirmada.
- Decisão: ✅ revalidar.

---

## FASE 6 — Revalidação pós-rollback
```bash
python scripts/homolog_transfer_sandbox.py validate --expect origin
```
Verifica que **tudo voltou à origem**: turmas/alunos/matrículas/conteúdo/AEE/Bolsa Família,
`school_history` **restaurado exatamente** ao baseline (sem segmento do destino), e **origem reaberta** (`active`).

Validação manual:
- [ ] Relatórios críticos voltam a coincidir com os de "ANTES".
- [ ] Auditoria imutável: registro da reversão (quem/quando/justificativa/IP/protocolos) + evento original preservado.

**🚦 GATE 6 — Pós-rollback aprovado**
- [ ] `validate --expect origin` → **TUDO OK**.
- Decisão: ✅ ciclo concluído com sucesso.

---

## FASE 7 — Encerramento e limpeza
```bash
python scripts/homolog_transfer_sandbox.py teardown
```
Remove **todo** o sandbox (idempotente). Confirme que `remaining` zera.

---

## ✅ Critérios objetivos de aprovação (liberar aos Super Admins)
Liberar **somente se TODOS** forem verdadeiros:
1. [ ] GATE 1: Dry Run `can_execute=true` e contagens == baseline.
2. [ ] GATE 2: execução com protocolo + origem encerrada.
3. [ ] GATE 3: `validate --expect dest` TUDO OK + relatórios coerentes (Histórico respeita escola temporal).
4. [ ] GATE 4: recibo PDF correto + QR autêntico; janela de rollback preservada.
5. [ ] GATE 5: rollback OK + idempotência.
6. [ ] GATE 6: `validate --expect origin` TUDO OK (school_history restaurado exatamente; origem reaberta).
7. [ ] Nenhum erro 500/exception nos logs do backend durante o ciclo.
8. [ ] **Aprovação formal por escrito** do responsável.

> Qualquer GATE reprovado = **não liberar**. Tratar como bloqueio.

---

## 🛟 Plano de contingência
- **Falha no Dry Run / GATE 1:** não executar; sem mutação, risco zero. Investigar e `teardown`.
- **Anomalia após execução (GATE 3):** **rollback imediato** (Fase 5) → revalidar (Fase 6).
- **Rollback falha parcialmente:** por design o estado **não** é marcado como revertido e o lock é liberado → **reexecutar o rollback** (idempotente). Persistindo após 2 tentativas: **não liberar**, acionar dev com protocolo+logs, restaurar via backup do ambiente de teste.
- **Janela expirada / documento oficial emitido:** rollback bloqueia (esperado). Não forçar.
- Ao final de qualquer contingência: rodar `teardown` para limpar o sandbox.

---

## 🔁 Smoke test de REGRESSÃO (não-interativo)
```bash
cd /app/backend
python scripts/homolog_transfer_sandbox.py cycle --password '<senha_super_admin>'
# ou: HOMOLOG_ADMIN_PASSWORD='<senha>' python scripts/homolog_transfer_sandbox.py cycle
```
Roda sozinho o ciclo completo (seed → dry-run → execute → validate(dest) → receipt → rollback →
idempotência → validate(origin) → teardown) e imprime **NENHUMA REGRESSÃO DETECTADA** ou
**REGRESSÃO DETECTADA** com a lista de falhas. Exit code 0 = sem regressão; 1 = regressão.

> ⚠️ **REGRA:** o `cycle` **NÃO certifica o sistema** — ele **apenas detecta regressões** nas
> verificações automatizadas. A **certificação** para liberar aos Super Admins exige a
> **homologação assistida guiada** (este runbook, com os 7 gates de decisão humana) e a
> **aprovação formal por escrito** do responsável. Use o `cycle` como guarda de regressão
> antes de cada release da transferência, nunca como substituto da homologação.

---

## 📌 Resultado do ensaio interno (automatizado, antes da entrega deste runbook)
- Ciclo completo executado no sandbox isolado: dry-run → execute → validate(dest) **TUDO OK** → recibo PDF (HTTP 200, `%PDF`) → rollback (idempotente, origem reaberta) → validate(origin) **TUDO OK** → teardown limpo.
- **Bug encontrado e corrigido durante o ensaio:** o snapshot de rollback guardava uma *referência* ao `school_history` (mutado in-place no re-homing), fazendo a reversão **não restaurar** o histórico de turmas que já possuíam `school_history`. Corrigido com `deepcopy` na captura do snapshot. Teste de regressão adicionado (`test_rollback_restores_preexisting_school_history_exactly`). Suíte: **11/11 PASS**.
