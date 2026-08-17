# Validação da proteção da branch `main`

**Data:** 2026-08-17  
**Objetivo:** validar o ruleset de proteção da branch principal após a Fase 2 do Diário por Vínculo Docente.

## Regras esperadas

- alterações na `main` somente por Pull Request;
- branch de PR deve estar atualizada com a `main` antes do merge;
- resolução obrigatória de conversas de revisão;
- force-push bloqueado;
- exclusão da `main` bloqueada;
- bypass administrativo somente por Pull Request;
- método de merge permitido: `Merge`;
- aprovações obrigatórias: 0.

## Status checks obrigatórios

1. `Nomenclature - Estudante guard`;
2. `Frontend - yarn build`;
3. `Backend - ruff lint`;
4. `Backend - Diário por Vínculo guards`;
5. `GATE - Regressão Transferência`.

## Critério de validação

Este arquivo não altera comportamento funcional do SIGESC. O PR que o adiciona existe exclusivamente para confirmar que o ruleset recém-criado é aplicado à `main` e que os checks obrigatórios são executados antes do merge.
