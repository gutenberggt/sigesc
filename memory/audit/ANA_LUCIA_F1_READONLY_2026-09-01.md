# ANA-LUCIA-F1 — Auditoria forense read-only de conteúdo/frequência

## Autorização

Gate autorizado explicitamente pelo proprietário em 2026-09-01 e acompanhado pelo issue #304.

## Caso

Professora: **Ana Lucia Faria Pinto**. Relato: registros de conteúdo de datas anteriores e frequência não são exibidos em alguns vínculos, embora a professora informe que os lançou.

Alvos autorizados (2026):

1. 6º ANO A / Língua Inglesa
2. 6º ANO B / Língua Inglesa
3. 6º ANO C / Língua Inglesa
4. 6º ANO D / Língua Inglesa
5. 9º ANO A / Língua Inglesa
6. 9º ANO B / Língua Inglesa
7. 9º ANO C / Língua Inglesa
8. 9º ANO D / Língua Inglesa
9. 3ª ETAPA / Língua Inglesa
10. 4ª ETAPA / Língua Inglesa
11. 6º ANO C / Literatura e Redação
12. 6º ANO D / Literatura e Redação
13. 7º ANO B / Literatura e Redação
14. 7º ANO C / Literatura e Redação
15. 9º ANO C / Literatura e Redação
16. 7º ANO A / Estudos Amazônicos
17. 8º ANO C / Estudos Amazônicos

## Perguntas forenses

Para cada par, o coletor deve determinar somente por metadados estruturais:

- existência do vínculo legado ativo em `teacher_assignments`;
- existência de vínculos DVD atuais/históricos em `teacher_class_assignments`;
- existência e intervalo de datas de `learning_objects`;
- existência e intervalo de datas de `content_entries`, distinguindo assignment atual, histórico da mesma professora, sem assignment e outro/indeterminado;
- existência e intervalo de datas de `attendance` e `attendance_documentary` nas mesmas categorias;
- se o histórico legado de conteúdo está dentro/fora da janela de fallback do assignment atual;
- se frequência canônica do assignment atual tem snapshot mínimo e tipo de `academic_year` compatível;
- causa estrutural provável da não projeção, sem qualquer remediação automática.

## Guardas obrigatórias

- MongoDB **somente leitura**;
- nenhuma chamada HTTP da aplicação;
- nenhuma escrita, backfill, migração, reconciliação, exclusão ou remapeamento;
- nenhum `attendance.records` é lido;
- nenhum estudante, matrícula ou status individual de frequência é lido/emitido;
- nenhum texto pedagógico de conteúdo é lido/emitido;
- nenhum valor de nota é lido;
- nenhum ID bruto de usuário, staff, assignment ou registro é emitido;
- fingerprints SHA-256 truncados servem apenas para distinguir vínculos no artefato privado;
- nenhuma alteração da política MT-1;
- execução em `environment: production`, com issue owner-scoped, SHA exato de `main` e SSH host key pinado.

## Artefatos

- coletor: `backend/scripts/ana_lucia_f1_readonly_audit.py`;
- testes: `backend/tests/test_ana_lucia_f1_readonly_audit.py`;
- workflow: `.github/workflows/ana-lucia-f1-readonly-audit.yml`.

O resultado final deve ser uma matriz dos 17 pares com presença dos registros, assignment de origem (somente fingerprint), projetabilidade estrutural e códigos de causa. Nenhuma correção de dados está autorizada por este gate.
