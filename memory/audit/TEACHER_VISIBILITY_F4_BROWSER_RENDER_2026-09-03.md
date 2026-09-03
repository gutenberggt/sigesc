# TEACHER-VISIBILITY-F4 — Browser/runtime público → DOM

Data: 2026-09-03  
Tracking: #357

## Contexto

As fases anteriores separaram três camadas:

1. **F1 — identidade/alocação:** para Luiz Gomes dos Santos, os seis pares de Matemática da E M E I E F Jose Pereira Barbosa não apresentam cisão de identidade nem drift de assignment no vínculo efetivo.
2. **F2 — Mongo → HTTP:** os seis pares possuem dados legados e as respostas GET do professor e da gestão permanecem em paridade. O rótulo histórico `*_REACHES_SCREEN`, porém, é uma classificação estrutural; a F2 não executa Chromium nem inspeciona o DOM React real.
3. **F3.1 — assets públicos:** a release de produção e o Service Worker estão coerentes e todos os chunks JS publicados no `asset-manifest.json` contêm os bridges esperados. A falsa classificação anterior vinha de examinar somente os scripts iniciais do `index.html`.

A F4 fecha exclusivamente o elo que ainda não foi observado em browser:

`assets públicos da release → execução React → prefill da rota → estado visível no DOM`.

## Alvo exato

Ano: **2026**.  
Escola: **E M E I E F Jose Pereira Barbosa**.  
Componente: **Matemática**.

Turmas:

- 6º ANO A;
- 6º ANO B;
- 7º ANO A;
- 7º ANO B;
- 8º ANO A;
- 9º ANO A.

## Princípio de segurança

A F4 **não usa a API real do SIGESC**.

O Chromium baixa somente os recursos públicos necessários para executar a SPA publicada (HTML, JS, CSS, fontes e outros assets GET). Antes de qualquer navegação:

- `service_workers="block"` impede que um Service Worker intercepte ou origine tráfego fora do controle do coletor;
- qualquer request cujo path contenha `/api/` é respondida localmente por fixture sintética;
- qualquer método diferente de GET é abortado antes da rede;
- `fetch`/XHR GET fora de `/api/` só pode alcançar, no mesmo origin público, a allowlist explícita `/version.json`, `/asset-manifest.json` e `/manifest.json`; qualquer outro tráfego dinâmico é abortado;
- todo WebSocket é roteado antes da criação da página e fechado localmente sem conexão com o servidor;
- nenhuma request `/api/` é encaminhada à produção.

A sessão é sintética dentro do navegador. Não existe login, senha, cookie autenticado, JWT real ou chamada real a `/auth/me`.

## Fixtures sintéticas

As fixtures modelam somente a forma necessária para provar o comportamento visual:

- um professor sintético;
- uma escola sintética com o nome público do alvo;
- seis turmas sintéticas com os nomes do escopo;
- um componente sintético `Matemática` por turma;
- três datas sintéticas: 01, 02 e 03 de setembro de 2026.

Conteúdo sintético não possui texto pedagógico. Os objetos contêm apenas metadados técnicos artificiais necessários ao frontend (IDs artificiais, data, ano, origem e flags de histórico/read-only).

Frequência sintética contém apenas a lista das três datas. Não há estudantes, matrículas, `attendance.records`, presença/falta, atestados ou PII.

## Provas de DOM

### Objetos de Conhecimento

Para cada uma das seis turmas:

1. abre `/professor/objetos-conhecimento` com `academic_year`, escola, turma e componente sintéticos na query string;
2. confirma que o prefill selecionou a turma esperada e `Matemática`;
3. aguarda explicitamente e confirma que as três datas sintéticas aparecem no calendário com o estado visual de registro existente usado pela tela.

### Frequência

Para cada uma das seis turmas:

1. abre `/professor/frequencia` com o mesmo contexto legado, sem `assignment_id`;
2. confirma o prefill de turma e componente;
3. abre a aba `Registros`;
4. confirma três células DOM com `title="Frequência registrada"`.

## Classificação

- `PUBLIC_BROWSER_RENDER_CURRENT`: os seis pares aplicam o prefill e projetam as três datas sintéticas em ambas as superfícies.
- `PUBLIC_BROWSER_RENDER_GAP`: pelo menos um par falha no prefill ou na projeção DOM.

A classificação é diagnóstica. Um `GAP` não autoriza alteração funcional ou saneamento de dados.

## O que a F4 prova — e o que não prova

Se a F4 passar, fica provado que **a release pública atualmente servida consegue executar, em um Chromium limpo, o caminho de renderização esperado para dados com a mesma forma estrutural que a UI consome**.

Isso, combinado com F2 (dados reais chegam aos endpoints) e F3.1 (build público correto), reduz a hipótese restante para condições específicas da sessão/dispositivo quando a ausência visual persistir — por exemplo, estado local antigo, cache ou Service Worker previamente instalado.

A F4 deliberadamente **não** reproduz o cache, localStorage ou Service Worker de um dispositivo real já usado pelo professor. Portanto, ela não deve ser descrita como prova de que todo cliente existente está atualizado.

## Boundary

- produção: recursos públicos GET somente;
- `/api/`: 100% local/sintética, zero requests à produção;
- fetch/XHR dinâmico não-API: allowlist explícita e same-origin; demais tentativas abortadas;
- WebSocket: bloqueado antes de conexão ao servidor;
- autenticação real: não;
- MongoDB: não;
- estudantes/matrículas/notas: não;
- `attendance.records`: não;
- texto pedagógico: não;
- screenshots: não;
- escrita, backfill, remapeamento, migração ou correção: não;
- MT-1, Transferência e AEE: intocados.

## Gate após merge aprovado

A execução browser só fica disponível na `main` após revisão e merge humano deste PR. Depois disso, o gate é uma issue criada pelo proprietário com o SHA exato da `main` e o SHA exato da branch `production`:

Título:

`[TEACHER-VISIBILITY-F4-BROWSER] <TARGET_SHA>`

Corpo:

```text
TEACHER_VISIBILITY_F4=AUTHORIZED
CONFIRMATION=AUDIT_PUBLIC_BROWSER_RENDER_READ_ONLY
TRACKING_ISSUE=357
TARGET_SHA=<SHA exato da main>
EXPECTED_PRODUCTION_SHA=<SHA exato da production>
```

O workflow recusa execução se `main` ou `production` tiverem se movido, se o tracking #357 estiver fechado, se o gate não tiver sido criado pelo proprietário ou se qualquer campo divergir.

O artifact contém somente JSON de diagnóstico/metadados e é retido por 90 dias. O resumo é anexado ao tracking #357. Nenhum merge ou deploy é automatizado por esta fase.
