# F2.1C — Documentos, pós-validação e elegibilidade de rollback

## Status
Terceiro eixo da Retificação de Matrícula/Turma, posterior a F2.1A (Frequência) e F2.1B (Notas). Esta fase não expõe execução acadêmica pública.

## Objetivo
Concentrar em um domínio único a análise e a resolução documental necessária à futura saga executável, preservando documentos históricos e impedindo que a retificação seja declarada concluída enquanto houver resíduo acadêmico na turma errada.

## Invariantes
1. Documento publicado nunca é apagado nem tem payload/hash reescrito.
2. Documento verificável rastreado somente pode ser invalidado por serviço de domínio e com protocolo da retificação.
3. `manual_document_issuances` incompatível bloqueia automação total enquanto não houver política própria de supersessão/revogação.
4. `diary_snapshots` é imutável; snapshot afetado bloqueia a saga até workflow institucional de supersessão.
5. `promotion_books` é indicador de risco, não prova de emissão de PDF.
6. Os caminhos síncronos históricos sem ledger impedem prova absoluta de ausência de emissão; a futura execução exige reconhecimento administrativo explícito.
7. Rollback é fail-closed quando houve revogação documental irreversível ou emissão nova posterior à retificação.
8. O estado final exige `origem acadêmica = zero`: matrícula ativa, frequência, notas e projeção `students.class_id` não podem permanecer na turma errada.
9. Todas as consultas e mutações são tenant-scoped.

## Serviço canônico
`backend/services/enrollment_rectification_documents.py`

Responsabilidades:
- `build_rectification_document_inventory`: inventário unificado e digest determinístico;
- `resolve_rectification_documents`: resolução idempotente de artefatos revogáveis;
- `check_rectification_rollback_eligibility`: gate documental de rollback;
- `detect_rectification_origin_residues`: pós-condição de limpeza acadêmica da origem.

## Classificação
### Revogáveis automaticamente
- `verifiable_documents` ativos com código verificável;
- `bulletin_verifications` ativos com identidade estável;
- `history_verifications` ativos com identidade estável.

### Bloqueantes
- `school_documents_log` sem documento verificável correspondente;
- `manual_document_issuances` afetados;
- `diary_snapshots` afetados.

### Advertências
- `promotion_books` da turma/ano;
- `document_render_jobs` relacionados;
- existência de rotas síncronas históricas sem ledger.

## Cadeia de custódia
Cada invalidação automática grava ledger em `document_rectifications`, único por mantenedora + protocolo + tipo + artefato, com snapshot/hash anterior, estado, autor e resultado. A revogação de `verifiable_documents` reutiliza `services.verifiable_docs_service.revoke_document`.

## Rollback
O serviço não desfaz revogações definitivas. Se a retificação revogou documento rastreado, o rollback automático fica inelegível. Também fica inelegível quando houver documento rastreado emitido após a execução.

## Rollout
F2.1C não cria `/execute` nem `/rollback`. A ativação acadêmica pertence exclusivamente à fase da saga executável, que deverá consumir este serviço sob o mesmo lock de estudante e somente após concluir os primitivos de Notas e Frequência.
