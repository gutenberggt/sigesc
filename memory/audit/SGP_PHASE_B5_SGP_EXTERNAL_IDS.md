# Fase B.5 — Armazenamento separado dos IDs externos SGP

Data-base: 2026-08-14  
Status: implementação em branch, **sem provider real e sem envio ao MEC**.

## 1. Objetivo

Persistir, de forma explícita, multi-tenant, idempotente e auditável, o vínculo entre os identificadores internos do SIGESC e os identificadores atribuídos pelo SGP/CMDE:

- `Student.id` ↔ `id_sgp_estudante`;
- `Enrollment.id` ↔ `id_sgp_matricula`.

A B.5 não cria, envia nem consulta lotes. Ela somente fornece a infraestrutura de identidade externa que será consumida por reconciliação/preview/provider em fases posteriores.

## 2. Evidência do contrato oficial

A documentação pública CMDEB v2.0.0, verificada em 2026-08-14, confirma:

- `GET /api/v2/estudantes` retorna `id_sgp_estudante` e matrículas associadas;
- filtros oficiais incluem `id_sgp_matricula`;
- operações posteriores de matrícula usam `id_sgp_estudante` e `id_sgp_matricula`, incluindo enturmação, edição, movimentação/conclusão e frequência;
- os exemplos oficiais apresentam esses identificadores como inteiros positivos.

Consequência: os IDs SGP precisam ser persistidos após reconciliação para que operações subsequentes não dependam de busca ambígua por nome/CPF/matrícula da rede.

## 3. Decisão arquitetural

### 3.1 Coleção própria MIG

A B.5 introduz a coleção:

```text
mig_sgp_external_ids
```

Ela é a SSoT da camada de integração para vínculos externos SGP.

Formato lógico:

```json
{
  "id": "uuid-interno-do-vinculo",
  "provider": "cmde",
  "namespace": "sgp",
  "tenant_id": "...",
  "entity_type": "student | enrollment",
  "internal_id": "ID SIGESC",
  "external_id": "123456",
  "source": "cmde_lookup | lot_reconciliation | manual_reconciliation | legacy_compatibility",
  "correlation_id": "...",
  "lote_id": "...",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### 3.2 Por que não sobrescrever Student/Enrollment

`Student.id` e `Enrollment.id` continuam sendo identidade de domínio do SIGESC. O processo de integração não faz `$set` nesses IDs nem depende de substituir chaves primárias.

O campo já existente `Enrollment.sgp_enrollment_id` permanece compatível com registros anteriores, mas **não é escrito pela B.5**. A B.5 evita dual-write entre entidades escolares e integração. Os slots `sgp_student_id`/`sgp_enrollment_id` do DTO canônico B.1 permanecem como representação de transporte; a hidratação a partir do registro B.5 pertence ao fluxo de preview/reconciliação B.6.

Essa decisão concentra a identidade externa em uma única camada e reduz risco de divergência entre cadastro escolar e estado de integração.

## 4. Normalização

A API oficial expõe os IDs SGP como inteiros. Internamente, a B.5 persiste `external_id` como string decimal positiva:

```text
123456 -> "123456"
"00123456" -> "123456"
```

São rejeitados:

- `0`;
- negativos;
- booleanos;
- vazios;
- valores alfanuméricos;
- formatos com pontuação.

A string evita acoplamento ao limite numérico do provider e mantém estabilidade caso o tamanho do identificador cresça no futuro.

## 5. Integridade e anti-colisão

### 5.1 Índice por identidade interna

Único por:

```text
provider + namespace + tenant_id + entity_type + internal_id
```

Impede um mesmo Student/Enrollment do SIGESC de apontar silenciosamente para dois IDs SGP.

### 5.2 Índice por identidade externa

Único por:

```text
provider + namespace + tenant_id + entity_type + external_id
```

Impede um mesmo ID SGP de apontar para dois registros internos do mesmo tipo e tenant.

### 5.3 Tenant

A unicidade é escopada por `tenant_id`. Isso evita que redes municipais distintas colidam apenas porque o provider utiliza identificadores iguais em contextos diferentes.

### 5.4 Tipos separados

`student` e `enrollment` são namespaces lógicos distintos. O número `123456` pode existir como ID SGP de estudante e como ID SGP de matrícula sem colisão.

## 6. Idempotência e conflito

Repetir:

```text
student-1 -> 123456
```

é idempotente e não cria um segundo documento.

Tentar posteriormente:

```text
student-1 -> 654321
```

falha com `SgpExternalIdConflict`.

Da mesma forma, tentar:

```text
student-2 -> 123456
```

no mesmo tenant/tipo falha explicitamente.

Não existe rebind automático na B.5. Uma eventual correção manual futura deverá ter fluxo próprio, autorização explícita e trilha de auditoria específica.

## 7. Concorrência

Os índices UNIQUE são a barreira definitiva contra race condition. Se duas execuções concorrentes tentarem criar o mesmo vínculo:

1. uma inserção vence;
2. a outra recebe `DuplicateKeyError`;
3. o store relê o vínculo;
4. se for o mesmo par, retorna idempotência;
5. se houver divergência, retorna conflito.

## 8. Auditoria

Cada tentativa de vínculo registra evento no `MigAuditService` com:

- provider;
- tenant;
- operação `external_id.link.student` ou `external_id.link.enrollment`;
- status;
- correlation_id;
- código de conflito, quando aplicável.

O valor do ID SGP **não é gravado no evento de auditoria**, reduzindo exposição desnecessária. O vínculo em si permanece na coleção B.5.

## 9. API interna

`backend/mig/cmde/external_ids.py` fornece:

- `ensure_indexes()`;
- `get(...)`;
- `get_by_external(...)`;
- `link(...)`;
- `resolve_pair(...)`.

`resolve_pair()` entrega:

```python
SgpExternalIdPair(
    student_external_id="123456",
    enrollment_external_id="987654",
)
```

sem substituir os IDs internos. A função prepara a hidratação do contrato canônico no preview B.6.

## 10. Fora de escopo

- autenticação CMDE;
- chamada `GET /api/v2/estudantes`;
- polling de lotes;
- reconciliação automática por CPF/nome;
- provider oficial;
- alteração de feature flags;
- escrita em Student/Enrollment;
- migração automática do campo legado `sgp_enrollment_id`;
- rebind/correção destrutiva de vínculo;
- preview/dry-run B.6.

## 11. Critérios de aceite

- IDs internos nunca são substituídos;
- tenant é obrigatório;
- Student e Enrollment possuem namespaces separados;
- ID SGP inválido não é persistido;
- mesmo vínculo é idempotente;
- divergência interna ou externa falha explicitamente;
- índices UNIQUE protegem concorrência;
- auditoria não expõe o ID externo;
- nenhuma coleção escolar é alterada pela B.5;
- ausência de vínculo continua `None`, nunca `0` ou string vazia;
- nenhum envio real ao MEC é habilitado.
