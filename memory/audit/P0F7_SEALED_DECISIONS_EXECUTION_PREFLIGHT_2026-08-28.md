# P0-F7 — Preflight de execução das decisões humanas seladas

Data: 2026-08-28

## Objetivo

A P0-F7 transforma a cadeia privada P0-F5 -> P0-F6 selado em um plano de execução **exclusivamente read-only**. A fase não aplica nenhuma decisão e não autoriza um executor futuro.

Entradas privadas esperadas:

- pacote P0-F5 original, com `manifest_sha256` válido;
- manifesto P0-F6 selado, com `decision_manifest_sha256` válido;
- estado atual do MongoDB consultado apenas para leitura.

## Invariantes

1. A cobertura das decisões P0-F6 deve ser exata: uma decisão por `review_unit_id` conhecido.
2. A origem criptográfica deve apontar para o mesmo manifesto P0-F5.
3. O estado vivo de cada valor SOURCE/TARGET deve continuar equivalente ao snapshot P0-F5; qualquer drift bloqueia.
4. Cada documento envolvido recebe fingerprint SHA-256 para um futuro CAS.
5. `KEEP_SOURCE` e `KEEP_TARGET` são decisões humanas determinísticas, mas não são executadas nesta fase.
6. `MANUAL_RECONCILIATION` não é convertida automaticamente em valor de banco. A nota humana é texto livre e somente seu hash é levado ao plano.
7. Sobreposições semânticas fora do pacote P0-F5 continuam bloqueando quando exigem revisão, inclusive alocação docente, vínculo docente, horário ou dependência.
8. O componente source só poderá ser retirado depois de referência zero e sempre no fim de uma execução futura.
9. Rollback exigirá autorização explícita separada.
10. O manifesto P0-F7 não constitui autorização para escrita em produção.

## Saída

O relatório privado P0-F7 contém:

- hashes canônicos P0-F5 e P0-F6;
- contagem por decisão humana;
- unidades determinísticas e reconciliações manuais;
- intenções `SET_TARGET_FROM_SOURCE` e `PRESERVE_TARGET_VALUE` sem copiar o valor acadêmico;
- hashes do valor snapshot e do valor vivo;
- fingerprints CAS por documento;
- blockers individualizados;
- contagem conservadora de documentos source ainda referenciados;
- colisões semânticas determinísticas candidatas;
- ordem obrigatória de uma futura execução;
- contrato de rollback.

O stdout é compacto e não imprime conteúdo pedagógico, notas, frequência ou justificativas humanas.

## Interpretação da P0-F6 selada atual

A P0-F6 fechou com 144 decisões humanas:

- 92 `KEEP_SOURCE`;
- 44 `KEEP_TARGET`;
- 8 `MANUAL_RECONCILIATION`.

A P0-F7 não assume que as 8 notas livres constituam um valor final estruturado. Portanto, se a execução em produção confirmar essas 8 decisões manuais, `p0f7_1_structured_manual_reconciliation_required` deverá permanecer verdadeiro e o executor continuará bloqueado até uma fase específica materializar os valores finais de forma explícita e verificável.

## Ordem segura prevista

1. validar cadeia e CAS;
2. materializar reconciliações manuais estruturadas;
3. aplicar resoluções humanas de campo com CAS;
4. resolver colisões semânticas não humanas;
5. remapear referências source não colidentes para target;
6. provar referência source zero;
7. retirar o componente source por último;
8. executar auditoria pós-operação e emitir recibo.

Essa ordem é apenas contrato de planejamento. Nenhuma etapa é executada pela P0-F7.

## Execução planejada em produção

Após merge e redeploy, o auditor deverá receber os dois artefatos privados preservados no host e gravar um novo JSON privado com modo `0600`.

Exemplo de interface:

```bash
python /app/scripts/audit_p0f7_sealed_decisions_execution_preflight.py \
  --packet /tmp/p0f5-private-review.json \
  --sealed /tmp/p0f6-human-decisions-sealed.json \
  --academic-year 2026 \
  --json /tmp/p0f7-private-preflight.json
```

A execução produtiva só deverá ocorrer depois do PR aprovado e integrado. Nenhuma autorização de merge é autorização de escrita no MongoDB.
