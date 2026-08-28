# P0-C — Preflight de Remediação da Identidade Docente

Data de referência pedagógica: **2026-08-27**  
Execução P0-B em produção: **2026-08-28T01:24:44Z**  
Estado: **PREFLIGHT READ-ONLY — nenhuma remediação autorizada**

## 1. Evidência imutável de origem

Arquivo preservado no host de produção:

`/root/sigesc-p0-audits/p0_teacher_binding_integrity_20260828T012444Z.json`

SHA-256:

`519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be`

O P0-B confirmou previamente:

- contenção P0 deployada;
- backend saudável e conectado ao MongoDB;
- guard READ-ONLY aprovado;
- 23 escolas e 234 turmas de 2026 no escopo;
- 71 componentes curriculares;
- 2.220 `teacher_assignments` ativos;
- 0 `teacher_allocations`;
- 1.457 `teacher_class_assignments` candidatos;
- 137.954 referências curriculares inspecionadas.

## 2. Leitura correta dos 3.407 sinais

`risk_signals_total=3407` não equivale a 3.407 vínculos docentes quebrados.

A composição observada foi:

- 1.182 `DVD_TEACHER_IDENTITY_UNRESOLVED`;
- 2 `COURSE_MISSING`;
- 3 `DUPLICATE_COURSE_IDENTITY`;
- 1 `DUPLICATE_BINDING_LEGACY`;
- 2.219 chaves de vínculo classificadas como diferentes de `ALL_THREE_OK` porque a terceira representação, `teacher_allocations`, está vazia em produção.

Além disso, `teacher_class_assignments` é uma fonte temporal de rollout progressivo do Diário por Vínculo. Logo, `LEGACY_ONLY=1944` não pode ser automaticamente interpretado como perda de vínculo.

### Conclusão

O P0-C não deve preencher `teacher_allocations` para fabricar convergência entre três fontes. Essa coleção deve ser tratada separadamente como representação possivelmente inativa/legada até decisão arquitetural explícita.

## 3. Achado central de identidade

No P0-B:

- `USER_ID = 227`;
- `EMAIL_FALLBACK = 48`;
- `UNRESOLVED = 1182`.

Os 275 vínculos DVD cuja identidade foi resolvida (`227 + 48`) coincidiram com chaves existentes no legado. Não apareceu `DVD_ONLY` nem outra divergência entre DVD resolvido e `teacher_assignments`.

Isso sustenta a hipótese principal:

> o defeito dominante está na ponte `users.id -> staff.id`, e não em uma perda aleatória de `class_id/component_id`.

O contrato atual confirma duas identidades diferentes:

- `teacher_class_assignments.teacher_id` referencia `users.id`;
- `teacher_assignments.staff_id` referencia `staff.id`.

O cadastro atual de professor grava `staff.user_id` quando cria o usuário automaticamente, porém registros antigos/importados podem não possuir essa ligação.

## 4. Regra de remediação P0-C

Nenhuma correção será inferida por nome de professor ou nome de componente.

Um backfill `staff.user_id <- users.id` só poderá entrar no lote automático se TODOS os critérios abaixo forem satisfeitos:

1. existe usuário DVD real;
2. existe ao menos um vínculo DVD com `component_id`;
3. para cada par exato `(class_id, component_id)` do usuário DVD existe evidência em `teacher_assignments` ativo na data de referência;
4. cada par possui exatamente um `staff_id` candidato;
5. todos os pares do mesmo usuário apontam para o MESMO `staff_id`;
6. `staff.cargo = professor` e o servidor não está explicitamente inativo;
7. `staff.user_id` está vazio ou já corresponde ao próprio usuário;
8. não existe outro `staff` ligado ao mesmo `users.id`;
9. staff e todas as turmas DVD pertencem ao mesmo tenant;
10. se `users.mantenedora_id` existir, também deve coincidir;
11. e-mail pode apenas reforçar a evidência; nunca é suficiente sozinho;
12. qualquer ambiguidade, substituição concorrente, co-docência, conflito de tenant ou divergência de evidência permanece `NEEDS_REVIEW`/`BLOCKED`.

A ausência histórica de `users.mantenedora_id` não autoriza cross-tenant. Nessa situação, o tenant é aceito apenas quando `staff` e todas as turmas envolvidas convergem para exatamente o mesmo tenant.

## 5. Artefato implementado

Script:

`backend/scripts/preflight_teacher_identity_remediation_p0c.py`

Características:

- READ-ONLY contra MongoDB;
- sem modo `--apply`;
- guard estático contra operações Mongo mutadoras;
- sem matching por nome;
- agrupa por `teacher_user_id`;
- produz decisões `ALREADY_CANONICAL`, `READY_SAFE`, `NEEDS_REVIEW` e `BLOCKED`;
- grava manifesto completo determinístico;
- calcula SHA-256 canônico do manifesto;
- cada proposta `READY_SAFE` recebe também `evidence_sha256` próprio;
- não cria `teacher_allocations`;
- não altera AEE.

## 6. Execução planejada após CI + merge

No backend de produção:

```bash
python /app/scripts/preflight_teacher_identity_remediation_p0c.py \
  --academic-year 2026 \
  --reference-date 2026-08-27 \
  --source-evidence-sha256 519f078008fae82dc1277975fcf7de141a9231f391da9d1d47666db9e5f781be \
  --manifest /tmp/sigesc_p0c_teacher_identity_preflight.json
```

O resultado desta fase NÃO autoriza aplicação automática. O manifesto será revisado e preservado antes da construção de qualquer executor P0-C.

## 7. Trilhas paralelas ainda abertas

Não misturar a correção de identidade docente com os demais sinais:

### P0-C.1 — identidade docente

Objeto deste preflight: `users.id -> staff.id`.

### P0-C.2 — referências curriculares ausentes

Investigar individualmente os 2 `COURSE_MISSING`, priorizando proveniência histórica e nunca remapeando por nome.

### P0-C.3 — duplicidade curricular

Os 3 grupos `DUPLICATE_COURSE_IDENTITY` são diagnóstico. Nenhuma exclusão ou consolidação destrutiva será reativada. Um eventual merge curricular deverá ter mapa determinístico, remapeamento de todas as referências, snapshot, pós-check e rollback.

### P0-C.4 — duplicidade de vínculo legado

O único `DUPLICATE_BINDING_LEGACY` será identificado e classificado antes de qualquer alteração.

## 8. Gate para etapa de escrita

Uma futura etapa de aplicação só poderá existir se houver:

- manifesto P0-C preservado;
- SHA-256 conhecido;
- lista fechada de `READY_SAFE`;
- executor idempotente;
- pré-condições `before` verificadas por registro;
- snapshot/rollback;
- auditoria por alteração;
- pós-check obrigatório;
- nova execução do P0-B/P0-C após aplicação;
- autorização humana explícita para escrita em produção.
