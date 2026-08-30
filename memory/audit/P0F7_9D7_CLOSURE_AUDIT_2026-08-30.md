# P0-F7.9D7 — Auditoria formal de encerramento

Data: 2026-08-30

**Veredito técnico: `CLOSED`**

## 1. Escopo desta auditoria

Esta auditoria revisa a cadeia versionada P0-F7.9D7.1 → P0-F7.9D7.8, os contratos fail-closed, os GitHub Actions efetivamente executados e as evidências publicadas pela execução e pela verificação pós-estado.

Esta auditoria de encerramento não executou nova consulta ao banco de produção, não executou writer, migração, backfill, hard delete ou remediação histórica. A conclusão abaixo deriva exclusivamente de código, documentos e metadados/evidências do GitHub já existentes.

## 2. Problema que originou a trilha

A trilha D7 tratou a consolidação controlada de `teacher_assignments` cujo remapeamento curricular poderia produzir colisão semântica ativa. O preflight detectou o par duplicado antes da escrita; a investigação forense confirmou dois vínculos ativos concorrentes no mesmo escopo sem realizar mutação; a adjudicação posterior recusou escolher survivor ou carga automaticamente.

O plano revisado consolidou o lote em exatamente 23 updates documentais:

1. 21 `REMAP_COURSE`;
2. 1 `RETIRE_DUPLICATE_ASSIGNMENT` (`status -> inativo`);
3. 1 `CONSOLIDATE_SURVIVOR`.

Hard delete permaneceu proibido, e `RETIRE_DUPLICATE_ASSIGNMENT` foi fixado antes de `CONSOLIDATE_SURVIVOR` para evitar uma colisão ativa transitória.

## 3. Cadeia de controle

### D7.1 — collision preflight

O lote foi interrompido preventivamente ao detectar colisão semântica intra-batch. Não houve write.

### D7.2 — forensic

O par foi investigado em modo bounded read-only, com resultado selado e sem dados de estudante ou mutação.

### D7.3 / D7.3.1 — adjudicação e política curricular

A escolha do survivor foi separada da determinação de carga. A carga semanal deixou de ser uma escolha humana e passou a derivar da política curricular canônica. Para o caso adjudicado, EJA Anos Finais / Geografia / 80h anuais resulta em 2h semanais.

### D7.4 — last-mile preflight + CAS dry-run

O plano revisado foi revalidado contra o estado corrente, com simulação forward, pós-condições do par, rollback reverso e CAS por operação. A etapa somente permitia selagem do executor com 23/23 CAS claros, nenhuma colisão e rollback restaurável.

### D7.5 — manifesto imutável

Foi selada a especificação das 23 operações, mantendo separadas validação, autorização, materialização do executor e execução. A topologia observada exigiu `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`.

### D7.6 → D7.6.4 — execução autorizada e endurecida

O contrato de execução recebeu CAS explícito para aposentadoria, validador offline de recibo, captura robusta do output do `mongosh` e pipeline GitHub-only com código revisado pinado, manifesto selado e confirmação manual explícita.

A cadeia imutável registrada pela D7.7 é:

- D7.3.1 revised plan: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`;
- D7.4 preflight: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`;
- D7.5 manifest: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`;
- D7.6.3 executor: `aa61676f8e3841436b34d8f345d235304380eda866984319b815ceec638e4e5b`.

## 4. Evidência da execução real

GitHub Actions run: `33313000964`

Workflow: `P0-F7.9D7.6.4 GitHub-only Production Execution`

Head SHA: `a2565bb511b6b2a95598c402219fd75bb86d16ef`

Resultado: `success`.

O job `Execute exact authorized D7.6.3 remediation` concluiu com sucesso todas as etapas críticas, incluindo confirmação explícita, checkout pinado, restauração do manifesto selado, execução do writer, captura do output e validação offline do recibo contra a cadeia exata.

Pelo contrato fail-closed versionado, sucesso somente é possível com recibo `APPLIED`, exatamente 23 forward writes, zero rollback writes e `remediation_executed=true`.

Artefato de execução:

- id: `9732563705`;
- nome: `p0f7-9d764-production-evidence-33313000964`;
- digest: `sha256:61b5f41d94463e8e5d40e1d068c5b571d73de90b4dd5aa11e347fcbf85b02311`;
- expiração GitHub prevista: `2026-11-28T13:00:39Z`.

## 5. Verificação pós-execução e selo final

GitHub Actions run: `33313719678`

Workflow: `P0-F7.9D7.7 Post-execution Verification`

Head SHA: `f043cccd77cafc7dde97ccdb3b7e1a6c7cf7f841`

Resultado: `success`.

O job `Verify D7.6 remediation final state read-only` concluiu com sucesso a restauração do manifesto selado, construção do verificador bounded read-only, leitura/verificação do estado final, selagem offline e upload da evidência.

O contrato D7.7 verifica:

- os 23 registros afetados no escopo exato;
- os `set_fields` aplicados;
- 21 remaps + survivor ativos;
- duplicado aposentado como `inativo`;
- 22 tuples semânticos ativos finais únicos;
- survivor no curso-alvo com carga semanal canônica de 2h.

Classificação final definida pelo sealer após snapshot aprovado:

`REMEDIATION_APPLIED_AND_POST_STATE_VERIFIED`

Artefato de verificação:

- id: `9732779122`;
- nome: `p0f7-9d77-final-verification-33313719678`;
- digest: `sha256:a0a4c72a030ccfdf267d1f65dbafc0c61044eaf5da4a4aeda32100962fcf26e0`;
- expiração GitHub prevista: `2026-11-28T13:16:16Z`.

## 6. Prevenção de recorrência — D7.8

O PR #239 (`P0-F7.9D7.8: runtime teacher workload hardening`) conectou a SSoT `curricular_workload_policy` à fronteira de domínio de `teacher_assignments`.

A barreira cobre as superfícies ativas de escrita:

- criação titular;
- criação de substituição, após eventual herança da carga;
- update cujo estado resultante seja ativo.

Para componentes cobertos pela política — atualmente Geografia, História e Ciências — carga ausente, irresolúvel ou divergente falha fechada. `ativo` e `active` são tratados como estados ativos. Regra multisseriada, conversão institucional, isolamento por tenant, auditoria e bloqueio de hard delete permanecem preservados.

No head do PR #239 (`8fbcc28d5fa0d28e6c291a71747f1af3484ae3e2`), o guard específico `runtime-workload-guard` e os cinco status checks exigidos pela ruleset da `main` concluíram com `success`:

- `Nomenclature - Estudante guard`;
- `Frontend - yarn build`;
- `Backend - ruff lint`;
- `Backend - Diário por Vínculo guards`;
- `GATE - Regressão Transferência`.

## 7. GAPs e ressalvas residuais

### 7.1 Escopo da SSoT de carga — não bloqueante

A D7.8 aplica validação fail-closed de carga aos componentes atualmente cobertos pela SSoT (Geografia, História e Ciências). Componentes ainda fora da política mantêm `NOT_APPLICABLE` deliberadamente para evitar expansão silenciosa de escopo.

Isso não constitui GAP da remediação D7 encerrada. Qualquer ampliação da SSoT para outros componentes deve ser tratada como evolução separada, com sua própria validação curricular e regressões.

### 7.2 Retenção dos artefatos GitHub — não bloqueante

Os dois artefatos de Actions estão configurados para expirar em 90 dias. Seus IDs, nomes, SHAs e digests ficam registrados neste documento, mas os bytes dos artefatos deixarão de estar disponíveis pelo GitHub após a expiração se não houver política adicional de preservação.

Trata-se de risco de retenção de evidência, não de correção funcional ou integridade do estado pós-remediação; portanto não impede o fechamento da D7.

## 8. Critérios de encerramento

A P0-F7.9D7 satisfaz os critérios de fechamento porque:

1. a colisão original foi detectada antes de escrita insegura;
2. o caso ambíguo foi investigado e adjudicado sem decisão automática indevida;
3. a carga canônica foi promovida a SSoT;
4. o plano revisado passou por preflight, CAS dry-run, simulação forward e rollback;
5. o executor foi selado e executado somente após autorização explícita;
6. o recibo de execução foi validado em modo fail-closed;
7. o estado final foi revalidado em produção por workflow estritamente read-only;
8. a unicidade final e a carga canônica foram verificadas;
9. a prevenção de recorrência foi incorporada aos writers ativos;
10. não há PR nem issue D7 aberta identificada na auditoria de fechamento.

## 9. Veredito

**P0-F7.9D7 = `CLOSED`.**

Não deve ser criada uma P0-F7.9D7.9 apenas para prolongar a trilha. Qualquer novo trabalho deve nascer de um GAP novo e independente.

A trilha somente deve ser reaberta se surgir evidência objetiva de quebra de uma das invariantes encerradas — por exemplo, drift nos 23 documentos remediados, reaparecimento de colisão semântica ativa no escopo tratado, regressão da política canônica de carga ou bypass de algum writer protegido.
