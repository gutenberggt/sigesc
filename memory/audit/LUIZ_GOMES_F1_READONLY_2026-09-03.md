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

## Refinamento de escopo (2026-09-03)

O proprietário pediu precisão: verificar especificamente o registro de
conteúdo (`learning_objects`/`content_entries`) de fevereiro, março e abril de
2026, nas turmas 8º ANO A e 9º ANO A de Matemática. Diante de 3 opções
apresentadas (restringir a esses 2 pares, manter os 6 pares originais só
acrescentando o detalhamento mensal, ou abrir uma segunda auditoria em
paralelo), o proprietário escolheu **restringir o escopo aos 2 pares
pedidos**, reduzindo a superfície de leitura em produção. Os outros 4 pares
inicialmente propostos (6º ANO A/B, 7º ANO A/B) saem do escopo desta F1; se
necessário, podem virar uma auditoria própria depois, seguindo o mesmo
padrão.

Alvos finais (2026):

1. 8º ANO A / Matemática
2. 9º ANO A / Matemática

Além da matriz padrão por par (idêntica à ANA-LUCIA-F1), o coletor agora
também emite `content.learning_objects.monthly_breakdown_target_months` e
`content.content_entries.monthly_breakdown_target_months`: contagem de
documentos e de datas distintas para cada um dos 3 meses-alvo
(`TARGET_MONTHS = ("2026-02", "2026-03", "2026-04")`), sem abrir o texto
pedagógico — só a data de cada registro já lido.

## Relação com outros incidentes já rastreados

A mesma escola (E M E I E F Jose Pereira Barbosa) já aparece em
`memory/audit/P0_250_F2_PROFESSOR_PROMOTION_READONLY_AUDIT_2026-08-30.md`,
um incidente **diferente** (Livro de Promoção, professora Abadia Alves
Martins). A coincidência de escola é registrada aqui apenas como contexto; a
LUIZ-GOMES-F1 não assume a mesma causa raiz e não reaproveita nenhuma
conclusão daquele caso.

## Perguntas forenses

Idênticas à ANA-LUCIA-F1, reaplicadas aos 2 pares acima — para cada par, o
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

O resultado final deve ser uma matriz dos 2 pares com presença dos registros,
assignment de origem (somente fingerprint), projetabilidade estrutural,
códigos de causa e o detalhamento mensal de conteúdo (fev/mar/abr) descrito
acima. Nenhuma correção de dados está autorizada por este gate; um eventual
saneamento exigirá uma fase F2+ separada, nos mesmos moldes de
`ANA_LUCIA_F2_*`.
