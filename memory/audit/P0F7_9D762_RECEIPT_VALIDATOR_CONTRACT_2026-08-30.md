# P0-F7.9D7.6.2 — Compatibilidade do validador de recibo

Data: 2026-08-30

## Motivo

Após a D7.6.1 materializar corretamente o executor usando o status ativo exato selado (`active` ou `ativo`) para `RETIRE_DUPLICATE_ASSIGNMENT`, foi identificada uma assimetria residual: o validador offline de recibos ainda importava diretamente o builder D7.6 original.

Isso significava que uma execução poderia produzir um recibo legítimo, mas a validação offline subsequente falharia antes de classificar o resultado, porque o builder original rejeita o status exato preservado pelo manifesto D7.5.

## Correção

O validador `validate_p0f7_9d76_execution_receipt_offline.py` passa a carregar o builder compatível D7.6.1 e utiliza o objeto `d76` já patchado exclusivamente no contrato de status da operação de aposentadoria.

Nenhuma lógica do writer foi alterada. O executor já materializado continua válido e seu SHA não muda.

## Invariantes preservadas

- manifesto D7.5 permanece imutável: `89e0f72d97f7cfa8b2d4b5dd7b5d35a01376a813d69d46f5bce7fa9c11440fcc`;
- plano D7.3.1 permanece imutável: `b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb`;
- preflight D7.4 permanece imutável: `b835f5393e035dee0703f1aa0ae0dd52c779b81d5f73b8c05d0adff3fbcedc9e`;
- exatamente 23 operações;
- estratégia `CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED`;
- zero hard delete;
- nenhuma rede ou banco no validador;
- nenhuma execução de produção pelo wrapper;
- classificação de recibo continua restrita a `APPLIED`, `SAFE_ROLLBACK` ou `ROLLBACK_INCOMPLETE`.

## Regressão adicionada

O teste focado agora importa o validador real e confirma que seu `builder.validate_manifest()` aceita o mesmo status exato que o builder D7.6.1 usa para materialização.

## Estado operacional

Esta correção é pré-execução. Não realiza acesso a produção, não materializa novo executor e não altera os bytes do executor já gerado localmente.
