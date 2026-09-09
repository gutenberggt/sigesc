# F2.1B — Retificação de Matrícula/Turma: notas por campo e proveniência DVD

> Issue: #570  
> Baseline: `c462022d2906804a5b1e137c14f92cde1f9864f1`  
> Pré-requisitos: F2.0 + F2.1A publicados, ambos sem execução acadêmica pública.  
> Estado desta fase: **primitivo interno; não exposto para retificação real**.

## 1. Objetivo

Fechar o domínio de Notas/Conceitos necessário à futura saga de `retificacao_enturmacao`, preservando o contrato DVD de autoria por campo, o mapa curricular 1:1 e o comportamento fail-closed em colisão ou concorrência.

A F2.1B não ativa a saga. O gate global `ACADEMIC_MUTATION_IMPLEMENTED` permanece `False` e não será criada rota `/execute` ou `/rollback`.

## 2. Decisão arquitetural

A F0 determina que a retificação não é movimentação acadêmica. Logo, a nota da turma errada não pode continuar aparecendo como percurso real, mas também não pode ser simplesmente reatribuída por troca de `class_id`.

Cada documento de `grades` deve ser tratado por:

1. identidade canônica `student_id + class_id + course_id + academic_year`;
2. mapa curricular origem → destino 1:1;
3. migração apenas dos campos avaliativos não-nulos da origem;
4. colisão não-nula no destino como blocker absoluto;
5. preservação de `grade_ownership` por campo;
6. marcação explícita dos campos retificados;
7. cadeia de custódia suficiente para compensação e auditoria.

## 3. Invariantes

### GRD-F21B-01 — Mapa 1:1 obrigatório

Todo `source_course_id` com valor avaliativo deve possuir exatamente um `target_course_id` aprovado pelo dry-run. Correspondência aproximada não autoriza escrita.

### GRD-F21B-02 — Colisão fail-closed

Se origem e destino tiverem valor não-nulo para o mesmo campo (`b1`, `b2`, `b3`, `b4`, `rec_s1`, `rec_s2`, `recovery`), o item bloqueia antes da primeira mutação.

Não sobrescrever, não tirar média, não escolher por timestamp.

### GRD-F21B-03 — Migração por campo

Quando o documento de destino já existir, somente campos vazios podem receber valores da origem.

### GRD-F21B-04 — Proveniência preservada

Para cada campo migrado, `grade_ownership[field]` deve acompanhar a evidência da origem sem atribuir autoria retroativa ao professor do destino.

Ausência de ownership na origem continua ausência; a gestão não deve inventar ownership.

### GRD-F21B-05 — `rectified_fields` explícito

Campos trazidos pela retificação devem ser registrados explicitamente, por exemplo:

```json
{
  "rectified_fields": {
    "b1": {
      "protocol": "RET-...",
      "source_grade_id": "...",
      "source_class_id": "...",
      "source_course_id": "...",
      "target_course_id": "...",
      "source_value_hash": "sha256",
      "rectified_at": "ISO-8601",
      "rectified_by": "user-id"
    }
  }
}
```

O contrato final pode acrescentar campos, mas não pode depender apenas de `migrated_from_class_id`.

### GRD-F21B-06 — Congelamento granular

Professor comum não pode editar campo explicitamente retificado. Campos do destino não retificados continuam editáveis conforme DVD/vigência normal.

Compatibilidade com documentos legados que usam `migrated_from_class_id` deve ser preservada.

### GRD-F21B-07 — Dependência bloqueia V1

Qualquer grade com `dependency_id` continua `manual_review` / blocker. F2.1B não migra dependência de estudos automaticamente.

### GRD-F21B-08 — Tenant e identidade

Tenant, estudante, turma de origem, ano letivo, `source_grade_id`, `source_course_id` e `target_course_id` são revalidados imediatamente antes de qualquer write.

### GRD-F21B-09 — TOCTOU/CAS

O dry-run deve fornecer fingerprints suficientes da origem e do destino. Mudança de identidade, valores, ownership, dependência ou destino desde o dry-run bloqueia o item.

Se a coleção não possuir `version` canônico, a comparação e o CAS devem usar fingerprint determinístico sobre o subconjunto acadêmico relevante, sem confiar apenas em `updated_at`.

### GRD-F21B-10 — Idempotência

Replay do mesmo protocolo/item não cria segundo destino, não reaplica campo e não altera novamente a origem.

### GRD-F21B-11 — Origem deixa de ser percurso ativo

Após a pós-condição completa do item, a evidência avaliativa da turma errada não pode permanecer como grade acadêmica ativa do estudante na origem.

A remoção/arquivamento deve ocorrer somente depois de o destino estar materializado e verificável, com snapshot F2.0 e auditoria preservando cadeia de custódia.

### GRD-F21B-12 — Cálculo canônico

`final_average` e `status` são derivados novamente pelo cálculo canônico de notas. A F2.1B não duplica fórmula de média.

## 4. Hardening do manifesto F1.0

O `grades_manifest` deve passar a carregar, no mínimo:

- `source_grade_id`;
- `source_course_id`;
- `target_course_id`;
- `source_values`;
- campos não-nulos efetivamente migráveis;
- fingerprint acadêmico da origem, incluindo valores + `grade_ownership` + `dependency_id` + identidade;
- `destination_grade_id` ou ausência esperada;
- fingerprint acadêmico do destino quando existir;
- `overlapping_fields`;
- referência ao mapa curricular já resolvido e coberto pelo `precondition_hash`/token.

O manifesto não contém senha, segredo ou token operacional reutilizável além do contrato HMAC já existente.

## 5. Primitivo interno

Criar serviço dedicado, sugerido:

`backend/services/enrollment_rectification_grades.py`

Responsabilidade de uma chamada: aplicar exatamente **um item** de grade sob o lock da futura saga.

Fluxo:

1. validar actor, tenant, protocolo e parâmetros;
2. revalidar fonte e destino contra manifesto/fingerprints;
3. bloquear `dependency_id`, mapa ausente e overlaps;
4. determinar `fields_to_apply`;
5. criar ou atualizar destino com CAS;
6. copiar `grade_ownership` apenas nos campos aplicados;
7. registrar `rectified_fields` por campo;
8. recalcular média/status pelo serviço canônico;
9. confirmar pós-condições do destino;
10. retirar a grade acadêmica ativa da origem de forma compensável;
11. confirmar ausência ativa na origem e integridade do destino;
12. registrar resultado idempotente/auditável.

Nenhum router chama esse serviço nesta fase.

## 6. Estratégia de compensação

Como produção não presume transação Mongo multi-documento, o item deve ser uma mini-saga persistível/repetível.

Estados mínimos recomendados:

- `PENDING`;
- `DESTINATION_APPLIED`;
- `APPLIED`;
- `FAILED_RECOVERABLE`.

Se houver falha após materializar o destino e antes de retirar a origem, o estado precisa exigir recuperação explícita. Nunca continuar best-effort.

A fonte de restauração continua sendo o snapshot compensável da F2.0 + metadados de cadeia de custódia da F2.1B.

## 7. Compatibilidade com o DVD

`grade_ownership` continua sendo a SSoT de autoria pedagógica por campo.

A F2.1B não deve chamar `apply_grade_field_ownership` como se a retificação fosse um novo lançamento docente; isso poderia atribuir autoria operacional indevida. O primitivo transfere a proveniência já existente.

O write normal de Notas/DVD deve reconhecer `rectified_fields` para congelar somente esses campos, mantendo o comportamento legado de `migrated_from_class_id` para registros históricos já existentes.

## 8. Testes obrigatórios

1. destino inexistente — criação correta;
2. destino existente/vazio — merge seletivo;
3. overlap não-nulo — zero writes;
4. mapa ausente/ambíguo — zero writes;
5. `dependency_id` — bloqueado;
6. ownership preservado por campo;
7. ownership ausente não é inventado;
8. `rectified_fields` granular;
9. campo retificado congelado para professor;
10. campo legítimo futuro permanece editável;
11. source fingerprint stale — zero writes;
12. destination fingerprint stale — zero writes;
13. conflito CAS durante aplicação — estado recuperável/fail-closed;
14. replay idempotente;
15. tenant/student/class/year divergentes — bloqueados;
16. cálculo de média/status canônico;
17. origem não permanece ativa após APPLIED;
18. nenhuma rota `/execute`/`/rollback`;
19. `ACADEMIC_MUTATION_IMPLEMENTED = False`;
20. regressão das rotas atuais de Grades/DVD e do historical backfill.

## 9. Fora de escopo

- executar retificação sobre estudante real;
- reescrever matrícula ou `students.*`;
- acionar a F2.1A de frequência;
- migrar dependência de estudos;
- alterar documentos verificáveis/snapshots;
- alterar histórico escolar nesta fase;
- UI final;
- ativar saga pública.

## 10. Critério de saída

PR isolado a partir do baseline `c462022d2906804a5b1e137c14f92cde1f9864f1`, com:

- contrato F1.0 endurecido para notas;
- primitivo interno F2.1B;
- compatibilidade DVD/`rectified_fields`;
- testes e guard CI específicos;
- regressões verdes;
- revisão do diff.

Merge e deploy dependem de autorização humana explícita própria para a PR da F2.1B.