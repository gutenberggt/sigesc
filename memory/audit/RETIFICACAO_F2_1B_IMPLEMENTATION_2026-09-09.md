# Evidência técnica — Retificação de Matrícula/Turma F2.1B

Data: 2026-09-09
Baseline: `c462022d2906804a5b1e137c14f92cde1f9864f1`
Branch: `feat/enrollment-rectification-f2-1b-grades`
Issue: #570

## Resultado

Implementação técnica do domínio interno de Notas/Conceitos concluída em branch.

### Contratos fechados

- fingerprint acadêmico determinístico de `grades`;
- manifesto F1.0 endurecido para TOCTOU;
- mapa curricular 1:1 obrigatório;
- colisão não-nula no destino fail-closed;
- ownership DVD preservado por campo;
- `rectified_fields` granular;
- mini-saga/ledger `grade_rectifications`;
- destino materializado e verificado antes da retirada CAS da origem;
- retry idempotente;
- estado recuperável em falha intermediária;
- compatibilidade com documentos legados sem mapas de metadados;
- cálculo de média/status reutiliza a rotina canônica existente.

### Travas preservadas

- sem `/execute`;
- sem `/rollback`;
- sem router público para o primitivo;
- `ACADEMIC_MUTATION_IMPLEMENTED = False`;
- nenhum estudante real processado.

### CI técnico pré-PR

- Bootstrap F2.1B: success;
- compilação dos contratos: success;
- suíte F2.1B + F1/F2 + DVD + historical backfill: success;
- hardening CAS legado: success;
- suíte focada após hardening: success.

A integração em `main` e o deploy permanecem sujeitos à autorização humana explícita específica para o PR.
