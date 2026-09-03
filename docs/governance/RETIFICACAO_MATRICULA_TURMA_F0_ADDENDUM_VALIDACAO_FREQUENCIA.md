# Adendo F0 — Validação Institucional e Concorrência da Frequência

> **Normativo complementar a:** `RETIFICACAO_MATRICULA_TURMA_F0.md`  
> **Baseline:** `9954fe5a687a5cf4e661aec11725a7520e23c6f6`  
> **Escopo:** frequência institucionalmente validada, versionamento e CAS.  
> **Sem implementação funcional.**

## 1. Achado da auditoria

`backend/routers/attendance.py` possui validação institucional explícita da frequência.

Ao validar um documento de `attendance`, o SIGESC grava, entre outros:

- `validated_by`;
- `validated_by_name`;
- `validated_by_role`;
- `validated_at`;
- nova `version`.

A reversão de validação também é uma operação institucional controlada. Ela:

- exige autorização;
- limpa os campos de validação corrente;
- incrementa `version`;
- preserva a validação anterior em `validation_history[]`;
- exige rationale;
- mantém trilha append-only.

Conclusão: remover um estudante de `attendance.records[]` altera materialmente o conteúdo de um documento que pode já ter sido validado. A Retificação não pode manter o selo de validação anterior sobre um payload diferente.

## 2. Invariantes adicionais

### FREQ-08 — Validação nunca sobrevive silenciosamente à mudança de payload

Se um documento de `attendance` afetado pela retificação possuir `validated_by`, o motor NÃO pode alterar `records[]` mantendo `validated_by/validated_at` como se o novo conteúdo tivesse sido originalmente validado.

### FREQ-09 — Desvalidação administrativa auditada

Antes de remover o student-record de um lançamento validado, a saga deve registrar a reversão institucional da validação com rationale derivada do protocolo, por exemplo:

`Retificação de matrícula/turma — protocolo RET-...`

A validação anterior permanece em `validation_history[]`.

A operação deve reutilizar serviço interno canônico da validação/desvalidação ou extrair esse domínio do router; NÃO duplicar a regra no motor de retificação.

### FREQ-10 — CAS/versionamento obrigatório

Toda alteração de um documento de `attendance` pela retificação deve usar Compare-And-Set com a `version` observada no dry-run/revalidação.

Conceitualmente:

```text
update attendance
where id = <attendance_id>
  and version = <expected_version>
```

Se `matched_count != 1`, a operação falha fechado com conflito concorrente. Não usar overwrite forçado.

A versão deve ser incrementada em cada mudança institucional relevante.

### FREQ-11 — Revalidação pós-correção

Depois da retirada do student-record:

- o documento não pode voltar automaticamente a `validated` fingindo que o mesmo usuário validou o novo payload;
- a F1 deve escolher explicitamente um dos estados:
  1. `pending_revalidation`/não validado, exigindo nova validação institucional por usuário autorizado; OU
  2. revalidação administrativa própria da retificação, com novo evento, novo timestamp e autoria explícita da autoridade que executou a correção.

**Recomendação F0:** opção 1 — deixar pendente de revalidação. É mais fiel à separação de responsabilidades: a retificação corrige o vínculo; a validação institucional confirma o diário resultante.

### FREQ-12 — Status final da retificação e pendências de revalidação

Uma frequência aguardando revalidação não é resíduo do estudante na turma errada, mas é uma pendência institucional.

O protocolo deve separar:

- `academic_postconditions_passed`: origem sem student-record e ledger íntegro;
- `attendance_revalidation_pending`: lista de attendance IDs;
- `document_resolution_pending`: lista documental, quando houver.

A operação pode chegar a `core_applied`, mas somente deve alcançar `applied` final quando a política aprovada para revalidação e documentos tiver sido satisfeita.

## 3. Impacto no dry-run

O manifesto de frequência deve incluir, para cada documento:

- `attendance_id`;
- `version` atual;
- `validated` true/false;
- `validated_by` (ID; nome apenas quando necessário na UI autorizada);
- `validated_at`;
- existência de snapshot publicado associado;
- student-record a retirar;
- hash do student-record/documento necessário ao CAS/snapshot;
- classificação `requires_unvalidation`;
- classificação `requires_revalidation`.

Resumo obrigatório:

```json
{
  "attendance": {
    "documents_affected": 0,
    "validated_documents": 0,
    "records_to_rectify": 0,
    "requires_revalidation": 0
  }
}
```

## 4. Impacto na saga

A sequência de frequência do documento principal da F0 é refinada para:

1. revalidar `version`/hash;
2. snapshotar estado anterior;
3. se validado, executar desvalidação administrativa auditada;
4. confirmar nova `version`;
5. inserir evidência idempotente em `attendance_rectifications`;
6. remover somente o student-record via CAS;
7. incrementar versão;
8. auditar diff individual;
9. marcar o documento para revalidação institucional;
10. pós-validar ausência do estudante e preservação dos demais records.

Nenhuma etapa altera data, componente, `aula_numero`, autoria docente ou status dos demais estudantes.

## 5. Impacto no rollback

Rollback somente é elegível se as versões/hashes ainda coincidirem com os checkpoints esperados.

Quando a retificação desvalidou um documento:

- o rollback pode restaurar o student-record pelo snapshot, via CAS;
- não deve apagar `validation_history[]`;
- não deve recriar silenciosamente a validação antiga como se a reversão nunca tivesse ocorrido;
- o documento restaurado continua sujeito a validação institucional explícita conforme política aprovada.

Portanto, a trilha de validação é append-only mesmo quando o payload acadêmico é restaurado.

## 6. Testes adicionais obrigatórios para F1

1. attendance não validado → retificação com CAS passa;
2. attendance validado → não é alterado mantendo selo antigo;
3. desvalidação preserva entrada em `validation_history`;
4. mudança concorrente de `version` entre dry-run e execute → 409 e zero mutação parcial;
5. alteração concorrente durante a fase de frequência → saga interrompe/compensa;
6. demais estudantes permanecem idênticos;
7. documento alterado fica explicitamente pendente de revalidação;
8. rollback não apaga histórico de validação/desvalidação;
9. revalidação posterior gera nova autoria/timestamp, nunca reaproveita os antigos.

## 7. Decisão proposta

**DEC-11 — frequência validada será desvalidada de forma auditável antes da retificação e ficará pendente de nova validação institucional após a correção.**

Essa política impede que o SIGESC apresente como “validado” um conteúdo diferente daquele efetivamente validado e preserva integralmente a cadeia de custódia do diário escolar.
