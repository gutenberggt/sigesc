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
4. Alunos com deficiência: Seção "Matrícula em Atendimento/Programa"
5. AEE: Alunos matriculados em turma AEE aparecem no Diário AEE
6. Cascata de programa: Tipo de atendimento filtrado por programas
7. Página de Usuários Online (/admin/online-users)
8. Correções: auto-refresh, erro ao salvar escola, CAIXA ALTA, ESLint, turma AEE
9. Papel SEMED 3 com permissões de somente visualização
10. SEMED 3 Analytics: Ranking e Análise Comparativa
11. Deploy Coolify: Serviço mongo no docker-compose.coolify.yml
12. Bug "Anexa a:" corrigido (backend + frontend)
13. Upload de Imagem de Perfil: Permissão ajustada
14. UI: Breadcrumb "Início", rodapé fixo

## Implementado (02/03/2026)
15. **Bug P0 Componentes Curriculares (RESOLVIDO):** Filtro fiel à turma - atendimento_programa, series multisseriadas, case-insensitive
16. **Prevenção de Duplicidade de Matrícula (RESOLVIDO):**
    - Backend impede matrícula duplicada na mesma turma (HTTP 409)
    - Backend impede matrícula em turma regular quando aluno já tem matrícula ativa em outra regular (HTTP 409)
    - Backend PERMITE matrícula em turmas AEE, Recomposição da Aprendizagem, Reforço Escolar
    - Índice parcial único no MongoDB para prevenir race conditions
    - DuplicateKeyError handling para proteção de última camada
    - Frontend: Atualização imediata da lista local após matrícula
    - Frontend: Mensagens de erro claras do backend exibidas ao usuário

## Regras de Negócio - Matrícula
- Aluno pode ter APENAS 1 matrícula ativa em turma regular por ano letivo
- Turmas especiais (AEE, Recomposição, Reforço) são exceção - aluno pode ter matrículas simultâneas
- Turmas especiais identificadas por `atendimento_programa`: 'aee', 'recomposicao_aprendizagem', 'reforco_escolar'

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
