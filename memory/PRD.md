# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado (26/02/2026)
1. Escolas: "Aulas Complementares" → "Recomposição da Aprendizagem"
2. Alunos: Listagem exige seleção de escola ou busca
3. Alunos: comunidade_tradicional padrão "Não Pertence"
4. Alunos com deficiência: Seção "Matrícula em Atendimento/Programa" com cascata Escola → Tipo → Turma
5. AEE: Alunos matriculados em turma AEE aparecem no Diário AEE
6. Cascata de programa: Tipo de atendimento filtrado por programas disponíveis na escola
7. Página de Usuários Online (/admin/online-users)
8. Correções: auto-refresh, erro ao salvar escola, CAIXA ALTA universal, ESLint, turma AEE
9. **Papel SEMED 3 (semed3):** Acesso somente visualização. Sem acesso a Log de Conversas, Ferramentas, Mantenedora.
10. **SEMED 3 Analytics:** Ranking e Análise Comparativa.
11. **SEMED 3 Permissões extras:** Usuários Online e Avisos.
12. **Deploy Coolify:** Serviço mongo adicionado ao docker-compose.coolify.yml.
13. **Bug "Anexa a:":** Corrigido no backend e frontend.
14. **Upload de Imagem de Perfil:** Permissão ajustada.
15. **UI:** Breadcrumb "Início" em Usuários Online, rodapé fixo.

## Implementado (02/03/2026)
16. **Bug P0 Componentes Curriculares (RESOLVIDO):** Filtro de componentes na alocação de professores corrigido em `useStaff.js`:
    - **Filtro por atendimento_programa**: Turma AEE → só cursos AEE; Turma regular → só cursos regulares + integral (se escola suporta)
    - **Suporte a turmas multisseriadas**: Usa campo `series` (ex: ['1º ANO', '2º ANO', ...]) para matching de grade_levels
    - **Comparações case-insensitive**: nivel_ensino, grade_levels, atendimento_programa
    - Limite de listagem de cursos aumentado de 100 para 500

## Issues Pendentes
- P2: Dashboard Analítico (pendente verificação do usuário)

## Tarefas Futuras
- P1: Paginação na listagem de turmas
- P2: Refatorar StudentsComplete.js
- P2: Envio de e-mail na pré-matrícula
- P2: Refatoração backend (mover rotas do server.py)

## Credenciais
- Admin: `gutenberg@sigesc.com` / `@Celta2007`
- SEMED 3: `semed3@sigesc.com` / `semed123`
