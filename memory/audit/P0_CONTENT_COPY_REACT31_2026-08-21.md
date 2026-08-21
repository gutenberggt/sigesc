# P0 complementar — crash React #31 ao copiar conteúdo

Data: 2026-08-21

## Caso sentinela

Professora Karina Soares de Oliveira — Escola 22 de Abril — fluxo **Copiar para outra turma** em Objetos de Conhecimento.

## Sintoma

Ao tentar copiar um conteúdo, a rota `/professor/objetos-conhecimento` cai no ErrorBoundary com **Minified React error #31**. Esse erro ocorre quando um objeto JavaScript é entregue diretamente como filho React.

## Causa técnica

O backend/bridge pode retornar `response.data.detail` como objeto estruturado, normalmente com campos como `code` e `message`. A tela de Objetos de Conhecimento encaminha `detail` para `showAlert()`, e o alerta renderiza `alert.message` diretamente.

Já existia `contentCopyErrorNormalizer.js`, mas ele era registrado antes do `contentDvdBridge`. Erros originados dentro de interceptors posteriores do bridge — por exemplo durante operações internas subsequentes à cópia — podiam escapar da primeira barreira e chegar ao React ainda como objeto.

## Correção

1. O normalizador passa a converter detalhes estruturados de rotas de conteúdo (`copy-to-class`, `content-entries`, `learning-objects`) em texto seguro.
2. Arrays de validação FastAPI também são convertidos para uma mensagem textual.
3. O payload técnico original continua preservado em `technical_detail` e o código em `error_code`.
4. Uma segunda barreira (`contentCopyErrorNormalizerLate.js`) é registrada **depois** do `contentDvdBridge`, cobrindo rejeições produzidas por interceptors internos do bridge.
5. Nenhuma regra de RBAC, assignment, cópia, publicação ou persistência é relaxada.

## Critério de aceite

Ao repetir a cópia que antes derrubava a página:

- a tela não pode mais cair no ErrorBoundary/React #31;
- em caso de falha funcional, o usuário deve permanecer na tela e ver mensagem textual legível;
- a mensagem deve revelar a causa real do backend para a etapa seguinte de diagnóstico;
- em caso de sucesso, o conteúdo deve ser copiado normalmente.

## Regressão

`backend/tests/test_content_copy_react31_p0.py` protege:

- normalização de objetos e arrays;
- cobertura das rotas de conteúdo;
- preservação do detalhe técnico;
- ordem de registro da barreira tardia após o DVD bridge.
