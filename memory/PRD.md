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
22. **Tabela de Alunos**: Coluna "Escola" removida, coluna "Ano" adicionada entre Turma e Status
23. **Detalhes de Turma Multisseriada**: Fix student_series fallback para grade_level da turma. Distribuicao por Serie e coluna Serie agora mostram valores corretos.
24. **Tabela de Turmas**: Coluna "Ano Letivo" removida, filtro "Ano Letivo" adicionado com ano atual como padrao
25. **Aba Turma/Observacoes**: Campo "Ano/Serie" readonly adicionado entre Turma e Status. Mostra automaticamente o ano/serie da turma do aluno.
26. **Backend Enrollment**: Todas as criacoes de matricula agora incluem student_series automaticamente a partir do grade_level da turma.

## Regras de Negocio - Matricula
- Aluno pode ter APENAS 1 matricula ativa em turma regular por ano letivo
- Turmas especiais (AEE, Recomposicao, Reforco) sao excecao
- student_series definido automaticamente na criacao da matricula

## Regras de Negocio - Formulario de Turma
- Ordem: Ano Letivo > Escola > Tipo de Atendimento > Nome > Nivel de Ensino > Serie > Turno
- AEE/Recomposicao: sem nivel de ensino, multisseriada sempre disponivel, series de toda a escola

## Regras de Negocio - Componentes Curriculares
- Turmas regulares: componentes regulares
- Turmas em escola integral: regulares + integrais
- Turmas AEE: apenas componentes AEE

## Padrao de Bug Recorrente - Literal + Uppercase
- format_data_uppercase pode corromper campos Literal do Pydantic
- Campos Literal devem estar na lista LOWERCASE_FIELDS em text_utils.py
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
