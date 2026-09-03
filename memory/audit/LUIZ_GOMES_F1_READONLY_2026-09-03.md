# LUIZ-GOMES-F1 — Auditoria forense read-only de conteúdo/frequência

## Autorização

Caso relatado pelo proprietário em conversa de suporte em 2026-09-03, no mesmo
formato do relato original de Ana Lucia Faria Pinto (issue #304 / ANA-LUCIA-F1,
`memory/audit/ANA_LUCIA_F1_READONLY_2026-09-01.md`).

Este gate **não está autorizado para execução em produção** ainda. Código e
testes ficam prontos e revisados em PR; a execução real exige que o
proprietário abra uma issue owner-scoped equivalente à do caso anterior, com
SHA exato de `main` e a confirmação literal descrita em
"Contrato de autorização" abaixo — mesmo padrão fail-closed de
`ana-lucia-f2-1-runtime-legacy-audit.yml` e demais workflows desta família.

## Caso

Professor: **Luiz Gomes dos Santos**. Escola: **E M E I E F Jose Pereira
Barbosa**. Relato: alguns registros de conteúdo e frequência não são
detectados/exibidos para determinados pares turma/componente, apesar de o
professor informar que os lançou. Sintoma estruturalmente idêntico ao caso já
apurado de Ana Lucia Faria Pinto (vínculo legado presente, mas sem projeção
canônica atual em parte dos pares).

Alvos propostos (2026), todos em Matemática:

1. 6º ANO A / Matemática
2. 6º ANO B / Matemática
3. 7º ANO A / Matemática
4. 7º ANO B / Matemática
5. 8º ANO A / Matemática
6. 9º ANO A / Matemática

## Relação com outros incidentes já rastreados

A mesma escola (E M E I E F Jose Pereira Barbosa) já aparece em
`memory/audit/P0_250_F2_PROFESSOR_PROMOTION_READONLY_AUDIT_2026-08-30.md`,
um incidente **diferente** (Livro de Promoção, professora Abadia Alves
Martins). A coincidência de escola é registrada aqui apenas como contexto; a
LUIZ-GOMES-F1 não assume a mesma causa raiz e não reaproveita nenhuma
conclusão daquele caso.

## Perguntas forenses

Idênticas à ANA-LUCIA-F1, reaplicadas aos 6 pares acima — para cada par, o
coletor determina somente por metadados estruturais:

- existência do vínculo legado ativo em `teacher_assignments`;
- existência de vínculos DVD atuais/históricos em `teacher_class_assignments`;
- existência e intervalo de datas de `learning_objects`;
- existência e intervalo de datas de `content_entries`, distinguindo assignment
  atual, histórico do mesmo professor, sem assignment e outro/indeterminado;
- existência e intervalo de datas de `attendance` e `attendance_documentary`
  nas mesmas categorias;
- se o histórico legado de conteúdo está dentro/fora da janela de fallback do
  assignment atual;
- se a frequência canônica do assignment atual tem snapshot mínimo e tipo de
  `academic_year` compatível;
- causa estrutural provável da não projeção, sem qualquer remediação
  automática.

## Guardas obrigatórias

- MongoDB **somente leitura**;
- nenhuma chamada HTTP da aplicação;
- nenhuma escrita, backfill, migração, reconciliação, exclusão ou remapeamento;
- nenhum `attendance.records` é lido;
- nenhum estudante, matrícula ou status individual de frequência é
  lido/emitido;
- nenhum texto pedagógico de conteúdo é lido/emitido;
- nenhum valor de nota é lido;
- nenhum ID bruto de usuário, staff, assignment ou registro é emitido —
  somente fingerprints SHA-256 truncados;
- nenhuma alteração da política MT-1;
- execução planejada em `environment: production`, com issue owner-scoped e
  SHA exato de `main`, via SSH ao host de produção + `docker exec` no
  container de backend (mesmo mecanismo já usado por
  `ana-lucia-f2-1-runtime-legacy-audit.yml` e demais workflows da família —
  não expõe porta de MongoDB à internet).

## Contrato de autorização

O workflow `.github/workflows/luiz-gomes-f1-readonly-audit.yml` só executa a
auditoria de produção quando uma issue for aberta pelo dono do repositório
com:

- título exatamente `[LUIZ-GOMES-F1] <SHA-40-hex-de-main>`;
- corpo contendo, uma linha por campo, sem duplicatas:

```text
LUIZ_GOMES_F1=AUTHORIZED
CONFIRMATION=AUDIT_LUIZ_GOMES_READ_ONLY
ACADEMIC_YEAR=2026
TRACKING_ISSUE=<numero da issue de rastreamento>
TARGET_SHA=<mesmo SHA do titulo>
```

O workflow falha fechado se `main` tiver avançado desde a autorização, se
qualquer campo divergir, ou se a issue de rastreamento não existir/estiver
fechada.

## Artefatos

- coletor: `backend/scripts/luiz_gomes_f1_readonly_audit.py`;
- testes: `backend/tests/test_luiz_gomes_f1_readonly_audit.py`;
- workflow: `.github/workflows/luiz-gomes-f1-readonly-audit.yml`.

O resultado final deve ser uma matriz dos 6 pares com presença dos registros,
assignment de origem (somente fingerprint), projetabilidade estrutural e
códigos de causa — mesmo formato de saída da ANA-LUCIA-F1. Nenhuma correção
de dados está autorizada por este gate; um eventual saneamento exigirá uma
fase F2+ separada, nos mesmos moldes de `ANA_LUCIA_F2_*`.
