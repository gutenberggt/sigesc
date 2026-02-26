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
9. **Papel SEMED 3 (semed3):** Implementado com acesso somente visualização a: Dashboard, Escolas, Turmas, Alunos, Servidores, Componentes Curriculares, Usuários, Diário AEE, Frequência, Notas, Calendário, Avisos, Analytics, Usuários Online. Sem acesso a: Log de Conversas, Ferramentas, Mantenedora. Todos botões CRUD ocultos.
10. **SEMED 3 Analytics:** Ranking de Escolas (Score V2.1) e Análise Comparativa por Bloco (Top 5 Escolas) exibidos para SEMED 3 no Dashboard Analítico.
11. **SEMED 3 Permissões extras:** Acesso a Usuários Online e permissão para criar/enviar Avisos (Novo Aviso).

## Modelos Atualizados
- **UserRole:** Inclui 'semed3' no Literal de roles permitidos
- **StudentBase/Update:** atendimento_programa_school_id, atendimento_programa_tipo, atendimento_programa_class_id
- **SchoolBase/Update:** recomposicao_aprendizagem (boolean)

## Issues Pendentes
- P0: Deploy Coolify — RESOLVIDO: docker-compose.coolify.yml reescrito (removidos networks, container_name, ports). Instruções de configuração fornecidas.
- P1: Criação de Turmas não atualiza lista consistentemente
- P2: Dashboard Analítico (pendente verificação do usuário)
- P2: Migração CAIXA ALTA (pendente verificação do usuário)

## Tarefas Futuras
- P1: Paginação na listagem de turmas
- P2: Refatorar StudentsComplete.js
- P2: Envio de e-mail na pré-matrícula
- P2: Refatoração backend (mover rotas do server.py)

## Credenciais
- Admin: `gutenberg@sigesc.com` / `@Celta2007`
- SEMED 3 (teste): `semed3test@sigesc.com` / `Semed3Test123`
