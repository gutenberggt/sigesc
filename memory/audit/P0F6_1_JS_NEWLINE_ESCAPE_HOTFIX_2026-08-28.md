# P0-F6.1 — Hotfix de escape de newline na estação offline

Data: 2026-08-28

## Sintoma

O HTML privado P0-F6 foi gerado com `PASS`, SHA e permissões corretas, porém o navegador exibiu `0 / 0 decisões` e o Console registrou:

`Uncaught SyntaxError: Invalid or unexpected token`.

## Causa raiz

O template Python do P0-F6 continha o literal JavaScript destinado a gerar `+'\\n'` no JSON exportado. Por estar dentro de uma string Python, o escape foi consumido antes da emissão do HTML, produzindo uma quebra de linha física dentro de uma string JavaScript e tornando o script inválido.

## Correção

Foi criada uma camada compatível e fail-closed que:

- reutiliza integralmente o P0-F6 original;
- corrige exclusivamente o padrão de newline inválido;
- exige ocorrência determinística do padrão esperado;
- preserva CSP, modo `0600`, ausência de rede, ausência de recomendação automática e ausência de banco;
- delega a selagem ao contrato P0-F6 original sem mudança semântica.

## Regressão adicionada

O CI agora gera um HTML sintético e extrai o JavaScript emitido. A sintaxe é validada com `node --check`, além de verificar explicitamente que o newline permanece escapado como backslash+n no HTML final.

## Escopo

Nenhum dado privado foi versionado. Nenhum acesso ao MongoDB, nenhuma decisão humana, nenhuma consolidação, remapeamento, exclusão, criação ou escrita em produção é autorizada por este hotfix.
