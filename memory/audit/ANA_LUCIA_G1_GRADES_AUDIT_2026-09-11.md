# ANA-LUCIA-G1 — Auditoria read-only de notas históricas

Data: 11/09/2026
Tracking issue: #694

## Objetivo
Inventariar em produção, sem escrita, a distribuição dos documentos `grades` dos oito pares de Língua Inglesa (6º A/B/C/D e 9º A/B/C/D) da professora Ana Lucia Faria Pinto em 2026 entre a identidade legada `eja_final` e a identidade canônica `fundamental_anos_finais`.

## Classificações
- `LEGACY_ONLY`: existe somente sob o componente legado.
- `CANONICAL_ONLY`: existe somente sob o componente canônico.
- `BOTH_IDENTICAL`: existem dois documentos com campos pedagógicos equivalentes.
- `BOTH_COMPLEMENTARY`: existem dois documentos sem divergência nos campos sobrepostos e com preenchimentos complementares.
- `BOTH_CONFLICTING`: há divergência real em pelo menos um campo pedagógico preenchido em ambos.
- `NO_GRADE`: matrícula sem documento de nota em nenhuma das duas identidades.
- `DUPLICATE_LEGACY` / `DUPLICATE_CANONICAL`: mais de um documento para a mesma chave turma+estudante+componente+ano.

## Boundary
- MongoDB somente leitura.
- Valores de notas podem ser comparados em memória, mas nunca são emitidos.
- Nomes de estudantes não são lidos.
- IDs de estudantes não são emitidos.
- Nenhuma mutação, backfill, merge, exclusão ou remapeamento.
- 3ª/4ª Etapas EJA ficam fora do escopo por construção.

## Gate de produção
A execução só ocorre por issue owner-only com título `[ANA-LUCIA-G1-RUNTIME] <SHA-de-main>` e corpo contendo:

```
ANA_LUCIA_G1_RUNTIME=AUTHORIZED
CONFIRMATION=READ_ONLY_GRADES_AUDIT
ACADEMIC_YEAR=2026
TRACKING_ISSUE=694
TARGET_SHA=<SHA exato de main>
```

O workflow valida que `main` ainda aponta exatamente para o SHA autorizado antes de acessar produção.
