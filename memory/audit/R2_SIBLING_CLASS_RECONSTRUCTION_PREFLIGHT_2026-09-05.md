# R2.0 — Preflight reutilizável por manifesto — reconstrução turma-espelho

Data: 2026-09-05  
Tracking: `#439` → `#438` → `#418` → `#357`

## Decisão de arquitetura

A correção administrativa por turma-espelho não será implementada como script descartável específico do professor Luiz. O SIGESC passa a preparar esta classe de saneamento em duas camadas:

1. **motor reutilizável read-only**: `backend/scripts/sibling_class_reconstruction_preflight_readonly.py`;
2. **especificação declarativa do caso**: arquivo JSON versionado sob `backend/reconstruction_cases/`.

Cada caso futuro deve possuir especificação, preflight, manifesto congelado por hash e gate humano próprios. A reutilização é do motor, não da autorização.

## Primeiro caso

- Luiz Gomes dos Santos;
- E M E I E F Jose Pereira Barbosa;
- Matemática;
- fevereiro, março e abril de 2026;
- 8º ANO B → 8º ANO A;
- 9º ANO B → 9º ANO A;
- estratégia `MONTHLY_ORDINAL_EXACT_COUNT`.

## Semântica

A operação futura será classificada como **reconstrução administrativa por turma-espelho**, não como recuperação histórica exata. O baseline forense `RECOVERABLE_EXACT=0` não é alterado por esta decisão.

O pareamento reinicia a cada mês. O mês inteiro fica bloqueado se as contagens não coincidirem ou se qualquer condição de segurança falhar.

## R2.0

O preflight:

- resolve professor, escola, turmas, componente e vínculos;
- lê conteúdo da turma B somente para fingerprint interno;
- lê datas de frequência da turma A sem `attendance.records`;
- verifica conteúdo já existente no destino;
- resolve assignment DVD ativo ou histórico posterior aplicável ao backfill;
- gera itens sanitizados apenas quando todo o mês é `READY_TO_APPLY`;
- produz SHA-256 determinístico do manifesto.

Saídas possíveis por mês:

- `READY_TO_APPLY`;
- `BLOCKED_REVIEW_REQUIRED`.

## Boundary

- Mongo: read-only;
- nenhuma escrita em produção;
- nenhuma escrita em `content_entries`, `learning_objects` ou `attendance`;
- `attendance.records` não é projetado/lido;
- sem estudantes, matrículas ou notas;
- plaintext pedagógico pode ser lido somente no processo para fingerprint, mas não pode ser emitido/logado/artefatado;
- IDs técnicos brutos não podem ser publicados;
- sem deploy da aplicação para o preflight.

## Aplicação futura

A futura R2.1 deverá reutilizar o manifesto exato, revalidar o estado de produção e usar exclusivamente a escrita canônica do domínio `content_entries`/`save_content_canonical`. Deve possuir idempotência, provenance explícita, rollback restrito ao lote e gate humano próprio.

A autorização de escrita registrada pelo usuário não transforma R2.0 em mutação: esta fase permanece estritamente read-only.
