# F2.1B — Registro de implementação técnica

Baseline: `c462022d2906804a5b1e137c14f92cde1f9864f1`

A F2.1B implementa o domínio interno de Notas/Conceitos para a futura saga de `retificacao_enturmacao`, sem expor execução pública.

## Implementado

- fingerprint acadêmico compartilhado para `grades`, independente de `updated_at`;
- hardening do `grades_manifest` F1.0 com fingerprints de origem/destino, cardinalidade, campos migráveis e conflitos de metadados;
- primitivo interno `apply_grade_rectification_item` com ledger `grade_rectifications`, idempotência e estados `PENDING`, `DESTINATION_APPLIED`, `APPLIED` e `FAILED_RECOVERABLE`;
- validação fail-closed de tenant, estudante, turma, ano, componente, `dependency_id`, fingerprints e colisões;
- criação/merge seletivo do destino somente em campos vazios;
- preservação de `grade_ownership` por campo sem atribuir autoria ao professor destino;
- `rectified_fields` granular por campo com protocolo e cadeia de custódia;
- recálculo de `final_average/status` pelo cálculo canônico existente;
- retirada CAS da grade ativa da turma errada somente após confirmar o destino;
- snapshot da origem e do estado anterior do destino no ledger para compensação futura;
- compatibilidade CAS com documentos legados que não possuem fisicamente `grade_ownership`/`rectified_fields`;
- compatibilidade de congelamento: novas retificações usam `rectified_fields`; `migrated_from_class_id` legado continua suportado;
- guard CI específico da F2.1B.

## Segurança

- nenhum router novo;
- nenhum `/execute`;
- nenhum `/rollback`;
- `ACADEMIC_MUTATION_IMPLEMENTED = False` permanece obrigatório;
- nenhuma retificação real de estudante é executada nesta fase.

## Validação executada

O bootstrap técnico executou compilação, regressões F1/F2, Notas/DVD e historical backfill. O hardening adicional executou a suíte focada F2.1B incluindo documentos legados sem mapas de metadados.

A validação definitiva ocorre novamente no PR pelo workflow `Enrollment Rectification F2.1B - Grades Guard` e pelos gates gerais do repositório.
