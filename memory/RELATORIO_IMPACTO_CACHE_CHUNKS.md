# Relatório de Impacto de Armazenamento — Pré-cache de Chunks (Opção A)

> Gerado a partir do build de produção real (`yarn build`, craco/react-scripts).
> Decisão do usuário: **Opção A** — pré-cachear TODOS os chunks listados no `asset-manifest.json`.

## Medições do build (Jun/2026)

| Categoria | Arquivos | Tamanho |
|---|---|---|
| **Entrypoints** | 2 | `main.js` 527,1 KB + `main.css` 138,5 KB |
| **JS chunks (total, inclui main)** | 101 `.js` | **4.495,8 KB (4,39 MB)** |
| **CSS** | 1 `.css` | 138,5 KB |
| `.map` (source maps) | 102 | 16.617,4 KB (**NÃO cacheados** — não são carregados em runtime) |
| `index.html` (em `files`) | 1 | servido network-first (app shell) |

### Total a ser pré-cacheado (js + css, **excluindo** `.map`)
- **102 arquivos · ~4.634 KB · ≈ 4,53 MB**

## Análise de impacto
- **Quota do Cache Storage:** navegadores modernos permitem dezenas de MB a vários GB
  (tipicamente ≥ 50 MB; Chrome até ~60% do disco livre por origem). **4,53 MB é seguro**
  e representa fração mínima da quota.
- **`.map` propositalmente excluídos:** o CRA inclui os `.map` em `asset-manifest.files`,
  mas eles só são baixados ao abrir o DevTools. Cacheá-los inflaria o cache em ~16,6 MB
  sem benefício offline. O pré-cache filtra para `.js`/`.css` apenas.
- **Custo de instalação:** ~4,5 MB baixados uma vez na instalação/atualização do SW
  (sempre durante uma visita ONLINE). Aceitável; ocorre em background.
- **Benefício:** navegabilidade offline consistente em **qualquer rota** já distribuída
  no build, mesmo nunca visitada online antes.

## Estratégia técnica adotada (resumo)
1. `sw.js` install → `fetch('/asset-manifest.json')` → filtra `files` por `.js`/`.css`
   (exclui `.map`) → `cache.add` individual com `allSettled` (um 404 não aborta o install).
2. Bump `CACHE_NAME` v13 → v14. `activate` apaga caches antigos (invalidação) +
   `clients.claim()`. `install` mantém `skipWaiting()`. `OfflineContext` já recarrega
   uma vez em `controllerchange`.
3. `App.js`: `lazy()` envolto em retry com **guard anti-loop** (sessionStorage + janela
   de 10s) para `ChunkLoadError` (hash antigo após deploy).
