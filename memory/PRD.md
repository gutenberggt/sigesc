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
17. Layout Certidao Civil (P0 RESOLVIDO): Campo Numero/Matricula aumentado (3 colunas), Livro e Folha reduzidos (1 coluna cada). Grid alterado de 4 para 6 colunas.
18. Lista de Turmas nao atualizava (P1 RESOLVIDO): Cache busting + atualizacao otimista.
19. **Bug Componentes Curriculares em Turmas Integrais (P0 RESOLVIDO):** Turmas com atendimento_programa='atendimento_integral' nao exibiam nenhum componente curricular na alocacao de professor. A correcao trata turmas integrais como regulares (temTurmaRegular=true) no filtro de componentes, permitindo que componentes regulares E integrais aparecam. Turmas AEE continuam mostrando apenas componentes AEE.

## Regras de Negocio - Matricula
- Aluno pode ter APENAS 1 matricula ativa em turma regular por ano letivo
- Turmas especiais (AEE, Recomposicao, Reforco) sao excecao
- Turmas especiais identificadas por atendimento_programa: 'aee', 'recomposicao_aprendizagem', 'reforco_escolar'

## Regras de Negocio - Componentes Curriculares
- Turmas regulares (sem programa): mostram componentes regulares
- Turmas regulares em escola integral: mostram regulares + integrais
- Turmas com atendimento_programa='atendimento_integral': mostram regulares + integrais
- Turmas AEE: mostram apenas componentes AEE
- Filtro por nivel_ensino e grade_levels tambem aplicado

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
