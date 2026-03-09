# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado (08-09/03/2026)
27. Selecao de serie em turma multisseriada (Novo/Editar Aluno)
28. Exibicao de serie na edicao (Editar Aluno)
29. Backend student_series completo
30. **Correcao student_series em todas as views:**
    - **Detalhes da Turma (Distribuicao por Serie):** Agora conta corretamente alunos por serie individual (student_series da matricula), com comparacao case-insensitive
    - **Detalhes da Turma (Alunos Matriculados):** Mostra o student_series individual do aluno, nao o grade_level da turma
    - **Tabela de Alunos (coluna Ano):** Mostra o student_series individual do aluno via nova funcao getStudentSeries(), nao todas as series da turma
    - **Backend lista alunos:** Endpoint /api/students agora faz lookup na enrollment ativa e inclui student_series no response

## Regras de Negocio - student_series
- Cada aluno tem seu student_series individual armazenado na enrollment
- Para turma nao-multisseriada: auto-set para grade_level da turma
- Para turma multisseriada: usuario escolhe via dropdown
- Listagem de alunos: backend busca student_series das enrollments ativas via batch query
- Detalhes da turma: contagem por serie usa comparacao case-insensitive
- Fallback: se student_series nao definido e turma nao-multi, usa grade_level; se multi, mostra '-'

## Issues Pendentes
- P2: Dashboard Analitico (pendente verificacao do usuario)

## Tarefas Futuras
- P1: Paginacao na listagem de turmas
- P2: Refatorar StudentsComplete.js
- P2: Envio de e-mail na pre-matricula
- P2: Refatoracao backend (mover rotas do server.py)

## Credenciais
- Admin: gutenberg@sigesc.com / @Celta2007
- SEMED 3: semed3@sigesc.com / semed123
