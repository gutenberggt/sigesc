# AEE V2 — Fase 6.5B: Homologação em Produção do PDF Individual pela Fonte Efetiva

**Data:** 2026-08-23  
**Status:** ✅ HOMOLOGADA E ENCERRADA  
**Ambiente:** Produção — SIGESC  
**Marco de produção:** `fad44478d2d9987236a6a8e924eabb930063d7da`

## 1. Objetivo deste registro

Formalizar o encerramento técnico e operacional da Fase 6.5B do AEE V2, na qual o PDF individual do Plano AEE passou a consumir a **Fonte Efetiva** do Dossiê V2 quando existe `sidecar_active`, preservando o Plano legado como fallback fail-closed em qualquer condição de integridade, identidade ou projeção não representável.

Este documento é um marco de auditoria. Ele não inicia uma nova fase e não altera dados, contratos ou comportamento de runtime.

## 2. Contexto da evolução

A ativação da 6.5B foi precedida por uma etapa obrigatória de Shadow Mode em produção.

### 2.1 Fase 6.5A — Shadow Mode

A 6.5A foi executada em produção no endpoint individual de PDF sem substituir os bytes gerados pelo fluxo legado. O diagnóstico comparou, em memória, os campos efetivamente representados pelo PDF legado com a projeção da Fonte Efetiva V2.

Na primeira execução real com `sidecar_active`, o Shadow Mode registrou:

- `fields_total = 31`;
- `equal_count = 29`;
- `divergent_count = 2`;
- divergências: `status` e `adequacoes_curriculares`;
- `blockers = []`;
- `error = null`;
- resposta HTTP do PDF: `200 OK`.

A divergência de `status` foi classificada como legítima: o Plano legado permanecia `rascunho`, enquanto o snapshot V2 vigente estava `active`, que é projetado para `ativo` no contrato consumido pelo PDF.

A divergência de `adequacoes_curriculares` foi identificada como falso positivo de apresentação. Quando somente `acessibilidade_curricular` estava preenchida, a projeção adicionava o prefixo `Curricular:` que não existia no conteúdo legado. O PR #102 corrigiu esse comportamento preservando o texto puro nesse cenário.

Após a correção, nova execução real da 6.5A apresentou:

- `fields_total = 31`;
- `equal_count = 30`;
- `divergent_count = 1`;
- única divergência: `status`;
- `blockers = []`;
- `error = null`.

Com isso, a 6.5A foi considerada homologada e liberou o gate para a ativação controlada da 6.5B.

## 3. Ativação da Fase 6.5B

O PR #103 realizou exclusivamente o cutover de runtime:

- retirou o setup da 6.5A Shadow do bootstrap;
- instalou `install_aee_v2_plano_pdf_effective_setup`;
- manteve intactos o router AEE legado e o gerador ReportLab;
- manteve a projeção exclusivamente em memória;
- preservou o fallback legado fail-closed;
- preservou isolamento concorrente por `ContextVar`.

Após merge e redeploy, o runtime de produção confirmou:

```text
from aee_v2.plano_pdf_effective import install_aee_v2_plano_pdf_effective_setup
install_aee_v2_plano_pdf_effective_setup(_aee_mod)
```

A inspeção da cadeia montada pelo servidor confirmou ainda:

```text
endpoint = /app/aee_v2/plano_pdf_effective.py
wrapped = True
effective_installed = True
generator_effective_installed = True
```

## 4. Evidência de Fonte Efetiva aplicada

Uma consulta read-only, executada contra o mesmo Plano utilizado na homologação, confirmou a resolução e a projeção da Fonte Efetiva:

```text
context_status = effective
effective_source = sidecar_active
effective_version = {
  active_snapshot_id: <snapshot ativo>,
  document_version: 1,
  revision: 14
}
applied_status = effective
plan_source = sidecar_active
blockers = []
legacy_status = rascunho
projected_status = ativo
```

O documento PDF gerado em produção exibiu:

```text
Situação do Plano: Vigente
```

Esse resultado é coerente com o contrato do gerador, no qual:

```text
ativo -> Vigente
rascunho -> Em elaboração
```

Portanto, a evidência visual confirmou que o PDF recebeu o valor projetado `ativo` proveniente da Fonte Efetiva, e não o valor legado `rascunho`.

## 5. Observabilidade operacional

Durante a homologação foi identificado um GAP de observabilidade: o evento `AEE_V2_PLANO_PDF_EFFECTIVE` era emitido em nível `INFO`, enquanto o logging efetivo do ambiente de produção estava em `WARNING`. O cutover funcionava, porém o evento não aparecia nos logs operacionais.

O PR #104 corrigiu somente a política de nível de log:

- `effective_source = sidecar_active` → `WARNING`;
- qualquer evento com `blockers > 0` → `WARNING`;
- fluxo `legacy` sem blockers → permanece `INFO`.

Essa decisão evita elevar todo acesso legado a alerta, mas garante visibilidade para uso real do sidecar e para qualquer fallback bloqueado.

Após novo redeploy e nova geração real do PDF, a produção registrou:

```text
AEE_V2_PLANO_PDF_EFFECTIVE {
  "blockers": 0,
  "document_version": 1,
  "effective_source": "sidecar_active",
  "phase": "6.5B",
  "plan_source": "sidecar_active",
  "revision": 14,
  "sessions_total": 1,
  "status": "effective"
}
```

A mesma requisição concluiu com:

```text
GET /api/aee/planos/{plano_id}/pdf HTTP/1.1 200 OK
```

## 6. Critérios de aceite — resultado final

| Critério | Resultado |
|---|---|
| 6.5B instalada no runtime | ✅ |
| 6.5A Shadow retirada do runtime do PDF individual | ✅ |
| Fonte Efetiva resolvida como `sidecar_active` | ✅ |
| Projeção aplicada ao gerador | ✅ |
| `blockers = []` no caso homologado | ✅ |
| PDF entregue com HTTP 200 | ✅ |
| Status V2 `active` projetado como `ativo` | ✅ |
| PDF apresenta `Vigente` | ✅ |
| Fallback legado preservado | ✅ |
| Nenhum write MongoDB introduzido pela 6.5B | ✅ |
| Observabilidade `AEE_V2_PLANO_PDF_EFFECTIVE` visível em produção | ✅ |
| Gates críticos de CI aprovados antes dos merges | ✅ |

## 7. Invariantes preservadas

A homologação confirma a manutenção das seguintes invariantes arquiteturais:

- nenhuma escrita adicional em `planos_aee` pela geração do PDF;
- nenhuma alteração destrutiva em snapshots V2;
- nenhuma sincronização reversa automática do sidecar para o Plano legado;
- `backend/routers/aee.py` permanece sem alteração para o cutover 6.5B;
- `backend/pdf/plano_aee.py` permanece como gerador oficial;
- a substituição do Plano ocorre somente em memória, antes da chamada ao gerador;
- erro de resolução, integridade, identidade ou projeção não representável mantém o PDF legado;
- `ContextVar` permanece responsável pelo isolamento do contexto entre requisições concorrentes.

## 8. Rastreabilidade de Pull Requests

| PR | Finalidade | Merge commit |
|---|---|---|
| #101 | Restaurar e instalar a 6.5A Shadow Mode no PDF individual | `644441633216766285141f2d49ef724a1cafd54d` |
| #102 | Eliminar falso positivo de `adequacoes_curriculares` na projeção | `086827e88b4709f377a9a459702d9a31e0fcceda` |
| #103 | Ativar a Fonte Efetiva 6.5B no runtime | `19f8e1cbd9c970622eb31d9d910d3e326247e019` |
| #104 | Tornar a observabilidade 6.5B visível no logging de produção | `fad44478d2d9987236a6a8e924eabb930063d7da` |

## 9. Limitações e ressalvas da homologação

1. Na janela de homologação havia somente um snapshot V2 ativo disponível em produção para exercício real do caminho `sidecar_active`. A cobertura automatizada continua responsável pelos demais cenários de contrato, incluindo legacy, mismatch de identidade, cronograma não representável e fallback fail-closed.
2. O nível `WARNING` do evento de `sidecar_active` é uma decisão de observabilidade operacional para o ambiente atual; não significa, por si só, erro funcional.
3. O Plano legado pode permanecer com estado histórico diferente do snapshot V2 ativo. Essa divergência é esperada na arquitetura sidecar e não deve ser interpretada como inconsistência quando a Fonte Efetiva está corretamente resolvida.

## 10. Decisão arquitetural

**DECISÃO: Fase 6.5B HOMOLOGADA E ENCERRADA EM PRODUÇÃO EM 23/08/2026.**

A partir deste marco, o PDF individual do Plano AEE está autorizado a usar a Fonte Efetiva V2 quando houver `sidecar_active`, observadas as regras de projeção e fallback fail-closed já implementadas.

A 6.5A permanece como precedente de homologação e diagnóstico, mas não é mais a camada ativa do runtime do PDF individual.

## 11. Gate para a próxima fase

Não existe, neste momento, definição canônica de uma “Fase 6.6” no repositório. Portanto, **nenhuma nova fase é iniciada por este documento**.

Antes da próxima implementação do AEE V2, deve ser criado um escopo explícito que defina:

- nome e objetivo da fase;
- superfície funcional afetada;
- Fonte Efetiva envolvida;
- estratégia Shadow/Cutover, se aplicável;
- invariantes que não podem ser quebradas;
- critérios de aceite e rollback;
- testes e observabilidade obrigatórios;
- impactos ou ausência de impactos sobre dados legados e snapshots V2.

Somente após esse gate documental a próxima fase deve receber código de produção.
