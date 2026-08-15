# Auditoria de Nomenclatura — “Aluno” × “Estudante”

**Data:** 2026-08-15  
**Baseline auditada:** `9f0564712f954f676753bd144c07850cf1f03c3b` (`main`)  
**Escopo:** auditoria e plano de saneamento. Nenhuma regra de negócio, schema, rota, permissão ou dado é alterado neste documento.

## 1. Decisão canônica

O SIGESC adota **ESTUDANTE** como termo institucional e canônico.

```text
PESSOA → ESTUDANTE → MATRÍCULA
identidade  contexto       vínculo temporal
civil       educacional    com escola/turma/ano
```

Consequências:

- interface, tutoriais, relatórios, documentos e mensagens institucionais devem usar **Estudante / Estudantes**;
- “Aluno” fica restrito a nome oficial externo, linguagem social excepcional ou legado técnico deliberadamente preservado;
- `student`, `students`, `student_id` não devem ser renomeados apenas por terminologia;
- o valor técnico de papel `aluno` pode permanecer por compatibilidade, mas o rótulo exibido deve ser **Estudante**;
- URLs, slugs e nomes de componentes legados não precisam ser renomeados quando isso trouxer risco sem benefício de UX.

## 2. Classes de decisão

| Classe | Significado | Ação |
|---|---|---|
| A — Visível institucional | UI, tutorial, PDF, declaração, mensagem humana de API | Corrigir para Estudante |
| B — Nome oficial externo | nome formal de órgão/programa/contrato externo | Preservar exatamente |
| C — Legado técnico | variável, papel, rota, slug, arquivo, componente, collection, campo | Não migrar nesta iniciativa |
| D — Evidência histórica | auditorias, changelog pretérito, test reports, snapshots | Não reescrever retroativamente |

**Regra de segurança:** é proibido fazer substituição global cega `aluno → estudante`.

## 3. Resultado executivo

A inconsistência é sistêmica, porém majoritariamente de apresentação. Foram confirmadas ocorrências em:

1. frontend e navegação;
2. trilhas de tutoriais;
3. PDFs e documentos institucionais;
4. mensagens humanas do backend/API.

A correção não exige migração de banco, `student_id`, collection `students`, IDs, autenticação ou rotas.

## 4. Navegação, papéis e dashboards — P0

### `frontend/src/pages/Users.js`

Confirmado:

- módulo `students` exibido como **“Alunos”**;
- valor técnico `role: 'aluno'`;
- rótulo `aluno: 'Aluno(a)'`.

Decisão:

```text
key students                  → manter
label "Alunos"               → "Estudantes"
role "aluno"                 → manter
rótulo visual "Aluno(a)"     → "Estudante"
```

### `frontend/src/pages/Dashboard.js`

Padronizar textos visíveis como:

- `Portal do Aluno` → **Portal do Estudante**;
- `Aluno(a)` → **Estudante**;
- `Alunos` → **Estudantes**;
- `Alunos Ativos` → **Estudantes Ativos**.

### Compatibilidade técnica

Podem permanecer:

- `AlunoDashboard`;
- `BoletimAluno`;
- rota `/aluno`;
- verificações de papel `aluno`.

Também revisar textos visíveis em `frontend/src/components/Layout.js`.

## 5. Gestão cadastral e matrícula — P0

Ocorrências confirmadas em:

- `frontend/src/pages/Students.js`;
- `frontend/src/pages/StudentsComplete.js`;
- `frontend/src/pages/Classes.js`;
- `frontend/src/pages/Enrollments.js`;
- `frontend/src/pages/EnrollmentAudit.jsx`;
- `frontend/src/pages/HistoryReconstruction.jsx`;
- `frontend/src/pages/Guardians.js`;
- `frontend/src/pages/PreMatriculaManagement.jsx`.

Exemplos:

```text
"Novo(a) Aluno(a)" → "Novo Estudante"
"Alunos Ativos"    → "Estudantes Ativos"
"Total de Alunos"  → "Total de Estudantes"
"Nome do Aluno"    → "Nome do Estudante"
```

Identificadores `Students`, `student_id`, `student_series` e `studentsAPI` permanecem.

## 6. Notas, frequência e acompanhamento — P0/P1

Ocorrências confirmadas em:

- `frontend/src/pages/Grades.js`;
- `frontend/src/components/grades/AlunoTab.jsx`;
- `frontend/src/pages/Attendance.js`;
- `frontend/src/components/attendance/AlertasTab.jsx`;
- `frontend/src/components/attendance/InformacoesTab.jsx`;
- `frontend/src/pages/Promotion.jsx`;
- `frontend/src/pages/PmeAnosFinais.jsx`.

`AlunoTab.jsx` pode manter o nome técnico; a aba/rótulo visível deve ser **Estudante**.

## 7. Gestão social, saúde e outras áreas — P1

Ocorrências confirmadas em:

- `frontend/src/pages/BolsaFamilia.js`;
- `frontend/src/pages/AssocialDashboard.js`;
- `frontend/src/pages/VaccineDashboard.js`;
- `frontend/src/pages/Announcements.js`;
- `frontend/src/pages/DocumentValidator.jsx`;
- `frontend/src/pages/AdminTools.js`;
- `frontend/src/pages/SchoolsComplete.js`;
- `frontend/src/pages/VerifyHistory.jsx`;
- `frontend/src/pages/VerifyBulletin.jsx`.

Textos próprios do SIGESC usam **Estudante**; citações e nomes formais externos são preservados.

## 8. Tutoriais — P0

Arquivos confirmados:

- `frontend/src/pages/TutorialsPage.jsx`;
- `frontend/src/pages/tutorials/secretaryTutorials.js`;
- `frontend/src/pages/tutorials/directorTutorials.js`;
- `frontend/src/pages/tutorials/coordinatorTutorials.js`;
- `frontend/src/pages/tutorials/TutorialTransferencia.jsx`.

Exemplos:

```text
"Alunos(as)"                       → "Estudantes"
"Acesso ao portal do aluno"       → "Acesso ao Portal do Estudante"
"Consulta de alunos da turma"     → "Consulta de estudantes da turma"
"acompanhamento escolar do aluno" → "acompanhamento escolar do estudante"
"Consulta de notas do aluno"      → "Consulta de notas do estudante"
```

Na trilha de Secretários também há mistura interna, como:

```text
"cards resumem escolas, alunos, turmas..." → estudantes
"Escolas, Turmas, Alunos..."               → Estudantes
"fora da ficha do aluno"                   → estudante
"botão de novo aluno"                      → novo estudante
"criar outro aluno"                        → outro estudante
```

Slugs já publicados (`cadastro-aluno`, `documentos-aluno`) podem permanecer por compatibilidade.

## 9. PDFs e documentos institucionais — P0/P1

Ocorrências confirmadas em:

- `backend/pdf/boletim.py`;
- `backend/pdf/ficha_individual.py`;
- `backend/pdf/certificado.py`;
- `backend/pdf/notas.py`;
- `backend/pdf/turma.py`;
- `backend/pdf/livro_promocao.py`;
- `backend/pdf/dossie_institucional.py`;
- `backend/pdf/historico_escolar.py`;
- `backend/pdf/plano_aee.py`;
- `backend/pdf/diario_aee.py`;
- `backend/pdf/declaracoes.py`;
- `backend/pdf/transfer_receipt.py`.

Renderizadores/serviços relacionados:

- `backend/services/bulletin_renderer.py`;
- `backend/services/history_renderer.py`;
- `backend/services/school_docs_service.py`.

Padronizar, quando forem rótulos próprios do SIGESC:

```text
"Nome do Aluno"   → "Nome do Estudante"
"Total de Alunos" → "Total de Estudantes"
"Aluno(a)"        → "Estudante"
```

Modelos externos literais devem ser verificados antes de alteração.

## 10. Mensagens backend/API — P1

A expressão `Aluno não encontrado` foi confirmada em diversos endpoints/serviços, incluindo:

- `backend/routers/students.py`;
- `backend/routers/bulletins.py`;
- `backend/routers/bulletin_pdf.py`;
- `backend/routers/closure.py`;
- `backend/routers/student_history.py`;
- `backend/routers/history_pdf.py`;
- `backend/routers/vaccines.py`;
- `backend/routers/aee.py`;
- `backend/routers/admin.py`;
- `backend/routers/documents.py`;
- `backend/routers/grades.py`;
- `backend/routers/student_health.py`;
- `backend/routers/maintenance.py`;
- `backend/routers/student_dependencies.py`;
- `backend/routers/attendance.py`;
- `backend/routers/attendance_ext.py`;
- `backend/routers/medical_certificates.py`;
- `backend/routers/student_intelligence.py`;
- `backend/services/school_docs_service.py`;
- `backend/services/bulletin_renderer.py`;
- `backend/services/history_renderer.py`.

Exemplos:

```text
"Aluno não encontrado"    → "Estudante não encontrado"
"Aluno transferido..."    → "Estudante transferido..."
"Este aluno já possui..." → "Este estudante já possui..."
```

Ao alterar mensagens:

1. manter status HTTP, códigos e estrutura do payload;
2. localizar testes/assertions dependentes do texto literal;
3. atualizar somente testes ativos necessários;
4. verificar que frontend não usa a string como regra de negócio.

## 11. Legado técnico que deve permanecer

### Banco/domínio

- collection `students`;
- `student_id`;
- `student_series`;
- `studentsAPI`;
- classes/DTOs `Student*`.

### Papel/autorização

- valor técnico `role = "aluno"`;
- comparações `userRole === 'aluno'`;
- regras de permissão que dependam desse valor.

O rótulo visual correspondente é **Estudante**.

### Rotas

- `/aluno` e rotas legadas associadas ao portal.

### Componentes/arquivos

- `AlunoDashboard.jsx`;
- `BoletimAluno.jsx`;
- `AlunoTab.jsx`.

### Slugs

- `cadastro-aluno`;
- `documentos-aluno`;
- outros slugs já divulgados.

## 12. Evidência histórica

Não executar substituição retroativa em massa em:

- `memory/audit/**` históricos;
- entradas pretéritas de `memory/CHANGELOG.md`;
- homologações antigas;
- `test_reports/**`;
- outputs CSV/JSON de scripts;
- snapshots/evidências anteriores.

Esses artefatos registram o estado histórico do sistema.

Documentação viva deve ser revisada separadamente, preservando identificadores técnicos. Exemplos:

- `docs/HISTORICO_ESCOLAR_CONTRACT.md`;
- `docs/STUDENT_DEPENDENCY.md`;
- `README.md` quando houver linguagem institucional atual.

## 13. Matriz de substituição

| Atual | Padrão SIGESC |
|---|---|
| Aluno | Estudante |
| Aluna | Estudante |
| Aluno(a) | Estudante |
| Alunos | Estudantes |
| Alunos(as) | Estudantes |
| Novo(a) Aluno(a) | Novo Estudante |
| Nome do Aluno | Nome do Estudante |
| Dados do Aluno | Dados do Estudante |
| Portal do Aluno | Portal do Estudante |
| Total de Alunos | Total de Estudantes |
| Alunos Ativos | Estudantes Ativos |
| Aluno não encontrado | Estudante não encontrado |

Evitar `Estudante(a)`: **estudante** já é substantivo comum de dois gêneros.

## 14. Plano de saneamento

### N1 — UI + Tutoriais — P0

Tudo que o usuário lê na aplicação web passa a usar Estudante.

Não alterar papel `aluno`, rota `/aluno`, nomes de componentes ou `student*`.

### N2 — PDFs e documentos — P0/P1

Padronizar documentos emitidos pelo SIGESC: boletim, ficha, histórico, declarações, certificado, AEE, livro de promoção, relatórios e comprovantes.

### N3 — Mensagens backend/API — P1

Padronizar mensagens humanas, preservando contrato estrutural e atualizando testes dependentes de texto.

### N4 — Documentação viva + prevenção — P1

- revisar documentação viva;
- preservar documentação histórica;
- adicionar guard de nomenclatura ao CI;
- usar allowlist para exceções técnicas deliberadas.

## 15. Guard de nomenclatura recomendado

Após N1–N3, criar verificação automática para novos usos visíveis de:

```text
Aluno
Alunos
Aluno(a)
Alunos(as)
```

O guard deve aceitar allowlist explícita para:

- valor técnico `aluno`;
- rota `/aluno`;
- nomes de arquivo/componente legados;
- identificadores técnicos;
- documentos históricos;
- nomes oficiais externos documentados.

## 16. Critérios de aceite

1. menus, cards, labels, botões, títulos e ajuda usam **Estudante**;
2. papel técnico continua `aluno`, exibido como **Estudante**;
3. Central e tutoriais usam **Estudante**;
4. PDFs/documentos próprios do SIGESC usam **Estudante**;
5. mensagens humanas da API usam **Estudante**;
6. rotas, IDs, collections e schemas continuam compatíveis;
7. nenhuma migração de banco é necessária;
8. testes funcionais permanecem verdes;
9. evidência histórica permanece íntegra;
10. guard evita regressão futura.

## 17. Conclusão

**Diagnóstico:** a decisão institucional “Estudante” ainda não está aplicada integralmente ao produto.

**Risco:** baixo a moderado se a correção for feita por camadas; alto se feita por substituição global.

**Recomendação:** executar N1 → N2 → N3 → N4 em PRs pequenos e certificados.

> No SIGESC, **Estudante** é a linguagem institucional. Identificadores `student*` e o valor técnico `aluno` podem permanecer como implementação legada estável, desde que não definam a experiência textual oferecida ao usuário.
