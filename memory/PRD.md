# SIGESC - Sistema Integrado de Gestao Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestao escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado (26/02/2026)
1. Escolas: "Aulas Complementares" -> "Recomposicao da Aprendizagem"
2. Alunos: Listagem exige selecao de escola ou busca
3. Alunos: comunidade_tradicional padrao "Nao Pertence"
4. Alunos com deficiencia: Secao "Matricula em Atendimento/Programa"
5. AEE: Alunos matriculados em turma AEE aparecem no Diario AEE
6. Cascata de programa: Tipo de atendimento filtrado por programas
7. Pagina de Usuarios Online (/admin/online-users)
8. Correcoes: auto-refresh, erro ao salvar escola, CAIXA ALTA, ESLint, turma AEE
9. Papel SEMED 3 com permissoes de somente visualizacao
10. SEMED 3 Analytics: Ranking e Analise Comparativa
11. Deploy Coolify: Servico mongo no docker-compose.coolify.yml
12. Bug "Anexa a:" corrigido (backend + frontend)
13. Upload de Imagem de Perfil: Permissao ajustada
14. UI: Breadcrumb "Inicio", rodape fixo

## Implementado (02/03/2026)
15. Bug P0 Componentes Curriculares (RESOLVIDO)
16. Prevencao de Duplicidade de Matricula (RESOLVIDO)

## Implementado (03/03/2026)
17. Layout Certidao Civil (P0 RESOLVIDO)
18. Lista de Turmas nao atualizava (P1 RESOLVIDO)
19. Bug Componentes Curriculares em Turmas Integrais (P0 RESOLVIDO)
20. Reestruturacao formulario Nova/Editar Turma (CONCLUIDO)
21. **Bug "Erro ao salvar escola" (P0 RESOLVIDO):**
    - Campos Literal (zona_localizacao, tipo_unidade, status) armazenados em MAIUSCULAS no DB causavam falha na validacao Pydantic
    - Adicionado model_validator(mode='before') em SchoolBase e SchoolUpdate para normalizar campos Literal para minusculas automaticamente
    - Corrige tanto dados corrompidos vindos do DB (GET/resposta) quanto dados em maiusculas enviados pelo frontend (PUT/entrada)

## Regras de Negocio - Matricula
- Aluno pode ter APENAS 1 matricula ativa em turma regular por ano letivo
- Turmas especiais (AEE, Recomposicao, Reforco) sao excecao

## Regras de Negocio - Formulario de Turma
- Ordem: Ano Letivo > Escola > Tipo de Atendimento > Nome > Nivel de Ensino > Serie > Turno
- AEE/Recomposicao: sem nivel de ensino, multisseriada sempre disponivel, series de toda a escola
- Regular/Integral/Reforco: fluxo normal com nivel de ensino obrigatorio

## Regras de Negocio - Componentes Curriculares
- Turmas regulares: mostram componentes regulares
- Turmas em escola integral: regulares + integrais
- Turmas AEE: apenas componentes AEE

## Padrao de Bug Recorrente - Literal + Uppercase
- O utilitario format_data_uppercase pode corromper campos Literal do Pydantic
- Campos Literal devem estar na lista LOWERCASE_FIELDS em text_utils.py
- Modelos com campos Literal devem ter model_validator para normalizar valores
- Dados ja corrompidos no DB de producao precisam de normalizacao na leitura

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
