# SIGESC - Sistema Integrado de Gestão Escolar

## Problema Original
Sistema full-stack (React + FastAPI + MongoDB) para gestão escolar municipal.

## Arquitetura
- **Frontend:** React com Shadcn/UI, react-router-dom
- **Backend:** FastAPI com Motor (MongoDB async)
- **DB:** MongoDB

## Implementado (25/02/2026)
1. Escolas: "Aulas Complementares" → "Recomposição da Aprendizagem"
2. Alunos: Listagem exige seleção de escola ou busca
3. Alunos: comunidade_tradicional padrão "Não Pertence"
4. Alunos com deficiência: Seção "Matrícula em Atendimento/Programa" com cascata Escola → Tipo → Turma
5. AEE: Alunos matriculados em turma AEE aparecem no Diário AEE
6. **Cascata de programa:** Tipo de atendimento filtrado por programas disponíveis na escola selecionada

## Modelos Atualizados
- **StudentBase/Update:** atendimento_programa_school_id, atendimento_programa_tipo, atendimento_programa_class_id
- **SchoolBase/Update:** recomposicao_aprendizagem (boolean)

## Issues Pendentes
- P0: Deploy Coolify (infraestrutura)
- P3: Dashboard Analítico (pendente verificação)
- P4: Migração CAIXA ALTA

## Credenciais
- Admin: `gutenberg@sigesc.com` / `@Celta2007`
