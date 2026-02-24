# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal. Inclui gerenciamento de escolas, turmas, alunos, matrículas, frequência, notas, AEE, calendário letivo, servidores, e dashboards analíticos.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## O que foi implementado
### Sessão Anterior
- Acesso `ass_social`: Corrigido bug de busca de alunos, escolas e turmas
- Validação de CPF: Corrigido endpoint `check-cpf-duplicate`
- Dashboard `ass_social`: Dados de alunos "Não matriculados" ocultados
- Cancelar Matrícula: Implementado no frontend e backend
- Plano de AEE: Módulo totalmente reformulado
- Central de Tutoriais: Página de tutorial para Diário AEE
- Correção de acentuação no tutorial
- Branding: "Gutenberg Barroso" como desenvolvedor, logo SIGESC
- Dashboard Analítico: Lógica de contagem corrigida

### Sessão Atual (24/02/2026)
- **Bug Edição de Escolas:** CORRIGIDO - Removido campo duplicado "Situação de Funcionamento", unificado em "Status da Escola" com valores `active`/`inactive`. Testado e verificado via testing agent (100% pass rate).
- **Criação de Turmas:** Verificado funcionando corretamente via testes automatizados.

## Issues Pendentes
- **P0:** Deploy em produção (Coolify) - Bad Gateway após deploy (infraestrutura do servidor)
- **P3:** Inconsistência no Dashboard Analítico - Fix aplicado, pendente verificação do usuário
- **P4:** Migração CAIXA ALTA possivelmente incompleta - pendente verificação

## Tarefas Futuras
- Paginação na listagem de turmas
- Refatoração do `StudentsComplete.js`
- Envio de e-mail na pré-matrícula
- Refatoração do backend (extrair rotas do `server.py`)

## Credenciais
- Admin: `gutenberg@sigesc.com` / `@Celta2007`
