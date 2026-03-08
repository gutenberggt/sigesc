# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado (03/03/2026)
17. Layout Certidao Civil (P0 RESOLVIDO)
18. Lista de Turmas nao atualizava (P1 RESOLVIDO)
19. Bug Componentes Curriculares em Turmas Integrais (P0 RESOLVIDO)
20. Reestruturacao formulario Nova/Editar Turma (CONCLUIDO)
21. Bug "Erro ao salvar escola" (P0 RESOLVIDO)
22. Tabela de Alunos: coluna Escola removida, coluna Ano adicionada
23. Detalhes Turma Multisseriada: fix student_series
24. Tabela de Turmas: coluna Ano Letivo removida, filtro adicionado
25. Aba Turma/Observacoes: campo Ano/Serie readonly adicionado
26. Backend Enrollment: student_series automatico na criacao

## Implementado (08/03/2026)
27. **Selecao de serie em turma multisseriada (Novo Aluno):** Dropdown para escolher ano/serie ao matricular em turma multisseriada. Auto-set para turmas nao-multi. Campo presente em AMBOS os formularios (novo e editar).
28. **Exibicao de serie na edicao (Editar Aluno):** Campo Ano/Serie mostra o student_series especifico da matricula do aluno (nao todos os anos da turma). Para turma multisseriada, dropdown editavel. Para turma normal, campo readonly.
29. **Backend student_series completo:** GET /students/{id} retorna student_series da enrollment ativa. POST cria enrollment com student_series. PUT atualiza student_series na enrollment. student_series adicionado ao LOWERCASE_FIELDS.

## Regras de Negocio - Matricula
- Aluno pode ter APENAS 1 matricula ativa em turma regular por ano letivo
- student_series definido na criacao: valor enviado pelo frontend OU fallback para grade_level
- Para turma multisseriada: usuario escolhe o ano/serie no dropdown
- Para turma nao-multisseriada: auto-set para o grade_level da turma

## Regras de Negocio - Formulario de Turma
- Ordem: Ano Letivo > Escola > Tipo de Atendimento > Nome > Nivel de Ensino > Serie > Turno
- AEE/Recomposicao: sem nivel de ensino, multisseriada sempre disponivel

## Padrao de Bug Recorrente - Literal + Uppercase
- format_data_uppercase pode corromper campos Literal do Pydantic
- Modelos com campos Literal devem ter model_validator para normalizar valores

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
