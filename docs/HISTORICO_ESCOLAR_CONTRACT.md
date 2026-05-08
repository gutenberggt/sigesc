# Contrato do Histórico Escolar (com Dependência de Estudos)

> **Status: CONGELADO V1 (Fev/2026).**
> Documento normativo. Mudanças exigem PR explícito + bump de `document_version`.
> Quaisquer reemissões futuras de históricos antigos DEVEM resultar no mesmo
> documento — preservar fidelidade temporal é requisito jurídico.
>
> Rotas de implementação: Fase 4 (depois do Boletim — Fase 3).

## 1. Princípio fundador

> **Histórico escolar registra a vida acadêmica REAL do aluno, não a vida acadêmica DESEJADA.**

Toda dependência é evento **complementar**, jamais substitutivo. Reprovação
permanece. Aprovação posterior (via dependência) é registrada **separadamente**,
referenciando o ano original.

---

## 2. Versionamento

Cada histórico emitido carrega:

```json
{
  "document_version": "1.0.0",          // versão do layout/PDF/legendas
  "history_schema_version": "1",        // versão do shape canônico de dados
  "issued_at": "2027-12-15T10:00:00Z",  // ISO timestamp
  "issued_by_user_id": "...",
  "school_id": "...",
  "mantenedora_id": "..."
}
```

Reemissões futuras devem honrar `history_schema_version` para reproduzir o documento
sem deriva. Layouts novos ganham `document_version` mais alto sem alterar
shape de dados.

---

## 3. Regras imutáveis

### 3.1 Nunca sobrescrever reprovação original

❌ ERRADO:
```
2024 → Matemática → Reprovado
2025 → Dependência aprovada
=> alterar 2024 para "Aprovado"
```

✅ CORRETO:
```
2024 → Matemática → Reprovado em Dependência
2025 → Dependência de Matemática (ref. 2024) → Aprovado
```

A linha de 2024 permanece intocada para sempre. A linha de 2025 referencia
a origem via `original_academic_year`.

### 3.2 Cronologia real

Eventos aparecem na ordem em que aconteceram. Dependências concluídas anos
depois ficam na linha do ano de **conclusão** (não no ano original).

### 3.3 Carga horária preservada

Cada componente reprovado e cada dependência preservam `carga_horaria_h` de
**quando aconteceu**. Reorganização curricular futura não retroage.

### 3.4 Coerência temporal de matriz

Componentes referenciam `original_curriculum_version` para que reemissões
futuras renderem com a matriz vigente naquele ano — mesmo que a matriz tenha
sido reformulada depois.

### 3.5 Dependência concluída ainda mantém referência ao ano original

Mesmo após `dependency.status = 'completed'`, o item do histórico preserva:
- `original_course_id`
- `original_course_name` (snapshot — não link, pois nome pode mudar)
- `original_academic_year`
- `original_class_id` (snapshot)
- `original_curriculum_version`

### 3.6 Online ≡ PDF

PDF e visualização online são gerados pela **mesma fonte canônica de dados**.
Pipeline obrigatório:

```
canonical_history_payload → renderer único → { html, pdf }
```

Nunca renderizar PDF a partir do DOM. Diferenças entre online e PDF são
inconsistência jurídica grave.

---

## 4. Shape canônico (history_schema_version=1)

```json
{
  "history_schema_version": "1",
  "document_version": "1.0.0",
  "student": {
    "id": "...",
    "full_name_at_issue": "...",         // snapshot — não link, pois pode mudar legalmente
    "cpf": "...",                         // se aplicável e autorizado
    "birth_date": "YYYY-MM-DD",
    "rg": null,
    "nationality": "Brasileira",
    "origin_state": "..."
  },
  "school": {
    "id": "...",
    "name_at_issue": "...",
    "cnpj": "...",
    "inep_code": "...",
    "address": "...",
    "mantenedora_id": "..."
  },
  "issue": {
    "issued_at": "...",
    "issued_by_user_id": "...",
    "issued_by_role": "secretario",
    "rationale": "Solicitação do responsável"  // opcional
  },
  "academic_records": [
    {
      "academic_year": 2024,
      "school_stage": "anos_finais",
      "series_label": "9º ano",
      "class_label_at_issue": "9A",
      "result": "reprovado",
      "components": [
        {
          "course_id": "co_mat",
          "course_name_at_issue": "Matemática",
          "carga_horaria_h": 200,
          "curriculum_version": "BNCC-2018-municipal-rev3",
          "final_grade": 4.5,
          "final_attendance_pct": 78.0,
          "result": "reprovado",
          "is_dependency_origin": true
        },
        {
          "course_id": "co_pt",
          "course_name_at_issue": "Português",
          "carga_horaria_h": 240,
          "curriculum_version": "BNCC-2018-municipal-rev3",
          "final_grade": 7.2,
          "final_attendance_pct": 92.0,
          "result": "aprovado"
        }
      ]
    },
    {
      "academic_year": 2025,
      "school_stage": "anos_finais",
      "series_label": "9º ano (cursando — em dependência)",
      "class_label_at_issue": "9B",
      "result": "aprovado_em_dependencia",
      "components": [
        // ... componentes regulares de 2025 ...
      ],
      "dependency_completions": [
        {
          "dependency_id": "dep_xyz",
          "original_academic_year": 2024,
          "original_course_id": "co_mat",
          "original_course_name": "Matemática",
          "original_class_id": "cl_9a_2024",
          "original_curriculum_version": "BNCC-2018-municipal-rev3",
          "completed_in_academic_year": 2025,
          "final_grade": 7.0,
          "final_attendance_pct": 88.0,
          "result": "aprovado",
          "completed_at": "2025-12-10"
        }
      ]
    }
  ],
  "summary": {
    "first_enrollment_year": 2014,
    "current_status": "concluinte",
    "total_years": 12
  },
  "signatures": [
    { "role": "secretario", "name": "...", "matricula": "..." },
    { "role": "diretor", "name": "...", "matricula": "..." }
  ],
  "audit": {
    "checksum_sha256": "...",      // hash do payload canônico (sem signatures)
    "ip": "...",
    "user_agent": "..."
  }
}
```

**Observação importante**: campos com sufixo `_at_issue` são **snapshots**. NÃO
sobrescrever quando o registro de origem mudar — preservam o estado vigente
quando o histórico foi gerado.

---

## 5. Dependências no histórico — regras específicas

### 5.1 Formato textual obrigatório

Linha de origem (ano da reprovação):

```
2024 — 9º ano — Matemática — 4.5 — 78% — REPROVADO EM DEPENDÊNCIA
```

Linha de conclusão (ano da aprovação na dependência):

```
2025 — Dependência de Matemática (ref. 2024 — 9º ano) — 7.0 — 88% — APROVADO
```

### 5.2 Dependência cancelada

NÃO aparece no histórico. Permanece apenas no log/auditoria interna.

### 5.3 Dependência reprovada

Aparece no histórico no ano da tentativa, com `result: "reprovado_em_dependencia"`.
A linha de origem permanece marcada como `REPROVADO EM DEPENDÊNCIA`. O aluno
pode tentar nova dependência em ano subsequente — cada tentativa gera linha
própria.

---

## 6. PDF — regras técnicas

### 6.1 Pipeline obrigatório

```
canonical_history_payload (JSON, schema v1)
  → server-side template renderer (HTML)
    → headless renderer (Playwright/Chromium ou WeasyPrint)
      → PDF/A-2b (arquivamento)
```

NÃO usar:
- Renderização do DOM da SPA via `html2canvas` ou similar
- PDF gerado client-side
- Templates desincronizados entre online e PDF

### 6.2 Metadados embutidos no PDF

```
PDF Metadata:
  /Title         "Histórico Escolar - <full_name_at_issue>"
  /Author        "<school.name_at_issue>"
  /Subject       "Histórico Escolar"
  /CreationDate  ISO timestamp
  /Keywords      "historico, escolar, <mantenedora>, <inep>"
  /Producer      "SIGESC v<version> (history_schema_version=1)"
```

Documento canônico SHA-256 também embutido como custom field para verificação
posterior.

### 6.3 QR Code de verificação

Cada PDF carrega QR code apontando para
`https://<host>/api/public/history/verify/<verification_token>`. Endpoint
público devolve `{ valid: true, issued_at, school_name, checksum }` para
validação por terceiros (faculdades, processos seletivos).

---

## 7. Reemissão fiel de históricos antigos

Para reemitir um histórico de 2018 hoje:

1. Carrega o snapshot canônico daquela emissão (immutable record em
   `db.issued_histories`).
2. Resolve `document_version` daquele snapshot.
3. Roteia para o renderer do template correspondente (templates antigos
   permanecem versionados em `/app/backend/pdf/templates/history_v1.0.0.html`).
4. Gera PDF idêntico ao original.

Templates antigos NUNCA são deletados. Apenas marcados como `deprecated_for_new_issues`.

---

## 8. Cenários a cobrir nos testes (Fase 4)

1. Aluno sem reprovações — histórico simples regular
2. Aluno com reprovação em dependência (sem ainda ter cursado a dependência)
3. Aluno com dependência concluída no mesmo ano da matrícula regular (ano subsequente)
4. Aluno com dependência cancelada — NÃO aparece
5. Aluno com dependência reprovada (precisa nova tentativa)
6. Aluno com 2 dependências em anos diferentes (anos 2023 + 2024 → conclusão 2025)
7. Aluno transferido entre escolas durante uma dependência
8. Mantenedora com mudança de curriculum_version entre o ano original e ano de conclusão
9. Componente curricular extinto entre o ano original e ano atual (preservar nome snapshot)
10. Reemissão de histórico antigo deve gerar PDF idêntico ao original (checksum equal)

---

## 9. Versionamento futuro

Quando bumpar `history_schema_version`?
- Adição de campo obrigatório
- Mudança de semântica de campo existente
- Remoção/renomeação de campo

Quando bumpar `document_version` (sem mudar schema)?
- Nova legenda/regulamentação
- Novo selo/QR/marca d'água
- Reorganização visual sem perda de dados

NUNCA bumpe sem PR + atualização deste documento.

---

## 10. Não tocar (escopo desta especificação)

- Histórico Acadêmico do Ensino Superior (escopo extra-municipal)
- Diploma de conclusão (documento separado)
- Atestado de matrícula (documento separado, sem histórico)

---

## 11. Riscos conhecidos endereçados

- **Reorganização curricular**: tratado via `original_curriculum_version` snapshot.
- **Mudança de nome de componente**: tratado via `*_name_at_issue` snapshot.
- **Mudança de carga horária**: preservada por ano via `carga_horaria_h` no record.
- **Conflito de calendário entre ano original e ano de conclusão**: cada
  dependência registra `completed_at` separado de `original_academic_year`.
- **Conflito de etapa escolar**: cada record carrega `school_stage` próprio.
- **Mantenedora reorganizada (fusão de redes)**: snapshot `mantenedora_id_at_issue`
  preserva pertencimento histórico.

---

## 12. Pré-requisito de dados (Fase 3 antes da Fase 4)

Antes de implementar histórico, o boletim/ficha individual (Fase 3) deve já:

- Persistir `dependency_completions[]` em coleção própria
  (`db.dependency_completions`) com snapshot de `original_course_name`,
  `original_curriculum_version`, `original_academic_year`.
- Trigger de transição de status `active → completed` cria automaticamente
  o registro em `dependency_completions` capturando o snapshot daquele momento.

Sem isso, a Fase 4 não tem fonte de verdade para emitir o histórico.

---

## 13. Roteiro de implementação (Fase 4)

1. Criar coleção `db.dependency_completions` (snapshot imutável).
2. Hook em `PUT /api/student-dependencies/{id}` que ao mudar status para
   `completed` cria o snapshot.
3. Backfill: snapshot retroativo para deps já completadas em produção.
4. Endpoint canônico `GET /api/history/student/{student_id}` retorna o
   payload canônico schema v1.
5. Renderer único `pdf/history_renderer.py` (template HTML + Chromium/WeasyPrint).
6. Endpoint público de verificação `GET /api/public/history/verify/{token}`.
7. Testes E2E cobrindo os 10 cenários de §8.
8. Bloqueio: histórico só pode ser emitido se aluno tiver `enrollments_history`
   completo (não há lacunas anuais não justificadas).
