# TEACHER VISIBILITY — F4.1 Probe Hardening

Data: 2026-09-03  
Tracking: #357 — Luiz Gomes dos Santos  
Origem: F4 gate #372 / run `33809801364`  
Natureza: auditoria read-only; nenhuma correção funcional ou mutação de produção.

## Motivo

A F4 original foi corretamente autorizada para:

`assets públicos → React → prefill → DOM`

usando `main=35eb078fc5434b0b5eaf7e0c6d461213567f4281` e
`production=4982421378139ce823005ae374e4b970183c6333`.

O gate validou autorização owner-only, SHAs, tracking #357, checkout exato e
instalação do Chromium. A etapa de browser começou às 21:47:47Z e foi encerrada
pelo `timeout-minutes: 25` às 22:12:27Z. Não houve
`TEACHER_VISIBILITY_F4_JSON=`, artefato ou classificação estruturada.

Leitura correta:

- **não** houve `PUBLIC_BROWSER_RENDER_GAP`;
- **não** houve `PUBLIC_BROWSER_RENDER_CURRENT`;
- o resultado foi **inconclusivo por timeout do probe**;
- repetir o mesmo gate sem hardening não acrescentaria evidência.

A revisão independente via Claude confirmou o mesmo ponto metodológico: a F4
era sequencial, acumulava múltiplos timeouts por turma/superfície e não
capturava várias exceções Playwright antes de `evaluate_result()`.

## Objetivo F4.1

Preservar exatamente o boundary read-only da F4 e tornar a evidência browser
determinística, granular e resistente a falhas de um único par.

A F4.1 deve responder, para cada uma das seis turmas de Matemática:

1. a página pública carregou;
2. os anchors necessários ao probe existem;
3. turma e componente foram prefilled;
4. as três datas sintéticas aparecem no DOM de Objetos de Conhecimento;
5. as três datas sintéticas aparecem no DOM de Frequência;
6. qualquer erro do instrumento é separado de um mismatch funcional.

## Escopo

Escola:

`E M E I E F Jose Pereira Barbosa`

Professor investigado:

`Luiz Gomes dos Santos`

Componente:

`Matemática`

Turmas:

- 6º ANO A
- 6º ANO B
- 7º ANO A
- 7º ANO B
- 8º ANO A
- 9º ANO A

Datas sintéticas:

- 2026-09-01
- 2026-09-02
- 2026-09-03

## Taxonomia obrigatória

### `PASS / PUBLIC_BROWSER_RENDER_CURRENT`

Somente quando os seis pares concluírem os probes de Conteúdo e Frequência sem
erro de instrumento e com prefill/DOM esperados.

### `FAIL / PUBLIC_BROWSER_RENDER_GAP`

Somente quando todos os probes necessários forem executáveis e houver mismatch
determinístico do estado renderizado.

Exemplos:

- selects existem e permanecem selecionados em valores diferentes do esperado;
- região DOM esperada existe, mas a contagem das datas sintéticas diverge.

### `INCONCLUSIVE / PUBLIC_BROWSER_RENDER_PROBE_ERROR`

Qualquer falha de instrumento impede que o caso seja promovido a product gap.

Exemplos:

- navegação expira;
- anchor de heading/tab/botão não pode ser localizado;
- ação Playwright falha;
- Chromium/runner não inicia;
- quantidade de pares não pode ser completada.

Regra principal:

> **timeout nunca é convertido automaticamente em `PUBLIC_BROWSER_RENDER_GAP`.**

## Hardening

### Isolamento por par

Cada turma recebe uma página própria no mesmo BrowserContext. Falha em um par
não encerra os demais.

### Checkpoints em streaming

A F4.1 emite linhas metadata-only:

`TEACHER_VISIBILITY_F4_1_CHECKPOINT=...`

por turma, superfície e estágio. Assim, mesmo um encerramento anormal deixa
evidência de progresso no log do job.

### Timeouts menores e explícitos

Defaults:

- navegação: 15 s;
- ação Playwright: 8 s;
- polling determinístico: 8 s.

O pior caso deixa margem operacional significativa abaixo do teto do job
F4.1, configurado em 15 minutos.

### JSON sempre estruturado

O executável captura falhas de browser/runner e tenta sempre emitir:

`TEACHER_VISIBILITY_F4_1_JSON=...`

A ausência desse JSON é convertida pelo workflow em
`PUBLIC_BROWSER_RENDER_PROBE_ERROR`, nunca em gap de produto.

## Boundary read-only

A F4.1 preserva o contrato da F4:

- produção: somente recursos públicos via GET;
- `service_workers="block"`;
- toda URL com `/api/` é interceptada e respondida localmente;
- qualquer método diferente de GET é abortado antes da rede;
- fetch/XHR não-API somente em allowlist same-origin:
  - `/version.json`
  - `/asset-manifest.json`
  - `/manifest.json`
- WebSockets são fechados localmente sem `connect_to_server`;
- usuário/token/tenant/escola/turmas são sintéticos;
- sem login real;
- sem Mongo;
- sem estudantes;
- sem `attendance.records`;
- sem notas;
- sem texto pedagógico;
- sem screenshots;
- sem escrita em produção;
- sem backfill/remapeamento/migração/correção.

## Gate pós-merge

A F4.1 só pode executar após merge explicitamente autorizado em `main`.

Título:

`[TEACHER-VISIBILITY-F4.1-BROWSER] <TARGET_SHA>`

Corpo:

```text
TEACHER_VISIBILITY_F4_1=AUTHORIZED
CONFIRMATION=AUDIT_PUBLIC_BROWSER_RENDER_READ_ONLY
TRACKING_ISSUE=357
TARGET_SHA=<exact main SHA>
EXPECTED_PRODUCTION_SHA=<exact production SHA>
```

O workflow deve falhar fechado se:

- o gate não for criado pelo owner;
- o tracking #357 não estiver aberto;
- `main` mover;
- `production` mover;
- qualquer SHA/campo/título divergir.

Nenhum merge ou deploy é automático.

## Interpretação causal

F1/F2/F3.1 permanecem válidas:

- F1: sem identity split/assignment drift nos seis pares Luiz Gomes;
- F2: dados e projeção HTTP presentes para os seis pares;
- F3.1: assets públicos atuais contêm os bridges esperados.

A F4.1 existe exclusivamente para fechar, com metodologia corrigida, o elo:

`assets públicos → execução React → prefill → DOM`.

Somente depois de `PUBLIC_BROWSER_RENDER_CURRENT` será defensável deslocar a
causa remanescente para estado específico do dispositivo/sessão do professor
(cache HTTP, localStorage ou Service Worker previamente instalado).

Somente depois de `PUBLIC_BROWSER_RENDER_GAP` estruturado será defensável abrir
uma etapa de investigação/correção React.

`PUBLIC_BROWSER_RENDER_PROBE_ERROR` mantém o produto **não condenado** e exige
correção do instrumento antes de qualquer inferência funcional.
